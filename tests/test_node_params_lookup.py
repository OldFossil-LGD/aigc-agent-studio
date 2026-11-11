"""The platform splits one declared -s batch across two places.

Real payloads (2026-11-12, canvas 0bd2566c): modeType sits at params.modeType,
enableSound sits at params.settings.enableSound. Comparing only one of them made
re-running --apply fail with "node parameters mismatch" on every node that
declares mode_type and on every video node.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan


def node(params):
    return {'name': 'n', 'nodeType': 'video', 'data': {'params': params}}


def cmd(**fields):
    # node_type 必须给：_node_matches 先比对它，缺了会提前返回 False，
    # 那样"不匹配"用例会因为错误的原因通过（假绿）。
    base = {'name': 'n', 'node_type': 'video'}
    base.update(fields)
    return base


class ParameterLookupTests(unittest.TestCase):
    def test_setting_declared_at_top_level_matches(self):
        self.assertTrue(plan._node_matches(
            cmd(settings={'modeType': 'mixed2video'}), node({'modeType': 'mixed2video'})))

    def test_param_declared_under_settings_matches(self):
        self.assertTrue(plan._node_matches(
            cmd(params={'enableSound': 'off'}), node({'settings': {'enableSound': 'off'}})))

    def test_differing_value_still_mismatches(self):
        self.assertFalse(plan._node_matches(
            cmd(params={'enableSound': 'on'}), node({'settings': {'enableSound': 'off'}})))

    def test_absent_key_still_mismatches(self):
        self.assertFalse(plan._node_matches(
            cmd(params={'enableSound': 'off'}), node({'settings': {'ratio': '16:9'}})))

    def test_conflicting_values_on_both_copies_are_not_a_match(self):
        self.assertFalse(plan._node_matches(
            cmd(settings={'modeType': 'mixed2video'}),
            node({'modeType': 'text2image', 'settings': {'modeType': 'mixed2video'}})))

    def test_nested_params_settings_still_compare(self):
        # params 分支必须能原样比对嵌套的 settings 结构（合并视图曾把它排除）。
        declared = {'settings': {'enableSound': 'off'}}
        self.assertTrue(plan._node_matches(
            cmd(params=declared), node({'settings': {'enableSound': 'off'}})))

    def test_conflicting_top_level_and_nested_is_not_a_match(self):
        # 两处都有但值不同：平台以哪处为准未知，不猜，判不匹配。
        self.assertFalse(plan._node_matches(
            cmd(settings={'enableSound': 'off'}),
            node({'enableSound': 'on', 'settings': {'enableSound': 'off'}})))

    def test_params_branch_uses_json_semantics_for_conflicts(self):
        # params 分支同样要按 JSON 口径发现冲突（审计指出的未覆盖点）。
        self.assertFalse(plan._node_matches(
            cmd(params={'y': True}),
            node({'y': True, 'settings': {'y': 1}})))

    def test_conflict_detected_with_json_semantics(self):
        # True 与 1 在 Python 里相等，在 JSON 里不同：冲突检查必须用 JSON 口径。
        self.assertFalse(plan._node_matches(
            cmd(settings={'x': True}),
            node({'x': True, 'settings': {'x': 1}})))

if __name__ == '__main__':
    unittest.main()
