#!/usr/bin/env python3
"""Dry-run or apply a compiled LibTV command plan without ignition.

The default is dry-run. --execute only creates projects/groups/nodes/links;
it never appends --run and refuses any plan command with run=true.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


def resolve_libtv_binary() -> Path:
    explicit = os.environ.get("LIBTV_BIN")
    if explicit:
        return Path(explicit).expanduser()
    found = shutil.which("libtv")
    if found is None:
        found = shutil.which("libtv.exe")
    if found:
        return Path(found)
    home_install = Path.home() / ".libtv" / ("libtv.exe" if os.name == "nt" else "libtv")
    if home_install.exists():
        return home_install
    return Path("libtv")


LIBTV = resolve_libtv_binary()


def _node_args(
    command: dict[str, Any],
    project_uuid: str,
    incoming: list[str] | None = None,
    with_prompt: bool = True,
) -> list[str]:
    args = [
        str(LIBTV),
        "node",
        "--x",
        str(command.get("x", 0)),
        "--y",
        str(command.get("y", 0)),
        "create",
        command["name"],
        "-t",
        command["node_type"],
        "-p",
        project_uuid,
    ]
    model = command.get("model")
    if model:
        args.extend(["-s", f"model={model}"])
    mode_type = command.get("mode_type")
    if mode_type:
        args.extend(["-s", f"modeType={mode_type}"])
    for key, value in (command.get("settings") or {}).items():
        args.extend(["-s", f"{key}={value}"])
    if with_prompt:
        prompt = command.get("prompt")
        if prompt:
            args.extend(["--prompt", prompt])
        content = command.get("content")
        if content is not None:
            args.extend(["-u", "content=" + json.dumps(content, ensure_ascii=False)])
    for source in incoming or []:
        args.extend(["--left", source])
    return args


def build_phases(plan: dict[str, Any], project_uuid: str) -> dict[str, Any]:
    """Split a plan into ordered phases.

    Nodes are ordered by their incoming links and created with those links
    inlined. Cyclic dependencies and run=true commands are rejected.
    """
    groups: list[list[str]] = []
    links: list[list[str]] = []
    prompts: list[list[str]] = []
    by_group: dict[str, list[str]] = defaultdict(list)
    node_cmds: list[dict[str, Any]] = []
    incoming: dict[str, list[str]] = defaultdict(list)
    seen_node_names: set[str] = set()
    for command in plan.get("commands") or []:
        if command.get("run") is True:
            raise ValueError("plan contains run=true; refusing to execute")
        kind = command.get("kind")
        if kind == "group_create":
            groups.append([str(LIBTV), "group", "create", command["name"], "-p", project_uuid])
        elif kind == "node_create":
            name = command.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("invalid planned node name")
            if name in seen_node_names:
                raise ValueError("duplicate planned node name: %s" % name)
            seen_node_names.add(name)
            node_cmds.append(command)
            group_name = command.get("group_name")
            if group_name:
                by_group[group_name].append(command["name"])
        elif kind == "node_link":
            links.append(
                [str(LIBTV), "node", command["target"], "--left", command["left"], "-p", project_uuid]
            )
            incoming[command["target"]].append(command["left"])

    # The platform validates both `--left` and `{{Node "..."}}` at write time:
    # a video node refuses to be created without its image/video references, and
    # a placeholder must resolve to an existing node. So nodes are created in
    # dependency order with their links inlined; cycles are rejected.

    names = [c["name"] for c in node_cmds]
    name_set = set(names)
    remaining = {c["name"]: [s for s in incoming.get(c["name"], []) if s in name_set] for c in node_cmds}
    resolved: set[str] = set()
    ordered_cmds: list[dict[str, Any]] = []
    while remaining:
        ready = [n for n, deps in remaining.items() if all(d in resolved for d in deps)]
        if not ready:
            raise ValueError("cyclic dependency in plan: %s" % ", ".join(sorted(remaining)))
        by_name = {c["name"]: c for c in node_cmds}
        for n in ready:
            ordered_cmds.append(by_name[n])
            resolved.add(n)
            remaining.pop(n, None)

    nodes: list[list[str]] = []
    node_names: list[str] = []
    for command in ordered_cmds:
        nodes.append(_node_args(command, project_uuid, incoming.get(command["name"], []), with_prompt=True))
        node_names.append(command["name"])
    binds: list[list[str]] = []
    for group_name, names in by_group.items():
        bind = [str(LIBTV), "group", group_name, "-p", project_uuid]
        for name in names:
            bind.extend(["--node", name])
        binds.append(bind)
    return {
        "groups": groups,
        "nodes": nodes,
        "node_names": node_names,
        "prompts": prompts,
        "links": links,
        "binds": binds,
    }


def build_commands(plan: dict[str, Any], project_uuid: str) -> list[list[str]]:
    """Back-compat flat view (dry-run display)."""
    phases = build_phases(plan, project_uuid)
    return phases["groups"] + phases["nodes"] + phases["prompts"] + phases["links"] + phases["binds"]


def _names(args: list[str]) -> set[str] | None:
    try:
        data = _read_json(args)
    except RuntimeError:
        return None
    if not isinstance(data, dict):
        return None
    if "nodes" in data:
        rows = data["nodes"]
    elif "groups" in data:
        rows = data["groups"]
    else:
        return None
    if not isinstance(rows, list):
        return None
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return None
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        if name in names:
            return None
        names.add(name)
    return names


def _run(command: list[str], stats: dict, key: str) -> None:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError("command failed: %s\n%s" % (" ".join(command), proc.stderr.decode("utf-8", "replace")))
    stats[key] += 1


def _read_json(args):
    proc = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("command failed: %s" % message if message else "command failed")
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        raise RuntimeError("invalid JSON output")
    if not isinstance(data, dict):
        raise RuntimeError("command output is not a JSON object")
    return data


def _existing_nodes(project_uuid, commands):
    inventory = _read_json([str(LIBTV), "node", "list", "-p", project_uuid])
    rows = inventory.get("nodes")
    if not isinstance(rows, list):
        raise RuntimeError("invalid node inventory")
    by_name = {}
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("invalid node inventory row")
        node_id = row.get("id")
        name = row.get("name")
        if not isinstance(node_id, str) or not node_id.strip():
            raise RuntimeError("invalid node id")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError("invalid node name")
        if node_id in by_id or name in by_name:
            raise RuntimeError("ambiguous node inventory")
        by_id[node_id] = row
        by_name[name] = row

    skip_names = set()
    for command in commands or []:
        if not isinstance(command, dict):
            continue
        if "kind" in command and command.get("kind") != "node_create":
            continue
        name = command.get("name")
        if not isinstance(name, str) or name not in by_name:
            continue
        node_id = by_name[name]["id"]
        detail = _read_json([str(LIBTV), "node", node_id, "-p", project_uuid])
        if isinstance(detail, dict) and "nodes" in detail:
            detail_nodes = detail.get("nodes")
            if not isinstance(detail_nodes, list) or len(detail_nodes) != 1 or not isinstance(detail_nodes[0], dict):
                raise RuntimeError("invalid node detail")
            node = detail_nodes[0]
        elif isinstance(detail, dict):
            node = detail
        else:
            raise RuntimeError("invalid node detail")
        if not isinstance(node, dict) or node.get("id") != node_id:
            raise RuntimeError("node id mismatch")
        if node.get("name") != name:
            raise RuntimeError('node name mismatch')
        if not _node_matches(command, node):
            raise RuntimeError("node parameters mismatch")
        skip_names.add(name)
    return skip_names


def _node_matches(command, node):
    if not isinstance(command, dict) or not isinstance(node, dict):
        return False
    node_type = command.get("node_type")
    if node_type is None or type(node.get("type")) is not type(node_type) or node.get("type") != node_type:
        return False

    model = command.get("model")
    mode_type = command.get("mode_type")
    prompt = command.get("prompt")
    settings = command.get("settings")
    if settings is None:
        settings = {}
    if not isinstance(settings, dict):
        return False
    content = command.get("content")
    needs_params = bool(model) or bool(mode_type) or bool(prompt) or bool(settings)
    params = node.get("params")
    if needs_params and not isinstance(params, dict):
        return False
    if not isinstance(params, dict):
        params = {}

    if model:
        try:
            if json.dumps(params.get("model"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                return False
        except (TypeError, ValueError):
            return False
    if mode_type:
        try:
            if json.dumps(params.get("modeType"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(mode_type, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                return False
        except (TypeError, ValueError):
            return False
    if prompt:
        try:
            if json.dumps(params.get("prompt"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                return False
        except (TypeError, ValueError):
            return False
    if settings:
        params_settings = params.get("settings")
        if not isinstance(params_settings, dict):
            return False
        for key, value in settings.items():
            if key not in params_settings:
                return False
            try:
                if json.dumps(params_settings[key], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                    return False
            except (TypeError, ValueError):
                return False
    if content is not None:
        try:
            if json.dumps(node.get("content"), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                return False
        except (TypeError, ValueError):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("--project-uuid", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    with open(args.plan, "r", encoding="utf-8") as handle:
        plan = json.load(handle)
    phases = build_phases(plan, args.project_uuid)
    if not args.execute:
        print(json.dumps({"mode": "dry_run", "counts": {k: len(v) for k, v in phases.items() if isinstance(v, list)}}, ensure_ascii=False, indent=2))
        return 0

    stats = {"groups_created": 0, "groups_skipped": 0, "nodes_created": 0, "nodes_skipped": 0,
             "prompts_applied": 0, "links_applied": 0, "binds_applied": 0}
    existing_groups = _names([str(LIBTV), "group", "list", "-p", args.project_uuid])
    if existing_groups is None:
        raise RuntimeError("failed to read existing project groups; refusing to execute")
    planned_nodes = [command for command in (plan.get("commands") or []) if isinstance(command, dict) and command.get("kind") == "node_create"]
    verified_skip_names = _existing_nodes(args.project_uuid, planned_nodes)
    for command in phases["groups"]:
        if command[3] in existing_groups:
            stats["groups_skipped"] += 1
            continue
        _run(command, stats, "groups_created")
    for command, name in zip(phases["nodes"], phases["node_names"]):
        if name in verified_skip_names:
            stats["nodes_skipped"] += 1
            continue
        _run(command, stats, "nodes_created")
    for command in phases["prompts"]:
        _run(command, stats, "prompts_applied")
    for command in phases["links"]:
        _run(command, stats, "links_applied")
    for command in phases["binds"]:
        _run(command, stats, "binds_applied")
    stats["mode"] = "execute_no_run"
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
