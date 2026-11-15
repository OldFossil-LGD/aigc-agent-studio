"""Declared positions must be read back, and unreadable positions must fail closed.

Real CLI (2026-11-11): node <id> details carry no position; positions exist only
in the project payload, and only as x/y (no width/height).
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

import libtv_canvas_build as canvas
from test_final_delivery_audit import apply_options, prop_document
from test_libtv_execution_integrity import CanvasCLI


def build_with_positions():
    doc, cli = prop_document(), CanvasCLI()
    doc['assets'][0]['position'] = {'x': 0, 'y': 0, 'w': 100, 'h': 100}
    doc['assets'][1]['position'] = {'x': 200, 'y': 0, 'w': 100, 'h': 100}
    with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
        assert canvas.apply(doc, apply_options()) == 0
    return doc, cli


def build_with_shot_position():
    doc, cli = prop_document(), CanvasCLI()
    doc['shots'] = [{'id': 's1', 'prompt': '一个镜头', 'position': {'x': 50, 'y': 60},
                     'reference_plan': {'assets': [doc['assets'][0]['asset_id']],
                                        'primary_asset_id': doc['assets'][0]['asset_id'],
                                        'prompt_refs': ['{{Image 1}}']}}]
    with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
        assert canvas.apply(doc, apply_options()) == 0
    return doc, cli


class NullPositionMeansUndeclaredTests(unittest.TestCase):
    def test_null_position_is_declared_absent_not_invalid(self):
        doc, cli = prop_document(), CanvasCLI()
        for asset in doc['assets']:
            asset['position'] = None
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)

    def test_unparseable_position_is_still_invalid(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['position'] = {'x': 0}
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertIn('节点位置无效', log.getvalue())


class DeclaredPositionReadbackTests(unittest.TestCase):
    def test_shot_position_is_read_back_too(self):
        doc, cli = build_with_shot_position()
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            # 这份夹具在别处会给出 WARN（可核验范围有限），这里只关心位置不判失败。
            self.assertNotEqual(canvas.verify('P', doc), canvas.RC_FAIL)
        self.assertNotIn('位置', log.getvalue())

    def test_moved_shot_fails_verification(self):
        doc, cli = build_with_shot_position()
        video_id = next(k for k, n in cli.nodes.items() if n.get('type') == 'video')
        cli.nodes[video_id]['position'] = {'x': 777, 'y': 888}
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.verify('P', doc), canvas.RC_FAIL)
        self.assertIn('节点位置与计划不一致', log.getvalue())

    def test_verify_passes_when_positions_match(self):
        doc, cli = build_with_positions()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.verify('P', doc), canvas.RC_OK)

    def test_moved_node_fails_verification(self):
        doc, cli = build_with_positions()
        cli.nodes['id-1']['position'] = {'x': 999, 'y': 999}
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.verify('P', doc), canvas.RC_FAIL)
        self.assertIn('节点位置与计划不一致', log.getvalue())

    def test_unparseable_declared_position_fails_closed(self):
        doc, cli = build_with_positions()
        doc['assets'][0]['position'] = {'x': 0}          # 缺 y，_geometry 给不出坐标
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.verify('P', doc), canvas.RC_FAIL)
        self.assertIn('声明的坐标无法解析', log.getvalue())

    def test_unreadable_positions_fail_closed(self):
        doc, cli = build_with_positions()

        def run(args):
            if args[:1] == ['project']:
                return 1, {'_raw': 'project unavailable'}
            return cli(args)

        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=run), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.verify('P', doc), canvas.RC_FAIL)
        self.assertIn('读不到画布坐标', log.getvalue())


if __name__ == '__main__':
    unittest.main()
