import unittest

from scripts.apply_libtv_plan import build_phases, build_commands


class ApplyLibtvPlanTests(unittest.TestCase):
    def test_cycle_is_rejected(self):
        plan = {
            "commands": [
                {"kind": "node_create", "name": "a", "node_type": "text", "x": 0, "y": 0, "group_name": "g"},
                {"kind": "node_create", "name": "b", "node_type": "text", "x": 0, "y": 0, "group_name": "g"},
                {"kind": "node_link", "target": "a", "left": "b", "purpose": "x"},
                {"kind": "node_link", "target": "b", "left": "a", "purpose": "y"},
            ]
        }
        with self.assertRaises(ValueError):
            build_phases(plan, "P")

    def test_normal_plan_orders_dependencies(self):
        plan = {
            "commands": [
                {"kind": "node_create", "name": "a", "node_type": "text", "x": 0, "y": 0, "group_name": "g"},
                {"kind": "node_create", "name": "b", "node_type": "text", "x": 0, "y": 0, "group_name": "g"},
                {"kind": "node_link", "target": "b", "left": "a", "purpose": "x"},
            ]
        }
        phases = build_phases(plan, "P")
        self.assertEqual(phases["node_names"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
