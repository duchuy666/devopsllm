import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.apply_admission_review import validate_review,transaction,CHECKS


class AdmissionApplicationTests(unittest.TestCase):
    def record(self):
        return {'decision':'approved','reviewer_id':'human-fixture','reviewed_at':'2026-01-01T00:00:00+00:00',
                'reason':'Synthetic fixture only','evidence_locations':[{'file':'telemetry/metrics.json'}],
                **{key:True for key in CHECKS}}

    def test_complete_record_is_accepted_without_imputing_reviewer_values(self):
        record=self.record();before=copy.deepcopy(record);validate_review(record);self.assertEqual(record,before)

    def test_pending_false_checks_missing_identity_or_naive_time_cannot_admit(self):
        for key,value in [('decision','pending'),('reviewer_id',None),('reason',''),('evidence_locations',[]),
                          ('reviewed_at','2026-01-01T00:00:00'),('target_effect_confirmed',False),
                          ('target_effect_confirmed','true'),('reviewed_at','2999-01-01T00:00:00+00:00')]:
            with self.subTest(key=key,value=value),self.assertRaises((ValueError,TypeError)):
                record=self.record();record[key]=value;validate_review(record)

    def test_successful_transaction_preserves_before_files_and_records_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'registry.json';old.write_bytes(b'original')
            new=root/'receipt.json';directory=transaction({old:b'updated',new:b'new receipt'},root)
            self.assertEqual(old.read_bytes(),b'updated');self.assertEqual(new.read_bytes(),b'new receipt')
            self.assertEqual((directory/'before-0.json').read_bytes(),b'original')
            self.assertEqual(json.loads((directory/'transaction.json').read_text())['status'],'committed')

    def test_interrupted_multi_file_update_rolls_back_all_completed_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);first=root/'registry.json';second=root/'ground.json'
            first.write_bytes(b'original registry');second.write_bytes(b'original ground')
            def interrupted(path,payload):
                if path==second:raise KeyboardInterrupt('fixture interruption')
                path.write_bytes(payload)
            with patch('scripts.apply_admission_review.atomic_write',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):
                transaction({first:b'new registry',second:b'new ground'},root)
            self.assertEqual(first.read_bytes(),b'original registry');self.assertEqual(second.read_bytes(),b'original ground')
            log=next((root/'results/admission-transactions').glob('*/transaction.json'))
            self.assertEqual(json.loads(log.read_text())['status'],'rolled_back')


if __name__=='__main__':unittest.main()
