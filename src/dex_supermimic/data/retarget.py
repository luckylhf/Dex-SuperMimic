"""Packaged V8 entry, dataset routing, and conversion identity (CPU only)."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from dex_supermimic.common import atomic, sha
from dex_supermimic.paths import ASSETS

ROOT = Path(__file__).resolve().parent
SOLVER_ROOT = ROOT / 'v8'
CONVERTER = 'dex_v8'
POSE_SOLVER = 'dex_v8_per_axis_velocity'
CONVERTER_RELEASE = 'V8_cpu_coupled_arms_20261105'
SOLVER_POLICY = 'per_axis_velocity_v8_mink_arm_recovery_v2'
QUALITY_POLICY = 'adjacent_joint_speed_and_arm_collision_v8'
DATASETS = {
    'bones_seed': ('soma', 'BONES-SEED: Skeletal Everyday Embodiment Dataset — SOMA Uniform BVH'),
    'lafan1': ('lafan', 'Ubisoft La Forge Animation Dataset (LAFAN1)'),
}


def resolve_dataset(path, requested='auto'):
    if requested not in ('auto', *DATASETS):
        raise ValueError('dataset must be auto, bones_seed, or lafan1')
    names = set()
    with Path(path).open() as f:
        for line in f:
            if line.strip() == 'MOTION':
                break
            match = re.match(r'\s*(?:ROOT|JOINT)\s+(\S+)', line)
            if match:
                names.add(match.group(1))
    if {'LeftShin', 'RightShin', 'LeftHandIndex1', 'RightHandIndex1'} <= names:
        detected = 'bones_seed'
    elif {'LeftUpLeg', 'RightUpLeg', 'LeftLeg', 'RightLeg', 'LeftHand', 'RightHand'} <= names and 'LeftHandIndex1' not in names:
        detected = 'lafan1'
    else:
        raise ValueError('Unrecognized dataset skeleton; batch conversion supports BONES-SEED SOMA Uniform and LAFAN1')
    if requested != 'auto' and requested != detected:
        raise ValueError(f'Dataset/skeleton mismatch: requested {requested}, detected {detected}')
    return detected


def conversion_identity(dataset, *, include_runtime=True):
    """Invalidate old mappings, changed solver/config/quality code and model assets."""
    if dataset not in DATASETS:
        raise ValueError('Unknown resolved dataset: ' + dataset)
    model, urdf = ASSETS/'mjcf/dex_29.xml', ASSETS/'urdf/dex_29.urdf'
    manifest = json.loads((ASSETS/'model.json').read_text())
    if sha(model) != manifest['model_sha256']:
        raise ValueError('Conversion model differs from the training model manifest')
    xml = ET.parse(model).getroot()
    compiler = xml.find('compiler')
    meshdir = compiler.get('meshdir', '') if compiler is not None else ''
    meshes = {(model.parent/meshdir/m.get('file')).resolve() for m in xml.findall('./asset/mesh') if m.get('file')}
    geometry = {str(p.relative_to(ASSETS.resolve())):sha(p) for p in sorted(meshes)}
    files = [p for p in SOLVER_ROOT.rglob('*') if p.is_file() and p.suffix in ('.py', '.json', '.bvh')]
    files += [ROOT/n for n in ('prepare.py', 'retarget.py', 'training_format.py', 'quality_pose.py', 'quality_pose.json', 'quality_v8.py')]
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'mujoco', 'osqp', 'mink', 'qpsolvers')} if include_runtime else None
    identity = dict(converter_release=CONVERTER_RELEASE, backend=CONVERTER, pose_solver=POSE_SOLVER, solver_policy=SOLVER_POLICY, quality_policy=QUALITY_POLICY, dataset=dataset, source_type=DATASETS[dataset][0], fps=50.,
                    model_sha256=sha(model), urdf_sha256=sha(urdf), manifest_sha256=sha(ASSETS/'model.json'),
                    mesh_sha256=geometry,
                    implementation={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)})
    if include_runtime: identity['runtime_versions'] = versions
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(identity, fingerprint=digest)


def validate_record_identity(record, expected):
    """Building features can use another runtime; solver code/model must still match."""
    stored = dict(record.get('converter_identity', {}))
    digest = stored.pop('fingerprint', None)
    actual = hashlib.sha256(json.dumps(stored, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != actual or digest != record.get('converter_fingerprint'):
        raise ValueError('Corrupt converter identity: '+record['id'])
    stored.pop('runtime_versions', None)
    expected = {k:v for k,v in expected.items() if k not in ('runtime_versions','fingerprint')}
    if stored != expected:
        raise ValueError('Stale converter/model identity; reconvert into a new directory: '+record['id'])


def convert(source, output, *, dataset='auto', fps=50., max_frames=None):
    """Full V8 solve from BVH with named-axis velocity limits and fixed timing."""
    from .v8.convert import convert as solve
    resolved = resolve_dataset(source, dataset)
    meta = solve(source, output, source=DATASETS[resolved][0],
                 model=str(ASSETS/'mjcf/dex_29.xml'), fps=fps, max_frames=max_frames)
    meta.update(converter_release=CONVERTER_RELEASE, converter_version=8, pose_solver=POSE_SOLVER, solver_policy=SOLVER_POLICY, quality_policy=QUALITY_POLICY)
    atomic(Path(output).with_suffix('.json'), meta)
    return meta
