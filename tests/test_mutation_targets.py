"""Mutation targets isolate the changed rule from catalog and platform setup."""
import unittest

from scripts import delivery_contract, final_delivery_audit, libtv_canvas_build


class MutationTargetTests(unittest.TestCase):
    def test_film_without_authoritative_target_is_blocked(self):
        contract = delivery_contract.derive({}, 'film')
        result = delivery_contract.validate(contract, {}, 'film', None, ['clip.mp4'])
        self.assertIsInstance(result, dict)
        self.assertEqual(result['status'], 'BLOCKED')

    def test_placeholder_paragraph_is_identified(self):
        result = final_delivery_audit._placeholder_line('# Review\nCompleted prose.\nTODO\n')
        self.assertEqual(result, (3, 'TODO'))

    def test_overlapping_rectangles_are_reported(self):
        document = {'assets': [
            {'asset_id': 'A', 'position': {'x': 0, 'y': 0, 'w': 100, 'h': 100}},
            {'asset_id': 'B', 'position': {'x': 50, 'y': 50, 'w': 100, 'h': 100}},
        ], 'shots': []}
        errors = libtv_canvas_build._layout_errors(document, {'A': 'First', 'B': 'Second'})
        self.assertEqual(len(errors), 1)
        self.assertIn('First', errors[0])
        self.assertIn('Second', errors[0])

    def test_missing_parent_is_reported(self):
        document = {'assets': [{'asset_id': 'A', 'parent': 'MISSING'}], 'shots': []}
        errors = libtv_canvas_build._workflow_errors(document)
        self.assertTrue(any('MISSING' in error for error in errors), errors)


if __name__ == '__main__':
    unittest.main()
