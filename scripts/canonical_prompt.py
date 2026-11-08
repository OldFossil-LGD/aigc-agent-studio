#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一提示词标准：任何输入都按 12 块出正文，缺的标"未给"，不编。

为什么要有它（`block-spec.md` + `stage1-delivery-entry.md`）：
本库的提示词标准是 12 块（后期特效 / 统一提质层 / 风险移除 / 本镜目的 / 镜头规格 /
构图 / 人物与环境 / 光位与影调 / 时间线 / 摄影机 / 声音 / 过渡压力）。
但机器交付件此前只排它手里有的块（video_candidate 7 块），于是同一条需求，
输入薄的时候出来 5 段、输入厚的时候出来 9 段——**标准随输入浮动**。

用户只说一句话，不该由他选模板。所以本模块负责一件事：
**把任意来源的块投影成固定的 12 块，逐块标状态**。

  已填 = 该块有来源文本（逐字取自包/契约，不改写）
  未给 = 没有来源 → 写清"缺什么、回哪一站补"，**绝不生成看起来合理的句子**

退出码：0 通过 ｜ 1 有 FAIL ｜ 2 用法错误 ｜ 3 没有可投影的包（≠通过）

用法（通常由 compile_intent_delivery 内部调用）：
  python scripts/canonical_prompt.py --packages out/04_prompt_packages.jsonl [--out out/13_Draft_Prompt.md]
  python scripts/canonical_prompt.py --self-test
"""
from __future__ import print_function

import argparse
import io
import json
import os
import re
import sys

try:
    from .filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE
except ImportError:
    from filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE

# 12 块标准（顺序即交付顺序）。第三列＝该块缺内容时，由哪一站/哪一册补。
CANON_BLOCKS = [
    ("1", "后期特效", ["style_detail", "grade", "color", "post_effect"], "站 3 调色族 + 风格编号（color-grading-styles.md）"),
    ("2", "统一提质层", ["quality_layer", "quality", "visual", "style"], "站 3 统一提质层整段（quality-layer.md §二）"),
    ("3", "风险移除 + 禁止出现", ["negative", "forbidden", "risk_removal"], None),
    ("4", "本镜目的", ["purpose", "shot_purpose"], "站 1 命题（这一镜为什么存在）"),
    ("5", "镜头规格", ["camera_spec", "lens", "shot_spec"], "站 3 器材包（机身/镜头/焦段/光圈）+ 画幅"),
    ("6", "构图", ["composition"], "站 6 构图（主体位置/引导线/留白）"),
    ("7", "人物与环境", ["identity", "wardrobe", "scene", "entities", "material_roles"], "站 5 资产（身份/服装/场景）"),
    ("8", "光位与影调", ["lighting", "light", "tone"], "站 6 光位（光源/性质/明暗分界）"),
    ("9", "时间线", ["action", "motion_path", "performance"], None),
    ("10", "摄影机", ["camera_movement", "camera"], "站 6 运镜（速度/落点/落点接下一镜）"),
    ("11", "声音", ["sound", "sound_layers", "ambience"], None),
    ("12", "过渡压力", ["transition", "continuity_link"], "站 6 过渡（下一镜从哪里接）"),
]

DELIVERABLE_ROLES = ("video_candidate", "candidate_image", "storyboard")
EMPTY_MARK = "未给"


def _clean(text):
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        parts = [_clean(x) for x in text]
        return "\n".join(p for p in parts if p)
    if isinstance(text, dict):
        return "\n".join("%s：%s" % (k, _clean(v)) for k, v in text.items() if _clean(v))
    return re.sub(r"[ \t]+", " ", str(text)).strip()


def _package_blocks(package):
    blocks = package.get("blocks") or {}
    if isinstance(blocks, dict):
        return {str(k): _clean(v) for k, v in blocks.items()}
    out = {}
    for block in blocks or []:
        if isinstance(block, dict):
            out[str(block.get("name") or "未命名")] = _clean(block.get("text"))
    return out


def pick_deliverable(packages):
    for role in DELIVERABLE_ROLES:
        hit = [p for p in packages if p.get("role") == role]
        if hit:
            return hit
    return packages


def project(packages, shot=None):
    """→ [{no,label,text,status,supplier}]，12 条，顺序固定。"""
    shot = shot or {}
    used = set()
    merged = {}
    for package in pick_deliverable(packages):
        for name, text in _package_blocks(package).items():
            if text and name not in merged:
                merged[name] = text
    rows = []
    for no, label, keys, supplier in CANON_BLOCKS:
        texts = []
        for key in keys:
            text = merged.get(key)
            if text and text not in used:
                used.add(text)
                texts.append(text)
        if no == "4" and not texts and shot.get("purpose"):
            texts.append(_clean(shot["purpose"]))
        if no == "9" and not texts and shot.get("description"):
            texts.append(_clean(shot["description"]))
        text = "\n".join(texts).strip()
        rows.append({"no": no, "label": label, "text": text,
                     "status": "filled" if text else "unfilled", "supplier": supplier})
    return rows


MAPPED_KEYS = {key for _no, _label, keys, _sup in CANON_BLOCKS for key in keys}


def render(rows, header="# 提示词（12 块标准）\n", settings=None, extras=None, node=None):
    """12 块正文：填了的照抄，没填的写"未给 + 谁补"。

    ★ 只用一个 `##` 标题（节点名）：交付语义复核按 `##` 切段判约束是否落地，
      多出来的 `## 覆盖率` 会被当成"该段没有风格标记"而判 FAIL（实测踩过）。
    `settings` 是平台要抄的画幅/时长；`extras` 是 12 块之外的正本块，逐字附在末尾。
    """
    filled = [r for r in rows if r["status"] == "filled"]
    lines = [header.rstrip(), ""]
    lines.append("> 统一标准：任何输入都按 12 块交付，块序固定；块内文字逐字取自正本，未填的块只说明缺口，不代写。")
    lines.append("")
    if node:
        lines.append("## %s" % node)
        lines.append("")
    if settings:
        lines.append("【可复制设置】")
        lines.append(_clean(settings))
        lines.append("")
    for row in rows:
        lines.append("【%s · %s】" % (row["no"], row["label"]))
        if row["status"] == "filled":
            lines.append(row["text"])
        else:
            lines.append("%s（缺：%s → %s）" % (EMPTY_MARK, row["label"], row["supplier"] or "剧本/本合同未给"))
        lines.append("")
    if extras:
        base = set(MAPPED_KEYS)
        for name, text in extras:
            if text and str(name) not in base:
                lines.append("【附 · %s】" % name)
                lines.append(text)
                lines.append("")
    missing = [r["label"] for r in rows if r["status"] == "unfilled"]
    lines.append("覆盖率：12 块已填 %d，未给 %d%s" % (
        len(filled), len(missing), ("：" + "、".join(missing)) if missing else "（全部有据）"))
    return "\n".join(lines).rstrip() + "\n"


def render_many(packages, header="# 提示词标准视图（12 块）\n"):
    """多镜：每镜一个 `## 节点`，每镜都排满 12 块。"""
    chosen = pick_deliverable(packages)
    parts = [header.rstrip(), ""]
    for package in chosen:
        blocks = _package_blocks(package)
        rows = project([package], {})
        settings = blocks.get("delivery_settings")
        extras = [(k, v) for k, v in blocks.items() if k not in MAPPED_KEYS and k != "delivery_settings"]
        parts.append(render(rows, "", settings=settings, extras=extras,
                            node=package.get("node_id") or package.get("role")).strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_from_file(packages_path, shot=None, header=None):
    with io.open(packages_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if len(pick_deliverable(rows)) > 1:
        return render_many(rows, header or "# 提示词（12 块标准）\n")
    return render(project(rows, shot), header or "# 提示词（12 块标准）\n")


# ───────────────────────────── 自检 ─────────────────────────────

THIN = [
    {"role": "video_candidate", "node_id": "shot_01__video_candidate_A", "blocks": {
        "visual": "写实电影感：真实材质、自然光、细颗粒。",
        "action": "青年抬头看向霓虹招牌。",
        "sound": "保留环境声与动作声。",
        "negative": "禁止字幕、LOGO、水印。",
        "duration": "5 秒。",
        "delivery_settings": "画幅 9:16；时长 5 秒。",
    }},
]
RICH = [
    {"role": "video_candidate", "node_id": "shot_01__video_candidate_A", "blocks": {
        "style_detail": "调色：十三冷调犯罪族，阴影饱和 15%。",
        "quality_layer": "统一提质：真实材质、自然光、细颗粒。",
        "negative": "禁止字幕、LOGO、水印。",
        "purpose": "让观众看见他第一次意识到雨停不了。",
        "camera_spec": "ARRI Alexa Mini LF + 40mm 球面，中景。",
        "composition": "主体左三分，右上看板留白。",
        "identity": "短发，24 岁，湿透的深色夹克。",
        "lighting": "招牌为唯一主光，侧逆。",
        "action": "抬头，雨滴沿发梢落下。",
        "camera": "固定机位，不动。",
        "sound": "雨声与脚步溅水。",
        "transition": "以招牌亮起切下一镜。",
        "duration": "5 秒。",
        "delivery_settings": "画幅 9:16；时长 5 秒。",
    }},
]


def self_test():
    bad = 0
    thin = project(THIN, {"description": "青年抬头"})
    rich = project(RICH, {"description": "青年抬头"})
    checks = [
        ("12 块恒定", len(thin) == 12 and len(rich) == 12),
        ("薄输入标未给", len([r for r in thin if r["status"] == "unfilled"]) >= 5),
        ("厚输入全部有据", all(r["status"] == "filled" for r in rich)),
        ("块内不重复", len({r["text"] for r in rich if r["text"]}) == len([r for r in rich if r["text"]])),
        ("缺块写明谁补", all(r["supplier"] or r["no"] in ("3", "9", "11") for r in thin if r["status"] == "unfilled")),
        ("渲染含 12 个块头", sum(1 for line in render(thin).splitlines() if line.startswith("【") and " · " in line) == 12),
        ("空块不编内容", "未给（缺：" in render(thin)),
        ("覆盖率可算", "覆盖率：12 块已填 12" in render(rich)),
        ("确定性", render(thin) == render(project(THIN, {"description": "青年抬头"}))),
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
    ap = argparse.ArgumentParser(description="统一 12 块提示词标准（block-spec.md）")
    ap.add_argument("--packages", help="04_prompt_packages.jsonl")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.packages:
        ap.print_help()
        return RC_USAGE
    try:
        with io.open(args.packages, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (IOError, OSError, ValueError) as exc:
        print("读不了包：%s" % exc)
        return RC_USAGE
    if not rows:
        print("[EMPTY] 包里没有节点：没投影到 ≠ 通过")
        return RC_EMPTY
    text = render_many(rows) if len(pick_deliverable(rows)) > 1 else render(project(rows))
    if args.out:
        parent = os.path.dirname(os.path.abspath(args.out))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(text)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
