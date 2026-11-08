"""Regression for actual C01 camera wording; scope remains finite."""
import unittest
from scripts.constraint_semantics import evaluate_constraint

class FixedCameraSemanticsTests(unittest.TestCase):
    def test_observed_immobile_eye_level_camera_is_delivered(self):
        result = evaluate_constraint('固定平视，机位不移动，不要俯拍。',
                                     {'required_all': ['固定机位', '平视'], 'forbidden': ['俯拍']})
        self.assertTrue(result['ok'], result)

    def test_negated_fixed_camera_does_not_satisfy_requirement(self):
        for text in ('不要机位不移动。', '不要固定机位。'):
            with self.subTest(text=text):
                self.assertFalse(evaluate_constraint(text, {'required_all': ['固定机位']})['ok'])

    def test_fixed_camera_alias_does_not_supply_eye_level_or_hide_overhead(self):
        self.assertFalse(evaluate_constraint('机位不移动。', {'required_all': ['固定机位', '平视']})['ok'])
        result = evaluate_constraint('机位不移动，正上方俯视。',
                                     {'required_all': ['固定机位'], 'forbidden': ['俯拍']})
        self.assertTrue(result['required_satisfied'])
        self.assertFalse(result['ok'])

    def test_internal_negation_does_not_spread_into_parallel_affirmation(self):
        text = '机位不移动并保持平视，不要俯拍。'
        result = evaluate_constraint(text, {'required_all': ['固定机位', '平视'], 'forbidden': ['俯拍']})
        self.assertTrue(result['ok'], result)
        self.assertFalse(evaluate_constraint('机位不移动并配有旁白。', {'forbidden': ['旁白']})['ok'])

    def test_internal_negation_still_prohibits_motion_inside_the_phrase(self):
        self.assertTrue(evaluate_constraint('机位不移动。', {'forbidden': ['移动']})['ok'])
        self.assertFalse(evaluate_constraint('机位不移动并且主体移动。', {'forbidden': ['移动']})['ok'])
        self.assertFalse(evaluate_constraint('不要机位不移动。', {'required_all': ['固定机位']})['ok'])
