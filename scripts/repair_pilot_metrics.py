#!/usr/bin/env python3
"""Re-query archived metric windows; preserve already exported logs and traces.

Jaeger is in-memory, so never overwrite an older trace export with a new empty
query after its retention window has passed.
"""
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.metric_queries import QUERIES
from verify_telemetry import get

failed=False
for case in sorted(Path('data/pilot').glob('PILOT-*')):
    ground=case/'ground-truth.json'
    if not ground.exists() or json.loads(ground.read_text()).get('status')!='injected': continue
    source=case/('telemetry-complete' if (case/'telemetry-complete/capture.json').exists() else 'telemetry')
    if not (source/'capture.json').exists(): continue
    metadata=json.loads((source/'capture.json').read_text())
    target=case/'telemetry-corrected'
    target.mkdir(exist_ok=True)
    try:
        metrics={name:{'query':query,'response':get('http://127.0.0.1:9090/api/v1/query_range',
                    {'query':query,'start':metadata['window_start'],'end':metadata['window_end'],'step':5})}
                 for name,query in QUERIES.items()}
        # Retention may have expired since the pilot. Preserve the last complete
        # metric export just as we preserve old Jaeger exports.
        if not all(v['response'].get('data',{}).get('result') for v in metrics.values()):
            raise RuntimeError('Metric window incomplete/expired; existing export was preserved')
        (target/'metrics.json').write_text(json.dumps(metrics)+'\n')
        for name in ('logs.json','traces.json'):
            if (source/name).exists(): shutil.copyfile(source/name,target/name)
        metadata['metrics_query_version']='current-container-id-join-v1'
        metadata['quality']['metrics_present']=all(v['response'].get('data',{}).get('result') for v in metrics.values())
        metadata['preserved_log_and_trace_export']=True
        (target/'capture.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print(case.name,'corrected_metrics=',metadata['quality']['metrics_present'],flush=True)
    except Exception as exc:
        failed=True
        (target/'repair-error.json').write_text(json.dumps({'error':type(exc).__name__,'message':str(exc)})+'\n')
        print(case.name,'FAILED',type(exc).__name__,flush=True)
raise SystemExit(1 if failed else 0)
