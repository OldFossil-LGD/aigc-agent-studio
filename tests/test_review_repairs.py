"""Regression coverage for the 2026-11-09 repository review."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import compile_intent_delivery as delivery
from scripts import libtv_canvas_build as canvas
from tests.test_libtv_execution_integrity import prop_document, CanvasCLI, apply_options

ROOT = Path(__file__).resolve().parents[1]


class DeliveryFailureTests(unittest.TestCase):
    def test_prior_final_is_invalidated_before_failing_pipeline_stages(self):
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        for stage in ('compile_production', 'render', 'evaluate_delivery_review'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                final = out / delivery.COPYABLE_MARKDOWN
                original = '# 最终提示词（可直接复制投喂）\nPrior delivery'
                final.write_text(original, encoding='utf-8')
                target = 'scripts.delivery_review.evaluate_delivery_review' if stage == 'evaluate_delivery_review' else 'scripts.compile_intent_delivery.' + stage
                with patch(target, side_effect=OSError('injected pipeline failure')):
                    with self.assertRaises(OSError):
                        delivery.compile_intent_delivery(intent, out, draft=True)
                self.assertFalse(final.exists())
                archives = list(out.glob('13_Previous_Final_Prompt*.md'))
                self.assertEqual(len(archives), 1)
                self.assertEqual(archives[0].read_text(encoding='utf-8'), original)

    def test_new_final_is_published_only_after_reports_are_written(self):
        from scripts.delivery_review import evaluate_delivery_review
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        review_result = evaluate_delivery_review(ROOT, intent, {}, None)
        review_result.update(delivery_ready=True, status='REVIEW_EVIDENCE_VALID')
        real_write = delivery._write_json
        def fail_report(path, payload):
            if path.name == delivery.VERIFICATION_REPORT:
                raise OSError('injected report write failure')
            real_write(path, payload)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch('scripts.delivery_review.evaluate_delivery_review', return_value=review_result), patch.object(delivery, '_write_json', side_effect=fail_report):
                with self.assertRaises(OSError):
                    delivery.compile_intent_delivery(intent, out)
            self.assertFalse((out / delivery.COPYABLE_MARKDOWN).exists())

    def test_publishing_failure_never_leaves_ready_metadata(self):
        from scripts.delivery_review import evaluate_delivery_review
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        review_result = evaluate_delivery_review(ROOT, intent, {}, None)
        review_result.update(delivery_ready=True, status='REVIEW_EVIDENCE_VALID')
        real_replace = Path.replace
        def fail_final_replace(path, target):
            if Path(target).name == delivery.COPYABLE_MARKDOWN:
                raise OSError('injected final publication failure')
            return real_replace(path, target)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch('scripts.delivery_review.evaluate_delivery_review', return_value=review_result), patch.object(Path, 'replace', fail_final_replace), patch.object(delivery, '_final_audit_gate', return_value={'status': 'PASS', 'reason': 'test-only gate'}):
                with self.assertRaises(OSError):
                    delivery.compile_intent_delivery(intent, out)
            package = json.loads((out / delivery.DELIVERY_PACKAGE).read_text(encoding='utf-8'))
            self.assertNotEqual(package['delivery_readiness'], 'REVIEW_EVIDENCE_READY')
            self.assertNotIn(delivery.COPYABLE_MARKDOWN, package['artifacts'])
            self.assertFalse((out / delivery.COPYABLE_MARKDOWN).exists())

    def test_previous_ready_metadata_is_invalidated_before_compilation(self):
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / delivery.COPYABLE_MARKDOWN).write_text('# 最终提示词（可直接复制投喂）\nOld', encoding='utf-8')
            (out / delivery.DELIVERY_PACKAGE).write_text(json.dumps({'delivery_readiness': 'REVIEW_EVIDENCE_READY', 'artifacts': [delivery.COPYABLE_MARKDOWN]}), encoding='utf-8')
            with patch.object(delivery, 'compile_production', side_effect=OSError('injected compiler failure')):
                with self.assertRaises(OSError):
                    delivery.compile_intent_delivery(intent, out, draft=True)
            package = json.loads((out / delivery.DELIVERY_PACKAGE).read_text(encoding='utf-8'))
            self.assertNotEqual(package['delivery_readiness'], 'REVIEW_EVIDENCE_READY')
            self.assertNotIn(delivery.COPYABLE_MARKDOWN, package['artifacts'])

    def test_ready_metadata_write_failure_removes_new_final(self):
        from scripts.delivery_review import evaluate_delivery_review
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        review_result = evaluate_delivery_review(ROOT, intent, {}, None)
        review_result.update(delivery_ready=True, status='REVIEW_EVIDENCE_VALID')
        real_write = delivery._write_json
        def fail_ready(path, payload):
            if path.name == delivery.DELIVERY_PACKAGE and payload.get('delivery_readiness') == 'REVIEW_EVIDENCE_READY':
                raise OSError('injected ready metadata failure')
            real_write(path, payload)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch('scripts.delivery_review.evaluate_delivery_review', return_value=review_result), patch.object(delivery, '_write_json', side_effect=fail_ready), patch.object(delivery, '_final_audit_gate', return_value={'status': 'PASS', 'reason': 'test-only gate'}):
                with self.assertRaises(OSError):
                    delivery.compile_intent_delivery(intent, out)
            self.assertTrue((out / delivery.DELIVERY_PACKAGE).exists())
            package = json.loads((out / delivery.DELIVERY_PACKAGE).read_text(encoding='utf-8'))
            self.assertNotEqual(package['delivery_readiness'], 'REVIEW_EVIDENCE_READY')
            self.assertFalse((out / delivery.COPYABLE_MARKDOWN).exists())

    def test_foreign_final_is_refused_before_any_compiler_artifacts(self):
        intent = json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            final = out / delivery.COPYABLE_MARKDOWN
            final.write_text('Hand-written document', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                delivery.compile_intent_delivery(intent, out, draft=True)
            self.assertEqual(final.read_text(encoding='utf-8'), 'Hand-written document')
            self.assertFalse((out / '01_production_contract.json').exists())


class AssetDependencyTests(unittest.TestCase):
    def test_invalid_parent_graph_stops_before_any_cli_call(self):
        for parent in ('MISSING', 'B', True, ['A']):
            doc = prop_document()
            doc['assets'][1].update(role='closeup', layer=2, parent=parent)
            with self.subTest(parent=parent), patch.object(canvas, '_run', side_effect=AssertionError('CLI called before validation')) as cli, contextlib.redirect_stdout(io.StringIO()):
                try:
                    code = canvas.apply(doc, apply_options())
                except TypeError as exc:
                    self.fail('Malformed parent escaped validation: ' + str(exc))
                self.assertEqual(code, canvas.RC_FAIL)
                cli.assert_not_called()
                with self.assertRaises(ValueError):
                    canvas.build_commands(doc, 'P')

    def test_cycle_is_refused_before_command_generation(self):
        doc = prop_document()
        doc['assets'][0]['parent'] = 'B'
        doc['assets'][1]['parent'] = 'A'
        self.assertTrue(canvas.validate(doc)[0])
        with self.assertRaises(ValueError):
            canvas.build_commands(doc, 'P')

    def test_parent_is_created_before_reversed_input_child(self):
        doc = prop_document()
        doc['assets'][0].update(role='closeup', layer=2, parent='B')
        doc['assets'][1].update(role='closeup', layer=2)
        cli = CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            try:
                code = canvas.apply(doc, apply_options())
            except (RuntimeError, StopIteration) as exc:
                self.fail('Child was created before its parent: ' + str(exc))
            self.assertEqual(code, 0)
        self.assertEqual(cli.creates, ['资产_second_近距版', '资产_first_近距版'])


class MergedViewTests(unittest.TestCase):
    def test_composition_consumes_every_declared_view(self):
        facts = {'age': 30, 'face': 'square face', 'hair': 'short hair', 'clothing': 'plain shirt'}
        for variant, covers, required in [('front', ['front', 'back'], ['正面全身', '背面全身']),
                                          ('left', ['left', 'top'], ['正左侧90度', '正上方90度'])]:
            doc = {'assets': [{'asset_id': 'V', 'kind': 'character', 'subject': 'C1',
                              'role': 'view', 'variant': variant, 'covers': covers, 'facts': facts}]}
            with self.subTest(covers=covers):
                self.assertEqual(canvas.compose_all(doc), [])
                for text in required:
                    self.assertIn(text, doc['assets'][0]['prompt'])
                for view in covers:
                    self.assertIn('【' + canvas.VIEW_CN[view] + '区域】', doc['assets'][0]['prompt'])

    def test_unknown_declared_view_is_unresolved(self):
        asset = {'kind': 'character', 'role': 'view', 'variant': 'front',
                 'covers': ['front', 'unknown'],
                 'facts': {'age': 30, 'face': 'face', 'hair': 'hair', 'clothing': 'shirt'}}
        prompt, missing = canvas._compose_one(asset, {})
        self.assertIsNone(prompt)
        self.assertTrue(missing)


class CanvasReadbackTests(unittest.TestCase):
    def setUp(self):
        self.doc = prop_document()
        self.rows = [{'id': 'A', 'name': '资产_first_主图', 'type': 'image'},
                     {'id': 'B', 'name': '资产_second_主图', 'type': 'image'}]

    def test_wrong_asset_type_fails_verification(self):
        self.rows[0]['type'] = 'video'
        with patch.object(canvas, '_run', return_value=(0, {'nodes': self.rows})), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.verify('P', self.doc), canvas.RC_FAIL)

    def test_missing_inventory_type_is_read_from_identity_bound_details(self):
        for wrong_id, node_type, expected in [(False, 'image', 0), (False, 'video', 1), (True, 'image', 1)]:
            rows = [{k: v for k, v in row.items() if k != 'type'} for row in self.rows]
            def read(args):
                if args[:2] == ['node', 'list']:
                    return 0, {'nodes': rows}
                row = next(row for row in self.rows if args[1] == row['id'])
                return 0, {'nodes': [dict(row, type=node_type, id='FOREIGN' if wrong_id else row['id'])]}
            with self.subTest(wrong_id=wrong_id, node_type=node_type), patch.object(canvas, '_run', side_effect=read), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.verify('P', self.doc), expected)

    def test_strict_media_check_requires_nonblank_location_content(self):
        self.doc['shots'] = [{'id': 'S1', 'prompt': 'shot', 'reference_plan': {
            'assets': ['A'], 'primary_asset_id': 'A', 'prompt_refs': ['image1']}}]
        rows = self.rows + [{'id': 'V', 'name': '镜头_S1', 'type': 'video'}]
        for urls, expected in [([''], 1), (['   '], 1), ([None], 1), ({'bad': True}, 1),
                               (' ', 1), (['https://media.test/a.png'], 0), ('https://media.test/a.png', 0)]:
            def read(args):
                if args[:2] == ['node', 'list']:
                    return 0, {'nodes': rows}
                if args[1] == '镜头_S1':
                    return 0, {'params': {'imageListOrder': ['A']}}
                return 0, {'data': {'url': urls}, 'params': {}}
            with self.subTest(urls=urls), patch.object(canvas, '_run', side_effect=read), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.verify('P', self.doc, strict_effective=True), expected)


if __name__ == '__main__':
    unittest.main()
