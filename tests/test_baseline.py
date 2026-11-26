import copy
import unittest
from app.baseline import diagnose_rules


class BaselineTests(unittest.TestCase):
    def test_resource_threshold_requires_matching_observed_limit(self):
        context={'incident_id':'CTX-fixture','metrics':[
            {'metric':'cpu','pod':'payment-8549d96754-784qt','max':.19,'evidence_id':'E-M001'},
            {'metric':'cpu_limit','pod':'payment-8549d96754-784qt','max':.2,'evidence_id':'E-M002'}]}
        report=diagnose_rules(context);self.assertEqual(report['hypotheses'][0]['service'],'payment')
        self.assertEqual(report['hypotheses'][0]['fault_type'],'Resource Exhaustion')
        context['metrics'][1]['pod']='other'
        self.assertEqual(diagnose_rules(context)['status'],'insufficient_evidence')

    def test_latency_does_not_invent_network_root_cause_or_read_labels(self):
        context={'incident_id':'CTX-fixture','metrics':[{'metric':'latency_mean','service':'front-end',
            'route':'/cart','max':.6,'evidence_id':'E-M001'}]}
        before=copy.deepcopy(context);report=diagnose_rules(context)
        context['ground_truth']={'target':'carts','fault':'network-loss'}
        self.assertEqual(report,diagnose_rules(context));self.assertEqual(report['hypotheses'][0]['fault_type'],'Unknown')
        self.assertEqual(before['metrics'],context['metrics'])
