"""A supported generic prompt constraint must reach actual copyable candidates."""
import tempfile, unittest
from pathlib import Path
from scripts.compile_intent_delivery import compile_intent_delivery
from tests.test_rework_application import intent

class OtherConstraintDeliveryTests(unittest.TestCase):
    def test_generic_constraint_reaches_each_targeted_candidate_and_final_text(self):
        raw=intent()
        raw['constraints']=[dict(id='pace',kind='other',text='画面保持疏朗，以细小变化推进。',
            delivery='prompt',source='user_explicit',locked=True,shots=['s1','s2'],
            semantics=dict(required_all=['疏朗','细小变化']))]
        with tempfile.TemporaryDirectory() as tmp:
            result=compile_intent_delivery(raw,Path(tmp))
            self.assertEqual(result['verification']['status'],'PASS',result['verification']['failures'])
            for package in result['prompts']:
                if package['role'] in ('video_candidate','candidate_image'):
                    self.assertIn('疏朗',str(package['blocks']))
            text=(Path(tmp)/'13_Draft_Prompt.md').read_text(encoding='utf-8')
            self.assertEqual(text.count('画面保持疏朗，以细小变化推进。'),2)
