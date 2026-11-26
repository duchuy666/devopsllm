import copy
import json
from pathlib import Path
import unittest
from experiments.audit_plan import audit


class PlanTests(unittest.TestCase):
    def test_traffic_changes_do_not_hide_family_leakage(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'experiments/scenario-plan.json').read_text())
        self.assertFalse(audit(plan)['errors'])
        changed=copy.deepcopy(plan)
        first=changed['scenarios'][0]
        other=next(r for r in changed['scenarios'] if r['split']=='test' and r['fault_class']==first['fault_class'])
        other.update(variant=first['variant'],target=first['target'],traffic_profile='a-different-profile')
        self.assertGreater(audit(changed)['risk_count'],0)
