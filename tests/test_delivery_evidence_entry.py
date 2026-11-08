import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.compile_intent_delivery import compile_intent_delivery

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'samples' / 'papercut_empty_shot_intent.json'

class DeliveryEvidenceEntryTests(unittest.TestCase):
    def test_missing_review_does_not_create_a_final_deliverable(self):
        handoff = json.loads(SAMPLE.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'draft output'
            result = compile_intent_delivery(handoff, out)
            self.assertEqual(result['delivery'].get('delivery_readiness'), 'DRAFT_REVIEW_REQUIRED')
            self.assertFalse((out / '13_Final_Prompt.md').exists())
            self.assertTrue((out / '13_Draft_Prompt.md').is_file())
            self.assertEqual(set(result['delivery']['artifacts']), {p.name for p in out.iterdir() if p.is_file()})
            self.assertFalse(result['delivery']['claims'].get('creative_quality_verified', False))

    def test_default_cli_cannot_report_success_without_review(self):
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts' / 'compile_intent_delivery.py'), str(SAMPLE), '--out', str(Path(td) / 'blocked')], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('DRAFT_REVIEW_REQUIRED', proc.stdout + proc.stderr)

    def test_explicit_draft_is_offline_success_but_not_final(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'draft only'
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts' / 'compile_intent_delivery.py'), str(SAMPLE), '--out', str(out), '--draft'], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('DRAFT_REVIEW_REQUIRED', proc.stdout)
            self.assertFalse((out / '13_Final_Prompt.md').exists())

class LibraryConsiderationTests(unittest.TestCase):
    def test_current_catalog_matches_real_public_tree(self):
        from scripts.knowledge_catalog import validate_catalog
        result = validate_catalog(ROOT)
        self.assertEqual(result['status'], 'CATALOG_VALID', result)

    def test_unregistered_new_source_is_not_silently_ignored(self):
        from scripts.knowledge_catalog import validate_catalog
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'isolated skill'
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.snapshots', '.git'))
            self.assertEqual(validate_catalog(root)['status'], 'CATALOG_VALID')
            (root / 'references' / 'unregistered_creative_case.md').write_text('# New creative knowledge\n', encoding='utf-8')
            result = validate_catalog(root)
            self.assertNotEqual(result['status'], 'CATALOG_VALID')
            self.assertTrue(result.get('errors'))

if __name__ == '__main__':
    unittest.main()
