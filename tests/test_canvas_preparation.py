"""Exercise canvas preparation entirely offline, including sanctioned merged views."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import libtv_canvas_build as canvas


class CanvasPreparationTests(unittest.TestCase):
    def document(self, state=None):
        assets = [{'asset_id': 'F', 'kind': 'character', 'subject': 'C1',
                   'role': 'face', 'layer': 1, 'prompt': 'Face reference'}]
        for view in ['front', 'back', 'left', 'right', 'top', 'body']:
            assets.append({'asset_id': view, 'kind': 'character', 'subject': 'C1',
                           'role': 'body' if view == 'body' else 'view', 'variant': view,
                           'layer': 2, 'state': state, 'parent': 'F', 'prompt': 'View reference'})
        return {'characters': [{'id': 'C1', 'base_state': state or '基准'}],
                'assets': assets, 'shots': []}

    def test_declared_look_cannot_be_omitted_entirely(self):
        doc = self.document()
        doc['characters'][0]['states'] = ['基准', 'L002']
        self.assertTrue(canvas.validate(doc)[0])

    def test_named_baseline_and_legacy_empty_state_share_one_look(self):
        doc = self.document()
        for asset in doc['assets'][1:4]:
            asset['state'] = '基准'
        self.assertEqual(canvas.validate(doc)[0], [])

    def test_one_named_look_requires_six_derived_views(self):
        errors, _ = canvas.validate(self.document('L001'))
        self.assertEqual(errors, [])

    def test_merged_nodes_cover_the_seven_required_views(self):
        doc = self.document()
        doc['assets'] = [a for a in doc['assets'] if a['asset_id'] not in ['back', 'top']]
        doc['assets'][1]['covers'] = ['front', 'back']
        doc['assets'][2]['covers'] = ['left', 'top']
        self.assertEqual(canvas.validate(doc)[0], [])

    def test_duplicate_bodies_do_not_replace_directional_views(self):
        doc = self.document()
        for asset in doc['assets'][1:]:
            asset['role'] = 'body'
        self.assertTrue(canvas.validate(doc)[0])

    def test_views_from_other_looks_do_not_fill_missing_view(self):
        doc = self.document('L001')
        other = self.document('L002')['assets'][1:]
        for asset in other:
            asset['asset_id'] += '_L002'
        doc['assets'].extend(other)
        doc['assets'] = [a for a in doc['assets'] if a['asset_id'] != 'back_L002']
        self.assertTrue(canvas.validate(doc)[0])

    def test_offline_dry_run_without_platform_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'plan.json'
            source.write_text(json.dumps(self.document()), encoding='utf-8')
            for flags in [[], ['--dry-run']]:
                with self.subTest(flags=flags), \
                        patch.object(canvas, 'LIBTV', str(Path(temp) / 'missing.exe')), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    code = canvas.main([str(source)] + flags)
                    self.assertEqual(code, 0)
                    self.assertIn('dry-run', output.getvalue())

    def test_failed_readbacks_cannot_validate_stale_response_data(self):
        doc = {'assets': [{'asset_id': 'F', 'subject': 'C1', 'role': 'face'}],
               'shots': [{'id': 'S1', 'reference_plan': {'assets': ['F']}}]}
        for failed_kind in ['order', 'artifact']:
            def readback(args):
                if args[:2] == ['node', 'list']:
                    return 0, {'nodes': [{'id': 'idF', 'name': 'asset_F'}]}
                if args[1] == '镜头_S1':
                    return (1 if failed_kind == 'order' else 0), {
                        'data': {'params': {'imageListOrder': ['idF']}}}
                return (1 if failed_kind == 'artifact' else 0), {'data': {'url': ['old-data']}}

            with self.subTest(failed_kind=failed_kind), \
                    patch.object(canvas, '_run', side_effect=readback), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.verify('P', doc, {'F': 'asset_F'}, True), 1)


if __name__ == '__main__':
    unittest.main()
