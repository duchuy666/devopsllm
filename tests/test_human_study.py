import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from app.human_study import timing,study_complete,hidden_test_contexts


class HumanStudyTests(unittest.TestCase):
    def fixture(self,root):
        plan={'study_id':'fixture','tasks':[{'case_opaque_id':'H-a','condition':'B0_dashboard'},
                                           {'case_opaque_id':'H-b','condition':'B3_assistant'}]}
        p=root/'experiments/human-study-plan.json';p.parent.mkdir();p.write_text(json.dumps(plan))
        session={'consent':True,'protocol_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                 'completed_tasks':[{'case_opaque_id':t['case_opaque_id'],'condition':t['condition'],
                                     'ended_at':'2026-01-01T00:01:00+00:00','final_diagnosis':{'target':'fixture'}} for t in plan['tasks']]}
        path=root/'results/human-study/fixture/person/session.json';path.parent.mkdir(parents=True)
        return path,session

    def test_consistent_observed_wall_and_active_time_is_measured(self):
        result=timing('2026-01-01T00:00:00+00:00','2026-01-01T00:01:00+00:00',100,160)
        self.assertEqual(result['observed_seconds'],60);self.assertTrue(result['valid_timing'])

    def test_suspend_or_clock_reversal_does_not_impute_human_seconds(self):
        for end,mono in [('2026-01-01T00:10:00+00:00',160),('2025-12-31T23:59:00+00:00',160)]:
            result=timing('2026-01-01T00:00:00+00:00',end,100,mono)
            self.assertFalse(result['valid_timing']);self.assertIsNone(result['observed_seconds'])

    def test_absent_or_partial_sessions_do_not_unlock_test_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,session=self.fixture(root)
            self.assertFalse(study_complete(root))
            session['completed_tasks'].pop();path.write_text(json.dumps(session))
            self.assertFalse(study_complete(root))

    def test_all_tasks_with_consent_protocol_and_conditions_unlock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,session=self.fixture(root);path.write_text(json.dumps(session))
            self.assertTrue(study_complete(root))
            session['consent']=False;path.write_text(json.dumps(session));self.assertFalse(study_complete(root))
            session['consent']=True;session['protocol_sha256']='changed';path.write_text(json.dumps(session));self.assertFalse(study_complete(root))

    def test_test_reports_stay_hidden_before_session_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,session=self.fixture(root)
            manifest=root/'results/prospective-benchmark/cohort/test/manifest.json';manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'cases':[{'context_id':'CTX-test'}]}))
            self.assertEqual(hidden_test_contexts(root),{'CTX-test'})
            path.write_text(json.dumps(session));self.assertEqual(hidden_test_contexts(root),set())


if __name__=='__main__':unittest.main()
