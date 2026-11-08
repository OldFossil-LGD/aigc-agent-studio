"""Synthetic graph mutations used by the offline fidelity regression."""
import copy

def overbuild_2x(source):
    nodes, edges = [], []
    for copy_index in range(2):
        suffix = '__copy%d' % copy_index
        for original in source['nodes']:
            node = copy.deepcopy(original)
            node['id'] = str(node['id']) + suffix
            nodes.append(node)
        for original in source['edges']:
            edge = copy.deepcopy(original)
            edge['id'] = str(edge.get('id', 'edge')) + suffix
            edge['source'] = str(edge['source']) + suffix
            edge['target'] = str(edge['target']) + suffix
            edges.append(edge)
    return {'nodes': nodes, 'edges': edges}

def underbuild_60pct(source):
    result = copy.deepcopy(source)
    result['nodes'] = result['nodes'][:int(len(result['nodes']) * 0.6)]
    ids = {node['id'] for node in result['nodes']}
    result['edges'] = [edge for edge in result['edges'] if edge['source'] in ids and edge['target'] in ids]
    return result

def schema_mismatch(source):
    result = copy.deepcopy(source)
    for node in result['nodes']:
        if 'type' in node:
            node['node_type'] = node.pop('type')
    return result

def lineage_variant(source, every):
    result = copy.deepcopy(source)
    for index, node in enumerate(result['nodes']):
        node.pop('source_node_id', None)
        if every and index % every == 0:
            node['source_node_id'] = node['id']
    return result

DERIVATIONS = {
    'overbuild_2x': overbuild_2x,
    'underbuild_60pct': underbuild_60pct,
    'schema_mismatch': schema_mismatch,
    'mirror_plan_linked': lambda graph: lineage_variant(graph, 1),
    'mirror_plan_unlinked': lambda graph: lineage_variant(graph, 0),
    'mirror_plan_half_mapped': lambda graph: lineage_variant(graph, 2),
}
