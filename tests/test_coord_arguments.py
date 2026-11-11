"""Missing coordinates must never be rendered as the string "None".

node <id> takes --x/--y; an explicit "x": null used to reach the CLI as
--x None. Absent key and explicit null mean the same thing: no coordinate.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan


def args_for(**extra):
    command = {'name': 'n', 'node_type': 'image'}
    command.update(extra)
    return plan._node_args(command, 'P', [], with_prompt=True)


def coord(args, flag):
    return args[args.index(flag) + 1]


class CoordArgumentTests(unittest.TestCase):
    def test_absent_coordinates_default_to_zero(self):
        args = args_for()
        self.assertEqual((coord(args, '--x'), coord(args, '--y')), ('0', '0'))

    def test_explicit_null_is_not_the_string_none(self):
        args = args_for(x=None, y=None)
        self.assertEqual((coord(args, '--x'), coord(args, '--y')), ('0', '0'))
        self.assertNotIn('None', args)

    def test_real_coordinates_are_preserved(self):
        args = args_for(x=10, y=20)
        self.assertEqual((coord(args, '--x'), coord(args, '--y')), ('10', '20'))

    def test_huge_integer_survives_without_overflow(self):
        huge = 10 ** 400
        args = args_for(x=huge, y=0)
        self.assertEqual(coord(args, '--x'), str(huge))

    def test_infinity_and_bool_fall_back_to_zero(self):
        self.assertEqual(coord(args_for(x=float('inf'), y=True), '--x'), '0')
        self.assertEqual(coord(args_for(x=float('inf'), y=True), '--y'), '0')


if __name__ == '__main__':
    unittest.main()
