"""Graph revisions preserve semantic changes even when edge IDs stay stable."""
import copy
import unittest
from scripts.workflow_graph_ir import build_legacy_v1, diff

class GraphDifferenceTests(unittest.TestCase):
    def graph(self):
        return build_legacy_v1({'nodes':[{'id':'I','node_type':'image'},
            {'id':'V','node_type':'video'},{'id':'W','node_type':'video'}],
            'edges':[{'source':'I','target':'V','purpose':'reference'}]})

    def test_retargeted_edge_is_reported_without_being_added_or_removed(self):
        before=self.graph()
        after=copy.deepcopy(before)
        after['edges'][0]['target']['node_uid']='W'
        result=diff(before,after)
        self.assertEqual(result['edges_added'],[])
        self.assertEqual(result['edges_removed'],[])
        self.assertEqual(result.get('edges_changed',[]),[{'edge_uid':'E001',
            'changed_fields':['target'],'before':before['edges'][0],'after':after['edges'][0]}])

    def test_kind_payload_and_condition_changes_are_reported(self):
        before=self.graph()
        after=copy.deepcopy(before)
        after['edges'][0].update(kind='control_dependency',payload_type='VideoAssetRef',condition='approved')
        result=diff(before,after)
        self.assertEqual(result.get('edges_changed',[{}])[0].get('changed_fields'),
                         ['condition','kind','payload_type'])

    def test_reference_order_remains_in_its_existing_channel(self):
        before=self.graph()
        after=copy.deepcopy(before)
        after['edges'][0]['reference_order']=2
        result=diff(before,after)
        self.assertTrue(result['reference_order_changed'])
        self.assertEqual(result.get('edges_changed',[]),[])

if __name__=='__main__':
    unittest.main()
