#!/usr/bin/env python3
"""Summarize network calibration evidence locally, outside model context."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.context_builder import observed_peer
from experiments.review_case import phase_statistics, review


def summarize(directory):
    ground = json.loads((directory / 'ground-truth.json').read_text())
    if ground['scenario']['variant'] not in ('network-delay', 'network-loss'):
        raise ValueError('Network candidate required')
    source = ground['resolved']['source_service']
    destination = ground['resolved']['destination_service']
    start = dt.datetime.fromisoformat(ground['injection_requested_at']).timestamp()
    end = dt.datetime.fromisoformat(ground['cleanup_completed_at']).timestamp()
    traffic = json.loads((directory / 'traffic.json').read_text())
    route = '/orders' if source == 'orders' else '/cart' if source == 'front-end' else None
    points = [(dt.datetime.fromisoformat(row['timestamp']).timestamp(), row['latency_ms'])
              for row in traffic['requests'] if route and row['method'] == 'POST' and row['path'] == route]
    raw = json.loads((directory / 'telemetry/traces.json').read_text())
    spans = []; seen = set()
    for document in raw if isinstance(raw, list) else [raw]:
        for resource in document.get('result', {}).get('resourceSpans', []):
            service = next((a.get('value', {}).get('stringValue')
                            for a in resource.get('resource', {}).get('attributes', [])
                            if a.get('key') == 'service.name'), None)
            if service != source:
                continue
            for scope in resource.get('scopeSpans', []):
                for span in scope.get('spans', []):
                    identity = (service, span.get('traceId'), span.get('spanId'))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if span.get('kind') != 3 or observed_peer(span.get('attributes', []), 'client') != destination:
                        continue
                    left = int(span['startTimeUnixNano']); right = int(span['endTimeUnixNano'])
                    spans.append((left / 1e9, max(0, right - left) / 1e6))
    structural = review(directory)
    counters = json.loads((directory / 'network-counters.json').read_text()) if (directory / 'network-counters.json').exists() else {}
    return {'status': 'observations_ready_effect_review_required', 'scenario_id': ground['scenario']['scenario_id'],
            'observed_edge_to_review': [source, destination], 'structural_checks': structural['checks'],
            'route': route, 'route_latency_ms': phase_statistics(points, start, end),
            'matching_client_span_latency_ms': phase_statistics(spans, start, end),
            'qdisc_max_reported_drops': counters.get('max_reported_drops'),
            'completed_journeys': traffic['completed_journeys'], 'failed_requests': traffic['failed_requests'],
            'independent_human_review': 'pending', 'official_admitted': False,
            'note': 'Uses ground truth only to audit the targeted edge. Never index or send this file as observation context.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    output = args.directory / 'network-observation-review.json'
    if output.exists():
        parser.error('Refuse to overwrite an existing review')
    result = summarize(args.directory)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
