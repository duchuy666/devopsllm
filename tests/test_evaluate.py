import json
from pathlib import Path
import tempfile
import unittest
from experiments.evaluate import evaluate, score, wilson


class EvaluationTests(unittest.TestCase):
    def test_target_and_fault_both_required_and_edges_directed(self):
        expected={'target':['front-end','catalogue'],'fault_type':'Network Delay / Packet Loss'}
        hypotheses=[{'service':'catalogue -> front-end','fault_type':expected['fault_type']},
                    {'service':'front-end -> catalogue','fault_type':'Resource Exhaustion'}]
        self.assertEqual(score(expected,hypotheses),{'top1_correct':False,'top3_correct':False})
        hypotheses.append({'service':'front-end -> catalogue','fault_type':expected['fault_type']})
        self.assertEqual(score(expected,hypotheses),{'top1_correct':False,'top3_correct':True})

    def test_failed_calls_remain_in_denominator_and_duplicate_cases_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base/'invalid.json').write_text(json.dumps({'generated':{'report':{}}}))
            cases=[{'case_id':name,'admission_status':'admitted','context_id':'CTX-test',
                    'expected':{'target':'payment','fault_type':'Resource Exhaustion'},'reports':reports}
                   for name,reports in [('one',{}),('two',{'B3':'invalid.json'})]]
            manifest={'dataset_role':'development_pilot','modes':['B3'],'cases':cases}
            result=evaluate(manifest,base)
            summary=next(s for s in result['summaries'] if s['fault_class']=='all')
            self.assertEqual(summary['denominator'],2)
            self.assertEqual(summary['missing_or_invalid_reports'],2)
            self.assertEqual(summary['top1_correct']['rate'],0)
            manifest['cases'].append(cases[0])
            with self.assertRaises(ValueError):evaluate(manifest,base)

    def test_small_sample_uncertainty(self):
        low,high=wilson(1,1)
        self.assertAlmostEqual(low,0.2065493144)
        self.assertAlmostEqual(high,1)
        self.assertIsNone(wilson(0,0))

    def test_development_review_does_not_admit_an_official_test_case(self):
        manifest={'dataset_role':'development_pilot','modes':['B3'],'cases':[
            {'case_id':'dev','context_id':'CTX-example','split':'test',
             'admission_status':'reviewed_for_development_scoring',
             'expected':{'target':'shipping','fault_type':'Resource Exhaustion'},'reports':{}}]}
        self.assertEqual(evaluate(manifest,Path('.'))['case_count'],1)
        manifest['dataset_role']='official_test'
        with self.assertRaises(ValueError):evaluate(manifest,Path('.'))
