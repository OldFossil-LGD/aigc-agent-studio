#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_intent_delivery —— 用户意图 → 提示词正本 → 可直接复制的 Markdown。

这是阶段一的**真实入口**：Agent 把用户原话理解成 `intent-handoff/v1` 文档，
本脚本负责结构化交接、校验与转换，然后：

1. 编译生产合同 / 图 / Prompt Package（正本 = `prompt-package/v1`）；
2. 把正本交给旧离线渲染器做**单向适配**渲染出 Markdown；
3. 写出一份可复制的最终提示词 Markdown（含来源与消费证据）。

不联网、不点火、不生成媒体、不写平台画布。

用法：
  python scripts/compile_intent_delivery.py <intent_handoff.json> --out out/
  python scripts/compile_intent_delivery.py --self-test

停止点：`prompt_only` / `single_shot` 在图计划与 Prompt Package 停止，
不产生 05/08 执行计划。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# The skill root must be importable as a package *before* the first
# `scripts.<mod>` import. When this file is run as a CLI script, sys.path[0]
# is `skill/scripts/`, and the bare name `scripts` then resolves to an
# unrelated namespace package on some hosts (e.g.
# site-packages/win32/scripts). Once that namespace package is bound, every
# `from scripts.<mod> import ...` fails and the whole compiler falls back to
# flat imports — which is not fatal, but it makes different modules load as
# two distinct objects and it silently starves the delivery verifier of its
# routing table. Putting the skill root at the front of sys.path makes the
# real package win and keeps every module loaded exactly once.
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if sys.path and sys.path[0] != str(_SKILL_ROOT):
    sys.path.insert(0, str(_SKILL_ROOT))

try:
    from scripts.compile_production import compile_production
    from scripts.intent_handoff import (
        FORMAT,
        IntentHandoffError,
        to_compiler_input,
        validate_intent_handoff,
    )
    from scripts.production_capability_gate import evaluate
    from scripts.render_offline_prompts import (
        PROMPT_PACKAGE_FORMAT,
        UnsupportedPackageFormat,
        render,
    )
    from scripts.verify_delivery_semantics import verify_delivery
except ImportError:
    from compile_production import compile_production
    from intent_handoff import (
        FORMAT,
        IntentHandoffError,
        to_compiler_input,
        validate_intent_handoff,
    )
    from production_capability_gate import evaluate
    from render_offline_prompts import (
        PROMPT_PACKAGE_FORMAT,
        UnsupportedPackageFormat,
        render,
    )
    from verify_delivery_semantics import verify_delivery


DELIVERY_PACKAGE = "12_intent_delivery_package.json"
VERIFICATION_REPORT = "14_delivery_verification.json"
COPYABLE_MARKDOWN = "13_Final_Prompt.md"
DRAFT_MARKDOWN = "13_Draft_Prompt.md"
CANONICAL_MARKDOWN = "15_Canonical_Prompt.md"

# Roles whose prompt is the copyable deliverable. Video first; a still-only
# delivery falls back to the candidate image.
DELIVERABLE_ROLES = ("video_candidate", "candidate_image")

# Unlanded upstream references. In this stage no reference image exists, so
# the copyable text must not name a node that was never produced.
_NODE_REF = re.compile(r"\{\{Node[^}]*\}\}")

_COPYABLE_HEADER = """# 最终提示词（可直接复制投喂）

> 正本：`prompt-package/v1`，由 `scripts/compile_prompt_packages.py` 编译生成；本文件由同一份正本派生，未另手写。
> 交付边界（阶段一 · prompt_only）：本文件只交付提示词正文。**未生成任何参考图或素材，未创建平台画布，未生成媒体**。
> 正文里不写不存在的参考图；若后续要走图生视频，须先按 `references/production-compiler.md` 补齐场景/构图/候选图素材，
> 那一步不在本次交付范围内。
"""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean_block_value(value: Any) -> str:
    """Render one prompt block as plain text, without control information.

    * `{{Node ...}}` references name upstream nodes that were never produced
      in this stage — they are removed, together with the line that carries
      them, rather than left as a promise the delivery cannot keep.
    * list values become one line per entry.
    """

    if isinstance(value, list):
        parts = []
        for item in value:
            text = _clean_block_value(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    text = str(value or "")
    lines: list[str] = []
    for raw in text.splitlines():
        if "{{Node" in raw:
            # The whole line only names upstream nodes (e.g. "引用： ...").
            continue
        cleaned = _NODE_REF.sub("", raw).strip()
        if not cleaned:
            continue
        if cleaned.rstrip("：: ").endswith("引用"):
            continue
        lines.append(cleaned)
    return "\n".join(lines)


def build_copyable_markdown(prompts: list[dict[str, Any]], *, reviewed: bool = False) -> str:
    """Build the final copyable prompt document from the canonical packages.

    The document is derived from the same canonical packages the platform
    would receive — nothing is re-written by hand. The delivery settings
    (aspect ratio / duration) come out of the packages' own
    ``delivery_settings`` block, so the copyable text carries the decision
    instead of leaving it in the contract.
    """

    chosen: list[dict[str, Any]] = []
    for role in DELIVERABLE_ROLES:
        chosen = [package for package in prompts if package.get("role") == role]
        if chosen:
            break
    header = _COPYABLE_HEADER if reviewed else _COPYABLE_HEADER.replace("# 最终提示词（可直接复制投喂）", "# 提示词草稿（创作审阅证据未完成，不是正式交付）", 1)
    lines = [header, ""]
    for package in chosen:
        lines.append("## %s" % (package.get("node_id") or package.get("role")))
        lines.append("")
        blocks = package.get("blocks") or {}
        if isinstance(blocks, dict):
            items = list(blocks.items())
        else:
            items = [
                (block.get("name") or "未命名", block.get("text") or "")
                for block in blocks
                if isinstance(block, dict)
            ]
        # The delivery settings come first: they are what the operator has to
        # be able to copy without scrolling.
        ordered = sorted(
            items,
            key=lambda item: 0 if str(item[0]) == "delivery_settings" else 1,
        )
        for name, value in ordered:
            text = _clean_block_value(value)
            if not text:
                continue
            label = "可复制设置" if name == "delivery_settings" else name
            lines.append("【%s】" % label)
            lines.append(text)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _constraint_evidence(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate where each declared constraint actually landed."""

    per_constraint: dict[str, dict[str, Any]] = {}
    for package in prompts:
        for item in package.get("constraint_evidence") or []:
            cid = item.get("constraint_id")
            if not cid:
                continue
            record = per_constraint.setdefault(
                cid,
                {
                    "constraint_id": cid,
                    "kind": item.get("kind"),
                    "delivery": item.get("delivery"),
                    "blocks": [],
                    "nodes": [],
                    "status": "consumed",
                    "reason": None,
                },
            )
            record["nodes"].append(package.get("node_id"))
            if item.get("block"):
                record["blocks"].append(item.get("block"))
            if item.get("delivery") == "pending":
                record["status"] = "pending"
                record["reason"] = item.get("reason")
    return per_constraint


def build_delivery_package(
    handoff: dict[str, Any],
    compiler_input: dict[str, Any],
    result: dict[str, Any],
    out_dir: Path,
    rendered: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the delivery package: decisions, evidence, and the stop point."""

    contract = result.get("contract") or {}
    gate = result.get("gate") or {}
    evidence = _constraint_evidence(result.get("prompts") or [])
    pending = [item for item in evidence.values() if item.get("status") != "consumed"]

    delivery = {
        "intent_format": FORMAT,
        "prompt_package_format": PROMPT_PACKAGE_FORMAT,
        "task_id": "INTENT-DELIVERY-01",
        "goal": compiler_input.get("goal"),
        "task_type": contract.get("task_type"),
        "mode": contract.get("production_mode"),
        "deliverable": contract.get("deliverable"),
        "stop_point": "graph_plan_ready" if contract.get("task_type") == "prompt_only" else contract.get("task_type"),
        "decisions": contract.get("decision_log") or [],
        "proposed_decisions": contract.get("proposed_decisions") or [],
        "contract_status": contract.get("status"),
        "contract_questions": list(result.get("contract_result", {}).get("questions") or []),
        "gate_status": gate.get("status"),
        "gate_failures": list(gate.get("failures") or []),
        "constraint_evidence": sorted(evidence.values(), key=lambda item: item["constraint_id"]),
        "pending_constraints": pending,
        "rendered_markdown": sorted(rendered.get("generated") or {}),
        "artifacts": sorted(p.name for p in Path(out_dir).iterdir() if p.is_file()),
        "no_media_generated": True,
        "no_platform_write": True,
        "no_ignition": True,
        "claims": {
            "creative_decisions_locked": bool(contract.get("decision_log")) and not contract.get("proposed_decisions"),
            "media_quality_verified": False,
            "note": "本包只证明结构、约束兑现与产物存在；未生成媒体，不声称画面效果已验证。",
        },
    }
    return delivery


def compile_intent_delivery(handoff: dict[str, Any], out_dir: Path, previous_graph: dict[str, Any] | None = None, *, review=None, capture_root=None, session_id=None, draft=False, canonical_13=False) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    validate_intent_handoff(handoff)
    compiler_input = to_compiler_input(handoff)
    result = compile_production(compiler_input, out_dir, previous_graph=previous_graph)

    # One-way adapter: canonical prompt packages -> legacy offline renderer.
    packages_path = out_dir / "04_prompt_packages.jsonl"
    if not packages_path.exists():
        raise RuntimeError("missing canonical prompt packages: %s" % packages_path)
    legacy_dir = out_dir / "rendered"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(packages_path, legacy_dir / "03_Prompt_Packages.jsonl")
    manifest_path, generated = render(str(legacy_dir))

    contract_result = {}
    contract_file = out_dir / "01_production_contract.json"
    if contract_file.exists():
        contract_result = json.loads(contract_file.read_text(encoding="utf-8"))
    result["contract_result"] = contract_result

    delivery = build_delivery_package(
        handoff, compiler_input, result, out_dir, {"generated": generated}
    )

    try:
        from scripts.delivery_review import evaluate_delivery_review
    except ImportError:
        from delivery_review import evaluate_delivery_review
    canonical = json.dumps(result.get("prompts") or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    review_check = evaluate_delivery_review(_SKILL_ROOT, handoff, {"prompt_packages": canonical}, review, capture_root=capture_root, session_id=session_id)
    evidence_ready = review_check["delivery_ready"] and not draft
    formal = False  # Write Final only after independent verification.
    # An unreviewed rerun must not leave an old generated Final masquerading as current.
    old_final = out_dir / COPYABLE_MARKDOWN
    if not formal and old_final.exists():
        if old_final.read_text(encoding="utf-8").startswith("# 最终提示词（可直接复制投喂）"):
            previous = out_dir / "13_Previous_Final_Prompt.unverified.md"
            index = 1
            while previous.exists():
                previous = out_dir / ("13_Previous_Final_Prompt.%d.unverified.md" % index)
                index += 1
            old_final.rename(previous)
        else:
            raise RuntimeError("Existing Final is not a recognised generated artifact; use a new output directory")
    copyable = out_dir / (COPYABLE_MARKDOWN if formal else DRAFT_MARKDOWN)
    markdown = build_copyable_markdown(result.get("prompts") or [])
    if not formal:
        markdown = markdown.replace("# 最终提示词（可直接复制投喂）", "# 提示词草稿（创作审阅证据未完成，不是正式交付）", 1)
    copyable.write_text(markdown, encoding="utf-8")
    if canonical_13:
        try:
            try:
                from scripts.canonical_prompt import render_many
            except ImportError:
                from canonical_prompt import render_many
            copyable.write_text(
                render_many(result.get("prompts") or [],
                            header="# 提示词（12 块 Canonical · 由正本编译）\n"),
                encoding="utf-8")
            delivery["canonical_13"] = True
        except Exception as exc:  # 视图失败不许拖垮交付正文
            delivery["canonical_13_error"] = str(exc)
    # 统一标准视图（12 块）：与 13 同源同正本，只换排法。13 是受语义复核约束的交付正文，
    # 15 是"任何输入都按 12 块排"的标准视图；两者不许互相改写。
    try:
        try:
            from scripts.canonical_prompt import render_many
        except ImportError:
            from canonical_prompt import render_many
        (out_dir / CANONICAL_MARKDOWN).write_text(
            render_many(result.get("prompts") or []), encoding="utf-8")
    except Exception as exc:  # 视图失败不许拖垮交付正文
        print("canonical view skipped: %s" % exc)
    delivery["delivery_readiness"] = "REVIEW_EVIDENCE_READY" if formal else "DRAFT_REVIEW_REQUIRED"
    delivery["review_evidence"] = review_check
    delivery["claims"]["material_decision_provenance_locked"] = delivery["claims"].pop("creative_decisions_locked")
    delivery["claims"]["creative_quality_verified"] = False

    # Independent acceptance: the delivered text is judged against the
    # authoritative intent. It runs on the real artefacts, never on the
    # generator's self-report.
    verification = verify_delivery(
        handoff,
        result.get("prompts") or [],
        result.get("graph"),
        copyable.read_text(encoding="utf-8"),
    )
    if evidence_ready and verification["status"] == "PASS" and result["gate"]["status"] == "PASS" and result["contract"].get("status") == "READY":
        final_text = build_copyable_markdown(result.get("prompts") or [], reviewed=True)
        final_check = verify_delivery(handoff, result.get("prompts") or [], result.get("graph"), final_text)
        if final_check["status"] == "PASS":
            copyable = out_dir / COPYABLE_MARKDOWN
            copyable.write_text(final_text, encoding="utf-8")
            delivery["delivery_readiness"] = "REVIEW_EVIDENCE_READY"
            verification = final_check
    delivery["verification_scope"] = "Declared constraint semantics; not all creative quality or actual media"
    _write_json(out_dir / VERIFICATION_REPORT, verification)
    delivery["verification_status"] = verification["status"]
    delivery["verification_failures"] = verification["failures"]
    delivery["verification_report"] = VERIFICATION_REPORT
    delivery["claims"]["delivery_semantics_verified"] = verification["status"] == "PASS"
    delivery["claims"]["note"] = (
        "本包只证明结构、约束兑现与产物存在；未生成媒体，不声称画面效果已验证。"
        "约束语义验收由 scripts/verify_delivery_semantics.py 独立执行，结果见 %s。"
        % VERIFICATION_REPORT
    )
    delivery["artifacts"] = sorted({p.name for p in out_dir.iterdir() if p.is_file()} | {DELIVERY_PACKAGE})
    _write_json(out_dir / DELIVERY_PACKAGE, delivery)

    return {
        "gate": result["gate"],
        "contract": result["contract"],
        "prompts": result["prompts"],
        "graph": result.get("graph"),
        "delivery": delivery,
        "render_manifest": manifest_path,
        "copyable_markdown": str(copyable),
        "verification": verification,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="intent handoff -> prompt package -> Markdown")
    parser.add_argument("intent", nargs="?", help="intent-handoff/v1 JSON 文件")
    parser.add_argument("--out", help="输出目录")
    parser.add_argument("--previous-graph", help="Existing record graph for offline local rework")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--draft", action="store_true", help="Explicit offline engineering draft; not a reviewed creative delivery")
    # ★ 2026-10-31 补（改造书 §6.2）：可选把 13 号换成 12 块 Canonical 形态。
    #   默认关闭——语义复核按 `##` 逐镜分段判约束，换排法要连带改复核器与契约测试。
    parser.add_argument("--canonical-13", action="store_true",
                        help="把 13 号写成 12 块 Canonical 形态（实验；默认旧排法）")
    parser.add_argument("--review", help="Current creative-review/v1 JSON")
    parser.add_argument("--capture-root")
    parser.add_argument("--session")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.intent or not args.out:
        parser.print_help()
        return 2
    try:
        handoff = json.loads(Path(args.intent).read_text(encoding="utf-8"))
        previous = json.loads(Path(args.previous_graph).read_text(encoding="utf-8")) if args.previous_graph else None
        review = json.loads(Path(args.review).read_text(encoding="utf-8")) if args.review else None
        result = compile_intent_delivery(handoff, Path(args.out), previous_graph=previous, review=review, capture_root=args.capture_root, session_id=args.session, draft=args.draft, canonical_13=getattr(args, "canonical_13", False))
    except IntentHandoffError as exc:
        sys.stderr.write("intent handoff invalid: %s\n" % exc)
        return 2
    except UnsupportedPackageFormat as exc:
        sys.stderr.write("unsupported prompt package format: %s\n" % exc)
        return 3
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        sys.stderr.write("%s\n" % exc)
        return 1
    print(json.dumps({
        "gate_status": result["gate"]["status"],
        "contract_status": result["contract"].get("status"),
        "proposed_decisions": result["contract"].get("proposed_decisions"),
        "copyable_markdown": result["copyable_markdown"],
        "verification_status": result["verification"]["status"],
        "delivery_readiness": result["delivery"]["delivery_readiness"],
    }, ensure_ascii=False, indent=2))
    if result["gate"]["status"] == "FAIL":
        return 1
    if result["verification"]["status"] != "PASS":
        # A delivery that cannot prove it honours the constraints is not a
        # delivery — the compiler must not report success anyway.
        sys.stderr.write(
            "delivery verification: %s\n%s\n"
            % (
                result["verification"]["status"],
                json.dumps(result["verification"]["failures"], ensure_ascii=False, indent=2),
            )
        )
        return 1
    if not args.draft and result["delivery"]["delivery_readiness"] != "REVIEW_EVIDENCE_READY":
        sys.stderr.write("DRAFT_REVIEW_REQUIRED: full current source and decision evidence required before formal delivery\n")
        return 1
    return 0


def self_test() -> int:
    import tempfile

    handoff = {
        "intent_format": FORMAT,
        "goal": "剪纸空镜",
        "task_type": "prompt_only",
        "decisions": {
            "duration_sec": {"value": 5, "source": "user_explicit", "locked": True},
            "aspect_ratio": {"value": "9:16", "source": "user_explicit", "locked": True},
            "visual_style": {
                "value": {"text": "剪纸风格", "register": "stylized"},
                "source": "user_explicit",
                "locked": True,
            },
        },
        "shots": [{"id": "s1", "duration_sec": 5, "description": "白色纸制时钟的影子扫过蓝色墙面", "shot_kind": "empty"}],
        "constraints": [
            {
                "id": "c_camera",
                "kind": "camera",
                "text": "相机固定俯拍。",
                "delivery": "prompt",
                "source": "user_explicit",
                "locked": True,
                "semantics": {"required_any": ["俯拍"], "forbidden": ["平视"]},
            }
        ],
        "entities": [],
    }
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / "out"
        result = compile_intent_delivery(handoff, out, draft=True)
        if result["gate"]["status"] != "PASS":
            print("gate FAIL", result["gate"]["failures"])
            return 1
        if result["verification"]["status"] != "PASS":
            print("verification", result["verification"]["status"], result["verification"]["failures"])
            return 1
        if (out / "05_platform_execution_plan.json").exists():
            print("prompt_only must not write an execution plan")
            return 1
        if (out / "08_libtv_command_plan.json").exists():
            print("prompt_only must not write a libtv command plan")
            return 1
        text = (out / DRAFT_MARKDOWN).read_text(encoding="utf-8")
        if "俯拍" not in text:
            print("constraint did not reach the markdown")
            return 1
        if "{{Node" in text:
            print("copyable markdown still carries unlanded node references")
            return 1
        if not (out / VERIFICATION_REPORT).exists():
            print("verification report missing")
            return 1
    print("self-test 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
