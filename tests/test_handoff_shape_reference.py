"""Published handoff shape agrees with the runtime at observed model failure boundaries."""
import copy,json,unittest
from pathlib import Path
from jsonschema import Draft202012Validator,ValidationError
from scripts.intent_handoff import validate_intent_handoff,IntentHandoffError
from tests.test_rework_application import intent
ROOT=Path(__file__).resolve().parents[1]
class HandoffShapeReferenceTests(unittest.TestCase):
    def setUp(self):
        self.schema=Draft202012Validator(json.loads((ROOT/'schemas/intent_handoff.schema.json').read_text(encoding='utf-8')))
    def test_style_reference_rejects_the_observed_string_and_accepts_real_object(self):
        good=intent();self.schema.validate(good);validate_intent_handoff(good)
        bad=copy.deepcopy(good);bad['decisions']['visual_style']['value']='木刻'
        with self.assertRaises(IntentHandoffError):validate_intent_handoff(bad)
        with self.assertRaises(ValidationError):self.schema.validate(bad)
    def test_sound_reference_uses_the_actual_runtime_modes_at_both_scopes(self):
        for mode in ('silent','ambience_only','dialogue_allowed','unspecified'):
            good=intent();good['sound']=dict(mode=mode,allowed=[],forbidden=[])
            self.schema.validate(good);validate_intent_handoff(good)
        for scope in ('project','shot'):
            bad=intent();sound=dict(mode='restricted_diegetic',allowed=['water'],forbidden=[])
            if scope=='project':bad['sound']=sound
            else:bad['shots'][0]['sound']=sound
            with self.assertRaises(IntentHandoffError):validate_intent_handoff(bad)
            with self.assertRaises(ValidationError):self.schema.validate(bad)
    def test_style_specialization_preserves_generic_decision_contract(self):
        bad=intent();bad['decisions']['visual_style'].pop('source')
        with self.assertRaises(ValidationError):self.schema.validate(bad)
        bad=intent();bad['decisions']['visual_style']['locked']='yes'
        with self.assertRaises(ValidationError):self.schema.validate(bad)
    def test_style_whitespace_is_not_a_user_style(self):
        bad=intent();bad['decisions']['visual_style']['value']['text']='  \t'
        with self.assertRaises(IntentHandoffError):validate_intent_handoff(bad)
        with self.assertRaises(ValidationError):self.schema.validate(bad)
if __name__=='__main__':unittest.main()
