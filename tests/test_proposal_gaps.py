import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from app.case_memory import eligible
from scripts.auto_diagnose import new_incidents,ttd_record
from scripts.build_grafana_dashboard import dashboard
from tests.test_admission_batch import AdmissionBatchTests,approved
from scripts.export_dataset_labels import export


class CaseMemoryLeakageTests(unittest.TestCase):
    def ground(self,split='reference',admission='admitted',role='prospective_candidate'):
        return {'admission_status':admission,'dataset_role':role,'scenario':{'split':split}}

    def test_only_admitted_reference_cases_are_eligible(self):
        eligible(self.ground())
        for bad in (self.ground(split='test'),self.ground(split='validation'),self.ground(admission='requires_review'),
                    self.ground(role='development_candidate')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):eligible(bad)


class LiveTTDTests(unittest.TestCase):
    def test_only_new_completed_incidents_are_diagnosed_once(self):
        start=dt.datetime(2026,11,25,12,tzinfo=dt.timezone.utc)
        listing=[{'id':'old','status':'captured','received_at':'2026-11-25T11:59:00+00:00'},
                 {'id':'queued','status':'collecting','received_at':'2026-11-25T12:01:00+00:00'},
                 {'id':'done','status':'captured','received_at':'2026-11-25T12:02:00+00:00'},
                 {'id':'new','status':'partial','received_at':'2026-11-25T12:03:00+00:00'}]
        self.assertEqual([i['id'] for i in new_incidents(listing,start,{'done'})],['new'])

    def test_ttd_counts_from_alert_receipt_and_failed_call_has_no_ttd(self):
        incident={'id':'INC-1','received_at':'2026-11-25T12:00:00+00:00'};manifest={'context_ready_at':'2026-11-25T12:00:30+00:00'}
        ctx=dt.datetime(2026,11,25,12,0,31,tzinfo=dt.timezone.utc);report=dt.datetime(2026,11,25,12,0,40,tzinfo=dt.timezone.utc)
        record=ttd_record(incident,manifest,ctx,report,{'analysis_latency_seconds':9.0,'context_id':'CTX-1'},'B3')
        self.assertEqual(record['ttd_seconds'],40.0);self.assertEqual(record['components_seconds']['alert_to_capture'],30.0)
        failed=ttd_record(incident,manifest,ctx,None,None,'B3','RuntimeError: x')
        self.assertIsNone(failed['ttd_seconds']);self.assertEqual(failed['status'],'failed')


class DashboardTests(unittest.TestCase):
    def test_dashboard_has_unique_panels_and_three_telemetry_sources(self):
        board=dashboard();ids=[p['id'] for p in board['panels']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue({'prometheus','loki'}<={p.get('datasource',{}).get('uid') for p in board['panels']})


class LabelExportTests(AdmissionBatchTests):
    def test_only_admitted_cases_exported_and_runbook_label_needs_explicit_review(self):
        record=approved();record.update(relevant_runbook_ids=['RB-CPU-001'],runbook_relevance_reviewed=False)
        self.case('CANDIDATE-A','S0001',record,admission='admitted');self.case('CANDIDATE-B','S0002',approved())
        for name in ('CANDIDATE-A','CANDIDATE-B'):
            path=self.root/'data/candidates'/name/'ground-truth.json';g=json.loads(path.read_text())
            g['scenario'].update(group_id='G1',fault_class='Resource Exhaustion',target='payment');path.write_text(json.dumps(g))
        data=export(self.root)
        self.assertEqual(data['case_count'],1);case=data['cases'][0]
        self.assertIsNone(case['runbook_id']);self.assertEqual(case['runbook_relevance_status'],'pending_reviewer_label')
        self.assertEqual(case['expected_evidence'],[{'file':'telemetry/metrics.json'}])


if __name__=='__main__':unittest.main()
