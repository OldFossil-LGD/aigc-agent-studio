"""Compile production roles for every shot.

The graph contains roles and dependencies, not media results. A later
platform adapter is responsible for mapping nodes/edges into LibTV calls.
"""

from __future__ import annotations

import copy
import hashlib
import json

from typing import Any

try:
    from scripts.production_timing import resolve_shot_timing
except ImportError:
    from production_timing import resolve_shot_timing


STANDARD_SHOT_ROLES = [
    "storyboard",
    "prompt",
    "scene_ref",
    "identity_ref",
    "composition_ref",
    "state_ref",
    "candidate_image",
    "refined_image",
    "video_candidate",
    "selection",
    "audio",
    "assembly",
]

# Shot-kind vocabularies. Shared with compile_prompt_packages so the prompt
# blocks and the graph roles cannot drift apart on what counts as an empty or
# a silent shot.
EMPTY_SHOT_KINDS = {"empty", "empty_shot", "no_character", "visual_only"}
SILENT_SHOT_KINDS = {"silent", "no_audio", "mute"}


def resolve_shot_roles(raw: dict[str, Any]) -> list[str]:
    if not isinstance(raw, dict):
        raise ValueError("shot must be an object")
    kind = str(raw.get("shot_kind") or raw.get("kind") or "standard").lower()
    silent = kind in SILENT_SHOT_KINDS
    explicit = raw.get("roles")
    if not explicit:
        explicit = raw.get("required_roles")
    if explicit:
        if not isinstance(explicit, (list, tuple, set)):
            raise ValueError("shot roles must be a list of strings")
        if any(not isinstance(role, str) for role in explicit):
            raise ValueError("shot roles must contain only strings")
        explicit_set = set(explicit)
        if silent:
            explicit_set.discard("audio")
        return [role for role in STANDARD_SHOT_ROLES if role in explicit_set]
    if kind in EMPTY_SHOT_KINDS:
        return [r for r in STANDARD_SHOT_ROLES if r not in {"identity_ref", "state_ref", "audio"}]
    if silent:
        return [r for r in STANDARD_SHOT_ROLES if r != "audio"]
    return list(STANDARD_SHOT_ROLES)


def _candidate_count(shot: dict[str, Any]) -> int:
    risk = str(shot.get("risk") or "medium").lower()
    if risk in {"high", "critical"}:
        return 2
    if risk == "low":
        return 1
    return 1


def _sound_intent_for_node(contract: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any] | None:
    """Effective structured sound intent for a shot (shot overrides project)."""

    if isinstance(raw, dict) and isinstance(raw.get("sound"), dict):
        return raw["sound"]
    sound = contract.get("sound") if isinstance(contract, dict) else None
    return sound if isinstance(sound, dict) else None


def _platform_sound_enabled(sound_intent: dict[str, Any] | None) -> bool | None:
    """Whether the platform must generate sound for this shot.

    `None` means "no structured intent" - the compiler keeps its historical
    default (`enableSound: off`) and the library rule stays in charge.
    """

    if not isinstance(sound_intent, dict):
        return None
    mode = sound_intent.get("mode")
    if mode == "silent":
        return False
    if mode in ("ambience_only", "dialogue_allowed"):
        return True
    return None


def _defaults(node_type: str, role: str, ratio: str = "16:9", duration: Any = None) -> dict[str, Any]:
    if node_type == "text":
        return {"model": "GVLM 3.1", "settings": {}}
    if node_type == "image":
        return {"model": "General image Pro", "settings": {"quality": "2K", "ratio": ratio}}
    if node_type == "video":
        model = "Kling O3" if role == "video_candidate" else "Kling 3.0"
        settings: dict[str, Any] = {"ratio": ratio, "quality": "low", "enableSound": "off"}
        if duration not in (None, ""):
            settings["duration"] = duration
        return {"model": model, "settings": settings}
    if node_type == "audio":
        return {"model": "Seed Audio 1.0", "settings": {"language": "zh", "format": "wav"}}
    if node_type == "video-clip":
        return {"model": None, "settings": {"ratio": ratio} if ratio else {}}
    return {"model": None, "settings": {}}


def _node(node_id: str, role: str, shot_id: str, node_type: str, ratio: str = "16:9", duration: Any = None, **extra: Any) -> dict[str, Any]:
    value = {"id": node_id, "role": role, "shot_id": shot_id, "node_type": node_type, "version": 1}
    value.update(_defaults(node_type, role, ratio, duration))
    value.update(extra)
    return value


WORLD_STATE_KINDS = {"identity", "physical", "prop", "world", "dialogue", "frame", "approval"}
WORLD_STATE_VISUAL_BLOCKS = {
    "video_candidate": "continuity", "candidate_image": "composition",
    "refined_image": "continuity", "state_ref": "continuity",
    "storyboard": "shot_contract", "prompt": "compiled_constraints", "assembly": "timeline",
}


def _state_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _world_entry(value, key):
    if not isinstance(value, dict) or value.get("kind") not in WORLD_STATE_KINDS:
        raise ValueError("unknown world-state kind: %s" % key)
    expected = value["kind"] != "approval"
    if value.get("observable") is not expected:
        raise ValueError("world state needs explicit observability declaration: %s" % key)
    if "value" not in value or value["value"] is None or (
            isinstance(value["value"], str) and not value["value"].strip()):
        raise ValueError("world-state value is missing: %s" % key)
    _state_digest(value)  # Reject non-JSON/non-finite data rather than invent a value.
    return copy.deepcopy(value)


def resolve_world_states(contract):
    """Resolve declared state only; observability/media truth remain unverified."""
    shots = contract.get("shots") or []
    if "world_state_initial" not in contract and not any(
            "world_state_delta" in shot or "world_state_refs" in shot for shot in shots):
        return {}
    initial = contract.get("world_state_initial", {})
    if not isinstance(initial, dict):
        raise ValueError("world_state_initial must be an object")
    state, sources, result = {}, {}, {}
    for key, value in initial.items():
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            raise ValueError("world-state keys must be non-empty canonical strings")
        state[key] = _world_entry(value, key)
        sources[key] = {"record_id": "world_initial", "version": contract.get("version", 1),
                        "sha256": _state_digest({key: value})}
    for index, raw in enumerate(shots, 1):
        sid = str(raw.get("id") or "shot_%02d" % index)
        if sid in result:
            raise ValueError("duplicate world-state shot: " + sid)
        delta, refs = raw.get("world_state_delta"), raw.get("world_state_refs")
        if not isinstance(delta, dict) or not set(state).issubset(delta):
            raise ValueError("world_state_delta must explicitly cover all known keys: " + sid)
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError("world_state_refs must be an explicit unique list: " + sid)
        start, source_start = copy.deepcopy(state), copy.deepcopy(sources)
        version = raw.get("version", 1)
        if type(version) is not int or version < 1:
            raise ValueError("world-state shot version must be a positive integer")
        for key, value in delta.items():
            if not isinstance(key, str) or not key.strip() or key != key.strip():
                raise ValueError("world-state keys must be non-empty canonical strings")
            if value == "unchanged":
                if key not in state:
                    raise ValueError("unchanged has no previous world state: " + key)
                continue
            state[key] = _world_entry(value, key)
            sources[key] = {"record_id": sid, "version": version,
                            "sha256": _state_digest({"shot": sid, "version": version, "key": key, "entry": value})}
        if not set(refs).issubset(state):
            raise ValueError("unknown world-state reference: " + sid)
        if str(raw.get("shot_kind") or raw.get("kind") or "standard").lower() in EMPTY_SHOT_KINDS and any(
                state[key]["kind"] == "identity" for key in refs):
            raise ValueError("empty shot cannot consume observable identity state: " + sid)
        result[sid] = {"world_state_start": start, "world_state_delta": copy.deepcopy(delta),
                       "world_state_end": copy.deepcopy(state), "world_state_refs": list(refs),
                       "world_state_sources_start": source_start,
                       "world_state_sources_end": copy.deepcopy(sources)}
    return result


def world_state_blocks(shot, role):
    """Only role-applicable declared facts enter creative text; metadata stays out."""
    if not isinstance(shot, dict) or "world_state_refs" not in shot:
        return {}, {}
    blocks, used_sources = {}, {}
    phases = [("start", "开场")]
    if role in ("video_candidate", "prompt", "assembly", "audio"):
        phases.append(("end", "结束"))
    for phase, label in phases:
        visual, sound = [], []
        for key in shot["world_state_refs"]:
            item = (shot.get("world_state_" + phase) or {}).get(key)
            if not item or item["kind"] == "approval":
                continue
            is_sound = item["kind"] == "dialogue"
            if (is_sound and role not in ("video_candidate", "prompt", "assembly", "audio")) or (
                    not is_sound and role not in WORLD_STATE_VISUAL_BLOCKS):
                continue
            value = item["value"]
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
            (sound if is_sound else visual).append(key + "：" + rendered)
            used_sources[phase + ":" + key] = shot["world_state_sources_" + phase][key]
        if visual:
            block = WORLD_STATE_VISUAL_BLOCKS[role]
            blocks[block] = (blocks.get(block, "") + "\n" + label + "可观察状态：" + "；".join(visual) + "。").strip()
        if sound:
            block = "sound_layers" if role == "audio" else "sound"
            blocks[block] = (blocks.get(block, "") + "\n" + label + "声音/对白状态：" + "；".join(sound) + "。").strip()
    return blocks, used_sources


def compile_shot_graph(contract: dict[str, Any], assets: dict[str, Any]) -> dict[str, Any]:
    """Build role-complete nodes, edges and groups for every shot."""

    shots = contract.get("shots") or []
    world_states = resolve_world_states(contract)
    graph_version = contract.get("version", 1)
    if type(graph_version) is not int or graph_version < 1:
        raise ValueError("graph version must be a positive integer")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    shot_plans: list[dict[str, Any]] = []

    ratio = str(contract.get("aspect_ratio") or "16:9")

    active_assets = [a for a in assets.get("assets") or [] if a.get("active", True)]
    asset_sources: list[dict[str, Any]] = []
    for asset in active_assets:
        asset_id = asset["id"]
        asset_ratio = asset.get("aspect_ratio") if isinstance(asset, dict) else None
        if not isinstance(asset_ratio, str) or not asset_ratio:
            asset_ratio = ratio
        nodes.append(
            _node(
                f"{asset_id}__asset_anchor",
                "asset_anchor",
                None,
                "image",
                ratio=asset_ratio,
                mode_type="text2image",
                entity_id=asset_id,
            )
        )
        if asset.get("requires_iteration"):
            nodes.append(
                _node(
                    f"{asset_id}__asset_refine_a",
                    "asset_refine",
                    None,
                    "image",
                    ratio=asset_ratio,
                    mode_type="image2image",
                    entity_id=asset_id,
                )
            )
            nodes.append(
                _node(
                    f"{asset_id}__asset_refine_b",
                    "asset_refine",
                    None,
                    "image",
                    ratio=asset_ratio,
                    mode_type="image2image",
                    entity_id=asset_id,
                )
            )
            edges.extend(
                [
                    {
                        "source": f"{asset_id}__asset_anchor",
                        "target": f"{asset_id}__asset_refine_a",
                        "purpose": "asset_refine",
                    },
                    {
                        "source": f"{asset_id}__asset_refine_a",
                        "target": f"{asset_id}__asset_refine_b",
                        "purpose": "asset_refine",
                    },
                ]
            )
        asset_sources.append(
            {
                "id": asset.get("base_entity_id", asset_id),
                "kind": asset.get("kind", "other"),
                "version": asset.get("version", 1),
                "source": (
                    f"{asset_id}__asset_refine_b"
                    if asset.get("requires_iteration")
                    else f"{asset_id}__asset_anchor"
                ),
            }
        )

    assets_by_id = {asset["id"]: asset for asset in assets.get("assets") or []}
    sources_by_id = {(source["id"], source["version"]): source for source in asset_sources}
    for node in nodes:
        asset = assets_by_id[node["entity_id"]]
        node["version"] = asset.get("version", 1)
        if node["role"] == "asset_anchor":
            if "definition" in asset:
                node["asset_definition_sha256"] = _state_digest(asset["definition"])
            node["asset_state"] = asset.get("state")
            node["asset_description"] = asset.get("description")

    MODE_TYPE_BY_ROLE = {
        "scene_ref": "text2image",
        "identity_ref": "text2image",
        "composition_ref": "text2image",
        "state_ref": "text2image",
        "candidate_image": "image2image",
        "refined_image": "image2image",
        "video_candidate": "mixed2video",
        "assembly": "videoEdit2video",
        "audio": "text2audio",
    }

    for index, raw in enumerate(shots, start=1):
        shot_id = str(raw.get("id") or f"shot_{index:02d}")
        shot_version = raw.get("version", 1)
        if type(shot_version) is not int or shot_version < 1:
            raise ValueError("shot version must be a positive integer: %s" % shot_id)
        shot_asset_sources = asset_sources
        explicit_refs = "asset_refs" in raw
        if explicit_refs:
            refs = raw["asset_refs"]
            if not isinstance(refs, list):
                raise ValueError("asset_refs must be a list: %s" % shot_id)
            shot_asset_sources = []
            selected = set()
            for ref in refs:
                if not isinstance(ref, dict) or not isinstance(ref.get("entity_id"), str):
                    raise ValueError("asset reference must identify an entity: %s" % shot_id)
                entity_id = ref["entity_id"]
                source = sources_by_id.get((entity_id, ref.get("version")))
                if source is None or entity_id in selected:
                    raise ValueError("unknown or duplicate asset reference: %s" % entity_id)
                if type(ref.get("version")) is not int or ref["version"] != source["version"]:
                    raise ValueError("asset reference version mismatch: %s" % entity_id)
                selected.add(entity_id)
                shot_asset_sources.append(source)
        risk = str(raw.get("risk") or "medium")
        shot_duration = raw.get("duration_sec")
        if shot_duration in (None, ""):
            shot_duration = None
        shot_timing = resolve_shot_timing(raw if isinstance(raw, dict) else {})
        candidate_count = _candidate_count(raw)
        graph_shot_id = f"{shot_id}"
        role_nodes: list[dict[str, Any]] = []
        shot_kind = str(raw.get("shot_kind") or raw.get("kind") or "standard").lower()

        shot_description = raw.get("description") or raw.get("visual") or contract.get("goal", "")
        roles = resolve_shot_roles(raw)
        creative = {key: copy.deepcopy(raw[key]) for key in (
            "camera", "composition", "lighting", "purpose", "camera_movement",
            "sound", "story_time", "environment_id", "props", "entities") if key in raw}

        if "storyboard" in roles:
            role_nodes.append(
                _node(
                    f"{shot_id}__storyboard",
                    "storyboard",
                    graph_shot_id,
                    "text",
                    ratio=ratio,
                    duration=shot_duration,
                    shot_description=shot_description,
                )
            )
        if "prompt" in roles:
            role_nodes.append(_node(f"{shot_id}__prompt", "prompt", graph_shot_id, "text", ratio=ratio, duration=shot_duration))
        for role in ("scene_ref", "identity_ref", "composition_ref", "state_ref"):
            if role in roles:
                role_nodes.append(
                    _node(
                        f"{shot_id}__{role}",
                        role,
                        graph_shot_id,
                        "image",
                        ratio=ratio,
                        duration=shot_duration,
                        mode_type=MODE_TYPE_BY_ROLE[role],
                    )
                )

        for candidate_index in range(1, candidate_count + 1):
            suffix = chr(64 + candidate_index)
            if "candidate_image" in roles:
                role_nodes.append(
                    _node(
                        f"{shot_id}__candidate_image_{suffix}",
                        "candidate_image",
                        graph_shot_id,
                        "image",
                        ratio=ratio,
                        duration=shot_duration,
                        mode_type="image2image",
                        candidate_index=candidate_index,
                        shot_description=shot_description,
                    )
                )
            if "refined_image" in roles:
                role_nodes.append(
                    _node(
                        f"{shot_id}__refined_image_{suffix}",
                        "refined_image",
                        graph_shot_id,
                        "image",
                        ratio=ratio,
                        duration=shot_duration,
                        mode_type="image2image",
                        candidate_index=candidate_index,
                    )
                )
            if "video_candidate" in roles:
                role_nodes.append(
                    _node(
                        f"{shot_id}__video_candidate_{suffix}",
                        "video_candidate",
                        graph_shot_id,
                        "video",
                        ratio=ratio,
                        duration=shot_duration,
                        mode_type="mixed2video",
                        candidate_index=candidate_index,
                        shot_description=shot_description,
                    )
                )

        if "selection" in roles:
            role_nodes.append(_node(f"{shot_id}__selection", "selection", graph_shot_id, "text", ratio=ratio, duration=shot_duration))
        if "audio" in roles:
            role_nodes.append(_node(f"{shot_id}__audio", "audio", graph_shot_id, "audio", ratio=ratio, duration=shot_duration, mode_type="text2audio"))
        if "assembly" in roles:
            role_nodes.append(
                _node(
                    f"{shot_id}__assembly",
                    "assembly",
                    graph_shot_id,
                    "video",
                    ratio=ratio,
                    duration=shot_duration,
                    mode_type="videoEdit2video",
                    model="Kling O3",
                )
            )
        for role_node in role_nodes:
            role_node.update(copy.deepcopy(creative))
            state_blocks, state_sources = world_state_blocks(world_states.get(shot_id), role_node["role"])
            if state_blocks:
                role_node["world_state_instruction_sha256"] = _state_digest(state_blocks)
                role_node["world_state_sources_sha256"] = _state_digest(state_sources)
            role_node["version"] = shot_version
            role_node["shot_kind"] = shot_kind
            if isinstance(raw, dict) and isinstance(raw.get("sound"), dict):
                role_node["sound"] = copy.deepcopy(raw["sound"])
            if role_node.get("role") == "video_candidate":
                role_node["shot_timing"] = copy.deepcopy(shot_timing)
                if isinstance(shot_timing, dict):
                    generation_duration = shot_timing.get("generation_duration_sec")
                    if generation_duration is not None:
                        role_node.setdefault("settings", {})["duration"] = generation_duration
        nodes.extend(role_nodes)

        for candidate_index in range(1, candidate_count + 1):
            suffix = chr(64 + candidate_index)
            image_node = f"{shot_id}__candidate_image_{suffix}"
            refined_node = f"{shot_id}__refined_image_{suffix}"
            video_node = f"{shot_id}__video_candidate_{suffix}"
            if "candidate_image" in roles:
                for asset in shot_asset_sources:
                    edges.append(
                        {
                            "source": asset["source"],
                            "target": image_node,
                            "purpose": f"asset_{asset['kind']}",
                        }
                    )
                for source_role in ("scene_ref", "identity_ref", "composition_ref"):
                    if source_role in roles:
                        edges.append({"source": f"{shot_id}__{source_role}", "target": image_node, "purpose": source_role.replace("_ref", "")})
            if "candidate_image" in roles and "refined_image" in roles:
                edges.append({"source": image_node, "target": refined_node, "purpose": "refine"})
            if "state_ref" in roles and "refined_image" in roles:
                edges.append({"source": f"{shot_id}__state_ref", "target": refined_node, "purpose": "state"})
            if "prompt" in roles and "video_candidate" in roles:
                edges.append({"source": f"{shot_id}__prompt", "target": video_node, "purpose": "prompt"})
            if "refined_image" in roles and "video_candidate" in roles:
                edges.append({"source": refined_node, "target": video_node, "purpose": "image_reference"})
            if "video_candidate" in roles and "assembly" in roles:
                edges.append({"source": video_node, "target": f"{shot_id}__assembly", "purpose": "candidate_input"})

        if "storyboard" in roles and "prompt" in roles:
            edges.append({"source": f"{shot_id}__storyboard", "target": f"{shot_id}__prompt", "purpose": "compile"})
        if "selection" in roles and "assembly" in roles:
            edges.append({"source": f"{shot_id}__selection", "target": f"{shot_id}__assembly", "purpose": "selection"})
        if "selection" in roles:
            edges.append({"source": f"{shot_id}__selection", "target": "global__production_ledger", "purpose": "selection_record"})
        if "audio" in roles:
            edges.append({"source": f"{shot_id}__audio", "target": "global__final_composite", "purpose": "sound"})
        groups.append({"id": f"group__{shot_id}", "name": f"{shot_id}｜生产批次", "node_ids": [n["id"] for n in role_nodes]})
        shot_plans.append(
            {
                "id": shot_id,
                "version": shot_version,
                "asset_refs": copy.deepcopy(raw.get("asset_refs")),
                "asset_reference_scope": "explicit" if explicit_refs else "legacy_all_unconfirmed",
                "duration_sec": raw.get("duration_sec"),
                "shot_timing": copy.deepcopy(shot_timing),
                "risk": risk,
                "candidate_count": candidate_count,
                "description": shot_description,
                "shot_kind": str(raw.get("shot_kind") or raw.get("kind") or "standard").lower(),
                "roles": roles,
                "required_roles": roles,
            }
        )
        shot_plans[-1].update(copy.deepcopy(creative))
    for shot_plan in shot_plans:
        shot_plan.update(copy.deepcopy(world_states.get(shot_plan["id"], {})))
    nodes.extend(
        [
            _node("global__asset_manifest", "asset_manifest", None, "text", ratio=ratio),
            _node("global__production_ledger", "production_ledger", None, "text", ratio=ratio),
            _node("global__final_composite", "final_composite", None, "video-clip", ratio=ratio),
            _node("global__qa", "qa", None, "text", ratio=ratio),
        ]
    )
    asset_node_ids: list[str] = []
    for asset in active_assets:
        asset_id = asset["id"]
        asset_node_ids.append(f"{asset_id}__asset_anchor")
        if asset.get("requires_iteration"):
            asset_node_ids.extend([f"{asset_id}__asset_refine_a", f"{asset_id}__asset_refine_b"])
    for asset in active_assets:
        edges.append(
            {
                "source": "global__asset_manifest",
                "target": f"{asset['id']}__asset_anchor",
                "purpose": "asset_manifest",
            }
        )

    groups.extend(
        [
            {"id": "group__assets", "name": "资产图与迭代链", "node_ids": asset_node_ids},
            {"id": "group__global", "name": "全局契约与门禁", "node_ids": ["global__asset_manifest", "global__production_ledger", "global__final_composite", "global__qa"]},
        ]
    )
    for shot in shot_plans:
        edges.append({"source": f"{shot['id']}__assembly", "target": "global__final_composite", "purpose": "assemble"})
    edges.append({"source": "global__production_ledger", "target": "global__qa", "purpose": "qa"})

    result = {
        "shots": shot_plans,
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "policy": {
            "link_grammar": {
                "asset_chain": [
                    "global_asset_manifest -> asset_anchor -> asset_refine_a -> asset_refine_b -> shot_candidate_image"
                ],
                "shot_chain": [
                    "storyboard -> prompt -> video_candidate",
                    "scene_ref/identity_ref/composition_ref/state_ref -> candidate_image",
                    "candidate_image -> refined_image -> video_candidate",
                    "video_candidate -> assembly",
                    "selection -> assembly",
                    "selection -> production_ledger -> qa",
                    "audio -> final_composite",
                    "assembly -> final_composite",
                ],
                "terminal_nodes": ["final_composite", "qa"],
            },
            "required_shot_roles": [
                "storyboard",
                "prompt",
                "scene_ref",
                "identity_ref",
                "composition_ref",
                "candidate_image",
                "refined_image",
                "video_candidate",
                "selection",
                "audio",
                "assembly",
            ],
            "high_risk_candidate_min": 2,
        },
    }

    definitions = {a["id"]:copy.deepcopy(a["definition"]) for a in assets.get("assets") or [] if "definition" in a}
    if definitions:
        result["asset_definitions"] = definitions
    if world_states or "version" in contract:
        result.update(version=graph_version, source_revision=_state_digest(contract),
                      world_state_scope="declared_state_not_media_verification", generation_authorized=False)
    return result


def plan_rework(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return advice only; actual record application lives in the main compiler."""
    try:
        from scripts.production_records import rework_advice
    except ImportError:
        from production_records import rework_advice
    return rework_advice(previous, current)


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("assets")
    parser.add_argument("--out")
    parser.add_argument("--previous-graph", help="Emit rework advice against this previous shot graph")
    args = parser.parse_args()
    with open(args.contract, "r", encoding="utf-8") as handle:
        contract_payload = json.load(handle)
    with open(args.assets, "r", encoding="utf-8") as handle:
        assets = json.load(handle)
    contract = contract_payload.get("production_contract", contract_payload)
    result = compile_shot_graph(contract, assets)
    if args.previous_graph:
        with open(args.previous_graph, "r", encoding="utf-8") as handle:
            result = plan_rework(json.load(handle), result)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 1 if result.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
