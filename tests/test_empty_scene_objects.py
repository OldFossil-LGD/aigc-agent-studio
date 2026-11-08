"""Exercise empty scenes containing declared props, stillness and explicit sound."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from scripts.compile_intent_delivery import compile_intent_delivery
ROOT = Path(__file__).resolve().parents[1]

class EmptySceneObjectTests(unittest.TestCase):
    def compile(self, task):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        result = compile_intent_delivery(task, Path(temp.name), draft=True)
        self.assertEqual(result['verification']['status'], 'PASS', result['verification'])
        package = next(p for p in result['prompts'] if p['role'] == 'video_candidate')
        return package['blocks']
    def station(self):
        return json.loads((ROOT / 'samples/woodcut_station_creator_intent.json').read_text(encoding='utf-8'))
    def test_still_empty_scene_is_not_instructed_to_change_the_picture(self):
        blocks = self.compile(self.station())
        self.assertIn('整段保持静止', blocks['action'])
        self.assertNotIn('画面变化', blocks['action'])
    def test_cloth_prop_is_preserved_without_a_blanket_clothing_ban(self):
        blocks = self.compile(self.station())
        self.assertIn('红围巾', blocks['visual'])
        self.assertNotRegex(blocks['continuity'], r'(?:不引入|禁止)[^；。]*[、，]服装')
        self.assertIn('物件', blocks['continuity'])
    def test_explicit_offscreen_voice_is_not_negated_by_visual_continuity(self):
        task = self.station()
        task['goal'] = '只要8秒16:9木刻空镜：红围巾放在长椅上，完全静止、固定侧面远景；允许画外旁白，不出现人物、字幕或音乐。'
        task['decisions']['sound_mode']['value'] = 'dialogue_allowed'
        task['sound'] = {'mode': 'dialogue_allowed', 'allowed': ['画外旁白'], 'forbidden': ['音乐'], 'source': 'user_explicit', 'locked': True}
        task['shots'][0]['sound'] = copy.deepcopy(task['sound'])
        task['shots'][0]['description'] = '雨后的空站台，一条红围巾平放在长椅上，整段保持静止；允许画外旁白，不出现人物。'
        for c in task['constraints']:
            if c['id'] == 'c_sound':
                c['text'] = '允许画外旁白，不加音乐。'; c['semantics'] = {'required_any': ['画外旁白'], 'forbidden': ['强制静音']}
            if c['id'] == 'c_negative':
                c['text'] = '不出现人物，也不加字幕或音乐。'; c['semantics'] = {'required_any': ['不出现人物'], 'forbidden': ['人物登场']}
        blocks = self.compile(task)
        self.assertIn('允许', blocks['sound'])
        self.assertIn('画外旁白', blocks['sound'])
        self.assertNotRegex(blocks['continuity'], r'(?:不引入|禁止)[^；。]*人声')
    def test_unspecified_empty_scene_sound_does_not_request_new_human_voice(self):
        task = self.station()
        task['goal'] = '只要一条8秒16:9木刻空镜提示词：红围巾在长椅上，画面静止、固定侧面远景、无人；声音尚未指定。'
        task.pop('sound', None)
        task['decisions'].pop('sound_mode', None)
        task['shots'][0].pop('sound', None)
        task['shots'][0]['description'] = '雨后空站台，红围巾平放长椅，整段保持静止，固定侧面远景。'
        task['constraints'] = [c for c in task['constraints'] if c['kind'] != 'sound']
        for c in task['constraints']:
            if c['id'] == 'c_negative':
                c['text'] = '不出现人物，也不加字幕。'; c['semantics'] = {'required_any': ['不出现人物'], 'forbidden': ['人物登场']}
        blocks = self.compile(task)
        self.assertNotIn('必要的人声', blocks['sound'])
    def test_moving_empty_scene_keeps_its_declared_movement(self):
        task = json.loads((ROOT / 'samples/papercut_empty_shot_intent.en.json').read_text(encoding='utf-8'))
        blocks = self.compile(task)
        self.assertIn('slowly sweeps', blocks['action'])
        self.assertNotIn('整段保持静止', blocks['action'])

if __name__ == '__main__': unittest.main()
