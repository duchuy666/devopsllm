import unittest
from tests.test_admission_batch import AdmissionBatchTests,approved
from scripts.recapture_rejected import eligibility


class RecaptureEligibilityTests(AdmissionBatchTests):
    def test_only_fully_documented_rejection_is_eligible(self):
        rejected={'decision':'rejected','reviewer_id':'human-fixture','reviewed_at':'2026-01-01T00:00:00+00:00','reason':'No target effect'}
        self.case('CANDIDATE-C1','S0001',rejected)
        row,rejections=eligibility(self.root,'S0001')
        self.assertEqual(rejections[0]['reason'],'No target effect')
        self.case('CANDIDATE-C2','S0002',{'decision':'rejected'})
        with self.assertRaises(ValueError):eligibility(self.root,'S0002')

    def test_pending_approved_admitted_or_uncaptured_cannot_be_recaptured(self):
        self.case('CANDIDATE-C1','S0001');self.case('CANDIDATE-C2','S0002',approved())
        self.case('CANDIDATE-C3','S0003',admission='admitted')
        for scenario in ('S0001','S0002','S0003','S0004','S9999'):
            with self.subTest(scenario=scenario),self.assertRaises(ValueError):eligibility(self.root,scenario)

    def test_rejected_then_pending_replicate_blocks_another_recapture(self):
        rejected={'decision':'rejected','reviewer_id':'h','reviewed_at':'2026-01-01T00:00:00+00:00','reason':'r'}
        self.case('CANDIDATE-C1','S0001',rejected);self.case('CANDIDATE-C2','S0001')
        with self.assertRaises(ValueError):eligibility(self.root,'S0001')


if __name__=='__main__':unittest.main()
