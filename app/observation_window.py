"""Export a bounded, completed observation from persisted raw telemetry only."""
import hashlib
import json
from pathlib import Path


def crop(source, destination, start, end):
    if end <= start:
        raise ValueError('Positive observation window required')
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('Refuse to replace an observation')
    capture = json.loads((source / 'capture.json').read_text())
    if capture['window_start'] > start or capture['window_end'] < end:
        raise ValueError('Raw export does not cover the precommitted observation window')
    if capture.get('errors') or capture['quality'].get('log_export_incomplete') or capture['quality'].get('trace_limit_reached'):
        raise ValueError('Cannot certify an observation from an incomplete raw export')
    payloads = {name: json.loads((source / (name + '.json')).read_text()) for name in ('metrics', 'logs', 'traces')}
    trace_documents=payloads['traces'] if isinstance(payloads['traces'],list) else [payloads['traces']]
    if payloads['logs'].get('export_metadata',{}).get('incomplete') or any(
            d.get('export_metadata',{}).get('incomplete') for d in trace_documents):
        raise ValueError('Source metadata reports an incomplete export')
    for payload in payloads['metrics'].values():
        rows = payload.get('response', {}).get('data', {}).get('result', [])
        for row in rows:
            row['values'] = [pair for pair in row.get('values', []) if start <= float(pair[0]) <= end]
        payload['response']['data']['result'] = [row for row in rows if row['values']]
    logs = payloads['logs']
    for row in logs.get('data', {}).get('result', []):
        row['values'] = [pair for pair in row.get('values', []) if start * 1e9 <= int(pair[0]) <= end * 1e9]
    logs['data']['result'] = [row for row in logs.get('data', {}).get('result', []) if row['values']]
    traces = payloads['traces']
    count = 0
    for document in traces if isinstance(traces, list) else [traces]:
        resources = document.get('result', {}).get('resourceSpans', [])
        for resource in resources:
            for scope in resource.get('scopeSpans', []):
                # A span that ends after cutoff was not yet available at cutoff.
                scope['spans'] = [s for s in scope.get('spans', [])
                                  if 'startTimeUnixNano' in s and 'endTimeUnixNano' in s
                                  and start * 1e9 <= int(s['startTimeUnixNano'])
                                  <= int(s['endTimeUnixNano']) <= end * 1e9]
                count += len(scope['spans'])
            resource['scopeSpans'] = [s for s in resource.get('scopeSpans', []) if s.get('spans')]
        document['result']['resourceSpans'] = [r for r in resources if r.get('scopeSpans')]
        # Original query counts describe the full raw export, not the crop.
        original_metadata = document.pop('export_metadata', {})
        document['export_metadata'] = {'window_start': start, 'window_end': end,
                                       'incomplete': bool(original_metadata.get('incomplete'))}
    logs.pop('export_metadata', None)
    logs['export_metadata'] = {'window_start': start, 'window_end': end, 'incomplete': False}
    quality = {'metrics_present': any(p.get('response', {}).get('data', {}).get('result') for p in payloads['metrics'].values()),
               'logs_present': bool(logs['data']['result']), 'traces_present': count > 0,
               'span_count': count, 'log_export_incomplete': False, 'trace_limit_reached': False}
    receipt = {'window_start': start, 'window_end': end, 'quality': quality, 'errors': {},
               'source_sha256': {name: hashlib.sha256((source / (name + '.json')).read_bytes()).hexdigest()
                                 for name in payloads}, 'note': 'Completed spans only; no fault labels included.'}
    destination.mkdir(parents=True)
    for name, payload in payloads.items():
        (destination / (name + '.json')).write_text(json.dumps(payload) + '\n')
    (destination / 'capture.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
