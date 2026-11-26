#!/usr/bin/env python3
"""Offline scoring. Labels never enter retrieval/context or a provider call."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.report_schema import IncidentReport


def target_key(value):
    if isinstance(value, list):
        if len(value) != 2:
            raise ValueError('Directed edges need exactly source and destination')
        return tuple(str(part).strip() for part in value)
    return tuple(part.strip() for part in value.split('->'))


def wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes/total
    denominator = 1+z*z/total
    center = (p+z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0, center-half), min(1, center+half)]


def score(expected, hypotheses):
    matches = [target_key(h['service']) == target_key(expected['target']) and
               h['fault_type'] == expected['fault_type'] for h in hypotheses[:3]]
    return {'top1_correct': bool(matches and matches[0]), 'top3_correct': any(matches)}


def evaluate(manifest, base):
    if manifest['dataset_role'] not in ('development_pilot', 'official_test'):
        raise ValueError('Explicit dataset role required')
    cases = manifest['cases']
    if len({case['case_id'] for case in cases}) != len(cases):
        raise ValueError('Duplicate case IDs would bias the denominator')
    if not manifest['modes'] or len(set(manifest['modes'])) != len(manifest['modes']):
        raise ValueError('Modes must be nonempty and unique')
    rows = []
    for case in cases:
        allowed_status={'admitted'} if manifest['dataset_role']=='official_test' else {'admitted','reviewed_for_development_scoring'}
        if case['admission_status'] not in allowed_status or (manifest['dataset_role']=='official_test' and case.get('split')!='test'):
            raise ValueError('Only admitted cases in the declared evaluation split may be scored')
        for mode in manifest['modes']:
            row = {'case_id': case['case_id'], 'mode': mode, 'fault_type': case['expected']['fault_type'],
                   'status': 'missing_report', 'top1_correct': False, 'top3_correct': False}
            filename = case.get('reports', {}).get(mode)
            if filename:
                path = base/filename
                if path.exists():
                    try:
                        saved = json.loads(path.read_text())
                        report = IncidentReport.model_validate(saved['generated']['report'])
                        if saved['mode'] != mode or report.incident_id != case['context_id']:
                            raise ValueError('Context or mode mismatch')
                        row.update(score(case['expected'], [h.model_dump() for h in report.hypotheses]),
                                   status='valid_report', report=str(path))
                    except (ValueError, KeyError, TypeError) as exc:
                        row.update(status='invalid_report', error_type=type(exc).__name__)
            rows.append(row)
    groups = defaultdict(list)
    for row in rows:
        groups[(row['mode'], 'all')].append(row)
        groups[(row['mode'], row['fault_type'])].append(row)
    summaries = []
    for (mode, fault_class), group in sorted(groups.items()):
        n = len(group)
        summary = {'mode': mode, 'fault_class': fault_class, 'denominator': n,
                   'valid_reports': sum(r['status']=='valid_report' for r in group),
                   'missing_or_invalid_reports': sum(r['status']!='valid_report' for r in group)}
        for metric in ('top1_correct', 'top3_correct'):
            successes = sum(row[metric] for row in group)
            summary[metric] = {'count': successes, 'rate': successes/n, 'wilson_95_ci': wilson(successes, n)}
        summaries.append(summary)
    return {'dataset_role': manifest['dataset_role'], 'case_count': len(cases), 'rows': rows, 'summaries': summaries,
            'limitations': ['Missing/invalid reports count as incorrect in the admitted-case denominator.',
                            'Target plus fault class exact match; directed edges are not reversible.',
                            'No semantic grounding, human time, retrieval relevance, or live TTD inferred by this script.',
                            'A development pilot score is not an official test benchmark.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.manifest.read_text()), args.manifest.resolve().parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'dataset_role': result['dataset_role'], 'cases': result['case_count'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
