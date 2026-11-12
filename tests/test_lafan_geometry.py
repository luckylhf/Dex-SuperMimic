"""Local dataset geometry must be explicit, validated and part of cache identity."""
import copy
import json

import pytest

from dex_supermimic.common import sha
from dex_supermimic.data.v8 import lafan_geometry


@pytest.fixture
def surface():
    vertices = [[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1]]
    foot = dict(heel_local_in_foot=[-.02, -.03, 0.], toe_local_in_foot=[.2, -.03, 0.],
                sole_up_local_in_foot=[0., 1., 0.], forward_local_in_foot=[1., 0., 0.],
                geometry='synthetic test fixture', gmr_to_surface_correction_deg=0.)
    return dict(schema_version=1, units='metres', fbx_sha256=lafan_geometry.FBX_SHA256,
                semantic_bones=lafan_geometry.SEMANTIC_BONES.copy(),
                bones={bone:dict(vertices=copy.deepcopy(vertices))
                       for bone in lafan_geometry.SEMANTIC_BONES.values()},
                feet={side:foot.copy() for side in ('Left', 'Right')})


def test_missing_local_geometry_explains_preparation(tmp_path, monkeypatch):
    monkeypatch.setenv('DEX_LAFAN_GEOMETRY', str(tmp_path / 'missing.json'))
    with pytest.raises(FileNotFoundError, match='prepare-lafan-geometry'):
        lafan_geometry.load_geometry()


def test_default_geometry_is_outside_package(tmp_path, monkeypatch):
    monkeypatch.delenv('DEX_LAFAN_GEOMETRY', raising=False)
    monkeypatch.setattr(lafan_geometry, 'ROOT', tmp_path)
    assert lafan_geometry.geometry_path() == tmp_path / 'data/lafan1/local_geometry/lafan1_surfaces.json'


@pytest.mark.parametrize('corruption', ['source', 'bone', 'foot'])
def test_rejects_wrong_source_and_corrupt_geometry(surface, corruption):
    if corruption == 'source':
        surface['fbx_sha256'] = 'another model'
    elif corruption == 'bone':
        surface['bones']['Hips']['vertices'][0][0] = float('nan')
    else:
        surface['feet']['Left']['sole_up_local_in_foot'] = [0., 0., 0.]
    with pytest.raises(ValueError, match='Invalid local LAFAN geometry'):
        lafan_geometry.validate_geometry(surface)


def test_local_geometry_identity_is_portable_and_detects_changes(surface, tmp_path, monkeypatch):
    from dex_supermimic.data.retarget import conversion_identity
    first, second = tmp_path / 'first.json', tmp_path / 'second.json'
    first.write_text(json.dumps(surface))
    second.write_bytes(first.read_bytes())
    monkeypatch.setenv('DEX_LAFAN_GEOMETRY', str(first))
    identity = conversion_identity('lafan1', include_runtime=False)
    assert identity['implementation']['v8/reference/lafan1_surfaces.json'] == sha(first)
    monkeypatch.setenv('DEX_LAFAN_GEOMETRY', str(second))
    assert conversion_identity('lafan1', include_runtime=False) == identity
    surface['bones']['Hips']['vertices'][0][0] = .001
    second.write_text(json.dumps(surface))
    assert conversion_identity('lafan1', include_runtime=False)['fingerprint'] != identity['fingerprint']


def test_soma_identity_does_not_require_lafan_geometry(tmp_path, monkeypatch):
    from dex_supermimic.data.retarget import conversion_identity
    monkeypatch.setenv('DEX_LAFAN_GEOMETRY', str(tmp_path / 'missing.json'))
    identity = conversion_identity('bones_seed', include_runtime=False)
    assert 'v8/reference/lafan1_surfaces.json' not in identity['implementation']


def test_preparation_checks_input_before_creating_output(tmp_path):
    from argparse import Namespace
    from dex_supermimic.data.v8.prepare_lafan_geometry import prepare_geometry
    source = tmp_path / 'model.fbx'
    source.write_text('synthetic invalid source')
    output = tmp_path / 'output/surface.json'
    args = Namespace(fbx=str(source), ufbx_dir=str(tmp_path), out=str(output), compiler='cc')
    with pytest.raises(ValueError, match='FBX SHA-256 mismatch'):
        prepare_geometry(args)
    assert not output.parent.exists()


def test_batch_preflights_local_geometry_before_creating_output(tmp_path, monkeypatch):
    from argparse import Namespace
    from dex_supermimic.data.prepare import convert_dataset
    source = tmp_path / 'synthetic.bvh'
    source.write_text('ROOT Hips\n' + ''.join('JOINT ' + joint + '\n' for joint in (
        'LeftUpLeg', 'RightUpLeg', 'LeftLeg', 'RightLeg', 'LeftHand', 'RightHand')) + 'MOTION\n')
    manifest = tmp_path / 'sources.jsonl'
    manifest.write_text(json.dumps(dict(id='synthetic', source=str(source), actor='test',
                                        sampling_group='dance', dataset='lafan1')) + '\n')
    output = tmp_path / 'output'
    monkeypatch.setenv('DEX_LAFAN_GEOMETRY', str(tmp_path / 'missing.json'))
    with pytest.raises(FileNotFoundError, match='prepare-lafan-geometry'):
        convert_dataset(Namespace(manifest=str(manifest), out=str(output), dataset='auto', workers=1))
    assert not output.exists()
