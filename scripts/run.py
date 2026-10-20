"""Rebuild numerical outputs and reports while measuring local resource usage."""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import psutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--online',action='store_true')
    parser.add_argument('--numerical-only',action='store_true')
    parser.add_argument('--reports-only',action='store_true')
    parser.add_argument('--workers',type=int,default=16)
    args=parser.parse_args();os.chdir(ROOT)
    commands=[]
    if args.online:commands.append(('acquire',[sys.executable,'scripts/acquire.py']))
    if not args.reports_only:
        commands.extend([
            ('process',[sys.executable,'scripts/process.py','--workers',str(args.workers)]),
            ('validate',[sys.executable,'scripts/validate.py']),
            ('migrate',[sys.executable,'scripts/migrate.py']),
            ('experiments',[sys.executable,'scripts/experiments.py']),
            ('sensitivity',[sys.executable,'scripts/sensitivity.py','historical','modern_same','expanded']),
            ('point-tests',[sys.executable,'scripts/validate.py','--points']),
            ('compare',[sys.executable,'scripts/compare.py']),
            ('panels',[sys.executable,'scripts/panels.py']),
            ('plot',[sys.executable,'scripts/plot.py'])])
    if not args.numerical_only:
        commands.extend([('report-source',[sys.executable,'scripts/report.py']),
                         ('compile',['bash','scripts/compile.sh'])])
    record=dict(start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                python=sys.version,platform=platform.platform(),logical_cpus=os.cpu_count(),
                machine_memory_gb=psutil.virtual_memory().total/1e9,
                gpu_hours=0,measurement='CPU is child user+system time. Peak memory is sampled sum of process-tree RSS; shared pages may be counted more than once.',
                stages=[])
    stamp=time.strftime('%Y%m%dT%H%M%S',time.gmtime());path=ROOT/f'logs/run-{stamp}.json'
    def save():
        path.write_text(json.dumps(record,indent=2));(ROOT/'logs/latest-run.json').write_text(json.dumps(record,indent=2))
    save()
    for name,command in commands:
        print('Running',name,flush=True)
        before=resource.getrusage(resource.RUSAGE_CHILDREN);begin=time.monotonic();peak=0
        with (ROOT/f'logs/build-{name}.log').open('w') as log:
            child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            process=psutil.Process(child.pid)
            while child.poll() is None:
                try:
                    rss=sum(p.memory_info().rss for p in [process]+process.children(recursive=True) if p.is_running())
                    peak=max(peak,rss)
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                time.sleep(.5)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        record['stages'].append(dict(name=name,command=command,returncode=child.returncode,
                wall_seconds=time.monotonic()-begin,cpu_seconds=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime),
                peak_tree_rss_gb=peak/1e9))
        save()
        if child.returncode:raise SystemExit(f'{name} failed; see logs/build-{name}.log')
    record['complete']=True;record['end_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());save()
    if not args.numerical_only:
        # Final usage PDF reads the completed build measurements. Its own brief
        # compilation is explicitly excluded from the completed-stage totals.
        subprocess.run([sys.executable,'scripts/usage.py'],check=True)
    print('Rebuild completed:',path,flush=True)


if __name__=='__main__':main()
