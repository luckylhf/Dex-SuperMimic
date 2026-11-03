"""Dex adapter using the existing tg3 actuator profile and verified motion contract."""
from pathlib import Path
import hashlib
import json
import os
import re

import mujoco
import numpy as np
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from instanttrack.dr import DomainRandCfg
from instanttrack.robot import RobotSpec

from dex_supermimic.paths import ROOT, ASSETS
XML = ASSETS / 'mjcf/dex_29.xml'
MANIFEST = json.loads((ASSETS / 'model.json').read_text())
NAMES = tuple(MANIFEST['joint_names'])
TRACKED = ('pelvis','hip_roll_l_link','knee_pitch_l_link','ankle_roll_l_link',
           'hip_roll_r_link','knee_pitch_r_link','ankle_roll_r_link','waist_pitch_link',
           'shoulder_roll_l_link','elbow_pitch_l_link','wrist_roll_l_link',
           'shoulder_roll_r_link','elbow_pitch_r_link','wrist_roll_r_link')
GROUPS = (
    (r'hip_pitch_.*_joint',600.,15.,.24),(r'hip_roll_.*_joint',600.,15.,.24),
    (r'hip_yaw_.*_joint',350.,10.,.18),(r'knee_pitch_.*_joint',650.,14.,.37),
    (r'ankle_pitch_.*_joint',60.,7.,.032),(r'ankle_roll_.*_joint',35.,3.,.032),
    (r'shoulder_pitch_.*_joint',150.,5.,.1),(r'shoulder_roll_.*_joint',50.,2.5,.1),
    (r'shoulder_yaw_.*_joint',50.,2.5,.1),(r'elbow_pitch_.*_joint',150.,5.,.1),
    (r'elbow_yaw_.*_joint',500.,15.,.1),(r'wrist_pitch_.*_joint',200.,8.,.0236),
    (r'wrist_roll_.*_joint',200.,8.,.0236),(r'waist_.*_joint',400.,10.,.17),
)
DEFAULT = {r'hip_pitch_.*_joint':-.05,r'knee_pitch_.*_joint':.05,
           r'ankle_pitch_.*_joint':-.05,'shoulder_roll_l_joint':.1,
           'shoulder_roll_r_joint':-.1,r'elbow_pitch_.*_joint':-.1}

def profile(name):
    values=[(kp,kd,arm) for pat,kp,kd,arm in GROUPS if re.fullmatch(pat,name)]
    if len(values)!=1:raise ValueError(f'Actuator profile ambiguous for {name}')
    return values[0]

def get_spec():
    spec=mujoco.MjSpec.from_file(str(XML))
    for sensor in list(spec.sensors):
        if sensor.name.endswith('_joint_torque'):spec.delete(sensor)
    for actuator in list(spec.actuators):spec.delete(actuator)
    for geom in list(spec.worldbody.geoms):spec.delete(geom)
    return spec

def get_robot_cfg():
    acts=tuple(BuiltinPositionActuatorCfg(target_names_expr=(n,),stiffness=profile(n)[0],
               damping=profile(n)[1],armature=profile(n)[2],frictionloss=0.,viscous_damping=0.,
               effort_limit=float(MANIFEST['joint_limits'][n]['effort'])) for n in NAMES)
    return EntityCfg(spec_fn=get_spec,sort_actuators=True,
        init_state=EntityCfg.InitialStateCfg(pos=(0.,0.,.97),joint_pos=DEFAULT,joint_vel={'.*':0.}),
        articulation=EntityArticulationInfoCfg(actuators=acts,soft_joint_pos_limit_factor=1.))

def load_dex_npz(path):
    with np.load(path,allow_pickle=False) as z:
        if tuple(z['joint_names'].tolist())!=NAMES:raise ValueError(f'{path}: joint order')
        if str(z['model_sha256'])!=MANIFEST['model_sha256']:raise ValueError(f'{path}: model hash')
        if str(z['quat_order'])!='wxyz' or float(z['fps'])!=50.:raise ValueError(f'{path}: frame convention')
        root=z['body_names'].tolist().index('pelvis')
        p,q,j=z['body_pos_w'][:,root].copy(),z['body_quat_w'][:,root].copy(),z['joint_pos'].copy()
        if len(j)<33 or not all(np.isfinite(x).all() for x in (p,q,j)):raise ValueError(f'{path}: invalid motion')
        return p,q,j,50.

SPEC=RobotSpec(name='dex',mjcf_path=str(XML),joint_names=NAMES,tracked_bodies=TRACKED,
    # A common radian scale preserves reference feed-through under the upstream +/-20 action cap.
    # The old torque/kp scale made elbow/wrist reference actions exceed 120. PD gains are unchanged.
    default_joint_pos=DEFAULT,action_scale={n:.25 for n in NAMES},
    com_body='waist_pitch_link',com_range=((-0.01,.01),(-.01,.01),(-.01,.01)),
    robot_cfg=get_robot_cfg,motion_dir=str(ROOT/'data/bones_seed/processed/motions'),motion_glob='*.npz',
    load_motion=load_dex_npz,njmax=1000,nconmax=256,
    dr=DomainRandCfg(friction_range=(.7,1.2),joint_offset={'.*':.005},
        reset_pos=(.02,.02,.005),reset_rot=(.05,.05,.1),reset_lin_vel=(.15,.15,.05),
        reset_ang_vel=(.15,.15,.2),reset_joint_pos=.03))
