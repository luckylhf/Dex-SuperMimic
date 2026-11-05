"""Self-contained real-Dex geometry tests; no dataset download or private pickle."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from dex_supermimic.data.v8.robot import Robot
from dex_supermimic.data.v8.anatomy import configure
from dex_supermimic.data.v8.self_collision import CollisionModel, scan, refine, windows, POLICY


@pytest.fixture(scope='module')
def case():
    import dex_supermimic.data.v8.self_collision as module
    cfg=json.loads(Path(module.__file__).with_name('config.json').read_text())
    r=Robot();configure(r,cfg['anatomy'])
    # Fixed single robot configuration reproducing left wrist/hip intersection.
    # Synthetic nine-frame stationary sequence, not an external motion fixture.
    x=np.array([-.082268,.069503,.986713,-.338480,.025618,.025783,.825310,-.039831,-.062103,
        -.149138,.105593,.022964,.340727,-.199559,-.162439,.186105,-.008812,.009291,
        .065607,-.061616,-.089741,-.261682,.129451,-.083764,.408536,
        .129616,-.105160,.402336,-.398569,-.011382,-.101461,-.406754])
    # Global yaw has no effect on self-distance; identity simplifies this fixture.
    rot=np.eye(3);r.set(x,rot);n=9
    def rep(v):return np.repeat(np.asarray(v)[None],n,axis=0)
    def direction(a,b):
        d=r.point(b)-r.point(a);return rep(d/np.linalg.norm(d))
    t=dict(fps=50.,root_r=rep(rot),sides={},body_contacts=[])
    for side,g in r.sides.items():
        t['sides'][side]=dict(upper=direction(g['shoulder'],g['elbow']),lower=direction(g['elbow'],g['wrist']),
            hand_forward=rep(-r.rot(g['tcp'])[:,2]),hand_width=rep(r.rot(g['tcp'])[:,0]),
            forearm_width=rep(r.rot(g['forearm'])[:,0]),elbow_axis=rep(-r.rot(g['shoulder'])[:,1]),
            signed_elbow_bend=np.full(n,g['elbow_geometric_zero']-x[g['arm'][3]]))
    return r,t,rep(x),cfg


def test_named_pairs_detect_wrist_and_do_not_mutate_shared_model(case):
    r,t,x,cfg=case;ct=r.m.geom_contype.copy();ca=r.m.geom_conaffinity.copy()
    m=CollisionModel(r,cfg['self_collision']);m.update(x[0],t['root_r'][0]);d=m.distances()
    assert d.min()<-.02
    assert set(m.names[int(d.argmin())])=={'hip_pitch_l_link_collision','wrist_pitch_l_link_collision'}
    assert any(set(p)=={'left_tcp_link_collision','right_tcp_link_collision'} for p in m.names)
    assert all(a!=b for a,b in m.pairs)
    np.testing.assert_array_equal(r.m.geom_contype,ct);np.testing.assert_array_equal(r.m.geom_conaffinity,ca)


def test_mink_penetrating_distance_derivative_and_recovery(case):
    r,t,x,cfg=case;m=CollisionModel(r);m.update(x[0],t['root_r'][0]);k=int(m.distances().argmin())
    con=m.limit.compute_qp_inequalities(m.configuration,1.);ids=np.array(r.sides['Left']['arm'])
    j=int(ids[np.argmax(abs(con.G[k,r.cols[ids]]))]);eps=1e-6
    v=x[0].copy();v[j]+=eps;m.update(v,t['root_r'][0]);plus=m.distances()[k]
    v[j]-=2*eps;m.update(v,t['root_r'][0]);minus=m.distances()[k]
    assert (plus-minus)/(2*eps)==pytest.approx(-con.G[k,r.cols[j]],abs=1e-5)
    m.update(x[0],t['root_r'][0]);_,bounds=m.linear(ids)
    assert bounds.min()<-.02  # Official h alone is zero inside the margin.


def test_actual_repair_preserves_nonarm_limits_speed_and_interpolation(case):
    r,t,x,cfg=case;out,report=refine(r,t,x,cfg['solver'],cfg['self_collision'])
    assert report['before']['collision_samples']>0
    assert report['after']['collision_samples']==0
    assert report['windows'][0]['status']=='repaired'
    ids=np.array(r.sides['Left']['arm']);other=np.setdiff1d(np.arange(32),ids)
    np.testing.assert_array_equal(out[:,other],x[:,other])
    assert np.all(out[:,ids]>=r.lower[ids]-2e-6) and np.all(out[:,ids]<=r.upper[ids]+2e-6)
    assert np.all(abs(np.diff(out[:,3:],axis=0))<=r.joint_step(t['fps'],cfg['solver'])+2e-6)
    assert scan(CollisionModel(r),out,t['root_r'],8)[0]['collision_samples']==0


def test_failed_recovery_rolls_back_and_reports(case):
    r,t,x,cfg=case;out,report=refine(r,t,x,cfg['solver'],dict(cfg['self_collision'],max_iterations=0))
    np.testing.assert_array_equal(out,x)
    assert report['after']['collision_samples']>0
    assert report['windows'][0]['status']=='unresolved'


def test_load_bearing_arm_is_not_released(case):
    r,t,x,cfg=case;t=copy.deepcopy(t)
    t['body_contacts']=[dict(body=r.sides['Left']['forearm'],mode=np.ones(len(x),dtype=int))]
    out,report=refine(r,t,x,cfg['solver'],cfg['self_collision'])
    np.testing.assert_array_equal(out,x)
    assert report['windows'][0]['reason']=='active_arm_support_requires_coupled_repair'


def test_clean_motion_does_not_construct_arm_objectives(case,monkeypatch):
    r,t,x,cfg=case;x=x.copy();x[:,r.sides['Left']['arm'][1]]+=.3
    import dex_supermimic.data.v8.self_collision as module
    def forbidden(*a,**kw):raise AssertionError('Clean motion must bypass local solving')
    monkeypatch.setattr(module,'ArmObjective',forbidden)
    out,report=refine(r,t,x,cfg['solver'],cfg['self_collision'])
    assert report['before']['collision_samples']==0
    np.testing.assert_array_equal(out,x)


def test_window_merge_and_real_sequence_edges():
    assert windows({0,3,18},20,2)==[[0,6],[16,20]]


def test_training_gate_requires_collision_evidence():
    from dex_supermimic.data.prepare import require_v8_acceptance
    from dex_supermimic.data.retarget import CONVERTER,QUALITY_POLICY
    row=dict(id='test',converter=CONVERTER,frames=10,grade='A_kinematic_candidate',
        quality=dict(quality_policy=QUALITY_POLICY,flags=[],step_velocity=dict(policy=QUALITY_POLICY,intervals=9,violating_intervals=0)))
    with pytest.raises(ValueError,match='collision evidence'):require_v8_acceptance(row)
    row['quality']['self_collision']=dict(policy=POLICY,frames=10,collision_samples=0)
    require_v8_acceptance(row)
    row['quality']['self_collision']['collision_samples']=1
    with pytest.raises(ValueError,match='Inconsistent'):require_v8_acceptance(row)
    row['grade']='B_needs_repair';row['quality']['flags']=['arm_self_collision_unresolved']
    require_v8_acceptance(row)
