#!/usr/bin/env python3
"""Prepare offline review units; never assign human labels or invoke a model."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ['supported', 'partially_supported', 'unsupported', 'contradicted', 'unverifiable']


def prepare(source, output):
    if output.exists():
        raise ValueError('Refuse to overwrite an existing review packet')
    reports = sorted(source.glob('*/B*/result.json'))
    if not reports:
        raise ValueError('No persisted reports found')
    staged = []
    for path in reports:
        original = json.loads(path.read_text())
        context = json.loads(path.with_name('context.json').read_text())
        report = original['generated']['report']
        if context['incident_id'] != report['incident_id']:
            raise ValueError('Report/context identity mismatch: ' + str(path))
        opaque = 'REVIEW-' + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        units = []
        for rank, hypothesis in enumerate(report['hypotheses'], 1):
            for field in ('root_cause', 'rationale'):
                units.append({'unit_id': f'H{rank}-{field}', 'text': hypothesis[field],
                              'cited_evidence_ids': hypothesis['evidence_ids']})
        for index, action in enumerate(report['recommended_actions'], 1):
            units.append({'unit_id': f'A{index}', 'text': action, 'cited_evidence_ids': []})
        for unit in units:
            unit.update(claims_to_segment=[], reviewer_1=None, reviewer_2=None,
                        adjudication=None)
        document = {'review_id': opaque, 'status': 'awaiting_two_independent_reviewers',
                    'allowed_labels': LABELS, 'units': units,
                    'observed_context': context,
                    'instructions': [
                        'Split each unit into factual claims before scoring; a unit is not a claim count.',
                        'Resolve cited evidence against original raw telemetry; existence of an ID is not support.',
                        'For actions, assess the factual premise separately from the recommendation.',
                        'Record reviewer identity, claim label, reason and raw source location independently.',
                        'Do not infer labels from diagnostic correctness; keep disagreement until adjudication.'],
                    'limitations': 'Mode label omitted, but modalities remain visible. This is not a fully blinded study.'}
        staged.append((opaque, document, path, original['mode'], len(units)))
    if len({row[0] for row in staged}) != len(staged):
        raise ValueError('Review ID collision; source reports must be distinct')
    output.mkdir(parents=True)
    mapping = []
    for opaque, document, path, mode, count in sorted(staged):
        (output / (opaque + '.json')).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
        mapping.append({'review_id': opaque, 'source_report': str(path.resolve()),
                        'mode': mode, 'unit_count': count,
                        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {'status': 'prepared_no_human_labels', 'report_count': len(mapping),
                'unit_count': sum(row['unit_count'] for row in mapping),
                'human_claim_count': None, 'grounding_score': None,
                'reviewer_mapping_do_not_distribute_with_forms': mapping,
                'generation_called': False}
    (output / 'coordinator-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {key: manifest[key] for key in ('status', 'report_count', 'unit_count', 'human_claim_count')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'results/diagnoses')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))
