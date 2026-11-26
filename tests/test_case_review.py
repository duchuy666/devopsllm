import json
from pathlib import Path
import tempfile
import unittest
from experiments.review_case import review,phase_statistics


class CaseReviewTests(unittest.TestCase):
    def test_preflight_failure_cannot_become_admitted_or_effect_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'ground-truth.json').write_text(json.dumps({'execution_status':'preflight_failed'}))
            result=review(root)
            self.assertFalse(result['official_admitted'])
            self.assertEqual(result['admission_status'],'requires_review')
            self.assertFalse(result['checks']['controller_all_injected'])
            self.assertEqual(result['review_status'],'structural_review_failed')

    def test_fault_window_does_not_include_recovery_or_nan_in_baseline(self):
        stats=phase_statistics([[0,'1'],[1,'NaN'],[10,'8'],[20,'9'],[21,'2']],10,20)
        self.assertEqual(stats['baseline']['count'],1)
        self.assertEqual(stats['baseline']['mean'],1)
        self.assertEqual(stats['fault']['mean'],8.5)
        self.assertEqual(stats['recovery']['mean'],2)
