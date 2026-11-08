#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""十站出口门：每一站「必须有产出、默认值已生效、不许静默跳过」。

为什么有它：规则写在十册里，但 agent 可以"跳过 → 交付 → 事后解释"。
本工具把每站的**出口条件**变成可判的：文件在不在、必填段有没有、清单过没过、
参考是否生效、任务号与证据是否齐。**跳过只有一种合法方式：用户明说 + 写进 waivers.json**。

用法：
  python scripts/stage_gate.py --dir projects/P1 --all
  python scripts/stage_gate.py --dir projects/P1 --stage S5
  python scripts/stage_gate.py --list
  python scripts/stage_gate.py --self-test
退出码：0 全过（含合法豁免）｜1 有站不过 ｜2 用法错误 ｜3 没扫到任何站（≠通过）
"""
from __future__ import print_function

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3

EMPTY_WORDS = ["电影感", "氛围感", "高级感", "质感拉满", "大片感", "有内味儿"]
PLACEHOLDERS = ["TODO", "待补", "（待定）", "(待定)", "XXX", "[ ]"]

STAGES = [
    {"id": "S1", "name": "命题", "kind": "md", "path": "01_命题.md",
     "markers": ["命题", "核心矛盾", "视觉母题", "人物三问", "进出差", "主导问题", "可反转"]},
    {"id": "S2", "name": "可行性+brief", "kind": "md", "path": "02_brief.md",
     "markers": ["时长", "画幅", "主旨", "交付物", "难点", "风格"]},
    {"id": "S3", "name": "风格+方案包", "kind": "md", "path": "03_style.md",
     "markers": ["风格编号", "量级系", "方案包"]},
    {"id": "S4", "name": "剧本", "kind": "md", "path": "04_script.md",
     "markers": ["主旨", "梗概", "人物", "节拍", "无对白", "分场", "台词"],
     # ★ 2026-10-31 起：剧本站出口同时要求「拆解单」，否则资产与分镜没有结构输入
     #   （用户不需要知道有这一步；缺就红，除非用户明说豁免）。
     "extras": [{"kind": "json_exists", "path": "10_breakdown.json", "why": "剧本拆解"}]},
    {"id": "S5", "name": "资产", "kind": "json", "path": "assets/asset_manifest.json",
     "checks": ["manifest_ok"]},
    {"id": "S5.5", "name": "参考闭环", "kind": "json", "path": "refs/resolved.json",
     "checks": ["refs_effective"]},
    {"id": "S6", "name": "分镜", "kind": "md", "path": "06_shotlist.md",
     "markers": ["镜号", "景别", "时长"],
     # ★ 2026-10-31 起：分镜站出口同时要求 Production IR 无 BLOCK，且 12 块视图存在
     "extras": [{"kind": "ir_pass", "path": "16_production_ir.json", "why": "Production IR"},
                {"kind": "file_exists", "path": "15_Canonical_Prompt.md", "why": "12 块视图"}]},
    {"id": "S6.5", "name": "生成", "kind": "jsonl", "path": "gen/tasks.jsonl",
     "checks": ["tasks"]},
    {"id": "S6.6", "name": "合成", "kind": "files",
     "paths": ["out/final.mp4", "qc/container.json"]},
    {"id": "S6.7", "name": "交付", "kind": "json", "path": "delivery/evidence.json",
     "checks": ["evidence4"]},
    {"id": "S7", "name": "返工", "kind": "md", "path": "rework/decision.md",
     "markers": ["责任层", "回退站"]},
]

DEFAULTS = [
    ("画幅", "16:9（竖屏 9:16 仅用户指定）"),
    ("单镜时长", "5s；生成单元下限 2.0s"),
    ("声音", "平台侧 enableSound=off，声音本地做"),
    ("每镜参考", "2–4 张；同一身份 ≤1 张脸"),
    ("人物", "每造型 7 件（脸 + 前后左右俯 + 无头身体）"),
    ("场景", "平面图 1 + 每个机位 1 张"),
    ("道具", "主图 1；多面 3；上限 5；物证加近距版"),
    ("命名", "资产_{主体}_{角色}[_{状态}]；镜头_{id}"),
    ("目录", "assets/ refs/ gen/ out/ qc/ delivery/"),
    ("幂等", "每次付费调用带 idempotencyKey"),
    ("重试", "每阶段 2 次；同一产物 ≤3 次"),
]


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _waivers(root):
    p = os.path.join(root, "waivers.json")
    if not os.path.isfile(p):
        return {}
    try:
        data = json.loads(_read(p))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _check_md(root, st):
    path = os.path.join(root, st["path"])
    if not os.path.isfile(path):
        return ["缺文件 %s" % st["path"]]
    text = _read(path)
    problems = [("缺必填段「%s」" % m) for m in st["markers"] if m not in text]
    if len(text.strip()) < 80:
        problems.append("文件过短（<80 字）：多半是占位")
    for w in EMPTY_WORDS:
        if w in text:
            problems.append("空话词「%s」" % w)
    for p in PLACEHOLDERS:
        if p in text:
            problems.append("未替换占位「%s」" % p)
    return problems


def _check_json(root, st):
    path = os.path.join(root, st["path"])
    if not os.path.isfile(path):
        return ["缺文件 %s" % st["path"]]
    try:
        d = json.loads(_read(path))
    except ValueError as exc:
        return ["JSON 不合法：%s" % exc]
    out = []
    for c in st.get("checks") or []:
        if c == "manifest_ok":
            if not d.get("ok") or (d.get("counts") or {}).get("fail"):
                out.append("清单有 FAIL（ok=%r fail=%r）" % (d.get("ok"), (d.get("counts") or {}).get("fail")))
        elif c == "refs_effective":
            rows = d.get("shots") or d.get("resolved") or []
            if not rows:
                out.append("没有任何镜头绑定")
            for r in rows:
                if r.get("effective") is not True or not r.get("node_key"):
                    out.append("绑定未生效：%s" % (r.get("shot") or r.get("asset_id")))
        elif c == "evidence4":
            for k in ("task_id", "params", "result_path", "criteria"):
                if not d.get(k):
                    out.append("证据缺「%s」" % k)
    return out


def _check_jsonl(root, st):
    path = os.path.join(root, st["path"])
    if not os.path.isfile(path):
        return ["缺文件 %s" % st["path"]]
    n, bad = 0, []
    for i, line in enumerate(_read(path).splitlines(), 1):
        if not line.strip():
            continue
        n += 1
        try:
            row = json.loads(line)
        except ValueError:
            bad.append("第 %d 行不是 JSON" % i)
            continue
        if not row.get("task_id"):
            bad.append("第 %d 行缺 task_id" % i)
        if not row.get("refs"):
            bad.append("第 %d 行没有参考（空引用＝生成必漂）" % i)
        if row.get("status") in ("failed", "cancelled"):
            bad.append("第 %d 行状态 %s" % (i, row.get("status")))
    if n == 0:
        bad.append("没有任何任务记录")
    return bad


def _check_files(root, st):
    out = []
    for rel in st["paths"]:
        p = os.path.join(root, rel)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            out.append("缺文件或空文件 %s" % rel)
    return out


def _check_extras(root, st):
    """标准件的附加出口（2026-10-31）：拆解单 / IR / 12 块视图。

    设计成"默认开、可豁免"：用户不需要知道这些文件存在，但工程缺了就不许往下走。
    """
    out = []
    for extra in st.get("extras") or []:
        path = os.path.join(root, extra["path"])
        kind = extra.get("kind")
        why = extra.get("why") or extra["path"]
        if not os.path.isfile(path):
            out.append("缺%s（%s）" % (why, extra["path"]))
            continue
        if kind == "ir_pass":
            try:
                ir = json.loads(_read(path))
                if str(ir.get("schema_version")) != "1.0.0":
                    out.append("IR schema_version 不是 1.0.0")
            except ValueError as exc:
                out.append("IR 不是合法 JSON：%s" % exc)
                continue
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from production_ir import validate as ir_validate
                issues = ir_validate(ir)
                blocks = [i for i in issues if i.get("severity") == "BLOCK"]
                if blocks:
                    out.append("IR 有 %d 条 BLOCK（首条：%s）" % (len(blocks), blocks[0].get("rule_id")))
            except Exception as exc:  # 校验器不可用时不放行
                out.append("IR 校验器不可用：%s" % exc)
    return out


CHECKERS = {"md": _check_md, "json": _check_json, "jsonl": _check_jsonl, "files": _check_files}


def run(root, only=None):
    waivers = _waivers(root)
    rows = []
    for st in STAGES:
        if only and st["id"] != only:
            continue
        problems = CHECKERS[st["kind"]](root, st) + _check_extras(root, st)
        w = waivers.get(st["id"])
        if problems and w and str(w.get("user_quote") or "").strip():
            rows.append({"id": st["id"], "name": st["name"], "status": "WAIVED",
                         "problems": problems, "quote": w.get("user_quote")})
        elif problems:
            rows.append({"id": st["id"], "name": st["name"], "status": "FAIL", "problems": problems})
        else:
            rows.append({"id": st["id"], "name": st["name"], "status": "PASS", "problems": []})
    return rows


def report(rows):
    bad = [r for r in rows if r["status"] == "FAIL"]
    for r in rows:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "WAIVED": "WAIV"}[r["status"]]
        print("[%s] %-5s %s" % (mark, r["id"], r["name"]))
        if r["status"] == "FAIL":
            for p in r["problems"]:
                print("        -", p)
        elif r["status"] == "WAIVED":
            print("        豁免：%s" % r["quote"])
            for p in r["problems"][:2]:
                print("        （仍缺）", p)
    print("结论：%d 站通过 / %d 站失败 / %d 站豁免" %
          (sum(1 for r in rows if r["status"] == "PASS"), len(bad),
           sum(1 for r in rows if r["status"] == "WAIVED")))
    if bad:
        print("下一站不许开工：先补 %s。" % "、".join(r["id"] for r in bad))
    return RC_OK if not bad else RC_FAIL


def _self_test():
    root = tempfile.mkdtemp(prefix="stagegate_")
    bad = 0
    try:
        md = {
            "S1": "命题 核心矛盾 视觉母题 人物三问 进出差 主导问题 可反转",
            "S2": "时长 画幅 主旨 交付物 难点 风格",
            "S3": "风格编号 量级系 方案包",
            "S4": "主旨 梗概 人物 节拍 无对白 分场 台词 " + "正文" * 40,
            "S6": "镜号 景别 时长 " + "正文" * 40,
            "S7": "责任层 回退站 " + "正文" * 40,
        }
        paths = {"S1": "01_命题.md", "S2": "02_brief.md", "S3": "03_style.md",
                 "S4": "04_script.md", "S6": "06_shotlist.md", "S7": "rework/decision.md"}
        for sid, text in md.items():
            p = os.path.join(root, paths[sid])
            if os.path.dirname(p):
                os.makedirs(os.path.dirname(p), exist_ok=True)
            io.open(p, "w", encoding="utf-8").write(text + "正文" * 40)
        # ★ 2026-10-31：标准件（拆解单 / IR / 12 块视图）——干净工程必须同时具备
        io.open(os.path.join(root, "10_breakdown.json"), "w", encoding="utf-8").write(
            json.dumps({"format": "breakdown/v1", "shots": [{"id": "shot_01"}],
                        "characters": [], "props": [], "scenes": []}, ensure_ascii=False))
        _ir = {"schema_version": "1.0.0",
               "project": {"project_id": "PRJ_SELFTEST",
                           "delivery": {"duration_sec": {"value": 5, "source_type": "user_explicit", "locked": True},
                                        "aspect_ratio": {"value": "16:9", "source_type": "user_explicit", "locked": True},
                                        "fps": {"value": 24, "source_type": "user_explicit", "locked": True}}},
               "requirements": [],
               "assets": {"characters": [], "locations": [], "props": []},
               "shots": [{"shot_id": "shot_01", "order": 0,
                          "purpose": {"value": "让观众看见雨停了", "source_type": "script"},
                          "delivery": {"duration_sec": {"value": 5, "source_type": "script"},
                                       "aspect_ratio": "16:9", "fps": 24},
                          "camera_spec": {"value": {"shot_size": "LS", "lens_status": "unknown",
                                                    "camera_movement": "static"}, "source_type": "script"},
                          "composition": {"value": "主体画面右侧", "source_type": "script"},
                          "lighting": {"value": "顶灯为主光", "source_type": "script"},
                          "camera_movement": {"value": "固定", "source_type": "script"},
                          "timeline": {"beats": [{"start_sec": 0, "end_sec": 5, "action": "雨停"}]},
                          "asset_refs": {"character_refs": [], "location_id": None,
                                         "prop_refs": [], "continuity_state_id": "cs_01"},
                          "audio_policy": {"mode": "ambience_only", "allow": ["雨声"], "deny": ["人声"],
                                           "dialogue": "none", "sound_events": []},
                          "transition": {"kind": "cut", "target_shot_id": "END"}}]}
        io.open(os.path.join(root, "16_production_ir.json"), "w", encoding="utf-8").write(
            json.dumps(_ir, ensure_ascii=False))
        io.open(os.path.join(root, "15_Canonical_Prompt.md"), "w", encoding="utf-8").write(
            "【1 · 后期特效】" + "正文" * 30)
        os.makedirs(os.path.join(root, "assets"))
        io.open(os.path.join(root, "assets/asset_manifest.json"), "w", encoding="utf-8").write(
            json.dumps({"ok": True, "counts": {"fail": 0}}))
        os.makedirs(os.path.join(root, "refs"))
        io.open(os.path.join(root, "refs/resolved.json"), "w", encoding="utf-8").write(
            json.dumps({"shots": [{"shot": "V1", "node_key": "n1", "effective": True}]}))
        os.makedirs(os.path.join(root, "gen"))
        io.open(os.path.join(root, "gen/tasks.jsonl"), "w", encoding="utf-8").write(
            json.dumps({"task_id": "t1", "refs": ["n1"], "status": "succeeded"}) + "\n")
        os.makedirs(os.path.join(root, "out"))
        os.makedirs(os.path.join(root, "qc"))
        io.open(os.path.join(root, "out/final.mp4"), "wb").write(b"x")
        io.open(os.path.join(root, "qc/container.json"), "w", encoding="utf-8").write("{}")
        os.makedirs(os.path.join(root, "delivery"))
        io.open(os.path.join(root, "delivery/evidence.json"), "w", encoding="utf-8").write(
            json.dumps({"task_id": "t1", "params": {"model": "x"}, "result_path": "out/final.mp4", "criteria": "x"}))

        rows = run(root)
        if any(r["status"] == "FAIL" for r in rows):
            bad += 1
            print("[FAIL] 干净工程被判失败：", [r for r in rows if r["status"] == "FAIL"])
        # ★ 删掉 IR → S6 必须红（标准件缺了就许往下走）
        _ir_path = os.path.join(root, "16_production_ir.json")
        _ir_backup = _read(_ir_path)
        os.remove(_ir_path)
        if run(root, "S6")[0]["status"] != "FAIL":
            bad += 1
            print("[FAIL] 删掉 Production IR 没有变红")
        io.open(_ir_path, "w", encoding="utf-8").write(_ir_backup)
        # 删一站 → 必须红
        os.remove(os.path.join(root, "04_script.md"))
        rows = run(root, "S4")
        if rows[0]["status"] != "FAIL":
            bad += 1
            print("[FAIL] 删掉剧本没有变红")
        # 空话 → 必须红
        io.open(os.path.join(root, "04_script.md"), "w", encoding="utf-8").write(
            "主旨 梗概 人物 节拍 无对白 分场 台词 电影感 " + "正文" * 40)
        if run(root, "S4")[0]["status"] != "FAIL":
            bad += 1
            print("[FAIL] 空话词没有被拦")
        # 合法豁免 → 放行
        io.open(os.path.join(root, "waivers.json"), "w", encoding="utf-8").write(
            json.dumps({"S4": {"user_quote": "只给提示词，不要剧本", "reason": "用户豁免"}}))
        io.open(os.path.join(root, "04_script.md"), "w", encoding="utf-8").write("x")
        r = run(root, "S4")[0]
        if r["status"] != "WAIVED":
            bad += 1
            print("[FAIL] 合法豁免没有放行：", r)
        print("自检：%d 失败" % bad)
        return RC_OK if not bad else RC_FAIL
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="十站出口门（默认标准 + 合法豁免）")
    ap.add_argument("--dir", help="工程目录")
    ap.add_argument("--stage", help="只跑某站，如 S5")
    ap.add_argument("--all", action="store_true", help="跑全部")
    ap.add_argument("--list", action="store_true", help="列出默认值与各站出口")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.list:
        for sid, val in DEFAULTS:
            print("%-10s %s" % (sid, val))
        print("")
        for st in STAGES:
            print("%-5s %-10s %s" % (st["id"], st["name"], st.get("path") or "/".join(st.get("paths") or [])))
        return RC_OK
    if not args.dir:
        ap.print_help()
        return RC_USAGE
    if not os.path.isdir(args.dir):
        print("目录不存在：%s" % args.dir)
        return RC_USAGE
    rows = run(args.dir, args.stage)
    if not rows:
        print("没有匹配的站")
        return RC_EMPTY
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return RC_OK if all(r["status"] != "FAIL" for r in rows) else RC_FAIL
    return report(rows)


if __name__ == "__main__":
    sys.exit(main())
