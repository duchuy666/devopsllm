import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.admission_progress import progress
from scripts.apply_admission_batch import run
from scripts.apply_admission_review import CHECKS


def approved():
    return {'decision':'approved','reviewer_id':'human-fixture','reviewed_at':'2026-01-01T00:00:00+00:00',
            'reason':'Synthetic fixture only','evidence_locations':[{'file':'telemetry/metrics.json'}],
            **{key:True for key in CHECKS}}


class AdmissionBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'experiments').mkdir()
        plan=[{'scenario_id':f'S{i:04d}','split':'reference','variant':'cpu'} for i in range(1,201)]
        (self.root/'experiments/scenario-plan.json').write_text(json.dumps({'scenarios':plan}))
        self.attempts=[]

    def tearDown(self):self.tmp.cleanup()

    def case(self,name,scenario,review=None,role='prospective_candidate',status='captured_requires_review',admission='requires_review'):
        folder=self.root/'data/candidates'/name;folder.mkdir(parents=True)
        (folder/'ground-truth.json').write_text(json.dumps({'dataset_role':role,'execution_status':status,
            'admission_status':admission,'scenario':{'scenario_id':scenario,'split':'reference','variant':'cpu'}}))
        record=review or {'decision':'pending'}
        (folder/'review-packet.json').write_text(json.dumps({'candidate_id':name,'independent_review':record}))
        self.attempts.append({'candidate_id':name,'scenario_id':scenario})
        (self.root/'experiments/candidate-registry.json').write_text(json.dumps({'attempts':self.attempts}))

    def test_funnel_counts_scenarios_once_and_never_counts_unreviewed_or_development(self):
        self.case('CANDIDATE-C1','S0001',admission='admitted')
        self.case('CANDIDATE-C2','S0002',approved())
        incomplete=approved();incomplete['reason']=''
        self.case('CANDIDATE-C3','S0003',incomplete)
        self.case('CANDIDATE-C4','S0004')
        self.case('CANDIDATE-C5','S0005',{'decision':'rejected'})
        self.case('CANDIDATE-C6','S0006',role='development_candidate',admission='admitted')
        self.case('CANDIDATE-C7','S0001')  # replicate of an admitted scenario
        result=progress(self.root);counts=result['counts']
        self.assertEqual(result['admitted'],1);self.assertEqual(result['remaining_to_target'],199)
        self.assertEqual(counts['approved_ready_to_apply'],1);self.assertEqual(counts['approved_record_incomplete'],1)
        self.assertEqual(counts['pending_review'],1);self.assertEqual(counts['rejected_requires_new_attempt'],1)
        self.assertEqual(counts['not_captured'],195);self.assertEqual(sum(counts.values()),200)

    def test_preview_writes_nothing_admitted_and_refusals_do_not_block_others(self):
        self.case('CANDIDATE-C1','S0001',approved());self.case('CANDIDATE-C2','S0002',approved());self.case('CANDIDATE-C3','S0003')
        def fake(candidate,packet,root):
            if candidate.name=='CANDIDATE-C2':raise ValueError('Raw telemetry changed after observation export')
            return {root/'x.json':b'{}'}
        with patch('scripts.apply_admission_batch.propose',side_effect=fake),\
             patch('scripts.apply_admission_batch.transaction') as tx:
            summary=run(self.root,apply=False)
        tx.assert_not_called()
        self.assertEqual(summary['would_admit'],1);self.assertEqual(summary['refused'],1)
        self.assertEqual(summary['admitted_after'],0);self.assertEqual(summary['remaining_to_target'],199)
        self.assertFalse((self.root/'results/admission-batches').exists())
        # Reviewer packets are exported without overwriting, so the UI has a file to fill in.
        self.assertTrue((self.root/'results/review-handoff/prospective-review/CANDIDATE-C3.json').exists())

    def test_only_one_admission_per_scenario_even_with_two_approved_replicates(self):
        self.case('CANDIDATE-C1','S0001',approved());self.case('CANDIDATE-C2','S0001',approved())
        with patch('scripts.apply_admission_batch.propose',return_value={}) as fake,\
             patch('scripts.apply_admission_batch.transaction',return_value=self.root/'tx'):
            summary=run(self.root,apply=True)
        self.assertEqual(fake.call_count,1);self.assertEqual(len(summary['results']),1)
        self.assertTrue((self.root/summary['receipt']).exists())


if __name__=='__main__':unittest.main()
