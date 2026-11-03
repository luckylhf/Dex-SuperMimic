"""Low-rate resource sampler; optional synchronized stage timing for diagnostics."""
from pathlib import Path
import json,os,subprocess,threading,time
class Sampler:
    def __init__(self,path):
        self.path=Path(path);self.stop=threading.Event();self.thread=threading.Thread(target=self._run,daemon=True)
    def start(self):self.thread.start();return self
    def _run(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('a',buffering=1) as f:
            while not self.stop.is_set():
                try:
                    mem=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines())
                    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],text=True,timeout=5).strip()
                    rss=next(x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')).split()[1]
                    f.write(json.dumps(dict(time=time.time(),pid=os.getpid(),gpu=gpu,rss_kB=int(rss),available_RAM_kB=int(mem['MemAvailable'].split()[0])))+'\n')
                except Exception as e:f.write(json.dumps(dict(time=time.time(),sampler_error=str(e)))+'\n')
                self.stop.wait(1)
    def close(self):self.stop.set();self.thread.join(timeout=6)
