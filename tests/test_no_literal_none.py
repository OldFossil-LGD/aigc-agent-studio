"""Two renderers turn plans into LibTV argv; neither may emit the string "None".

libtv_canvas_build.build_commands renders a canvas document;
apply_libtv_plan._node_args renders a compiled command dict.
They diverged once each (prompt, coordinates), both times sending the literal
text "None" to the CLI. This pins that property for both.

Note: _expected_nodes is NOT the same structure as a renderer command - it keeps
position/params in their own shape (libtv_canvas_build.py:576-582) rather than the
x/y/settings a renderer reads, so the two must not be fed into each other.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan
import libtv_canvas_build as canvas


def flat(args):
    return [str(a) for a in args]


def sparse_doc():
    """Every optional field absent: the shape that used to leak "None"."""
    return {
        'assets': [
            {'asset_id': 'b', 'kind': 'board', 'subject': 'style',
             'role': 'design', 'layer': 0},
            {'asset_id': 'a', 'kind': 'prop', 'subject': 'P1', 'role': 'anchor',
             'layer': 1, 'prompt': '道具正面', 'parent': 'b'},
        ],
        'shots': [],
    }


class NoLiteralNoneTests(unittest.TestCase):
    def test_canvas_builder_never_emits_none(self):
        doc = sparse_doc()
        commands, node_of = canvas.build_commands(doc, 'P')
        self.assertEqual(len(commands), len(doc['assets']))   # 空列表不算通过
        # node_of 为空时下面的 for 循环体一次都不执行——必须先把映射钉住。
        self.assertEqual(set(node_of), {a['asset_id'] for a in doc['assets']})
        joined = ' '.join(' '.join(flat(c)) for c in commands)
        for asset_id, name in node_of.items():
            # 空名字必须挡在前面：'' in 任何字符串 都为真，assertIn 会假绿。
            self.assertTrue(name and name.strip(), "节点名为空：%r" % (asset_id,))
            self.assertIn(name, joined)
        # 整族一次堵死：任何一条命令、任何一个参数 token 都不许为空串。
        for command in commands:
            self.assertTrue(command, "出现了空命令")
            for token in flat(command):
                self.assertTrue(token.strip(), "出现了空参数：%r" % (command,))
        self.assertNotIn('None', joined)

    def test_command_renderer_never_emits_none(self):
        command = {'name': '目标节点', 'node_type': 'image',
                   'prompt': None, 'model': None, 'mode_type': None,
                   'x': None, 'y': None, 'settings': None, 'refs': []}
        args = flat(plan._node_args(command, 'P', [], with_prompt=True))
        self.assertIn('create', args)
        self.assertIn('目标节点', args)
        self.assertNotIn('None', ' '.join(args))

    def test_expected_nodes_keeps_absent_prompts_absent(self):
        doc = sparse_doc()
        _, node_of = canvas.build_commands(doc, 'P')
        expected = canvas._expected_nodes(doc, node_of)
        board = node_of['b']
        matches = [e for e in expected if e['name'] == board]
        self.assertEqual(len(matches), 1)          # 空集不得因 all([]) 通过
        self.assertIn('prompt', matches[0])        # 键存在
        self.assertIsNone(matches[0]['prompt'])    # 且值为 None，不是 "None"

    def test_expected_nodes_still_carries_position_and_params(self):
        """纠正一个曾经的错误说法：_expected_nodes 并非不带坐标与参数。"""
        doc = sparse_doc()
        doc['assets'][1]['position'] = {'x': 5, 'y': 6}
        doc['assets'][1]['settings'] = {'weight': 0.5}
        _, node_of = canvas.build_commands(doc, 'P')
        expected = {e['name']: e for e in canvas._expected_nodes(doc, node_of)}
        node = expected[node_of['a']]
        self.assertEqual(node['position'], {'x': 5, 'y': 6})
        self.assertEqual(node['params'], {'weight': 0.5})
        # 形状差异本身也要钉住：渲染器读的是 x/y/settings，这里一个都没有。
        for renderer_key in ('x', 'y', 'settings'):
            self.assertNotIn(renderer_key, node)


if __name__ == '__main__':
    unittest.main()
