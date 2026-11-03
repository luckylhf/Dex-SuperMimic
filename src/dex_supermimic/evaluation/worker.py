"""One CPU evaluation worker per durable queue; failed jobs remain visible."""
import argparse
import fcntl
import json
from pathlib import Path
import time
import traceback
from .evaluate import evaluate
from dex_supermimic.common import atomic

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue',required=True);p.add_argument('--suite',required=True);p.add_argument('--history',required=True)
    p.add_argument('--ros-python');p.add_argument('--ros-setup');p.add_argument('--domain',type=int,default=226)
    p.add_argument('--render',action='store_true');p.add_argument('--once',action='store_true');p.add_argument('--stop-file')
    a=p.parse_args();queue=Path(a.queue).resolve();queue.mkdir(parents=True,exist_ok=True)
    with (queue/'.worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while not (a.stop_file and Path(a.stop_file).exists()):
            jobs=sorted(queue.glob('job_*.json'))
            jobs=[j for j in jobs if not j.with_suffix('.done').exists() and not j.with_suffix('.failed').exists()]
            if not jobs:
                if a.once:return
                time.sleep(5);continue
            job=jobs[0];data=json.loads(job.read_text())
            try:
                evaluate(argparse.Namespace(checkpoint=data['checkpoint'],out=data['out'],suite=a.suite,history=a.history,
                    ros_python=a.ros_python,ros_setup=a.ros_setup,domain=a.domain,max_steps=0,render=a.render))
                atomic(job.with_suffix('.done'),dict(status='completed'))
            except Exception:
                atomic(job.with_suffix('.failed'),dict(error=traceback.format_exc()))
                raise
            if a.once:return

if __name__=='__main__':main()
