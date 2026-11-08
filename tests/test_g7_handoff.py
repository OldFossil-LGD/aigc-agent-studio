"""Independent behavioral cases for G7 projection and media handoff (Codex audit)."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


orch = load('libtv_orchestrate.py', 'g7_audit_orch')
gate = load('libtv_model_rules_gate.py', 'g7_audit_gate')


def schema(constraints=None, require=None):
    result = {'properties': {'modeType': {'items': {'mixed2video': [1, 5]}}},
              'rules': [{'require': require or ['prompt']}]}
    if constraints is not None:
        result['properties']['mediaConstraints'] = {'mixed2video': {'video': constraints}}
    return result


def target(refs=('source',)):
    return {'id': 'target', 'nodeType': 'video', 'prompt': 'synthetic audited prompt',
            'params': {'model': 'audit-model', 'modeType': 'mixed2video'}, 'refs': list(refs)}


def video(url='synthetic.mp4', meta=None, node_id='source'):
    node = {'id': node_id, 'nodeType': 'video', 'data': {'url': url}}
    if meta is not None:
        node['resourceMeta'] = {'items': [meta]}
    return node


def routed(nodes, model_schema):
    original = copy.deepcopy(nodes)
    with tempfile.TemporaryDirectory(prefix='g7-test-') as temporary:
        (Path(temporary) / 'audit-model.json').write_text(json.dumps(model_schema), encoding='utf-8')
        result, findings = orch.g7_per_node(nodes, temporary)
    assert nodes == original, 'Routing mutated the input spec'
    return result['target'], findings


class G7HandoffTests(unittest.TestCase):
    def test_text_string_survives_projection_and_real_routing(self):
        nodes = [{'id': 'source', 'nodeType': 'text', 'data': {'content': 'synthetic text'}}, target()]
        nodes[-1]['prompt'] = ''
        nodes[-1]['params']['modeType'] = 'text2video'
        row, _ = routed(nodes, schema(require=['prompt']))
        self.assertEqual(row['state'], 'pass')

    def test_text_array_is_normalized_by_existing_gate(self):
        nodes = [{'id': 'source', 'nodeType': 'text', 'data': {'content': [None, 'actual text', 3]}}, target()]
        graph = orch.spec_gate_graph(nodes, 'target')
        result = gate.counts_from_graph(graph)
        self.assertEqual(result['lists']['textList'][0]['content'], ['actual text'])
        self.assertTrue(result['ctxFromGraph']['prompt'])

    def test_empty_text_does_not_invent_prompt(self):
        for content in ('', [], None, [1, None]):
            with self.subTest(content=content):
                nodes = [{'id': 'source', 'nodeType': 'text', 'data': {'content': content}}, target()]
                nodes[-1]['prompt'] = ''
                nodes[-1]['params']['modeType'] = 'text2video'
                row, _ = routed(nodes, schema(require=['prompt']))
                self.assertEqual(row['state'], 'FAIL')

    def test_group_child_text_survives(self):
        nodes = [{'id': 'group', 'nodeType': 'group'},
                 {'id': 'text', 'nodeType': 'text', 'parentId': 'group', 'data': {'content': ['inside group']}},
                 target(('group',))]
        self.assertTrue(gate.counts_from_graph(orch.spec_gate_graph(nodes, 'target'))['ctxFromGraph']['prompt'])

    def test_bad_format_reaches_real_per_node_gate(self):
        constraints = {'formats': {'allowed': ['mp4', 'mov'], 'action': 'block', 'message': 'SYNTHETIC FORMAT'}}
        row, findings = routed([video('synthetic.avi'), target()], schema(constraints))
        self.assertEqual(row['state'], 'FAIL')
        self.assertIn('SYNTHETIC FORMAT', row['reasons'])
        self.assertTrue(any(x['level'] == 'FAIL' for x in findings))

    def test_video_url_array_uses_first_entry(self):
        constraints = {'formats': {'allowed': ['mp4'], 'action': 'block', 'message': 'FIRST URL'}}
        row, _ = routed([video(['synthetic.avi', 'synthetic.mp4']), target()], schema(constraints))
        self.assertEqual(row['state'], 'FAIL')
        self.assertIn('FIRST URL', row['reasons'])

    def test_duration_from_first_resource_metadata_item(self):
        constraints = {'duration': {'min': 3, 'max': 10, 'action': 'block', 'message': 'SYNTHETIC DURATION'}}
        source = video(meta={'durationSec': 20})
        source['resourceMeta']['items'].append({'durationSec': 5})
        row, _ = routed([source, target()], schema(constraints))
        self.assertEqual(row['state'], 'FAIL')
        self.assertIn('SYNTHETIC DURATION', row['reasons'])

    def test_known_metadata_can_pass_all_applicable_media_checks(self):
        constraints = {'formats': {'allowed': ['mp4'], 'action': 'block'},
                       'duration': {'min': 3, 'max': 10, 'action': 'block'},
                       'height': {'min': 720, 'max': 2160, 'action': 'block'}}
        row, _ = routed([video(meta={'durationSec': 5, 'height': 1080}), target()], schema(constraints))
        self.assertEqual(row['state'], 'pass')
        self.assertEqual(row['layers']['media']['state'], 'pass')

    def test_warn_is_retained_without_becoming_failure(self):
        constraints = {'height': {'min': 720, 'action': 'warn', 'message': 'SYNTHETIC HEIGHT WARNING'}}
        row, findings = routed([video(meta={'height': 500}), target()], schema(constraints))
        self.assertNotEqual(row['state'], 'FAIL')
        self.assertEqual(row['layers']['media']['state'], 'warn')
        self.assertIn('SYNTHETIC HEIGHT WARNING', json.dumps([row, findings]))

    def test_missing_duration_is_not_reported_as_full_pass(self):
        constraints = {'duration': {'min': 3, 'max': 10, 'action': 'block'}}
        row, findings = routed([video(), target()], schema(constraints))
        self.assertIn(row['state'], ('not_verified', 'partial'))
        self.assertIs(row['layers']['media']['complete'], False)
        self.assertTrue(any(x['level'] == 'WARN' for x in findings))

    def test_partial_metadata_is_not_reported_as_full_pass(self):
        constraints = {'duration': {'min': 3, 'max': 10, 'action': 'block'},
                       'height': {'min': 720, 'action': 'block'}}
        row, _ = routed([video(meta={'durationSec': 5}), target()], schema(constraints))
        self.assertIn(row['state'], ('not_verified', 'partial'))

    def test_only_incoming_nonvirtual_materials_are_checked(self):
        constraints = {'formats': {'allowed': ['mp4'], 'action': 'block'}}
        nodes = [video(), video('unrelated.avi', node_id='other'), target()]
        row, _ = routed(nodes, schema(constraints))
        self.assertEqual(row['state'], 'pass')
        nodes[-1]['refs'].append('other')
        nodes[-1]['refEdgeData'] = {'other': {'assetVirtual': True}}
        row, _ = routed(nodes, schema(constraints))
        self.assertEqual(row['state'], 'pass')

    def test_group_video_metadata_reaches_media_layer(self):
        constraints = {'duration': {'max': 10, 'action': 'block', 'message': 'GROUP DURATION'}}
        source = video(meta={'durationSec': 20})
        source['parentId'] = 'group'
        row, _ = routed([{'id': 'group', 'nodeType': 'group'}, source, target(('group',))], schema(constraints))
        self.assertEqual(row['state'], 'FAIL')
        self.assertIn('GROUP DURATION', row['reasons'])

    def test_no_media_constraint_remains_compatible(self):
        row, _ = routed([video(), target()], schema())
        self.assertEqual(row['state'], 'pass')

    def test_layer_details_are_retained_for_the_consumer(self):
        row, _ = routed([video(), target()], schema())
        self.assertEqual(set(row['layers']), {'ranges', 'configs', 'media', 'rules'})

    def test_explicit_legacy_materials_still_block(self):
        model_schema = schema({'formats': {'allowed': ['mp4'], 'action': 'block', 'message': 'EXPLICIT FORMAT'}})
        result = gate.evaluate(model_schema, {'prompt': True}, 'mixed2video', materials=[{'url': 'synthetic.avi'}])
        self.assertEqual(result['exit_code'], 1)
        self.assertIn('EXPLICIT FORMAT', result['reasons'])

    def test_missing_url_keeps_legacy_skip_without_claiming_complete(self):
        model_schema = schema({'duration': {'max': 10, 'action': 'block'}})
        layer = gate.evaluate_media(model_schema, 'mixed2video', [{'url': '', 'durationSec': 99}])
        self.assertEqual(layer['state'], 'pass')
        self.assertIs(layer['complete'], False)

    def test_no_supplied_materials_are_not_complete(self):
        model_schema = schema({'duration': {'max': 10, 'action': 'block'}})
        layer = gate.evaluate_media(model_schema, 'mixed2video', None)
        self.assertEqual(layer['state'], 'skipped')
        self.assertIs(layer['complete'], False)

    def test_invalid_gate_evidence_does_not_become_pass(self):
        original = orch._run_gate
        try:
            for stdout in ('not json', '{}', '{"layers": null}'):
                with self.subTest(stdout=stdout):
                    orch._run_gate = lambda *args, **kwargs: (0, stdout)
                    row, findings = routed([video(), target()], schema())
                    self.assertIn(row['state'], ('not_verified', 'partial'))
                    self.assertTrue(any(x['level'] == 'WARN' for x in findings))
        finally:
            orch._run_gate = original


if __name__ == '__main__':
    unittest.main()
