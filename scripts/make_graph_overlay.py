"""make_graph_overlay.py - build the C-path overlay for graph_plan_lint from a
compiled LibTV command plan.

The overlay carries only facts that already exist in the plan:
  operation      - always "create" (apply_libtv_plan only ever creates)
  node_platform  - model / modeType per node, as emitted by the compiler
  authored_params- the flat settings the plan will write (never nested
                   `settings`, never derived fields such as imageListOrder)
  media_ready    - deliberately EMPTY: nothing has been generated yet, so the
                   media gate must stay "not verified" instead of being faked

Read-only, offline.

Usage:
  python make_graph_overlay.py <08_libtv_command_plan.json> --out overlay.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(plan: dict) -> dict:
    node_platform: dict[str, dict] = {}
    authored_params: dict[str, dict] = {}
    for cmd in plan.get("commands", []):
        if cmd.get("kind") != "node_create":
            continue
        name = cmd["name"]
        platform = {}
        if cmd.get("model"):
            platform["model"] = cmd["model"]
        if cmd.get("mode_type"):
            platform["modeType"] = cmd["mode_type"]
        if platform:
            node_platform[name] = platform
        settings = cmd.get("settings") or {}
        if settings:
            # flat keys only; nesting under "settings" is the update-time trap
            authored_params[name] = dict(settings)
    return {
        "operation": "create",
        "node_platform": node_platform,
        "authored_params": authored_params,
        "media_ready": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    overlay = build(plan)
    Path(args.out).write_text(json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "operation": overlay["operation"],
                "node_platform": len(overlay["node_platform"]),
                "authored_params": len(overlay["authored_params"]),
                "media_ready": len(overlay["media_ready"]),
                "out": args.out,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
