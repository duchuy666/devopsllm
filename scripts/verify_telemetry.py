#!/usr/bin/env python3
"""Verify real telemetry over local port-forwards; keep evidence on disk."""
import datetime
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.metric_queries import QUERIES


def trace_services(payload):
    grouped = {}
    documents = payload if isinstance(payload, list) else [payload]
    for document in documents:
        for resource in document.get('result', {}).get('resourceSpans', []):
            service = next((a.get('value', {}).get('stringValue') for a in resource.get('resource', {}).get('attributes', [])
                            if a.get('key') == 'service.name'), None)
            for scope in resource.get('scopeSpans', []):
                for span in scope.get('spans', []):
                    if span.get('traceId') and service:
                        grouped.setdefault(span['traceId'], set()).add(service)
    return grouped


def get(url, params=None):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read().decode()
        decoder, documents = json.JSONDecoder(), []
        remaining = body.strip()
        while remaining:
            document, end = decoder.raw_decode(remaining)
            documents.append(document)
            remaining = remaining[end:].lstrip()
        return documents[0] if len(documents) == 1 else documents


def main():
    checks, evidence = {}, {}
    queries = {
        'pod_cpu': QUERIES['cpu'],
        'pod_memory': QUERIES['memory'],
        'pod_ready': 'kube_pod_status_ready{namespace="sock-shop",condition="true"}',
    }
    for name, query in queries.items():
        try:
            data = get('http://127.0.0.1:9090/api/v1/query', {'query': query})
            evidence[name] = {'query': query, 'response': data}
            checks[name] = data.get('status') == 'success' and bool(data.get('data', {}).get('result'))
        except Exception as exc:
            checks[name], evidence[name] = False, {'error': str(exc)}
    try:
        now = time.time_ns()
        data = get('http://127.0.0.1:3100/loki/api/v1/query_range',
                   {'query': '{namespace="sock-shop"}', 'limit': 10,
                    'start': now-600*10**9, 'end': now})
        evidence['logs'] = data
        checks['logs'] = data.get('status') == 'success' and bool(data.get('data', {}).get('result'))
    except Exception as exc:
        checks['logs'], evidence['logs'] = False, {'error': str(exc)}
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        services = get('http://127.0.0.1:16686/api/v3/services')
        traces = get('http://127.0.0.1:16686/api/v3/traces', {
            'query.service_name': 'orders',
            'query.start_time_min': (now-datetime.timedelta(hours=1)).isoformat(),
            'query.start_time_max': now.isoformat(), 'query.num_traces': 10})
        evidence['services'], evidence['traces'] = services, traces
        grouped = trace_services(traces)
        evidence['trace_service_coverage'] = {tid: sorted(names) for tid, names in grouped.items()}
        checks['traces'] = bool(grouped)
        checks['cross_service_trace'] = any(len(names) >= 2 for names in grouped.values())
    except Exception as exc:
        checks['traces'], checks['cross_service_trace'] = False, False
        evidence['traces'] = {'error': str(exc)}
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'checks': checks, 'evidence': evidence}
    out = Path('results/environment/telemetry-check.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(checks, indent=2))
    print(f'Evidence: {out}')
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
