"""Export one shared actor and separate reference files; CPU-only preparation."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import os

import mujoco
import numpy as np
import torch
import onnx
import onnxruntime as ort
from mjlab.scene import Scene
import instanttrack.networks as networks
from instanttrack.networks import Policy
from instanttrack.robot import get_robot
from instanttrack.kinematics import Kinematics
from instanttrack.motion import MotionLib, CONTROL_DT
from instanttrack.mdp import obs_dim
from instanttrack.env import make_scene_cfg, make_sim
from instanttrack.dex.dex_constants import MANIFEST, profile

FEATURE_CONTRACT = 'dex-instanttrack-goal-v1-50hz-wxyz-row6d'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_motion(source, output, goal_frames):
    start = time.monotonic()
    robot = get_robot('dex')
    kin = Kinematics(robot, 'cpu')
    motion = MotionLib([source], kin, 'cpu', robot.load_motion)
    f = torch.arange(motion.num_frames)
    arrays = {k: getattr(motion, k).numpy() for k in
              ('root_p', 'root_R', 'root_v', 'root_w', 'q', 'qd', 'body_p', 'body_R')}
    arrays['goal'] = motion.goal(f, goal_frames).numpy()
    metadata = {'feature_contract': FEATURE_CONTRACT, 'source': Path(source).name,
                'source_sha256': sha(source), 'model_sha256': MANIFEST['model_sha256'],
                'joint_names': list(robot.joint_names), 'tracked_bodies': list(robot.tracked_bodies),
                'goal_frames': goal_frames, 'control_dt': CONTROL_DT,
                'num_frames': motion.num_frames, 'preparation_wall_seconds': time.monotonic() - start}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **arrays, metadata=json.dumps(metadata))
    print('REFERENCE_READY', json.dumps(metadata), flush=True)


def export(checkpoint, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(731)
    robot = get_robot('dex')
    ck = torch.load(checkpoint, map_location='cpu', weights_only=False)
    a = ck['args']
    os.environ['DEX_ROOT_FEEDBACK']='1' if a.get('root_feedback',False) else '0'
    assert a['robot'] == 'dex'
    K, H, O = a['goal_frames'], a['hist'], obs_dim(robot.num_joints)
    G = K * (15 + 2 * robot.num_joints)
    widths = lambda key: tuple(map(int, a[key].split(',')))
    networks.AMP_DTYPE = None
    pi = Policy(O, G, robot.num_joints, hist=H, enc_hidden=widths('enc_hidden'),
                dec_hidden=widths('dec_hidden'), ref_residual=a['ref_residual'],
                experts=a.get('pi_experts', 1)).eval()
    pi.load_state_dict(ck['pi'])
    # The graph has no motion table. The same weights accept any compatible reference.
    path = output / 'policy.onnx'
    torch.onnx.export(pi, (torch.zeros(1, H, O), torch.zeros(1, G)), str(path),
                      input_names=['obs_history', 'goal'], output_names=['actions'],
                      opset_version=18, dynamo=False)
    onnx.checker.check_model(onnx.load(path))
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), opts, providers=['CPUExecutionProvider'])
    errors, timings = [], []
    with torch.no_grad():
        for _ in range(64):
            o = torch.zeros(1,H,O)
            o[...,:pi.base_obs_dim] = pi.obs_norm.mean + pi.obs_norm.std() * torch.randn(1,H,pi.base_obs_dim)
            if pi.root_feedback:o[...,-3:] = torch.randn(1,H,3)
            g = pi.goal_norm.mean + pi.goal_norm.std() * torch.randn(1, G)
            expected = pi(o, g).numpy()
            start = time.perf_counter()
            actual = session.run(None, {'obs_history': o.numpy(), 'goal': g.numpy()})[0]
            timings.append((time.perf_counter() - start) * 1000)
            errors.append(float(np.max(np.abs(actual - expected))))
    if max(errors) > 1e-3:
        raise AssertionError(f'ONNX action mismatch: {max(errors)}')
    scene = Scene(make_scene_cfg(robot, 1), device='cpu')
    model = scene.compile()
    make_sim(robot).mujoco.apply(model)
    # Match DomainRandomizer.startup(eval_mode=True), including the ground.
    model.geom_friction[:, 0] = 1.0
    mujoco.mj_saveModel(model, str(output / 'model.mjb'))
    gains = [profile(n) for n in robot.joint_names]
    contract = {'feature_contract': FEATURE_CONTRACT, 'robot': 'dex',
                'root_feedback': bool(a.get('root_feedback',False)),
                'root_feedback_source': 'simulation_ground_truth' if a.get('root_feedback',False) else None,
                'motor_feedback_precision': 'float32_before_default_offset',
                'observation_contract': 'dex-refine-root-error-xyz-v1' if a.get('root_feedback',False) else 'dex-refine-proprio-v1',
                'checkpoint': Path(checkpoint).name, 'checkpoint_sha256': sha(checkpoint),
                'iteration': ck['iteration'], 'model_sha256': MANIFEST['model_sha256'],
                'policy_sha256': sha(path), 'compiled_model_sha256': sha(output / 'model.mjb'),
                'mujoco_version': mujoco.__version__, 'joint_names': list(robot.joint_names),
                'tracked_bodies': list(robot.tracked_bodies), 'default_q': robot.default_joint_pos_list(),
                'action_scale': robot.action_scale_list(), 'action_clip': 20.,
                'kp': [g[0] for g in gains], 'kd': [g[1] for g in gains],
                'effort_limits': [MANIFEST['joint_limits'][n]['effort'] for n in robot.joint_names],
                'history': H, 'obs_dim': O, 'goal_dim': G, 'goal_frames': K,
                'control_dt': CONTROL_DT, 'physics_dt': float(model.opt.timestep), 'decimation': 4,
                'nominal_sliding_friction': 1.0,
                'term_height': .25, 'term_tilt': .8,
                'observation': 'q-q0, qd, angular velocity in root frame, projected gravity, previous clipped action, (R_robot.T @ R_ref)[:, :2] flattened row-major',
                'history_order': 'oldest to newest', 'target': 'q0 + action_scale * clip(action,-20,20)',
                'acceptance': 'interface export only; no tracking or hardware acceptance implied'}
    (output / 'contract.json').write_text(json.dumps(contract, indent=2))
    report = {'max_abs_action_error': max(errors), 'samples': len(errors),
              'inference_median_ms': float(np.median(timings)),
              'inference_p95_ms': float(np.percentile(timings, 95)), 'status': 'passed'}
    (output / 'export_check.json').write_text(json.dumps(report, indent=2))
    print('EXPORT_READY', json.dumps(report), flush=True)


if __name__ == '__main__':
    torch.set_num_threads(2)
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    ex = sub.add_parser('export'); ex.add_argument('--checkpoint', required=True); ex.add_argument('--out', required=True)
    mo = sub.add_parser('motion'); mo.add_argument('--source', required=True); mo.add_argument('--out', required=True); mo.add_argument('--goal-frames', type=int, default=10)
    a = p.parse_args()
    if a.command == 'export': export(a.checkpoint, a.out)
    else: prepare_motion(a.source, a.out, a.goal_frames)
