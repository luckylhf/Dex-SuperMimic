"""Copy a verified Dex robot directory into assets/dex_evt."""
import argparse
import json
from pathlib import Path
import shutil
from dex_supermimic.common import sha

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',required=True);p.add_argument('--out',default='assets/dex_evt');a=p.parse_args()
source=Path(a.source).expanduser().resolve();out=Path(a.out).resolve()
manifest=json.loads((source/'model.json').read_text())
if manifest['model_sha256']!='17573c55d1c9d9d43b2e44a5e3ebc237027bfcfb6f5b5d928aa0205792548194':
    raise ValueError('This release requires the 12341 robot model')
if sha(source/'mjcf/dex_29.xml')!=manifest['model_sha256']:raise ValueError('XML hash mismatch')
if out.exists() and any(p.name!='README.md' for p in out.iterdir()):raise FileExistsError('Destination contains assets')
for name in ('LICENSE','model.json','mjcf','meshes','meshes_visual','meshes_convex','urdf'):
    path=source/name
    if not path.exists():raise FileNotFoundError(path)
    if path.is_dir():shutil.copytree(path,out/name)
    else:out.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out/name)
import mujoco
model=mujoco.MjModel.from_xml_path(str(out/'mjcf/dex_29.xml'))
assert model.nq==36 and model.nv==35
print('Dex assets imported and compiled:',out)
