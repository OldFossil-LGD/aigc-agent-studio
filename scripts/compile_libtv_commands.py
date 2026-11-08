"""Compile a production graph into non-executing LibTV CLI commands."""

from __future__ import annotations

import copy
import hashlib
import re

from typing import Any


PROJECT_TOKEN = "<PROJECT_UUID>"

# ★ 2026-10-31（P1 / I-05）：只有带数据语义的边才允许落成平台引用连线。
#   旧图只有 purpose，这里做一次显式映射；映射不到的按 control_dependency 处理——
#   **绝不允许"有边就连"**。
try:
    from scripts.workflow_graph_ir import PURPOSE_TO_KIND
except ImportError:
    from workflow_graph_ir import PURPOSE_TO_KIND
LINKABLE_KINDS = {"data_reference"}


def _edge_kind(edge: dict) -> str:
    if edge.get("kind"):
        return str(edge["kind"])
    return PURPOSE_TO_KIND.get(str(edge.get("purpose")), "control_dependency")


def _platform_base(logical_id: str) -> str:
    """逻辑 ID → 可读平台名（不是最终名）：`shot__a` → `shot_a`，其余不合法字符压成 `_`。"""
    base = logical_id.replace("__", "_")
    base = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fa5]", "_", base).strip("_")
    return base or "node"


def build_binding_map(
    graph: dict[str, Any], preferred_names: dict[str, str] | None = None,
) -> dict[str, str]:
    """建立 `logical_id -> platform_name` 的**单射**映射（P0-02）。

    规则（确定性，同一输入多次编译结果相同）：
      1. 每个逻辑 ID 先取可读基名；
      2. 基名相同的 ID 视为碰撞，全部加 `_<sha1(逻辑ID)[:6]>` 后缀（不做“先来后到”的隐式胜负）；
      3. 后缀后仍碰撞则加长哈希，直到整图唯一；
      4. 逻辑 ID 本身永远保留在 `binding_map` 的键里，不因改名丢失。
    """
    ids = sorted({str(n.get("id")) for n in (graph.get("nodes") or []) if n.get("id")})
    bases = {nid: preferred_names[nid] if preferred_names is not None else _platform_base(nid)
             for nid in ids}
    groups: dict[str, list[str]] = {}
    for nid in ids:
        groups.setdefault(bases[nid], []).append(nid)
    binding: dict[str, str] = {}
    for base, members in groups.items():
        if len(members) == 1:
            binding[members[0]] = base
            continue
        for nid in members:
            digest = hashlib.sha1(nid.encode("utf-8")).hexdigest()
            binding[nid] = "%s_%s" % (base, digest[:6])
    used: dict[str, str] = {}
    for nid in ids:  # 极端情况：加后缀后仍撞（理论上不会）→ 加长哈希
        name = binding[nid]
        digest = hashlib.sha1(nid.encode("utf-8")).hexdigest()
        extra = 8
        while name in used and used[name] != nid:
            name = "%s_%s" % (bases[nid], digest[:extra])
            extra += 2
        used[name] = nid
        binding[nid] = name
    return binding


def _sanitize_refs(text: str, binding: dict[str, str] | None = None) -> str:
    """把 `{{Node "<graph id>"}}` 改成**建图时真正会创建的节点名**。

    必须与 `node_create` 共用同一张 `binding_map`：否则引用对象与建图对象会分叉
    （实测过：提示词里引用的名字平台不存在）。没有映射时退回可读基名，保证旧调用不崩。
    """
    def repl(match):
        logical = match.group(1)
        if binding and logical in binding:
            return '{{Node "%s"}}' % binding[logical]
        return '{{Node "%s"}}' % _platform_base(logical)

    return re.sub(r'\{\{Node "([^"]+)"\}\}', repl, text)


def _node_type(node: dict[str, Any]) -> str:
    node_type = node.get("node_type") or "text"
    if node_type not in {"text", "image", "video", "audio", "video-clip"}:
        raise ValueError(f"unsupported node type: {node_type}")
    return node_type


def compile_commands(
    graph: dict[str, Any],
    prompts: list[dict[str, Any]] | None = None,
    project_token: str = PROJECT_TOKEN,
) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    prompt_by_node = {p.get("node_id"): p for p in (prompts or [])}
    group_positions = {group["id"]: {"x": index * 2400, "y": 0} for index, group in enumerate(graph.get("groups") or [])}
    group_names = {group["id"]: group["name"] for group in graph.get("groups") or []}
    node_to_group: dict[str, str] = {}
    for group in graph.get("groups") or []:
        commands.append({"kind": "group_create", "name": group["name"], "project": project_token, "run": False})
        for node_id in group.get("node_ids") or []:
            node_to_group[node_id] = group["id"]

    per_group_index: dict[str, int] = {}
    node_names: dict[str, str] = build_binding_map(graph)
    for node in graph.get("nodes") or []:
        node_id = node["id"]
        group_id = node_to_group.get(node_id) or (graph.get("groups") or [{}])[-1].get("id", "root")
        index = per_group_index.get(group_id, 0)
        per_group_index[group_id] = index + 1
        base = group_positions.get(group_id, {"x": 0, "y": 0})
        x = base["x"] + 40 + (index % 5) * 340
        y = base["y"] + 40 + (index // 5) * 260
        name = node_names[node_id]  # 来自 binding_map（单射），不在这里替换字符串
        package = prompt_by_node.get(node_id) or {}
        blocks = package.get("blocks") or {}
        prompt_text = "\n".join(f"{key}: {value}" for key, value in blocks.items())
        prompt_text = _sanitize_refs(prompt_text, node_names)
        content = [prompt_text] if node.get("node_type") == "text" and prompt_text else None
        commands.append(
            {
                "kind": "node_create",
                "name": name,
                "logical_node_id": node_id,
                "node_type": _node_type(node),
                "role": node.get("role"),
                "shot_id": node.get("shot_id"),
                "x": x,
                "y": y,
                "group_id": group_id,
                "group_name": group_names.get(group_id),
                "project": project_token,
                "model": node.get("model"),
                "mode_type": node.get("mode_type"),
                "settings": node.get("settings") or {},
                "shot_timing": copy.deepcopy(node.get("shot_timing")),
                "prompt": prompt_text,
                "content": content,
                "prompt_status": package.get("status"),
                "run": False,
                "ignition_allowed": False,
            }
        )

    skipped_links: list[dict[str, Any]] = []
    for edge in graph.get("edges") or []:
        kind = _edge_kind(edge)
        source = node_names.get(edge["source"], edge["source"])
        target = node_names.get(edge["target"], edge["target"])
        if kind not in LINKABLE_KINDS:
            # 逻辑依赖/血缘/合成/条件：不落物理连线（I-05），但要留痕，供审计与后续批准
            skipped_links.append({"source": source, "target": target, "kind": kind,
                                  "reason": "NOT_A_DATA_REFERENCE"})
            continue
        commands.append(
            {
                "kind": "node_link",
                "target": target,
                "left": source,
                "purpose": edge.get("purpose"),
                "edge_kind": kind,
                "project": project_token,
                "run": False,
            }
        )

    return {
        "project_token": project_token,
        "group_names": group_names,
        "binding_map": node_names,
        "skipped_links": skipped_links,
        "commands": commands,
        "safety": {
            "run": False,
            "ignition_allowed": False,
            "execute_only_after_user_approval": True,
        },
    }


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("graph")
    parser.add_argument("--prompts")
    parser.add_argument("--contract")
    parser.add_argument("--project-token", default=PROJECT_TOKEN)
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.graph, "r", encoding="utf-8") as handle:
        graph = json.load(handle)
    prompts = []
    if args.prompts:
        with open(args.prompts, "r", encoding="utf-8") as handle:
            prompts = [json.loads(line) for line in handle if line.strip()]
    result = compile_commands(graph, prompts, args.project_token)
    if args.contract:
        contract_payload = json.loads(open(args.contract, "r", encoding="utf-8").read())
        contract = contract_payload.get("production_contract", contract_payload)
        result["mode"] = contract.get("mode") or contract.get("production_mode")
        result["source_access"] = contract.get("source_access")
        result["source_project_uuid"] = contract.get("source_project_uuid")
        result["copy_project_uuid"] = contract.get("copy_project_uuid")
        result["evidence_default"] = contract.get("evidence_default")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
