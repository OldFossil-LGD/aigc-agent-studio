"""Offline regressions for LibTV command ordering, identity and recovery."""
import contextlib
import copy
import io
import subprocess
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import apply_libtv_plan as adapter
from scripts import libtv_canvas_build as canvas


def prop_document(same_name=False):
    return {
        'props': [{'id': 'P1', 'name': 'first'},
                  {'id': 'P2', 'name': 'first' if same_name else 'second'}],
        'assets': [
            {'asset_id': 'A', 'kind': 'prop', 'subject': 'P1', 'role': 'anchor',
             'layer': 1, 'prompt': 'First prop'},
            {'asset_id': 'B', 'kind': 'prop', 'subject': 'P2', 'role': 'anchor',
             'layer': 1, 'prompt': 'Second prop'}],
        'shots': []}


def apply_options(project='P'):
    return SimpleNamespace(project=project, name='offline-test', dry_run=False,
                           apply=True, yes=True, verify=False, strict_effective=False)


class CanvasCLI:
    """Stateful external CLI double. It never calls a real executable."""
    def __init__(self):
        self.nodes = {}
        self.creates = []
        self.calls = []
        self.fail_once = None

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ['node', 'list']:
            return 0, {'nodes': [
                {'id': key, 'name': node['name']} for key, node in self.nodes.items()]}
        if args[:2] == ['node', 'create']:
            name = args[2]
            if name == self.fail_once:
                self.fail_once = None
                return 1, {'_raw': 'synthetic interrupted request'}
            key = 'id-' + str(len(self.nodes) + 1)
            prompt = args[args.index('--prompt') + 1] if '--prompt' in args else None
            params = {'prompt': prompt}
            for i, arg in enumerate(args):
                if arg == '-s':
                    setting, value = args[i + 1].split('=', 1)
                    params[setting] = value
            sources = [args[i + 1] for i, arg in enumerate(args) if arg == '--left']
            params['imageListOrder'] = [next(k for k, n in self.nodes.items() if n['name'] == source)
                                        for source in sources]
            self.nodes[key] = {'id': key, 'name': name, 'type': args[args.index('-t') + 1],
                               'params': params}
            self.creates.append(name)
            return 0, {'nodeKey': key}
        if args[0] == 'node':
            selected = [node for key, node in self.nodes.items()
                        if args[1] in (key, node['name'])]
            if len(selected) == 1:
                return 0, copy.deepcopy(selected[0])
            return 1, {'_raw': 'missing or ambiguous node'}
        raise AssertionError('Unexpected CLI operation: ' + repr(args))


class ReferenceIntegrityTests(unittest.TestCase):
    def test_multiple_incoming_references_survive_all_execution_phases(self):
        plan = {'commands': [
            {'kind': 'node_create', 'name': 'A', 'node_type': 'image'},
            {'kind': 'node_create', 'name': 'B', 'node_type': 'image'},
            {'kind': 'node_create', 'name': 'V', 'node_type': 'video'},
            {'kind': 'node_link', 'target': 'V', 'left': 'A'},
            {'kind': 'node_link', 'target': 'V', 'left': 'B'}]}
        phases = adapter.build_phases(plan, 'P')
        references = {}
        for command in phases['nodes'] + phases['links'] + phases['links']:
            sources = [command[i + 1] for i, arg in enumerate(command) if arg == '--left']
            target = command[command.index('create') + 1] if 'create' in command else command[2]
            references[target] = sources
        self.assertEqual(references['V'], ['A', 'B'])


class CanvasIdentityTests(unittest.TestCase):
    def test_same_display_names_have_stable_distinct_bindings(self):
        doc = prop_document(same_name=True)
        commands, bindings = canvas.build_commands(doc, 'P')
        self.assertEqual(len(set(bindings.values())), 2)
        self.assertEqual({c[2] for c in commands}, set(bindings.values()))
        doc['assets'].reverse()
        self.assertEqual(canvas.build_commands(doc, 'P')[1], bindings)

    def test_existing_unambiguous_display_names_are_preserved(self):
        self.assertEqual(canvas.build_commands(prop_document(), 'P')[1],
                         {'A': '资产_first_主图', 'B': '资产_second_主图'})

    def test_malformed_identifiers_are_rejected_before_command_generation(self):
        for value in (None, '', ' ', True, 1):
            doc = prop_document()
            doc['assets'][0]['asset_id'] = value
            with self.subTest(value=value):
                try:
                    errors, _ = canvas.validate(doc)
                except (TypeError, AttributeError) as exc:
                    self.fail('Invalid identity escaped validation: ' + str(exc))
                self.assertTrue(errors)
                with self.assertRaises(ValueError):
                    canvas.build_commands(doc, 'P')

    def test_falsey_non_list_collections_are_rejected(self):
        for value in (False, 0, "", {}):
            doc = prop_document()
            doc["assets"] = value
            with self.subTest(value=value):
                self.assertTrue(canvas.validate(doc)[0])
                with self.assertRaises(ValueError):
                    canvas.build_commands(doc, "P")

    def test_duplicate_asset_ids_are_rejected_before_commands(self):
        doc = prop_document()
        doc['assets'][1]['asset_id'] = 'A'
        self.assertTrue(canvas.validate(doc)[0])
        with self.assertRaises(ValueError):
            canvas.build_commands(doc, 'P')

    def test_duplicate_shot_ids_are_rejected(self):
        doc = prop_document()
        shot = {'id': 'S1', 'prompt': 'Shot', 'reference_plan': {
            'assets': ['A'], 'primary_asset_id': 'A', 'prompt_refs': ['{{Image 1}}']}}
        doc['shots'] = [shot, copy.deepcopy(shot)]
        self.assertTrue(canvas.validate(doc)[0])

    def test_assets_without_shots_must_still_exist_on_canvas(self):
        with patch.object(canvas, '_run', return_value=(0, {'nodes': []})), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.verify('P', prop_document()), canvas.RC_FAIL)

    def test_duplicate_inventory_names_cannot_pass_verification(self):
        inventory = {'nodes': [{'id': '1', 'name': '资产_first_主图'},
                               {'id': '2', 'name': '资产_first_主图'},
                               {'id': '3', 'name': '资产_second_主图'}]}
        with patch.object(canvas, '_run', return_value=(0, inventory)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.verify('P', prop_document()), canvas.RC_FAIL)

    def test_malformed_inventory_is_a_failed_verification(self):
        for inventory in ({}, {'nodes': 'bad'}, {'nodes': [{}]}):
            with self.subTest(inventory=inventory), \
                    patch.object(canvas, '_run', return_value=(0, inventory)), \
                    contextlib.redirect_stdout(io.StringIO()):
                try:
                    code = canvas.verify('P', prop_document())
                except (KeyError, TypeError, AttributeError) as exc:
                    self.fail('Malformed inventory escaped validation: ' + str(exc))
                self.assertEqual(code, canvas.RC_FAIL)


class CanvasRecoveryTests(unittest.TestCase):
    def test_retry_skips_nodes_with_verified_matching_parameters(self):
        cli = CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options()), 0)
            self.assertEqual(canvas.apply(prop_document(), apply_options()), 0)
        self.assertEqual(cli.creates, ['资产_first_主图', '资产_second_主图'])
        self.assertEqual(len(cli.nodes), 2)

    def test_partial_failure_can_resume_without_duplicate_nodes(self):
        cli = CanvasCLI()
        cli.fail_once = '资产_second_主图'
        with patch.object(canvas, '_run', side_effect=cli), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options()), canvas.RC_FAIL)
            self.assertEqual(canvas.apply(prop_document(), apply_options()), 0)
        self.assertEqual(cli.creates, ['资产_first_主图', '资产_second_主图'])

    def test_existing_parameter_mismatch_stops_before_new_writes(self):
        cli = CanvasCLI()
        cli.nodes['existing'] = {'id': 'existing', 'name': '资产_first_主图',
                                  'type': 'image', 'params': {'prompt': 'Foreign prompt'}}
        with patch.object(canvas, '_run', side_effect=cli), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options()), canvas.RC_FAIL)
        self.assertEqual(cli.creates, [])

    def test_nested_node_parameters_are_supported_when_resuming(self):
        cli = CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options()), 0)
            for node in cli.nodes.values():
                node['data'] = {'params': node.pop('params')}
            self.assertEqual(canvas.apply(prop_document(), apply_options()), 0)
        self.assertEqual(len(cli.creates), 2)

    def test_resuming_with_changed_parent_reference_stops_all_writes(self):
        doc = prop_document()
        doc['assets'][1].update(role='closeup', layer=2, parent='A')
        cli = CanvasCLI()
        with patch.object(canvas, '_run', side_effect=cli), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(doc, apply_options()), 0)
            cli.nodes['id-2']['params']['imageListOrder'] = []
            self.assertEqual(canvas.apply(doc, apply_options()), canvas.RC_FAIL)
        self.assertEqual(len(cli.creates), 2)

    def test_failed_canvas_creation_cannot_use_stale_project_identifier(self):
        calls = []
        def failed_create(args):
            calls.append(list(args))
            if args[:2] == ['project', 'list']:
                return 0, {'projects': []}
            if args[:2] == ['project', 'create']:
                return 1, {'projectMeta': {'uuid': 'stale-project'}}
            return 0, {'nodeKey': 'unexpected-node'}
        with patch.object(canvas, '_run', side_effect=failed_create), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options(None)), canvas.RC_FAIL)
        self.assertTrue(all(args[0] != 'node' for args in calls))

    def test_invalid_created_node_identifier_stops_execution(self):
        def invalid_key(args):
            if args[:2] == ['node', 'list']:
                return 0, {'nodes': []}
            return 0, {'nodeKey': True}
        with patch.object(canvas, '_run', side_effect=invalid_key), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(prop_document(), apply_options()), canvas.RC_FAIL)

    def test_connection_failure_precedes_creating_new_canvas(self):
        calls = []
        def unavailable(args):
            calls.append(list(args))
            return 1, {'_raw': 'authentication required'}
        with patch.object(canvas, '_run', side_effect=unavailable), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(canvas.apply(prop_document(), apply_options(None)), 0)
        self.assertTrue(calls)
        self.assertTrue(all('create' not in args for args in calls))


class CLIEnvironmentTests(unittest.TestCase):
    def test_cli_cannot_consume_parent_stdin_as_reference_edges(self):
        result = SimpleNamespace(returncode=0, stdout=b'{"nodes": []}', stderr=b'')
        with patch.object(canvas.subprocess, 'run', return_value=result) as child:
            canvas._run(['node', 'list', '-p', 'P'])
        self.assertEqual(child.call_args.kwargs.get('stdin'), subprocess.DEVNULL)

    def test_missing_cli_is_explained_at_normal_apply_entrypoint(self):
        script = Path(adapter.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'plan.json'
            source.write_text(json.dumps({'commands': []}), encoding='utf-8')
            env = dict(os.environ, LIBTV_BIN=str(Path(directory) / 'missing-libtv'),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            command = [sys.executable, str(script), str(source), '--project-uuid', 'P']
            dry_run = subprocess.run(command, env=env, capture_output=True, text=True,
                                     encoding="utf-8")
            self.assertEqual(dry_run.returncode, 0)
            execution = subprocess.run(command + ['--execute'], env=env,
                                       capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(execution.returncode, 3)
            self.assertNotIn('Traceback', execution.stderr)

    def test_adapter_writes_cannot_consume_inherited_reference_input(self):
        result = SimpleNamespace(returncode=0, stdout=b'{}', stderr=b'')
        with patch.object(adapter.subprocess, 'run', return_value=result) as child:
            adapter._run(['libtv', 'node', 'V', '--left', 'A'], {'writes': 0}, 'writes')
        self.assertEqual(child.call_args.kwargs.get('stdin'), subprocess.DEVNULL)

    def test_missing_cli_and_timeouts_return_environment_failures(self):
        for error in (FileNotFoundError('synthetic missing CLI'),
                      subprocess.TimeoutExpired('libtv', 1)):
            with self.subTest(error=type(error).__name__), \
                    patch.object(canvas.subprocess, 'run', side_effect=error):
                try:
                    code, response = canvas._run(['node', 'list', '-p', 'P'])
                except (OSError, subprocess.TimeoutExpired) as exc:
                    self.fail('CLI failure escaped the execution boundary: ' + str(exc))
                self.assertNotEqual(code, 0)
                self.assertIn('_raw', response)


if __name__ == '__main__':
    unittest.main()
