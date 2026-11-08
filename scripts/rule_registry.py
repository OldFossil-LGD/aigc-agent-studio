#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rule Registry：把"散在手册里的执行规则"收敛成可检索、可测的记录。

任务书 T-P2-05。本模块只做三件确定性的事：
  ① 校验注册表结构（rule_id 唯一、必填字段齐、severity 合法）；
  ② 校验 owner_doc 与 test_id 真实存在（指向脚本时按 `脚本#self-test` 形式）；
  ③ 给其它模块一个查询入口（按 applies_to / rule_id）。

不解释规则语义（那是各 owner_doc 的事），不改手册。

用法：
  python scripts/rule_registry.py --registry docs/implementation/rule_registry.json
  python scripts/rule_registry.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RC_OK, RC_FAIL, RC_USAGE = 0, 1, 2
SEV = ("ERROR", "WARN", "UNDET")


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(reg, root=ROOT):
    issues = []
    seen = set()
    for rule in reg.get("rules") or []:
        rid = rule.get("rule_id")
        for key in ("rule_id", "owner_doc", "severity", "applies_to", "test_id"):
            if not rule.get(key):
                issues.append({"rule_id": rid, "code": "RULE_FIELD_MISSING", "field": key})
        if rid in seen:
            issues.append({"rule_id": rid, "code": "RULE_ID_DUPLICATE"})
        seen.add(rid)
        if rule.get("severity") not in SEV:
            issues.append({"rule_id": rid, "code": "RULE_SEVERITY_BAD", "severity": rule.get("severity")})
        owner = str(rule.get("owner_doc") or "").split("#")[0]
        if owner and not os.path.isfile(os.path.join(root, owner)):
            issues.append({"rule_id": rid, "code": "RULE_OWNER_MISSING", "owner_doc": owner})
        test = str(rule.get("test_id") or "").split("#")[0]
        if test and not os.path.isfile(os.path.join(root, test)):
            issues.append({"rule_id": rid, "code": "RULE_TEST_MISSING", "test_id": test})
    return issues


def query(reg, applies_to=None, rule_id=None):
    out = []
    for rule in reg.get("rules") or []:
        if rule_id and rule.get("rule_id") != rule_id:
            continue
        if applies_to and applies_to not in (rule.get("applies_to") or []):
            continue
        out.append(rule)
    return out


def self_test():
    reg = {"schema_version": "rule-registry/v1", "rules": [
        {"rule_id": "A", "owner_doc": "scripts/graph_plan_lint.py", "severity": "ERROR",
         "applies_to": ["graph-plan"], "test_id": "tests/test_graph_video_reference_actions.py"},
        {"rule_id": "B", "owner_doc": "scripts/nope.py", "severity": "WARN",
         "applies_to": ["x"], "test_id": "tests/nope.py"},
    ]}
    issues = validate(reg)
    checks = [
        ("缺文件被抓", any(i["code"] == "RULE_OWNER_MISSING" for i in issues)),
        ("缺测试被抓", any(i["code"] == "RULE_TEST_MISSING" for i in issues)),
        ("合法规则不误报", not any(i["rule_id"] == "A" for i in issues)),
        ("按 applies_to 查询", len(query(reg, applies_to="graph-plan")) == 1),
        ("重复 id 被抓", any(i["code"] == "RULE_ID_DUPLICATE" for i in validate(
            {"rules": [reg["rules"][0], reg["rules"][0]]}))),
    ]
    bad = 0
    for label, ok in checks:
        if not ok:
            bad += 1
            print("[FAIL] %s" % label)
        else:
            print("[PASS] %s" % label)
    print("自检：%d 项，%d 失败" % (len(checks), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rule Registry 校验与查询")
    ap.add_argument("--registry", default=os.path.join(ROOT, "docs", "implementation", "rule_registry.json"))
    ap.add_argument("--applies-to")
    ap.add_argument("--rule-id")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    reg = load(args.registry)
    issues = validate(reg)
    print(json.dumps({"issues": issues, "count": len(reg.get("rules") or [])}, ensure_ascii=False, indent=2))
    if args.applies_to or args.rule_id:
        print(json.dumps(query(reg, args.applies_to, args.rule_id), ensure_ascii=False, indent=2))
    return RC_FAIL if issues else RC_OK


if __name__ == "__main__":
    sys.exit(main())
