import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.compile_intent_delivery import compile_intent_delivery
from scripts.delivery_review import evaluate_delivery_review
from tests.review_fixture import mechanical_review
ROOT = Path(__file__).resolve().parents[1]

class BoundReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.capture = self.base / 'captures'; self.capture.mkdir()
        self.task = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        self.draft = compile_intent_delivery(self.task, self.base / 'draft', draft=True)
        self.artifacts = {'prompt_packages': json.dumps(self.draft['prompts'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))}
        self.review = mechanical_review(ROOT, self.task, self.artifacts, self.capture)
    def tearDown(self): self.temp.cleanup()
    def check_review(self, review, artifacts=None, task=None, session='mechanical-test-session'):
        return evaluate_delivery_review(ROOT, task or self.task, artifacts or self.artifacts, review, capture_root=self.capture, session_id=session)
    def test_current_evidence_can_finalize_without_quality_or_generation_claim(self):
        checked = self.check_review(self.review)
        self.assertTrue(checked['delivery_ready'], checked)
        self.assertFalse(checked['creative_quality_verified']); self.assertFalse(checked['media_quality_verified']); self.assertFalse(checked['generation_authorized'])
        final = compile_intent_delivery(self.task, self.base / 'final', review=self.review, capture_root=self.capture, session_id='mechanical-test-session')
        self.assertEqual(final['delivery']['delivery_readiness'], 'REVIEW_EVIDENCE_READY', final['delivery']['review_evidence'])
        self.assertTrue((self.base / 'final/13_Final_Prompt.md').is_file())
        self.assertEqual(set(final['delivery']['artifacts']), {p.name for p in (self.base / 'final').iterdir() if p.is_file()})
        self.assertFalse(final['delivery']['claims']['creative_quality_verified'])
    def test_changed_task_or_output_rejected(self):
        changed = copy.deepcopy(self.task); changed['goal'] += ' changed'
        self.assertFalse(self.check_review(self.review, task=changed)['delivery_ready'])
        self.assertFalse(self.check_review(self.review, artifacts={'prompt_packages': 'changed'})['delivery_ready'])
    def test_partial_capture_and_wrong_session_rejected(self):
        self.assertFalse(self.check_review(self.review, session='different')['delivery_ready'])
        path = self.review['read_receipt']['reads'][0]['capture_path']
        (self.capture / path).write_text('partial', encoding='utf-8')
        self.assertFalse(self.check_review(self.review)['delivery_ready'])
    def test_generic_rationale_and_fake_output_mapping_rejected(self):
        record = copy.deepcopy(self.review); record['decisions'][0]['rationale'] = '已思考'
        self.assertFalse(self.check_review(record)['delivery_ready'])
        record = copy.deepcopy(self.review); record['decisions'][0]['applied_to'][0]['text'] = 'absent from real output'
        self.assertFalse(self.check_review(record)['delivery_ready'])
    def test_missing_domain_or_dismissed_camera_rejected(self):
        record = copy.deepcopy(self.review); record['consideration'].pop()
        self.assertFalse(self.check_review(record)['delivery_ready'])
        record = copy.deepcopy(self.review)
        for row in record['consideration']:
            if row['domain'] == 'camera_space': row['status'] = 'not_applicable'
        self.assertFalse(self.check_review(record)['delivery_ready'])
    def test_missing_requirement_and_invented_source_rejected(self):
        record = copy.deepcopy(self.review); record['decisions'].pop()
        self.assertFalse(self.check_review(record)['delivery_ready'])
        record = copy.deepcopy(self.review); record['decisions'][0]['source_evidence'][0]['quote'] = 'invented quote'
        self.assertFalse(self.check_review(record)['delivery_ready'])
    def test_unreviewed_rerun_archives_previous_final(self):
        out = self.base / 'reuse'
        compile_intent_delivery(self.task, out, review=self.review, capture_root=self.capture, session_id='mechanical-test-session')
        self.assertTrue((out / '13_Final_Prompt.md').is_file())
        compile_intent_delivery(self.task, out, draft=True)
        self.assertFalse((out / '13_Final_Prompt.md').exists())
        self.assertTrue((out / '13_Previous_Final_Prompt.unverified.md').exists())

if __name__ == '__main__': unittest.main()
