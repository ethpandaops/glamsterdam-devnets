"""Wait for Erigon's compressors to finish before SIGTERM during snapshot audits."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import time
from pipeline_rpc import save

BUSY=re.compile(r'db/state\.\(\*[^)]*\)\.(?:merge|Merge)|db/seg\.\(\*Compressor\)')


def probe(name):
    since=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')
    subprocess.run(['docker','kill','--signal=USR1',name],check=True,capture_output=True)
    deadline=time.monotonic()+20
    while True:
        time.sleep(1)
        profile=subprocess.check_output(['docker','logs','--since',since,name],
                                        stderr=subprocess.STDOUT,text=True)
        if 'goroutine profile: total ' in profile:
            # Let the signal handler finish writing its multi-line profile.
            time.sleep(1)
            profile=subprocess.check_output(['docker','logs','--since',since,name],
                                            stderr=subprocess.STDOUT,text=True)
            break
        if time.monotonic()>=deadline:
            raise RuntimeError('Erigon did not emit its SIGUSR1 goroutine profile')
    busy=sorted({line.strip() for line in profile.splitlines() if BUSY.search(line)})
    return {'time':time.time(),'busy':bool(busy),'frames':busy},profile


def wait_for_idle(name,report_path,timeout=7200):
    start=time.monotonic();idle=0
    while idle<2:
        state,profile=probe(name)
        idle=0 if state['busy'] else idle+1
        state.update(wait_seconds=time.monotonic()-start,consecutive_idle=idle)
        save(report_path,state)
        Path(str(report_path)+'.profile.log').write_text(profile)
        if idle==2:return
        if time.monotonic()-start>=timeout:
            raise RuntimeError('Erigon merge/compression still active; refusing SIGTERM after known cancellation deadlock')
        if state['busy']:
            print(f'Waiting for Erigon merge/compression before shutdown ({state["wait_seconds"]:.0f}s)',flush=True)
            time.sleep(45)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.check:
        state,_=probe('pbt-1-erigon-execution');print(json.dumps(state))
    else:
        wait_for_idle('pbt-1-erigon-execution',Path('/data/pbt-1/pipeline/erigon-idle.json'))
