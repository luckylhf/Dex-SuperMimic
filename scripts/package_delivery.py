"""Build the complete source + baseline + demo delivery; no training datasets."""
from pathlib import Path
import hashlib
import json
import zipfile
from dex_supermimic.baseline import verify

root=Path(__file__).resolve().parents[1]
verify(root,hashes=True)
paths=set()
for name in ('README.md','LICENSE','THIRD_PARTY.md','pyproject.toml','requirements-mjlab.txt','.gitignore'):
    paths.add(Path(name))
for folder in ('src','scripts','tests','configs','docs','LICENSES','.github'):
    for p in (root/folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'):
            paths.add(p.relative_to(root))
for folder in ('data','assets','checkpoints','external'):
    paths.update(p.relative_to(root) for p in (root/folder).rglob('README.md'))
for manifest,base in [(Path('checkpoints/12341/artifacts_manifest.json'),Path('.')),
                      (Path('data/evaluation/download_manifest.json'),Path('data/evaluation'))]:
    paths.add(manifest)
    paths.update(base/row['path'] for row in json.loads((root/manifest).read_text())['files'])
paths.update([Path('data/evaluation/suite.json'),Path('data/evaluation/LOCAL_FILES.md')])
out=root/'dist';out.mkdir(exist_ok=True)
target=out/'Dex-SuperMimic-12341.zip';temporary=target.with_suffix('.zip.partial')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for path in sorted(paths):
        z.write(root/path,'Dex-SuperMimic/'+path.as_posix())
with zipfile.ZipFile(temporary) as z:
    failure=z.testzip()
    if failure:raise ValueError('ZIP CRC failure: '+failure)
temporary.replace(target)
h=hashlib.sha256()
with target.open('rb') as f:
    for chunk in iter(lambda:f.read(4*1024**2),b''):h.update(chunk)
target.with_suffix('.zip.sha256').write_text(h.hexdigest()+'  '+target.name+'\n')
print(json.dumps(dict(file=str(target),files=len(paths),bytes=target.stat().st_size,sha256=h.hexdigest()),indent=2))
