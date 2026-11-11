"""Canvas integrity must report stacked positions without breaking on bad data.

Real payload (2026-11-11, authorized CLI): `libtv project <uuid>` returns
nodes[*].position as {x, y}. A node without usable coordinates yields no
conclusion rather than a guess.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import wiring_plan


def node(name, position=None, node_type='image'):
    row = {'id': name, 'name': name, 'type': node_type}
    if position is not None:
        row['position'] = position
    return row


class StackedPositionTests(unittest.TestCase):
    def report(self, rows, edges=()):
        nodes = {r['id']: r for r in rows}
        names = {r['id']: r['name'] for r in rows}
        return wiring_plan.integrity_report(nodes, names, {}, list(edges))

    def test_two_nodes_at_the_same_point_are_reported(self):
        rep = self.report([node('a', {'x': 0, 'y': 0}), node('b', {'x': 0, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 1)
        self.assertEqual(rep['stacked_nodes'], 2)

    def test_distinct_positions_are_clean(self):
        rep = self.report([node('a', {'x': 0, 'y': 0}), node('b', {'x': 400, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 0)

    def test_missing_or_invalid_position_is_skipped(self):
        rep = self.report([node('a'), node('b', {'x': 'nope', 'y': 0}),
                           node('c', {'x': None, 'y': None}), node('d', {'x': True, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 0)
        self.assertEqual(rep['stacked_nodes'], 0)

    def test_float_and_int_coordinates_compare_equal(self):
        rep = self.report([node('a', {'x': 0, 'y': 0}), node('b', {'x': 0.0, 'y': 0.0})])
        self.assertEqual(rep['stacked_count'], 1)

    def test_huge_integer_is_a_valid_coordinate_and_does_not_raise(self):
        huge = 10 ** 400
        rep = self.report([node('a', {'x': huge, 'y': 0}), node('b', {'x': huge, 'y': 0}),
                           node('c', {'x': 0, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 1)
        self.assertEqual(rep['stacked_nodes'], 2)

    def test_bool_is_not_a_coordinate(self):
        rep = self.report([node('a', {'x': True, 'y': 0}), node('b', {'x': True, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 0)

    def test_inf_and_nan_are_not_coordinates(self):
        inf, nan = float('inf'), float('nan')
        rep = self.report([node('a', {'x': inf, 'y': 0}), node('b', {'x': inf, 'y': 0}),
                           node('c', {'x': nan, 'y': nan})])
        self.assertEqual(rep['stacked_count'], 0)

    def test_large_integers_do_not_collapse_through_float(self):
        big = 2 ** 53 + 1
        rep = self.report([node('a', {'x': big, 'y': 0}), node('b', {'x': big + 1, 'y': 0})])
        self.assertEqual(rep['stacked_count'], 0)

    def test_existing_findings_still_work(self):
        rep = self.report([node('a', {'x': 0, 'y': 0}, 'image'),
                           node('b', {'x': 9, 'y': 0}, 'video')],
                          edges=[{'source': 'a', 'target': 'missing'}])
        self.assertEqual(rep['unknown_endpoints'], 1)
        self.assertEqual(rep['duplicate_count'], 0)


if __name__ == '__main__':
    unittest.main()
