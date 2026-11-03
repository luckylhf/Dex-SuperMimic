"""Create an evaluation suite from already prepared reference NPZs."""
import argparse
import json
from pathlib import Path
from dex_supermimic.common import atomic,sha

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference',action='append',required=True,help='name=path/to/prepared_reference.npz')
p.add_argument('--in-training',action='append',default=[],help='Mark a named case as an in-training difficulty probe')
p.add_argument('--out',required=True);p.add_argument('--profile',choices=['strict_v1','height_diagnostic_v1'],default='height_diagnostic_v1')
a=p.parse_args();out=Path(a.out).resolve();refs={}
import numpy as np
for item in a.reference:
    name,value=item.split('=',1);path=Path(value).resolve()
    if name in refs:raise ValueError('Duplicate case')
    with np.load(path,allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata']))
        if metadata['feature_contract']!='dex-instanttrack-goal-v1-50hz-wxyz-row6d':raise ValueError('Not a prepared reference')
    import os
    refs[name]=dict(reference=os.path.relpath(path,out.parent),reference_sha256=sha(path),training_member=name in a.in_training)
if set(a.in_training)-set(refs):raise ValueError('Unknown in-training case name')
atomic(out,dict(evaluation_profile=a.profile,references=refs))
print(out)
