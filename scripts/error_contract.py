#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一错误契约（T-P0-03）：图/编译/映射错误一律给稳定机器码。

字段（任务书 §9）：
  code / severity / path / node_id / edge_id / message / suggested_fix

纪律：
  · 不允许 `except Exception: pass` 吞错；
  · severity 只有 ERROR / WARN / UNDET 三档（UNDET＝不确定，**不是通过**）；
  · 私有令牌与用户素材地址不得进入错误对象。
"""
from __future__ import print_function

import argparse
import json
import sys

RC_OK, RC_FAIL, RC_USAGE = 0, 1, 2
SEVERITIES = ("ERROR", "WARN", "UNDET")

# 旧模块的三元组 → 契约。新增模块直接用 mk_error。
LEGACY_SEVERITY = {"FAIL": "ERROR", "PASS": "WARN", "UNDET": "UNDET", "WARN": "WARN"}


def mk_error(code, severity, message, path=None, node_id=None, edge_id=None, fix=None, evidence=None):
    if severity not in SEVERITIES:
        raise ValueError("severity 必须是 %s，收到 %r" % (SEVERITIES, severity))
    return {"code": str(code), "severity": severity, "message": str(message),
            "path": path, "node_id": node_id, "edge_id": edge_id,
            "suggested_fix": fix, "evidence": list(evidence or [])}


def normalize(rows):
    """把 (verdict, code, message) 旧三元组转成契约对象（PASS 保留为 WARN 以便调用方区分）。"""
    out = []
    for row in rows or []:
        verdict, code, message = (list(row) + [None, None, None])[:3]
        out.append(mk_error(code or "UNKNOWN", LEGACY_SEVERITY.get(verdict, "UNDET"),
                            message or "", evidence=[verdict]))
    return out


def self_test():
    checks = [
        ("字段齐全", set(mk_error("X", "ERROR", "m")) >=
         {"code", "severity", "path", "node_id", "edge_id", "message", "suggested_fix"}),
        ("非法 severity 报错", _raises(lambda: mk_error("X", "FAIL", "m"))),
        ("三元组可归一", normalize([("FAIL", "EDGE_X", "m")])[0]["severity"] == "ERROR"),
        ("UNDET 不冒充通过", normalize([("UNDET", "E", "m")])[0]["severity"] == "UNDET"),
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


def _raises(fn):
    try:
        fn()
        return False
    except ValueError:
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="统一错误契约")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    ap.print_help()
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
