"""A projection that puts the display name under data.name must not break paths
that look nodes up by name.

Measured 2026-11-12 (audit): verify() indexed nodes by the raw name field, so an
MCP-shaped row whose top-level name is "" indexed everything under the empty
string and raised KeyError on the first planned name. _existing_nodes compared
the detail's top-level name and rejected a correct node as "node name mismatch".
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan
import libtv_canvas_build as canvas

UUID = '7f0d1c22-0000-4000-8000-000000000001'
NAME = '资产_甲_主图'


def mcp_row(name=NAME):
    return {'id': UUID, 'name': '', 'type': 'image', 'data': {'name': name}}


class NameProjectionTests(unittest.TestCase):
    def test_existing_nodes_accepts_name_under_data(self):
        def read_json(args):
            # args[0] 是可执行文件路径，不能用 args[:2] 判子命令。
            if 'list' in args and 'node' in args:
                return {'count': 1, 'nodes': [mcp_row()]}
            return {'nodeKey': UUID, 'name': '', 'nodeType': 'image',
                    'data': {'name': NAME, 'params': {'prompt': 'p'}}}
        command = {'name': NAME, 'node_type': 'image', 'prompt': 'p'}
        self.assertEqual(plan._existing_nodes('P', [command], read_json=read_json), {NAME})

    def test_detail_readback_accepts_name_under_data(self):
        # 列表行缺 type 时会回读详情；详情顶层 name 为空、真实名在 data.name。
        doc = {'assets': [{'asset_id': 'A', 'kind': 'prop', 'subject': 'S',
                           'role': 'design', 'layer': 1, 'prompt': 'p'}],
               'props': [{'id': 'S', 'name': '道具'}], 'shots': []}
        node_of = canvas._asset_names(doc)
        target = list(node_of.values())[0]
        row = {'id': UUID, 'name': target, 'data': {'name': target}}   # 无 type → 触发回读
        calls = {'n': 0}

        def fake_run(args, *a, **k):
            calls['n'] += 1
            if calls['n'] == 1:
                return 0, {'count': 1, 'nodes': [row]}
            return 0, {'nodeKey': UUID, 'name': '', 'nodeType': 'image',
                       'data': {'name': target}}

        with patch.object(canvas, '_run', side_effect=fake_run):
            code = canvas.verify('P', doc, node_of=node_of)
        self.assertIn(code, (canvas.RC_OK, canvas.RC_WARN))

    def test_verify_does_not_key_error_on_mcp_rows(self):
        doc = {'assets': [{'asset_id': 'A', 'kind': 'prop', 'subject': 'S',
                           'role': 'design', 'layer': 1, 'prompt': 'p'}],
               'props': [{'id': 'S', 'name': '道具'}], 'shots': []}
        node_of = canvas._asset_names(doc)
        row = {'id': UUID, 'name': '', 'type': 'image', 'data': {'name': list(node_of.values())[0]}}

        def fake_run(args, *a, **k):
            return 0, {'count': 1, 'nodes': [row]}

        with patch.object(canvas, '_run', side_effect=fake_run):
            code = canvas.verify('P', doc, node_of=node_of)
        self.assertIn(code, (canvas.RC_OK, canvas.RC_WARN))


if __name__ == '__main__':
    unittest.main()
