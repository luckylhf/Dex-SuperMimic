"""Generate local LAFAN reference hulls from the user's official FBX."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from dex_supermimic.common import sha
from .lafan_geometry import FBX_SHA256, SEMANTIC_BONES, geometry_path, validate_geometry

UFBX_COMMIT = '5955c5c0b042ac2dc6f32955ab206aaec0620cfc'
UFBX_HASHES = {
    'ufbx.h': 'f787be529af577efc04f3e3e735844a08556718dbb613d1211c2b313d72895dc',
    'ufbx.c': '4a956c26a708e40d82ecb0aeaee54da709d5ba7c144c9642174970059bda7e1d',
}


def foot_geometry(vertices, relative):
    """Use the existing area-dominant sole plane and 6 mm support band."""
    import numpy as np
    from scipy.spatial import ConvexHull

    rotation = relative[:3, :3]
    prior = rotation @ np.array([0., 1., 0.])
    hull = ConvexHull(vertices)
    normals = -hull.equations[:, :3]
    triangles = vertices[hull.simplices]
    areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0],
                                   triangles[:, 2] - triangles[:, 0]), axis=1) / 2
    candidates = np.flatnonzero(normals @ prior > .8)
    cosine = np.cos(np.deg2rad(5))
    scores = np.array([areas[normals @ normals[index] > cosine].sum()
                       for index in candidates])
    best = candidates[scores.argmax()]
    patch = normals @ normals[best] > cosine
    up = np.sum(normals[patch] * areas[patch, None], axis=0)
    up /= np.linalg.norm(up)
    forward = rotation @ np.array([1., 0., 0.])
    forward -= up * np.dot(forward, up)
    forward /= np.linalg.norm(forward)
    width = np.cross(up, forward)
    coordinates = np.column_stack([vertices @ forward, vertices @ width, vertices @ up])
    lowest = float(coordinates[:, 2].min())
    sole = coordinates[coordinates[:, 2] <= lowest + .006]
    heel = np.array([np.percentile(sole[:, 0], 5), np.median(sole[:, 1]), lowest])
    toe = np.array([np.percentile(sole[:, 0], 95), np.median(sole[:, 1]), lowest])
    basis = np.column_stack([forward, width, up])
    return dict(
        heel_local_in_foot=(basis @ heel).tolist(),
        toe_local_in_foot=(basis @ toe).tolist(),
        sole_up_local_in_foot=up.tolist(),
        forward_local_in_foot=forward.tolist(),
        geometry='official reference shoe: area-dominant lower hull plane near GMR sole normal; fixed 6mm lower band 5/95 percentiles',
        gmr_to_surface_correction_deg=float(np.degrees(np.arccos(np.clip(up @ prior, -1, 1)))),
        hull=np.round(vertices[hull.vertices], 8).tolist(),
    )


def build_geometry(bind):
    import numpy as np
    from scipy.spatial import ConvexHull

    nodes = {node['name']: node for node in bind['nodes']}
    unit = bind['unit_meters']
    matrices = {}
    for name, node in nodes.items():
        matrix = np.eye(4)
        matrix[:3] = node['world']
        matrices[name] = matrix
    allowed = {'Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head'} | {
        side + joint for side in ('Left', 'Right')
        for joint in ('UpLeg', 'Leg', 'Foot', 'Toe', 'Shoulder', 'Arm', 'ForeArm', 'Hand')
    }
    groups = {}
    for vertex in bind['vertices']:
        name = vertex['bone']
        target = name
        while target not in allowed and target in nodes:
            target = nodes[target]['parent']
        if target not in allowed:
            continue
        point = np.r_[vertex['p'], 1.]
        local = (np.linalg.inv(matrices[target]) @ matrices[name] @ point)[:3] * unit
        groups.setdefault(target, []).append(local)
    result = dict(
        schema_version=1,
        source='Ubisoft official fbx/model_skeleton.fbx',
        source_url='https://github.com/ubisoft/ubisoft-laforge-animation-dataset/blob/master/fbx/model_skeleton.fbx',
        fbx_sha256=FBX_SHA256,
        units='metres',
        method='dominant skin binding; fingers merged to Hand; rigid per-bone convex hulls',
        limitation='joint-skin blending is approximated at segment boundaries; inferred contacts are not force measurements',
        bones={},
    )
    for name, points in groups.items():
        vertices = np.array(points)
        hull = vertices[ConvexHull(vertices).vertices]
        result['bones'][name] = dict(
            vertices=np.round(hull, 8).tolist(),
            parent=nodes[name]['parent'],
            bind_parent_translation_m=(np.array(nodes[name]['local'])[:, 3] * unit).tolist(),
            raw_vertices=len(vertices),
        )
    result['feet'] = {}
    for side in ('Left', 'Right'):
        foot, toe = side + 'Foot', side + 'Toe'
        relative = np.linalg.inv(matrices[foot]) @ matrices[toe]
        toe_vertices = np.array(groups[toe]) @ relative[:3, :3].T + relative[:3, 3] * unit
        vertices = np.r_[np.array(groups[foot]), toe_vertices]
        result['feet'][side] = foot_geometry(vertices, relative)
    result['semantic_bones'] = SEMANTIC_BONES.copy()
    return validate_geometry(result)


def prepare_geometry(args):
    source = Path(args.fbx).expanduser().resolve()
    if sha(source) != FBX_SHA256:
        raise ValueError('FBX SHA-256 mismatch. Use the official LAFAN model_skeleton.fbx.')
    ufbx = Path(args.ufbx_dir).expanduser().resolve()
    for filename, expected in UFBX_HASHES.items():
        if sha(ufbx / filename) != expected:
            raise ValueError(f'ufbx source mismatch: use {filename} from commit {UFBX_COMMIT}')
    extractor = Path(__file__).with_name('reference') / 'extract_lafan_bind.c'
    with tempfile.TemporaryDirectory(prefix='dex-lafan-geometry-') as directory:
        binary = Path(directory) / 'extract'
        subprocess.run([args.compiler, '-O2', '-I', str(ufbx), str(extractor),
                        str(ufbx / 'ufbx.c'), '-lm', '-o', str(binary)], check=True)
        extracted = subprocess.run([str(binary), str(source)], check=True,
                                   capture_output=True, text=True)
        surface = build_geometry(json.loads(extracted.stdout))
    output = Path(args.out).expanduser().resolve() if args.out else geometry_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         prefix=output.name + '.', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            json.dump(surface, file, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps(dict(output=str(output), sha256=sha(output), fbx_sha256=FBX_SHA256,
                          bones=len(surface['bones']), ufbx_commit=UFBX_COMMIT), indent=2))


def add_parser(subparsers):
    parser = subparsers.add_parser('prepare-lafan-geometry', help=__doc__)
    parser.add_argument('--fbx', required=True, help='Official LAFAN model_skeleton.fbx')
    parser.add_argument('--ufbx-dir', required=True, help='Pinned upstream ufbx.c and ufbx.h directory')
    parser.add_argument('--compiler', default='cc', help='C compiler executable')
    parser.add_argument('--out', help='Defaults to DEX_LAFAN_GEOMETRY or data/lafan1/local_geometry/lafan1_surfaces.json')
    parser.set_defaults(fn=prepare_geometry)
