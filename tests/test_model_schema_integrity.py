"""The model-schema snapshot must be self-consistent, or say why not."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import lib_doctor


class ModelSchemaIntegrityTests(unittest.TestCase):
    def build(self, entries, declared=None):
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        schemas = base / 'schemas' / 'libtv-models'
        schemas.mkdir(parents=True)
        for entry in entries:
            (schemas / entry['file']).write_text('{}', encoding='utf-8')
        payload = {'count': len(entries) if declared is None else declared, 'models': entries}
        (schemas / '_manifest.json').write_text(json.dumps(payload), encoding='utf-8')
        self.addCleanup(tmp.cleanup)
        return base

    def check(self, base):
        with patch.object(lib_doctor, 'HERE', str(base / 'scripts')):
            return lib_doctor._model_schema_integrity()

    def test_consistent_snapshot_is_clean(self):
        base = self.build([{'modelKey': 'a', 'file': 'a.json'}])
        self.assertEqual(self.check(base), ([], 1))

    def test_missing_schema_file_is_reported(self):
        base = self.build([{'modelKey': 'a', 'file': 'a.json'},
                           {'modelKey': 'b', 'file': 'b.json'}])
        (base / 'schemas' / 'libtv-models' / 'b.json').unlink()
        problems, _ = self.check(base)
        self.assertTrue(any('b.json' in p for p in problems))

    def test_declared_count_mismatch_is_reported(self):
        base = self.build([{'modelKey': 'a', 'file': 'a.json'}], declared=9)
        problems, _ = self.check(base)
        self.assertTrue(any('count' in p for p in problems))

    def test_duplicate_keys_are_reported(self):
        base = self.build([{'modelKey': 'a', 'file': 'a.json'},
                           {'modelKey': 'a', 'file': 'a.json'}])
        problems, _ = self.check(base)
        self.assertTrue(any('重复' in p for p in problems))


if __name__ == '__main__':
    unittest.main()
