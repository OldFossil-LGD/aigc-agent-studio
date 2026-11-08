#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_delivery_semantics —— 独立于生成者自报状态的最终交付验收。

**它回答什么**：最终交付出去的提示词正文（以及平台参数）到底有没有兑现
用户明确给出的约束。

**它不回答什么**：它不判断画面好不好看、媒体质量如何、不调用任何模型。

四条纪律（对应验收 E）：

1. **不信自报状态**：`consumed` / `READY` / `constraint_evidence` 一律不作为
   判定依据。判定输入只有两样：权威输入（intent handoff / contract）与
   **实际最终提示词正文与参数**。
2. **按语义判定，不按整句字串**：合法的同义表达（"正上方俯视" 对 "俯拍"）
   判为兑现；"禁止人声" 不算人声违规，"旁白朗读解说" 算违规。
3. **不许别的节点掩盖本候选的错误**：每个消费角色单独判定，一个节点兑现了
   不能替另一个节点免罪。
4. **没判过 ≠ 通过**：缺包、漏候选、零判定、未知约束一律不报 PASS；
   未知项标 `UNVERIFIED`，缺包/漏候选/语义违规报 `FAIL`。

用法：

```text
python scripts/verify_delivery_semantics.py --intent intent.json --out out/
python scripts/verify_delivery_semantics.py --intent intent.json --packages p.jsonl --markdown m.md
python scripts/verify_delivery_semantics.py --self-test
```

退出码：0 PASS · 1 FAIL 或 UNVERIFIED · 2 用法/输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# The skill root must be importable as a package regardless of whether this
# file is run as a CLI script (`python scripts/verify_delivery_semantics.py`)
# or imported as `scripts.verify_delivery_semantics`.
#
# It must also be importable as a package *first*. On some hosts the bare name
# `scripts` resolves to an unrelated namespace package (e.g.
# site-packages/win32/scripts). Once that namespace package is bound into
# sys.modules, every later `from scripts.<mod> import ...` fails and the
# fallback below silently reduces the routing table to {} — which makes the
# verifier judge nothing while still looking like it ran. Putting the skill
# root at the front of sys.path *before* the first `scripts.` import makes the
# real package win.
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if sys.path and sys.path[0] != str(_SKILL_ROOT):
    sys.path.insert(0, str(_SKILL_ROOT))

try:
    from scripts.constraint_semantics import evaluate_constraint
except ImportError:
    from constraint_semantics import evaluate_constraint

try:
    from scripts.compile_prompt_packages import CONSTRAINT_DELIVERY_BY_KIND
except ImportError:
    try:
        from compile_prompt_packages import CONSTRAINT_DELIVERY_BY_KIND
    except ImportError as exc:  # pragma: no cover - defensive
        # A missing routing table is not a detail: without it no constraint has
        # a consuming role, every judgement is skipped, and the delivery would
        # be reported as verified without a single judgement. Fail loudly
        # instead of degrading into a false pass.
        raise RuntimeError(
            "cannot import the constraint delivery routing table from "
            "scripts/compile_prompt_packages.py: %s" % exc
        ) from exc


CREATIVE_CRAFT_KEYS = frozenset(
    {
        "performance",
        "action_feedback",
        "continuity_state",
        "transition",
        "style_detail",
        "sound_craft",
        "motion_path",
        "style_notes",
    }
)
CANONICAL_PROMPT_FORMAT = "prompt-package/v1"

# Roles that can carry a deliverable candidate. A shot that declares
# delivered for that shot.
CANDIDATE_ROLES = ("video_candidate", "candidate_image")

# Markdown section headings in the final delivery document.
_SECTION_SPLIT = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# Markdown block markers like ``【duration】``.
_MARKDOWN_BLOCK_SPLIT = re.compile(r"^【(.+?)】\s*$", re.MULTILINE)


def _markdown_control_blocks(text: str) -> list[tuple[str | None, str]]:
    """Split a markdown section into (block_name, body) pairs.

    Block names are normalised to the canonical package block names used by
    the compiler, so ``【可复制设置】`` becomes ``delivery_settings`` and
    ``【duration】`` stays ``duration``.
    """
    body = str(text or "")
    matches = list(_MARKDOWN_BLOCK_SPLIT.finditer(body))
    if not matches:
        return [(None, body)]
    out: list[tuple[str | None, str]] = []
    if matches[0].start() > 0:
        out.append((None, body[: matches[0].start()]))
    for index, match in enumerate(matches):
        raw = match.group(1).strip()
        block_name = raw
        if raw == "可复制设置":
            block_name = "delivery_settings"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        out.append((block_name, body[match.end() : end]))
    return out


def _consuming_roles(kind: str) -> list[str]:
    """Roles that can carry a given constraint kind.

    Derived from the canonical compiler routing table. Only roles that
    actually exist in the delivery are judged.
    """

    routing = CONSTRAINT_DELIVERY_BY_KIND.get(kind) or {}
    return [role for role, block in routing.items() if block]


def _package_text(package: dict[str, Any]) -> str:
    """The text a platform would actually receive for this package."""

    blocks = package.get("blocks")
    if isinstance(blocks, dict):
        items = blocks.items()
    else:
        items = [
            (block.get("name") or "未命名", block.get("text") or "")
            for block in (blocks or [])
            if isinstance(block, dict)
        ]
    return "\n".join("%s\n%s" % (key, value) for key, value in items)


def _norm(text: Any) -> str:
    return str(text or "").strip()


_RATIO_PATTERN = re.compile(r"(?<![0-9])(\d{1,2})\s*[:：比x×]\s*(\d{1,2})(?![0-9])")
_DURATION_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s\b|sec|seconds?)", re.IGNORECASE)
_CUT_RANGE_PATTERN = re.compile(
    r"(?:裁切|cut)\s*(\d+(?:\.\d+)?)\s*[–\-~～至]\s*(\d+(?:\.\d+)?)\s*(?:秒|s\b)?",
    re.IGNORECASE,
)

# Field-specific duration control markers.  Each tuple is a regex that
# captures the numeric value for that control slot.
_CONTROL_DURATION_PATTERNS: dict[str, list[str]] = {
    # Final duration must be introduced by a final-specific marker.  Bare
    # ``时长`` in a ``duration`` block is handled by the bare-number fallback.
    "final": [
        r"(?:成片时长|成片|final\s+duration)\s*(\d+(?:\.\d+)?)\s*(?:秒|s\b)",
    ],
    "gen": [
        r"(?:生成|generation)\s*(\d+(?:\.\d+)?)\s*(?:秒|s\b)",
    ],
    "settings": [
        r"(?:当前镜头时长|时长)\s*(\d+(?:\.\d+)?)\s*(?:秒|s\b)",
    ],
    "total": [
        r"(?:(?:全片|完整(?:影片)?|影片|整片|total)\s*(?:总\s*)?(?:时长|长度)?|总(?:时长|时|长))\s*(\d+(?:\.\d+)?)\s*(?:秒|s\b)",
    ],
}

# Roles that are allowed to carry duration control claims.  Other roles may
# still state whole-film totals, but their per-shot duration numbers are
# intermediate/platform parameters, not authoritative control fields.
_DURATION_CONSUMER_ROLES = frozenset(
    (CONSTRAINT_DELIVERY_BY_KIND.get("duration") or {}).keys()
)


def _ratio_pairs(text: Any) -> list[tuple[int, int]]:
    """Every ``W:H`` pair stated in ``text``."""

    out: list[tuple[int, int]] = []
    for match in _RATIO_PATTERN.finditer(str(text or "")):
        try:
            width = int(match.group(1))
            height = int(match.group(2))
        except ValueError:
            continue
        if width <= 0 or height <= 0:
            continue
        out.append((width, height))
    return out


def _duration_numbers(text: Any) -> list[float]:
    """Every duration stated in ``text`` (in seconds)."""

    out: list[float] = []
    for match in _DURATION_PATTERN.finditer(str(text or "")):
        try:
            out.append(float(match.group(1)))
        except ValueError:
            continue
    return out


def _contradicting_ratios(text: Any, ratio: Any) -> list[str]:
    """Aspect ratios stated in ``text`` that contradict the authoritative one."""

    try:
        expected = str(ratio).strip()
        parts = expected.split(":", 1)
        expected_pair = (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return []
    out: list[str] = []
    for pair in _ratio_pairs(text):
        if pair == expected_pair:
            continue
        out.append("%d:%d" % pair)
    return sorted(set(out))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _authoritative_control_specs(intent: Any, graph: Any = None) -> dict[str, dict[str, Any]]:
    """Per-shot/node authoritative control fields.

    Each spec holds the authoritative final duration, generation duration and
    cut range for one shot or node.  Sound timings are deliberately excluded:
    they belong to the creative domain and must never excuse a control field.

    The graph is derivative: it may only fill values that the intent left
    unset.  Any explicit graph value that differs from a locked intent value
    is reported as a conflict by ``_control_graph_conflicts``; this function
    simply keeps the intent value.
    """
    out: dict[str, dict[str, Any]] = {}

    def _ensure(key: Any) -> dict[str, Any] | None:
        if key is None:
            return None
        key = str(key)
        if key not in out:
            out[key] = {
                "final": None,
                "gen": None,
                "cut_start": None,
                "cut_end": None,
            }
        return out[key]

    def _apply_explicit(
        spec: dict[str, Any] | None,
        final: Any = None,
        gen: Any = None,
        cut_range: Any = None,
        override: bool = True,
    ) -> None:
        if spec is None:
            return
        final_value = _float_or_none(final)
        if final_value is not None and (override or spec["final"] is None):
            spec["final"] = final_value
        gen_value = _float_or_none(gen)
        if gen_value is not None and (override or spec["gen"] is None):
            spec["gen"] = gen_value
        if isinstance(cut_range, dict):
            for start_key in ("start_sec", "start", "cut_start"):
                if cut_range.get(start_key) is not None:
                    value = _float_or_none(cut_range.get(start_key))
                    if value is not None and (override or spec["cut_start"] is None):
                        spec["cut_start"] = value
                    break
            for end_key in ("end_sec", "end", "cut_end"):
                if cut_range.get(end_key) is not None:
                    value = _float_or_none(cut_range.get(end_key))
                    if value is not None and (override or spec["cut_end"] is None):
                        spec["cut_end"] = value
                    break

    def _apply_defaults(spec: dict[str, Any] | None) -> None:
        if spec is None:
            return
        # Fill generation from final when the authoritative input omits it.
        if spec["gen"] is None and spec["final"] is not None:
            spec["gen"] = spec["final"]
        # Default cut range mirrors the compiler's own default (0 .. final).
        if spec["cut_start"] is None and spec["final"] is not None:
            spec["cut_start"] = 0.0
        if spec["cut_end"] is None and spec["final"] is not None:
            spec["cut_end"] = spec["final"]

    # Intent is authoritative: apply unconditionally.
    if isinstance(intent, dict):
        for shot in (intent.get("shots") or []):
            if not isinstance(shot, dict):
                continue
            sid = shot.get("id")
            if sid is None:
                continue
            _apply_explicit(
                _ensure(sid),
                final=shot.get("duration_sec"),
                gen=shot.get("generation_duration_sec"),
                cut_range=shot.get("cut_range"),
                override=True,
            )

    # Graph is derivative: only fill missing values.
    if isinstance(graph, dict):
        for node in (graph.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            sid = node.get("shot_id")
            nid = node.get("id")
            timing = node.get("shot_timing") if isinstance(node.get("shot_timing"), dict) else {}
            settings = node.get("settings") if isinstance(node.get("settings"), dict) else {}
            final = timing.get("duration_sec")
            if final is None:
                final = settings.get("duration")
            gen = timing.get("generation_duration_sec")
            cut_range = timing.get("cut_range")
            keys: list[str] = []
            if sid is not None:
                keys.append(str(sid))
            if nid is not None:
                keys.append(str(nid))
            for key in keys:
                _apply_explicit(
                    _ensure(key),
                    final=final,
                    gen=gen,
                    cut_range=cut_range,
                    override=False,
                )

    for spec in out.values():
        _apply_defaults(spec)
    return out


def _control_graph_conflicts(intent: Any, graph: Any) -> list[dict[str, Any]]:
    """Detect places where the derived graph contradicts locked intent values."""
    conflicts: list[dict[str, Any]] = []
    if not isinstance(intent, dict) or not isinstance(graph, dict):
        return conflicts

    intent_explicit: dict[str, dict[str, Any]] = {}
    for shot in (intent.get("shots") or []):
        if not isinstance(shot, dict):
            continue
        sid = shot.get("id")
        if sid is None:
            continue
        cut_range = shot.get("cut_range")
        intent_explicit[str(sid)] = {
            "final": _float_or_none(shot.get("duration_sec")),
            "gen": _float_or_none(shot.get("generation_duration_sec")),
            "cut_start": _float_or_none(cut_range.get("start_sec")) if isinstance(cut_range, dict) else None,
            "cut_end": _float_or_none(cut_range.get("end_sec")) if isinstance(cut_range, dict) else None,
        }

    for node in (graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        sid = node.get("shot_id")
        if sid is None:
            continue
        sid = str(sid)
        if sid not in intent_explicit:
            continue
        spec = intent_explicit[sid]
        timing = node.get("shot_timing") if isinstance(node.get("shot_timing"), dict) else {}
        settings = node.get("settings") if isinstance(node.get("settings"), dict) else {}
        final = _float_or_none(timing.get("duration_sec"))
        if final is None:
            final = _float_or_none(settings.get("duration"))
        gen = _float_or_none(timing.get("generation_duration_sec"))
        cut_range = timing.get("cut_range")
        cut_start = _float_or_none(cut_range.get("start_sec")) if isinstance(cut_range, dict) else None
        cut_end = _float_or_none(cut_range.get("end_sec")) if isinstance(cut_range, dict) else None
        for field, graph_value, intent_value in (
            ("final", final, spec["final"]),
            ("gen", gen, spec["gen"]),
            ("cut_start", cut_start, spec["cut_start"]),
            ("cut_end", cut_end, spec["cut_end"]),
        ):
            if graph_value is None or intent_value is None:
                continue
            if abs(graph_value - intent_value) < 1e-6:
                continue
            conflicts.append(
                {
                    "code": "CONTROL_GRAPH_%s_CONFLICT" % field.upper(),
                    "shot_id": sid,
                    "node_id": node.get("id"),
                    "field": field,
                    "intent_value": intent_value,
                    "graph_value": graph_value,
                    "message": "派生图与锁定 intent 在 %s 控制字段冲突。" % field,
                }
            )
    return conflicts


def _shot_allowed_durations(intent: Any, graph: Any = None) -> dict[str, set[float]]:
    """Backwards-compatible view: control numbers per shot/node.

    The ``allowed`` pool is intentionally retired: each control slot is judged
    against its own authoritative field.  This helper remains only so older
    callers receive an empty set.
    """
    specs = _authoritative_control_specs(intent, graph)
    return {key: set() for key in specs}


def _shot_id_for_heading(heading: Any, graph: Any, packages: list[dict[str, Any]]) -> Any:
    text = str(heading or "")
    if isinstance(graph, dict):
        for node in (graph.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            if nid and str(nid) in text:
                return node.get("shot_id")
    for package in packages or []:
        nid = package.get("node_id")
        if nid and str(nid) in text:
            return package.get("shot_id")
    return None


def _parse_control_duration_claims(text: str, block_name: str | None = None) -> list[dict[str, Any]]:
    """Parse explicit duration control claims from ``text``.

    Returns a list of claims.  Each claim has ``field`` (final, gen,
    cut_start, cut_end, settings, total), ``value``, ``span`` and ``raw``.

    Only ``duration`` and ``delivery_settings`` blocks may carry per-shot
    control claims; other blocks only carry whole-film total claims.  This
    keeps creative blocks (action, sound, visual, ...) from being judged as
    control fields.
    """
    claims: list[dict[str, Any]] = []
    body = str(text or "")
    is_control_block = block_name in ("duration", "delivery_settings")

    if is_control_block:
        # final / generation / settings claims.
        for field in ("final", "gen", "settings"):
            for pattern in _CONTROL_DURATION_PATTERNS.get(field, []):
                for match in re.finditer(pattern, body, re.IGNORECASE):
                    claims.append(
                        {
                            "field": field,
                            "value": _float_or_none(match.group(1)),
                            "span": match.span(1),
                            "raw": match.group(0),
                        }
                    )
        # Cut range claims: both endpoints must be captured.
        for match in _CUT_RANGE_PATTERN.finditer(body):
            claims.append(
                {
                    "field": "cut_start",
                    "value": _float_or_none(match.group(1)),
                    "span": match.span(1),
                    "raw": match.group(0),
                }
            )
            claims.append(
                {
                    "field": "cut_end",
                    "value": _float_or_none(match.group(2)),
                    "span": match.span(2),
                    "raw": match.group(0),
                }
            )
        # In a duration block, a bare number + 秒 is the final duration.
        if block_name == "duration":
            covered: list[tuple[int, int]] = [(c["span"][0], c["span"][1]) for c in claims]
            for match in _DURATION_PATTERN.finditer(body):
                span = match.span(1)
                if any(start <= span[0] and end >= span[1] for start, end in covered):
                    continue
                claims.append(
                    {
                        "field": "final",
                        "value": _float_or_none(match.group(1)),
                        "span": span,
                        "raw": match.group(0),
                    }
                )

    # Whole-film totals may appear in any block.
    for pattern in _CONTROL_DURATION_PATTERNS.get("total", []):
        for match in re.finditer(pattern, body, re.IGNORECASE):
            claims.append(
                {
                    "field": "total",
                    "value": _float_or_none(match.group(1)),
                    "span": match.span(1),
                    "raw": match.group(0),
                }
            )

    # A number governed by a total marker (e.g. "全片时长 12 秒") must not
    # also be read as a per-shot final/settings claim just because the pattern
    # "时长" matched inside the total phrase.
    total_spans = [(c["span"][0], c["span"][1]) for c in claims if c["field"] == "total"]
    claims = [
        c
        for c in claims
        if c["field"] == "total"
        or not any(start <= c["span"][0] and end >= c["span"][1] for start, end in total_spans)
    ]
    return claims


def _unknown_control_durations(text: str, block_name: str | None, claims: list[dict[str, Any]]) -> list[str]:
    """Numbers with ``秒`` in a control block that are not recognized claims."""
    if block_name not in ("duration", "delivery_settings"):
        return []
    covered: list[tuple[int, int]] = [(c["span"][0], c["span"][1]) for c in claims]
    unknown: list[str] = []
    for match in _DURATION_PATTERN.finditer(str(text or "")):
        span = match.span(1)
        if any(start <= span[0] and end >= span[1] for start, end in covered):
            continue
        unknown.append(match.group(0))
    return unknown


def _contradicting_durations(
    text: Any,
    duration: Any,
    allowed: set[float] | None = None,
    spec: dict[str, Any] | None = None,
    block_name: str | None = None,
    role: str | None = None,
) -> list[str]:
    """Durations stated in ``text`` that contradict the authoritative control.

    Each control slot is validated against its own authoritative field.
    No cross-field fallback is used.  Whole-film totals are compared against
    the top-level ``duration`` decision.  Unknown or malformed control
    declarations are reported as contradictions so they cannot silently pass.
    """
    total_duration = _float_or_none(duration)
    claims = _parse_control_duration_claims(str(text or ""), block_name)

    # Non-duration-consumer roles may carry platform/intermediate duration
    # numbers that are not authoritative control fields.
    is_non_consumer = role is not None and str(role) not in _DURATION_CONSUMER_ROLES
    if is_non_consumer:
        claims = [c for c in claims if c["field"] == "total"]

    expected_by_field: dict[str, float | None] = {
        "final": spec.get("final") if spec else None,
        "gen": spec.get("gen") if spec else None,
        "cut_start": spec.get("cut_start") if spec else None,
        "cut_end": spec.get("cut_end") if spec else None,
        # delivery_settings "时长" is the delivered shot duration.
        "settings": spec.get("final") if spec else total_duration,
        "total": total_duration,
    }

    out: list[str] = []
    for claim in claims:
        field = claim["field"]
        value = claim["value"]
        expected = expected_by_field.get(field)
        if value is None:
            out.append(claim["raw"])
        elif expected is None:
            out.append("%g" % value)
        elif abs(value - expected) >= 1e-6:
            out.append("%g" % value)

    if not is_non_consumer:
        out.extend(_unknown_control_durations(text, block_name, claims))
    return sorted(set(out))


def _authoritative_decisions(intent: dict[str, Any]) -> dict[str, Any]:
    """The material decisions, as the authoritative input states them.

    Both the intent-handoff shape (``decisions.<field>.value``) and a plain
    contract shape (``aspect_ratio`` / ``duration_sec`` at the top level) are
    accepted. Only *locked* / user-explicit values count as authoritative
    decisions that must be delivered; a proposed value is not a decision yet.
    """

    out: dict[str, Any] = {}
    if not isinstance(intent, dict):
        return out
    decisions = intent.get("decisions")
    if isinstance(decisions, dict):
        for field in ("aspect_ratio", "duration_sec"):
            record = decisions.get(field)
            if not isinstance(record, dict) or "value" not in record:
                continue
            if record.get("source") == "agent_proposed" and not record.get("locked"):
                continue
            out[field] = record.get("value")
        return out
    for field in ("aspect_ratio", "duration_sec"):
        if intent.get(field) is not None:
            out[field] = intent.get(field)
    return out


def _ratio_forms(ratio: Any) -> list[str]:
    """Every surface form that states this aspect ratio."""

    text = str(ratio or "").strip()
    if not text:
        return []
    forms = {text}
    if ":" in text:
        parts = text.split(":", 1)
        forms.add("%s:%s" % (parts[0], parts[1]))
        forms.add("%sx%s" % (parts[0], parts[1]))
        # "9:16" is also written "9比16" or "竖屏 9:16" — the numeric pair is
        # what carries the decision, so the bare pair is a valid form.
        forms.add("%s比%s" % (parts[0], parts[1]))
    return sorted(forms)


def _where_ratio_is_delivered(
    ratio: Any,
    packages: list[dict[str, Any]],
    graph: dict[str, Any] | None,
    markdown: str | None,
) -> list[str]:
    """Where the aspect ratio really reaches the user.

    Returns the list of delivery surfaces that carry the ratio. An empty
    list means the decision did not leave the contract.
    """

    forms = _ratio_forms(ratio)
    if not forms:
        return []
    where: list[str] = []
    if markdown:
        body = _norm(markdown)
        if any(form in body for form in forms):
            where.append("final_markdown")
    for package in packages:
        blocks = package.get("blocks")
        if not isinstance(blocks, dict):
            continue
        for name, value in blocks.items():
            if not isinstance(value, str):
                continue
            if any(form in value for form in forms):
                where.append("package:%s:%s" % (package.get("node_id"), name))
                break
    if isinstance(graph, dict):
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            settings = node.get("settings") or {}
            node_ratio = settings.get("ratio")
            if node_ratio is not None and any(form in str(node_ratio) for form in forms):
                where.append("graph_settings:%s" % node.get("id"))
    return sorted(set(where))


def _where_duration_is_delivered(
    duration: Any,
    packages: list[dict[str, Any]],
    graph: dict[str, Any] | None,
    markdown: str | None,
) -> list[str]:
    """Where the duration really reaches the user."""

    try:
        number = float(duration)
    except (TypeError, ValueError):
        return []
    text_forms = {
        str(duration),
        ("%g" % number),
        ("%d" % round(number)) if float(number).is_integer() else ("%g" % number),
    }
    where: list[str] = []
    if markdown:
        body = _norm(markdown)
        if any(form in body for form in text_forms):
            where.append("final_markdown")
    for package in packages:
        blocks = package.get("blocks")
        if not isinstance(blocks, dict):
            continue
        for name, value in blocks.items():
            if not isinstance(value, str):
                continue
            if any(form in value for form in text_forms):
                where.append("package:%s:%s" % (package.get("node_id"), name))
                break
    if isinstance(graph, dict):
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            settings = node.get("settings") or {}
            node_duration = settings.get("duration")
            if node_duration is not None and str(node_duration) in text_forms:
                where.append("graph_settings:%s" % node.get("id"))
    return sorted(set(where))


def _authoritative_constraints(intent: dict[str, Any]) -> list[dict[str, Any]]:
    """Constraints as declared by the authoritative input."""

    out: list[dict[str, Any]] = []
    raw = intent.get("constraints") if isinstance(intent, dict) else None
    if not isinstance(raw, list):
        return out
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            out.append(
                {
                    "id": "constraint_%02d" % index,
                    "kind": "other",
                    "text": item.strip(),
                    "delivery": "prompt",
                    "source": "user_explicit",
                    "locked": True,
                    "shots": [],
                    "semantics": {},
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        text = _norm(item.get("text"))
        if not text:
            continue
        out.append(
            {
                "id": str(item.get("id") or "constraint_%02d" % index),
                "kind": str(item.get("kind") or "other"),
                "text": text,
                "delivery": str(item.get("delivery") or "prompt"),
                "source": str(item.get("source") or "user_explicit"),
                "locked": bool(item.get("locked")),
                "shots": [str(shot) for shot in (item.get("shots") or [])],
                "semantics": dict(item.get("semantics") or {}),
            }
        )
    return out


def _applicable(constraint: dict[str, Any], shot_id: Any) -> bool:
    shots = constraint.get("shots") or []
    if not shots:
        return True
    if shot_id is None:
        return False
    return str(shot_id) in set(shots)


def _markdown_sections(markdown: str) -> list[tuple[str, str]]:
    """Split the final document into (heading, body) pairs."""

    body = str(markdown or "")
    matches = list(_SECTION_SPLIT.finditer(body))
    if not matches:
        return [("", body)]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.append((match.group(1).strip(), body[match.end():end]))
    return sections


def _sections_for_shot(markdown: str, shot_id: str) -> list[tuple[str, str]]:
    """Sections of the final document that belong to ``shot_id``.

    When the document carries no per-shot heading the whole document is the
    only judgeable surface — it is then judged as one unit.
    """

    sections = _markdown_sections(markdown)
    tagged = [
        (heading, text)
        for heading, text in sections
        if shot_id and shot_id in heading
    ]
    if tagged:
        return tagged
    return sections


def _sections_for_node(markdown: str, node_id: str, shot_id: str | None = None) -> list[tuple[str, str]]:
    sections = _markdown_sections(markdown)
    if node_id:
        tagged = [(heading, text) for heading, text in sections if node_id in heading]
        if tagged:
            return tagged
    if shot_id:
        tagged = [(heading, text) for heading, text in sections if shot_id in heading]
        if tagged:
            return tagged
    return sections


def _world_state_delivery_failures(intent, packages, graph, markdown):
    """Check canonical state atoms against fresh intent, never producer metadata.

    This is deterministic serialization/coverage, not arbitrary-prose or media
    understanding. It intentionally inspects the assigned block and exact node.
    """
    source = intent.get("production_contract", intent) if isinstance(intent, dict) else {}
    if "world_state_initial" not in source and not any(
            "world_state_delta" in shot or "world_state_refs" in shot for shot in source.get("shots", [])):
        return [], 0
    from scripts.compile_shot_graph import resolve_world_states, world_state_blocks, resolve_shot_roles, _candidate_count
    from scripts.production_task_profile import task_roles
    failures, expected, count = [], {}, 0
    try:
        states = resolve_world_states(source)
        for index, shot in enumerate(source.get("shots") or [], 1):
            sid = str(shot.get("id") or "shot_%02d" % index)
            for role in task_roles(source, resolve_shot_roles(shot)):
                blocks, _ = world_state_blocks(states[sid], role)
                if not blocks:
                    continue
                suffixes = ["_" + chr(65 + n) for n in range(_candidate_count(shot))] if role in (
                    "candidate_image", "refined_image", "video_candidate") else [""]
                for suffix in suffixes:
                    expected[sid + "__" + role + suffix] = (role, blocks)
        # Extra actual candidates must be checked too; the source-derived set
        # above prevents deleting every declaration to obtain zero judgements.
        for node in (graph or {}).get("nodes", []):
            sid, role = str(node.get("shot_id") or ""), node.get("role")
            if sid in states:
                blocks, _ = world_state_blocks(states[sid], role)
                if blocks:
                    expected.setdefault(str(node.get("id")), (role, blocks))
    except (ValueError, TypeError, KeyError) as exc:
        return [{"code": "WORLD_STATE_SOURCE_INVALID", "reason": str(exc)}], 0
    by_node = {}
    for package in packages:
        by_node.setdefault(str(package.get("node_id") or ""), []).append(package)
    markers = ("开场可观察状态", "结束可观察状态", "开场声音/对白状态", "结束声音/对白状态")
    def lines(text):
        return sorted(_norm(line) for line in str(text or "").splitlines()
                      if any(marker in line for marker in markers))
    def state_text_matches(actual, expected_text):
        return lines(actual) == lines(expected_text) and _norm(expected_text) in _norm(actual)
    final_role = "video_candidate" if any(role == "video_candidate" for role, _ in expected.values()) else "candidate_image"
    if any(role == final_role for role, _ in expected.values()) and markdown is None:
        failures.append({"code": "WORLD_STATE_FINAL_MISSING"})
    for node_id, (role, blocks) in expected.items():
        matches = by_node.get(node_id, [])
        if len(matches) != 1:
            failures.append({"code": "WORLD_STATE_PACKAGE_MISSING_OR_DUPLICATE", "node_id": node_id})
            continue
        actual = matches[0].get("blocks")
        actual = actual if isinstance(actual, dict) else {}
        sections = [(heading, text) for heading, text in _markdown_sections(markdown or "")
                    if heading.split() and heading.split()[0].strip(chr(96)) == node_id]
        final_blocks = {}
        if role == final_role and markdown is not None and len(sections) != 1:
            failures.append({"code": "WORLD_STATE_FINAL_SECTION_INVALID", "node_id": node_id})
        elif role == final_role and sections:
            for block, text in _markdown_control_blocks(sections[0][1]):
                final_blocks[block] = final_blocks.get(block, "") + "\n" + text
        for block, text in blocks.items():
            count += 1
            if not state_text_matches(actual.get(block), text):
                failures.append({"code": "WORLD_STATE_CONSUMPTION_MISSING", "node_id": node_id,
                                 "block": block, "surface": "canonical_block"})
            if role == final_role and markdown is not None and len(sections) == 1 and not state_text_matches(final_blocks.get(block), text):
                failures.append({"code": "WORLD_STATE_CONSUMPTION_MISSING", "node_id": node_id,
                                 "block": block, "surface": "final_markdown"})
    return failures, count


def verify_delivery(
    intent: dict[str, Any],
    packages: list[dict[str, Any]],
    graph: dict[str, Any] | None = None,
    markdown: str | None = None,
) -> dict[str, Any]:
    """Judge the delivered prompt text against the authoritative intent."""

    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}

    packages = packages if isinstance(packages, list) else []
    constraints = _authoritative_constraints(intent)
    judged = [item for item in constraints if item["delivery"] == "prompt" and item["semantics"]]
    unverifiable = [item["id"] for item in constraints if item["delivery"] == "prompt" and not item["semantics"]]

    by_role: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        by_role.setdefault(str(package.get("role")), []).append(package)

    # --- delivery must exist at all -----------------------------------------
    if not packages:
        failures.append(
            {
                "code": "NO_PROMPT_PACKAGES",
                "message": "交付里没有任何 Prompt Package：0 包不构成一次交付，也不能算通过。",
            }
        )
    checks["packages_present"] = bool(packages)

    # --- structure / version / provenance -----------------------------------
    format_failures: list[dict[str, Any]] = []
    for package in packages:
        declared = package.get("prompt_format")
        if declared != CANONICAL_PROMPT_FORMAT:
            format_failures.append(
                {
                    "code": "PROMPT_PACKAGE_FORMAT_MISMATCH",
                    "node_id": package.get("node_id"),
                    "expected": CANONICAL_PROMPT_FORMAT,
                    "actual": declared,
                }
            )
    if format_failures:
        failures.extend(format_failures)
    checks["prompt_package_format"] = not format_failures

    node_roles: dict[str, str] = {}
    graph_roles_by_shot: dict[str, set[str]] = {}
    if isinstance(graph, dict):
        for node in graph.get("nodes") or []:
            if isinstance(node, dict) and node.get("id"):
                node_roles[str(node["id"])] = str(node.get("role"))
                shot_id = node.get("shot_id")
                if shot_id is not None:
                    graph_roles_by_shot.setdefault(str(shot_id), set()).add(str(node.get("role")))

    structure_failures: list[dict[str, Any]] = []
    for package in packages:
        node_id = str(package.get("node_id") or "")
        if node_roles and node_id and node_id not in node_roles:
            structure_failures.append(
                {
                    "code": "PROMPT_PACKAGE_NODE_UNKNOWN",
                    "node_id": node_id,
                    "message": "提示词包的节点不在权威图里，结构被改动过。",
                }
            )
            continue
        if node_roles and node_id:
            expected_role = node_roles[node_id]
            if str(package.get("role")) != expected_role:
                structure_failures.append(
                    {
                        "code": "PROMPT_PACKAGE_ROLE_MISMATCH",
                        "node_id": node_id,
                        "expected": expected_role,
                        "actual": package.get("role"),
                    }
                )
        if package.get("missing_blocks"):
            structure_failures.append(
                {
                    "code": "PROMPT_PACKAGE_BLOCK_MISSING",
                    "node_id": node_id,
                    "missing": list(package.get("missing_blocks") or []),
                }
            )
    if structure_failures:
        failures.extend(structure_failures)
    checks["package_structure"] = not structure_failures

    # --- provenance: the packages may not invent or rewrite constraints -----
    authoritative_ids = {item["id"] for item in constraints}
    authoritative_by_id = {item["id"]: item for item in constraints}
    provenance_failures: list[dict[str, Any]] = []
    for package in packages:
        for evidence in package.get("constraint_evidence") or []:
            if not isinstance(evidence, dict):
                continue
            cid = evidence.get("constraint_id")
            if cid not in authoritative_ids:
                provenance_failures.append(
                    {
                        "code": "CONSTRAINT_PROVENANCE_UNKNOWN",
                        "node_id": package.get("node_id"),
                        "constraint_id": cid,
                        "message": "提示词包引用了权威输入里不存在的约束。",
                    }
                )
                continue
            declared = authoritative_by_id[cid]
            for key in ("source", "locked"):
                if key in evidence and evidence.get(key) != declared.get(key):
                    provenance_failures.append(
                        {
                            "code": "CONSTRAINT_PROVENANCE_TAMPERED",
                            "node_id": package.get("node_id"),
                            "constraint_id": cid,
                            "field": key,
                            "expected": declared.get(key),
                            "actual": evidence.get(key),
                        }
                    )
    if provenance_failures:
        failures.extend(provenance_failures)
    checks["constraint_provenance"] = not provenance_failures

    # --- candidate coverage: every candidate node in the graph must ship ----
    # Coverage is counted **per node**, not per role: "this shot has one
    # video_candidate" is not enough when the authoritative graph declares a
    # second candidate node. Each graph candidate node must be matched by
    # exactly one package with the same node id and role. Missing, duplicated
    # and mismatched packages are all failures.
    graph_candidate_nodes: dict[str, dict[str, Any]] = {}
    if isinstance(graph, dict):
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict) or not node.get("id"):
                continue
            if str(node.get("role")) not in CANDIDATE_ROLES:
                continue
            graph_candidate_nodes[str(node["id"])] = node

    packages_by_node: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        packages_by_node.setdefault(str(package.get("node_id") or ""), []).append(package)

    candidate_failures: list[dict[str, Any]] = []
    for node_id, node in sorted(graph_candidate_nodes.items()):
        matched = packages_by_node.get(node_id) or []
        if not matched:
            candidate_failures.append(
                {
                    "code": "CANDIDATE_NODE_PACKAGE_MISSING",
                    "node_id": node_id,
                    "shot_id": node.get("shot_id"),
                    "role": node.get("role"),
                    "message": "权威图里的这个候选节点没有对应的提示词包：漏交付一个候选。",
                }
            )
            continue
        if len(matched) > 1:
            candidate_failures.append(
                {
                    "code": "CANDIDATE_NODE_PACKAGE_DUPLICATED",
                    "node_id": node_id,
                    "count": len(matched),
                    "message": "同一个候选节点交了多份提示词包：重复交付。",
                }
            )
        for package in matched:
            if str(package.get("role")) != str(node.get("role")):
                candidate_failures.append(
                    {
                        "code": "CANDIDATE_NODE_ROLE_MISMATCH",
                        "node_id": node_id,
                        "expected": node.get("role"),
                        "actual": package.get("role"),
                        "message": "候选节点的提示词包角色与权威图不一致：错配。",
                    }
                )
            expected_shot = node.get("shot_id")
            if expected_shot is not None and str(package.get("shot_id")) != str(expected_shot):
                candidate_failures.append(
                    {
                        "code": "CANDIDATE_NODE_SHOT_MISMATCH",
                        "node_id": node_id,
                        "expected": expected_shot,
                        "actual": package.get("shot_id"),
                        "message": "候选节点的提示词包挂在别的镜头上：错配。",
                    }
                )

    # A shot that owes a deliverable must have at least one candidate package
    # even when the graph itself does not spell the candidate nodes out.
    shots_with_obligations = sorted(
        {
            shot
            for constraint in judged
            for shot in (constraint.get("shots") or [])
        }
    )
    for shot_id in shots_with_obligations:
        candidates = [
            package
            for package in packages
            if str(package.get("role")) in CANDIDATE_ROLES
            and str(package.get("shot_id")) == shot_id
        ]
        if not candidates:
            candidate_failures.append(
                {
                    "code": "CANDIDATE_PACKAGE_MISSING",
                    "shot_id": shot_id,
                    "message": "该镜头没有任何候选交付物（video_candidate / candidate_image），等于漏交付。",
                }
            )
    if candidate_failures:
        failures.extend(candidate_failures)
    checks["candidate_coverage"] = not candidate_failures
    checks["candidate_nodes_expected"] = len(graph_candidate_nodes)

    # --- a consuming role that exists in the graph must be delivered --------
    delivery_failures: list[dict[str, Any]] = []
    for constraint in judged:
        applicable_shots = constraint.get("shots") or []
        for role in _consuming_roles(constraint["kind"]):
            delivered = [
                package
                for package in by_role.get(role, [])
                if _applicable(constraint, package.get("shot_id"))
            ]
            if delivered:
                continue
            expected_shots = [
                shot
                for shot in applicable_shots
                if role in graph_roles_by_shot.get(shot, set())
            ]
            if expected_shots:
                delivery_failures.append(
                    {
                        "code": "CONSTRAINT_ROLE_PACKAGE_MISSING",
                        "constraint_id": constraint["id"],
                        "role": role,
                        "shots": expected_shots,
                        "message": "该约束在权威图里应当由这个角色消费，但交付里没有它的提示词包。",
                    }
                )
            elif not applicable_shots and not graph_roles_by_shot:
                delivery_failures.append(
                    {
                        "code": "CONSTRAINT_NOT_DELIVERED",
                        "constraint_id": constraint["id"],
                        "role": role,
                        "message": "该约束的消费角色没有任何提示词包，约束没有进入任何提示词。",
                    }
                )
    if delivery_failures:
        failures.extend(delivery_failures)
    checks["constraint_delivery_coverage"] = not delivery_failures

    # --- semantics per (constraint, consuming package) ----------------------
    semantic_results: list[dict[str, Any]] = []
    semantic_failures: list[dict[str, Any]] = []
    for constraint in judged:
        kinds_roles = _consuming_roles(constraint["kind"])
        if not kinds_roles:
            warnings.append(
                {
                    "code": "CONSTRAINT_NO_ROUTE",
                    "constraint_id": constraint["id"],
                    "message": "该约束类型没有消费路由，无法判定兑现；需人工确认。",
                }
            )
            continue
        for role in kinds_roles:
            candidates = [
                package
                for package in by_role.get(role, [])
                if _applicable(constraint, package.get("shot_id"))
            ]
            if not candidates:
                continue
            for package in candidates:
                report = evaluate_constraint(_package_text(package), constraint["semantics"])
                record = {
                    "constraint_id": constraint["id"],
                    "kind": constraint["kind"],
                    "node_id": package.get("node_id"),
                    "role": role,
                    "ok": report["ok"],
                    "required_matched": report["required"]["matched"],
                    "required_missing": report["required"]["missing"],
                    "forbidden_violations": report["forbidden"]["violations"],
                }
                semantic_results.append(record)
                if not report["ok"]:
                    semantic_failures.append(
                        {
                            "code": "CONSTRAINT_SEMANTICS_VIOLATED",
                            "constraint_id": constraint["id"],
                            "node_id": package.get("node_id"),
                            "role": role,
                            "required_missing": report["required"]["missing"],
                            "forbidden_violations": report["forbidden"]["violations"],
                        }
                    )
    if semantic_failures:
        failures.extend(semantic_failures)
    checks["constraint_semantics"] = not semantic_failures
    checks["constraints_judged"] = len(judged)
    checks["constraints_without_semantics"] = unverifiable
    checks["judgements"] = len(semantic_results)

    # --- zero judgements must never read as a pass -------------------------
    if judged and not semantic_results:
        failures.append(
            {
                "code": "CONSTRAINTS_NOT_JUDGED",
                "count": len(judged),
                "message": "有可判定的约束，但一次实际判定都没发生：0 次判定不等于通过。",
            }
        )
    checks["judgements_performed"] = len(semantic_results)

    # --- authoritative decisions must reach the delivered text ---------------
    # A decision that only lives in the contract is not a delivered decision.
    # The aspect ratio and the duration are read from the authoritative input
    # and must appear in the copyable body (or, for the parameters, in the
    # package settings that the platform would receive).
    decision_failures: list[dict[str, Any]] = []
    decision_results: list[dict[str, Any]] = []
    authoritative_decisions = _authoritative_decisions(intent)
    ratio = authoritative_decisions.get("aspect_ratio")
    duration = authoritative_decisions.get("duration_sec")

    if ratio is not None:
        where = _where_ratio_is_delivered(ratio, packages, graph, markdown)
        contradicting = _contradicting_ratios(markdown, ratio)
        if not contradicting:
            for package in packages:
                blocks = package.get("blocks")
                if not isinstance(blocks, dict):
                    continue
                for value in blocks.values():
                    if isinstance(value, str):
                        contradicting.extend(_contradicting_ratios(value, ratio))
            contradicting = sorted(set(contradicting))
        decision_results.append(
            {
                "decision": "aspect_ratio",
                "value": ratio,
                "delivered_in": where,
                "contradicting": contradicting,
            }
        )
        if not where:
            decision_failures.append(
                {
                    "code": "DECISION_ASPECT_RATIO_NOT_DELIVERED",
                    "expected": ratio,
                    "message": "画幅决定只存在于合同/参数里，没有进入可复制的交付正文或设置。",
                }
            )
        if contradicting:
            decision_failures.append(
                {
                    "code": "DECISION_ASPECT_RATIO_CONTRADICTED",
                    "expected": ratio,
                    "actual": contradicting,
                    "message": "交付正文/提示词里出现了与权威画幅不同的画幅。",
                }
            )

    if duration is not None:
        control_specs = _authoritative_control_specs(intent, graph)
        graph_conflicts = _control_graph_conflicts(intent, graph)
        if graph_conflicts:
            decision_failures.extend(graph_conflicts)
        where = _where_duration_is_delivered(duration, packages, graph, markdown)
        contradicting: list[str] = []
        if markdown:
            for heading, text in _markdown_sections(markdown):
                sid = _shot_id_for_heading(heading, graph, packages)
                spec = control_specs.get(str(sid)) if sid is not None else None
                # Prefer node-level spec when the heading names a node.
                section_role: str | None = None
                if isinstance(graph, dict):
                    for node in (graph.get("nodes") or []):
                        nid = node.get("id")
                        if nid and str(nid) in str(heading) and str(nid) in control_specs:
                            spec = control_specs[str(nid)]
                            section_role = node.get("role")
                            break
                # Validate each markdown block with its own block name so
                # creative blocks are not confused with control blocks.
                for md_block_name, block_text in _markdown_control_blocks(text):
                    contradicting.extend(
                        _contradicting_durations(
                            block_text, duration, spec=spec, block_name=md_block_name, role=section_role
                        )
                    )
        for package in packages:
            blocks = package.get("blocks")
            if not isinstance(blocks, dict):
                continue
            sid = package.get("shot_id")
            nid = package.get("node_id")
            role = package.get("role")
            spec = None
            if nid is not None and str(nid) in control_specs:
                spec = control_specs[str(nid)]
            elif sid is not None and str(sid) in control_specs:
                spec = control_specs[str(sid)]
            for block_name, value in blocks.items():
                if isinstance(value, str):
                    contradicting.extend(
                        _contradicting_durations(value, duration, spec=spec, block_name=str(block_name), role=role)
                    )
        contradicting = sorted(set(contradicting))
        decision_results.append(
            {
                "decision": "duration_sec",
                "value": duration,
                "delivered_in": where,
                "contradicting": contradicting,
            }
        )
        if not where:
            decision_failures.append(
                {
                    "code": "DECISION_DURATION_NOT_DELIVERED",
                    "expected": duration,
                    "message": "时长决定只存在于合同/参数里，没有进入可复制的交付正文或设置。",
                }
            )
        if contradicting:
            decision_failures.append(
                {
                    "code": "DECISION_DURATION_CONTRADICTED",
                    "expected": duration,
                    "actual": contradicting,
                    "message": "交付正文/提示词里出现了与权威时长不同的时长。",
                }
            )

    if decision_failures:
        failures.extend(decision_failures)
    checks["decision_delivery"] = not decision_failures
    checks["decision_results"] = decision_results

    # --- the copyable document must not carry unlanded node references ------
    if markdown is not None:
        body = str(markdown)
        if "{{Node" in body or "{{Node " in body:
            failures.append(
                {
                    "code": "DELIVERY_TEXT_HAS_PENDING_NODE_REF",
                    "message": "最终交付正文仍含未落地的 {{Node ...}} 引用，不能声称可直接投喂。",
                }
            )
            checks["delivery_text_ready"] = False
        else:
            checks["delivery_text_ready"] = True
        if not body.strip():
            failures.append(
                {"code": "DELIVERY_TEXT_EMPTY", "message": "最终交付正文为空。"}
            )
            checks["delivery_text_checked"] = False
        else:
            checks["delivery_text_checked"] = True
            text_failures: list[dict[str, Any]] = []
            text_results: list[dict[str, Any]] = []
            for constraint in judged:
                shots = constraint.get("shots") or [None]
                for shot_id in shots:
                    for heading, text in _sections_for_shot(body, str(shot_id) if shot_id else ""):
                        report = evaluate_constraint(text, constraint["semantics"])
                        record = {
                            "constraint_id": constraint["id"],
                            "shot_id": shot_id,
                            "section": heading or None,
                            "ok": report["ok"],
                            "required_missing": report["required"]["missing"],
                            "forbidden_violations": report["forbidden"]["violations"],
                        }
                        text_results.append(record)
                        if not report["ok"]:
                            text_failures.append(
                                {
                                    "code": "DELIVERY_TEXT_CONSTRAINT_VIOLATED",
                                    "constraint_id": constraint["id"],
                                    "shot_id": shot_id,
                                    "section": heading or None,
                                    "required_missing": report["required"]["missing"],
                                    "forbidden_violations": report["forbidden"]["violations"],
                                }
                            )
            if text_failures:
                failures.extend(text_failures)
            checks["delivery_text_semantics"] = not text_failures
            checks["delivery_text_judgements"] = len(text_results)

    # --- craft consumption: shot-level creative directives must reach delivery ---
    craft_directives: list[tuple[str, str, str]] = []
    if isinstance(intent, dict):
        for _shot in (intent.get("shots") or []):
            if not isinstance(_shot, dict):
                continue
            _sid = str(_shot.get("id") or "").strip()
            for _key, _value in _shot.items():
                if _key not in CREATIVE_CRAFT_KEYS:
                    continue
                if isinstance(_value, (list, tuple)):
                    _items = [str(x).strip() for x in _value if str(x).strip()]
                else:
                    _items = [str(_value).strip()] if str(_value).strip() else []
                for _item in _items:
                    craft_directives.append((_sid, _key, _item))

    candidate_packages_by_shot: dict[str, list[dict[str, Any]]] = {}
    deliverable_role = "candidate_image"
    if any(str(_pkg.get("role") or "") == "video_candidate" for _pkg in packages):
        deliverable_role = "video_candidate"
    for _pkg in packages:
        if str(_pkg.get("role") or "") != deliverable_role:
            continue
        candidate_packages_by_shot.setdefault(str(_pkg.get("shot_id") or ""), []).append(_pkg)

    craft_failures: list[dict[str, Any]] = []
    for _sid, _key, _value in craft_directives:
        _norm_value = _norm(_value)
        candidates = candidate_packages_by_shot.get(_sid) or []
        # If no candidate package exists, candidate coverage already reports it.
        # Still record one consumption failure so a missing candidate cannot be
        # masked by craft text elsewhere.
        if not candidates:
            craft_failures.append(
                {
                    "code": "CRAFT_CONSUMPTION_MISSING",
                    "shot_id": _sid,
                    "craft_key": _key,
                    "value": _value,
                    "node_id": None,
                    "surface": "candidate_package",
                    "message": "镜头级工艺决定未进入该镜头的交付正文/提示词包。",
                }
            )
            continue
        for _pkg in candidates:
            node_id = str(_pkg.get("node_id") or "")
            # The positive block in the canonical package must carry the craft.
            if _norm_value not in _norm(_package_text(_pkg)):
                craft_failures.append(
                    {
                        "code": "CRAFT_CONSUMPTION_MISSING",
                        "shot_id": _sid,
                        "craft_key": _key,
                        "value": _value,
                        "node_id": node_id,
                        "surface": "candidate_package",
                        "message": "镜头级工艺决定未进入该候选的正本块。",
                    }
                )
            # The corresponding final Markdown segment must carry the same craft.
            if markdown:
                _sections = _sections_for_node(markdown, node_id, _sid)
                _md_text = _norm(" ".join(text for _heading, text in _sections))
                if _norm_value not in _md_text:
                    craft_failures.append(
                        {
                            "code": "CRAFT_CONSUMPTION_MISSING",
                            "shot_id": _sid,
                            "craft_key": _key,
                            "value": _value,
                            "node_id": node_id,
                            "surface": "final_markdown",
                            "message": "镜头级工艺决定未进入该候选对应的最终 Markdown 段。",
                        }
                    )
    if craft_failures:
        failures.extend(craft_failures)
    checks["craft_consumption"] = not craft_failures
    checks["craft_directives_checked"] = len(craft_directives)

    world_failures, world_count = _world_state_delivery_failures(intent, packages, graph, markdown)
    failures.extend(world_failures)
    checks["world_state_consumption"] = not world_failures
    checks["world_state_judgements"] = world_count

    status = "FAIL" if failures else ("UNVERIFIED" if unverifiable else "PASS")
    if unverifiable and status != "FAIL":
        warnings.append(
            {
                "code": "CONSTRAINTS_UNVERIFIABLE",
                "constraint_ids": unverifiable,
                "message": "这些约束没有可判定的语义标记，只能标未验证，不能当作已兑现。",
            }
        )
    return {
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "semantic_results": semantic_results,
        "unverified_constraints": unverifiable,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_maybe(path: Path | None) -> Any:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="final delivery semantic acceptance")
    parser.add_argument("--intent", help="权威输入（intent-handoff/v1 或合同 JSON）")
    parser.add_argument("--out", help="交付目录（读 04_prompt_packages.jsonl / 13_Final_Prompt.md）")
    parser.add_argument("--packages", help="直接指定 Prompt Package JSONL")
    parser.add_argument("--markdown", help="直接指定最终交付 Markdown")
    parser.add_argument("--graph", help="直接指定权威图 JSON")
    parser.add_argument("--report", help="把结果写成 JSON")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.intent:
        parser.print_help()
        return 2

    intent_path = Path(args.intent)
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if isinstance(intent.get("production_contract"), dict):
        intent = intent["production_contract"]

    packages: list[dict[str, Any]] = []
    packages_path = Path(args.packages) if args.packages else None
    if packages_path is None and args.out:
        packages_path = Path(args.out) / "04_prompt_packages.jsonl"
    if packages_path and packages_path.exists():
        packages = _load_jsonl(packages_path)

    graph = _load_maybe(Path(args.graph) if args.graph else (Path(args.out) / "03_shot_graph_plan.json" if args.out else None))

    markdown = None
    markdown_path = Path(args.markdown) if args.markdown else None
    if markdown_path is None and args.out:
        candidate = Path(args.out) / "13_Final_Prompt.md"
        if candidate.exists():
            markdown_path = candidate
    if markdown_path and markdown_path.exists():
        markdown = markdown_path.read_text(encoding="utf-8")

    result = verify_delivery(intent, packages, graph, markdown)
    if args.report:
        Path(args.report).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(
        {
            "status": result["status"],
            "failures": result["failures"],
            "checks": result["checks"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if result["status"] == "PASS" else 1


def self_test() -> int:
    intent = {
        "intent_format": "intent-handoff/v1",
        "goal": "t",
        "task_type": "prompt_only",
        "decisions": {},
        "shots": [],
        "constraints": [
            {
                "id": "c_camera",
                "kind": "camera",
                "text": "相机固定俯拍。",
                "delivery": "prompt",
                "source": "user_explicit",
                "locked": True,
                "shots": ["shot_01"],
                "semantics": {"required_any": ["俯拍"], "forbidden": ["平视"]},
            }
        ],
    }
    good = {
        "prompt_format": "prompt-package/v1",
        "node_id": "shot_01__video_candidate_A",
        "role": "video_candidate",
        "shot_id": "shot_01",
        "blocks": {"visual": "相机固定俯拍，机位不移动。"},
        "missing_blocks": [],
        "constraint_evidence": [
            {"constraint_id": "c_camera", "source": "user_explicit", "locked": True}
        ],
    }
    bad = json.loads(json.dumps(good))
    bad["blocks"]["visual"] = "相机平视，机位不移动。"
    if verify_delivery(intent, [good])["status"] != "PASS":
        print("self-test: good package must PASS")
        return 1
    if verify_delivery(intent, [bad])["status"] != "FAIL":
        print("self-test: tampered package must FAIL")
        return 1
    synonym = json.loads(json.dumps(good))
    synonym["blocks"]["visual"] = "正上方俯视，固定机位。"
    if verify_delivery(intent, [synonym])["status"] != "PASS":
        print("self-test: legal synonym must PASS")
        return 1
    if verify_delivery(intent, [])["status"] != "FAIL":
        print("self-test: empty delivery must FAIL")
        return 1

    # A constraint without a judgeable meaning must not read as a pass.
    unsem = json.loads(json.dumps(intent))
    unsem["constraints"] = [
        {
            "id": "c_other",
            "kind": "other",
            "text": "某种无法判定语义的要求",
            "delivery": "prompt",
            "source": "user_explicit",
            "locked": True,
            "shots": [],
            "semantics": {},
        }
    ]
    clean = json.loads(json.dumps(good))
    clean["constraint_evidence"] = []
    if verify_delivery(unsem, [clean])["status"] != "UNVERIFIED":
        print("self-test: unsemantically constrained delivery must be UNVERIFIED")
        return 1

    # A final document that contradicts the constraint must FAIL.
    bad_text = verify_delivery(intent, [good], None, "## shot_01\n相机平视。")
    if bad_text["status"] != "FAIL":
        print("self-test: contradictory final document must FAIL")
        return 1

    print("self-test 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
