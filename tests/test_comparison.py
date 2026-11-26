import unittest
from app.diagnosis import observed_context


class ComparisonTests(unittest.TestCase):
    def test_b1_b2_share_identical_log_evidence_without_modifying_source(self):
        source={'incident_id':'CTX-example','metrics':[{'evidence_id':'E-M001'}],
                'logs':[{'evidence_id':'E-L001','template':'error'}],'traces':[{'evidence_id':'E-T001'}]}
        a=observed_context(source,'B1');b=observed_context(source,'B2');c=observed_context(source,'B3')
        self.assertEqual(a,b)
        self.assertEqual(a['logs'],c['logs'])
        self.assertEqual(a['metrics'],[])
        self.assertEqual(a['traces'],[])
        self.assertEqual(len(source['metrics']),1)
        a['logs'][0]['template']='changed'
        self.assertEqual(source['logs'][0]['template'],'error')
