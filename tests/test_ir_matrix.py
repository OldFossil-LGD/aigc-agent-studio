# -*- coding: utf-8 -*-
"""P4 跨题材回归：IR fixtures → 校验规则命中 + 12 块编译形态。

覆盖五类镜头（空镜 / 人物近景 / 对白 / 机位冲突 / 空泛语言），
断言两件事：① 只有预期规则命中（不多报、不漏报）；② 每例都编出完整 12 块。
"""
import io
import json
import os
import unittest

from scripts.production_ir import IR_VERSION, render, validate

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "ir_matrix")


def _load(name):
    with io.open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class IRMatrixTest(unittest.TestCase):
    def test_fixtures_present(self):
        names = sorted(n for n in os.listdir(FIXTURES) if n.endswith(".json"))
        self.assertEqual(len(names), 5, names)

    def test_rule_matrix(self):
        for name in sorted(n for n in os.listdir(FIXTURES) if n.endswith(".json")):
            doc = _load(name)
            expected = sorted(doc.pop("expected_rules", []))
            got = sorted({i["rule_id"] for i in validate(doc)})
            self.assertEqual(got, expected, "%s: %s" % (name, got))

    def test_every_fixture_renders_twelve_blocks(self):
        for name in sorted(n for n in os.listdir(FIXTURES) if n.endswith(".json")):
            doc = _load(name)
            doc.pop("expected_rules", None)
            text = render(doc)
            blocks = [l for l in text.splitlines() if l.startswith("【") and " · " in l]
            self.assertEqual(len(blocks), 12, "%s 只编出 %d 块" % (name, len(blocks)))

    def test_empty_shot_declares_na(self):
        doc = _load("empty_shot.json")
        doc.pop("expected_rules", None)
        self.assertIn("人物：不适用", render(doc))

    def test_schema_version_pinned(self):
        for name in sorted(n for n in os.listdir(FIXTURES) if n.endswith(".json")):
            self.assertEqual(_load(name)["schema_version"], IR_VERSION)


if __name__ == "__main__":
    unittest.main()
