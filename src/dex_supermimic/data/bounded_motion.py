"""Bounded reference storage; shard switches invalidate all replay frame indices.

This module does not start training or modify checkpoints. Feature packs are made
by the unchanged MotionLib, and swaps retain tensor shapes, addresses and methods.
"""
from pathlib import Path
import json, time
import torch
from instanttrack.motion import MotionLib
from dex_supermimic.common import atomic, sha

FRAME_FIELDS = ('root_p','root_R','root_v','root_w','q','qd','body_p','body_R',
                'body_v','body_w','root_v_local','root_w_local','clip_id','frame_bin')
CLIP_FIELDS = ('clip_len','clip_start','clip_end')
BIN_FIELDS = ('bin_clip','bin_start','bin_prior')

def pack_motion(motion):
    return dict(format='bones-motion-features-v1', names=motion.names,
                cuda_matmul_allow_tf32=bool(torch.backends.cuda.matmul.allow_tf32),
                num_frames=motion.num_frames, num_bins=motion.num_bins,
                tensors={k:getattr(motion,k).detach().cpu().contiguous()
                         for k in FRAME_FIELDS+CLIP_FIELDS+BIN_FIELDS})

def build_pack(manifest, kin, robot, device):
    rows=manifest['records']
    assert rows and all(x['split']=='train' and x['grade']=='A_kinematic_candidate' for x in rows)
    for x in rows: assert sha(x['output'])==x['output_sha256'], x['id']
    lib=MotionLib([x['output'] for x in rows],kin,device,robot.load_motion)
    assert lib.names==[x['id'] for x in rows]
    assert lib.num_frames==sum(x['frames'] for x in rows)
    weights=torch.tensor([manifest['weights'][x] for x in lib.names],device=device)
    bins=torch.bincount(lib.bin_clip,minlength=len(rows))
    lib.bin_prior.copy_(weights[lib.bin_clip]/bins[lib.bin_clip])
    lib.bin_prior.div_(lib.bin_prior.sum())
    pack=pack_motion(lib)
    pack['source_hashes']={x['id']:x['output_sha256'] for x in rows}
    return pack,lib

class BoundedMotionLib(MotionLib):
    def __init__(self, pack, device, frame_capacity=600000):
        self.device=device;self.frame_capacity=frame_capacity
        self.clip_capacity=frame_capacity//33+1
        # With >=33 frames per clip, ceil((n-1)/50) <= n/25.
        self.bin_capacity=frame_capacity//25+1
        for names,capacity in [(FRAME_FIELDS,frame_capacity),(CLIP_FIELDS,self.clip_capacity),(BIN_FIELDS,self.bin_capacity)]:
            for name in names:
                t=pack['tensors'][name]
                setattr(self,name,torch.zeros((capacity,)+t.shape[1:],device=device,dtype=t.dtype))
        self.root_gz=self.root_R[:,2,2]
        self.num_bins=self.bin_capacity
        self.generation=0
        self.replace(pack)

    def validate_pack(self,pack):
        assert pack['format']=='bones-motion-features-v1'
        assert pack['cuda_matmul_allow_tf32'] is True,'Feature precision must match the existing training configuration'
        n=pack['num_frames'];c=len(pack['names']);b=pack['num_bins'];t=pack['tensors']
        assert 0<n<=self.frame_capacity and 0<c<=self.clip_capacity and 0<b<=self.bin_capacity
        assert len(set(pack['names']))==c and (t['clip_len']>=33).all()
        assert int(t['clip_len'].sum())==n and int(t['clip_end'][-1])==n-1
        assert torch.equal(t['clip_start'][1:],t['clip_end'][:-1]+1)
        assert torch.all((t['clip_id']>=0)&(t['clip_id']<c))
        assert torch.all((t['bin_clip']>=0)&(t['bin_clip']<c))
        assert torch.all((t['frame_bin']>=0)&(t['frame_bin']<b))
        assert torch.all(t['bin_prior']>0) and abs(float(t['bin_prior'].sum())-1)<1e-5
        for names,count in [(FRAME_FIELDS,n),(CLIP_FIELDS,c),(BIN_FIELDS,b)]:
            for name in names:
                src=t[name];dst=getattr(self,name)
                assert src.device.type=='cpu' and src.shape==(count,)+dst.shape[1:] and src.dtype==dst.dtype,name
                assert torch.isfinite(src).all(),name

    @torch.no_grad()
    def replace(self,pack):
        self.validate_pack(pack)
        if str(self.device).startswith('cuda'):torch.cuda.synchronize()
        started=time.monotonic()
        for name in FRAME_FIELDS+CLIP_FIELDS+BIN_FIELDS:
            dst=getattr(self,name);src=pack['tensors'][name]
            dst.zero_();dst[:len(src)].copy_(src)
        self.names=list(pack['names']);self.num_frames=pack['num_frames'];self.active_num_bins=pack['num_bins']
        self.generation+=1
        if str(self.device).startswith('cuda'):torch.cuda.synchronize()
        return time.monotonic()-started

def switch_shard(motion,pack,env,buffer,obs_hist):
    """Call between collection/update iterations; warm up again before sampling."""
    assert env.motion is motion and env.mdp.motion is motion
    motion.validate_pack(pack)  # Reject invalid packs before altering any live state.
    seconds=motion.replace(pack)
    buffer.ptr=buffer.size=0  # Old transitions contain reference frame indices.
    env.bin_G.zero_();env.bin_fail.zero_();env.bin_w_avg.copy_(motion.bin_prior)
    prev=torch.arange(motion.num_bins,device=motion.device)-1
    env.bin_prev.copy_(torch.where((prev>=0)&(motion.bin_clip[prev.clamp(min=0)]==motion.bin_clip),prev,prev+1))
    env.done_eval.zero_();env.failed_eval.zero_();obs_hist.zero_()
    env.reset(torch.arange(env.N,device=motion.device));env.refresh()
    return dict(copy_seconds=seconds,generation=motion.generation,frames=motion.num_frames,
                clips=len(motion.names),replay_size=buffer.size,warmup_required=True)
