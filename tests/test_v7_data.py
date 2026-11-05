"""Conversion boundaries: datasets, stale cache, quaternion order, source-pose gate."""
import ast
import copy
import hashlib
import json
import pickle
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from dex_supermimic.data import retarget, training_format, quality_pose
from dex_supermimic.data.prepare import _convert, training_rows, row_sha, source_row

ROOT = Path(__file__).resolve().parents[1]


def test_dataset_routing_rejects_mislabeled_skeleton(tmp_path):
    for dataset, names in [('bones_seed', ['LeftShin','RightShin','LeftHandIndex1','RightHandIndex1']),
                           ('lafan1', ['LeftUpLeg','RightUpLeg','LeftLeg','RightLeg','LeftHand','RightHand'])]:
        p=tmp_path/(dataset+'.bvh');p.write_text('ROOT Hips\n'+''.join('JOINT '+n+'\n' for n in names)+'MOTION\n')
        assert retarget.resolve_dataset(p)==dataset
        wrong='lafan1' if dataset=='bones_seed' else 'bones_seed'
        with pytest.raises(ValueError, match='mismatch'):retarget.resolve_dataset(p,wrong)
    p.write_text('ROOT Unknown\nMOTION\n')
    with pytest.raises(ValueError, match='Unrecognized'):retarget.resolve_dataset(p)


@pytest.mark.parametrize('backend,fingerprint',[('gmr','old'),('dex_v7','old'),('dex_v8','old')])
def test_unchanged_source_cannot_reuse_legacy_or_stale_conversion(tmp_path,monkeypatch,backend,fingerprint):
    from dex_supermimic.common import atomic, sha
    p=tmp_path/'source.bvh';p.write_text('source')
    monkeypatch.setattr('dex_supermimic.data.prepare.resolve_dataset',lambda *args:'lafan1')
    monkeypatch.setattr('dex_supermimic.data.prepare.conversion_identity',lambda *args,**kw:{'fingerprint':'current'})
    row=dict(id='clip',source=str(p))
    atomic(tmp_path/'records/clip.json',dict(source_sha256=sha(p),converter=backend,converter_fingerprint=fingerprint))
    with pytest.raises(ValueError,match='Legacy or stale'):_convert((row,tmp_path))


def test_build_rejects_legacy_a_grade():
    with pytest.raises(ValueError,match='Legacy conversion'):
        training_rows([dict(id='old',grade='A_kinematic_candidate',evaluation_only=False)])


def test_build_identity_allows_runtime_change_but_not_model_or_solver():
    payload=dict(backend='dex_v7',dataset='lafan1',model_sha256='model',implementation={'solver':'approved'},runtime_versions={'numpy':'old'})
    identity=dict(payload,fingerprint=row_sha(payload))
    record=dict(id='clip',converter_identity=identity,converter_fingerprint=identity['fingerprint'])
    expected=dict(payload,runtime_versions={'numpy':'new'})
    retarget.validate_record_identity(record,expected)
    with pytest.raises(ValueError,match='Stale'):
        retarget.validate_record_identity(record,dict(expected,model_sha256='different'))
    with pytest.raises(ValueError,match='Stale'):
        retarget.validate_record_identity(record,dict(expected,implementation={'solver':'changed'}))
    changed=copy.deepcopy(record);changed['converter_identity']['model_sha256']='tampered'
    with pytest.raises(ValueError,match='Corrupt'):retarget.validate_record_identity(changed,expected)


def test_changed_mesh_invalidates_geometry_identity(tmp_path,monkeypatch):
    from dex_supermimic.common import sha
    (tmp_path/'mjcf').mkdir();(tmp_path/'urdf').mkdir();(tmp_path/'meshes').mkdir()
    xml=tmp_path/'mjcf/dex_29.xml'
    xml.write_text('<mujoco><asset><mesh name="shoe" file="../meshes/shoe.stl"/></asset></mujoco>')
    (tmp_path/'urdf/dex_29.urdf').write_text('<robot/>')
    (tmp_path/'model.json').write_text(json.dumps(dict(model_sha256=sha(xml))))
    mesh=tmp_path/'meshes/shoe.stl';mesh.write_bytes(b'original shoe fixture')
    monkeypatch.setattr(retarget,'ASSETS',tmp_path)
    old=retarget.conversion_identity('lafan1',include_runtime=False)
    mesh.write_bytes(b'changed shoe dimensions fixture')
    new=retarget.conversion_identity('lafan1',include_runtime=False)
    assert old['fingerprint']!=new['fingerprint'] and old['mesh_sha256']!=new['mesh_sha256']


@pytest.fixture
def sample(tmp_path,monkeypatch):
    names=['joint_'+str(i) for i in range(29)]
    manifest=dict(joint_names=names,model_sha256='fixture',joint_limits={n:{'velocity':16.} for n in names})
    (tmp_path/'model.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(training_format,'ASSETS',tmp_path);monkeypatch.setattr(quality_pose,'ASSETS',tmp_path)
    p=np.arange(99,dtype=np.float32).reshape(33,3)/1000
    q=np.tile(np.array([.1,.2,.3,np.sqrt(.86)],dtype=np.float32),(33,1))
    data=dict(joint_names=names,root_pos=p,root_rot=q,dof_pos=np.zeros((33,29),dtype=np.float32),fps=50.,quat_order='xyzw')
    path=tmp_path/'motion.pkl';path.write_bytes(pickle.dumps(data))
    return path,data,manifest


def training_reader(manifest):
    # Execute the exact production loader, without importing GPU simulator setup.
    path=ROOT/'src/instanttrack/dex/dex_constants.py'
    fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='load_dex_npz')
    ns=dict(np=np,NAMES=tuple(manifest['joint_names']),MANIFEST=manifest)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    return ns['load_dex_npz']


def test_export_roundtrips_through_existing_training_reader(sample,tmp_path):
    path,data,manifest=sample;target=tmp_path/'training.npz'
    assert training_format.export_training_npz(path,target,dict(model_sha256='fixture',fingerprint='id',dataset='lafan1'))==33
    p,q,j,fps=training_reader(manifest)(target)
    np.testing.assert_array_equal(p,data['root_pos']);np.testing.assert_array_equal(j,data['dof_pos'])
    np.testing.assert_array_equal(q,data['root_rot'][:,[3,0,1,2]])
    assert fps==50. and q.shape==(33,4)
    with pytest.raises(FileExistsError):training_format.export_training_npz(path,target,{})


@pytest.mark.parametrize('field,value',[('fps',60.),('quat_order','wxyz'),('joint_names',['wrong']*29)])
def test_export_rejects_incompatible_contract(sample,tmp_path,field,value):
    path,data,_=sample;data[field]=value;path.write_bytes(pickle.dumps(data))
    with pytest.raises(ValueError):training_format.export_training_npz(path,tmp_path/'bad.npz',{})


def test_source_torso_flip_is_not_a_quality_candidate(sample):
    path,_,_=sample
    zero=dict(median=0.,p95=0.,max=0.)
    audit=dict(finite=True,effective_anatomical_limit_violation_deg=0.,root_orientation_deg=zero,
               torso_orientation_deg=zero,torso_up_deg=zero,stationary_floating_longest_seconds=0.,sides={})
    meta=dict(support_constraint_failures=[])
    assert quality_pose.quality(path,meta,audit)['flags']==[]
    audit['torso_up_deg']=dict(zero,max=90.);audit['torso_orientation_deg']=dict(zero,p95=90.)
    result=quality_pose.quality(path,meta,audit)
    assert 'source_torso_up_mismatch' in result['flags']
    assert 'source_torso_orientation_mismatch' in result['flags']
    assert 'priming_frames' not in result


def test_calibration_resources_are_self_contained():
    from dex_supermimic.data.v8.source import REFERENCE, adapt
    from dex_supermimic.data.v8.bvh import load
    motion=load(REFERENCE/'soma_zero.bvh')
    motion.local_p=np.repeat(motion.local_p[:1],30,axis=0)
    motion.local_r=np.repeat(motion.local_r[:1],30,axis=0)
    targets=adapt(motion,'soma')
    for side in ('Left','Right'):
        assert targets['sides'][side]['hand_method'].startswith('finger bases:')
    np.testing.assert_allclose(np.linalg.det(targets['root_r']),1.,atol=1e-8)


def test_wrists_match_physical_mount_and_nasa_intersection():
    from dex_supermimic.data.v8.robot import Robot, DEFAULT_MODEL
    from dex_supermimic.data.v8.anatomy import configure, wrist_from_relative_rotation
    from scipy.spatial.transform import Rotation
    if not Path(DEFAULT_MODEL).exists():pytest.skip('Local licensed robot assets not installed')
    robot=Robot();cfg=json.loads((retarget.SOLVER_ROOT/'config.json').read_text());configure(robot,cfg['anatomy'])
    for side,g in robot.sides.items():
        ids=g['arm'][5:7]
        np.testing.assert_allclose(np.degrees(robot.lower[ids]),[-20,-76],atol=1e-8)
        np.testing.assert_allclose(np.degrees(robot.upper[ids]),[45,76],atol=1e-8)
        for q6,q7 in [(-.3,.7),(.7,-1.2),(.2,1.2)]:
            x=np.r_[.1,.2,.8,np.zeros(29)];x[g['arm']]=[.3,.5,-.7,-1.1,.8,q6,q7]
            robot.set(x,Rotation.from_euler('xyz',[.7,-.2,1.1]).as_matrix())
            relative=robot.rot(g['forearm']).T@robot.rot(g['tcp'])
            np.testing.assert_allclose(wrist_from_relative_rotation(relative),[q6,q7],atol=1e-12)
