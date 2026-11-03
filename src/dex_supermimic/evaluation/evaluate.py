"""Export EMA actor, record physical rollouts, compare ROS, and retain per-motion best."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import numpy as np
from dex_supermimic.common import atomic, sha

def metric(report):
    rows=report['metrics']
    return dict(completed=report['completed'],elapsed_seconds=report['elapsed_seconds'],
                mean_body_global_rmse_m=sum(r['body_global_rmse_m'] for r in rows)/len(rows),
                max_root_error_m=max(r['root_error_m'] for r in rows),
                tracking_criteria_passed=report['tracking_criteria_passed'],
                termination_reason=report['termination_reason'])

def better(a,b):
    if a['completed'] != b['completed']:return a['completed']
    if not a['completed'] and abs(a['elapsed_seconds']-b['elapsed_seconds'])>.1:
        return a['elapsed_seconds']>b['elapsed_seconds']
    return (a['mean_body_global_rmse_m'],a['max_root_error_m']) < (b['mean_body_global_rmse_m'],b['max_root_error_m'])

def run(cmd, log, env, timeout=3600):
    with Path(log).open('w') as f:
        subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)

# These fields identify the contender, not the conditions under which it runs.
# Every other contract field (including future fields) participates in identity.
POLICY_FIELDS = {'checkpoint','checkpoint_sha256','iteration','policy_sha256'}

def history_identity(contract, references, profile, transport, max_steps):
    return dict(schema=2,references=references,profile=profile,transport=transport,max_steps=max_steps,
                model_sha256=contract['model_sha256'],compiled_model_sha256=contract['compiled_model_sha256'],
                control_contract={k:v for k,v in contract.items() if k not in POLICY_FIELDS})

def validate_history(history, identity):
    history=Path(history);path=history/'identity.json'
    if path.exists():
        previous=json.loads(path.read_text())
        if previous!=identity:
            raise ValueError('History physics/control/protocol mismatch or legacy identity; use a new history and re-evaluate its baseline')
    elif (history/'best.json').exists():
        raise ValueError('Best records have no verified history identity; use a new history')

@contextmanager
def history_transaction(history, identity):
    history.mkdir(parents=True,exist_ok=True)
    with (history/'.history.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        validate_history(history,identity)
        yield

def evaluate(a):
    suite_path=Path(a.suite).resolve(); suite=json.loads(suite_path.read_text())
    refs={}
    for name,row in suite['references'].items():
        if not name.replace('_','').replace('-','').isalnum():raise ValueError('Invalid case name')
        ref=Path(row['reference']); ref=ref if ref.is_absolute() else suite_path.parent/ref
        if sha(ref)!=row['reference_sha256']:raise ValueError('Reference hash mismatch: '+name)
        refs[name]=ref.resolve()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    bundle=out/'development/bundle';bundle.parent.mkdir()
    profile=suite.get('evaluation_profile','height_diagnostic_v1')
    transport='ros' if a.ros_python else 'native'
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',
             MUJOCO_GL=os.environ.get('MUJOCO_GL','egl'),DEX_EVALUATION_PROFILE=profile)
    run([sys.executable,'-m','dex_supermimic.deployment.build_bundle','export','--checkpoint',a.checkpoint,'--out',str(bundle)],out/'export.log',env)
    contract=json.loads((bundle/'contract.json').read_text())
    if sha(bundle/'model.mjb')!=contract['compiled_model_sha256']:
        raise ValueError('Compiled model hash mismatch before evaluation')
    identity=history_identity(contract,{n:sha(p) for n,p in refs.items()},profile,transport,a.max_steps)
    history=Path(a.history).resolve() if a.history else out.parent/'history'
    validate_history(history,identity)  # Reject mismatched conditions before rollout or best mutation.
    summary=dict(iteration=contract['iteration'],policy_sha256=contract['policy_sha256'],
                 evaluation_profile=profile,transport=transport,max_steps=a.max_steps,external={})
    for name,ref in refs.items():
        common=['--bundle',str(bundle),'--reference',str(ref),'--max-steps',str(a.max_steps)]
        run([sys.executable,'-m','dex_supermimic.deployment.native_mujoco',*common,'--out',str(out/f'{name}_native.json')],out/f'{name}_native.log',env)
        exact=None
        if a.ros_python:
            cmd=[a.ros_python,'-m','dex_supermimic.deployment.run_ros_isolated',*common,'--out',str(out/f'{name}_ros.json'),'--ros-domain',str(a.domain)]
            if a.ros_setup:cmd=['bash','-c','source '+shlex.quote(a.ros_setup)+'; exec '+shlex.join(cmd)]
            run(cmd,out/f'{name}_ros.log',env)
            with np.load(out/f'{name}_native.trajectory.npz') as n,np.load(out/f'{name}_ros.trajectory.npz') as r:
                exact=np.array_equal(n['qpos'],r['qpos'])
            if not exact:raise AssertionError('Native/ROS trajectory differs: '+name)
        report=json.loads((out/f'{name}_{transport}.json').read_text())
        summary['external'][name]=dict(metric(report),native_ros_exact=exact,
                                     training_member=suite['references'][name].get('training_member'))
    atomic(out/'summary.json',summary)
    # Recheck under the publication lock: another evaluator may have completed
    # while this one was simulating. Never upgrade incomplete legacy identities.
    with history_transaction(history,identity):
        best_file=history/'best.json'; best=json.loads(best_file.read_text()) if best_file.exists() else {}
        config=dict(latest_folder=str(out),latest_iteration=contract['iteration'],latest_label='Dex SuperMimic',
                    evaluation_profile=profile,transport=transport,out=str(out/'videos'),motions={})
        for name,reference in refs.items():
            result=summary['external'][name]
            if name not in best or better(result,best[name]['metrics']):
                best[name]=dict(folder=str(out),iteration=contract['iteration'],policy_sha256=contract['policy_sha256'],metrics=result)
            row=best[name]
            config['motions'][name]=dict(reference=str(reference),best_folder=row['folder'],best_iteration=row['iteration'],best_label=Path(row['folder']).name,
                                         same_model=row['policy_sha256']==contract['policy_sha256'])
        atomic(history/'identity.json',identity)
        atomic(best_file,best);atomic(out/'comparison.json',config)
    if a.render:
        run([sys.executable,'-m','dex_supermimic.evaluation.render','--config',str(out/'comparison.json')],out/'render.log',env,timeout=14400)
    print(json.dumps(summary,indent=2))

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True);p.add_argument('--suite',required=True);p.add_argument('--out',required=True)
    p.add_argument('--history');p.add_argument('--ros-python');p.add_argument('--ros-setup');p.add_argument('--domain',type=int,default=226)
    p.add_argument('--max-steps',type=int,default=0);p.add_argument('--render',action='store_true')
    return p

if __name__=='__main__':evaluate(parser().parse_args())
