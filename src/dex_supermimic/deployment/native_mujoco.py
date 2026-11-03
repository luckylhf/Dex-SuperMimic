"""CPU MuJoCo plant with the exact compiled training model and no support force."""
import json
import os
from pathlib import Path
import mujoco
import numpy as np
from dex_supermimic.deployment.runtime import sha, quat_to_mat


class Plant:
    def __init__(self, controller):
        c = controller.contract
        self.evaluation_profile = os.environ.get('DEX_EVALUATION_PROFILE', 'strict_v1')
        if self.evaluation_profile not in ('strict_v1', 'height_diagnostic_v1'):
            raise ValueError('Unknown evaluation termination profile')
        self.height_stop_enabled = self.evaluation_profile == 'strict_v1'
        model_path = controller.bundle / 'model.mjb'
        if sha(model_path) != c['compiled_model_sha256']: raise ValueError('Compiled model hash mismatch')
        if mujoco.__version__ != c['mujoco_version']: raise ValueError('MuJoCo binary version mismatch')
        self.model = m = mujoco.MjModel.from_binary_path(str(model_path))
        self.data = d = mujoco.MjData(m)
        self.controller = controller
        joints = [m.joint('robot/'+n).id for n in c['joint_names']]
        self.qadr, self.vadr = m.jnt_qposadr[joints], m.jnt_dofadr[joints]
        self.aids = np.array([int(np.flatnonzero(m.actuator_trnid[:, 0] == j)[0]) for j in joints])
        if len(set(self.aids)) != len(joints): raise ValueError('Ambiguous actuator mapping')
        root = np.flatnonzero(m.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
        if len(root) != 1: raise ValueError('Expected exactly one floating root')
        self.rq, self.rv = int(m.jnt_qposadr[root[0]]), int(m.jnt_dofadr[root[0]])
        self.body_ids = [m.body('robot/'+n).id for n in c['tracked_bodies']]
        r = controller.reference
        d.qpos[self.qadr] = np.clip(r['q'][0], m.jnt_range[joints, 0], m.jnt_range[joints, 1])
        d.qvel[self.vadr] = r['qd'][0]
        d.qpos[self.rq:self.rq+3] = r['root_p'][0]
        quat = np.zeros(4); mujoco.mju_mat2Quat(quat, r['root_R'][0].astype(np.float64).reshape(9))
        d.qpos[self.rq+3:self.rq+7] = quat
        d.qvel[self.rv:self.rv+3] = r['root_v'][0]
        d.qvel[self.rv+3:self.rv+6] = r['root_R'][0].T @ r['root_w'][0]
        d.ctrl[self.aids] = d.qpos[self.qadr]
        d.xfrc_applied[:] = 0; d.qfrc_applied[:] = 0
        mujoco.mj_forward(m, d)
        self.errors = []
        self.trajectory = [d.qpos.copy()]

    def sensors(self):
        d = self.data
        if self.controller.root_feedback:
            self.controller.root_position = d.qpos[self.rq:self.rq+3].copy()
        return d.qpos[self.qadr].copy(), d.qvel[self.vadr].copy(), d.qpos[self.rq+3:self.rq+7].copy(), d.qvel[self.rv+3:self.rv+6].copy()

    def step(self, target):
        self.data.ctrl[self.aids] = target
        for _ in range(self.controller.contract['decimation']):
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
            raise FloatingPointError('Non-finite physical state')
        if np.any(self.data.xfrc_applied) or np.any(self.data.qfrc_applied):
            raise AssertionError('Unexpected external support force')
        self.trajectory.append(self.data.qpos.copy())

    def measure(self, frame):
        c = self.controller.contract; ref = self.controller.reference; d = self.data
        p = d.qpos[self.rq:self.rq+3]; R = quat_to_mat(d.qpos[self.rq+3:self.rq+7])
        rz = ref['root_p'][frame, 2]; Rr = ref['root_R'][frame]
        height_error = abs(p[2]-rz)
        tilt_error = abs(R[2, 2]-Rr[2, 2])
        height_violation = bool(height_error > c['term_height'])
        tilt_violation = bool(tilt_error > c['term_tilt'])
        failed = (self.height_stop_enabled and height_violation) or tilt_violation
        e = {'time': float(d.time), 'root_height': float(p[2]),
             'reference_root_height': float(rz), 'height_error_m': float(height_error),
             'height_violation': height_violation, 'tilt_violation': tilt_violation,
             'tracking_violation': height_violation or tilt_violation,
             'root_error_m': float(np.linalg.norm(p-ref['root_p'][frame])),
             'joint_rmse_rad': float(np.sqrt(np.mean((d.qpos[self.qadr]-ref['q'][frame])**2))),
             'body_global_rmse_m': float(np.sqrt(np.mean(np.sum((d.xpos[self.body_ids]-ref['body_p'][frame])**2, axis=-1)))),
             'tilt_degrees': float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1)))), 'failed': bool(failed)}
        self.errors.append(e)
        return e

    def save(self, path, protocol, extra=None):
        trace_path = Path(path).with_suffix('.trajectory.npz')
        np.savez_compressed(trace_path, qpos=np.asarray(self.trajectory), control_dt=.02,
                            policy_sha256=self.controller.contract['policy_sha256'],
                            model_sha256=self.controller.contract['model_sha256'],
                            reference_source_sha256=self.controller.metadata['source_sha256'],
                            origin='recorded MuJoCo closed-loop physics; no state resets after initial state')
        report = {'protocol': protocol, 'model_sha256': self.controller.contract['model_sha256'],
                  'evaluation_profile': self.evaluation_profile, 'height_stop_enabled': self.height_stop_enabled,
                  'first_height_violation_seconds': next((x['time'] for x in self.errors if x['height_violation']), None),
                  'first_tilt_violation_seconds': next((x['time'] for x in self.errors if x['tilt_violation']), None),
                  'tracking_criteria_passed': not any(x['tracking_violation'] for x in self.errors),
                  'termination_reason': ('tilt_tracking_deviation' if self.errors[-1]['tilt_violation'] else
                                         'height_tracking_deviation' if self.errors[-1]['failed'] else
                                         'reference_end' if len(self.errors) == self.controller.frames-1 else 'step_limit'),
                  'policy_sha256': self.controller.contract['policy_sha256'], 'reference': self.controller.metadata,
                  'steps': len(self.errors), 'completed': len(self.errors) == self.controller.frames-1 and not any(x['failed'] for x in self.errors),
                  'failed': any(x['failed'] for x in self.errors),
                  'elapsed_seconds': float(self.data.time), 'physical_support': False,
                  'trajectory':str(trace_path),
                  'metrics': self.errors, **(extra or {})}
        Path(path).write_text(json.dumps(report, indent=2))
        print('ROLLOUT_RESULT', json.dumps({k:v for k,v in report.items() if k not in ('metrics','reference')}), flush=True)


if __name__ == '__main__':
    import argparse, time
    from dex_supermimic.deployment.runtime import Controller
    p = argparse.ArgumentParser(); p.add_argument('--bundle',required=True); p.add_argument('--reference',required=True); p.add_argument('--out',required=True)
    p.add_argument('--max-steps',type=int,default=0)
    a = p.parse_args(); controller = Controller(a.bundle,a.reference); plant = Plant(controller); start=time.monotonic()
    count = controller.frames-1 if a.max_steps<=0 else min(a.max_steps,controller.frames-1)
    for _ in range(count):
        plant.step(controller.step(*plant.sensors()))
        if plant.measure(controller.frame)['failed']: break
    plant.save(a.out, 'native CPU MuJoCo, ONNX CPU inference, 50 Hz, one start, no reset, no support', {'wall_seconds':time.monotonic()-start})
