import json
from pathlib import Path
import numpy as np
import pytest
from dex_supermimic.data.prepare import sampling_weights
from dex_supermimic.evaluation.evaluate import better

def test_sampler_preserves_category_anchor_actor_mass():
    rows=[]
    for group in ('dance','locomotion','stationary_upper','dynamic'):
        for anchor in (True,False):
            for actor,count in [('a',1),('b',3)]:
                for i in range(count):
                    rows.append(dict(id=f'{group}_{anchor}_{actor}_{i}',sampling_group=group,anchor=anchor,actor=actor))
    w=sampling_weights(rows)
    for group,mass in [('dance',.4),('locomotion',.25),('stationary_upper',.25),('dynamic',.1)]:
        selected=[r for r in rows if r['sampling_group']==group]
        assert sum(w[r['id']] for r in selected)==pytest.approx(mass)
        assert sum(w[r['id']] for r in selected if r['anchor'])==pytest.approx(mass*.25)
        for actor in ('a','b'):
            assert sum(w[r['id']] for r in selected if r['actor']==actor)==pytest.approx(mass/2)

def test_best_prefers_completion_then_survival_then_error():
    a=dict(completed=False,elapsed_seconds=20.,mean_body_global_rmse_m=.5,max_root_error_m=1.)
    assert better(dict(a,completed=True,elapsed_seconds=19.),a)
    assert better(dict(a,elapsed_seconds=21.,mean_body_global_rmse_m=2.),a)
    assert better(dict(a,elapsed_seconds=19.99,mean_body_global_rmse_m=.4),a)
    assert not better(a,a)

def test_baseline_contract_has_all_joints_and_root_feedback():
    root=Path(__file__).resolve().parents[1]
    c=json.loads((root/'configs/baseline_12341.json').read_text())
    assert len(c['joint_names'])==len(set(c['joint_names']))==29
    assert c['history']==10 and c['obs_dim']==102 and c['goal_dim']==730
    assert c['root_feedback'] and c['motor_feedback_precision']=='float32_before_default_offset'
    np.testing.assert_equal(c['action_scale'],np.full(29,.25))

def test_core_motion_math_fingerprints():
    from dex_supermimic.common import sha
    root=Path(__file__).resolve().parents[1]
    assert sha(root/'src/instanttrack/motion.py')=='1287c8ad251c4895b54b64a9072b69498d868ff04cd303aa0b060a7fd503ce7b'
    assert sha(root/'src/instanttrack/kinematics.py')=='9941b09d15dffce47fcf48aca55f4dd1bcaa21487a4fd5380a7e73854ad0f27a'
