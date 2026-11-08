#!/usr/bin/env python3
"""Extract per-node truth units from a LibTV work (read-only).

Reads the canvas summary, then reads each media node's params once and caches
it. No generation, no upload, no ignition: `libtv project` and `libtv node`
are read-only queries.

Usage:
  python scripts/work_units.py --project <uuid> --out units.json
  python scripts/work_units.py --graph <readback.json> --project <uuid> --out units.json
  python scripts/work_units.py --graph <readback.json> --cache-dir <dir> --out units.json --offline
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_CLI = str(Path.home() / ".libtv" / "libtv.exe")
DEFAULT_UNIT_TYPES = ("video",)

BLOCK_RULES = {
    "active_assets": re.compile(r"ACTIVE\s+ASSETS", re.IGNORECASE),
    "image_manifest": re.compile(r"@Image\d+"),
    "output_contract": re.compile(r"OUTPUT\s+CONTRACT", re.IGNORECASE),
    "timed_beats": re.compile(r"\d+(\.\d+)?\s*[-–~]\s*\d+(\.\d+)?", re.MULTILINE),
}


def run_cli(cli: str, args: list[str]) -> tuple[int, dict | None, str]:
    proc = subprocess.run([cli] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw = proc.stdout.decode("utf-8", "replace").strip()
    try:
        return proc.returncode, json.loads(raw), raw
    except Exception:
        return proc.returncode, None, raw + proc.stderr.decode("utf-8", "replace")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def node_params(payload: dict) -> dict:
    return ((payload or {}).get("data") or {}).get("params") or {}


def prompt_blocks(prompt: str) -> dict:
    return {name: bool(rule.search(prompt or "")) for name, rule in BLOCK_RULES.items()}


def unit_from(node: dict, readback: dict) -> dict:
    data = (readback or {}).get("data") or {}
    params = data.get("params") or {}
    settings = params.get("settings") or {}
    prompt = str(params.get("prompt") or "")
    # `text` nodes carry their body in data.content, not in params.prompt.
    raw_content = data.get("content")
    if isinstance(raw_content, list):
        content = "\n".join(str(part) for part in raw_content)
    else:
        content = str(raw_content or "")
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type") or node.get("node_type"),
        "model": params.get("model"),
        "modeType": params.get("modeType"),
        "duration": settings.get("duration"),
        "ratio": settings.get("ratio"),
        "quality": settings.get("quality"),
        "enableSound": settings.get("enableSound"),
        "imageList": len(params.get("imageList") or []),
        "audioList": len(params.get("audioList") or []),
        "prompt_len": len(prompt) if prompt else len(content),
        "content_len": len(content),
        "blocks": prompt_blocks(prompt),
        "evidence_class": "copy_readback",
    }


def build_units(graph: dict, project: str, cli: str, cache_dir: Path, offline: bool, limit: int | None, unit_types=DEFAULT_UNIT_TYPES) -> dict:
    nodes = [node for node in graph.get("nodes") or [] if (node.get("type") or node.get("node_type")) in unit_types]
    selected = nodes[:limit] if limit else nodes
    cache_dir.mkdir(parents=True, exist_ok=True)
    units, unreadable = [], []
    for node in selected:
        node_id = str(node.get("id"))
        cache_file = cache_dir / ("%s.json" % node_id)
        readback = None
        if cache_file.is_file():
            readback = load(str(cache_file))
        elif not offline and cli:
            code, payload, raw = run_cli(cli, ["node", node_id, "-p", project])
            if code == 0 and payload:
                cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                readback = payload
            else:
                unreadable.append({"id": node_id, "exit": code, "tail": raw[-200:]})
        if readback is None:
            if not cache_file.is_file():
                unreadable.append({"id": node_id, "reason": "no_cache_no_cli"})
            continue
        units.append(unit_from(node, readback))
    return {
        "project": project,
        "unit_types": list(unit_types),
        "unit_type": unit_types[0] if len(unit_types) == 1 else None,
        "nodes_in_graph": len(nodes),
        "sampled": len(selected),
        "units_total": len(units),
        "unreadable": unreadable,
        "units": units,
    }


def self_test() -> int:
    cases = []
    sample = {
        "data": {
            "params": {
                "model": "Seedance 2.5",
                "modeType": "mixed2video",
                "settings": {"duration": 10, "ratio": "16:9", "enableSound": "on"},
                "imageList": [1, 2],
                "audioList": [1],
                "prompt": "ACTIVE ASSETS\n@Image1 = x\nOUTPUT CONTRACT\n0.0-5.0 beat",
            }
        }
    }
    unit = unit_from({"id": "a", "name": "n", "type": "video"}, sample)
    cases.append(("params_extracted", unit["model"] == "Seedance 2.5" and unit["duration"] == 10))
    cases.append(("counts_extracted", unit["imageList"] == 2 and unit["audioList"] == 1))
    cases.append(("blocks_detected", all(unit["blocks"].values())))
    empty = unit_from({"id": "b", "type": "video"}, {})
    cases.append(("missing_params_are_null", empty["model"] is None and empty["imageList"] == 0))
    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail", "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--graph")
    parser.add_argument("--out")
    parser.add_argument("--cache-dir", default="work/units_cache")
    parser.add_argument("--cli", default=DEFAULT_CLI)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--types", default=",".join(DEFAULT_UNIT_TYPES))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.project or not args.out:
        parser.error("--project and --out are required unless --self-test")

    graph = load(args.graph) if args.graph else None
    if graph is None:
        if args.offline:
            parser.error("--graph is required together with --offline")
        code, payload, raw = run_cli(args.cli, ["project", args.project])
        if code != 0 or payload is None:
            print(json.dumps({"status": "FAIL", "exit": code, "tail": raw[-300:]}, ensure_ascii=False, indent=2))
            return 1
        graph = payload

    unit_types = tuple(part.strip() for part in args.types.split(",") if part.strip())
    result = build_units(graph, args.project, args.cli, Path(args.cache_dir), args.offline, args.limit, unit_types)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "units"}
    summary["status"] = "PASS" if result["units_total"] else "FAIL"
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result["units_total"] else 1


if __name__ == "__main__":
    sys.exit(main())
