"""Local contract-to-command acceptance; no platform or media calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_production import compile_production
from scripts.compile_production_contract import compile_contract
from scripts.compile_prompt_packages import compile_prompt_packages
from scripts.production_schema_validation import validate_contract_result


class NoDialogueTests(unittest.TestCase):
    def data(self):
        return {'goal': 'Synthetic ambience-only fixture', 'duration_sec': 3,
                'entities': [{'id': 'hero', 'kind': 'character', 'description': 'Red-coated adult'}],
                'shots': [{'id': 's1', 'duration_sec': 3}], 'delivery': {'ignition_allowed': False}}

    def compile(self, data):
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(data, Path(temp))
            commands = json.loads((Path(temp) / '08_libtv_command_plan.json').read_text(encoding='utf-8'))
        self.assertEqual(data, original)
        self.assertEqual(result['gate']['status'], 'PASS', result['gate']['failures'])
        self.assertTrue(all(c.get('run') is False for c in commands['commands']))
        return result, commands

    def assertNoSpeech(self, text):
        self.assertIn('禁止', text)
        for word in ['人声', '对白', '旁白']:
            self.assertIn(word, text)
        self.assertNotIn('必要的人声', text)
        self.assertNotIn('人声/旁白', text)
        self.assertNotIn('完全无声', text)

    def test_project_flag_preserves_explicit_true_and_false(self):
        for value in [True, False]:
            with self.subTest(value=value):
                data = dict(self.data(), no_dialogue=value)
                self.assertIs(compile_contract(data)['production_contract'].get('no_dialogue'), value)

    def test_invalid_project_flags_are_rejected(self):
        for value in [0, 1, 'false', 'true', None, [], {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                compile_contract(dict(self.data(), no_dialogue=value))

    def test_invalid_shot_flags_are_rejected(self):
        for value in [0, 1, 'false', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                data = self.data()
                data['shots'][0]['no_dialogue'] = value
                compile_contract(data)

    def test_global_no_dialogue_reaches_video_audio_and_assembly(self):
        result, commands = self.compile(dict(self.data(), no_dialogue=True))
        for role, key in [('video_candidate', 'sound'), ('audio', 'sound_layers'), ('assembly', 'sound')]:
            package = next(p for p in result['prompts'] if p['role'] == role)
            self.assertNoSpeech(package['blocks'][key])
            self.assertIn('环境', package['blocks'][key])
            self.assertNoSpeech(next(c for c in commands['commands'] if c.get('role') == role)['prompt'])
        self.assertTrue(any(n['node_type'] == 'audio' for n in result['graph']['nodes']))

    def test_shot_true_does_not_affect_another_shot(self):
        data = self.data()
        data['duration_sec'] = 6
        data['shots'] = [{'id': 'quiet', 'duration_sec': 3, 'no_dialogue': True},
                         {'id': 'shot_01', 'duration_sec': 3}]
        result, _ = self.compile(data)
        videos = {p['shot_id']: p['blocks']['sound'] for p in result['prompts'] if p['role'] == 'video_candidate'}
        self.assertNoSpeech(videos['quiet'])
        self.assertIn('必要的人声', videos['shot_01'])

    def test_shot_false_overrides_global_true(self):
        data = dict(self.data(), no_dialogue=True)
        data['shots'][0]['no_dialogue'] = False
        result, _ = self.compile(data)
        self.assertIn('必要的人声', next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound'])

    def test_full_silence_takes_priority(self):
        data = dict(self.data(), no_dialogue=False)
        data['shots'][0].update(shot_kind='silent', no_dialogue=False)
        result, _ = self.compile(data)
        self.assertIn('完全无声', next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound'])
        self.assertFalse(any(n['node_type'] == 'audio' for n in result['graph']['nodes']))

    def test_absent_flag_preserves_legacy_output(self):
        result, _ = self.compile(self.data())
        self.assertIn('必要的人声', next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound'])

    def test_no_dialogue_does_not_add_unsolicited_music(self):
        result, _ = self.compile(dict(self.data(), no_dialogue=True))
        sound = next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound']
        self.assertIn('除非镜头要求，不加入现代音乐', sound)
        self.assertNotIn('与音乐', sound)

    def graph(self, shot):
        return {'shots': [shot], 'edges': [], 'nodes': [
            {'id': 's1__video', 'role': 'video_candidate', 'shot_id': 's1', 'node_type': 'video'}]}

    def test_standalone_uses_graph_shot_flag(self):
        graph = self.graph({'id': 's1', 'no_dialogue': True})
        package = compile_prompt_packages({}, {'assets': []}, graph)[0]
        self.assertNoSpeech(package['blocks']['sound'])

    def test_contract_shot_false_beats_stale_graph_true(self):
        graph = self.graph({'id': 's1', 'no_dialogue': True})
        package = compile_prompt_packages({'shots': [{'id': 's1', 'no_dialogue': False}]}, {'assets': []}, graph)[0]
        self.assertIn('必要的人声', package['blocks']['sound'])

    def test_contract_shot_inherits_project_before_stale_graph(self):
        graph = self.graph({'id': 's1', 'no_dialogue': False})
        package = compile_prompt_packages({'no_dialogue': True, 'shots': [{'id': 's1'}]}, {'assets': []}, graph)[0]
        self.assertNoSpeech(package['blocks']['sound'])

    def test_schema_rejects_nonboolean_project_flag(self):
        payload = compile_contract(self.data())
        payload['production_contract']['no_dialogue'] = 'false'
        with self.assertRaises(Exception):
            validate_contract_result(payload)

    def test_schema_rejects_nonboolean_shot_flag(self):
        payload = compile_contract(self.data())
        payload['production_contract']['shots'][0]['no_dialogue'] = 'false'
        with self.assertRaises(Exception):
            validate_contract_result(payload)


if __name__ == '__main__':
    unittest.main()
