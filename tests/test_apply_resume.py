"""Independent resume checks. Every subprocess is replaced by a fake."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import apply_libtv_plan as adapter


def command():
    return {'kind': 'node_create', 'name': 'stable_name', 'node_type': 'video', 'model': 'Synthetic Model A',
            'mode_type': 'mixed2video', 'settings': {'duration': 8, 'ratio': '16:9'},
            'prompt': 'Synthetic requested prompt', 'run': False}


def detail():
    row = command()
    return {'id': 'stable-id', 'name': row['name'], 'type': row['node_type'],
            'params': {'model': row['model'], 'modeType': row['mode_type'],
                       'settings': copy.deepcopy(row['settings']), 'prompt': row['prompt']}}


def invoke(commands=None, inventory=None, node=None, query_failure=False, execute=True, envelope=False, group_output=None):
    commands = commands if commands is not None else [command()]
    inventory = inventory if inventory is not None else [{'id': 'stable-id', 'name': 'stable_name'}]
    node = detail() if node is None else node
    calls = []
    writes = []

    def fake(args, **kwargs):
        calls.append((list(args), kwargs))
        if args[1:3] == ['group', 'list']:
            body = {'groups': []} if group_output is None else group_output
        elif args[1:3] == ['node', 'list']:
            if query_failure:
                return SimpleNamespace(returncode=1, stdout=b'', stderr=b'synthetic read failure')
            body = {'nodes': inventory}
        elif len(args) == 5 and args[1] == 'node' and args[3] == '-p':
            if args[2] != 'stable-id':
                return SimpleNamespace(returncode=1, stdout=b'', stderr=b'synthetic ID mismatch')
            body = {'nodes': [node]} if envelope else node
        else:
            writes.append(list(args))
            body = {}
        return SimpleNamespace(returncode=0, stdout=json.dumps(body).encode('utf-8'), stderr=b'')

    with tempfile.TemporaryDirectory(prefix='resume-audit-') as temporary:
        plan = Path(temporary) / 'plan.json'
        plan.write_text(json.dumps({'commands': commands}), encoding='utf-8')
        argv = ['apply_libtv_plan.py', str(plan), '--project-uuid', 'synthetic-project']
        if execute:
            argv.append('--execute')
        capture = io.StringIO()
        error = None
        with patch.object(adapter.subprocess, 'run', side_effect=fake), patch.object(sys, 'argv', argv), contextlib.redirect_stdout(capture):
            try:
                code = adapter.main()
            except Exception as exc:
                code, error = None, exc
        text = capture.getvalue()
    return {'code': code, 'error': error, 'calls': calls, 'writes': writes,
            'stats': json.loads(text) if text else None}


class ApplyResumeTests(unittest.TestCase):
    def assertRefused(self, result):
        self.assertIsInstance(result['error'], (ValueError, RuntimeError))
        self.assertEqual(result['writes'], [])

    def test_existing_match_requires_stable_id_readback(self):
        result = invoke()
        self.assertIsNone(result['error'])
        self.assertEqual(result['stats']['nodes_skipped'], 1)
        self.assertTrue(any(args[1:] == ['node', 'stable-id', '-p', 'synthetic-project'] for args, _ in result['calls']))

    def test_single_node_envelope_is_supported(self):
        result = invoke(envelope=True)
        self.assertEqual(result['code'], 0)
        self.assertTrue(any(args[2] == 'stable-id' for args, _ in result['calls'] if len(args) > 2))

    def test_same_name_different_parameter_is_refused(self):
        for field, value in [('model', 'Synthetic Other'), ('modeType', 'text2video'), ('prompt', 'wrong'),
                             ('settings', {'duration': 3, 'ratio': '16:9'})]:
            with self.subTest(field=field):
                observed = detail()
                observed['params'][field] = value
                self.assertRefused(invoke(node=observed))

    def test_wrong_type_or_wrong_readback_id_is_refused(self):
        for field, value in [('id', 'foreign-id'), ('type', 'image')]:
            with self.subTest(field=field):
                observed = detail()
                observed[field] = value
                self.assertRefused(invoke(node=observed))

    def test_readback_name_must_still_match_inventory_name(self):
        for name in ('renamed-node', None):
            with self.subTest(name=name):
                observed = detail()
                observed['name'] = name
                self.assertRefused(invoke(node=observed))

    def test_missing_requested_properties_are_not_defaulted(self):
        for field in ('model', 'modeType', 'settings', 'prompt'):
            with self.subTest(field=field):
                observed = detail()
                observed['params'].pop(field)
                self.assertRefused(invoke(node=observed))

    def test_content_is_compared_when_submitted(self):
        desired = command()
        desired['content'] = ['expected']
        observed = detail()
        observed['content'] = ['wrong']
        self.assertRefused(invoke(commands=[desired], node=observed))
        observed['content'] = ['expected']
        self.assertEqual(invoke(commands=[desired], node=observed)['code'], 0)

    def test_comparison_preserves_json_value_types(self):
        desired = command()
        desired['settings']['count'] = 1
        observed = detail()
        observed['params']['settings']['count'] = True
        self.assertRefused(invoke(commands=[desired], node=observed))

    def test_extra_platform_defaults_do_not_block_a_match(self):
        observed = detail()
        observed['params']['settings']['extra_default'] = 'irrelevant'
        result = invoke(node=observed)
        self.assertEqual(result['code'], 0)
        self.assertTrue(any(args[2] == 'stable-id' for args, _ in result['calls'] if len(args) > 2))

    def test_preflight_completes_before_any_group_or_node_write(self):
        observed = detail()
        observed['params']['prompt'] = 'wrong'
        commands = [{'kind': 'group_create', 'name': 'new-group', 'run': False},
                    dict(command(), name='new-node'), command()]
        self.assertRefused(invoke(commands=commands, node=observed))

    def test_duplicate_planned_node_names_are_refused(self):
        with self.assertRaises(ValueError):
            adapter.build_phases({'commands': [command(), dict(command(), model='conflict')]}, 'synthetic-project')

    def test_duplicate_existing_names_or_ids_are_refused(self):
        for inventory in ([{'id': 'stable-id', 'name': 'stable_name'}, {'id': 'other-id', 'name': 'stable_name'}],
                          [{'id': 'stable-id', 'name': 'stable_name'}, {'id': 'stable-id', 'name': 'other_name'}]):
            with self.subTest(inventory=inventory):
                self.assertRefused(invoke(inventory=inventory))

    def test_inventory_without_stable_id_is_refused(self):
        self.assertRefused(invoke(inventory=[{'name': 'stable_name'}]))

    def test_missing_or_ambiguous_group_collection_is_refused(self):
        for output in ({}, {'unexpected': []}, {'groups': 'not-a-list'}, {'groups': [{}]},
                       {'groups': [{'id': 'g1', 'name': 'same'}, {'id': 'g2', 'name': 'same'}]}):
            with self.subTest(output=output):
                self.assertRefused(invoke(group_output=output))

    def test_blank_planned_names_and_blank_unrelated_inventory_identity_are_refused(self):
        for name in ('', '   ', None, 1):
            with self.subTest(planned_name=name):
                with self.assertRaises(ValueError):
                    adapter.build_phases({'commands': [dict(command(), name=name)]}, 'p')
        for unrelated in ({'id': '  ', 'name': 'other'}, {'id': 'other-id', 'name': '  '}):
            with self.subTest(unrelated=unrelated):
                self.assertRefused(invoke(inventory=[{'id': 'stable-id', 'name': 'stable_name'}, unrelated]))

    def test_query_failure_stops_all_writes(self):
        self.assertRefused(invoke(query_failure=True))

    def test_known_empty_inventory_creates_once_without_run(self):
        result = invoke(inventory=[])
        self.assertEqual(result['code'], 0)
        self.assertEqual(result['stats']['nodes_created'], 1)
        self.assertEqual(len(result['writes']), 1)
        self.assertNotIn('--run', result['writes'][0])

    def test_all_reads_use_devnull_to_avoid_stdin_link_mutation(self):
        result = invoke()
        self.assertIsNone(result['error'])
        self.assertTrue(result['calls'])
        for args, kwargs in result['calls']:
            self.assertEqual(kwargs.get('stdin'), subprocess.DEVNULL)

    def test_dry_run_never_calls_cli(self):
        result = invoke(execute=False)
        self.assertEqual(result['code'], 0)
        self.assertEqual(result['calls'], [])

    def test_run_true_and_cycles_still_refused(self):
        with self.assertRaises(ValueError):
            adapter.build_phases({'commands': [dict(command(), run=True)]}, 'p')
        with self.assertRaises(ValueError):
            adapter.build_phases({'commands': [command(), {'kind': 'node_link', 'target': 'stable_name', 'left': 'stable_name'}]}, 'p')


if __name__ == '__main__':
    unittest.main()
