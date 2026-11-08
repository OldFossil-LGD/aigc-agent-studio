#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""媒体 QC 与定向修复计划：把成片检查结果统一成 issue 格式，并给出最小影响域。

为什么要有它（改造书 §6）：结构 PASS 不等于画面成立。此前 `film_qc_gate.py` 能测
黑帧/静音/时长/画幅/fps/切点，但它的结论停在一份独立报告里，跟 IR 的镜头对不上，
于是"哪一镜要重做"仍靠人翻时间线。

本模块只做三件事：
  ① 跑既有的 `film_qc_gate.py`（不重复实现检测），把结果归一成统一 issue 结构；
  ② 按 IR 的镜头时长表把问题**映射到 shot_id**（时间点 → 镜头）；
  ③ 给**定向修复计划**：影响域（哪一镜/哪些下游）+ 建议动作 + 成本口径（不做自动重跑）。

永不自动重生成：`--repair-plan` 只打印计划；真实重跑仍要显式批准（站 6.5 纪律）。

退出码：0 通过 ｜ 1 有 BLOCK/检查失败 ｜ 2 用法错误 ｜ 3 未验证（缺文件/缺预期） ｜ 4 工具不可用

用法：
  python scripts/media_qc.py --video out/final.mp4 --ir out/16_production_ir.json [--repair-plan]
  python scripts/media_qc.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import subprocess
import sys

try:
    from .filmdsl_bridge import RC_FAIL, RC_OK, RC_USAGE
except ImportError:
    from filmdsl_bridge import RC_FAIL, RC_OK, RC_USAGE

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "film_qc_gate.py")
RC_EMPTY, RC_WARN = 3, 4


def _shots(ir):
    out = []
    t = 0.0
    for s in ir.get("shots") or []:
        dur = (((s.get("delivery") or {}).get("duration_sec") or {}).get("value") or 0)
        out.append({"shot_id": s.get("shot_id"), "start": t, "end": t + float(dur)})
        t += float(dur)
    return out


def shot_at(shots, sec):
    for s in shots:
        if s["start"] <= sec < s["end"]:
            return s["shot_id"]
    return None


def run_gate(video, expect=None):
    if not os.path.isfile(video):
        return RC_EMPTY, {"error": "找不到视频：%s" % video}
    command = [sys.executable, GATE, "--video", video]
    for key, flag in (("duration", "--expect-duration"), ("ratio", "--expect-ratio"),
                      ("fps", "--expect-fps")):
        if (expect or {}).get(key) is not None:
            command.extend([flag, str(expect[key])])
    r = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    try:
        payload = json.loads(r.stdout or "")
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        payload = {"raw": ((r.stdout or "") + (r.stderr or ""))[-2000:]}
    return r.returncode, payload


def normalize(payload, shots):
    issues = []
    for item in payload.get("failures") or payload.get("issues") or []:
        segments = item.get("segments") or [item]
        for index, segment in enumerate(segments):
            time = segment.get("time_sec", segment.get("time", segment.get("black_start", segment.get("start"))))
            issues.append({
                "issue_id": "QC_%s_%d" % (item.get("code") or "UNKNOWN", index),
                "rule_id": item.get("code") or "QC_UNKNOWN",
                "severity": "BLOCK", "affected_paths": ["media"],
                "shot_id": shot_at(shots, float(time)) if time is not None else None,
                "evidence": [str(item)[:300], str(segment)[:300]],
                "suggestion": "按检查原因修复受影响镜头或全片容器，重新核验",
            })
    return issues


def repair_plan(issues, shots):
    by_shot = {}
    for i in issues:
        by_shot.setdefault(i.get("shot_id") or "UNMAPPED", []).append(i["rule_id"])
    plan = []
    for sid, rules in by_shot.items():
        plan.append({"scope": sid, "rules": sorted(set(rules)),
                     "affected_downstream": ["assembly", "final_composite"] if sid == "UNMAPPED" else ["assembly"],
                     "action": "重生成该镜并重合成；其余镜头不动", "auto_retry": False})
    return plan


def self_test():
    import tempfile
    bad = 0
    shots = [{"shot_id": "shot_01", "start": 0, "end": 6}, {"shot_id": "shot_02", "start": 6, "end": 12}]
    checks = [
        ("时间点映射到镜头", shot_at(shots, 7.5) == "shot_02" and shot_at(shots, 0.3) == "shot_01"),
        ("越界时间不给假镜头", shot_at(shots, 99) is None),
        ("空 payload 归零", normalize({}, shots) == []),
        ("修复计划不自动重跑", all(p["auto_retry"] is False for p in repair_plan(
            [{"rule_id": "BLACK_FRAME", "shot_id": "shot_01"}], shots))),
        ("不存在的视频判 EMPTY", run_gate(os.path.join(tempfile.gettempdir(), "no_such_media_xyz.mp4"))[0] == RC_EMPTY),
    ]
    for label, ok in checks:
        if not ok:
            bad += 1
            print("[FAIL] %s" % label)
        else:
            print("[PASS] %s" % label)
    print("自检：%d 项，%d 失败" % (len(checks), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="媒体 QC 归一与定向修复计划")
    ap.add_argument("--video")
    ap.add_argument("--ir")
    ap.add_argument("--repair-plan", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.video:
        ap.print_help()
        return RC_USAGE
    ir = {}
    if args.ir:
        with io.open(args.ir, encoding="utf-8") as handle:
            ir = json.load(handle)
    delivery = (ir.get("project") or {}).get("delivery") or {}
    expect = {}
    for field, key in (("duration_sec", "duration"), ("aspect_ratio", "ratio"), ("fps", "fps")):
        value = delivery.get(field)
        value = value.get("value") if isinstance(value, dict) else value
        if value is not None:
            expect[key] = value
    rc, payload = run_gate(args.video, expect)
    valid_result = (rc == RC_OK and payload.get("status") == "PASS") or (
        rc == RC_FAIL and payload.get("status") == "FAIL" and bool(payload.get("failures") or payload.get("issues")))
    if not valid_result:
        status = {RC_EMPTY: "NOT_VERIFIED", RC_WARN: "WARN"}.get(rc, "ERROR")
        print(json.dumps({"status": status, "issues": [], "gate_exit_code": rc,
                          "gate_result": payload}, ensure_ascii=False, indent=2))
        return rc if rc in (RC_USAGE, RC_EMPTY, RC_WARN) else RC_FAIL
    shots = _shots(ir)
    issues = normalize(payload, shots)
    report = {"status": "BLOCK" if issues else "PASS", "issues": issues}
    if args.repair_plan:
        report["repair_plan"] = repair_plan(issues, shots)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return RC_FAIL if issues else RC_OK


if __name__ == "__main__":
    sys.exit(main())
