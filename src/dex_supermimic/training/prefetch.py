"""Bounded CPU LRU plus one pinned staging pack. No GPU work in the loader thread."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import torch
from dex_supermimic.common import sha

class PackPrefetch:
    def __init__(self,index,validate,budget_bytes=8*1024**3,pin=True):
        self.rows=index['records'];self.validate=validate;self.budget=budget_bytes;self.pin=pin
        self.cache=OrderedDict();self.bytes=0;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='reference-prefetch')
        self.future=None;self.pending=None;self.history=[]

    def _load(self,index):
        row=self.rows[index];started=time.monotonic();path=Path(row['pack']);s=path.stat()
        key=(index,s.st_ino,s.st_size,s.st_mtime_ns);hit=key in self.cache
        if hit:
            pack,n=self.cache.pop(key);self.cache[key]=(pack,n)
        else:
            assert sha(path)==row['pack_sha256'],'Feature pack hash mismatch'
            assert sha(row['manifest'])==row['manifest_sha256'],'Shard manifest hash mismatch'
            pack=torch.load(path,map_location='cpu',weights_only=True)
            self.validate(pack)
            n=sum(t.numel()*t.element_size() for t in pack['tensors'].values())
            while self.cache and self.bytes+n>self.budget:
                _,(_,old)=self.cache.popitem(last=False);self.bytes-=old
            if n<=self.budget:self.cache[key]=(pack,n);self.bytes+=n
        staged=dict(pack,tensors={k:(v.pin_memory() if self.pin else v) for k,v in pack['tensors'].items()})
        self.validate(staged)
        return staged,dict(index=index,cache_hit=hit,prepare_seconds=time.monotonic()-started,
                          cached_bytes=self.bytes,pinned_bytes=sum(t.numel()*t.element_size() for t in staged['tensors'].values()) if self.pin else 0)

    def start(self,index):
        assert self.future is None,'Previous prefetch must be consumed first'
        self.pending=index;self.future=self.pool.submit(self._load,index)

    def take(self,index):
        if self.future is None:self.start(index)
        assert self.pending==index
        started=time.monotonic();pack,report=self.future.result();report['foreground_wait_seconds']=time.monotonic()-started
        self.future=None;self.pending=None;self.history.append(report)
        return pack,report

    def close(self):
        self.pool.shutdown(wait=True,cancel_futures=True);self.future=None;self.cache.clear();self.bytes=0
