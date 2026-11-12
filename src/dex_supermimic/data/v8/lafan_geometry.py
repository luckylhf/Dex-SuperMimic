"""Resolve and validate the user's locally generated LAFAN reference geometry."""
import json
import os
from pathlib import Path

import numpy as np

from dex_supermimic.paths import ROOT

FBX_SHA256 = '3d9349b5ec686248be6ab73ea3b918f486016a0d22e4b4b80d5418c8f3a608aa'
SEMANTIC_BONES = {
    'pelvis': 'Hips', 'torso': 'Spine2', 'head': 'Neck',
    'Left_thigh': 'LeftUpLeg', 'Left_shin': 'LeftLeg',
    'Left_upper_arm': 'LeftArm', 'Left_forearm': 'LeftForeArm', 'Left_hand': 'LeftHand',
    'Right_thigh': 'RightUpLeg', 'Right_shin': 'RightLeg',
    'Right_upper_arm': 'RightArm', 'Right_forearm': 'RightForeArm', 'Right_hand': 'RightHand',
}


def geometry_path():
    default = ROOT / 'data/lafan1/local_geometry/lafan1_surfaces.json'
    return Path(os.environ.get('DEX_LAFAN_GEOMETRY', default)).expanduser().resolve()


def validate_geometry(surface):
    """Accept the original schema while checking every surface used at runtime."""
    try:
        if (surface['schema_version'] != 1 or surface['units'] != 'metres'
                or surface['fbx_sha256'] != FBX_SHA256
                or surface['semantic_bones'] != SEMANTIC_BONES):
            raise ValueError('source, units or schema mismatch')
        for bone in SEMANTIC_BONES.values():
            vertices = np.asarray(surface['bones'][bone]['vertices'], dtype=float)
            if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 4:
                raise ValueError('invalid bone hull: ' + bone)
            if not np.isfinite(vertices).all():
                raise ValueError('non-finite bone hull: ' + bone)
        for side in ('Left', 'Right'):
            foot = surface['feet'][side]
            for key in ('heel_local_in_foot', 'toe_local_in_foot',
                        'sole_up_local_in_foot', 'forward_local_in_foot'):
                vector = np.asarray(foot[key], dtype=float)
                if vector.shape != (3,) or not np.isfinite(vector).all():
                    raise ValueError('invalid foot vector: ' + side + '/' + key)
            up = np.asarray(foot['sole_up_local_in_foot'])
            forward = np.asarray(foot['forward_local_in_foot'])
            if (abs(np.linalg.norm(up) - 1.) > 1e-6
                    or abs(np.linalg.norm(forward) - 1.) > 1e-6
                    or abs(up @ forward) > 1e-6):
                raise ValueError('invalid foot basis: ' + side)
            if not np.isfinite(float(foot['gmr_to_surface_correction_deg'])) or not foot['geometry']:
                raise ValueError('invalid foot calibration: ' + side)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid local LAFAN geometry: ' + str(exc)) from exc
    return surface


def load_geometry():
    path = geometry_path()
    if not path.is_file():
        raise FileNotFoundError(
            f'LAFAN reference geometry is required at {path}. Generate it with '
            'dex-sm data prepare-lafan-geometry --fbx /path/to/model_skeleton.fbx '
            '--ufbx-dir /path/to/ufbx. Set DEX_LAFAN_GEOMETRY for a custom output path.'
        )
    return validate_geometry(json.loads(path.read_text()))
