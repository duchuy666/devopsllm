import copy
import unittest
from scripts.summarize_human_study import summarize


class HumanSummaryTests(unittest.TestCase):
    def fixture(self):
        plan={'tasks':[{'case_opaque_id':'a','condition':'B0_dashboard','group_id':'g'},
                       {'case_opaque_id':'b','condition':'B3_assistant','group_id':'g'}],'limitations':[]}
        rows=[]
        for task,seconds in zip(plan['tasks'],(30,60)):
            rows.append({**task,'started_at':'2026-01-01T00:00:00+00:00',
                'ended_at':'2026-01-01T00:'+('00:30' if seconds==30 else '01:00')+'+00:00',
                'start_monotonic':100,'monotonic_elapsed_seconds':seconds,'observed_seconds':seconds,
                'valid_timing':True,'final_diagnosis':{'target':'Unknown'}})
        return plan,{'consent':True,'protocol_sha256':'p','completed_tasks':rows,'active_task':None}

    def test_preserves_negative_observed_difference_and_optional_cost_assumption(self):
        plan,session=self.fixture();r=summarize(plan,'p',session,360000)
        self.assertEqual(r['mean_family_difference_seconds'],-30)
        self.assertEqual(r['labor_value_sensitivity']['gross_vnd_per_task'],-3000)
        self.assertFalse(r['ground_truth_read']);self.assertEqual(r['valid_pair_count'],1)

    def test_partial_or_mismatched_assignment_cannot_be_reported(self):
        plan,session=self.fixture()
        for mutation in ('partial','condition','protocol','no_consent'):
            bad=copy.deepcopy(session)
            if mutation=='partial':bad['completed_tasks'].pop()
            elif mutation=='condition':bad['completed_tasks'][0]['condition']='B3_assistant'
            elif mutation=='protocol':bad['protocol_sha256']='other'
            else:bad['consent']=False
            with self.assertRaises(ValueError):summarize(plan,'p',bad)

    def test_invalid_timing_is_excluded_not_imputed(self):
        plan,session=self.fixture();row=session['completed_tasks'][0]
        row.update(ended_at='2026-01-01T00:10:00+00:00',valid_timing=False,observed_seconds=None)
        result=summarize(plan,'p',session)
        self.assertEqual(result['conditions']['B0_dashboard']['invalid_timing'],1)
        self.assertIsNone(result['mean_family_difference_seconds'])
        self.assertEqual(result['valid_pair_count'],0)

    def test_tampered_seconds_and_nonfinite_cost_are_rejected(self):
        plan,session=self.fixture();session['completed_tasks'][0]['observed_seconds']=1
        with self.assertRaises(ValueError):summarize(plan,'p',session)
        plan,session=self.fixture()
        with self.assertRaises(ValueError):summarize(plan,'p',session,float('nan'))
