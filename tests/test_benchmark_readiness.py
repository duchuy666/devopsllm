import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.check_benchmark_readiness import assess, REQUIRED_PINS


class BenchmarkReadinessTests(unittest.TestCase):
    def fixture(self, root):
        plan = json.loads((Path(__file__).resolve().parents[1] / 'experiments/scenario-plan.json').read_text())
        for name in REQUIRED_PINS:
            p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fixture')
        (root / 'experiments/scenario-plan.json').write_text(json.dumps(plan))
        (root / 'config/experiment-protocol.yaml').write_text('status: frozen\n')
        cases = [{'candidate_id': 'FIXTURE-' + r['scenario_id'], 'scenario_id': r['scenario_id'],
                  'split': r['split'], 'execution_status': 'captured_requires_review',
                  'provenance': 'checksums_verified', 'official_admitted': True}
                 for r in plan['scenarios']]
        signature = {'decision': 'approved', 'independent_reviewer': 'human-reviewer-fixture',
                     'independent_reviewed_at': '2026-01-01T00:00:00+00:00', 'reason': 'Synthetic test only'}
        handoff = root / 'results/review-handoff'; handoff.mkdir(parents=True, exist_ok=True)
        (handoff / 'admission-review.json').write_text(json.dumps({'cases': [{**r, **signature} for r in cases]}))
        books = root / 'knowledge/runbooks'; books.mkdir(parents=True)
        hashes = []; reviews = []
        for i in range(5):
            p = books / f'RB-{i}.md'; p.write_text('Synthetic fixture ' + str(i))
            digest = hashlib.sha256(p.read_bytes()).hexdigest(); hashes.append(digest)
            reviews.append({'file': p.name, 'source_sha256': digest, **signature})
        (root / '.runtime/knowledge-index.json').write_text(json.dumps({
            'source_hashes': hashes, 'kb_version': 'fixture-kb', 'embedding_model': 'fixture-embedding'}))
        (handoff / 'runbook-review.json').write_text(json.dumps({'runbooks': reviews}))
        names = REQUIRED_PINS | {str(p.relative_to(root)) for p in books.glob('*.md')}
        freeze = {'status': 'frozen', 'pending': [], 'files_sha256': {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
            'configuration': {'model': 'fixture-model', 'embedding_model': 'fixture-embedding',
                              'kb_version': 'fixture-kb', 'observation_cutoff_policy': 'fixed fixture cutoff',
                              'missing_report_policy': 'keep denominator', 'retry_policy': 'zero'}}
        (handoff / 'freeze-candidate.json').write_text(json.dumps(freeze))
        return {'errors': [], 'cases': cases}, freeze

    def test_complete_synthetic_evidence_passes_without_cloud_or_admission_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, _ = self.fixture(root)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = assess(root, audit)
            self.assertFalse(result['blockers']); self.assertFalse(result['cloud_called'])
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_repeated_scenario_cannot_replace_missing_scenario_to_reach_200(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, _ = self.fixture(root)
            audit['cases'][-1] = copy.deepcopy(audit['cases'][0])
            result = assess(root, audit)
            self.assertIn('official_count', result['blockers'])
            self.assertIn('one_admitted_attempt_per_scenario', result['blockers'])

    def test_declared_frozen_flags_do_not_hide_modified_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, _ = self.fixture(root)
            (root / 'app/context_builder.py').write_text('changed after freeze')
            result = assess(root, audit)
            self.assertIn('source_hashes_match', result['blockers'])

    def test_legacy_capture_without_verified_provenance_is_not_official_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, _ = self.fixture(root)
            audit['cases'][0]['provenance'] = 'legacy_candidate_without_source_snapshot'
            self.assertIn('admitted_provenance', assess(root, audit)['blockers'])

    def test_approved_string_without_named_timezone_aware_review_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, _ = self.fixture(root)
            p = root / 'results/review-handoff/admission-review.json'; review = json.loads(p.read_text())
            review['cases'][0]['independent_reviewer'] = None
            review['cases'][1]['independent_reviewed_at'] = '2026-01-01T00:00:00'
            p.write_text(json.dumps(review))
            self.assertIn('independent_admission_records', assess(root, audit)['blockers'])

    def test_missing_plan_pin_and_draft_runbook_review_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, freeze = self.fixture(root)
            freeze['files_sha256'].pop('experiments/scenario-plan.json')
            p = root / 'results/review-handoff/freeze-candidate.json'; p.write_text(json.dumps(freeze))
            p = root / 'results/review-handoff/runbook-review.json'; review = json.loads(p.read_text())
            review['runbooks'][0]['decision'] = 'pending'; p.write_text(json.dumps(review))
            result = assess(root, audit)
            self.assertIn('required_sources_pinned', result['blockers'])
            self.assertIn('knowledge_independent_review', result['blockers'])

    def test_secret_or_external_paths_are_never_accepted_as_freeze_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); audit, freeze = self.fixture(root)
            freeze['files_sha256']['.env'] = 'not-read'
            freeze['files_sha256']['../outside-file'] = 'not-read'
            (root / 'results/review-handoff/freeze-candidate.json').write_text(json.dumps(freeze))
            check = next(c for c in assess(root, audit)['checks'] if c['check'] == 'source_hashes_match')
            self.assertEqual(set(check['detail']['unsafe_paths']), {'.env', '../outside-file'})


if __name__ == '__main__':
    unittest.main()
