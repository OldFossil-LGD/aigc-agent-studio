#!/usr/bin/env python3
"""Mechanical gate: **no high-risk claim without a method, or an explicit marker**.

Why this exists (E234 / E235 / E236): 2026-10-12 我在同一件事上连错两次 ——
先用静帧断言运镜，再用"只搜平移"的估计器断言第一个镜头是"横移+升降"（实为**环绕上升**）。
两次都不是措辞问题，而是**断言超出了所用方法的可及范围**，而且**没有任何机制拦我**。

本 lint 把那条纪律变成可执行判据：
  出现高危断言（运镜 / 排版 / 占位符 / 点火）时，同一行必须满足其一 ——
    ① 附了对应测量证据（包里存在带必需字段的 JSON），或
    ② 该行显式标注 `推断 / 不可判定 / 复刻选择 / 拟订 / 未验证 / 待确认`
  两条都不满足 → FAIL（视为"把推断写成实测"）。

用法：
  python scripts/claim_method_lint.py --dir <交付包目录> [--evidence-dir <额外证据目录>]
  python scripts/claim_method_lint.py --self-test

退出码：0 PASS · 1 FAIL · 2 用法 · 3 没扫到任何断言（≠通过）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path


CATEGORIES = (
    {
        "id": "motion",
        "pattern": re.compile(r"环绕|推近|拉远|平摇|摇镜|跟移|跟随|手持|固定机位|机位静止|机位在|升降|横移|变焦"),
        "evidence_keys": ("rotation_deg_per_s", "zoom_per_s", "pan_px_per_s", "tilt_px_per_s"),
        "why": "运镜类型必须来自帧间测量（且必须含旋转/缩放分量，见 E235）",
    },
    {
        "id": "layout",
        "pattern": re.compile(r"不重叠|零重叠|排版|入组|坐标"),
        "evidence_keys": ("overlapping_pairs", "shared_slots"),
        "why": "画布排版必须来自 layout 核验（见 E233）",
    },
    {
        "id": "placeholder",
        # ★ 只匹配**裸占位符**（{{A1}} 这种）；{{Node "…"}} 是**正确写法**，不该被当成问题
        #   （2026-10-12 实测：原写法把命令计划里全部 22 条合规提示词误报为违例）
        "pattern": re.compile(r"\{\{(?!Node\b)"),
        "evidence_keys": ("bare_placeholder_nodes",),
        "why": "提示词占位符合规必须来自节点回读",
    },
    {
        "id": "ignition",
        "pattern": re.compile(r"零点火|未点火|没有点火"),
        "evidence_keys": ("ignited_nodes",),
        "why": "点火状态必须来自节点回读",
    },
)

MARKERS = re.compile(r"推断|不可判定|复刻选择|拟订|未验证|待确认")
SCAN_SUFFIXES = (".md", ".json")


def collect_evidence_keys(paths: list[Path]) -> set[str]:
    keys: set[str] = set()
    for root in paths:
        if not root.exists():
            continue
        for path in root.rglob("*.json"):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for key in set(re.findall(r'"([a-z_]+)"\s*:', text)):
                keys.add(key)
    return keys


def scan(package: Path, evidence_dirs: list[Path]) -> dict:
    evidence_keys = collect_evidence_keys([package] + evidence_dirs)
    hits = {c["id"]: 0 for c in CATEGORIES}
    violations, marked = [], []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for category in CATEGORIES:
                if not category["pattern"].search(line):
                    continue
                hits[category["id"]] += 1
                if MARKERS.search(line):
                    marked.append({"file": path.name, "line": number, "category": category["id"]})
                    continue
                if all(key in evidence_keys for key in category["evidence_keys"]):
                    continue
                violations.append({
                    "file": path.name, "line": number, "category": category["id"],
                    "text": line.strip()[:120], "why": category["why"],
                    "missing_keys": [k for k in category["evidence_keys"] if k not in evidence_keys],
                })
    total = sum(hits.values())
    if not total:
        status = "NOT_VERIFIED"
    else:
        status = "PASS" if not violations else "FAIL"
    return {"status": status, "claims_found": total, "by_category": hits,
            "marked_as_inferred": len(marked), "violations": violations,
            "evidence_keys_seen": sorted(evidence_keys)[:20]}


def self_test() -> int:
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp)
        doc = pkg / "delivery.md"
        doc.write_text("第一个镜头是环绕上升镜头。\n", encoding="utf-8")
        r1 = scan(pkg, [])
        cases.append(("unbacked_motion_claim_fails", r1["status"] == "FAIL"))

        (pkg / "motion_readback.json").write_text(json.dumps({
            "shots": {"V1": {"rotation_deg_per_s": 4.5, "zoom_per_s": 0.0,
                             "pan_px_per_s": 1.5, "tilt_px_per_s": 21.0}}}), encoding="utf-8")
        r2 = scan(pkg, [])
        cases.append(("claim_with_method_passes", r2["status"] == "PASS"))

        doc.write_text("第一个镜头疑似环绕上升（**推断**，未做测量）。\n", encoding="utf-8")
        (pkg / "motion_readback.json").unlink()
        r3 = scan(pkg, [])
        cases.append(("explicit_marker_passes", r3["status"] == "PASS"))

        doc.write_text("画布节点不重叠，排版干净。\n", encoding="utf-8")
        r4 = scan(pkg, [])
        cases.append(("unbacked_layout_claim_fails", r4["status"] == "FAIL"))

        (pkg / "layout_check.json").write_text(json.dumps(
            {"overlapping_pairs": [], "shared_slots": {}}), encoding="utf-8")
        r5 = scan(pkg, [])
        cases.append(("layout_claim_with_evidence_passes", r5["status"] == "PASS"))

    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail",
                      "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir")
    parser.add_argument("--evidence-dir", action="append", default=[])
    parser.add_argument("--json-out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.dir:
        parser.error("--dir is required unless --self-test")

    result = scan(Path(args.dir), [Path(d) for d in args.evidence_dir])
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    if result["status"] == "PASS":
        return 0
    return 3 if result["status"] == "NOT_VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
