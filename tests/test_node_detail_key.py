"""Node identity read-back must survive the real CLI projection.

Measured 2026-11-11 against the authorized CLI: `node list` returns id,
`node <id>` returns nodeKey and no id at all, both the same UUID. Comparing the
detail's id therefore fails on every already-built canvas.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan
import libtv_canvas_build as canvas

UUID = '0096e0ae-19ab-4118-a414-497e5246e740'
LISTING = {'count': 1, 'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image'}]}
DETAIL = {'nodeKey': UUID, 'name': '资产_甲', 'nodeType': 'image',
          'data': {'params': {'model': 'x'}}}


class DetailKeyTests(unittest.TestCase):
    def test_cli_detail_key_is_node_key(self):
        self.assertEqual(canvas._detail_key(DETAIL), UUID)

    def test_list_shape_still_works(self):
        self.assertEqual(canvas._detail_key({'id': UUID}), UUID)

    def test_missing_key_is_none(self):
        self.assertIsNone(canvas._detail_key({'name': 'x'}))

    def test_snapshot_accepts_node_key_detail(self):
        def fake_run(args, *a, **k):
            return 0, LISTING
        def fake_read(args, *a, **k):
            return DETAIL
        original_run, original_read = canvas._run, canvas._read_existing
        canvas._run, canvas._read_existing = fake_run, fake_read
        try:
            snapshot = canvas._platform_snapshot('proj', {'资产_甲'})
        finally:
            canvas._run, canvas._read_existing = original_run, original_read
        self.assertEqual(sorted(snapshot), ['资产_甲'])
        self.assertIn('nodeKey', json.loads(snapshot['资产_甲']))


class ExistingNodesSkipTests(unittest.TestCase):
    """Re-running a build must skip nodes that already exist, not explode."""

    def test_existing_node_is_skipped_not_rejected(self):
        def read_json(args):
            if len(args) >= 3 and args[2] == 'list':
                return {'count': 1, 'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image'}]}
            return DETAIL

        skipped = plan._existing_nodes('proj', [{'kind': 'node_create', 'name': '资产_甲',
                                                  'node_type': 'image'}],
                                       read_json=read_json)
        self.assertEqual(skipped, {'资产_甲'})

    def test_declared_position_is_read_back_from_project(self):
        calls = []

        def read_json(args):
            calls.append(list(args))
            if args[2] == 'list':
                return {'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image'}]}
            if len(args) > 1 and args[1] == 'project':
                return {'projectUuid': 'proj',
                        'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image',
                                   'position': {'x': 10, 'y': 20}}]}
            return DETAIL

        skipped = plan._existing_nodes(
            'proj', [{'kind': 'node_create', 'name': '资产_甲', 'node_type': 'image',
                      'position': {'x': 10, 'y': 20}}], read_json=read_json)
        self.assertEqual(skipped, {'资产_甲'})

    def test_no_project_call_when_position_is_not_declared(self):
        calls = []

        def read_json(args):
            calls.append(list(args))
            if args[2] == 'list':
                return {'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image'}]}
            return DETAIL

        plan._existing_nodes('proj', [{'kind': 'node_create', 'name': '资产_甲',
                                       'node_type': 'image'}], read_json=read_json)
        self.assertNotIn('project', [c[2] for c in calls if len(c) > 2])

    def test_true_id_mismatch_is_still_rejected(self):
        def read_json(args):
            if len(args) >= 3 and args[2] == 'list':
                return {'count': 1, 'nodes': [{'id': UUID, 'name': '资产_甲', 'type': 'image'}]}
            other = dict(DETAIL, nodeKey='some-other-uuid')
            return other

        with self.assertRaises(RuntimeError):
            plan._existing_nodes('proj', [{'kind': 'node_create', 'name': '资产_甲',
                                           'node_type': 'image'}],
                                 read_json=read_json)


if __name__ == '__main__':
    unittest.main()
