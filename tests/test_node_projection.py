"""Node identity must survive both platform projections.

Measured on a real canvas through the authorized MCP channel: the display name
lives in data.name and the top-level name is an empty string. The CLI
projection puts it at the top level. Readers must accept both.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan

MCP_SHAPED = {"id": "n1", "name": "", "type": "image",
              "position": {"x": 0, "y": 0},
              "data": {"name": "资产_甲_主图", "params": {"prompt": "a"}}}
CLI_SHAPED = {"id": "n2", "name": "资产_乙_主图", "type": "image",
              "params": {"prompt": "b"}}


class NodeNameTests(unittest.TestCase):
    def test_mcp_projection_reads_name_from_data(self):
        self.assertEqual(plan._node_name(MCP_SHAPED), "资产_甲_主图")

    def test_cli_projection_reads_top_level_name(self):
        self.assertEqual(plan._node_name(CLI_SHAPED), "资产_乙_主图")

    def test_empty_name_is_not_an_identity(self):
        self.assertIsNone(plan._node_name({"id": "n3", "name": "", "data": {}}))

    def test_singleton_wrapper_is_unwrapped(self):
        self.assertEqual(plan._node_name({"nodes": [MCP_SHAPED]}), "资产_甲_主图")


if __name__ == '__main__':
    unittest.main()
