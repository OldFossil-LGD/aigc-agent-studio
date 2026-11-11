import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import compile_intent_delivery as delivery_module
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
    def compile_with_audit(self, out):
        """Two passes: stage the candidate, audit its bytes, then promote."""
        compile_intent_delivery(self.task, out, review=self.review,
                                capture_root=self.capture, session_id='mechanical-test-session')
        pending = out / delivery_module.PENDING_MARKDOWN
        report = out / 'audit.json'
        from scripts.final_delivery_audit import audit_manifest
        names = ['01_production_contract.json', '02_asset_graph_plan.json',
                 '03_shot_graph_plan.json', '04_prompt_packages.jsonl', pending.name]
        actual = {name: (out / name).read_text(encoding='utf-8') for name in names}
        audit_review = mechanical_review(ROOT, self.task, actual, self.capture)
        (out / 'audit-task.json').write_text(json.dumps(self.task), encoding='utf-8')
        (out / 'audit-review.json').write_text(json.dumps(audit_review), encoding='utf-8')
        manifest = {'audit_format': 'final-delivery-audit/v1', 'kind': 'prompt',
                    'task': 'audit-task.json', 'artifacts': names, 'review': 'audit-review.json',
                    'capture_root': str(self.capture), 'session': 'mechanical-test-session',
                    'prompt_dir': '.', 'prompt_markdown': pending.name,
                    'grill': str(ROOT / 'samples/grill_ledger_papercut_prompt.json')}
        manifest_path = out / 'audit-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        audited = audit_manifest(manifest_path)
        self.assertTrue(audited['delivery_ready'], audited['checks'])
        report.write_text(json.dumps(audited), encoding='utf-8')
        return compile_intent_delivery(self.task, out, review=self.review,
                                       capture_root=self.capture, session_id='mechanical-test-session',
                                       final_audit_report=str(report))

    def test_current_evidence_can_finalize_without_quality_or_generation_claim(self):
        checked = self.check_review(self.review)
        self.assertTrue(checked['delivery_ready'], checked)
        self.assertFalse(checked['creative_quality_verified']); self.assertFalse(checked['media_quality_verified']); self.assertFalse(checked['generation_authorized'])
        blocked = compile_intent_delivery(self.task, self.base / 'final', review=self.review, capture_root=self.capture, session_id='mechanical-test-session')
        self.assertEqual(blocked['delivery']['delivery_readiness'], 'FINAL_AUDIT_REQUIRED', blocked['delivery'].get('final_audit'))
        self.assertFalse((self.base / 'final/13_Final_Prompt.md').exists())
        self.assertTrue((self.base / ('final/' + delivery_module.PENDING_MARKDOWN)).is_file())
        self.assertTrue(Path(blocked['copyable_markdown']).is_file())
        self.assertTrue(all((self.base / 'final' / name).is_file()
                            for name in blocked['delivery']['artifacts']))
        final = self.compile_with_audit(self.base / 'final')
        self.assertEqual(final['delivery']['delivery_readiness'], 'REVIEW_EVIDENCE_READY', final['delivery']['final_audit'])
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
        with patch.object(delivery_module, '_final_audit_gate', return_value={'status': 'PASS', 'reason': 'test-only gate'}):
            compile_intent_delivery(self.task, out, review=self.review, capture_root=self.capture, session_id='mechanical-test-session')
        self.assertTrue((out / '13_Final_Prompt.md').is_file())
        compile_intent_delivery(self.task, out, draft=True)
        self.assertFalse((out / '13_Final_Prompt.md').exists())
        self.assertTrue((out / '13_Previous_Final_Prompt.unverified.md').exists())

if __name__ == '__main__': unittest.main()
