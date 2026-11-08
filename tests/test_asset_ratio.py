"""Independent asset-ratio intent tests, entirely offline and synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_asset_graph import compile_asset_graph
from scripts.compile_production import _mirror_graph, compile_production
from scripts.production_capability_gate import evaluate


def fixture():
    return {'goal': 'Synthetic independent asset ratios', 'duration_sec': 3, 'aspect_ratio': '9:16',
            'entities': [{'id': 'room', 'kind': 'scene', 'description': 'Geometric room',
                          'reuse_count': 2, 'aspect_ratio': '1:1'},
                         {'id': 'hero', 'kind': 'character', 'description': 'Blue wooden figure',
                          'aspect_ratio': '4:5'},
                         {'id': 'clock', 'kind': 'prop', 'description': 'Round brass clock'}],
            'shots': [{'id': 's1', 'duration_sec': 3, 'description': 'Figure inside room'}],
            'delivery': {'ignition_allowed': False}}


def compile_case(data):
    with tempfile.TemporaryDirectory(prefix='asset-ratio-audit-') as directory:
        result = compile_production(data, Path(directory))
        result['commands'] = json.loads((Path(directory) / '08_libtv_command_plan.json').read_text(encoding='utf-8'))
    return result


def gate(result):
    return evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])


class AssetRatioTests(unittest.TestCase):
    def test_asset_plan_records_resolved_ratio_and_its_source(self):
        assets = compile_asset_graph(fixture())['assets']
        actual = {a['id']: (a.get('aspect_ratio'), a.get('aspect_ratio_source')) for a in assets}
        self.assertEqual(actual, {'room': ('1:1', 'entity'), 'hero': ('4:5', 'entity'), 'clock': ('9:16', 'project_default')})

    def test_final_asset_commands_preserve_explicit_and_default_ratios(self):
        result = compile_case(fixture())
        self.assertEqual(result['gate']['status'], 'PASS')
        expected = {'room': '1:1', 'hero': '4:5', 'clock': '9:16'}
        nodes = {n['id'].replace('__', '_'): n for n in result['graph']['nodes'] if n.get('role') in {'asset_anchor', 'asset_refine'}}
        rows = [r for r in result['commands']['commands'] if r.get('kind') == 'node_create' and r['name'] in nodes]
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row['settings']['ratio'], expected[nodes[row['name']]['entity_id']])

    def test_shot_images_and_videos_keep_project_ratio(self):
        result = compile_case(fixture())
        for row in result['commands']['commands']:
            if row.get('shot_id') and row.get('node_type') in {'image', 'video'}:
                self.assertEqual(row['settings']['ratio'], '9:16')

    def test_omitted_entity_ratio_defaults_to_project(self):
        data = fixture()
        for entity in data['entities']:
            entity.pop('aspect_ratio', None)
        result = compile_case(data)
        self.assertEqual(result['gate']['status'], 'PASS')
        self.assertTrue(all(a.get('aspect_ratio') == '9:16' for a in result['assets']['assets']))

    def test_explicit_invalid_ratio_never_silently_defaults(self):
        for value in (None, '', True, 1, [], '0:1', '1:0', '-1:1', 'nan:1', '1:1:1'):
            with self.subTest(value=value):
                data = fixture()
                data['entities'][0]['aspect_ratio'] = value
                with self.assertRaises(ValueError):
                    compile_asset_graph(data)

    def test_changing_one_asset_ratio_does_not_change_other_settings(self):
        a = compile_case(fixture())
        data = fixture()
        data['entities'][0]['aspect_ratio'] = '2:3'
        b = compile_case(data)
        nodes = {n['id'].replace('__', '_'): n for n in b['graph']['nodes']}
        settings = {r['name']: r.get('settings') for r in a['commands']['commands'] if r.get('kind') == 'node_create'}
        for row in b['commands']['commands']:
            if row.get('kind') != 'node_create':
                continue
            if nodes[row['name']].get('entity_id') == 'room':
                self.assertEqual(row['settings']['ratio'], '2:3')
            else:
                self.assertEqual(row.get('settings'), settings[row['name']])

    def test_gate_rejects_wrong_asset_ratio(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('entity_id') == 'room':
                node['settings']['ratio'] = '9:16'
        self.assertEqual(gate(result)['status'], 'FAIL')

    def test_gate_rejects_missing_explicit_asset_ratio(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('entity_id') == 'room':
                node['settings'].pop('ratio', None)
        self.assertEqual(gate(result)['status'], 'FAIL')

    def test_gate_uses_contract_even_if_asset_plan_is_tampered(self):
        result = compile_case(fixture())
        for asset in result['assets']['assets']:
            if asset['id'] == 'room':
                asset['aspect_ratio'] = '9:16'
        for node in result['graph']['nodes']:
            if node.get('entity_id') == 'room':
                node['settings']['ratio'] = '9:16'
        self.assertEqual(gate(result)['status'], 'FAIL')

    def test_gate_rejects_invalid_direct_contract_ratio(self):
        result = compile_case(fixture())
        result['contract']['entities'][0]['aspect_ratio'] = None
        self.assertEqual(gate(result)['status'], 'FAIL')

    def test_input_unchanged_and_commands_never_ignite(self):
        data = fixture()
        before = copy.deepcopy(data)
        result = compile_case(data)
        self.assertEqual(data, before)
        self.assertTrue(all(row['run'] is False for row in result['commands']['commands']))

    def test_mirror_preserves_source_settings_with_different_project_ratio(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.json'
            source.write_text(json.dumps({'nodes': [{'id': 'n1', 'type': 'image', 'settings': {'ratio': '3:2'}}], 'edges': []}), encoding='utf-8')
            graph = _mirror_graph({'source_graph_path': str(source), 'aspect_ratio': '9:16'})
            self.assertEqual(graph['nodes'][0]['settings'], {'ratio': '3:2'})


if __name__ == '__main__':
    unittest.main()
