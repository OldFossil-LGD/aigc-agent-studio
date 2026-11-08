"""Codex independent regression audit for the Hermes contract-coverage implementation."""
import copy
import unittest

from scripts.production_capability_gate import evaluate
from tests.test_graph_integrity import build_plan


class ContractCoverageAuditTests(unittest.TestCase):
    def assert_blocked(self, plan, code):
        result = evaluate(*plan)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn(code, {item['code'] for item in result['failures']})

    def test_normal_compiled_plan_passes(self):
        self.assertEqual(evaluate(*build_plan())['status'], 'PASS')

    def test_empty_graph_is_rejected(self):
        contract, _, _, _ = build_plan()
        self.assert_blocked((contract, {'assets': []}, {'nodes': [], 'edges': [], 'shots': []}, []),
                            'EMPTY_PRODUCTION_GRAPH')

    def test_missing_graph_shot_manifest_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        graph['shots'] = []
        self.assert_blocked((contract, assets, graph, prompts), 'MISSING_GRAPH_SHOT')

    def test_missing_assets_are_rejected(self):
        contract, assets, graph, prompts = build_plan()
        assets['assets'] = []
        self.assert_blocked((contract, assets, graph, prompts), 'MISSING_ASSET_FOR_ENTITY')

    def test_contract_graph_shot_id_disagreement_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        contract['shots'][0]['id'] = 'absent_from_graph'
        result = evaluate(contract, assets, graph, prompts)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue({'MISSING_GRAPH_SHOT', 'EXTRA_GRAPH_SHOT'} <=
                        {item['code'] for item in result['failures']})

    def test_graph_cannot_waive_contract_identity_role(self):
        contract, assets, graph, prompts = build_plan()
        removed = {node['id'] for node in graph['nodes'] if node.get('role') == 'identity_ref'}
        self.assertTrue(removed, 'Fixture must actually contain the role being removed')
        graph['nodes'] = [node for node in graph['nodes'] if node['id'] not in removed]
        graph['edges'] = [edge for edge in graph['edges']
                          if edge['source'] not in removed and edge['target'] not in removed]
        prompts = [package for package in prompts if package['node_id'] not in removed]
        for shot in graph['shots']:
            for key in ('roles', 'required_roles'):
                if key in shot:
                    shot[key] = [role for role in shot[key] if role != 'identity_ref']
                    self.assertNotIn('identity_ref', shot[key])
        self.assert_blocked((contract, assets, graph, prompts), 'MISSING_SHOT_ROLE')

    def test_malformed_contract_roles_are_rejected(self):
        contract, assets, graph, prompts = build_plan()
        contract['shots'][0]['roles'] = [{}]
        self.assert_blocked((contract, assets, graph, prompts), 'INVALID_SHOT_ROLES')

    def test_non_object_graph_shot_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        graph['shots'].append(None)
        self.assert_blocked((contract, assets, graph, prompts), 'INVALID_GRAPH_SHOT_ID')

    def test_non_object_asset_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        assets['assets'].append(None)
        self.assert_blocked((contract, assets, graph, prompts), 'INVALID_ASSET_ID')

    def test_duplicate_graph_shot_id_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        graph['shots'].append(copy.deepcopy(graph['shots'][0]))
        self.assert_blocked((contract, assets, graph, prompts), 'DUPLICATE_GRAPH_SHOT_ID')

    def test_extra_graph_shot_id_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        extra = copy.deepcopy(graph['shots'][0])
        extra['id'] = 'extra_shot'
        graph['shots'].append(extra)
        self.assert_blocked((contract, assets, graph, prompts), 'EXTRA_GRAPH_SHOT')

    def test_duplicate_asset_id_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        assets['assets'].append(copy.deepcopy(assets['assets'][0]))
        self.assert_blocked((contract, assets, graph, prompts), 'DUPLICATE_ASSET_ID')

    def test_extra_asset_id_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        extra = copy.deepcopy(assets['assets'][0])
        extra['id'] = 'extra_asset'
        assets['assets'].append(extra)
        self.assert_blocked((contract, assets, graph, prompts), 'EXTRA_ASSET')

    def test_foreign_node_shot_reference_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        node = next(node for node in graph['nodes'] if node.get('shot_id'))
        node['shot_id'] = 'foreign_shot'
        self.assert_blocked((contract, assets, graph, prompts), 'FOREIGN_SHOT_REFERENCE')

    def test_foreign_node_entity_reference_is_rejected(self):
        contract, assets, graph, prompts = build_plan()
        node = next(node for node in graph['nodes'] if node.get('entity_id'))
        node['entity_id'] = 'foreign_entity'
        self.assert_blocked((contract, assets, graph, prompts), 'FOREIGN_ENTITY_REFERENCE')

    def test_non_string_node_shot_reference_is_structured_failure(self):
        contract, assets, graph, prompts = build_plan()
        node = next(node for node in graph['nodes'] if node.get('shot_id'))
        node['shot_id'] = {'invalid': 'reference'}
        self.assert_blocked((contract, assets, graph, prompts), 'FOREIGN_SHOT_REFERENCE')

    def test_contract_authorized_roles_without_audio_pass(self):
        roles = ['storyboard', 'prompt', 'scene_ref', 'identity_ref', 'composition_ref', 'state_ref',
                 'candidate_image', 'refined_image', 'video_candidate', 'selection', 'assembly']

        def authorize(contract):
            contract['shots'][0]['roles'] = roles

        plan = build_plan(mutate_contract=authorize)
        self.assertFalse(any(node.get('role') == 'audio' and node.get('shot_id') for node in plan[2]['nodes']))
        self.assertEqual(evaluate(*plan)['status'], 'PASS')

    def test_empty_entity_set_does_not_invent_asset_coverage_errors(self):
        contract, assets, graph, prompts = build_plan()
        contract['entities'] = []
        assets['assets'] = []
        assets['iteration_chains'] = []
        if 'exemptions' in assets:
            assets['exemptions'] = []
        removed = {node['id'] for node in graph['nodes'] if node.get('entity_id')}
        graph['nodes'] = [node for node in graph['nodes'] if node['id'] not in removed]
        graph['edges'] = [edge for edge in graph['edges']
                          if edge['source'] not in removed and edge['target'] not in removed]
        prompts = [package for package in prompts if package['node_id'] not in removed]
        result = evaluate(contract, assets, graph, prompts)
        codes = {item['code'] for item in result['failures']}
        self.assertTrue({'MISSING_ASSET_FOR_ENTITY', 'EXTRA_ASSET', 'FOREIGN_ENTITY_REFERENCE'}.isdisjoint(codes))


if __name__ == '__main__':
    unittest.main()
