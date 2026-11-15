"""Ambiguous node inventories must be refused, not silently collapsed.

_existing_nodes builds id and name maps; a duplicate in either would make later
lookups nondeterministic, so it raises instead. This was not covered by any test
until the mutation suite flagged the guard as removable.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan


def stub(rows):
    def read_json(args):
        return {'nodes': rows}
    return read_json


class AmbiguousInventoryTests(unittest.TestCase):
    def test_duplicate_id_is_rejected(self):
        rows = [{'id': 'n1', 'name': '甲'}, {'id': 'n1', 'name': '乙'}]
        with self.assertRaises(RuntimeError) as ctx:
            plan._existing_nodes('P', [], read_json=stub(rows))
        self.assertIn('ambiguous', str(ctx.exception))

    def test_duplicate_name_is_rejected(self):
        rows = [{'id': 'n1', 'name': '甲'}, {'id': 'n2', 'name': '甲'}]
        with self.assertRaises(RuntimeError) as ctx:
            plan._existing_nodes('P', [], read_json=stub(rows))
        self.assertIn('ambiguous', str(ctx.exception))

    def test_distinct_rows_are_accepted(self):
        rows = [{'id': 'n1', 'name': '甲'}, {'id': 'n2', 'name': '乙'}]
        self.assertEqual(plan._existing_nodes('P', [], read_json=stub(rows)), set())


if __name__ == '__main__':
    unittest.main()
