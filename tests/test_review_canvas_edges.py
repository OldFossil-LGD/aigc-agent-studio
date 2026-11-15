"""Independent physical graph and read-failure regressions, entirely offline."""
import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import libtv_canvas_build as canvas, wiring_plan
from tests.test_libtv_execution_integrity import CanvasCLI, prop_document, apply_options


class CanvasEdgeReviewTests(unittest.TestCase):
    def setUp(self):
        self.doc = prop_document()
        self.doc['assets'][1].update(role='closeup', layer=2, parent='A')
        self.cli = CanvasCLI()
        with patch.object(canvas, '_run', side_effect=self.cli), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.apply(self.doc, apply_options()), 0)
        # This graph is independent of the node parameter arrays.
        self.edges = [{'id': 'edge-1', 'source': 'id-1', 'target': 'id-2'}]

    def audit(self, transform=None):
        count = 0
        def call(args):
            nonlocal count
            code, body = self.cli(args)
            if args[0] == 'project':
                count += 1
                body['edges'] = copy.deepcopy(self.edges)
                if transform:
                    code, body = transform(count, code, body)
            return code, body
        with patch.object(canvas, '_run', side_effect=call), contextlib.redirect_stdout(io.StringIO()):
            return canvas.audit_canvas('P', self.doc)

    def test_valid_physical_graph_passes(self):
        self.assertEqual(self.audit(), 0)

    def test_missing_physical_edge_fails_with_unchanged_reference_order(self):
        self.edges.clear()
        self.assertEqual(self.cli.nodes['id-2']['params']['imageListOrder'], ['id-1'])
        self.assertEqual(self.audit(), canvas.RC_FAIL)

    def test_extra_incoming_edge_on_root_fails(self):
        self.edges.append({'id': 'edge-2', 'source': 'id-2', 'target': 'id-1'})
        self.assertEqual(self.audit(), canvas.RC_FAIL)

    def test_duplicate_physical_edge_fails(self):
        self.edges.append(dict(self.edges[0], id='edge-2'))
        self.assertEqual(self.audit(), canvas.RC_FAIL)

    def test_unrelated_scoped_graph_is_ignored(self):
        self.cli.nodes['x'] = {'id': 'x', 'name': 'other', 'type': 'image', 'params': {}}
        self.edges.append({'id': 'edge-other', 'source': 'id-1', 'target': 'x'})
        self.assertEqual(self.audit(), 0)

    def test_physical_edge_drift_fails(self):
        def drift(count, code, body):
            if count > 1:
                body['edges'][0]['id'] = 'replaced-edge'
            return code, body
        self.assertEqual(self.audit(drift), canvas.RC_FAIL)

    def test_unrelated_geometry_and_edges_may_change(self):
        self.cli.nodes['x'] = {'id': 'x', 'name': 'other', 'type': 'image', 'params': {}}
        def drift(count, code, body):
            body['nodes'][-1]['position'] = {'x': count, 'y': 0}
            if count > 1:
                body['edges'].append({'id': 'other-edge', 'source': 'id-1', 'target': 'x'})
            return code, body
        self.assertEqual(self.audit(drift), 0)

    def test_owned_geometry_drift_without_declared_position_fails(self):
        def drift(count, code, body):
            body['nodes'][0]['position'] = {'x': count, 'y': 0}
            return code, body
        self.assertEqual(self.audit(drift), canvas.RC_FAIL)

    def test_malformed_graph_and_failed_reads_fail(self):
        variants = [(1, {}), (0, {}), (0, {'nodes': [], 'edges': []}),
                    (0, {'nodes': [], 'edges': 'bad'}), (0, [])]
        for result in variants:
            with self.subTest(result=result):
                self.assertEqual(self.audit(lambda *args: copy.deepcopy(result)), canvas.RC_FAIL)
        for edge in ({}, {'source': 'missing', 'target': 'id-2'},
                     {'source': [], 'target': 'id-2'},
                     {'source': 'id-1', 'target': 'id-2'},
                     {'id': False, 'source': 'id-1', 'target': 'id-2'}):
            self.edges = [edge]
            with self.subTest(edge=edge):
                self.assertEqual(self.audit(), canvas.RC_FAIL)

    def test_asset_id_takes_precedence_over_same_shot_id(self):
        self.doc['shots'] = [{'id': 'A', 'prompt': 'shot', 'reference_plan': {
            'assets': ['A'], 'primary_asset_id': 'A', 'prompt_refs': ['{{Image 1}}']}}]
        self.assertEqual(canvas.validate(self.doc)[0], [])
        self.assertEqual(canvas._workflow_errors(self.doc), [])

    def test_captured_project_shape_can_be_audited(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/libtv_platform_projection.json').read_text(encoding='utf-8'))
        project = fixture['project']
        owned = project['nodes'][0]
        doc = {'props': [{'id': 'P', 'name': 'captured'}], 'assets': [{
            'asset_id': 'A', 'kind': 'prop', 'subject': 'P', 'role': 'anchor',
            'layer': 1, 'prompt': 'p'}], 'shots': []}
        name = canvas._asset_names(doc)['A']
        owned['name'] = name
        # Scope the fixture to a root node, retaining the captured envelope.
        project['edges'] = [edge for edge in project['edges'] if edge['target'] != owned['id']]
        detail = copy.deepcopy(fixture['node_detail'])
        detail.update(nodeKey=owned['id'], nodeType='image', name=name)
        detail['data'].update(name=name, params={'prompt': 'p', 'imageListOrder': []})
        listing = {'nodes': [dict(owned, type='image')]}
        def call(args):
            if args[0] == 'project':
                return 0, project
            return (0, listing) if args[1] == 'list' else (0, detail)
        with patch.object(canvas, '_run', side_effect=call), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(canvas.audit_canvas('P', doc), 0)


class WiringReadFailureTests(unittest.TestCase):
    def test_failed_project_read_cannot_be_an_empty_success(self):
        result = SimpleNamespace(returncode=1, stdout=b'{"error":"no access"}')
        with patch.object(wiring_plan.proc, 'run', return_value=result), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wiring_plan.canvas_integrity('P'), wiring_plan.RC_FAIL)

    def test_empty_reference_order_cannot_hide_a_physical_incoming_edge(self):
        nodes = {'A': {'type': 'image'}, 'B': {'type': 'video'}}
        report = wiring_plan.integrity_report(
            nodes, {'A': 'A', 'B': 'B'}, {'B': []},
            [{'source': 'A', 'target': 'B'}])
        self.assertEqual(report['order_mismatch'], ['B'])

    def test_failed_or_malformed_detail_cannot_pass(self):
        meta = {'nodes': [{'id': 'A', 'name': 'A', 'type': 'image'}], 'edges': []}
        for code, payload in [(-9, b''), (1, b'{}'), (0, b'bad'),
                              (0, b'[]'), (0, b'{}'),
                              (0, b'{"data":{"params":{"imageListOrder":"bad"}}}')]:
            def call(args, **kwargs):
                if args[1] == 'project':
                    return SimpleNamespace(returncode=0, stdout=json.dumps(meta).encode())
                return SimpleNamespace(returncode=code, stdout=payload)
            with self.subTest(code=code, payload=payload), patch.object(wiring_plan.proc, 'run', side_effect=call), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(wiring_plan.canvas_integrity('P'), wiring_plan.RC_FAIL)


if __name__ == '__main__':
    unittest.main()
