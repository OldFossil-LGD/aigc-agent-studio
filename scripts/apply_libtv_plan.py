#!/usr/bin/env python3
"""Dry-run or apply a compiled LibTV command plan without ignition.

The default is dry-run. --execute only creates projects/groups/nodes/links;
it never appends --run and refuses any plan command with run=true.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
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


def _setting_value(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


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
        str(_coord(command.get("x"))),
        "--y",
        str(_coord(command.get("y"))),
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
        args.extend(["-s", f"{key}={_setting_value(value)}"])
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
            incoming[command["target"]].append(command["left"])

    for target, sources in incoming.items():
        command = [str(LIBTV), "node", target]
        for source in sources:
            command.extend(["--left", source])
        command.extend(["-p", project_uuid])
        links.append(command)

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
    proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError("command failed: %s\n%s" % (" ".join(command), proc.stderr.decode("utf-8", "replace")))
    stats[key] += 1


def _read_json(args):
    proc = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=60)
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


def _existing_nodes(project_uuid, commands, read_json=None):
    if read_json is None:
        read_json = _read_json
    inventory = read_json([str(LIBTV), "node", "list", "-p", project_uuid])
    rows = inventory.get("nodes")
    if not isinstance(rows, list):
        raise RuntimeError("invalid node inventory")
    by_name = {}
    by_id = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("invalid node inventory row")
        node_id = row.get("id")
        name = _node_name(row)
        if not isinstance(node_id, str) or not node_id.strip():
            raise RuntimeError("invalid node id")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError("invalid node name")
        if node_id in by_id or name in by_name:
            raise RuntimeError("ambiguous node inventory")
        by_id[node_id] = row
        by_name[name] = row

    # 单节点详情没有 position（实测：position 只出现在 libtv project 的回包里）。
    # 计划声明了坐标就必须补取，否则 _node_matches 会把它判成"参数不匹配"。
    positions = {}
    if any(isinstance(c, dict) and "position" in c for c in (commands or [])):
        try:
            meta = read_json([str(LIBTV), "project", project_uuid])
        except Exception:
            # 取不到就退回旧行为：缺坐标仍会被 _node_matches 判成不匹配，
            # 所以这里不是放宽校验，而是不把"读不到"升级成另一种失败。
            meta = None
        rows = meta.get("nodes") if isinstance(meta, dict) else None
        for row in rows or []:
            if (isinstance(row, dict) and isinstance(row.get("id"), str)
                    and isinstance(row.get("position"), dict)):
                positions[row["id"]] = row["position"]

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
        detail = read_json([str(LIBTV), "node", node_id, "-p", project_uuid])
        if isinstance(detail, dict) and "nodes" in detail:
            detail_nodes = detail.get("nodes")
            if not isinstance(detail_nodes, list) or len(detail_nodes) != 1 or not isinstance(detail_nodes[0], dict):
                raise RuntimeError("invalid node detail")
            node = detail_nodes[0]
        elif isinstance(detail, dict):
            node = detail
        else:
            raise RuntimeError("invalid node detail")
        if not isinstance(node, dict) or _detail_key(node) != node_id:
            raise RuntimeError("node id mismatch")
        # 详情投影同样可能把名字放在 data.name（MCP 形态），统一用 _node_name 取名。
        if _node_name(node) != name:
            raise RuntimeError('node name mismatch')
        if "position" in command and "position" not in node and node_id in positions:
            node = dict(node, position=positions[node_id])
        if not _node_matches(command, node):
            raise RuntimeError("node parameters mismatch")
        if "refs" in command:
            refs = command["refs"]
            if not isinstance(refs, list) or any(ref not in by_name for ref in refs):
                raise RuntimeError("unresolved planned references")
            expected_order = [by_name[ref]["id"] for ref in refs]
            params = _node_params(node)
            actual_order = params.get("imageListOrder") if isinstance(params, dict) else None
            if actual_order is None and not expected_order:
                actual_order = []
            if actual_order != expected_order:
                raise RuntimeError("node references mismatch")
        skip_names.add(name)
    return skip_names


def _node_params(node):
    if "nodes" in node:
        rows = node["nodes"]
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            return None
        node = rows[0]
    if "params" in node:
        return node["params"]
    data = node.get("data")
    return data.get("params") if isinstance(data, dict) else None


def _node_name(node):
    """展示名：CLI 投影在顶层，MCP 投影在 data.name（顶层为空串）。"""
    if "nodes" in node and isinstance(node.get("nodes"), list) and len(node["nodes"]) == 1:
        node = node["nodes"][0]
    if not isinstance(node, dict):
        return None
    for candidate in (node.get("name"),
                      node["data"].get("name") if isinstance(node.get("data"), dict) else None):
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _coord(value):
    """坐标：缺键与显式 null 同义，都按 0 处理。

    直接 str() 会把 None 渲染成字符串 "None" 发给 CLI（实测 --x None）。
    整数不做 float 转换（10**400 转 float 会抛 OverflowError，2**53+1 会丢精度）。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return 0


def _detail_key(detail):
    """详情里的节点标识。

    实测（2026-11-11，真实 CLI）：`node list` 给 `id`，`node <id>` 详情给
    `nodeKey` 且**没有 `id` 字段**，两者是同一个 UUID。只比 `id` 会让身份
    回读必定失败——重跑建库与审计已建好的画布都会踩到。
    """
    if not isinstance(detail, dict):
        return None
    return detail.get("nodeKey") or detail.get("id")


def _geometry(node):
    position = node.get("position")
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        position = dict(zip(("x", "y", "w", "h"), position))
    if not isinstance(position, dict):
        return None
    values = {"x": position.get("x"), "y": position.get("y")}
    for short, long_name in (("w", "width"), ("h", "height")):
        value = position.get(short, position.get(long_name, node.get(long_name)))
        if value is not None:
            values[short] = value
    if any(isinstance(value, bool) for value in values.values()):
        return None
    try:
        values = {key: float(value) for key, value in values.items()}
    except (TypeError, ValueError):
        return None
    return values if all(math.isfinite(value) for value in values.values()) else None


def _same_value(left, right):
    """按 JSON 语义判等（与后续比较用的口径一致）。

    不能用 Python 的 ==：True == 1 在 Python 里成立，而 JSON 里 true 与 1 是不同值。
    序列化失败一律判不等——宁可报不一致，也不要静默认为相同。
    """
    try:
        return (json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False)
                == json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False))
    except (TypeError, ValueError):
        return False


def _node_matches(command, node):
    if not isinstance(command, dict) or not isinstance(node, dict):
        return False
    node_type = command.get("node_type")
    # 列表投影给 type，单节点详情给 nodeType（实测同值），两处都要认。
    actual_type = node.get("type", node.get("nodeType")) if isinstance(node, dict) else None
    if node_type is None or type(actual_type) is not type(node_type) or actual_type != node_type:
        return False
    if "position" in command:
        expected_geometry, actual_geometry = _geometry(command), _geometry(node)
        if expected_geometry is None or actual_geometry is None:
            return False
        # 只比两边都有的键：真实 CLI 的 project 回包只给 x/y，没有宽高。
        # 宽高核不到就不装作核过——但 x/y 必须都在，缺一即判不匹配。
        shared = [key for key in expected_geometry if key in actual_geometry]
        if "x" not in shared or "y" not in shared:
            return False
        if any(actual_geometry.get(key) != expected_geometry[key] for key in shared):
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
    params_want = command.get("params")
    needs_params = bool(model) or bool(mode_type) or bool(prompt) or bool(settings) or bool(params_want)
    params = _node_params(node)
    if needs_params and not isinstance(params, dict):
        return False
    if not isinstance(params, dict):
        params = {}

    # 平台把同一批声明的 -s 拆到两处：modeType 在 params 顶层，enableSound 在
    # params.settings（实测 2026-11-12）。只查其中一处，重跑 apply 必然误判。
    # 合并视图包含顶层全部键（含 settings 本身），供 params 分支按原样比对嵌套结构。
    nested = params.get("settings") if isinstance(params.get("settings"), dict) else {}
    lookup = dict(nested)
    lookup.update(params)

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
        # 不再要求节点必须有 params.settings：单个 -s 键可能被平台放到 params 顶层。
        for key, value in settings.items():
            if key not in lookup:
                return False
            # 两处都有却互相矛盾时，无法判断平台以哪一处为准：判为不匹配（不猜）。
            if key in params and key in nested and not _same_value(params[key], nested[key]):
                return False
            actual = lookup[key]
            try:
                if json.dumps(actual, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
                    return False
            except (TypeError, ValueError):
                return False
    if params_want is not None:
        if not isinstance(params_want, dict):
            return False
        for key, value in params_want.items():
            if key not in lookup:
                return False
            if key in params and key in nested and not _same_value(params[key], nested[key]):
                return False
            try:
                if json.dumps(lookup[key], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) != json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False):
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
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("LibTV CLI unavailable or connection timed out: %s. "
              "See docs/LIBTV_SETUP.md for installation and login." % exc, file=sys.stderr)
        raise SystemExit(3)
    except (RuntimeError, ValueError) as exc:
        print("LibTV plan refused: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
