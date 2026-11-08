#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一句话到交付：一条命令跑完「拆解 → 编译 → IR → 12 块视图」，不暴露内部术语。

为什么要有它（用户视角）：用户不该知道什么是 IR、12 块、FilmDSL。
他只会说"做一条 X 秒的片子"。所以入口只留**一条命令**，中间产物（10–17 号）
按标准自动落盘；任何一环 BLOCK 就停并说明"缺什么、回哪一站"，而不是让他读 JSON。

流水线（全部只读/离线，不点火）：
  ① 有剧本 → `breakdown_compile`（拆解单 10 / 编译输入 11 / 分镜表 12）
  ② `compile_production`（01–08 计划与提示词包）
  ③ `production_ir` build（16 IR）+ validate（17 报告）
  ④ `production_ir` render（15 十二块视图）
  ⑤ 汇总 `00_run_report.json`（每步退出码 + BLOCK 摘要）

退出码：0 全过 ｜ 1 有站 BLOCK ｜ 2 用法错误

用法：
  python scripts/studio_run.py --script 剧本.md --out projects/P1 [--duration 90] [--aspect 16:9] [--style 写实电影纪录片] [--asset-spec 资产描述.json]
  python scripts/studio_run.py --artifacts out/ --out projects/P1     # 接已有 01–04
  python scripts/studio_run.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
RC_OK, RC_FAIL, RC_USAGE = 0, 1, 2


def _run(script, args):
    r = subprocess.run([PY, os.path.join(HERE, script)] + args, capture_output=True,
                       text=True, encoding="utf-8", env=ENV)
    return {"script": script, "exit": r.returncode,
            "stdout_tail": (r.stdout or "").strip().splitlines()[-6:],
            "stderr_tail": (r.stderr or "").strip().splitlines()[-3:]}


def _write(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def run(script=None, artifacts=None, out=".", duration=None, aspect=None, style=None,
        asset_spec=None):
    os.makedirs(out, exist_ok=True)
    steps = []
    if script:
        args = ["--script", script, "--out", out]
        for flag, value in (("--duration", duration), ("--aspect", aspect), ("--style", style),
                            ("--asset-spec", asset_spec)):
            if value:
                args += [flag, str(value)]
        steps.append(_run("breakdown_compile.py", args))
        if steps[-1]["exit"] not in (0, 4):
            return _finish(out, steps, blk="剧本拆解未通过")
        artifacts = out
    if not artifacts:
        raise ValueError("需要 --script 或 --artifacts")
    steps.append(_run("compile_production.py", [os.path.join(artifacts, "11_compiler_input.json"),
                                                "--out", os.path.join(out, "plan")]))
    if steps[-1]["exit"] != 0:
        return _finish(out, steps, blk="计划编译未通过（看 plan/06_gate_results.json）")
    steps.append(_run("production_ir.py", ["build", "--artifacts", os.path.join(out, "plan"),
                                           "--out", os.path.join(out, "16_production_ir.json")]))
    if steps[-1]["exit"] not in (0, 4):
        return _finish(out, steps, blk="IR 校验 BLOCK")
    steps.append(_run("production_ir.py", ["render", "--ir", os.path.join(out, "16_production_ir.json"),
                                           "--out", os.path.join(out, "15_Canonical_Prompt.md")]))
    if steps[-1]["exit"] != 0:
        return _finish(out, steps, blk="提示词渲染未通过")
    # 提示词语义层（Prompt AST v2）+ 锁定项消费证明
    steps.append(_run("prompt_ast.py", ["build", "--ir", os.path.join(out, "16_production_ir.json"),
                                        "--out", os.path.join(out, "18_prompt_ast.json")]))
    if steps[-1]["exit"] != 0:
        return _finish(out, steps, blk="Prompt AST 校验未通过")
    # 图权威（Workflow Graph IR v2）：由 03 号图迁移，供落线闸门与差异分析使用
    plan_graph = os.path.join(out, "plan", "03_shot_graph_plan.json")
    if os.path.isfile(plan_graph):
        steps.append(_run("workflow_graph_ir.py", ["build", "--in", plan_graph,
                                                   "--out", os.path.join(out, "19_graph_ir.json")]))
        if steps[-1]["exit"] not in (0, 4):
            return _finish(out, steps, blk="Workflow Graph IR 校验未通过")
    return _finish(out, steps)


def _finish(out, steps, blk=None):
    report = {"status": "BLOCK" if blk else "PASS", "blocked_at": blk, "steps": steps,
              "artifacts": sorted(n for n in os.listdir(out)) if os.path.isdir(out) else []}
    _write(os.path.join(out, "00_run_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return RC_FAIL if blk else RC_OK


def self_test():
    import shutil
    import tempfile

    bad = 0
    root = tempfile.mkdtemp(prefix="studiorun_")
    try:
        script = os.path.join(root, "script.txt")
        with io.open(script, "w", encoding="utf-8") as f:
            f.write("人物：林\n道具：玻璃门\n\n场景一 便利店门口 雨夜 外\n\n"
                    "近景 固定 5秒 林站在雨棚下，抬手抹掉眉骨上的雨水。\n")
        spec_path = os.path.join(root, "asset_spec.json")
        with io.open(spec_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"char_01": "24 岁短发青年，湿透的深色夹克",
                                "loc_01": "便利店门头，雨棚与霓虹招牌，雨夜",
                                "prop_01": "玻璃门，门轴干涩，门框有冷凝水珠"}, ensure_ascii=False))
        out = os.path.join(root, "proj")
        rc = run(script=script, out=out, duration=5, aspect="16:9", style="写实电影纪录片",
                 asset_spec=spec_path)
        arts = set(os.listdir(out)) if os.path.isdir(out) else set()
        checks = [
            ("一条命令跑通", rc == RC_OK),
            ("拆解单在", "10_breakdown.json" in arts),
            ("编译输入在", "11_compiler_input.json" in arts),
            ("IR 在", "16_production_ir.json" in arts),
            ("12 块视图在", "15_Canonical_Prompt.md" in arts),
            ("Prompt AST 在", "18_prompt_ast.json" in arts),
            ("Graph IR 在", "19_graph_ir.json" in arts),
            ("运行报告在", "00_run_report.json" in arts),
        ]
        view = os.path.join(out, "15_Canonical_Prompt.md")
        text = ""
        if os.path.isfile(view):
            with io.open(view, encoding="utf-8") as f:
                text = f.read()
        checks.append(("视图含 12 块头", sum(1 for l in text.splitlines() if l.startswith("【") and " · " in l) == 12))
        with io.open(os.path.join(out, "00_run_report.json"), encoding="utf-8") as f:
            checks.append(("不点火", "run\": true" not in json.dumps(json.load(f))))
        for label, ok in checks:
            if not ok:
                bad += 1
                print("[FAIL] %s" % label)
            else:
                print("[PASS] %s" % label)
        print("自检：%d 项，%d 失败" % (len(checks), bad))
        return RC_OK if not bad else RC_FAIL
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="一句话到交付（拆解→编译→IR→12 块）")
    ap.add_argument("--script")
    ap.add_argument("--artifacts")
    ap.add_argument("--out", default=".")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--aspect")
    ap.add_argument("--style")
    ap.add_argument("--asset-spec")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.script or args.artifacts):
        ap.print_help()
        return RC_USAGE
    try:
        return run(args.script, args.artifacts, args.out, args.duration, args.aspect,
                   args.style, args.asset_spec)
    except ValueError as exc:
        print("用法错误：%s" % exc)
        return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
