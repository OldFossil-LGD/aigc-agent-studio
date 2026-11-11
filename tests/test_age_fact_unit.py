"""Facts may carry their own unit; the age template must not append a second one.

Real run (2026-11-12): facts age="二十岁上下" produced "二十岁上下岁，圆脸…".
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import libtv_canvas_build as canvas


def block(age):
    return canvas._block({'age': age, 'gender': '女', 'face': '圆脸', 'hair': '短发',
                          'clothing': '外套'})


class AgeUnitTests(unittest.TestCase):
    def test_numeric_age_gets_the_unit(self):
        self.assertIn('20岁', block('20'))
        self.assertNotIn('20岁岁', block('20'))

    def test_age_with_its_own_unit_is_left_alone(self):
        text = block('二十岁上下')
        self.assertIn('二十岁上下', text)
        self.assertNotIn('二十岁上下岁', text)


if __name__ == '__main__':
    unittest.main()
