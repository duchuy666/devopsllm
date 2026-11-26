import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


class MetricRepairTests(unittest.TestCase):
    def test_expired_window_cannot_overwrite_archived_metrics(self):
        script=Path(__file__).resolve().parents[1]/'scripts/repair_pilot_metrics.py'
        provider=ModuleType('verify_telemetry')
        provider.get=lambda *args,**kwargs:{'status':'success','data':{'result':[]}}
        original_cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                case=Path('data/pilot/PILOT-expired')
                source=case/'telemetry';source.mkdir(parents=True)
                (case/'ground-truth.json').write_text(json.dumps({'status':'injected'}))
                (source/'capture.json').write_text(json.dumps({'window_start':1,'window_end':2,'quality':{}}))
                target=case/'telemetry-corrected';target.mkdir()
                (target/'metrics.json').write_text('ARCHIVED_COMPLETE_EXPORT')
                with patch.dict(sys.modules,{'verify_telemetry':provider}):
                    with self.assertRaises(SystemExit) as exit_state:runpy.run_path(str(script),run_name='__main__')
                self.assertEqual(exit_state.exception.code,1)
                self.assertEqual((target/'metrics.json').read_text(),'ARCHIVED_COMPLETE_EXPORT')
                self.assertIn('preserved',json.loads((target/'repair-error.json').read_text())['message'])
            finally:os.chdir(original_cwd)
