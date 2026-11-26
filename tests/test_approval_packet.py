import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.run_approved_comparison import main


class ApprovalPacketTests(unittest.TestCase):
    def test_prompt_or_schema_change_stops_before_cloud_or_execution_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet=Path(tmp);(packet/'request-manifest.json').write_text(json.dumps({'files_sha256':{},
                'prompt_fingerprint':{'prompt_version':'changed','prompt_task_sha256':'changed','report_schema_sha256':'changed'}}))
            with patch('sys.argv',['run','--approved-packet',tmp]),patch('scripts.run_approved_comparison.diagnose') as call:
                with self.assertRaisesRegex(RuntimeError,'prompt/schema changed'):main()
                call.assert_not_called()
            self.assertFalse((packet/'execution.json').exists())
    def test_changed_reviewed_payload_stops_before_cloud_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet=Path(tmp)
            (packet/'source-context.json').write_text('{"changed":true}')
            (packet/'request-manifest.json').write_text(json.dumps({
                'files_sha256':{'source-context.json':'a-reviewed-hash-that-no-longer-matches'}}))
            with patch('sys.argv',['run','--approved-packet',tmp]), patch('scripts.run_approved_comparison.diagnose') as call:
                with self.assertRaisesRegex(RuntimeError,'Reviewed packet changed'):main()
                call.assert_not_called()
            self.assertFalse((packet/'execution.json').exists())
