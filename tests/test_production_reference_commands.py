"""The executable plan must retain declared media-reference edges."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.compile_production import compile_production
from scripts.compile_libtv_commands import compile_commands
from scripts.workflow_graph_ir import build_legacy_v1


class ProductionReferenceCommandTests(unittest.TestCase):
    def test_actual_full_film_edges_survive_command_compilation(self):
        data = {
            'goal': 'Synthetic full film reference test', 'duration_sec': 5,
            'entities': [
                {'id': 'hero', 'kind': 'character', 'description': 'Blue-coated adult', 'requires_iteration': True},
                {'id': 'room', 'kind': 'scene', 'description': 'A blue room'}],
            'shots': [{'id': 's1', 'duration_sec': 5, 'description': 'The adult stands in the room'}],
            'delivery': {'ignition_allowed': False}}
        purposes = {'asset_refine', 'asset_character', 'asset_scene', 'scene',
                    'identity', 'composition', 'refine', 'state', 'image_reference', 'prompt'}
        with tempfile.TemporaryDirectory() as temp:
            result = compile_production(data, Path(temp))
            self.assertEqual(result['gate']['status'], 'PASS', result['gate'])
            plan = json.loads((Path(temp) / '08_libtv_command_plan.json').read_text(encoding='utf-8'))
        bindings = plan['binding_map']
        links = {(row['left'], row['target']) for row in plan['commands'] if row['kind'] == 'node_link'}
        selected = [edge for edge in result['graph']['edges'] if edge['purpose'] in purposes]
        self.assertEqual({edge['purpose'] for edge in selected}, purposes)
        for edge in selected:
            with self.subTest(edge=edge):
                self.assertIn((bindings[edge['source']], bindings[edge['target']]), links)
        self.assertTrue(all(not row['run'] for row in plan['commands']))
        ir = build_legacy_v1(result['graph'])
        for before, after in zip(result['graph']['edges'], ir['edges']):
            if before['purpose'] in purposes:
                self.assertEqual(after['kind'], 'data_reference')

    def test_control_and_unknown_purposes_stay_out_of_physical_links(self):
        graph = {'nodes': [{'id': 'a', 'node_type': 'text'}, {'id': 'b', 'node_type': 'image'}],
                 'edges': [{'source': 'a', 'target': 'b', 'purpose': purpose}
                           for purpose in ['asset_manifest', 'qa', 'selection_record', 'unregistered-purpose']]}
        plan = compile_commands(graph)
        self.assertFalse(any(row['kind'] == 'node_link' for row in plan['commands']))
        self.assertEqual(len(plan['skipped_links']), 4)


if __name__ == '__main__':
    unittest.main()
