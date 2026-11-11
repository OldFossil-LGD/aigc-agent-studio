"""A document missing subject must not reach the canvas.

subject is required by schemas/asset_system.schema.json and is the source of the
node name; without it the build names nodes 「资产_None_…」 on the real canvas.
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
from test_final_delivery_audit import apply_options
from test_libtv_execution_integrity import CanvasCLI, prop_document


class SubjectRequiredTests(unittest.TestCase):
    def test_missing_subject_blocks_the_build(self):
        doc = prop_document()
        del doc['assets'][0]['subject']
        errs, _ = canvas.validate(doc)
        self.assertTrue(any('subject' in e for e in errs), errs)

    def test_blank_subject_blocks_the_build(self):
        doc = prop_document()
        doc['assets'][0]['subject'] = '   '
        errs, _ = canvas.validate(doc)
        self.assertTrue(any('subject' in e for e in errs), errs)

    def test_apply_stops_before_touching_the_canvas(self):
        doc, cli = prop_document(), CanvasCLI()
        del doc['assets'][0]['subject']
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.nodes, {})

    def test_valid_document_still_builds(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)


class DesignBoardWithoutPromptTests(unittest.TestCase):
    """设计板合法地没有提示词；但不能把字符串 "None" 发到画布上去。"""

    def board_doc(self, prompt=None):
        asset = {'asset_id': 'b', 'kind': 'board', 'subject': 'style',
                 'role': 'design', 'layer': 0}
        if prompt is not None:
            asset['prompt'] = prompt
        return {'assets': [asset], 'shots': []}

    def test_board_without_prompt_emits_no_prompt_flag(self):
        commands, _ = canvas.build_commands(self.board_doc(), 'P')
        self.assertNotIn('--prompt', [t for c in commands for t in c])
        self.assertNotIn('None', ' '.join(t for c in commands for t in c))

    def test_board_with_prompt_still_emits_it(self):
        commands, _ = canvas.build_commands(self.board_doc('风格板描述'), 'P')
        flat = [t for c in commands for t in c]
        self.assertIn('--prompt', flat)
        self.assertIn('风格板描述', flat)

    def test_expected_prompt_is_absent_not_the_word_none(self):
        doc = self.board_doc()
        _, node_of = canvas.build_commands(doc, 'P')
        expected = canvas._expected_nodes(doc, node_of)
        self.assertIsNone(expected[0].get('prompt'))

    def test_blank_prompt_is_treated_as_absent(self):
        commands, _ = canvas.build_commands(self.board_doc('   '), 'P')
        self.assertNotIn('--prompt', [t for c in commands for t in c])

    def test_real_entry_dry_run_stays_clean(self):
        doc, cli = self.board_doc(), CanvasCLI()
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_OK)
        self.assertNotIn('None', log.getvalue())


if __name__ == '__main__':
    unittest.main()
