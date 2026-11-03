"""Verify the actual baseline payload, without importing the training stack."""
import argparse
import json
from pathlib import Path
from .common import sha
from .paths import ROOT

def verify(root, hashes=False):
    root=Path(root).resolve()
    manifests=[root/'checkpoints/12341/artifacts_manifest.json',root/'data/evaluation/download_manifest.json']
    missing=[str(p.relative_to(root)) for p in manifests if not p.is_file()]
    if missing:raise FileNotFoundError('Baseline attachments missing: '+', '.join(missing)+'. Use the complete Dex-SuperMimic-12341.zip delivery.')
    count=0;total=0
    for manifest,base in [(manifests[0],root),(manifests[1],root/'data/evaluation')]:
        for row in json.loads(manifest.read_text())['files']:
            rel=Path(row['path'])
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid attachment path')
            p=base/rel
            if not p.is_file():raise FileNotFoundError(p)
            if p.stat().st_size!=row['bytes']:raise ValueError('File size mismatch: '+str(p))
            if hashes and sha(p)!=row['sha256']:raise ValueError('SHA-256 mismatch: '+str(p))
            count+=1;total+=row['bytes']
    contract=json.loads((root/'checkpoints/12341/bundle/contract.json').read_text())
    if contract['iteration']!=12341:raise ValueError('Wrong baseline iteration')
    suite=json.loads((root/'data/evaluation/suite.json').read_text())
    if set(suite['references'])!={'gbtc','dance_boy','dance_girl'}:raise ValueError('Incomplete baseline suite')
    for row in suite['references'].values():
        p=root/'data/evaluation'/row['reference']
        if not p.is_file():raise FileNotFoundError(p)
        if hashes and sha(p)!=row['reference_sha256']:raise ValueError('Reference hash mismatch')
    return dict(status='passed',files=count,bytes=total,sha256_verified=hashes,baseline=12341)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=str(ROOT));p.add_argument('--sha256',action='store_true')
    a=p.parse_args();print(json.dumps(verify(a.root,a.sha256),indent=2))

if __name__=='__main__':main()
