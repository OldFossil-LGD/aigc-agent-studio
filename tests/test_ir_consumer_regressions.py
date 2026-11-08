"""Structured sound survives the real compiler-to-IR entry path."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.compile_production import compile_production
from scripts.intent_handoff import to_compiler_input
from scripts import production_ir

ROOT = Path(__file__).resolve().parents[1]

class IRSoundConsumerTests(unittest.TestCase):
    def data(self):
        return to_compiler_input(json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8')))

    def build(self, data):
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(data, Path(temp))
            self.assertEqual(result['gate']['status'], 'PASS')
            return production_ir.build(temp)

    def test_project_sound_and_denials_survive_rendering(self):
        ir = self.build(self.data())
        policy = ir['shots'][0]['audio_policy']
        self.assertEqual(policy['mode'], 'ambience_only')
        self.assertEqual(policy['allow'], ['雨声'])
        self.assertIn('人声', policy['deny'])
        self.assertEqual(policy['dialogue'], 'none')
        self.assertIn('雨声', production_ir.render(ir))

    def test_audio_asset_list_is_not_treated_as_policy_object(self):
        data = self.data()
        data['audio'] = [{'id': 'rain', 'description': 'Rain ambience'}]
        ir = self.build(data)
        self.assertEqual(ir['project']['audio_policy']['mode'], 'ambience_only')
        self.assertEqual(ir['shots'][0]['audio_policy']['allow'], ['雨声'])

    def test_shot_sound_overrides_project_sound(self):
        data = self.data()
        data['shots'][0]['sound'] = {'mode': 'silent', 'allowed': [],
            'forbidden': ['雨声'], 'source': 'user_explicit', 'locked': True}
        ir = self.build(data)
        self.assertEqual(ir['project']['audio_policy']['mode'], 'ambience_only')
        self.assertEqual(ir['shots'][0]['audio_policy']['mode'], 'silent')
        self.assertEqual(ir['shots'][0]['audio_policy']['allow'], [])
        self.assertEqual(ir['shots'][0]['audio_policy']['deny'], ['雨声'])

    def test_cinematography_survives_nodes_prompts_and_ir(self):
        data = self.data()
        data['shots'][0].update(camera={'shot_scale': 'CU', 'angle': 'overhead',
            'lens': '85mm', 'movement': 'static'}, composition='unique_composition',
            lighting='unique_lighting', purpose='unique_purpose', camera_movement='static')
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(data, Path(temp))
            video = next(p for p in result['prompts'] if p['role'] == 'video_candidate')
            self.assertIn('unique_composition', video['blocks']['composition'])
            self.assertIn('unique_lighting', video['blocks']['lighting'])
            ir = production_ir.build(temp)
        shot = ir['shots'][0]
        self.assertEqual(shot['camera_spec']['value']['shot_size'], 'CU')
        self.assertEqual(shot['camera_spec']['value']['lens'], '85mm')
        self.assertEqual(shot['purpose']['value'], 'unique_purpose')
        text = production_ir.render(ir)
        for expected in ['unique_composition', 'unique_lighting', 'unique_purpose', '85mm']:
            self.assertIn(expected, text)

    def test_explicit_asset_versions_survive_ir(self):
        data = self.data()
        data['constraints'] = []
        data['entities'] = [
            {'id': 'C1', 'kind': 'character', 'description': '蓝衣女性', 'version': 2},
            {'id': 'S1', 'kind': 'scene', 'description': '蓝色房间', 'version': 1},
            {'id': 'P1', 'kind': 'prop', 'description': '白色杯子', 'version': 3}]
        data['shots'][0].update(shot_kind='standard', description='她站在房间中握杯',
            asset_refs=[{'entity_id': 'C1', 'version': 2},
                        {'entity_id': 'S1', 'version': 1}, {'entity_id': 'P1', 'version': 3}])
        ir = self.build(data)
        refs = ir['shots'][0]['asset_refs']
        self.assertEqual(refs['character_refs'], [
            {'character_id': 'C1', 'identity_version': 'v002', 'look_id': None}])
        self.assertEqual(refs['location_id'], 'S1')
        self.assertEqual(refs['prop_refs'], ['P1'])
        self.assertNotIn('SHOT_PRESENCE_CONFLICT', {i['rule_id'] for i in production_ir.validate(ir)})

if __name__ == '__main__':
    unittest.main()
