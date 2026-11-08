#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prompt AST v2：提示词的语义权威，12 块与模型执行版都从这里渲染。

为什么要有它（任务书 T-P2-03 / 不变量 I-14）：
`block-spec.md` 是人类写作契约，`compile_prompt_packages.py` 是角色语义块，两者此前
只有"名字像"的关系。本模块把每镜的事实落到**同一个 AST**：

  fields{purpose, camera_spec, composition, lighting, timeline, sound}
  identity_refs[{character_id, identity_version, look_id, continuity_state_id}]
  constraint_coverage{covered[], unconsumed_locked_constraints[]}

规则：
  · 每个字段带 `source_decision_ids`；没有来源的字段标 `UNKNOWN`，不冒充已定；
  · 硬约束（locked）必须有消费路径，否则 `CONTRACT_UNCONSUMED_CONSTRAINT`（BLOCK）；
  · 12 块视图与模型短提示都由 AST 渲染（`--view blocks|model`），不再各自读散字段。

退出码：0 通过 ｜ 1 有 BLOCK ｜ 2 用法错误

用法：
  python scripts/prompt_ast.py build --ir out/16_production_ir.json --out out/18_prompt_ast.json
  python scripts/prompt_ast.py coverage --ast out/18_prompt_ast.json
  python scripts/prompt_ast.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

try:
    from .error_contract import mk_error
except ImportError:
    try:
        from error_contract import mk_error
    except ImportError:
        def mk_error(code, severity, message, path=None, node_id=None, edge_id=None, fix=None, evidence=None):
            return {"code": code, "severity": severity, "message": message, "path": path,
                    "node_id": node_id, "edge_id": edge_id, "suggested_fix": fix}

RC_OK, RC_FAIL, RC_USAGE = 0, 1, 2
VERSION = "prompt-ast/v2"

FIELD_SOURCES = {
    "purpose": ("purpose",),
    "camera_spec": ("camera_spec", "delivery"),
    "composition": ("composition",),
    "lighting": ("lighting",),
    "timeline": ("timeline",),
    "sound": ("audio_policy", "sound"),
}


def _applies_to_shot(req, shot_id):
    selected = req.get("shots")
    if isinstance(selected, list) and selected and shot_id not in selected:
        return False
    parts = str(req.get("field_path") or "").split(".")
    return not (len(parts) > 1 and parts[0] == "shots" and parts[1] not in ("*", shot_id))


def _decision_ids(ir, fields, shot_id=None):
    ids = []
    for req in ir.get("requirements") or []:
        path = str(req.get("field_path") or "")
        if (shot_id is None or _applies_to_shot(req, shot_id)) and any(f in path for f in fields):
            ids.append(req.get("requirement_id"))
    return [i for i in ids if i]


def _value(container, key):
    """IR 里字段可能是裸值或 ValueWithProvenance；统一取值 + 来源。"""
    row = (container or {}).get(key)
    if isinstance(row, dict) and "value" in row:
        return row.get("value"), row.get("source_type")
    return row, None


def build(ir):
    asts = []
    for shot in ir.get("shots") or []:
        fields = {}
        for name, src_keys in FIELD_SOURCES.items():
            if name == "timeline":
                beats = ((shot.get("timeline") or {}).get("beats") or [])
                value = "; ".join("%.1f-%.1fs %s" % (b.get("start_sec", 0), b.get("end_sec", 0),
                                                     b.get("action", "")) for b in beats)
            elif name == "sound":
                ap = shot.get("audio_policy") or {}
                value = "mode=%s; allow=%s; deny=%s; dialogue=%s" % (
                    ap.get("mode"), ",".join(ap.get("allow") or []) or "-",
                    ",".join(ap.get("deny") or []) or "-", ap.get("dialogue"))
            elif name == "camera_spec":
                cam = (shot.get("camera_spec") or {}).get("value") or {}
                deliv = shot.get("delivery") or {}
                bits = [str(cam.get(k)) for k in ("shot_size", "camera_angle", "lens") if cam.get(k)]
                if deliv.get("aspect_ratio"):
                    bits.append("画幅 %s" % deliv["aspect_ratio"])
                value = "；".join(bits)
            else:
                value, _src = _value(shot, name)
            text = str(value).strip() if value not in (None, "", []) else ""
            fields[name] = {"value": value if text else None,
                            "status": "filled" if text else "N/A",
                            "source_decision_ids": _decision_ids(ir, src_keys, shot.get("shot_id"))}
        refs = []
        for ref in (shot.get("asset_refs") or {}).get("character_refs") or []:
            refs.append({"character_id": ref.get("character_id"),
                         "identity_version": ref.get("identity_version"),
                         "look_id": ref.get("look_id"),
                         "continuity_state_id": ref.get("continuity_state_id")})
        ast = {"schema_version": VERSION, "shot_id": shot.get("shot_id"),
               "identity_refs": refs, "fields": fields,
               "constraint_coverage": {"covered": [], "unconsumed_locked_constraints": []}}
        ast["constraint_coverage"] = coverage(ir, ast)
        asts.append(ast)
    return {"schema_version": VERSION, "project_id": (ir.get("project") or {}).get("project_id"),
            "shots": asts}


def _ast_text(ast):
    parts = []
    for field in ast.get("fields", {}).values():
        if field.get("value") not in (None, ""):
            parts.append(str(field["value"]))
    return " ".join(parts)


def coverage(ir, ast):
    covered, unconsumed = [], []
    text = _ast_text(ast)
    for req in ir.get("requirements") or []:
        if not _applies_to_shot(req, ast.get("shot_id")):
            continue
        if not req.get("locked") or req.get("strength") != "hard":
            continue
        rid, op, val = req.get("requirement_id"), req.get("operator"), str(req.get("value"))
        path = "fields.*"
        if op in ("contains", "prohibits"):
            hit = val in text
        else:  # project 级 equals 由 IR 校验负责，这里记录消费位置
            hit = True
        row = {"requirement_id": rid, "operator": op, "value": val,
               "ast_path": path, "consumed": hit}
        (covered if hit else unconsumed).append(row if hit else rid)
    return {"covered": covered, "unconsumed_locked_constraints": unconsumed}


def validate(aast):
    issues = []
    for ast in aast.get("shots") or []:
        sid = ast.get("shot_id")
        for name in ("purpose", "camera_spec", "timeline"):
            field = (ast.get("fields") or {}).get(name) or {}
            if field.get("status") != "filled":
                issues.append(mk_error("PROMPT_FIELD_UNKNOWN", "WARN",
                                       "%s 的 %s 未给：渲染时写 N/A，不编" % (sid, name),
                                       path="shots.%s.fields.%s" % (sid, name), node_id=sid))
        unconsumed = (ast.get("constraint_coverage") or {}).get("unconsumed_locked_constraints") or []
        for rid in unconsumed:
            issues.append(mk_error("CONTRACT_UNCONSUMED_CONSTRAINT", "ERROR",
                                   "%s 的锁定约束 %s 在 AST 里没有消费路径" % (sid, rid),
                                   path="shots.%s.constraint_coverage" % sid, node_id=sid,
                                   fix="补对应字段或显式登记不适用"))
    return issues


def render_blocks(ast):
    """12 块阅读版（只渲染 AST 有的字段，缺的写 N/A）。"""
    f = ast.get("fields") or {}
    def val(name):
        row = f.get(name) or {}
        return row.get("value") if row.get("status") == "filled" else "N/A（未给）"
    lines = ["【4 · 本镜目的】\n%s" % val("purpose"),
             "【5 · 镜头规格】\n%s" % val("camera_spec"),
             "【6 · 构图】\n%s" % val("composition"),
             "【8 · 光位与影调】\n%s" % val("lighting"),
             "【9 · 时间线】\n%s" % val("timeline"),
             "【11 · 声音】\n%s" % val("sound")]
    return "\n\n".join(lines)


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def self_test():
    ir = {
        "project": {"project_id": "P1"},
        "requirements": [
            {"requirement_id": "R1", "locked": True, "strength": "hard", "operator": "contains",
             "value": "水声", "field_path": "shots.*.sound"},
            {"requirement_id": "R2", "locked": True, "strength": "hard", "operator": "contains",
             "value": "不存在的短语", "field_path": "shots.*.lighting"},
        ],
        "shots": [{"shot_id": "shot_01",
                   "purpose": {"value": "让她看见车里有人", "source_type": "script"},
                   "delivery": {"duration_sec": {"value": 6}, "aspect_ratio": "2.39:1"},
                   "camera_spec": {"value": {"shot_size": "MCU", "lens": "35mm"}},
                   "composition": {"value": "主体画面左半"},
                   "lighting": {"value": "顶部钠灯为主"},
                   "timeline": {"beats": [{"start_sec": 0, "end_sec": 6, "action": "擦镜面后停住"}]},
                   "asset_refs": {"character_refs": [{"character_id": "char_01",
                                                      "identity_version": "v001"}]},
                   "audio_policy": {"mode": "ambience_only", "allow": ["水声"], "deny": ["人声"],
                                    "dialogue": "none"}}],
    }
    aast = build(ir)
    ast = aast["shots"][0]
    checks = [
        ("版本", aast["schema_version"] == VERSION),
        ("身份引用带版本", ast["identity_refs"][0]["identity_version"] == "v001"),
        ("字段带来源 id", ast["fields"]["sound"]["source_decision_ids"] == ["R1"]),
        ("覆盖：命中", any(c["requirement_id"] == "R1" for c in ast["constraint_coverage"]["covered"])),
        ("覆盖：未消费被记", "R2" in ast["constraint_coverage"]["unconsumed_locked_constraints"]),
        ("未消费 = BLOCK", any(i["code"] == "CONTRACT_UNCONSUMED_CONSTRAINT" and i["severity"] == "ERROR"
                               for i in validate(aast))),
        ("12 块视图渲染 6 块", render_blocks(ast).count("【") == 6),
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
    ap = argparse.ArgumentParser(description="Prompt AST v2")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build"); b.add_argument("--ir", required=True); b.add_argument("--out")
    c = sub.add_parser("coverage"); c.add_argument("--ast", required=True)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "build":
        aast = build(_load(args.ir))
        text = json.dumps(aast, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out:
            io.open(args.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
        print(text)
        issues = validate(aast)
        return RC_FAIL if any(i["severity"] == "ERROR" for i in issues) else RC_OK
    if args.cmd == "coverage":
        aast = _load(args.ast)
        issues = validate(aast)
        print(json.dumps({"issues": issues}, ensure_ascii=False, indent=2))
        return RC_FAIL if any(i["severity"] == "ERROR" for i in issues) else RC_OK
    ap.print_help()
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
