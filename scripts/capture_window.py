#!/usr/bin/env python3
"""Export a fixed observation window from local monitoring APIs."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.telemetry import query_logs,query_traces
from app.metric_queries import QUERIES
from scripts.verify_telemetry import get, trace_services

def capture(start, end, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    errors, quality = {}, {}
    try:
        metrics = {name: {'query': query, 'response': get('http://127.0.0.1:9090/api/v1/query_range',
                    {'query': query, 'start': start, 'end': end, 'step': 5})} for name, query in QUERIES.items()}
        (destination / 'metrics.json').write_text(json.dumps(metrics)+'\n')
        quality['metrics_present'] = all(v['response'].get('data', {}).get('result') for v in metrics.values())
    except Exception as exc:
        errors['metrics'] = str(exc)
    try:
        logs = query_logs(get,'http://127.0.0.1:3100',int(start*10**9),int(end*10**9))
        (destination / 'logs.json').write_text(json.dumps(logs)+'\n')
        count = sum(len(s.get('values', [])) for s in logs.get('data', {}).get('result', []))
        quality['logs_present'], quality['log_lines'], quality['log_export_incomplete'] = count > 0, count, logs['export_metadata']['incomplete']
    except Exception as exc:
        errors['logs'] = str(exc)
    try:
        traces = query_traces(get,'http://127.0.0.1:16686',start,end)
        (destination / 'traces.json').write_text(json.dumps(traces)+'\n')
        groups = trace_services(traces)
        quality['traces_present'], quality['trace_count'] = bool(groups), len(groups)
        quality['trace_limit_reached'] = traces['export_metadata']['incomplete']
        quality['trace_export_metadata'] = traces['export_metadata']
        quality['cross_service_trace'] = any(len(names) > 1 for names in groups.values())
    except Exception as exc:
        errors['traces'] = str(exc)
    report = {'window_start': start, 'window_end': end, 'quality': quality, 'errors': errors,
              'admission_status': 'requires_review', 'note': 'Source presence is not evidence of correct root cause.'}
    (destination / 'capture.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.start, args.end, args.output), indent=2))
