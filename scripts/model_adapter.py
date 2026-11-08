#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型适配器接口层：IR 镜头 → 请求体，能力不匹配就拒（dry-run，永不发请求）。

为什么要有它（改造书 §8）：此前"提示词写好了"与"这个模型能不能吃"是两件事，
靠人记；模型一换就悄悄降级。本模块把三件事分开：

  ① 能力注册表（`schemas/model_capability.schema.json`）：只写 yes/no/unknown 与上限；
  ② 请求渲染：只从 IR 取字段（duration / aspect / first_frame / refs / negative），不读散文本；
  ③ 预检：能力缺失或超上限 → `BLOCK`，**不降级、不猜参数**。

本模块**永不发网络请求**：`--dry-run` 只打印请求体与预检结论；真实调用留给适配器实现者，
并且必须先拿到显式批准（与站 6.5 的点火纪律一致）。

退出码：0 通过 ｜ 1 能力不足/参数越界 ｜ 2 用法错误

用法：
  python scripts/model_adapter.py --ir out/16_production_ir.json --registry models.json --model wan-3.0 [--shot shot_01] [--dry-run]
  python scripts/model_adapter.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

try:
    from .filmdsl_bridge import RC_FAIL, RC_OK, RC_USAGE
except ImportError:
    from filmdsl_bridge import RC_FAIL, RC_OK, RC_USAGE


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def find_model(registry, model_id):
    for m in registry.get("models") or []:
        if m.get("model_id") == model_id:
            return m
    return None


def preflight(shot, model, has_reference=False):
    """→ (issues, request)。issues 里 severity 只有 BLOCK / WARN。"""
    issues = []
    caps = model.get("capabilities") or {}
    if not has_reference and caps.get("text_to_video") == "no":
        issues.append(("CAPABILITY_MISSING", "BLOCK", "模型不支持文生视频，而本镜没有参考图"))
    if has_reference and caps.get("image_to_video") == "no":
        issues.append(("CAPABILITY_MISSING", "BLOCK", "模型不支持图生视频，而本镜挂了参考"))
    dur = ((shot.get("delivery") or {}).get("duration_sec") or {}).get("value")
    max_dur = caps.get("max_duration_sec")
    if dur and max_dur and float(dur) > float(max_dur):
        issues.append(("DURATION_OVER_LIMIT", "BLOCK",
                       "本镜 %.2fs 超过模型上限 %.2fs" % (float(dur), float(max_dur))))
    aspect = (shot.get("delivery") or {}).get("aspect_ratio")
    ratios = caps.get("aspect_ratios") or []
    if aspect and ratios and aspect not in ratios:
        issues.append(("ASPECT_UNSUPPORTED", "WARN", "模型未登记画幅 %s（已登记：%s）" % (aspect, ratios)))
    for key in ("negative_prompt", "audio_native"):
        if caps.get(key) == "unknown":
            issues.append(("CAPABILITY_UNKNOWN", "WARN", "能力 %s 未验证" % key))
    request = {
        "model_id": model.get("model_id"),
        "modality": model.get("modality"),
        "prompt_blocks_source": "production-ir/v1",
        "shot_id": shot.get("shot_id"),
        "duration_sec": dur,
        "aspect_ratio": aspect,
        "fps": (shot.get("delivery") or {}).get("fps"),
        "has_reference": has_reference,
        "dry_run": True,
    }
    return issues, request


def self_test():
    ir = {
        "shots": [{"shot_id": "shot_01",
                   "delivery": {"duration_sec": {"value": 6}, "aspect_ratio": "2.39:1", "fps": 24}}],
    }
    reg = {"registry_version": "1.0.0", "models": [
        {"model_id": "m-ok", "modality": "video", "verified_at": "2026-10-31",
         "capabilities": {"text_to_video": "yes", "image_to_video": "yes", "negative_prompt": "yes",
                          "audio_native": "no", "max_duration_sec": 10, "aspect_ratios": ["2.39:1"]}},
        {"model_id": "m-short", "modality": "video", "verified_at": "2026-10-31",
         "capabilities": {"text_to_video": "yes", "max_duration_sec": 4, "aspect_ratios": []}},
        {"model_id": "m-unknown", "modality": "video", "verified_at": "2026-10-31",
         "capabilities": {"text_to_video": "unknown", "negative_prompt": "unknown"}},
    ]}
    cases = [
        ("ok", "m-ok", False, []),
        ("duration_over", "m-short", False, ["DURATION_OVER_LIMIT"]),
        ("unknown_caps", "m-unknown", False, ["CAPABILITY_UNKNOWN"]),
    ]
    bad = 0
    for name, mid, ref, expect in cases:
        issues, req = preflight(ir["shots"][0], find_model(reg, mid), ref)
        got = sorted({i[0] for i in issues})
        if got != sorted(expect):
            bad += 1
            print("[FAIL] %-14s expected=%s got=%s" % (name, expect, got))
        else:
            print("[PASS] %-14s %s" % (name, got or "-"))
    checks = [
        ("请求体不含密钥", "api_key" not in json.dumps(preflight(ir["shots"][0], find_model(reg, "m-ok"))[1])),
        ("请求体标 dry_run", preflight(ir["shots"][0], find_model(reg, "m-ok"))[1]["dry_run"] is True),
    ]
    for label, ok in checks:
        if not ok:
            bad += 1
            print("[FAIL] %s" % label)
        else:
            print("[PASS] %s" % label)
    print("自检：%d 项，%d 失败" % (len(cases) + len(checks), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="模型适配器预检（dry-run，不发请求）")
    ap.add_argument("--ir")
    ap.add_argument("--registry")
    ap.add_argument("--model")
    ap.add_argument("--shot")
    ap.add_argument("--reference", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.ir and args.registry and args.model):
        ap.print_help()
        return RC_USAGE
    ir, reg = _load(args.ir), _load(args.registry)
    model = find_model(reg, args.model)
    if model is None:
        print("[FAIL] 注册表里没有 %s：先登记能力，不要猜" % args.model)
        return RC_FAIL
    shots = [s for s in ir.get("shots") or [] if not args.shot or s.get("shot_id") == args.shot]
    if not shots:
        print("[EMPTY] 没有匹配的镜头")
        return RC_USAGE
    worst = RC_OK
    for shot in shots:
        issues, request = preflight(shot, model, bool(args.reference))
        print(json.dumps({"shot_id": shot.get("shot_id"), "issues": issues, "request": request},
                         ensure_ascii=False, indent=2))
        if any(i[1] == "BLOCK" for i in issues):
            worst = RC_FAIL
    return worst


if __name__ == "__main__":
    sys.exit(main())
