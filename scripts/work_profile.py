#!/usr/bin/env python3
"""Build a per-work profile from work_units.py output.

Why this is mandatory before compiling a reverse task: cross-work transfer was
measured and failed. Handing work A's modal model / ratio / duration to work B
scored model 0.25 / 0.00 / 0.00 and duration 0.67 / 0.07 / 0.00, so every work
needs its own numbers read out of its own canvas.

Read-only over cached units; no LibTV call, no generation.

Usage:
  python scripts/work_profile.py --units a.json,b.json --graph readback.json --out profile.json
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path


BLOCK_FIELDS = ("active_assets", "image_manifest", "output_contract", "timed_beats")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def top(values, limit=5):
    counter = collections.Counter(value for value in values if value not in (None, ""))
    return [[value, count] for value, count in counter.most_common(limit)]


def median(values):
    numbers = [value for value in values if isinstance(value, (int, float))]
    return statistics.median(numbers) if numbers else None


def block_rates(units: list[dict]) -> dict:
    if not units:
        return {}
    return {
        block: round(sum(1 for unit in units if (unit.get("blocks") or {}).get(block)) / len(units), 4)
        for block in BLOCK_FIELDS
    }


def profile_from(unit_files: list[dict], graph: dict | None, source_access: str) -> dict:
    by_type: dict[str, list[dict]] = collections.defaultdict(list)
    sources = []
    project = None
    for payload in unit_files:
        project = project or payload.get("project")
        sources.append(payload.get("project"))
        types = payload.get("unit_types") or ([payload["unit_type"]] if payload.get("unit_type") else [])
        for unit in payload.get("units") or []:
            kind = unit.get("type") or (types[0] if len(types) == 1 else "unknown")
            by_type[kind].append(unit)

    video = by_type.get("video") or []
    text = by_type.get("text") or []

    structure = {}
    if graph:
        nodes = graph.get("nodes") or []
        structure = {
            "nodes": len(nodes),
            "edges": len(graph.get("edges") or []),
            "groups": sum(1 for node in nodes if (node.get("type") or node.get("node_type")) == "group"),
            "type_counts": dict(collections.Counter((node.get("type") or node.get("node_type")) for node in nodes)),
        }

    return {
        "work": project,
        "source_access": source_access,
        "structure": structure,
        "units": {kind: len(items) for kind, items in sorted(by_type.items())},
        "video": {
            "model_top": top(unit.get("model") for unit in video),
            "mode_type_top": top(unit.get("modeType") for unit in video),
            "duration_top": top((unit.get("duration") for unit in video), 8),
            "ratio_top": top(unit.get("ratio") for unit in video),
            "enable_sound_top": top(unit.get("enableSound") for unit in video),
            "image_refs_median": median([unit.get("imageList") for unit in video]),
            "audio_refs_median": median([unit.get("audioList") for unit in video]),
            "prompt_len_median": median([unit.get("prompt_len") for unit in video]),
            "block_rates": block_rates(video),
        },
        "text": {
            "model_top": top(unit.get("model") for unit in text),
            "body_len_median": median([unit.get("content_len") for unit in text]),
            "body_len_max": max([unit.get("content_len") or 0 for unit in text], default=0),
        },
        "image": {"model_top": top(unit.get("model") for unit in by_type.get("image") or [])},
        "audio": {"model_top": top(unit.get("model") for unit in by_type.get("audio") or [])},
        "derived_from": sources,
        "evidence_class": "copy_readback" if source_access == "copy_readback" else source_access,
    }


def self_test() -> int:
    cases = []
    payload = {
        "project": "p",
        "unit_types": ["video"],
        "units": [
            {"type": "video", "model": "Seedance 2.5", "modeType": "mixed2video", "duration": 30,
             "ratio": "21:9", "enableSound": "on", "imageList": 4, "audioList": 1, "prompt_len": 100,
             "blocks": {"active_assets": True, "image_manifest": True, "output_contract": False, "timed_beats": True}},
            {"type": "video", "model": "Seedance 2.5", "modeType": "mixed2video", "duration": 10,
             "ratio": "21:9", "enableSound": "on", "imageList": 4, "audioList": 1, "prompt_len": 200,
             "blocks": {"active_assets": False, "image_manifest": True, "output_contract": False, "timed_beats": True}},
        ],
    }
    profile = profile_from([payload], {"nodes": [{"type": "video"}, {"type": "group"}], "edges": [1]}, "copy_readback")
    cases.append(("dominant_model", profile["video"]["model_top"][0][0] == "Seedance 2.5"))
    cases.append(("duration_distribution", dict((str(k), v) for k, v in profile["video"]["duration_top"]) == {"30": 1, "10": 1}))
    cases.append(("refs_median", profile["video"]["image_refs_median"] == 4))
    cases.append(("block_rate_half", profile["video"]["block_rates"]["active_assets"] == 0.5))
    cases.append(("structure_read", profile["structure"] == {"nodes": 2, "edges": 1, "groups": 1, "type_counts": {"video": 1, "group": 1}}))
    cases.append(("units_counted", profile["units"] == {"video": 2}))
    empty = profile_from([{"project": "q", "units": []}], None, "none")
    cases.append(("empty_stays_null", empty["video"]["duration_top"] == [] and empty["video"]["image_refs_median"] is None))
    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail", "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units")
    parser.add_argument("--graph")
    parser.add_argument("--source-access", default="copy_readback")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.units:
        parser.error("--units is required unless --self-test")

    payloads = [load(path.strip()) for path in args.units.split(",") if path.strip()]
    graph = load(args.graph) if args.graph else None
    profile = profile_from(payloads, graph, args.source_access)
    text = json.dumps(profile, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
