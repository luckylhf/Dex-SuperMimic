"""Own two ROS simulation processes on an isolated domain; allow whole long references."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--reference',required=True);p.add_argument('--out',required=True)
    p.add_argument('--max-steps',type=int,default=0);p.add_argument('--ros-domain',type=int,default=232);a=p.parse_args()
    assert 215<=a.ros_domain<=232
    with np.load(a.reference,allow_pickle=False) as z:m=json.loads(str(z['metadata']))
    steps=m['num_frames']-1 if a.max_steps<=0 else min(a.max_steps,m['num_frames']-1)
    timeout=max(120,steps*m['control_dt']*2+60)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,ROS_DOMAIN_ID=str(a.ros_domain),ROS_LOCALHOST_ONLY='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MUJOCO_GL='egl')
    cmd=[sys.executable,'-u','-m','dex_supermimic.deployment.ros_demo','--bundle',a.bundle,'--reference',a.reference,'--out',a.out,'--max-steps',str(a.max_steps)]
    children=[];files=[];started=time.monotonic()
    try:
        for mode in ['controller','sim']:
            f=out.with_suffix('.'+mode+'.log').open('w');files.append(f)
            children.append(subprocess.Popen(cmd+['--mode',mode],env=env,stdout=f,stderr=subprocess.STDOUT))
        code=children[1].wait(timeout=timeout)
        if code:raise RuntimeError('ROS simulator failed: '+str(code))
        if children[0].poll() is not None:raise RuntimeError('ROS controller exited prematurely')
        r=json.loads(out.read_text());assert r['reference']['source_sha256']==m['source_sha256']
    finally:
        out.with_suffix('.termination_requested').touch()
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=5)
            except subprocess.TimeoutExpired:c.kill();c.wait()
        for f in files:f.close()
        out.with_suffix('.cleanup.json').write_text(json.dumps(dict(owned_pids=[c.pid for c in children],exit_codes=[c.returncode for c in children],timeout_seconds=timeout,wall_seconds=time.monotonic()-started),indent=2))
if __name__=='__main__':main()
