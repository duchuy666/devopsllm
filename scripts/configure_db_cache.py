#!/usr/bin/env python3
"""Bound WiredTiger caches in this local testbed, without restarting databases."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.experiment_runtime import KUBE,experiment_lock

ROOT=Path(__file__).resolve().parents[1]
TARGETS=('user-db','carts-db','orders-db')


def mongo(service,expression):
    raw=subprocess.check_output(KUBE+['-n','sock-shop','exec','deployment/'+service,'--','mongo','--quiet','--eval',expression],text=True,timeout=30)
    return json.loads(raw.strip().splitlines()[-1])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    rows=[]
    with experiment_lock():
        for service in TARGETS:
            expression='var s=db.serverStatus(); print(JSON.stringify({version:s.version,cache_max:s.wiredTiger.cache["maximum bytes configured"],cache_used:s.wiredTiger.cache["bytes currently in the cache"],resident_mib:s.mem.resident}));'
            before=mongo(service,expression);row={'service':service,'before':before};rows.append(row)
            if args.apply and before['cache_max']!=128*1024**2:
                result=mongo(service,'print(JSON.stringify(db.adminCommand({setParameter:1,wiredTigerEngineRuntimeConfig:"cache_size=128M"})));')
                row['command_result']=result
                if result.get('ok')!=1:raise RuntimeError('Cache change rejected for '+service)
            row['after']=mongo(service,expression)
            if args.apply and row['after']['cache_max']!=128*1024**2:raise RuntimeError('Cache readback mismatch')
        directory=ROOT/'results/db-cache'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
        report={'status':'runtime_cache_configured' if args.apply else 'read_only_audit','rows':rows,
            'limitations':['Runtime setting resets when mongod restarts; rerun before experiments.',
                'Cache cap is not a total process RSS cap and does not establish that prior OOM was caused by cache.',
                'No database restart, data deletion or schema change performed.']}
        (directory/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
