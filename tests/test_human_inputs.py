import json
from pathlib import Path
import tempfile
import unittest
from app.human_study import snapshot_inputs,read_inputs


class HumanInputTests(unittest.TestCase):
    def test_task_keeps_its_exact_material_when_upstream_report_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);context=root/'context';report=root/'report';context.write_text('{"incident_id":"observed"}');report.write_text('{"report":"original"}')
            snapshot=root/'snapshot';hashes=snapshot_inputs(snapshot,context,report)
            report.write_text('{"report":"changed"}')
            self.assertEqual(read_inputs(snapshot,hashes)[1]['report'],'original')
            with self.assertRaisesRegex(ValueError,'replace'):snapshot_inputs(snapshot,context,report)

    def test_tampered_task_snapshot_is_not_silently_displayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);context=root/'context';report=root/'report';context.write_text('{}');report.write_text('{}')
            snapshot=root/'snapshot';hashes=snapshot_inputs(snapshot,context,report)
            (snapshot/'context.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'changed'):read_inputs(snapshot,hashes)
