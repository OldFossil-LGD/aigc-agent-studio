"""Run the real readers against a captured LibTV CLI payload.

The fixture records the platform's *shape*, not its content: values are replaced,
nesting and types are verbatim. These tests feed that payload through the actual
code paths, so the fixture pins behaviour instead of restating key lists.

A committed fixture cannot notice the platform changing under it. Drift needs a
fresh capture: python scripts/capture_libtv_projection.py --check
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_libtv_plan as plan
import wiring_plan

FIXTURE = json.loads(
    (ROOT / 'tests' / 'fixtures' / 'libtv_platform_projection.json').read_text(encoding='utf-8'))
LISTING = FIXTURE['node_list']
DETAIL = FIXTURE['node_detail']
PROJECT = FIXTURE['project']
FIRST = LISTING['nodes'][0]


def stub_read_json(args):
    """Serve the captured payloads exactly as the CLI would."""
    # args[0] 是可执行文件路径（可能被解析成绝对路径），只按子命令分派。
    if args[1:3] == ['node', 'list']:
        return LISTING
    if args[1] == 'project':
        return PROJECT
    return DETAIL


class DriftCheckerTests(unittest.TestCase):
    """漂移比对本身要能被证伪，否则它只是一个永远说'一致'的函数。"""

    def test_added_key_is_reported(self):
        live = {'a': 1, 'b': 'x'}
        stored = {'a': 1}
        self.assertTrue(any('新增' in line for line in diff_shape(live, stored)))

    def test_removed_key_is_reported(self):
        live = {'a': 1}
        stored = {'a': 1, 'b': 'x'}
        self.assertTrue(any('已移除' in line for line in diff_shape(live, stored)))

    def test_type_change_is_reported(self):
        live = {'a': 'text'}
        stored = {'a': [1]}
        self.assertTrue(any('类型' in line for line in diff_shape(live, stored)))

    def test_second_list_item_drift_is_reported(self):
        """只看首项会漏掉这项——这正是真实回包里最容易被忽略的位置。"""
        stored = {'nodes': [{'id': 1}, {'id': 2}]}
        live = {'nodes': [{'id': 1}, {'id': 2, 'type': 'x'}]}
        lines = diff_shape(live, stored)
        self.assertTrue(any('[1]' in line for line in lines), lines)

    def test_nested_note_is_not_exempt(self):
        """只有夹具根级说明可以跳过；回包内部的 note 必须参与比较。"""
        lines = diff_shape({'a': {'note': 'x'}}, {'a': {}})
        self.assertTrue(any('note' in line for line in lines), lines)

    def test_root_note_stays_exempt(self):
        self.assertEqual(diff_shape({'note': 'a', 'x': 1}, {'note': 'b', 'x': 1}), [])

    def test_list_length_change_is_reported(self):
        lines = diff_shape({'nodes': [{'id': 1}]}, {'nodes': [{'id': 1}, {'id': 2}]})
        self.assertTrue(any('元素数' in line for line in lines), lines)

    def test_identical_shape_is_clean(self):
        self.assertEqual(diff_shape({'a': [{'b': 1}]}, {'a': [{'b': 2}]}), [])


class FixtureFidelityTests(unittest.TestCase):
    """夹具必须是真实回包本身，不能是重建出来的近似物。"""

    def test_node_list_keeps_the_real_top_level_fields(self):
        for key in ('count', 'projectUuid', 'scope', 'nodes'):
            self.assertIn(key, FIXTURE['node_list'])

    def test_node_list_length_matches_what_was_captured(self):
        self.assertEqual(len(FIXTURE['node_list']['nodes']), FIXTURE['captured_from']['nodes'])

    def test_project_keeps_the_real_graph(self):
        self.assertEqual(len(FIXTURE['project']['edges']), FIXTURE['captured_from']['edges'])


class CapturedPayloadTests(unittest.TestCase):
    def test_existing_nodes_runs_on_the_captured_payloads(self):
        position = PROJECT['nodes'][0]['position']
        command = {'kind': 'node_create', 'name': FIRST['name'], 'node_type': FIRST['type'],
                   'position': position}
        skipped = plan._existing_nodes('P', [command], read_json=stub_read_json)
        self.assertEqual(skipped, {FIRST['name']})

    def test_position_survives_only_through_the_project_merge(self):
        self.assertIsNone(plan._geometry(DETAIL))            # 详情本身没有坐标
        self.assertIsNotNone(plan._geometry(PROJECT['nodes'][0]))

    def test_detail_is_identified_by_node_key(self):
        self.assertEqual(plan._detail_key(DETAIL), DETAIL['nodeKey'])
        self.assertNotIn('id', DETAIL)

    def test_params_are_read_from_the_detail_payload(self):
        params = plan._node_params(DETAIL)
        self.assertIsInstance(params, dict)
        self.assertIn('imageListOrder', params)
        self.assertIsInstance(params['imageListOrder'], list)

    def test_integrity_runs_on_the_captured_graph(self):
        nodes = {n['id']: n for n in PROJECT['nodes']}
        names = {key: value['name'] for key, value in nodes.items()}
        report = wiring_plan.integrity_report(nodes, names, {}, PROJECT['edges'])
        self.assertEqual(report['unknown_endpoints'], 0)

    def test_dangling_edge_is_detected(self):
        nodes = {n['id']: n for n in PROJECT['nodes']}
        names = {key: value['name'] for key, value in nodes.items()}
        broken = list(PROJECT['edges']) + [{'id': 'edge-x', 'source': FIRST['id'],
                                            'target': 'node-does-not-exist'}]
        report = wiring_plan.integrity_report(nodes, names, {}, broken)
        self.assertEqual(report['unknown_endpoints'], 1)


# --- 漂移检测 -------------------------------------------------------------
# 提交在仓库里的夹具是**历史快照**，平台改形状它不会自己变红。
# 漂移只能靠重新抓取比对：
#   python tests/test_platform_projection_contract.py --check   （需要已授权的 CLI）
#   python tests/test_platform_projection_contract.py --refresh （重写夹具）

CANVAS_UUID = '02e2eca2f8cc4ce887049e9108bf4bb9'


def _cli_json(*args):
    import subprocess
    result = subprocess.run(['libtv'] + list(args), capture_output=True, timeout=180)
    text = result.stdout.decode('utf-8', 'replace').strip()
    if not text:
        raise RuntimeError('libtv 无输出（是否未登录？先运行 libtv account info）')
    return json.loads(text)


def _sanitize(obj, ids, names, key=None):
    """值脱敏，结构/嵌套/类型原样保留（**不截断**：截断会掩盖对象特有结构）。"""
    if isinstance(obj, dict):
        return {k: _sanitize(v, ids, names, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v, ids, names, key) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, str):
        if key in ('id', 'nodeKey', 'source', 'target'):
            ids.setdefault(obj, 'node-%d' % (len(ids) + 1))
            return ids[obj]
        if key in ('name', 'nodeName'):
            names.setdefault(obj, '节点_%d' % (len(names) + 1))
            return names[obj]
        if key in ('url', 'poster', 'icon', 'cover'):
            return 'https://example.invalid/asset'
        return '<str>'
    return '<%s>' % type(obj).__name__


def capture(project=CANVAS_UUID):
    """三份回包**原样脱敏**：不重建顶层、不截断列表。

    重建会让真实回包里的字段漂移悄悄消失（此前 node_list 就是手搓的）。
    """
    listing = _cli_json('node', 'list', '-p', project)
    meta = _cli_json('project', project)
    nodes = meta.get('nodes') or []
    detail = _cli_json('node', nodes[0]['id'], '-p', project) if nodes else {}
    ids, names = {}, {}
    return {
        'note': ('LibTV CLI 回包的完整结构快照（值脱敏，结构/嵌套/类型保持原样）。'
                 '**本文件不会自动发现平台漂移**——'
                 '漂移需重跑 tests/test_platform_projection_contract.py --check。'),
        'captured_from': {'cli': '1.1.3', 'nodes': len(listing.get('nodes') or []),
                          'edges': len(meta.get('edges') or [])},
        'node_list': _sanitize(listing, ids, names),
        'node_detail': _sanitize(detail, ids, names),
        'project': _sanitize(meta, ids, names),
    }


def shape(obj):
    """只留形状：键集合与叶子类型，用于跨抓取比对。"""
    if isinstance(obj, dict):
        return {k: shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shape(item) for item in obj]
    return type(obj).__name__


def diff_shape(live, stored, path=''):
    out = []
    if isinstance(stored, dict) and isinstance(live, dict):
        for key in sorted(set(stored) | set(live)):
            # 只豁免夹具**根级**那句说明；真实回包任何层级出现 note 都必须进比较。
            if key == 'note' and path == '':
                continue
            here = path + '.' + key
            if key not in stored:
                out.append('%s：平台新增' % here)
            elif key not in live:
                out.append('%s：平台已移除' % here)
            else:
                out.extend(diff_shape(live[key], stored[key], here))
    elif isinstance(stored, list) and isinstance(live, list):
        if len(stored) != len(live):
            out.append('%s：元素数 %d → %d' % (path, len(stored), len(live)))
        # 逐项比对：只看首项会漏掉第 2 项以后的所有字段漂移。
        for index in range(min(len(stored), len(live))):
            out.extend(diff_shape(live[index], stored[index], '%s[%d]' % (path, index)))
    elif type(live).__name__ != type(stored).__name__:
        out.append('%s：类型 %s → %s' % (path, type(stored).__name__, type(live).__name__))
    return out


def main(argv):
    fixture = ROOT / 'tests' / 'fixtures' / 'libtv_platform_projection.json'
    if '--refresh' in argv:
        fixture.write_text(json.dumps(capture(), ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
        print('已重写夹具：%s' % fixture)
        return 0
    if '--check' in argv:
        stored = json.loads(fixture.read_text(encoding='utf-8'))
        differences = diff_shape(capture(), stored)
        if differences:
            print('平台投影已漂移：')
            for line in differences:
                print('  -', line)
            print('确认后运行 --refresh 更新夹具。')
            return 1
        print('平台投影与夹具一致。')
        return 0
    unittest.main(argv=argv)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
