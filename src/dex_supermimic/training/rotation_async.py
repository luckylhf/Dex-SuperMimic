"""Reference rotation with checked background loading and staged pinned transfer."""
import json,time
from pathlib import Path
import torch
from dex_supermimic.training.rotation import Rotation
from dex_supermimic.data.bounded_motion import BoundedMotionLib,switch_shard,FRAME_FIELDS,CLIP_FIELDS,BIN_FIELDS
from dex_supermimic.training.prefetch import PackPrefetch

class StagedMotion(BoundedMotionLib):
    def __init__(self,*a,**kw):
        self._validation_token=object();super().__init__(*a,**kw)
    def validate_pack(self,pack):
        if pack.get('_validated_for') is self._validation_token:return
        BoundedMotionLib.validate_pack(self,pack)
        pack['_validated_for']=self._validation_token
    @torch.no_grad()
    def replace(self,pack):
        self.validate_pack(pack)
        torch.cuda.synchronize();started=time.monotonic()
        for k in FRAME_FIELDS+CLIP_FIELDS+BIN_FIELDS:
            dst=getattr(self,k);src=pack['tensors'][k];dst.zero_();dst[:len(src)].copy_(src,non_blocking=src.is_pinned())
        self.names=list(pack['names']);self.num_frames=pack['num_frames'];self.active_num_bins=pack['num_bins'];self.generation+=1
        torch.cuda.synchronize();return time.monotonic()-started

class AsyncRotation(Rotation):
    def initial(self,device):
        self.motion=StagedMotion(self.load_pack(self.current),device,self.index['frame_capacity'])
        self.motion.generation=getattr(self,'resume_generation',self.motion.generation)
        self.prefetch=PackPrefetch(self.index,self.motion.validate_pack)
        self.prefetch.start((self.current+1)%len(self.index['records']))
        self.coverage={};self.coverage_clips=torch.zeros(self.motion.clip_capacity,dtype=torch.long,device=device)
        self.coverage_bins=torch.zeros(self.motion.num_bins,dtype=torch.long,device=device)
        return self.motion
    @torch.no_grad()
    def record_frames(self,frames):
        ones=torch.ones_like(frames)
        self.coverage_clips.index_add_(0,self.motion.clip_id[frames],ones)
        self.coverage_bins.index_add_(0,self.motion.frame_bin[frames],ones)
    def flush_coverage(self,log_dir):
        counts=self.coverage_clips[:len(self.motion.names)].cpu().tolist()
        seen=self.coverage_bins[:self.motion.active_num_bins].cpu().tolist()
        clips=self.motion.bin_clip[:self.motion.active_num_bins].cpu().tolist()
        starts=self.motion.bin_start[:self.motion.active_num_bins].cpu().tolist()
        clip_starts=self.motion.clip_start[:len(self.motion.names)].cpu().tolist()
        for name,n in zip(self.motion.names,counts):
            if n:self.coverage.setdefault(name,dict(environment_steps=0,bins_seen=set()))['environment_steps']+=n
        for count,clip,start in zip(seen,clips,starts):
            if count:
                name=self.motion.names[clip]
                self.coverage.setdefault(name,dict(environment_steps=0,bins_seen=set()))['bins_seen'].add((start-clip_starts[clip])//50)
        self.coverage_clips.zero_();self.coverage_bins.zero_()
        rows={name:dict(environment_steps=r['environment_steps'],one_second_bins_seen=sorted(r['bins_seen'])) for name,r in self.coverage.items()}
        p=Path(log_dir)/'motion_coverage.json';tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(visited_clips=len(rows),total_environment_steps=sum(x['environment_steps'] for x in rows.values()),clips=rows)))
        tmp.replace(p)
    def before_iteration(self,ns,iteration):
        now=time.monotonic()
        if self.next_at is None:self.next_at=now+getattr(self,'resume_delay',self.interval);return
        if now<self.next_at:return
        started=time.monotonic();index=(self.current+1)%len(self.index['records'])
        pack,prep=self.prefetch.take(index)
        self.flush_coverage(ns['args'].log_dir)
        report=switch_shard(self.motion,pack,ns['env'],ns['buffer'],ns['obs_hist'])
        self.current=index;self.cycles+=int(index==0)
        self.prefetch.start((index+1)%len(self.index['records']))
        ns['stats']={k:[] for k in ns['stats']};ns['agg']={k:[] for k in ns['agg']}
        warm_steps=getattr(self,'switch_warmup_steps',ns['args'].warmup_steps)
        assert warm_steps>=max(ns['args'].wm_window,ns['args'].hist)
        warm=time.monotonic();ns['collect'](warm_steps,ns['stats']);torch.cuda.synchronize()
        report.update(prefetch=prep,warmup_seconds=time.monotonic()-warm,total_pause_seconds=time.monotonic()-started,
                      iteration=iteration,shard=index,cycles=self.cycles,refilled_steps=ns['buffer'].size,warmup_steps=warm_steps)
        self.next_at=time.monotonic()+self.interval
        with (Path(ns['args'].log_dir)/'shard_switches.jsonl').open('a') as f:f.write(json.dumps(report)+'\n')
