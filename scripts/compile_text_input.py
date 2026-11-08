"""Parse a simple text or Markdown script into compiler input.

The parser is intentionally conservative: structured shot lines are parsed
exactly when present; otherwise blank-line/sentence paragraphs become shot
placeholders with explicit assumptions in the compiler.
"""

from __future__ import annotations

import re
from typing import Any


SHOT_PATTERNS = [
    re.compile(r"^\s*(?:镜头|shot)\s*(\d+)\s*[\|:：\-—]?\s*(?:(\d+(?:\.\d+)?)\s*秒)?\s*(.*)$", re.I),
    re.compile(r"^\s*(\d+)[\.\)、\s]+(?:(\d+(?:\.\d+)?)\s*秒)?\s*(.*)$"),
]

ENTITY_KEYWORDS = [
    ("main_character", "character", ["旅人", "男人", "女人", "孩子", "阿婆", "孙子"]),
    ("primary_scene", "scene", ["房间", "酒店", "旅馆", "走廊", "村寨", "梯田"]),
    ("primary_prop", "prop", ["行李箱", "行李", "杯子", "证件", "风筝", "门", "钥匙"]),
]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t-—:：")


def parse_text_input(text: str, goal: str | None = None, duration_sec: int | None = None) -> dict[str, Any]:
    """Return a JSON-compatible input dict for compile_contract."""

    lines = [line.strip() for line in text.splitlines()]
    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        if not line:
            continue
        parsed = None
        for pattern in SHOT_PATTERNS:
            match = pattern.match(line)
            if match:
                parsed = match
                break
        if parsed:
            if current:
                shots.append(current)
            shot_id = f"shot_{int(parsed.group(1)):02d}"
            seconds = float(parsed.group(2)) if parsed.group(2) else None
            description = _clean(parsed.group(3) or "")
            current = {"id": shot_id, "description": description, "risk": "medium"}
            if seconds:
                current["duration_sec"] = seconds
            continue
        if current is not None:
            current["description"] = _clean((current.get("description") or "") + " " + line)

    if current:
        shots.append(current)

    if not shots:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            paragraphs = ["未命名镜头"]
        shots = [
            {"id": f"shot_{index:02d}", "description": _clean(paragraph), "risk": "medium"}
            for index, paragraph in enumerate(paragraphs, start=1)
        ]

    inferred_duration = duration_sec
    if inferred_duration is None:
        durations = [float(s.get("duration_sec") or 0) for s in shots]
        inferred_duration = int(sum(durations)) if sum(durations) > 0 else 120

    entities: list[dict[str, Any]] = []
    for entity_id, kind, keywords in ENTITY_KEYWORDS:
        matched_keywords = [keyword for keyword in keywords if keyword in text]
        if matched_keywords:
            entities.append(
                {
                    "id": entity_id,
                    "kind": kind,
                    "name": entity_id,
                    "description": None,
                    "inferred_keywords": matched_keywords,
                    "identity_status": "unresolved_inferred",
                    "reuse_count": 1,
                    "state_versions": 1,
                    "needs_confirmation": True,
                }
            )

    return {
        "goal": goal or _clean(text.splitlines()[0] if text.strip() else "未命名生产目标"),
        "duration_sec": inferred_duration,
        "entities": entities,
        "shots": shots,
        "production_mode": "production_build",
        "delivery": {"ignition_allowed": False},
    }


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    parser.add_argument("--goal")
    parser.add_argument("--duration-sec", type=int)
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.text, "r", encoding="utf-8") as handle:
        text = handle.read()
    result = parse_text_input(text, args.goal, args.duration_sec)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
