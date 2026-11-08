"""Codex independent cases for generation, timeline and cut-range semantics."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.compile_production import compile_production
from scripts.compile_production_contract import compile_contract
from scripts.production_capability_gate import evaluate


def fixture():
    return {'goal': 'Synthetic three-clock contract', 'duration_sec': 3, 'aspect_ratio': '16:9',
            'entities': [{'id': 'room', 'kind': 'scene', 'description': 'Synthetic geometric room'}],
            'shots': [{'id': 's1', 'description': 'Static room shot', 'shot_kind': 'empty',
                       'duration_sec': 3, 'generation_duration_sec': 8,
                       'cut_range': {'start_sec': 2, 'end_sec': 5}}],
            'delivery': {'ignition_allowed': False}}


def compile_case(data):
    with tempfile.TemporaryDirectory(prefix='timing-audit-') as temporary:
        result = compile_production(data, Path(temporary))
        result['commands'] = json.loads((Path(temporary) / '08_libtv_command_plan.json').read_text(encoding='utf-8'))
        result['platform_plan'] = json.loads((Path(temporary) / '05_platform_execution_plan.json').read_text(encoding='utf-8'))
        result['contract_result'] = json.loads((Path(temporary) / '01_production_contract.json').read_text(encoding='utf-8'))
    return result


class ProductionTimingTests(unittest.TestCase):
    def test_generation_and_timeline_durations_are_separate_in_final_commands(self):
        result = compile_case(fixture())
        self.assertEqual(result['gate']['status'], 'PASS')
        self.assertEqual(result['contract']['duration_sec'], 3)
        for row in result['commands']['commands']:
            if row.get('role') == 'video_candidate':
                self.assertEqual(row['settings']['duration'], 8)
            if row.get('role') == 'assembly':
                self.assertEqual(row['settings']['duration'], 3)

    def test_cut_range_reaches_final_command_metadata(self):
        result = compile_case(fixture())
        rows = [row for row in result['commands']['commands'] if row.get('role') == 'video_candidate']
        self.assertTrue(rows)
        self.assertEqual(rows[0]['shot_timing']['cut_range'], {'start_sec': 2, 'end_sec': 5})
        self.assertEqual(rows[0]['shot_timing']['generation_duration_sec'], 8)
        self.assertEqual(rows[0]['shot_timing']['duration_sec'], 3)

    def test_duration_prompt_body_contains_the_actual_three_clocks(self):
        result = compile_case(fixture())
        package = next(p for p in result['prompts'] if p['role'] == 'video_candidate')
        block = str(package['blocks']['duration'])
        for number in (8, 3, 2, 5):
            self.assertRegex(block, rf'(?<!\d){number}(?!\d)')

    def test_platform_target_duration_stays_the_final_duration(self):
        result = compile_case(fixture())
        self.assertEqual(result['platform_plan']['project']['duration_sec'], 3)

    def test_legacy_one_clock_input_remains_compatible(self):
        data = fixture()
        del data['shots'][0]['generation_duration_sec']
        del data['shots'][0]['cut_range']
        result = compile_case(data)
        self.assertEqual(result['gate']['status'], 'PASS')
        self.assertTrue(all(n['settings']['duration'] == 3 for n in result['graph']['nodes'] if n['node_type'] == 'video'))

    def test_default_cut_for_explicit_longer_generation_is_recorded(self):
        data = fixture()
        del data['shots'][0]['cut_range']
        result = compile_case(data)
        shot = result['contract']['shots'][0]
        self.assertEqual(shot['cut_range'], {'start_sec': 0, 'end_sec': 3})
        assumptions = ' '.join(result['contract_result']['assumptions'])
        self.assertTrue('cut_range' in assumptions or '裁切' in assumptions or '截取' in assumptions)

    def test_generation_numeric_string_is_normalized(self):
        data = fixture()
        data['shots'][0]['generation_duration_sec'] = '8'
        self.assertEqual(compile_contract(data)['production_contract']['shots'][0]['generation_duration_sec'], 8)

    def test_invalid_generation_duration_is_rejected(self):
        for value in (0, -1, True, float('nan'), float('inf'), 'bad', None, ''):
            with self.subTest(value=value):
                data = fixture()
                data['shots'][0]['generation_duration_sec'] = value
                data['shots'][0]['cut_range'] = {'start_sec': 0, 'end_sec': 3}
                with self.assertRaises(ValueError):
                    compile_contract(data)

    def test_invalid_cut_ranges_are_rejected(self):
        for cut in ({'start_sec': -1, 'end_sec': 2}, {'start_sec': 5, 'end_sec': 2},
                    {'start_sec': 2, 'end_sec': 2}, {'start_sec': 7, 'end_sec': 10},
                    {'start_sec': 2, 'end_sec': 6}, {'start_sec': True, 'end_sec': 4},
                    {'start_sec': float('nan'), 'end_sec': 5}, {}, [], None):
            with self.subTest(cut=cut):
                data = fixture()
                data['shots'][0]['cut_range'] = cut
                with self.assertRaises(ValueError):
                    compile_contract(data)

    def test_generation_cannot_be_shorter_than_timeline_use(self):
        data = fixture()
        data['shots'][0]['generation_duration_sec'] = 2
        del data['shots'][0]['cut_range']
        with self.assertRaises(ValueError):
            compile_contract(data)

    def test_fractional_cut_range_is_preserved(self):
        data = fixture()
        data['duration_sec'] = data['shots'][0]['duration_sec'] = 3.5
        data['shots'][0]['cut_range'] = {'start_sec': 1.25, 'end_sec': 4.75}
        result = compile_case(data)
        self.assertEqual(result['gate']['status'], 'PASS')
        row = next(r for r in result['commands']['commands'] if r.get('role') == 'video_candidate')
        self.assertEqual(row['shot_timing']['cut_range'], {'start_sec': 1.25, 'end_sec': 4.75})

    def test_input_is_not_mutated(self):
        data = fixture()
        original = copy.deepcopy(data)
        compile_case(data)
        self.assertEqual(data, original)

    def test_project_total_uses_cut_lengths_instead_of_generated_lengths(self):
        data = fixture()
        data['duration_sec'] = 7
        second = copy.deepcopy(data['shots'][0])
        second.update(id='s2', duration_sec=4, cut_range={'start_sec': 1, 'end_sec': 5})
        data['shots'].append(second)
        result = compile_case(data)
        self.assertEqual(result['gate']['status'], 'PASS')
        self.assertEqual(result['platform_plan']['project']['duration_sec'], 7)
        self.assertEqual([r['settings']['duration'] for r in result['commands']['commands'] if r.get('role') == 'video_candidate'], [8, 8])

    def test_incorrect_project_total_still_fails(self):
        data = fixture()
        data['duration_sec'] = 4
        result = compile_case(data)
        self.assertEqual(result['gate']['status'], 'FAIL')
        self.assertIn('DURATION_TOTAL_MISMATCH', {x['code'] for x in result['gate']['failures']})

    def test_gate_rejects_mutated_generation_setting(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('role') == 'video_candidate':
                node['settings']['duration'] = 3
        gate = evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])
        self.assertEqual(gate['status'], 'FAIL')

    def test_gate_rejects_missing_generation_setting(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('role') == 'video_candidate':
                node['settings'].pop('duration', None)
        gate = evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])
        self.assertEqual(gate['status'], 'FAIL')

    def test_gate_rejects_mutated_cut_metadata(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('role') == 'video_candidate':
                node.setdefault('shot_timing', {})['cut_range'] = {'start_sec': 0, 'end_sec': 3}
        gate = evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])
        self.assertEqual(gate['status'], 'FAIL')

    def test_gate_rejects_missing_timing_metadata_for_explicit_contract(self):
        result = compile_case(fixture())
        for node in result['graph']['nodes']:
            if node.get('role') == 'video_candidate':
                node.pop('shot_timing', None)
        gate = evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])
        self.assertEqual(gate['status'], 'FAIL')

    def test_gate_handles_invalid_direct_contract_without_crashing(self):
        result = compile_case(fixture())
        result['contract']['shots'][0]['cut_range'] = {'start_sec': 2, 'end_sec': float('inf')}
        gate = evaluate(result['contract'], result['assets'], result['graph'], result['prompts'])
        self.assertEqual(gate['status'], 'FAIL')

    def test_graph_timing_mutation_does_not_change_contract(self):
        result = compile_case(fixture())
        node = next(n for n in result['graph']['nodes'] if n.get('role') == 'video_candidate')
        node['shot_timing']['cut_range']['start_sec'] = 0
        self.assertEqual(result['contract']['shots'][0]['cut_range'], {'start_sec': 2, 'end_sec': 5})

    def test_shared_timing_resolver_rejects_explicit_unknown_generation(self):
        from scripts.production_timing import resolve_shot_timing
        with self.assertRaises(ValueError):
            resolve_shot_timing({'duration_sec': 3, 'generation_duration_sec': None,
                                 'cut_range': {'start_sec': 0, 'end_sec': 3}})

    def test_no_compiled_command_ignites_anything(self):
        result = compile_case(fixture())
        self.assertTrue(all(row['run'] is False for row in result['commands']['commands']))


if __name__ == '__main__':
    unittest.main()
