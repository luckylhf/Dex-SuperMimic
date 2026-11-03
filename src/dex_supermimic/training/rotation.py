"""Training integration hook for prepared reference shards; imported only on explicit launch."""
from pathlib import Path
import json,time
import torch
from dex_supermimic.data.bounded_motion import BoundedMotionLib,switch_shard
from dex_supermimic.common import sha
from dex_supermimic.paths import ASSETS
import instanttrack.motion, instanttrack.kinematics

class Rotation:
    def __init__(self,dataset,interval_seconds=300,start_index=0,allow_fixture=False):
        self.directory=Path(dataset);self.index=json.loads((self.directory/'features/index.json').read_text())
        for row in self.index['records']:
            for key in ('pack','manifest'):
                path=Path(row[key])
                row[key]=str(path if path.is_absolute() else self.directory/path)
        self.dataset_sha256=sha(self.directory/'manifest.json')
        assert self.dataset_sha256==self.index['dataset_manifest_sha256']
        for key,path in [('robot_xml_sha256',ASSETS/'mjcf/dex_29.xml'),
                         ('model_contract_sha256',ASSETS/'model.json'),
                         ('motion_code_sha256',Path(instanttrack.motion.__file__)),
                         ('kinematics_code_sha256',Path(instanttrack.kinematics.__file__))]:
            assert sha(path)==self.index[key],'Feature cache contract changed: '+key
        manifest=json.loads((self.directory/'manifest.json').read_text())
        assert (manifest['complete'] and not manifest['snapshot']) or (allow_fixture and manifest.get('fixture_only') is True),'Incomplete production release'
        self.interval=interval_seconds;self.current=start_index%len(self.index['records']);self.cycles=0;self.next_at=None
        self.motion=None

    def load_pack(self,index):
        row=self.index['records'][index]
        assert sha(row['pack'])==row['pack_sha256']
        assert sha(row['manifest'])==row['manifest_sha256']
        # Own tensor-only cache, produced from hashed motion files during preparation.
        return torch.load(row['pack'],map_location='cpu',weights_only=True)

    def initial(self,device):
        self.motion=BoundedMotionLib(self.load_pack(self.current),device,self.index['frame_capacity'])
        return self.motion

    def before_iteration(self,ns,iteration):
        now=time.monotonic()
        if self.next_at is None:self.next_at=now+getattr(self,'resume_delay',self.interval);return
        if now<self.next_at:return
        index=(self.current+1)%len(self.index['records'])
        report=switch_shard(self.motion,self.load_pack(index),ns['env'],ns['buffer'],ns['obs_hist'])
        self.current=index;self.cycles+=int(index==0)
        # Statistics and replay transitions from different references must not be mixed.
        ns['stats']={k:[] for k in ns['stats']};ns['agg']={k:[] for k in ns['agg']}
        ns['collect'](ns['args'].warmup_steps,ns['stats'])
        self.next_at=time.monotonic()+self.interval
        report.update(iteration=iteration,shard=index,cycles=self.cycles,refilled_steps=ns['buffer'].size)
        with (Path(ns['args'].log_dir)/'shard_switches.jsonl').open('a') as f:f.write(json.dumps(report)+'\n')

    def checkpoint_state(self):
        return dict(dataset_sha256=self.dataset_sha256,shard=self.current,cycles=self.cycles,
                    interval_seconds=self.interval,generation=self.motion.generation,
                    seconds_until_switch=max(0,self.next_at-time.monotonic()) if self.next_at is not None else self.interval)
