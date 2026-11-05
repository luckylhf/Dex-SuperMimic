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
from .solver import solve,constrain_support as legacy_support
from .support_fast import constrain_support as hybrid_support
from .arms import plan_and_refine
from .contact_solver import refine as refine_body_contacts
from .anatomy import configure
from .self_collision import refine as refine_self_collision, audit_export as audit_self_collision

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def support_solver(cfg):
    mode=cfg.get('support_refinement','hybrid_cpu_v1')
    if mode=='hybrid_cpu_v1':return hybrid_support
    if mode=='legacy_slsqp':return legacy_support
    raise ValueError('Unknown support_refinement: '+str(mode))

def convert(bvh,output,source='auto',model=DEFAULT_MODEL,fps=None,config=None,max_frames=None,no_contacts=False):
    start=time.monotonic();output=Path(output)
    if output.exists():raise FileExistsError('Refusing to overwrite '+str(output))
    cfg=json.loads((ROOT/'config.json').read_text()) if config is None else json.loads(Path(config).read_text())
    constrain_support=support_solver(cfg['solver'])
    motion=load(bvh,fps=fps)
    if max_frames:motion.local_p=motion.local_p[:max_frames];motion.local_r=motion.local_r[:max_frames]
    if len(motion.local_p)<3:raise ValueError('Conversion needs at least 3 frames; one-frame poses are calibration-only')
    robot=Robot(model);configure(robot,cfg['anatomy']);t=prepare(adapt(motion,source),robot,cfg['contact'],enabled=not no_contacts)
    x,records=solve(robot,t,cfg['solver'],lambda i,n:print(f'{output.stem}: {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    x,support_reports=constrain_support(robot,t,x,cfg['solver'],lambda i,n:print(f'{output.stem}: support {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    x,arm_report=plan_and_refine(robot,t,x,cfg['solver'],lambda side,phase,i,n:print(f'{output.stem}: {side} {phase} {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    x,body_contact_reports=refine_body_contacts(robot,t,x,cfg['solver'],lambda i,n:print(f'{output.stem}: body_contacts {i}/{n} {time.monotonic()-start:.1f}s',flush=True))
    support_reports.extend(body_contact_reports)
    x,collision_report=refine_self_collision(robot,t,x,cfg['solver'],cfg.get('self_collision'),
        lambda i,n:print(f'{output.stem}: self_collision {i}/{n}',flush=True))
    quat=Rotation.from_matrix(t['root_r']).as_quat()
    for i in range(1,len(quat)):
        if quat[i]@quat[i-1]<0:quat[i]*=-1
    payload={'fps':motion.fps,'root_pos':x[:,:3].astype(np.float32),'root_rot':quat.astype(np.float32),
        'dof_pos':x[:,3:].astype(np.float32),'joint_names':robot.names,'quat_order':'xyzw',
        'local_body_pos':None,'link_body_list':None}
    collision_report['export_check']=audit_self_collision(robot,payload,cfg.get('self_collision'))
    from ..quality_v8 import adjacent_speed_report
    velocity_check = adjacent_speed_report(payload['dof_pos'], motion.fps, robot.names, robot.speed_limits)
    if velocity_check['violating_intervals']:
        raise ValueError('Final exported trajectory exceeds per-axis joint speed limits: '+str(velocity_check))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(pickle.dumps(payload,protocol=4))
    np.savez_compressed(output.with_suffix('.npz'),**{k:v for k,v in payload.items() if v is not None})
    diagnostics={'root_target':t['root_p'],'root_r':t['root_r'],'torso_target':t['torso_r'],'solver_records':records}
    support_stats=getattr(robot,'support_fast_report',None)
    if support_stats is not None:
        diagnostics['support_route']=np.array([{'bypass':0,'light':1,'fallback':2}[v['route']] for v in support_stats['frames']],dtype=np.uint8)
        diagnostics['support_qp_steps']=np.array([v['qp_steps'] for v in support_stats['frames']],dtype=np.int32)
        diagnostics['support_light_stop_reason']=np.array([v['light_stop_reason'] for v in support_stats['frames']])
        diagnostics['support_fallback_triggers']=np.array(['|'.join(v['fallback_triggers']) for v in support_stats['frames']])
        diagnostics['support_final_feasible']=np.array([v['final_feasible'] for v in support_stats['frames']],dtype=bool)
        # Detailed diagnostics remain JSON-readable without pickle-enabled NPZ.
        output.with_suffix('.support.json').write_text(json.dumps(support_stats,ensure_ascii=False,indent=2))
    for s,v in t['sides'].items():
        for k in ('foot_target_p','foot_target_r','raw_foot_p','raw_foot_r','contact','phase','anchors','pivots','heel','toe','heel_speed','toe_speed','thigh','shin','upper','lower','elbow_axis','signed_elbow_bend','hand_forward','hand_width','forearm_width','ground_contact_confidence'):
            diagnostics[s+'_'+k]=v[k]
    diagnostics['source_expected_contact']=t['source_expected_contact'];diagnostics['source_airborne']=t['source_airborne']
    for contact in t['body_contacts']:
        for k in ['mode','confidence','anchors','source_surface_height','source_surface_point']:diagnostics['body_'+contact['body_name']+'_'+k]=contact[k]
    np.savez_compressed(output.with_suffix('.diagnostics.npz'),**diagnostics)
    from ..retarget import CONVERTER_RELEASE,SOLVER_POLICY
    meta={'converter_version':8,'generation_mode':'full_v8_from_original_bvh','pose_solver':'dex_v8_per_axis_velocity','converter_release':CONVERTER_RELEASE,'solver_policy':SOLVER_POLICY,
        'input':str(Path(bvh).resolve()),'input_sha256':sha(bvh),'source_type':t['source_type'],
        'input_frames':motion.input_frames,'input_fps':motion.input_fps,'output_frames':len(x),'output_fps':motion.fps,
        'model':robot.path,'model_sha256':sha(robot.path),'viewer_urdf':DEFAULT_URDF,'viewer_urdf_sha256':sha(DEFAULT_URDF),
        'joint_names':robot.names,'quat_order':'xyzw','units':'metres/radians','cpu_only':True,
        'official_reference_commit':'cbdb2b494a2af82137bf9b6f15122d60167281c4','official_runtime':False,
        'configuration':cfg,'contacts_enabled':not no_contacts,'source_floor_m':t['floor'],'leg_scale':t['scale'],
        'ground_calibration':t['ground_calibration'],'multicontact':t['multicontact_record'],
        'body_contact_solver':robot.body_contact_qp_summary,
        'body_contact_task_policy':'bounded extra-body normal cues with existing foot support, linear body support without foot plants; independent hard mesh clearance and foot XYZ constraints',
        'body_contact_models':[{k:v for k,v in c.items() if k not in ('mode','confidence','anchors','source_surface_height','source_surface_point')} for c in t['body_contacts']],
        'world_origin':t['world_origin'].tolist(),'source_calibration':{s:{k:v[k] for k in ('foot_calibration','hand_method','elbow_calibration')} for s,v in t['sides'].items()},
        'wrist_limits':robot.wrist_limit_record,
        'estimated_contact_segments':{s:v['segments'] for s,v in t['sides'].items()},
        'arm_branch_planning':arm_report,
        'self_collision':collision_report,
        'support_constraint_failures':support_reports,
        'support_branch_relaxations':robot.support_branch_relaxations,
        'support_refinement':cfg['solver'].get('support_refinement','hybrid_cpu_v1'),
        'support_refinement_statistics':{k:v for k,v in support_stats.items() if k!='frames'} if support_stats is not None else None,
        'joint_velocity_limits_rad_s':dict(zip(robot.names,robot.speed_limits.tolist())),
        'solver_velocity_check':velocity_check,
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
