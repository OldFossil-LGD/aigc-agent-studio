"""Every spoken line survives breakdown, compilation and human review."""
import unittest
from scripts import breakdown_compile as bridge
from scripts import production_ir
from scripts.compile_production import compile_production
from pathlib import Path
import tempfile

SCRIPT = ('人物：张三、李四\n道具：杯子\n场景一 客厅 日 内\n'
          '镜头1 中景 固定 5秒 张三看着李四。\n'
          '张三：第一句独有台词。\n李四：第二句独有台词。\n')

class DialoguePreservationTests(unittest.TestCase):
    def test_multiple_lines_keep_speakers_and_order_without_inventing_shots(self):
        doc = bridge.parse_screenplay(SCRIPT)
        self.assertEqual(len(doc['shots']), 1)
        rows = doc['shots'][0].get('dialogues', [])
        self.assertEqual([(r['speaker_name'], r['text']) for r in rows],
                         [('张三', '第一句独有台词。'), ('李四', '第二句独有台词。')])
        payload = bridge.to_compiler_input(doc)
        description = payload['shots'][0]['description']
        self.assertIn('张三：第一句独有台词。', description)
        self.assertIn('李四：第二句独有台词。', description)
        self.assertLess(description.index('第一句'), description.index('第二句'))
        shotlist = bridge.to_shotlist_md(doc)
        self.assertIn('第一句独有台词。', shotlist)
        self.assertIn('第二句独有台词。', shotlist)

    def test_altered_earlier_line_is_rejected(self):
        doc = bridge.parse_screenplay(SCRIPT)
        if doc['shots'][0].get('dialogues'):
            doc['shots'][0]['dialogues'][0]['text'] = '编造的台词'
        codes = {v['code'] for v in bridge.validate(doc, SCRIPT)}
        self.assertIn('DIALOGUE_NOT_VERBATIM', codes)

    def test_legacy_single_dialogue_input_remains_supported(self):
        doc = bridge.parse_screenplay(SCRIPT)
        doc['shots'][0].pop('dialogues', None)
        payload = bridge.to_compiler_input(doc)
        self.assertIn('第二句独有台词。', payload['shots'][0]['description'])
        self.assertFalse(any(v['level'] == 'fail' for v in bridge.validate(doc, SCRIPT)))

    def test_parsed_camera_and_cast_reach_real_ir(self):
        doc = bridge.parse_screenplay(SCRIPT)
        spec = {item['id']: item['name'] for key in ['characters', 'props', 'scenes']
                for item in doc[key]}
        payload = bridge.to_compiler_input(doc, asset_spec=spec)
        self.assertEqual(payload['shots'][0].get('camera'),
                         {'shot_scale': 'MS', 'movement': 'static'})
        self.assertEqual(payload['shots'][0].get('asset_refs'), [
            {'entity_id': 'char_01', 'version': 1},
            {'entity_id': 'char_02', 'version': 1},
            {'entity_id': 'loc_01', 'version': 1}])
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(payload, Path(temp))
            self.assertEqual(result['gate']['status'], 'PASS', result['gate'])
            ir = production_ir.build(temp)
        self.assertEqual(ir['shots'][0]['camera_spec']['value']['shot_size'], 'MS')
        self.assertEqual(len(ir['shots'][0]['asset_refs']['character_refs']), 2)
        self.assertIn('第一句独有台词。', production_ir.render(ir))
        self.assertIn('第二句独有台词。', production_ir.render(ir))

if __name__ == '__main__':
    unittest.main()
