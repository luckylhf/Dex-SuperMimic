"""Unchanged screening and compact serialization functions copied from bones_control_v1."""
from pathlib import Path
import json,threading
import numpy as np
import mujoco
from dex_supermimic.paths import ASSETS
TLS=threading.local()
REFERENCE_SOURCE_SHA256='02237ba4553e24d1d286e6235f91836c3a55699e069f0f97195ae9fffd7c8d43'

def compact(source, target):
    with np.load(source, allow_pickle=False) as z:
        root = z['body_names'].tolist().index('pelvis')
        arrays = {k: z[k] for k in ('joint_pos', 'joint_names', 'model_sha256', 'fps', 'quat_order')}
        arrays.update(body_names=np.array(['pelvis']), body_pos_w=z['body_pos_w'][:, root:root+1],
                      body_quat_w=z['body_quat_w'][:, root:root+1], storage_format=np.array('root_joint_lossless_v1'))
        with Path(str(target)+'.tmp').open('wb') as f: np.savez_compressed(f, **arrays)
        with np.load(str(target)+'.tmp', allow_pickle=False) as check:
            assert all(np.array_equal(check[k], v, equal_nan=True) if v.dtype.kind in 'fc'
                       else np.array_equal(check[k], v) for k, v in arrays.items())
    Path(str(target)+'.tmp').replace(target)
    return len(arrays['joint_pos'])

def quality(npz, ik_path):
    flags = []
    ik = json.loads(ik_path.read_text()) if ik_path.exists() else None
    if ik is None: flags.append('missing_ik_audit')
    later = sum(int(e['frame']) > 0 for e in ik['events']) if ik else None
    if later: flags.append('ik_recovery_after_first_frame')
    if ik is None or ik.get('priming_frames',0)<60:
        flags.append('missing_ik_priming')
    with np.load(npz, allow_pickle=False) as z:
        root=z['body_names'].tolist().index('pelvis')
        q = z['joint_pos']; p = z['body_pos_w'][:, root]; quat = z['body_quat_w'][:, root]
        speed = np.linalg.norm(z['body_lin_vel_w'][:, root], axis=1)
        omega = float(np.linalg.norm(z['body_ang_vel_w'][:, root], axis=1).max())
        velocity=root_velocity_audit(p,float(z['fps']))
        flags.extend(velocity['flags'])
        if len(q) < 33: flags.append('too_short_for_training_window')
        if omega > 8: flags.append('root_angular_speed_above_provisional_8rad_s')
        if not hasattr(TLS, 'model'):
            TLS.model = mujoco.MjModel.from_xml_path(str(ASSETS/'mjcf/dex_29.xml'))
            TLS.data = mujoco.MjData(TLS.model)
            TLS.floor = mujoco.mj_name2id(TLS.model, mujoco.mjtObj.mjOBJ_GEOM, 'floor')
            TLS.feet = [mujoco.mj_name2id(TLS.model, mujoco.mjtObj.mjOBJ_GEOM,
                         f'ankle_roll_{side}_link_collision_{i}') for side in ('l','r') for i in range(7)]
            assert TLS.floor >= 0 and min(TLS.feet) >= 0
        minimum = float('inf'); penetrations = floating = longest = 0
        both_air = air_run = max_air = 0
        for f in range(len(q)):
            TLS.data.qpos[:3] = p[f]; TLS.data.qpos[3:7] = quat[f]; TLS.data.qpos[7:] = q[f]
            mujoco.mj_forward(TLS.model, TLS.data)
            zmin = min(mujoco.mj_geomDistance(TLS.model, TLS.data, TLS.floor, j, 10, None) for j in TLS.feet)
            minimum = min(minimum, zmin); penetrations += zmin < -.02
            floating = floating+1 if zmin > .05 and speed[f] < .2 else 0
            longest = max(longest, floating)
            air_run = air_run+1 if zmin > .05 else 0
            both_air += zmin > .05; max_air = max(max_air, air_run)
        if penetrations: flags.append('foot_penetration_below_minus_2cm')
        if longest >= 25: flags.append('stationary_floating_over_half_second')
        return dict(flags=flags, frames=len(q), ik_later_events=later, root_angular_speed_max_rad_s=omega,
                    root_velocity=velocity, priming_frames=ik.get('priming_frames') if ik else None,
                    min_foot_clearance_m=minimum, penetration_frames=int(penetrations),
                    stationary_floating_max_frames=longest, both_feet_above_5cm_fraction=both_air/len(q),
                    both_feet_above_5cm_longest_seconds=max_air/50)

def root_velocity_audit(p,fps):
    """Independent finite differences catch recorded IK initialization jumps."""
    speed=np.linalg.norm(np.diff(p,axis=0),axis=1)*fps
    first=speed[:max(1,round(fps))]
    later=speed[max(1,round(fps)):]
    later_p95=float(np.percentile(later,95)) if len(later) else float(np.percentile(speed,95))
    flags=[]
    if not np.isfinite(speed).all():flags.append('nonfinite_root_speed')
    if float(speed.max())>8:flags.append('root_linear_speed_above_provisional_8m_s')
    if float(first.max())>max(8,5*later_p95):flags.append('root_startup_velocity_spike')
    return dict(initial_m_s=float(speed[0]),maximum_m_s=float(speed.max()),
                first_second_maximum_m_s=float(first.max()),later_p95_m_s=later_p95,flags=flags)
