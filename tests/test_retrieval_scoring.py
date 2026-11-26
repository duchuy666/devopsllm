import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from scripts.score_retrieval import metrics,evaluate


class RetrievalScoringTests(unittest.TestCase):
    def test_rank_and_recall_use_human_relevance_not_cosine(self):
        r=metrics(['RB-a','RB-c'],['RB-x','RB-c','RB-y'])
        self.assertEqual(r['recall_at_3'],.5);self.assertEqual(r['reciprocal_rank_at_3'],.5)

    def test_missing_hits_count_zero_and_empty_relevance_is_undefined(self):
        self.assertEqual(metrics(['RB-a'],[])['recall_at_3'],0)
        self.assertIsNone(metrics([],['RB-a'])['recall_at_3'])
        with self.assertRaises(ValueError):metrics(['RB-a'],['RB-a','RB-a'])

    def fixture(self,root):
        books=root/'knowledge/runbooks';books.mkdir(parents=True);(books/'RB-a.md').write_text('fixture')
        folder=root/'results/review-handoff/prospective-review';folder.mkdir(parents=True)
        record={'reviewer_id':'fixture person','reviewed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                'decision':'approved','target_effect_confirmed':True,'recovery_confirmed':True,
                'telemetry_relevant':True,'near_duplicate_review':True,'reason':'fixture','evidence_locations':['fixture'],
                'runbook_relevance_reviewed':True,'relevant_runbook_ids':['RB-a']}
        packet={'candidate_id':'case','independent_review':record}
        file=folder/'case.json';file.write_text(json.dumps(packet))
        manifest={'dataset_role':'official_test','cases':[{'case_id':'case','context_id':'CTX-fixture',
                  'admission_status':'admitted','reports':{'B2':'absent-B2','B3':'absent-B3'}}]}
        return manifest,file,packet

    def test_missing_reports_stay_in_labeled_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest,_,_=self.fixture(root);r=evaluate(manifest,root,root)
            self.assertEqual(r['summaries']['B2']['scored_relevance_cases'],1)
            self.assertEqual(r['summaries']['B2']['mrr_at_3'],0)
            self.assertEqual(r['summaries']['B2']['missing_or_invalid_retrieval'],1)

    def test_pending_relevance_or_admission_does_not_produce_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest,file,packet=self.fixture(root)
            packet['independent_review']['runbook_relevance_reviewed']=False;file.write_text(json.dumps(packet))
            r=evaluate(manifest,root,root);self.assertIsNone(r['summaries']['B3']['mrr_at_3'])
            packet['independent_review']['runbook_relevance_reviewed']=True;file.write_text(json.dumps(packet))
            manifest['cases'][0]['admission_status']='requires_review'
            self.assertEqual(evaluate(manifest,root,root)['summaries']['B3']['pending_review_or_admission'],1)
