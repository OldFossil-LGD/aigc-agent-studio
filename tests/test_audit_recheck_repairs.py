"""Independent regressions discovered while reviewing the handover changes."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import libtv_canvas_build as canvas
from scripts.compile_intent_delivery import _final_audit_gate
from scripts.delivery_contract import derive, validate
from scripts.final_delivery_audit import audit_manifest
from scripts.final_delivery_audit import _placeholder_line
from tests.review_fixture import mechanical_review
from tests.test_libtv_execution_integrity import CanvasCLI, prop_document, apply_options

ROOT = Path(__file__).resolve().parents[1]


class ReviewCoverageTests(unittest.TestCase):
    def test_declared_specialist_is_executed_against_the_actual_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'captures').mkdir()
            task = {'goal': '检查雨夜排镜表的生成单元安排', 'profile': 'rework',
                    'requirements': [{'id': 'R1', 'text': '核对每镜生成时长'}],
                    'delivery': {'required_checks': ['shotlist']}}
            body = ('| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |\n'
                    '|---|---|---|---|---|\n'
                    '| SH01 | 全景 | 4.5 | 建立 | 门口无人 |\n'
                    '| SH02 | 近景 | 3.0 | 推进 | 门把转动 |\n'
                    '| SH03 | 大特写 | 2.0 | 反应 | 眼睛睁开 |\n'
                    '| SH04 | 中景 | 2.5 | 揭示 | 来人站在门边 |\n'
                    '| SH05 | 插入 | 2.5 | 收束 | 门锁停住 |\n')
            artifacts = {'shotlist.md': body}
            (root / 'shotlist.md').write_text(body, encoding='utf-8')
            review = mechanical_review(ROOT, task, artifacts, root / 'captures')
            (root / 'review.json').write_text(json.dumps(review), encoding='utf-8')
            (root / 'task.json').write_text(json.dumps(task), encoding='utf-8')
            manifest = {'audit_format': 'final-delivery-audit/v1', 'kind': 'text',
                        'task': 'task.json', 'artifacts': ['shotlist.md'], 'review': 'review.json',
                        'capture_root': 'captures', 'session': 'mechanical-test-session',
                        'specialists': {'shotlist': {'path': 'shotlist.md', 'mode': 'gen'}}}
            (root / 'audit.json').write_text(json.dumps(manifest), encoding='utf-8')
            result = audit_manifest(root / 'audit.json')
            receipt = next(item for item in result['checks'] if item['name'] == 'specialist_shotlist')
            self.assertIn('exit', receipt['detail'])
            self.assertEqual(receipt['detail']['exit'], 0, receipt)
            self.assertTrue(result['delivery_ready'], result['checks'])

    def test_annotated_todo_is_still_unfinished(self):
        self.assertIsNotNone(_placeholder_line('## 动作\nTODO: 补齐动作'))

    def test_quoted_example_is_allowed_in_a_text_review(self):
        self.assertIsNone(_placeholder_line('原提示词中有一处缺项\n> TODO\n以上引用需要修正。', allow_examples=True))

    def test_every_artifact_needs_an_actual_review_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'captures').mkdir()
            task = {'goal': '审阅交接动作和杯子的最终归属', 'profile': 'rework',
                    'requirements': [{'id': 'R1', 'text': '杯子最终由谁持有'}]}
            artifacts = {'review.md': '杯子仍在原持有者手中。', 'shotlist.md': '分镜表暂时只有标题。'}
            for name, body in artifacts.items():
                (root / name).write_text(body, encoding='utf-8')
            review = mechanical_review(ROOT, task, artifacts, root / 'captures')
            for decision in review['decisions']:
                decision['applied_to'] = [{'artifact': 'review.md', 'text': artifacts['review.md']}]
            (root / 'task.json').write_text(json.dumps(task), encoding='utf-8')
            (root / 'review.json').write_text(json.dumps(review), encoding='utf-8')
            manifest = {'audit_format': 'final-delivery-audit/v1', 'kind': 'text',
                        'task': 'task.json', 'artifacts': list(artifacts), 'review': 'review.json',
                        'capture_root': 'captures', 'session': 'mechanical-test-session'}
            (root / 'audit.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertFalse(audit_manifest(root / 'audit.json')['delivery_ready'])

    def test_required_check_cannot_be_silently_ignored(self):
        task = {'delivery': {'required_checks': ['shotlist']}}
        self.assertIn('shotlist', derive(task, 'text')['required_checks'])

    def test_nested_task_target_cannot_be_overridden_by_a_contract(self):
        task = {'delivery': {'project_uuid': 'P_USER'}}
        contract = derive(task, 'canvas')
        contract['project_uuid'] = 'P_OTHER'
        self.assertEqual(validate(contract, task, 'canvas', 'P_OTHER', [])['status'], 'BLOCKED')

    def test_explicit_delivery_endpoint_cannot_be_downgraded(self):
        task = {'delivery': {'endpoint': 'film'}}
        self.assertEqual(validate(derive({}, 'text'), task, 'text', None, [])['status'], 'BLOCKED')

    def test_declared_artifact_directory_is_significant(self):
        contract = derive({'delivery': {'required_artifacts': ['final/report.md']}}, 'text')
        self.assertEqual(validate(contract, {}, 'text', None, ['draft/report.md'])['status'], 'BLOCKED')

    def test_external_film_review_needs_no_fictional_canvas_target(self):
        contract = derive({}, 'film')
        contract['exemptions'] = [{'check': 'canvas', 'reason': '审阅用户提供的本地成片，没有画布'}]
        self.assertEqual(validate(contract, {}, 'film', None, ['clip.mp4'])['status'], 'PASS')

    def test_reference_and_negative_file_mentions_are_not_required_outputs(self):
        for text in ('参考 style.md，交付 review.md', '不要交付 style.md，交付 review.md'):
            task = {'requirements': [{'id': 'R1', 'text': text}]}
            names = {item['name'] for item in derive(task, 'text')['required_artifacts']}
            self.assertEqual(names, {'review.md'})

    def test_contract_reason_cannot_waive_an_explicit_task_check(self):
        task = {'delivery': {'required_checks': ['canvas']}}
        contract = derive(task, 'text')
        contract['exemptions'] = [{'check': 'canvas', 'reason': 'Skip it'}]
        self.assertEqual(validate(contract, task, 'text', None, [])['status'], 'BLOCKED')


class FinalPromotionIntegrityTests(unittest.TestCase):
    def test_record_serialization_is_stable_across_process_hash_seeds(self):
        code = ("import json; from scripts.production_records import _sync_node; "
                "node={'id':'n1'}; record={'record_id':'n1','version':1,'source_version':1,"
                "'source_revision':'r1','state':'graph_plan_ready','review_status':'NOT_VERIFIED'}; "
                "_sync_node(node,record); print(json.dumps(node))")
        outputs = []
        for seed in ('1', '2'):
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8='1'),
                capture_output=True, text=True, encoding='utf-8', check=True)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_a_report_with_only_success_labels_is_not_execution_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / '13_Final_Prompt.pending.md'
            pending.write_text('Candidate', encoding='utf-8')
            digest = hashlib.sha256(pending.read_bytes()).hexdigest()
            names = ['delivery_contract_scope_and_target', 'actual_files_and_scope',
                     'current_task_sources_and_decisions', 'inputs_unchanged_at_end']
            report = {'audit_format': 'final-delivery-audit/v1', 'status': 'PASS',
                      'delivery_ready': True, 'checks': [{'name': name, 'status': 'PASS'} for name in names],
                      'inputs': {str(pending): digest}}
            report_path = root / 'audit.json'
            report_path.write_text(json.dumps(report), encoding='utf-8')
            result = _final_audit_gate(report_path, pending, root / '13_Final_Prompt.md', digest)
            self.assertEqual(result['status'], 'BLOCKED')


class CanvasScopeAndGeometryTests(unittest.TestCase):
    def test_wrapped_node_details_support_reference_and_media_readback(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['shots'] = [{'id': 'S1', 'prompt': 'Shot', 'reference_plan': {
            'assets': ['A'], 'primary_asset_id': 'A', 'prompt_refs': ['{{Image 1}}']}}]
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            canvas.apply(doc, apply_options())
        cli.nodes['id-1']['data'] = {'url': ['https://fixture.invalid/a.png']}
        def wrapped(args):
            code, result = cli(args)
            if args[0] == 'node' and args[1] != 'list':
                return code, {'nodes': [result]}
            return code, result
        with patch.object(canvas, '_run', side_effect=wrapped), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.audit_canvas('P', doc, strict_effective=True), 0)

    def test_invalid_declared_footprints_block_before_writing(self):
        for position in ({'x': True, 'y': 0}, {'x': 0, 'y': 0, 'w': 0, 'h': 10},
                         {'x': 0, 'y': 0, 'w': None, 'h': 10}):
            doc = prop_document()
            doc['assets'][0]['position'] = position
            with self.subTest(position=position), patch.object(canvas, '_run') as cli, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
                cli.assert_not_called()

    def test_typed_settings_are_serialized_as_cli_json(self):
        doc = prop_document()
        doc['assets'][0]['settings'] = {'flag': True, 'options': {'value': 2}}
        commands, _ = canvas.build_commands(doc, 'P')
        self.assertIn('flag=true', commands[0])
        self.assertIn('options={"value":2}', commands[0])

    def test_invalid_or_conflicting_settings_block_before_writing(self):
        for settings in (['wrong'], False, {'imageListOrder': ['foreign']}, {'weight': float('nan')}):
            doc = prop_document()
            doc['assets'][0]['settings'] = settings
            with self.subTest(settings=settings), patch.object(canvas, '_run') as cli, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
                cli.assert_not_called()

    def test_unrelated_existing_nodes_are_outside_a_partial_plan(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            canvas.apply(doc, apply_options())
            cli.nodes['unrelated'] = {'id': 'unrelated', 'name': '其他任务节点',
                                      'type': 'text', 'params': {'prompt': 'Keep'}}
            self.assertEqual(canvas.audit_canvas('P', doc), 0)

    def test_actual_position_must_match_a_declared_position(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['position'] = {'x': 100, 'y': 200}
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            canvas.apply(doc, apply_options())
            cli.nodes['id-1']['position'] = {'x': 999, 'y': 999}
            self.assertEqual(canvas.audit_canvas('P', doc), canvas.RC_FAIL)

    def test_declared_coordinates_reach_the_real_cli_command(self):
        doc = prop_document()
        doc['assets'][0]['position'] = {'x': 100, 'y': 200}
        commands, _ = canvas.build_commands(doc, 'P')
        self.assertIn('--x', commands[0])
        self.assertLess(commands[0].index('--x'), commands[0].index('create'))

    def test_nonfinite_position_cannot_pass_validation(self):
        for value in (float('nan'), float('inf'), 'bad'):
            doc = prop_document()
            doc['assets'][0]['position'] = {'x': value, 'y': 0}
            with self.subTest(value=value), patch.object(canvas, '_run') as cli, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
                cli.assert_not_called()


if __name__ == '__main__':
    unittest.main()
