"""The final firewall must inspect actual files and platform readbacks."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import libtv_canvas_build as canvas
from tests.test_libtv_execution_integrity import CanvasCLI, prop_document, apply_options


class CanvasFinalAuditTests(unittest.TestCase):
    def test_whitespace_or_nontext_prompt_cannot_enter_canvas(self):
        for value in (' ', '\n\t', True, 123, ['prompt']):
            doc = prop_document()
            doc['assets'][0]['prompt'] = value
            with self.subTest(value=value):
                self.assertTrue(canvas.validate(doc)[0])

    def test_final_audit_detects_post_creation_prompt_loss(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
            cli.nodes['id-1']['params']['prompt'] = ''
            self.assertEqual(canvas.audit_canvas('P', doc), canvas.RC_FAIL)

    def test_complete_canvas_passes_without_generation(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            canvas.apply(doc, apply_options())
            self.assertEqual(canvas.audit_canvas('P', doc), 0)
        self.assertFalse(any('run' in call for call in cli.calls))

    def test_declared_model_and_ratio_must_match_the_node(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0].update(model='EXPECTED', settings={'ratio': '9:16'})
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
            self.assertEqual(canvas.audit_canvas('P', doc), 0)
            cli.nodes['id-1']['params'].update(model='WRONG', settings={'ratio': '16:9'})
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                self.assertEqual(canvas.audit_canvas('P', doc), canvas.RC_FAIL)
        self.assertRegex(log.getvalue(), '参数与计划不一致|mismatch')

    def test_canvas_edited_during_the_audit_is_rejected(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
        state = {'lists': 0}

        def drifting(args):
            if args[:2] == ['node', 'list']:
                state['lists'] += 1
                if state['lists'] == 3:
                    cli.nodes['id-1']['params']['prompt'] = 'CHANGED AFTER PARAMETER CHECK'
            return cli(args)

        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=drifting), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.audit_canvas('P', doc), canvas.RC_FAIL)
        self.assertIn('审计期间平台内容发生变化', log.getvalue())

    def test_unsupported_plan_field_blocks_the_audit(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['group'] = 'G1'
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.audit_canvas('P', doc), canvas.RC_FAIL)
        self.assertIn('无法核对的字段', log.getvalue())

    def test_shot_referencing_a_shot_blocks_before_writing(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['shots'] = [{'id': 'S1', 'prompt': 'p1', 'reference_plan': {'assets': ['A']}},
                        {'id': 'S2', 'prompt': 'p2', 'reference_plan': {'assets': ['S1']}}]
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.nodes, {})
        self.assertIn('S1', log.getvalue())

    def test_dangling_parent_blocks_before_writing(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][1]['parent'] = 'MISSING'
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.nodes, {})

    def test_overlapping_positions_block_before_writing(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['position'] = {'x': 0, 'y': 0, 'w': 100, 'h': 100}
        doc['assets'][1]['position'] = {'x': 50, 'y': 50, 'w': 100, 'h': 100}
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.nodes, {})
        self.assertIn('节点位置重合', log.getvalue())

    def test_separated_positions_are_accepted(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['position'] = {'x': 0, 'y': 0, 'w': 100, 'h': 100}
        doc['assets'][1]['position'] = {'x': 200, 'y': 0, 'w': 100, 'h': 100}
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
            self.assertEqual(canvas.audit_canvas('P', doc), 0)

    def test_unrelated_nodes_on_the_canvas_remain_out_of_scope(self):
        doc, cli = prop_document(), CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
            cli.nodes['id-x'] = {'id': 'id-x', 'name': '补充节点', 'type': 'image',
                                 'params': {'prompt': 'stray'}}
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                self.assertEqual(canvas.audit_canvas('P', doc), 0)

    def test_unsupported_plan_field_blocks_before_writing(self):
        doc, cli = prop_document(), CanvasCLI()
        doc['assets'][0]['group'] = 'G1'
        log = io.StringIO()
        with patch.object(canvas, '_run', side_effect=cli), contextlib.redirect_stdout(log):
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.nodes, {})
        self.assertIn('不写画布', log.getvalue())

    def test_empty_plan_is_not_a_successful_audit(self):
        with patch.object(canvas, '_run') as cli, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.audit_canvas('P', {'assets': [], 'shots': []}), canvas.RC_FAIL)
        cli.assert_not_called()


class FinalFirewallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = {'goal': '检查杯子的最终归属是否明确', 'profile': 'rework',
                     'requirements': [{'id': 'R1', 'text': '杯子最终由谁持有'}]}
        (self.root / 'task.json').write_text(json.dumps(self.task, ensure_ascii=False), encoding='utf-8')
        (self.root / 'review.md').write_text('杯子最终仍在原持有者手中，隔着完整玻璃无法完成交接。', encoding='utf-8')
        self.manifest = {'audit_format': 'final-delivery-audit/v1', 'kind': 'text',
                         'task': 'task.json', 'artifacts': ['review.md'], 'review': 'review.json',
                         'capture_root': 'captures', 'session': 'mechanical-test-session'}

    def tearDown(self):
        self.temp.cleanup()

    def audit(self):
        from scripts.final_delivery_audit import audit_manifest
        path = self.root / 'audit.json'
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return audit_manifest(path)

    def write_contract(self, **overrides):
        contract = {'contract_format': 'delivery-contract/v1', 'endpoint': self.manifest['kind'],
                    'required_artifacts': [], 'required_checks': [], 'exemptions': []}
        contract.update(overrides)
        (self.root / 'contract.json').write_text(json.dumps(contract, ensure_ascii=False), encoding='utf-8')
        self.manifest['contract'] = 'contract.json'
        return contract

    def add_review(self):
        from tests.review_fixture import mechanical_review
        capture = self.root / 'captures'
        capture.mkdir()
        artifacts = {Path(path).name: (self.root / path).read_text(encoding='utf-8')
                     for path in self.manifest['artifacts']}
        review = mechanical_review(Path(__file__).resolve().parents[1], self.task, artifacts, capture)
        (self.root / 'review.json').write_text(json.dumps(review), encoding='utf-8')

    def test_missing_evidence_blocks_delivery(self):
        result = self.audit()
        self.assertFalse(result['delivery_ready'])

    def test_current_actual_text_and_evidence_pass(self):
        self.add_review()
        result = self.audit()
        self.assertTrue(result['delivery_ready'], result)
        self.assertFalse(result['generation_authorized'])

    def test_placeholder_paragraph_blocks_the_delivery(self):
        (self.root / 'review.md').write_text(
            '# 杯子归属审阅\n杯子最终仍在原持有者手中。\n## 空间分析\nTODO\n## 结论\n待补充实际判断。',
            encoding='utf-8')
        self.add_review()
        result = self.audit()
        self.assertFalse(result['delivery_ready'])
        blocked = [item for item in result['checks'] if item['name'] == 'actual_files_and_scope'][0]
        self.assertIn('Unfinished section', str(blocked.get('error', '')))

    def test_changed_artifact_invalidates_review(self):
        self.add_review()
        (self.root / 'review.md').write_text('Changed output', encoding='utf-8')
        self.assertFalse(self.audit()['delivery_ready'])

    def test_missing_empty_duplicate_or_placeholder_artifacts_block(self):
        for paths, text in [([], 'valid'), (['missing.md'], 'valid'),
                            (['review.md', 'review.md'], 'valid'),
                            (['review.md'], '  '), (['review.md'], 'TODO')]:
            self.manifest['artifacts'] = paths
            (self.root / 'review.md').write_text(text, encoding='utf-8')
            self.assertFalse(self.audit()['delivery_ready'])

    def test_unknown_endpoint_and_incomplete_canvas_or_film_block(self):
        for kind in ('unknown', 'canvas', 'film'):
            self.manifest['kind'] = kind
            self.assertFalse(self.audit()['delivery_ready'])

    def test_prompt_task_cannot_be_relabelled_as_text(self):
        task = json.loads((Path(__file__).resolve().parents[1] / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        (self.root / 'task.json').write_text(json.dumps(task), encoding='utf-8')
        self.assertFalse(self.audit()['delivery_ready'])

    def test_inputs_changed_during_review_cannot_pass(self):
        (self.root / 'review.json').write_text('{}', encoding='utf-8')
        def mutate(*args, **kwargs):
            (self.root / 'review.md').write_text('Changed during audit', encoding='utf-8')
            return {'delivery_ready': True}
        with patch('scripts.final_delivery_audit.evaluate_delivery_review', side_effect=mutate):
            result = self.audit()
        self.assertFalse(result['delivery_ready'])
        self.assertEqual(result['checks'][-1]['name'], 'inputs_unchanged_at_end')

    def test_real_prompt_package_passes_and_tampering_is_blocked(self):
        from scripts.compile_intent_delivery import compile_intent_delivery
        package_root = Path(__file__).resolve().parents[1]
        self.task = json.loads((package_root / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
        (self.root / 'task.json').write_text(json.dumps(self.task), encoding='utf-8')
        compile_intent_delivery(self.task, self.root / 'prompt', draft=True)
        names = ['01_production_contract.json', '02_asset_graph_plan.json',
                 '03_shot_graph_plan.json', '04_prompt_packages.jsonl', '13_Draft_Prompt.md']
        self.manifest.update(kind='prompt', prompt_dir='prompt',
                             prompt_markdown='prompt/13_Draft_Prompt.md',
                             grill=str(package_root / 'samples/grill_ledger_papercut_prompt.json'),
                             artifacts=['prompt/' + name for name in names])
        self.add_review()
        checked = self.audit()
        self.assertTrue(checked['delivery_ready'], checked)
        (self.root / 'prompt/04_prompt_packages.jsonl').write_text('', encoding='utf-8')
        self.assertFalse(self.audit()['delivery_ready'])

    def test_zero_exit_without_media_qc_pass_is_blocked(self):
        self.manifest.update(kind='film', video='clip.mp4', media_record='record.json',
                             media_review='media-review.json', artifacts=['clip.mp4'])
        (self.root / 'clip.mp4').write_bytes(b'synthetic media fixture')
        for name in ('review.json', 'record.json', 'media-review.json'):
            (self.root / name).write_text('{}', encoding='utf-8')
        with patch('scripts.final_delivery_audit.evaluate_delivery_review', return_value={'delivery_ready': True}), \
                patch('scripts.final_delivery_audit.run_gate', return_value=(0, {'raw': 'unparsed'})), \
                patch('scripts.final_delivery_audit.verify_review_binding', return_value={'status': 'PASS'}):
            self.assertFalse(self.audit()['delivery_ready'])

    def test_video_fingerprint_does_not_load_entire_film_into_memory(self):
        self.manifest.update(kind='film', video='clip.mp4', media_record='record.json',
                             media_review='media-review.json', artifacts=['clip.mp4'])
        self.manifest['project'] = 'P_MEDIA'
        self.write_contract(project_uuid='P_MEDIA',
                            exemptions=[{'check': 'canvas', 'reason': 'Media-only fixture; no canvas in this delivery'}])
        video = self.root / 'clip.mp4'
        video.write_bytes(b'synthetic media fixture')
        for name in ('review.json', 'record.json', 'media-review.json'):
            (self.root / name).write_text('{}', encoding='utf-8')
        original = Path.read_bytes
        def bounded_read(path):
            if path == video:
                raise AssertionError('Whole-film byte read')
            return original(path)
        with patch.object(Path, 'read_bytes', bounded_read), \
                patch('scripts.final_delivery_audit.evaluate_delivery_review', return_value={'delivery_ready': True}), \
                patch('scripts.final_delivery_audit.run_gate', return_value=(0, {'status': 'PASS'})), \
                patch('scripts.final_delivery_audit.verify_review_binding', return_value={'status': 'PASS'}):
            self.assertTrue(self.audit()['delivery_ready'])


class DeliveryContractScopeTests(unittest.TestCase):
    """Regression tests for the F2 counterexamples: scope and target must bind to the task."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = {'goal': '交付报告和排镜表', 'profile': 'rework',
                     'requirements': [{'id': 'R1', 'text': '交付杯子归属审阅报告'},
                                      {'id': 'R2', 'text': '交付完整排镜表 shotlist.md'}]}
        (self.root / 'task.json').write_text(json.dumps(self.task, ensure_ascii=False), encoding='utf-8')
        (self.root / 'review.md').write_text('杯子最终由原持有者拿着，隔着完整玻璃无法完成交接。', encoding='utf-8')
        self.manifest = {'audit_format': 'final-delivery-audit/v1', 'kind': 'text',
                         'task': 'task.json', 'artifacts': ['review.md'], 'review': 'review.json',
                         'capture_root': 'captures', 'session': 'mechanical-test-session'}

    def tearDown(self):
        self.temp.cleanup()

    def audit(self):
        from scripts.final_delivery_audit import audit_manifest
        path = self.root / 'audit.json'
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return audit_manifest(path)

    def add_review(self):
        from tests.review_fixture import mechanical_review
        capture = self.root / 'captures'
        capture.mkdir(exist_ok=True)
        artifacts = {Path(path).name: (self.root / path).read_text(encoding='utf-8')
                     for path in self.manifest['artifacts']}
        review = mechanical_review(Path(__file__).resolve().parents[1], self.task, artifacts, capture)
        (self.root / 'review.json').write_text(json.dumps(review), encoding='utf-8')

    def contract_check(self, result):
        return next(item for item in result['checks'] if item['name'] == 'delivery_contract_scope_and_target')

    def test_requirement_naming_a_file_makes_it_required(self):
        self.add_review()
        result = self.audit()
        detail = self.contract_check(result)['detail']
        self.assertEqual(detail['status'], 'BLOCKED')
        self.assertIn('shotlist.md', ' '.join(detail['errors']))
        self.assertFalse(result['delivery_ready'])

    def test_declaring_the_required_delivery_clears_the_block(self):
        self.add_review()
        (self.root / 'shotlist.md').write_text('镜1 特写 杯子；镜2 过肩 交接。', encoding='utf-8')
        self.manifest['artifacts'] = ['review.md', 'shotlist.md']
        self.add_review()
        self.assertEqual(self.contract_check(self.audit())['detail']['status'], 'PASS')

    def test_explicit_contract_cannot_drop_a_stated_requirement(self):
        contract = {'contract_format': 'delivery-contract/v1', 'endpoint': 'text',
                    'required_artifacts': [], 'required_checks': ['review'], 'exemptions': []}
        (self.root / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')
        self.manifest['contract'] = 'contract.json'
        self.add_review()
        detail = self.contract_check(self.audit())['detail']
        self.assertEqual(detail['status'], 'BLOCKED')
        self.assertIn('shotlist.md', ' '.join(detail['errors']))

    def test_contract_may_add_scope_beyond_the_task(self):
        contract = {'contract_format': 'delivery-contract/v1', 'endpoint': 'text',
                    'required_artifacts': [{'name': 'review.md', 'requirement_ids': ['R1']},
                                           {'name': 'shotlist.md', 'requirement_ids': ['R2']}],
                    'required_checks': ['review'], 'exemptions': []}
        (self.root / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')
        self.manifest['contract'] = 'contract.json'
        (self.root / 'shotlist.md').write_text('镜1 特写 杯子；镜2 过肩 交接。', encoding='utf-8')
        self.manifest['artifacts'] = ['review.md', 'shotlist.md']
        self.add_review()
        self.assertEqual(self.contract_check(self.audit())['detail']['status'], 'PASS')

    def test_contract_endpoint_must_match_audited_kind(self):
        contract = {'contract_format': 'delivery-contract/v1', 'endpoint': 'film',
                    'required_artifacts': [], 'required_checks': [], 'exemptions': []}
        (self.root / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')
        self.manifest['contract'] = 'contract.json'
        self.add_review()
        detail = self.contract_check(self.audit())['detail']
        self.assertEqual(detail['status'], 'BLOCKED')
        self.assertTrue(any('endpoint' in error for error in detail['errors']))

    def test_audited_project_must_be_the_task_target(self):
        self.task['project_uuid'] = 'P_USER'
        (self.root / 'task.json').write_text(json.dumps(self.task), encoding='utf-8')
        self.manifest.update(kind='canvas', project='P_OTHER', artifacts=['review.md'])
        self.add_review()
        detail = self.contract_check(self.audit())['detail']
        self.assertEqual(detail['status'], 'BLOCKED')
        self.assertIn('P_OTHER', ' '.join(detail['errors']))

    def test_film_cannot_skip_the_canvas_silently(self):
        self.task['project_uuid'] = 'P_MEDIA'
        self.task['requirements'] = [{'id': 'R1', 'text': '检查成片的技术和画布绑定'}]
        (self.root / 'task.json').write_text(json.dumps(self.task), encoding='utf-8')
        self.manifest.update(kind='film', video='clip.mp4', media_record='record.json',
                             media_review='media-review.json', artifacts=['clip.mp4'], project='P_MEDIA')
        (self.root / 'clip.mp4').write_bytes(b'synthetic media fixture')
        for name in ('review.json', 'record.json', 'media-review.json'):
            (self.root / name).write_text('{}', encoding='utf-8')
        with patch('scripts.final_delivery_audit.evaluate_delivery_review', return_value={'delivery_ready': True}), \
                patch('scripts.final_delivery_audit.run_gate', return_value=(0, {'status': 'PASS'})), \
                patch('scripts.final_delivery_audit.verify_review_binding', return_value={'status': 'PASS'}):
            result = self.audit()
        canvas_check = next(item for item in result['checks']
                            if item['name'] == 'actual_canvas_nodes_parameters_and_references')
        self.assertEqual(canvas_check['status'], 'BLOCKED')

    def test_exemption_without_a_reason_is_still_blocked(self):
        contract = {'contract_format': 'delivery-contract/v1', 'endpoint': 'text',
                    'required_artifacts': [], 'required_checks': ['review'],
                    'exemptions': [{'check': 'review', 'reason': '  '}]}
        (self.root / 'contract.json').write_text(json.dumps(contract), encoding='utf-8')
        self.manifest['contract'] = 'contract.json'
        self.add_review()
        detail = self.contract_check(self.audit())['detail']
        self.assertEqual(detail['status'], 'BLOCKED')
        self.assertTrue(any('reason' in error for error in detail['errors']))


class FinalPromotionGateTests(unittest.TestCase):
    """F1: a formal entry may not promote a Final that no audit covers."""

    def setUp(self):
        from scripts.compile_intent_delivery import _final_audit_gate
        from scripts.delivery_review import task_fingerprint
        self.task = {'goal': 'Unit test fixture'}
        self.task_hash = task_fingerprint(self.task)
        self.gate = lambda *args: _final_audit_gate(*args, task=self.task)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pending = self.root / '13_Final_Prompt.pending.md'
        self.final = self.root / '13_Final_Prompt.md'
        self.body = '# 最终提示词（可直接复制投喂）\n\n正文字节\n'
        self.pending.write_text(self.body, encoding='utf-8')
        import hashlib
        self.digest = hashlib.sha256(self.pending.read_bytes()).hexdigest()
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text('{}', encoding='utf-8')
        # Dependency-isolated gate tests. BoundReviewTests exercises the real
        # manifest, receipt, revalidation and promotion flow without this stub.
        self.revalidation = patch('scripts.final_delivery_audit.audit_manifest', side_effect=lambda _: self.payload)
        self.revalidation.start()
        self.addCleanup(self.revalidation.stop)

    def tearDown(self):
        self.temp.cleanup()

    def report(self, **overrides):
        from scripts.compile_intent_delivery import REQUIRED_FINAL_CHECKS
        names = sorted(REQUIRED_FINAL_CHECKS)
        payload = {'audit_format': 'final-delivery-audit/v1', 'status': 'PASS',
                   'delivery_ready': True,
                   'kind': 'prompt', 'manifest': str(self.manifest), 'task_sha256': self.task_hash,
                   'checks': [{'name': name, 'status': 'PASS'} for name in names],
                   'inputs': {str(self.pending.resolve()): self.digest}}
        payload.update(overrides)
        self.payload = payload
        path = self.root / 'audit.json'
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def test_no_report_blocks_the_final(self):
        result = self.gate(None, self.pending, self.final, self.digest)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'FINAL_AUDIT_REQUIRED')

    def test_report_covering_these_bytes_permits_the_final(self):
        result = self.gate(self.report(), self.pending, self.final, self.digest)
        self.assertEqual(result['status'], 'PASS', result)

    def test_failing_report_blocks_the_final(self):
        result = self.gate(self.report(delivery_ready=False), self.pending, self.final, self.digest)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'FINAL_AUDIT_NOT_PASSING')

    def test_stale_report_blocks_the_final(self):
        other = self.report(inputs={str(self.pending.resolve()): 'a' * 64})
        result = self.gate(other, self.pending, self.final, self.digest)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'FINAL_AUDIT_DOES_NOT_COVER_THESE_BYTES')

    def test_bare_flag_report_is_not_enough(self):
        bare = self.report(checks=[], status='PASS')
        result = self.gate(bare, self.pending, self.final, self.digest)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['reason'], 'FINAL_AUDIT_INCOMPLETE')
        missing = self.report(checks=[{'name': 'actual_files_and_scope', 'status': 'PASS'}])
        self.assertEqual(self.gate(missing, self.pending, self.final, self.digest)['status'], 'BLOCKED')
        failing = self.report(checks=[{'name': 'delivery_contract_scope_and_target', 'status': 'BLOCKED'},
                                      {'name': 'actual_files_and_scope', 'status': 'PASS'},
                                      {'name': 'current_task_sources_and_decisions', 'status': 'PASS'},
                                      {'name': 'inputs_unchanged_at_end', 'status': 'PASS'}])
        self.assertEqual(self.gate(failing, self.pending, self.final, self.digest)['status'], 'BLOCKED')

    def test_rewritten_candidate_is_no_longer_covered(self):
        report = self.report()
        self.pending.write_text(self.body + '追加内容', encoding='utf-8')
        import hashlib
        changed = hashlib.sha256(self.pending.read_bytes()).hexdigest()
        result = self.gate(report, self.pending, self.final, changed)
        self.assertEqual(result['status'], 'BLOCKED')

    def test_stale_supporting_input_blocks_promotion(self):
        import hashlib
        source = self.root / 'source.json'
        canonical = self.pending
        alias = self.root / 'path_alias'
        alias.mkdir()
        for pending in (canonical, alias / '..' / canonical.name):
            with self.subTest(pending=pending):
                source.write_bytes(b'original')
                # Real audit reports store resolved paths, including on Windows
                # runners whose temporary directory has a short-path alias.
                report = self.report(inputs={str(pending.resolve()): self.digest,
                                             str(source.resolve()): hashlib.sha256(source.read_bytes()).hexdigest()})
                source.write_bytes(b'changed')
                self.assertEqual(self.gate(report, pending, self.final, self.digest)['reason'],
                                 'FINAL_AUDIT_STALE_INPUTS')

    def test_text_audit_cannot_authorize_prompt_promotion(self):
        report = self.report(kind='text')
        self.assertEqual(self.gate(report, self.pending, self.final, self.digest)['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
