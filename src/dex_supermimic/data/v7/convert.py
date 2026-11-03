#!/usr/bin/env python3
"""Convert SOMA/LAFAN/mocap BVH to a named-joint Dex PKL, entirely on CPU."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','1')
import argparse,hashlib,json,pickle,time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .bvh import load
from .source import adapt
from .robot import Robot,DEFAULT_MODEL,DEFAULT_URDF
from .contacts import prepare
from .solver import solve,constrain_support
from .arms import plan_and_refine
from .anatomy import configure

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def convert(bvh,output,source='auto',model=DEFAULT_MODEL,fps=None,config=None,max_frames=None,no_contacts=False):
    start=time.monotonic();output=Path(output)
    if output.exists():raise FileExistsError('Refusing to overwrite '+str(output))
    cfg=json.loads((ROOT/'config.json').read_text()) if config is None else json.loads(Path(config).read_text())
    motion=load(bvh,fps=fps)
    if max_frames:motion.local_p=motion.local_p[:max_frames];motion.local_r=motion.local_r[:max_frames]
    if len(motion.local_p)<3:raise ValueError('Conversion needs at least 3 frames; one-frame poses are calibration-only')
    robot=Robot(model);configure(robot,cfg['anatomy']);t=prepare(adapt(motion,source),robot,cfg['contact'],enabled=not no_contacts)
    x,records=solve(robot,t,cfg['solver'],lambda i,n:print(f'{output.stem}: {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    x,support_reports=constrain_support(robot,t,x,cfg['solver'],lambda i,n:print(f'{output.stem}: support {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    x,arm_report=plan_and_refine(robot,t,x,cfg['solver'],lambda side,phase,i,n:print(f'{output.stem}: {side} {phase} {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    quat=Rotation.from_matrix(t['root_r']).as_quat()
    for i in range(1,len(quat)):
        if quat[i]@quat[i-1]<0:quat[i]*=-1
    payload={'fps':motion.fps,'root_pos':x[:,:3].astype(np.float32),'root_rot':quat.astype(np.float32),
        'dof_pos':x[:,3:].astype(np.float32),'joint_names':robot.names,'quat_order':'xyzw',
        'local_body_pos':None,'link_body_list':None}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(pickle.dumps(payload,protocol=4))
    np.savez_compressed(output.with_suffix('.npz'),**{k:v for k,v in payload.items() if v is not None})
    diagnostics={'root_target':t['root_p'],'root_r':t['root_r'],'torso_target':t['torso_r'],'solver_records':records}
    for s,v in t['sides'].items():
        for k in ('foot_target_p','foot_target_r','raw_foot_p','raw_foot_r','contact','phase','anchors','pivots','heel','toe','heel_speed','toe_speed','thigh','shin','upper','lower','elbow_axis','signed_elbow_bend','hand_forward','hand_width','forearm_width'):
            diagnostics[s+'_'+k]=v[k]
    np.savez_compressed(output.with_suffix('.diagnostics.npz'),**diagnostics)
    meta={'converter_version':7,'generation_mode':'full_v7_from_original_bvh',
        'input':str(Path(bvh).resolve()),'input_sha256':sha(bvh),'source_type':t['source_type'],
        'input_frames':motion.input_frames,'input_fps':motion.input_fps,'output_frames':len(x),'output_fps':motion.fps,
        'model':robot.path,'model_sha256':sha(robot.path),'viewer_urdf':DEFAULT_URDF,'viewer_urdf_sha256':sha(DEFAULT_URDF),
        'joint_names':robot.names,'quat_order':'xyzw','units':'metres/radians','cpu_only':True,
        'official_reference_commit':'cbdb2b494a2af82137bf9b6f15122d60167281c4','official_runtime':False,
        'configuration':cfg,'contacts_enabled':not no_contacts,'source_floor_m':t['floor'],'leg_scale':t['scale'],
        'ground_calibration':t['ground_calibration'],
        'world_origin':t['world_origin'].tolist(),'source_calibration':{s:{k:v[k] for k in ('foot_calibration','hand_method','elbow_calibration')} for s,v in t['sides'].items()},
        'wrist_limits':robot.wrist_limit_record,
        'estimated_contact_segments':{s:v['segments'] for s,v in t['sides'].items()},
        'arm_branch_planning':arm_report,
        'support_constraint_failures':support_reports,
        'elapsed_s':time.monotonic()-start,'output_sha256':sha(output),
        'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(list(ROOT.glob('*.py'))+[ROOT/'config.json'])},
        'limits':'Kinematic reference only; contact inferred; flat floor assumed; no dynamics/self-collision certification.'}
    output.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bvh');p.add_argument('output');p.add_argument('--source',choices=['auto','soma','lafan','mocap'],default='auto')
    p.add_argument('--model',default=DEFAULT_MODEL);p.add_argument('--fps',type=float,default=None,help='Default preserves source fps; resampling uses local-rotation SLERP')
    p.add_argument('--config');p.add_argument('--max-frames',type=int);p.add_argument('--no-contacts',action='store_true',help='Ablation only')
    a=p.parse_args();m=convert(**vars(a));print(json.dumps({k:m[k] for k in ('output_frames','output_fps','elapsed_s')},ensure_ascii=False))
