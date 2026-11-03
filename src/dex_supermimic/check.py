"""Read-only environment/asset diagnostics."""
import importlib.metadata
import json
import shutil
from dex_supermimic.paths import ASSETS
from dex_supermimic.common import sha

def main():
    versions = {}
    for name in ('numpy','torch','mujoco','mujoco-warp','warp-lang','mjlab','onnx','onnxruntime','rclpy'):
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name] = 'not installed / ROS system package'
    checks = {p: (ASSETS/p).is_file() for p in ('model.json','mjcf/dex_29.xml','LICENSE')}
    if all(checks.values()):
        model = json.loads((ASSETS/'model.json').read_text())
        checks['xml_hash_matches_manifest'] = sha(ASSETS/'mjcf/dex_29.xml') == model['model_sha256']
    print(json.dumps(dict(versions=versions, assets=str(ASSETS), checks=checks,
                         nvidia_smi=shutil.which('nvidia-smi'), ffmpeg=shutil.which('ffmpeg')),indent=2))

if __name__ == '__main__': main()
