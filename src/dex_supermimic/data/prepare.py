"""CPU conversion, quality records, deterministic shards, and portable cache import."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import sys
import traceback
from dex_supermimic.common import atomic, sha, stamp
from dex_supermimic.paths import ASSETS

TARGETS = {'dance': .40, 'locomotion': .25, 'stationary_upper': .25, 'dynamic': .10}

# Manifest metadata can change without changing the BVH. Never let it overwrite
# conversion evidence, and never use an earlier label for current membership.
DERIVED_FIELDS = {'source_sha256','output','output_sha256','frames','grade','quality',
    'status','error','ik_audit','train_eligible','dynamic_status','started_at','finished_at',
    'source_manifest_row','source_row_sha256','metadata_updated_at'}

def source_row(row):
    row = dict(row)
    reserved = DERIVED_FIELDS.intersection(row)
    if reserved: raise ValueError('Derived fields are not source metadata: '+str(sorted(reserved)))
    for key in ('anchor','evaluation_only'):
        row.setdefault(key, False)
        if not isinstance(row[key], bool): raise ValueError(key+' must be a JSON boolean')
    return row

def row_sha(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def with_metadata(record, row):
    result = dict(record)
    for key in record.get('source_manifest_row', {}): result.pop(key, None)
    result.update(row)
    result.update(source_manifest_row=dict(row), source_row_sha256=row_sha(row),
                  split='evaluation' if row['evaluation_only'] else 'train',
                  train_eligible=record.get('grade')=='A_kinematic_candidate' and not row['evaluation_only'])
    return result

def load_records(directory):
    directory = Path(directory)
    records = {p.stem:json.loads(p.read_text()) for p in sorted(directory.glob('*.json'))}
    catalog = directory.parent/'catalog.json'
    if catalog.exists():
        expected = json.loads(catalog.read_text())
        if expected['status'] != 'complete': raise ValueError('Source catalog conversion is incomplete')
        selected = []
        for name, fingerprint in expected['records'].items():
            r = records.get(name)
            if r is None or r.get('source_row_sha256') != fingerprint:
                raise ValueError('Stale or missing source metadata: '+name)
            row = r.get('source_manifest_row', {})
            if row_sha(row) != fingerprint or any(r.get(k)!=v for k,v in row.items() if k!='split'):
                raise ValueError('Conversion record disagrees with its source catalog: '+name)
            selected.append(r)
        return selected  # Records removed from the current manifest cannot re-enter training.
    return list(records.values())  # Explicit legacy records import; membership is still checked below.

def training_rows(records):
    rows = []
    for r in records:
        if r.get('grade') != 'A_kinematic_candidate': continue
        if r.get('evaluation_only'):
            raise ValueError('External evaluation motion marked as training: '+r['id'])
        rows.append(dict(r, split='train'))
    return rows

def sampling_weights(rows):
    groups = defaultdict(list)
    for row in rows: groups[row['sampling_group']].append(row)
    total = sum(TARGETS[g] for g in groups)
    result = {}
    for category, clips in groups.items():
        old = [x for x in clips if x.get('anchor', False)]
        new = [x for x in clips if not x.get('anchor', False)]
        for subset, share in ((old, .25 if new else 1), (new, .75 if old else 1)):
            actors = defaultdict(list)
            for row in subset: actors[row['actor']].append(row)
            for actor_clips in actors.values():
                for row in actor_clips:
                    result[row['id']] = TARGETS[category]/total*share/len(actors)/len(actor_clips)
    assert abs(sum(result.values())-1) < 1e-8
    return result

def _convert(task):
    row, output = task
    row = source_row(row)
    output = Path(output)
    record = output/'records'/f"{row['id']}.json"
    if record.exists():
        old = json.loads(record.read_text())
        if old.get('source_sha256') != sha(row['source']): raise ValueError('Changed source: '+row['id'])
        if old.get('output') and sha(old['output']) != old['output_sha256']: raise ValueError('Changed output: '+row['id'])
        refreshed = with_metadata(old, row)
        if refreshed != old:
            refreshed['metadata_updated_at'] = stamp()
            atomic(record, refreshed)
        return refreshed
    work = output/'work'/row['id']
    work.mkdir(parents=True, exist_ok=False)
    rec = dict(row, source_sha256=sha(row['source']), started_at=stamp(),
               dynamic_status='not_tested_by_controller', split='train')
    try:
        from .retarget_soma import convert
        from .quality import quality, compact
        mimic = Path(os.environ['DEX_MIMIC_ROOT']).expanduser().resolve()
        sys.path.insert(0, str(mimic/'scripts'))
        from pkl_to_npz import convert_single, ROBOT_MJCF
        from check_motion import validate_motion
        if sha(ROBOT_MJCF['dex_evt']) != sha(ASSETS/'mjcf/dex_29.xml'):
            raise ValueError('Dex-Mimic conversion model differs from training assets')
        pkl, npz = work/'motion.pkl', work/'motion.npz'
        convert(row['source'], pkl)
        convert_single(str(pkl), str(npz), 50, 'dex_evt', ROBOT_MJCF['dex_evt'])
        validate_motion(npz)
        result = quality(npz, pkl.with_suffix('.ik.json'))
        target = output/'motions'/f"{row['id']}.npz"
        frames = compact(npz, target)
        rec.update(status='converted', quality=result, frames=frames, output=str(target),
                   output_sha256=sha(target), ik_audit=json.loads(pkl.with_suffix('.ik.json').read_text()),
                   grade='B_needs_repair' if result['flags'] else 'A_kinematic_candidate',
                   train_eligible=not result['flags'])
    except Exception:
        rec.update(status='failed', grade='C_failed', train_eligible=False, error=traceback.format_exc())
    rec = with_metadata(rec, row)
    rec['finished_at'] = stamp()
    atomic(record, rec)
    return rec

def convert_dataset(args):
    rows = [source_row(json.loads(line)) for line in Path(args.manifest).read_text().splitlines() if line.strip()]
    seen = set()
    for row in rows:
        required = {'id', 'source', 'actor', 'sampling_group'}
        if not required <= row.keys(): raise ValueError('Manifest requires '+str(sorted(required)))
        if row['id'] in seen or not row['id'].replace('_','').replace('-','').isalnum(): raise ValueError('Duplicate or invalid ID')
        seen.add(row['id'])
        if row['sampling_group'] not in TARGETS: raise ValueError('Unknown sampling group')
        path = Path(row['source']).expanduser()
        row['source'] = str((Path(args.manifest).resolve().parent/path).resolve() if not path.is_absolute() else path)
        if not Path(row['source']).is_file(): raise FileNotFoundError(row['source'])
    out = Path(args.out).resolve()
    for folder in ('records','motions','work'): (out/folder).mkdir(parents=True, exist_ok=True)
    catalog = dict(status='converting',records={r['id']:row_sha(r) for r in rows},
                   source_manifest_sha256=sha(args.manifest))
    atomic(out/'catalog.json',catalog)
    # Child processes import numerical libraries after these limits are established.
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', CUDA_VISIBLE_DEVICES='')
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        counts = Counter()
        for rec in pool.map(_convert, [(row,str(out)) for row in rows], chunksize=1):
            counts[rec['grade']] += 1
            atomic(out/'status.json', dict(expected=len(rows), completed=sum(counts.values()), grades=dict(counts), updated_at=stamp()))
    catalog['status']='complete';atomic(out/'catalog.json',catalog)
    print(json.dumps(dict(counts), indent=2))

def build_release(args):
    records = load_records(args.records)
    rows = training_rows(records)
    if not rows: raise ValueError('No A-grade motions')
    import torch
    from instanttrack.robot import get_robot
    from instanttrack.kinematics import Kinematics
    import instanttrack.motion, instanttrack.kinematics
    from .bounded_motion import build_pack, BoundedMotionLib
    torch.set_num_threads(args.threads)
    torch.backends.cuda.matmul.allow_tf32 = True
    if len({r['id'] for r in rows}) != len(rows): raise ValueError('Duplicate motion IDs')
    for r in rows:
        if r['frames'] < 33 or r['frames'] > args.capacity: raise ValueError('Whole clip outside capacity: '+r['id'])
        if r.get('evaluation_only'): raise ValueError('External evaluation motion marked as training')
    anchors = sorted([r for r in rows if r.get('anchor')], key=lambda r:r['id'])
    others = [r for r in rows if not r.get('anchor')]
    base = sum(r['frames'] for r in anchors)
    room = args.capacity-base
    if room <= 0 or any(r['frames'] > room for r in others): raise ValueError('Increase capacity: anchors plus whole clip do not fit')
    n = max(1, math.ceil(sum(r['frames'] for r in others)/room))
    while True:
        shards = [anchors.copy() for _ in range(n)]
        sizes, groups = [base]*n, [Counter() for _ in range(n)]
        for r in sorted(others, key=lambda r:(r['sampling_group'], -r['frames'], r['id'])):
            available = [i for i in range(n) if sizes[i]+r['frames'] <= args.capacity]
            if not available: n += 1; break
            i = min(available, key=lambda i:(groups[i][r['sampling_group']], sizes[i], i))
            shards[i].append(r); sizes[i] += r['frames']; groups[i][r['sampling_group']] += r['frames']
        else: break
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'features').mkdir()
    manifest = dict(complete=False, snapshot=False, train_clips=len(rows), train_frames=sum(r['frames'] for r in rows),
                    anchors=len(anchors), shards=n, frame_capacity=args.capacity,
                    grades=dict(Counter(r.get('grade') for r in records)), training_policy='all_qualified',
                    created_at=stamp(), internal_probes_are_heldout=False)
    atomic(out/'manifest.json', manifest)
    robot = get_robot('dex'); kin = Kinematics(robot,args.device); index = []
    for i, shard in enumerate(shards):
        shard.sort(key=lambda r:r['id'])
        data = dict(records=shard, weights=sampling_weights(shard), capacity=args.capacity)
        path = out/f'shard_{i:03d}.json'; atomic(path,data)
        pack, lib = build_pack(data, kin, robot, args.device)
        bounded = BoundedMotionLib(pack,args.device,args.capacity)
        frames = torch.cat([lib.clip_start, lib.clip_end])
        if not torch.equal(lib.goal(frames,10), bounded.goal(frames,10)): raise AssertionError('Goal boundary parity')
        target = out/'features'/f'shard_{i:03d}.pt'
        torch.save(pack,target)
        index.append(dict(pack=str(target.relative_to(out)), manifest=path.name, pack_sha256=sha(target),
                          manifest_sha256=sha(path), frames=lib.num_frames, clips=len(lib.names), goal_boundary_parity=True))
        del pack, lib, bounded
    manifest['complete']=True; atomic(out/'manifest.json',manifest)
    atomic(out/'features/index.json',dict(records=index,frame_capacity=args.capacity,
        dataset_manifest_sha256=sha(out/'manifest.json'), robot_xml_sha256=sha(robot.mjcf_path),
        model_contract_sha256=sha(ASSETS/'model.json'), motion_code_sha256=sha(instanttrack.motion.__file__),
        kinematics_code_sha256=sha(instanttrack.kinematics.__file__)))
    print(json.dumps(manifest,indent=2))

def import_release(args):
    source = Path(args.source).resolve(); out = Path(args.out).resolve()
    index = json.loads((source/'features/index.json').read_text())
    if sha(source/'manifest.json') != index['dataset_manifest_sha256']: raise ValueError('Dataset manifest hash')
    # Original absolute paths are deliberately ignored: resolve by the release layout.
    resolved = []
    for row in index['records']:
        pack = source/'features'/Path(row['pack']).name
        manifest = source/Path(row['manifest']).name
        if sha(pack) != row['pack_sha256'] or sha(manifest) != row['manifest_sha256']: raise ValueError('Corrupt source cache')
        resolved.append((row,pack,manifest))
    out.mkdir(parents=True,exist_ok=False); (out/'features').mkdir()
    shutil.copy2(source/'manifest.json',out/'manifest.json')
    for row,pack,manifest in resolved:
        shutil.copy2(manifest,out/manifest.name)
        destination=out/'features'/pack.name
        if args.copy_packs: shutil.copy2(pack,destination)
        else: destination.symlink_to(pack)
        row['pack']=str(destination.relative_to(out)); row['manifest']=manifest.name
    atomic(out/'features/index.json',index)
    print('Imported',len(resolved),'verified shards;', 'copied' if args.copy_packs else 'linked', 'packs')

def main():
    p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest='command',required=True)
    c=s.add_parser('convert');c.add_argument('--manifest',required=True);c.add_argument('--out',required=True)
    c.add_argument('--workers',type=int,default=max(1,min(8,(os.cpu_count() or 2)//2)));c.set_defaults(fn=convert_dataset)
    b=s.add_parser('build');b.add_argument('--records',required=True);b.add_argument('--out',required=True)
    b.add_argument('--capacity',type=int,default=600000);b.add_argument('--device',default='cpu');b.add_argument('--threads',type=int,default=4);b.set_defaults(fn=build_release)
    i=s.add_parser('import');i.add_argument('--source',required=True);i.add_argument('--out',required=True)
    i.add_argument('--copy-packs',action='store_true');i.set_defaults(fn=import_release)
    a=p.parse_args();a.fn(a)

if __name__=='__main__':main()
