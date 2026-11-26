import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_reference_calibration import validate_selection
from scripts.run_scenario import save_recipe


class CalibrationBoundaryTests(unittest.TestCase):
    def test_selection_rejects_duplicates_heldout_and_pod_before_other_cases(self):
        rows=[{'scenario_id':key,'split':split,'variant':variant} for key,split,variant in
              [('M','reference','memory'),('P','reference','pod-failure'),('T','test','cpu')]]
        plan={'scenarios':rows}
        validate_selection(['M','P'],plan)
        for ids in ([],['M','M'],['T'],['unknown'],['P','M'],['M','P','T','x','y']):
            with self.subTest(ids=ids),self.assertRaises(ValueError):validate_selection(ids,plan)

    def test_recipe_copies_allowlisted_inputs_without_env_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir()
            (root/'scripts/run_scenario.py').write_text('fixture source')
            (root/'.env').write_text('GEMINI_API_KEY=secret-fixture')
            (root/'credentials.json').write_text('private-fixture')
            plan=root/'plan.json';plan.write_text('{"scenarios":[]}')
            baseline=root/'baseline';baseline.mkdir()
            for name in ('result.json','samples.json','traffic.json'):(baseline/name).write_text('{}')
            out=root/'candidate';out.mkdir()
            with patch('scripts.run_scenario.ROOT',root):save_recipe(out,plan,baseline/'result.json')
            record=json.loads((out/'provenance.json').read_text())
            self.assertIn('scenario-plan.json',record['files_sha256'])
            self.assertIn('baseline/result.json',record['files_sha256'])
            combined=''.join(p.read_text() for p in out.rglob('*') if p.is_file())
            self.assertNotIn('secret-fixture',combined)
            self.assertNotIn('private-fixture',combined)
