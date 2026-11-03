"""Keep difficulty by source ID and relative one-second bin across reference swaps."""
from pathlib import Path
import json,time,torch
from dex_supermimic.training.rotation_async import AsyncRotation

class PersistentRotation(AsyncRotation):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.bin_memory={};self.env=None
    def capture(self):
        if self.env is None:return
        m=self.motion;b=m.active_num_bins
        counts=torch.bincount(m.bin_clip[:b],minlength=len(m.names)).cpu().tolist()
        data=torch.stack((self.env.bin_G[:b],self.env.bin_fail[:b],self.env.bin_w_avg[:b]/m.bin_prior[:b].clamp(min=1e-12)),1).detach().cpu()
        start=0
        for name,n in zip(m.names,counts):
            self.bin_memory[name]=data[start:start+n].clone();start+=n
    def restore(self):
        m=self.motion;e=self.env;b=m.active_num_bins
        counts=torch.bincount(m.bin_clip[:b],minlength=len(m.names)).cpu().tolist()
        data=torch.zeros((b,3));data[:,2]=1.;start=restored=0
        for name,n in zip(m.names,counts):
            if name in self.bin_memory:
                value=self.bin_memory[name];assert value.shape==(n,3)
                data[start:start+n]=value;restored+=n
            start+=n
        data=data.to(m.device);e.bin_G.zero_();e.bin_fail.zero_();e.bin_w_avg.zero_()
        e.bin_G[:b].copy_(data[:,0]);e.bin_fail[:b].copy_(data[:,1])
        e.bin_w_avg[:b].copy_(data[:,2].clamp(.001,1000)*m.bin_prior[:b]);e.bin_w_avg.div_(e.bin_w_avg.sum().clamp(min=1e-12))
        return restored
    def bind(self,env):
        self.env=env
        if self.bin_memory:
            self.restore();env.reset(torch.arange(env.N,device=self.motion.device));env.refresh()
    def checkpoint_state(self):
        self.capture();state=super().checkpoint_state();state['difficulty_memory']=self.bin_memory;state['difficulty_schema']='source-id-relative-second-v1';return state
    def before_iteration(self,ns,iteration):
        now=time.monotonic()
        if self.next_at is None:self.next_at=now+getattr(self,'resume_delay',self.interval);return
        if now<self.next_at:return
        started=time.monotonic();index=(self.current+1)%len(self.index['records']);pack,prep=self.prefetch.take(index)
        self.capture();self.flush_coverage(ns['args'].log_dir)
        m=self.motion;e=self.env;seconds=m.replace(pack);ns['buffer'].ptr=ns['buffer'].size=0
        restored=self.restore()
        prev=torch.arange(m.num_bins,device=m.device)-1
        e.bin_prev.copy_(torch.where((prev>=0)&(m.bin_clip[prev.clamp(min=0)]==m.bin_clip),prev,prev+1))
        e.done_eval.zero_();e.failed_eval.zero_();ns['obs_hist'].zero_()
        e.reset(torch.arange(e.N,device=m.device));e.refresh()
        self.current=index;self.cycles+=int(index==0);self.prefetch.start((index+1)%len(self.index['records']))
        ns['stats']={k:[] for k in ns['stats']};ns['agg']={k:[] for k in ns['agg']}
        warm=time.monotonic();ns['collect'](self.switch_warmup_steps,ns['stats']);torch.cuda.synchronize()
        report=dict(copy_seconds=seconds,generation=m.generation,frames=m.num_frames,clips=len(m.names),replay_size=ns['buffer'].size,
                    restored_difficulty_bins=restored,remembered_clips=len(self.bin_memory),prefetch=prep,warmup_seconds=time.monotonic()-warm,
                    total_pause_seconds=time.monotonic()-started,iteration=iteration,shard=index,cycles=self.cycles,warmup_steps=self.switch_warmup_steps)
        self.next_at=time.monotonic()+self.interval
        with (Path(ns['args'].log_dir)/'shard_switches.jsonl').open('a') as f:f.write(json.dumps(report)+'\n')
