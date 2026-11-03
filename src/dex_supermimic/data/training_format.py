"""Lossless v7 review PKL (XYZW) → existing 50 Hz training NPZ (WXYZ)."""
import json
import pickle
from pathlib import Path
import numpy as np
from dex_supermimic.paths import ASSETS


def export_training_npz(pkl, output, identity):
    pkl, output = Path(pkl), Path(output)
    if output.exists():
        raise FileExistsError(output)
    # Only called on the local v7 output, not arbitrary downloaded pickles.
    data = pickle.loads(pkl.read_bytes())
    manifest = json.loads((ASSETS/'model.json').read_text())
    if data['joint_names'] != manifest['joint_names']:
        raise ValueError('v7/training joint order differs')
    if data['quat_order'] != 'xyzw' or float(data['fps']) != 50.:
        raise ValueError('Training export requires v7 XYZW at exactly 50 Hz; re-solve BVH at 50 Hz')
    n = len(data['dof_pos'])
    for key, shape in [('dof_pos',(n,29)),('root_pos',(n,3)),('root_rot',(n,4))]:
        if data[key].shape != shape or not np.isfinite(data[key]).all():
            raise ValueError('Invalid v7 array: ' + key)
    if n < 3 or not np.allclose(np.linalg.norm(data['root_rot'],axis=1),1.,atol=2e-6):
        raise ValueError('Invalid root quaternion or frame count')
    arrays = dict(joint_pos=data['dof_pos'], joint_names=np.array(data['joint_names']),
                  body_names=np.array(['pelvis']), body_pos_w=data['root_pos'][:,None,:],
                  body_quat_w=data['root_rot'][:,None,[3,0,1,2]],
                  model_sha256=np.array(identity['model_sha256']), fps=np.array(50.),
                  quat_order=np.array('wxyz'), storage_format=np.array('root_joint_lossless_v1'),
                  converter=np.array('dex_v7'), converter_fingerprint=np.array(identity['fingerprint']),
                  dataset=np.array(identity['dataset']))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    with temporary.open('wb') as f:
        np.savez_compressed(f, **arrays)
    with np.load(temporary, allow_pickle=False) as check:
        if not all(np.array_equal(check[k],v) for k,v in arrays.items()):
            raise AssertionError('Training export is not lossless')
    temporary.replace(output)
    return n
