"""A cached read-back whose business status is FAIL must not become a unit.

work_units derived PASS from "how many units we built". A cached node payload
carrying {"status": "FAIL"} produced a normal unit and a green summary
(2026-11-12 audit).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import work_units


GRAPH = {'nodes': [{'id': 'n1', 'type': 'video', 'name': '镜头_S1'}]}


class CachedFailureTests(unittest.TestCase):
    def test_cached_failure_status_is_not_a_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / 'n1.json').write_text(json.dumps({'status': 'FAIL', 'params': {}}), encoding='utf-8')
            out = work_units.build_units(GRAPH, 'P', '', cache, offline=True, limit=None)
        self.assertEqual(out.get('units'), [])
        self.assertTrue(out.get('unreadable'), out)

    def test_cached_pass_status_is_still_a_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / 'n1.json').write_text(json.dumps({'status': 'PASS', 'params': {}}), encoding='utf-8')
            out = work_units.build_units(GRAPH, 'P', '', cache, offline=True, limit=None)
        self.assertEqual(len(out.get('units') or []), 1)


if __name__ == '__main__':
    unittest.main()
