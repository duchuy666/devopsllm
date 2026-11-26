import json
from pathlib import Path
import tempfile
import unittest
from scripts.build_thesis_docx import official_facts,grounding_facts,human_facts,pending_items,final_label,OFFICIAL


class ThesisBuilderTests(unittest.TestCase):
    def test_missing_results_are_reported_as_pending_never_as_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertFalse(official_facts(root)['available'])
            self.assertFalse(grounding_facts(root)['available']);self.assertFalse(human_facts(root)['available'])

    def test_development_file_cannot_masquerade_as_official_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/OFFICIAL).parent.mkdir(parents=True)
            (root/OFFICIAL).write_text(json.dumps({'dataset_role':'development_pilot','case_count':2,'rows':[],'summaries':[]}))
            self.assertFalse(official_facts(root)['available'])

    def test_claim_label_needs_agreement_or_adjudication(self):
        self.assertIsNone(final_label({'reviewer_1':'supported','reviewer_2':'unsupported'}))
        self.assertIsNone(final_label({'reviewer_1':'supported','reviewer_2':None}))
        self.assertEqual(final_label({'reviewer_1':'supported','reviewer_2':'supported'}),'supported')
        self.assertEqual(final_label({'reviewer_1':'supported','reviewer_2':'unsupported','adjudication':{'label':'unsupported'}}),'unsupported')

    def test_pending_list_names_every_missing_source(self):
        facts={'dataset':{'complete':False,'funnel':{'admitted':3}},'official':{'available':False},
               'grounding':{'available':False,'reason':'x'},'human':{'available':False},'live':{'available':False}}
        self.assertEqual(len(pending_items(facts)),6)


if __name__=='__main__':unittest.main()
