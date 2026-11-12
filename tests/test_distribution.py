"""A baseline manifest must preserve geometry, media and weight exclusions."""
import json
from pathlib import Path
import runpy
import shutil

import pytest


@pytest.mark.parametrize('filename', [
    'lafan1_surfaces.json', 'fbx_bind_geometry.json', 'Model.FBX', 'replay.gif', 'replay.mp4',
    'gvhmr_siga24_release.ckpt', 'vitpose.pth', 'model.safetensors',
])
def test_manifest_cannot_reintroduce_excluded_payload(tmp_path, monkeypatch, filename):
    from dex_supermimic import baseline
    # Isolate archive selection from the separately tested baseline verifier.
    monkeypatch.setattr(baseline, 'verify', lambda *args, **kwargs: None)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    script = scripts / 'package_delivery.py'
    shutil.copy2(Path(__file__).resolve().parents[1] / 'scripts/package_delivery.py', script)
    checkpoint = tmp_path / 'checkpoints/12341'
    checkpoint.mkdir(parents=True)
    (checkpoint / 'artifacts_manifest.json').write_text(json.dumps({'files': []}))
    evaluation = tmp_path / 'data/evaluation'
    evaluation.mkdir(parents=True)
    (evaluation / 'download_manifest.json').write_text(json.dumps({'files': [{'path': filename}]}))
    with pytest.raises(ValueError, match='Excluded geometry, media or external weights'):
        runpy.run_path(str(script), run_name='__main__')
    assert not (tmp_path / 'dist').exists()
