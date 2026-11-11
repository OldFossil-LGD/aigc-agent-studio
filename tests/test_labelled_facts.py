"""Facts that already carry their label must not get a second one.

Real run (2026-11-12): height="层高约三米" produced "层高层高约三米",
floor="水磨石地面" produced "地面水磨石地面".
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import libtv_canvas_build as canvas


class LabelledFactTests(unittest.TestCase):
    def test_label_added_when_absent(self):
        self.assertEqual(canvas._labelled('层高', '约三米'), '层高约三米')

    def test_label_not_duplicated_when_value_starts_with_it(self):
        self.assertEqual(canvas._labelled('层高', '层高约三米'), '层高约三米')
        self.assertEqual(canvas._labelled('进深', '进深五米'), '进深五米')

    def test_label_still_added_when_value_only_mentions_it_later(self):
        # 值不是以标签开头时照常加：'地面'+'水磨石地面' → '地面水磨石地面' 读起来是通顺的。
        self.assertEqual(canvas._labelled('地面', '水磨石地面'), '地面水磨石地面')

    def test_missing_value_yields_empty(self):
        for value in (None, '', '   '):
            self.assertEqual(canvas._labelled('进深', value), '')

    def test_scene_view_has_no_duplicate_labels(self):
        facts = {'walls': '石灰墙', 'floor': '地面水磨石', 'fingerprint': '可见空间指纹：墙角有水渍'}
        prompt, missing = canvas._compose_one(
            {'kind': 'scene', 'role': 'view', 'variant': 'A', 'facts': facts}, {})
        self.assertEqual(missing, [])
        self.assertNotIn('地面地面', prompt)
        self.assertNotIn('可见空间指纹：可见空间指纹', prompt)

    def test_scene_plan_has_no_duplicate_labels(self):
        # fingerprint 必须自带标签，否则 '空间指纹：空间指纹' 那条断言永远不会触发（空真）。
        facts = {'walls': '石灰墙', 'floor': '地面水磨石', 'size': '约二十平米',
                 'height': '层高约三米', 'depth': '进深五米', 'openings': '西侧一扇窗',
                 'fingerprint': '空间指纹：墙面有细裂纹'}
        prompt, missing = canvas._compose_one({'kind': 'scene', 'role': 'plan', 'facts': facts}, {})
        self.assertEqual(missing, [])
        for doubled in ('层高层高', '进深进深', '地面地面', '空间指纹：空间指纹'):
            self.assertNotIn(doubled, prompt)


if __name__ == '__main__':
    unittest.main()
