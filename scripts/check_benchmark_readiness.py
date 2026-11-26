#!/usr/bin/env python3
"""Check offline benchmark prerequisites without admitting cases or invoking APIs."""
from collections import Counter
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.test_dataset import evaluate

REQUIRED_PINS = {'experiments/scenario-plan.json', 'config/experiment-protocol.yaml',
                 'app/context_builder.py', 'app/gemini_provider.py', 'app/report_schema.py',
                 'app/baseline.py', 'app/rag.py', 'infra/sock-shop/local-emulated.yaml',
                 '.runtime/knowledge-index.json', 'results/review-handoff/runbook-review.json'}
CONFIG_FIELDS = ('model', 'embedding_model', 'kb_version', 'observation_cutoff_policy',
                 'missing_report_policy', 'retry_policy')


def signed_review(record):
    """Check completeness of a human record, not identity authenticity."""
    if record.get('decision') != 'approved':
        return False
    if any(not isinstance(record.get(key), str) or not record[key].strip()
           for key in ('independent_reviewer', 'reason')):
        return False
    try:
        stamp = dt.datetime.fromisoformat(record.get('independent_reviewed_at') or '')
        return stamp.utcoffset() is not None and stamp <= dt.datetime.now(dt.timezone.utc)
    except (ValueError, TypeError):
        return False


def assess(root=ROOT, dataset_audit=None):
    checks = []

    def check(name, passed, detail):
        checks.append({'check': name, 'status': 'passed' if passed else 'blocked', 'detail': detail})

    def read(name, default):
        try:
            value = json.loads((root / name).read_text())
            if not isinstance(value, dict):
                raise ValueError('Expected object')
            return value
        except (OSError, ValueError):
            check('read:' + name, False, 'Missing or invalid JSON artifact')
            return default

    if dataset_audit is None:
        dataset_audit = evaluate(root)
    check('dataset_integrity', not dataset_audit['errors'], dataset_audit['errors'])
    plan = read('experiments/scenario-plan.json', {'scenarios': []})
    by_id = {row['scenario_id']: row for row in plan['scenarios']}
    admitted = [row for row in dataset_audit['cases'] if row.get('official_admitted') is True]
    identities = [row['scenario_id'] for row in admitted]
    unique = set(identities)
    check('official_count', len(admitted) == 200 and unique == set(by_id) and len(unique) == 200,
          {'admitted_attempts': len(admitted), 'unique_scenarios': len(unique), 'required': 200})
    check('one_admitted_attempt_per_scenario', len(identities) == len(unique),
          [key for key, count in Counter(identities).items() if count > 1])
    missing_provenance = [row['candidate_id'] for row in admitted
                          if row.get('provenance') != 'checksums_verified']
    check('admitted_provenance', not missing_provenance, missing_provenance)
    splits = Counter(row['split'] for row in admitted)
    check('grouped_split_counts', splits == {'reference': 120, 'validation': 40, 'test': 40}, dict(splits))
    classes = Counter(by_id.get(row['scenario_id'], {}).get('fault_class', 'unknown') for row in admitted)
    expected = {'Resource Exhaustion': 67, 'Network Delay / Packet Loss': 67, 'Pod Failure': 66}
    check('fault_class_counts', classes == expected, dict(classes))

    handoff = read('results/review-handoff/admission-review.json', {'cases': []})
    rows = handoff['cases']; review_ids = [row['candidate_id'] for row in rows]
    check('review_record_identity_unique', len(review_ids) == len(set(review_ids)), 'No duplicate candidate review records')
    reviews = {row['candidate_id']: row for row in rows}; missing = []
    for case in admitted:
        record = reviews.get(case['candidate_id'], {})
        valid = (signed_review(record) and record.get('official_admitted') is True
                 and record.get('scenario_id') == case['scenario_id'] and record.get('split') == case['split']
                 and record.get('execution_status') == case['execution_status'])
        if not valid:
            missing.append(case['candidate_id'])
    check('independent_admission_records', not missing, missing)
    try:
        protocol = yaml.safe_load((root / 'config/experiment-protocol.yaml').read_text())
    except (OSError, ValueError, yaml.YAMLError):
        protocol = {}
    check('protocol_frozen', isinstance(protocol, dict) and protocol.get('status') == 'frozen',
          'config/experiment-protocol.yaml must explicitly be frozen before official test')

    freeze = read('results/review-handoff/freeze-candidate.json', {})
    check('freeze_declared', freeze.get('status') == 'frozen', freeze.get('status', 'missing'))
    pins = freeze.get('files_sha256', {}); bad = []; unsafe = []
    if not isinstance(pins, dict):
        pins = {}
    for name, digest in pins.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or any(part.startswith('.env') for part in Path(name).parts):
            unsafe.append(name)
            continue
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            bad.append(name)
    check('source_hashes_match', bool(pins) and not bad and not unsafe, {'changed': bad, 'unsafe_paths': unsafe})
    books = sorted((root / 'knowledge/runbooks').glob('*.md'))
    required = REQUIRED_PINS | {str(p.relative_to(root)) for p in books}
    check('required_sources_pinned', required <= set(pins), sorted(required - set(pins)))
    config = freeze.get('configuration', {})
    if not isinstance(config, dict):
        config = {}
    missing_config = [key for key in CONFIG_FIELDS if not isinstance(config.get(key), str) or not config[key].strip()]
    check('frozen_configuration', not missing_config, missing_config)
    knowledge = read('.runtime/knowledge-index.json', {})
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in books]
    check('knowledge_index_matches_sources', bool(books) and knowledge.get('source_hashes') == hashes
          and knowledge.get('kb_version') == config.get('kb_version')
          and knowledge.get('embedding_model') == config.get('embedding_model'),
          'Source hashes, KB version and embedding model must match the declared freeze')
    book_review = read('results/review-handoff/runbook-review.json', {'runbooks': []})
    records = book_review.get('runbooks', []); reviewed = {row['file']: row for row in records}
    pending_books = [p.name for p, digest in zip(books, hashes)
                     if not signed_review(reviewed.get(p.name, {}))
                     or reviewed.get(p.name, {}).get('source_sha256') != digest]
    check('knowledge_independent_review', bool(books) and not pending_books
          and len(records) == len(reviewed), pending_books)
    check('freeze_has_no_pending_work', freeze.get('pending') == [], freeze.get('pending', ['missing pending list']))
    blockers = [row['check'] for row in checks if row['status'] != 'passed']
    return {'status': 'ready_for_offline_benchmark_review' if not blockers else 'not_ready',
            'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'checks': checks,
            'blockers': blockers, 'official_admitted': len(admitted), 'official_required': 200,
            'cloud_called': False, 'cluster_changed': False,
            'limitations': ['Validates recorded evidence, not the authenticity of reviewer identities.',
                           'Does not verify live cluster health, provider access, or authorize paid API calls.',
                           'Passing cannot replace independent claim/retrieval review or observed human sessions.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'results/evaluation/benchmark-readiness.json')
    args = parser.parse_args()
    result = assess()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'official_admitted', 'blockers')}, indent=2))
    raise SystemExit(0 if not result['blockers'] else 2)
