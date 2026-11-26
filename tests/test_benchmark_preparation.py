import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from tests import test_prospective_collection as fixtures
from app.observation_window import crop
from scripts.prepare_prospective_benchmark import verify_observation


class BenchmarkPreparationTests(unittest.TestCase):
    def test_modified_observation_or_raw_is_rejected_before_context_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=fixtures.ProspectiveCollectionTests().raw(root);raw.rename(root/'telemetry');raw=root/'telemetry'
            p=raw/'capture.json';capture=json.loads(p.read_text());capture.update(window_start=-40,window_end=40);p.write_text(json.dumps(capture))
            ground={'injection_confirmed_at':dt.datetime.fromtimestamp(0,dt.timezone.utc).isoformat()}
            crop(raw,root/'observation/telemetry',-30,30);verify_observation(root,ground)
            observation=root/'observation/telemetry/metrics.json';saved=observation.read_bytes()
            observation.write_text('{}')
            with self.assertRaisesRegex(ValueError,'payload changed'):verify_observation(root,ground)
            observation.write_bytes(saved)
            p=raw/'metrics.json';metrics=json.loads(p.read_text());metrics['cpu']['query']='modified';p.write_text(json.dumps(metrics))
            with self.assertRaisesRegex(ValueError,'raw hash mismatch'):verify_observation(root,ground)
