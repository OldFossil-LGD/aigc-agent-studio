"""Mechanical text-endpoint tests; no artistic approval or model reading claim."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.delivery_review import evaluate_delivery_review
from tests.review_fixture import mechanical_review
ROOT = Path(__file__).resolve().parents[1]

class TextDeliveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.capture = self.base / 'captures'; self.capture.mkdir()
        self.task = {'goal': 'Review only the physical reachability in this storyboard', 'profile': 'rework', 'requirements': [{'id': 'user_reachability', 'text': 'A sealed glass wall separates the people; the hand cannot pass through it.'}]}
        self.artifacts = {'review.md': 'The sealed glass wall blocks physical reachability. This is a text-only review; media contact is unverified.'}
        self.review = mechanical_review(ROOT, self.task, self.artifacts, self.capture)
    def tearDown(self): self.temp.cleanup()
    def check(self, review):
        return evaluate_delivery_review(ROOT, self.task, self.artifacts, review, capture_root=self.capture, session_id='mechanical-test-session')
    def test_text_task_accepts_current_evidence_without_compiling_media(self):
        result = self.check(self.review)
        self.assertTrue(result['delivery_ready'], result)
        self.assertFalse(result['creative_quality_verified'])
        self.assertFalse(result['generation_authorized'])
    def test_text_task_cannot_omit_its_user_requirement(self):
        review = copy.deepcopy(self.review)
        review['decisions'] = [d for d in review['decisions'] if 'user_reachability' not in d['requirement_ids']]
        self.assertFalse(self.check(review)['delivery_ready'])
    def test_current_unresolved_facts_cannot_be_hidden_by_valid_source_receipts(self):
        review = copy.deepcopy(self.review)
        review['unresolved'] = ['Required current-task material is missing']
        self.assertFalse(self.check(review)['delivery_ready'])
    def test_missing_unresolved_declaration_is_not_a_review(self):
        review = copy.deepcopy(self.review)
        review.pop('unresolved', None)
        self.assertFalse(self.check(review)['delivery_ready'])
    def test_text_endpoint_cli_uses_actual_artifact_basename(self):
        for name, value in [('task.json', self.task), ('evidence.json', self.review)]:
            (self.base / name).write_text(json.dumps(value), encoding='utf-8')
        (self.base / 'review.md').write_text(self.artifacts['review.md'], encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/delivery_review.py'), '--task', str(self.base / 'task.json'), '--artifact', str(self.base / 'review.md'), '--review', str(self.base / 'evidence.json'), '--capture-root', str(self.capture), '--session', 'mechanical-test-session'], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['delivery_ready'])

if __name__ == '__main__': unittest.main()
