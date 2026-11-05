import json
import pickle
import numpy as np
import pytest

from dex_supermimic.data import quality_pose, quality_v8
from dex_supermimic.data.prepare import require_v8_acceptance, training_rows
from dex_supermimic.data.retarget import CONVERTER, QUALITY_POLICY


def test_direction_reversal_previously_missed(tmp_path, monkeypatch):
    names = ['knee', 'shoulder']
    model = {'joint_names': names, 'joint_limits': {name:{'velocity':1.0} for name in names}}
    (tmp_path/'model.json').write_text(json.dumps(model))
    monkeypatch.setattr(quality_v8, 'ASSETS', tmp_path)
    monkeypatch.setattr(quality_pose, 'ASSETS', tmp_path)
    q = np.zeros((40, 2))
    q[20] = [0.03, -0.03]  # Both intervals exceed 1 rad/s, with simultaneous axes.
    path = tmp_path/'motion.pkl'
    original = pickle.dumps(dict(joint_names=names, fps=50., dof_pos=q, root_pos=np.zeros((40,3)),
                                 root_rot=np.tile([0.,0.,0.,1.],(40,1))))
    path.write_bytes(original)
    zero = dict(median=0,p95=0,max=0)
    audit = dict(finite=True, effective_anatomical_limit_violation_deg=0, root_orientation_deg=zero,
                 torso_up_deg=zero, torso_orientation_deg=zero, stationary_floating_longest_seconds=0, sides={},
                 self_collision=dict(collision_samples=0))
    meta = dict(support_constraint_failures=[])
    assert not quality_pose.quality(path,meta,audit)['flags']
    result = quality_v8.quality(path,meta,audit)
    assert result['flags'] == ['joint_velocity_exceeds_model_limit']
    report = result['step_velocity']
    assert report['violating_intervals'] == 2 and report['central_excess_frames'] == 0
    assert report['violations_by_joint'] == {'knee':2, 'shoulder':2}
    assert report['worst_interval'] == 19 and report['peak_ratio'] == pytest.approx(1.5)
    assert path.read_bytes() == original


def test_build_requires_v8_evidence_and_rejects_inconsistent_grade():
    row = dict(id='x', converter='dex_v7', grade='B_needs_repair')
    with pytest.raises(ValueError, match='Legacy'):
        training_rows([row])
    row.update(converter=CONVERTER, grade='A_kinematic_candidate', frames=35, quality={})
    with pytest.raises(ValueError, match='Missing V8'):
        require_v8_acceptance(row)
    row['quality'] = dict(quality_policy=QUALITY_POLICY, flags=[],
                          step_velocity=dict(policy=QUALITY_POLICY,intervals=34,violating_intervals=1))
    with pytest.raises(ValueError, match='Inconsistent'):
        require_v8_acceptance(row)
