import datetime as dt
import unittest
from app.stability_timing import audit_timing


class StabilityTimingTests(unittest.TestCase):
    def samples(self,seconds):
        start=dt.datetime(2026,11,23,tzinfo=dt.timezone.utc)
        return [{'at':(start+dt.timedelta(seconds=n)).isoformat()} for n in seconds]

    def test_regular_sampling_passes(self):
        self.assertEqual(audit_timing(self.samples(range(0,601,30)),602,30)['status'],'passed')

    def test_sleep_gap_cannot_pass_even_with_600_active_seconds(self):
        result=audit_timing(self.samples([0,30,60,3660,3690]),600,30)
        self.assertEqual(result['status'],'failed')
        self.assertIn('utc_sampling_gap_above_bound',result['issues'])
        self.assertIn('utc_active_elapsed_disagreement',result['issues'])

    def test_clock_reversal_and_missing_samples_fail(self):
        self.assertIn('utc_clock_moved_backwards',audit_timing(self.samples([0,30,20]),30,30)['issues'])
        self.assertEqual(audit_timing([],600,30)['status'],'failed')
