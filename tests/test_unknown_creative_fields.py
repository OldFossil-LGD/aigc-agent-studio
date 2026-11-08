import copy
import json
import unittest
from pathlib import Path
from scripts.intent_handoff import IntentHandoffError, validate_intent_handoff, to_compiler_input
ROOT = Path(__file__).resolve().parents[1]
class UnknownCreativeFieldTests(unittest.TestCase):
    def sample(self): return json.loads((ROOT / 'samples/papercut_empty_shot_intent.json').read_text(encoding='utf-8'))
    def test_unknown_shot_instruction_is_not_silently_dropped(self):
        raw = self.sample(); raw['shots'][0]['unmapped_lighting_instruction'] = 'Keep the practical lamp warm'
        with self.assertRaises(IntentHandoffError): validate_intent_handoff(raw)
    def test_unknown_task_instruction_is_not_silently_dropped(self):
        raw = self.sample(); raw['unmapped_editing_intention'] = 'A visible match cut'
        with self.assertRaises(IntentHandoffError): validate_intent_handoff(raw)
    def test_declared_audit_metadata_stays_out_of_prompt_input(self):
        raw = self.sample(); raw['shots'][0]['audit'] = {'private_note': 'not prompt text'}
        data = to_compiler_input(raw)
        self.assertNotIn('audit', data['shots'][0])
if __name__ == '__main__': unittest.main()
