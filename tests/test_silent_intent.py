"""Independent offline acceptance of existing silent shot-kind semantics."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_production import compile_production
from scripts.compile_prompt_packages import compile_prompt_packages
from scripts.compile_shot_graph import resolve_shot_roles


class SilentIntentTests(unittest.TestCase):
    def compile(self, shots):
        data = {'goal': 'Synthetic local sound-intent fixture', 'duration_sec': 3 * len(shots),
                'entities': [{'id': 'hero', 'kind': 'character', 'description': 'Red-coated adult'}],
                'shots': shots, 'delivery': {'ignition_allowed': False}}
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(data, Path(temp))
            commands = json.loads((Path(temp) / '08_libtv_command_plan.json').read_text(encoding='utf-8'))
        self.assertEqual(data, original)
        self.assertEqual(result['gate']['status'], 'PASS', result['gate']['failures'])
        self.assertTrue(all(command.get('run') is False for command in commands['commands']))
        return result, commands

    def assertSilent(self, text):
        self.assertIsInstance(text, str)
        self.assertIn('禁止', text)
        for word in ['人声', '旁白', '环境声', '音乐']:
            self.assertIn(word, text)
        self.assertNotIn('保留环境声', text)
        self.assertNotIn('必要的人声', text)

    def test_existing_silent_aliases_reach_final_video_commands(self):
        for kind in ['silent', 'no_audio', 'mute']:
            with self.subTest(kind=kind):
                result, commands = self.compile([{'id': 's1', 'duration_sec': 3, 'shot_kind': kind}])
                package = next(p for p in result['prompts'] if p['role'] == 'video_candidate')
                self.assertSilent(package['blocks']['sound'])
                video = next(c for c in commands['commands'] if c.get('role') == 'video_candidate')
                self.assertSilent(video['prompt'])
                self.assertEqual(video['settings']['enableSound'], 'off')
                self.assertFalse(any(n['node_type'] == 'audio' for n in result['graph']['nodes']))

    def test_explicit_roles_cannot_reintroduce_audio_for_silent_shot(self):
        roles = resolve_shot_roles({'shot_kind': 'silent', 'roles': ['storyboard', 'audio', 'video_candidate']})
        self.assertEqual(roles, ['storyboard', 'video_candidate'])

    def test_required_roles_cannot_reintroduce_audio_for_mute_shot(self):
        roles = resolve_shot_roles({'kind': 'mute', 'required_roles': ['audio', 'assembly']})
        self.assertEqual(roles, ['assembly'])

    def test_all_silent_assembly_has_no_generic_sound_instruction(self):
        result, commands = self.compile([{'id': 's1', 'duration_sec': 3, 'shot_kind': 'silent'}])
        package = next(p for p in result['prompts'] if p['role'] == 'assembly')
        self.assertSilent(package['blocks']['sound'])
        self.assertSilent(next(c for c in commands['commands'] if c.get('role') == 'assembly')['prompt'])

    def test_mixed_shots_preserve_standard_sound_without_bleed(self):
        result, _ = self.compile([{'id': 'quiet', 'duration_sec': 3, 'shot_kind': 'silent'},
                                  {'id': 'normal', 'duration_sec': 3}])
        packages = {(p['shot_id'], p['role']): p for p in result['prompts'] if p['shot_id']}
        self.assertSilent(packages['quiet', 'video_candidate']['blocks']['sound'])
        self.assertSilent(packages['quiet', 'assembly']['blocks']['sound'])
        self.assertEqual(packages['normal', 'video_candidate']['blocks']['sound'],
                         '保留环境声、动作声和必要的人声层；除非镜头要求，不加入现代音乐。')
        self.assertIn(('normal', 'audio'), packages)
        self.assertNotIn(('quiet', 'audio'), packages)

    def test_kind_alias_and_uppercase_are_resolved(self):
        result, _ = self.compile([{'id': 's1', 'duration_sec': 3, 'kind': 'MUTE'}])
        self.assertSilent(next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound'])

    def test_graph_shot_kind_is_used_when_contract_has_no_shots(self):
        graph = {'shots': [{'id': 's1', 'shot_kind': 'no_audio'}], 'edges': [],
                 'nodes': [{'id': 's1__video', 'role': 'video_candidate', 'shot_id': 's1', 'node_type': 'video'}]}
        before = copy.deepcopy(graph)
        package = compile_prompt_packages({}, {'assets': []}, graph)[0]
        self.assertSilent(package['blocks']['sound'])
        self.assertEqual(graph, before)

    def test_absent_audio_role_does_not_imply_silent(self):
        graph = {'shots': [{'id': 's1', 'shot_kind': 'empty'}], 'edges': [],
                 'nodes': [{'id': 's1__video', 'role': 'video_candidate', 'shot_id': 's1', 'node_type': 'video'}]}
        package = compile_prompt_packages({}, {'assets': []}, graph)[0]
        self.assertEqual(package['blocks']['sound'], '保留环境声、动作声和必要的人声层；除非镜头要求，不加入现代音乐。')

    def test_explicit_ids_do_not_acquire_positional_aliases(self):
        result, _ = self.compile([{'id': 'quiet', 'duration_sec': 3, 'shot_kind': 'silent'},
                                  {'id': 'shot_01', 'duration_sec': 3}])
        standard = next(p for p in result['prompts'] if p['shot_id'] == 'shot_01' and p['role'] == 'video_candidate')
        self.assertIn('保留环境声', standard['blocks']['sound'])

    def test_contract_default_kind_overrides_stale_graph_kind(self):
        graph = {'shots': [{'id': 's1', 'shot_kind': 'silent'}], 'edges': [],
                 'nodes': [{'id': 's1__video', 'role': 'video_candidate', 'shot_id': 's1', 'node_type': 'video'}]}
        package = compile_prompt_packages({'shots': [{'id': 's1'}]}, {'assets': []}, graph)[0]
        self.assertIn('保留环境声', package['blocks']['sound'])

    def test_empty_primary_kind_uses_kind_alias_consistently(self):
        result, _ = self.compile([{'id': 's1', 'duration_sec': 3, 'shot_kind': '', 'kind': 'mute'}])
        self.assertSilent(next(p for p in result['prompts'] if p['role'] == 'video_candidate')['blocks']['sound'])

    def test_standalone_missing_id_uses_exact_graph_fallback(self):
        graph = {'edges': [], 'nodes': [{'id': 'shot_01__video', 'role': 'video_candidate',
                                        'shot_id': 'shot_01', 'node_type': 'video'}]}
        package = compile_prompt_packages({'shots': [{'kind': 'mute'}]}, {'assets': []}, graph)[0]
        self.assertSilent(package['blocks']['sound'])


if __name__ == '__main__':
    unittest.main()
