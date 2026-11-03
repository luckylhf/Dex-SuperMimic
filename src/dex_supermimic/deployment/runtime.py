"""NumPy/ONNX controller shared by native MuJoCo and the ROS simulation adapter."""
import hashlib
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quat_to_mat(quat):
    q = np.asarray(quat, dtype=np.float64)
    norm = np.linalg.norm(q)
    if not np.isfinite(q).all() or norm < 1e-8:
        raise ValueError('Invalid root quaternion')
    w, x, y, z = q / norm
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


class Controller:
    def __init__(self, bundle, reference):
        self.bundle = Path(bundle)
        self.contract = c = json.loads((self.bundle / 'contract.json').read_text())
        if sha(self.bundle / 'policy.onnx') != c['policy_sha256']:
            raise ValueError('Policy hash mismatch')
        with np.load(reference, allow_pickle=False) as z:
            self.reference = {k: z[k].copy() for k in z.files if k != 'metadata'}
            self.metadata = m = json.loads(str(z['metadata']))
        for key in ('feature_contract', 'model_sha256', 'joint_names', 'goal_frames', 'control_dt', 'tracked_bodies'):
            if m[key] != c[key]: raise ValueError(f'Reference contract mismatch: {key}')
        n = m['num_frames']
        if self.reference['goal'].shape != (n, c['goal_dim']): raise ValueError('Goal shape mismatch')
        if not all(np.isfinite(v).all() for v in self.reference.values()): raise ValueError('Non-finite reference')
        self.frames = n
        self.root_feedback = c.get('root_feedback', False)
        self.root_position = None
        if self.root_feedback and c.get('root_feedback_source') != 'simulation_ground_truth':
            raise ValueError('This engineering policy has not been paired with a deployable root estimator')
        self.q0 = np.array(c['default_q'], dtype=np.float32)
        self.alpha = np.array(c['action_scale'], dtype=np.float32)
        opts = ort.SessionOptions(); opts.intra_op_num_threads = 2; opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.bundle / 'policy.onnx'), opts, providers=['CPUExecutionProvider'])
        self.reset()

    def reset(self):
        self.frame = 0
        self.history = None
        self.previous_action = np.zeros(len(self.q0), dtype=np.float32)

    def observation(self, q, qd, quat_wxyz, angular_velocity_body):
        R = quat_to_mat(quat_wxyz)
        rel = R.T @ self.reference['root_R'][self.frame]
        # Match MotorStatus's actual float32 fields before offset subtraction.
        fields = (np.asarray(q,dtype=np.float32)-self.q0, np.asarray(qd,dtype=np.float32), angular_velocity_body,
                  -R[2], self.previous_action, rel[:, :2].reshape(6))
        if self.root_feedback:
            if self.root_position is None: raise ValueError('Fresh root feedback required')
            yaw = np.arctan2(R[1,0],R[0,0]);cs,sn=np.cos(yaw),np.sin(yaw)
            H = np.array([[cs,-sn,0],[sn,cs,0],[0,0,1]])
            error = H.T @ (self.reference['root_p'][self.frame] - np.asarray(self.root_position,dtype=np.float32))
            fields = fields + (np.clip(error,-3.,3.),)
        obs = np.concatenate(fields).astype(np.float32)
        if obs.shape != (self.contract['obs_dim'],) or not np.isfinite(obs).all():
            raise ValueError('Invalid observation')
        return obs

    def step(self, q, qd, quat_wxyz, angular_velocity_body):
        if self.frame >= self.frames-1: raise StopIteration('Reference complete')
        o = self.observation(q, qd, quat_wxyz, angular_velocity_body)
        H = self.contract['history']
        self.history = np.repeat(o[None], H, axis=0) if self.history is None else np.concatenate((self.history[1:], o[None]))
        a = self.session.run(['actions'], {'obs_history': self.history[None],
                            'goal': self.reference['goal'][self.frame:self.frame+1]})[0][0]
        if not np.isfinite(a).all(): raise FloatingPointError('Non-finite policy action')
        a = np.clip(a, -self.contract['action_clip'], self.contract['action_clip'])
        target = self.q0 + self.alpha * a
        self.previous_action = a
        self.frame += 1
        return target
