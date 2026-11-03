"""Prime IK on a held first pose before recording a clip; preserve the original motion time."""
from pathlib import Path
import argparse
import json
import pickle
import sys
import numpy as np

import os
if not os.environ.get('DEX_GMR_ROOT'):
    raise RuntimeError('Set DEX_GMR_ROOT to the Dex-GMR checkout; see data/README.md')
GMR=Path(os.environ['DEX_GMR_ROOT']).expanduser().resolve()
sys.path.insert(0,str(GMR));sys.path.insert(0,str(GMR/'scripts'))
from retarget_motion import retarget_frames
from general_motion_retargeting.utils.lafan1 import load_soma_file

def convert(source,output,warm_frames=None):
    source=Path(source);output=Path(output)
    if output.exists():raise FileExistsError(output)
    output.parent.mkdir(exist_ok=True,parents=True)
    frames,height,fps=load_soma_file(str(source))
    if fps is None:raise ValueError('Missing frame time')
    if warm_frames is None:warm_frames=round(2*fps)
    if warm_frames<2:raise ValueError('At least two priming frames are required')
    attempts=[]
    for count in (warm_frames,warm_frames*2,warm_frames*4):
        temporary=output.with_name(output.stem+f'.priming_{count}.pkl')
        retarget_frames([frames[0]]*count+frames,fps,'bvh_soma',height,temporary,
                        use_velocity_limit=True,use_collision_avoidance=True,ik_recovery='table-retry')
        # Only read the pickle just produced by this process.
        with temporary.open('rb') as f:motion=pickle.load(f)
        priming_root_speed=float(np.linalg.norm(motion['root_pos'][count-1]-motion['root_pos'][count-2])*fps)
        priming_joint_speed=float(np.max(np.abs(motion['dof_pos'][count-1]-motion['dof_pos'][count-2]))*fps)
        attempts.append(dict(frames=count,final_root_speed_m_s=priming_root_speed,
                             final_joint_speed_rad_s=priming_joint_speed))
        if priming_root_speed<=.02:
            warm_frames=count
            break
    # This guards the observed root startup defect. Joint limits and velocities
    # still require the existing final-NPZ checker; priming is not a feasibility proof.
    if priming_root_speed>.02:
        raise ValueError(f'Root did not settle during priming: {priming_root_speed} m/s')
    for key in ['root_pos','root_rot','dof_pos']:
        assert len(motion[key])==warm_frames+len(frames)
        motion[key]=motion[key][warm_frames:]
    motion['ik_priming_frames']=warm_frames
    motion['ik_priming_final_root_speed_m_s']=priming_root_speed
    motion['ik_priming_final_joint_speed_rad_s']=priming_joint_speed
    motion['ik_priming_method']='repeat first source pose before recording; no source motion frames dropped'
    audit=json.loads(temporary.with_suffix('.ik.json').read_text())
    audit['priming_events']=[e for e in audit['events'] if int(e['frame'])<warm_frames]
    audit['events']=[dict(e,frame=int(e['frame'])-warm_frames) for e in audit['events'] if int(e['frame'])>=warm_frames]
    audit['status_counts_including_priming']=audit.pop('status_counts')
    audit.update(requested_frames=len(frames),completed_frames=len(frames),priming_frames=warm_frames,
                 priming_attempts=attempts,
                 status_counts_scope='See status_counts_including_priming; retained-motion recovery events are reindexed separately')
    output.parent.mkdir(exist_ok=True,parents=True)
    with output.open('wb') as f:pickle.dump(motion,f)
    output.with_suffix('.ik.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True)
    p.add_argument('--warm-frames',type=int,default=None);a=p.parse_args()
    convert(a.input,a.output,a.warm_frames)
