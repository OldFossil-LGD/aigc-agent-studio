"""Task scope must constrain real emitted graphs and execution artifacts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_production import compile_production
from scripts.compile_production_contract import compile_contract
from scripts.production_capability_gate import evaluate
from scripts.production_schema_validation import validate_contract_result


class TaskStopsTests(unittest.TestCase):
    def data(self, task_type=None):
        data = {'goal': 'Synthetic task-scope fixture', 'duration_sec': 3,
                'entities': [{'id': 'hero', 'kind': 'character', 'description': 'Red-coated adult'}],
                'shots': [{'id': 's1', 'duration_sec': 3}], 'delivery': {'ignition_allowed': False}}
        if task_type is not None:
            data['task_type'] = task_type
        return data

    def compile(self, data):
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = compile_production(data, output)
            files = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        self.assertEqual(data, original)
        self.assertEqual(result['gate']['status'], 'PASS', result['gate']['failures'])
        return result, files

    def profile(self, files):
        self.assertIn('11_task_profile.json', files.keys())
        return json.loads(files['11_task_profile.json'])

    def assertPromptStop(self, result, files):
        self.assertNotIn('05_platform_execution_plan.json', files.keys())
        self.assertNotIn('08_libtv_command_plan.json', files.keys())
        self.assertIn('04_prompt_packages.jsonl', files.keys())
        forbidden = {'assembly', 'final_composite', 'production_ledger', 'qa'}
        self.assertFalse(forbidden & {n['role'] for n in result['graph']['nodes']})
        ids = {n['id'] for n in result['graph']['nodes']}
        self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in result['graph']['edges']))
        self.assertTrue(all(n in ids for g in result['graph']['groups'] for n in g['node_ids']))
        self.assertFalse(self.profile(files)['production_complete'])

    def test_prompt_only_stops_at_actual_graph_and_prompt_artifacts(self):
        result, files = self.compile(self.data('prompt_only'))
        self.assertPromptStop(result, files)
        self.assertEqual(self.profile(files)['target_state'], 'graph_plan_ready')
        self.assertEqual(result['contract']['task_type'], 'prompt_only')
        self.assertEqual(result['contract']['production_mode'], 'production_build')

    def test_single_shot_stops_at_prompt_package(self):
        result, files = self.compile(self.data('single_shot'))
        self.assertPromptStop(result, files)
        self.assertEqual(self.profile(files)['target_state'], 'prompt_package_ready')
        self.assertEqual({p['shot_id'] for p in result['prompts'] if p.get('shot_id')}, {'s1'})

    def test_full_film_preserves_full_graph_and_execution_plans(self):
        default, default_files = self.compile(self.data())
        explicit, files = self.compile(self.data('full_film'))
        self.assertEqual(default['graph'], explicit['graph'])
        for name in ['05_platform_execution_plan.json', '08_libtv_command_plan.json']:
            self.assertIn(name, files.keys())
            self.assertEqual(files[name], default_files[name])
        profile = self.profile(files)
        self.assertEqual(profile['target_state'], 'delivered')
        self.assertNotEqual(profile['compiler_state'], 'delivered')
        self.assertFalse(profile['production_complete'])

    def test_invalid_task_types_and_unimplemented_rework_do_not_fall_back(self):
        for value in ['', 'typo', 'rework', 0, False, None, [], {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                data = self.data()
                data['task_type'] = value
                compile_contract(data)

    def test_single_shot_requires_exactly_one_explicit_shot(self):
        for shots in [[], [{'id': 's1', 'duration_sec': 3}, {'id': 's2', 'duration_sec': 3}]]:
            with self.subTest(shots=shots), self.assertRaises(ValueError):
                data = self.data('single_shot')
                data['shots'] = shots
                compile_contract(data)

    def test_prompt_tasks_refuse_conflicting_generation_or_export(self):
        for task in ['prompt_only', 'single_shot']:
            for field in ['requires_media_generation', 'requires_export']:
                with self.subTest(task=task, field=field), self.assertRaises(ValueError):
                    data = self.data(task)
                    data['delivery'][field] = True
                    compile_contract(data)

    def test_partial_output_refuses_stale_execution_files_without_writes(self):
        for filename in ['05_platform_execution_plan.json', '08_libtv_command_plan.json']:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                output = Path(temp)
                (output / filename).write_bytes(b'preserve old plan\n')
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                with self.assertRaises(ValueError):
                    compile_production(self.data('prompt_only'), output)
                self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)

    def test_gate_rejects_full_graph_for_prompt_only(self):
        full, _ = self.compile(self.data())
        contract = dict(full['contract'], task_type='prompt_only')
        gate = evaluate(contract, full['assets'], full['graph'], full['prompts'])
        self.assertEqual(gate['status'], 'FAIL')
        self.assertIn('TASK_STAGE_EXCEEDED', {f['code'] for f in gate['failures']})

    def test_gate_derives_required_roles_from_contract_not_graph_claims(self):
        result, _ = self.compile(self.data('prompt_only'))
        graph = copy.deepcopy(result['graph'])
        removed = {n['id'] for n in graph['nodes'] if n['role'] == 'storyboard'}
        graph['nodes'] = [n for n in graph['nodes'] if n['id'] not in removed]
        graph['edges'] = [e for e in graph['edges'] if e['source'] not in removed and e['target'] not in removed]
        for shot in graph['shots']:
            shot['roles'] = [r for r in shot['roles'] if r != 'storyboard']
            shot['required_roles'] = list(shot['roles'])
        gate = evaluate(result['contract'], result['assets'], graph, result['prompts'])
        self.assertIn('MISSING_SHOT_ROLE', {f['code'] for f in gate['failures']})

    def test_selection_receives_its_actual_video_candidates(self):
        result, _ = self.compile(self.data('prompt_only'))
        graph = result['graph']
        videos = {n['id'] for n in graph['nodes'] if n['role'] == 'video_candidate'}
        selection = next(n['id'] for n in graph['nodes'] if n['role'] == 'selection')
        self.assertTrue(all(any(e['source'] == v and e['target'] == selection for e in graph['edges']) for v in videos))
        altered = copy.deepcopy(graph)
        altered['edges'] = [e for e in altered['edges'] if not (e['source'] in videos and e['target'] == selection)]
        gate = evaluate(result['contract'], result['assets'], altered, result['prompts'])
        self.assertIn('TASK_SELECTION_INPUT_MISSING', {f['code'] for f in gate['failures']})

    def test_no_assets_does_not_leave_an_isolated_global_manifest(self):
        data = self.data('prompt_only')
        data['entities'] = []
        data['shots'][0]['shot_kind'] = 'empty'
        result, files = self.compile(data)
        self.assertPromptStop(result, files)
        self.assertNotIn('global__asset_manifest', {n['id'] for n in result['graph']['nodes']})

    def test_sound_intents_survive_projection(self):
        for flag in ['silent', 'no_dialogue']:
            with self.subTest(flag=flag):
                data = self.data('single_shot')
                if flag == 'silent':
                    data['shots'][0]['shot_kind'] = 'silent'
                else:
                    data['no_dialogue'] = True
                result, _ = self.compile(data)
                sound = next(p['blocks']['sound'] for p in result['prompts'] if p['role'] == 'video_candidate')
                self.assertIn('禁止人声', sound)

    def test_schema_rejects_unknown_task_type(self):
        payload = compile_contract(self.data())
        payload['production_contract']['task_type'] = 'typo'
        with self.assertRaises(Exception):
            validate_contract_result(payload)

    def test_mirror_prompt_only_preserves_source_settings_and_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.json'
            source.write_text(json.dumps({'nodes': [{'id': 'n1', 'type': 'video', 'name': 'original'}], 'edges': []}), encoding='utf-8')
            cache = root / 'cache'
            cache.mkdir()
            params = {'model': 'source-model', 'modeType': 'source-mode', 'settings': {'ratio': '9:16', 'duration': 8}, 'prompt': 'source wording'}
            (cache / 'n1.json').write_text(json.dumps({'data': {'params': params}}), encoding='utf-8')
            data = self.data('prompt_only')
            data.update(mode='copy_reverse', deliverable='mirror', source_project_uuid='source-id', copy_project_uuid='copy-id',
                        source_access='copy_readback', source_graph_path=str(source), param_cache_dir=str(cache), work_profile={'fixture_only': True})
            result = compile_production(data, root / 'out')
            self.assertEqual(result['gate']['status'], 'PASS', result['gate']['failures'])
            node, = result['graph']['nodes']
            self.assertEqual(node['settings'], params['settings'])
            self.assertEqual(node['model'], params['model'])
            self.assertEqual(node['prompt'], params['prompt'])
            self.assertFalse((root / 'out/05_platform_execution_plan.json').exists())

    def test_single_shot_mirror_conflict_is_not_silently_reinterpreted(self):
        with self.assertRaises(ValueError):
            compile_contract(dict(self.data('single_shot'), deliverable='mirror'))


if __name__ == '__main__':
    unittest.main()
