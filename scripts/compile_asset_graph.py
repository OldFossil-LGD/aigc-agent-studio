"""Compile a production contract into an asset graph plan.

The plan is deliberately about roles and iteration, not about a fixed node
count. A reused or stateful entity receives an explicit refinement chain
unless the contract records an exemption.
"""

from __future__ import annotations

import copy
from typing import Any


def _requires_iteration(entity: dict[str, Any]) -> tuple[bool, str]:
    if entity.get("requires_iteration") is True:
        return True, "explicit_requires_iteration"
    if entity.get("requires_iteration") is False:
        return False, "explicit_exemption"
    if int(entity.get("reuse_count") or 1) > 1:
        return True, "cross_shot_reuse"
    if int(entity.get("state_versions") or 1) > 1:
        return True, "state_versions"
    if entity.get("precision_demand") or entity.get("contains_text"):
        return True, "precision_or_text"
    return False, "stable_leaf"


# Frozen supported entity declarations, distinct from derived output records.
HISTORY_FIELDS = {"id", "kind", "name", "description", "state", "version", "aspect_ratio",
                  "reference_purpose", "reuse_count", "state_versions", "requires_iteration",
                  "precision_demand", "contains_text"}


def _definition(raw, project_ratio):
    result=copy.deepcopy(raw);result.pop("history",None)
    result.setdefault("kind","other");result.setdefault("name",result["id"])
    result.setdefault("description",None);result.setdefault("state",None);result.setdefault("version",1)
    result.setdefault("aspect_ratio",project_ratio)
    result.setdefault("reference_purpose",["identity","scene" if result["kind"]=="scene" else "state"])
    result.setdefault("reuse_count",1);result.setdefault("state_versions",1)
    result.setdefault("requires_iteration",None);result.setdefault("precision_demand",False);result.setdefault("contains_text",False)
    return result


def expand_entity_versions(contract):
    """Resolve only explicit histories; ordinary entity IDs/semantics stay unchanged."""
    entities=copy.deepcopy(contract.get("entities") or [])
    if not any(isinstance(e,dict) and "history" in e for e in entities):return entities
    rows=[];base_ids=set();ratio=str(contract.get("aspect_ratio") or "16:9")
    for raw in entities:
        base=raw.get("id") if isinstance(raw,dict) else None
        if not isinstance(base,str) or not base.strip() or base in base_ids:
            raise ValueError("invalid or duplicate entity ID in versioned contract")
        base_ids.add(base)
        if "history" not in raw:
            rows.append(raw);continue
        history=raw["history"];version=raw.get("version",1)
        if not isinstance(history,list) or type(version) is not int or version<1:
            raise ValueError("asset history needs a list and positive current version")
        if type(raw.get("state_versions",1)) is not int or raw.get("state_versions",1)<len(history)+1:
            raise ValueError("state_versions must cover all explicit definitions")
        known=set()
        for old in history:
            if not isinstance(old,dict) or not HISTORY_FIELDS.issubset(old) or "history" in old:
                raise ValueError("history must contain a complete frozen entity definition")
            old_version=old["version"]
            if old["id"]!=base or type(old_version) is not int or old_version<1 or old_version>=version or old_version in known:
                raise ValueError("historical versions must be unique, older and from the same entity")
            if old.get("requires_iteration") not in (None,True,False):
                raise ValueError("invalid frozen iteration declaration")
            known.add(old_version)
        for definition,is_current in [(copy.deepcopy(h),False) for h in sorted(history,key=lambda h:h["version"])]+[(_definition(raw,ratio),True)]:
            row=copy.deepcopy(raw if is_current else definition);row.pop("history",None)
            row.setdefault("name",definition["name"])
            row.update(id=base+"__v"+str(definition["version"]),base_entity_id=base,
                       definition=definition,is_current=is_current)
            rows.append(row)
    ids=[r["id"] for r in rows]
    if len(set(ids))!=len(ids):raise ValueError("expanded asset version namespace collision")
    by_ref={(r.get("base_entity_id",r["id"]),r.get("version",1)):r for r in rows}
    referenced=set()
    for shot in contract.get("shots") or []:
        refs=shot.get("asset_refs")
        if not isinstance(refs,list):raise ValueError("versioned assets require explicit per-shot asset_refs")
        seen=set()
        for ref in refs:
            if not isinstance(ref,dict) or type(ref.get("version")) is not int:
                raise ValueError("asset reference needs an explicit version")
            key=(ref.get("entity_id"),ref["version"])
            if key not in by_ref or ref.get("entity_id") in seen:
                raise ValueError("unknown or duplicate asset version reference")
            seen.add(ref["entity_id"]);referenced.add(key)
    for row in rows:
        if "base_entity_id" in row:row["active"]=(row["base_entity_id"],row.get("version",1)) in referenced
    return rows


def compile_asset_graph(contract: dict[str, Any]) -> dict[str, Any]:
    """Return assets, iteration chains and explicit exemptions."""

    def _valid_ratio(value: Any) -> bool:
        if not isinstance(value, str) or not value:
            return False
        parts = value.split(":")
        if len(parts) != 2:
            return False
        left, right = parts
        if not left or not right:
            return False
        if any(ch not in "0123456789" for ch in left + right):
            return False
        try:
            width = int(left)
            height = int(right)
        except ValueError:
            return False
        return width > 0 and height > 0

    assets: list[dict[str, Any]] = []
    iteration_chains: list[dict[str, Any]] = []
    exemptions: list[dict[str, Any]] = []

    shots = contract.get("shots") or []
    explicit_scope = bool(shots) and all(isinstance(s.get("asset_refs"), list) for s in shots)
    selected = {(ref.get("entity_id"), ref.get("version")) for shot in shots
                for ref in (shot.get("asset_refs") or []) if isinstance(ref, dict)} if explicit_scope else set()
    project_ratio = contract.get("aspect_ratio") if isinstance(contract, dict) else None
    if not project_ratio:
        project_ratio = "16:9"
    project_ratio = str(project_ratio)

    for index, raw in enumerate(expand_entity_versions(contract), start=1):
        entity = copy.deepcopy(raw)
        entity_id = str(entity.get("id") or f"entity_{index:02d}")
        kind = str(entity.get("kind") or "other")
        state_versions = max(1, int(entity.get("state_versions") or 1))
        version = entity.get("version", 1)
        if type(version) is not int or version < 1:
            raise ValueError("asset version must be a positive integer: %s" % entity_id)
        requires_iteration, reason = _requires_iteration(entity)
        if isinstance(entity, dict) and "aspect_ratio" in entity:
            if not _valid_ratio(entity.get("aspect_ratio")):
                raise ValueError("invalid entity aspect_ratio: %r" % (entity.get("aspect_ratio"),))
            resolved_ratio = str(entity.get("aspect_ratio"))
            ratio_source = "entity"
        else:
            resolved_ratio = project_ratio
            ratio_source = "project_default"
        asset = {
            "id": entity_id,
            "kind": kind,
            "name": entity.get("name") or entity_id,
            "description": entity.get("description"),
            "state": entity.get("state"),
            "version": version,
            "anchor_role": f"{kind}_anchor",
            "requires_iteration": requires_iteration,
            "iteration_reason": reason,
            "state_versions": state_versions,
            "reference_purpose": entity.get("reference_purpose") or ["identity", "scene" if kind == "scene" else "state"],
            "aspect_ratio": resolved_ratio,
            "aspect_ratio_source": ratio_source,
        }
        if "base_entity_id" in entity:
            asset.update({k:copy.deepcopy(entity[k]) for k in ("base_entity_id","definition","is_current","active")})
        if explicit_scope and "active" not in asset:
            asset["active"] = (entity_id, version) in selected
        assets.append(asset)
        if requires_iteration:
            chain = {
                "entity_id": entity_id,
                "reason": reason,
                "nodes": [
                    {"id": f"{entity_id}__anchor", "role": "asset_anchor", "mode_type": "text2image"},
                    {"id": f"{entity_id}__refine_a", "role": "asset_refine", "mode_type": "image2image"},
                    {"id": f"{entity_id}__refine_b", "role": "asset_refine", "mode_type": "image2image"},
                ],
                "edges": [
                    {"source": f"{entity_id}__anchor", "target": f"{entity_id}__refine_a", "purpose": "refine"},
                    {"source": f"{entity_id}__refine_a", "target": f"{entity_id}__refine_b", "purpose": "refine"},
                ],
            }
            iteration_chains.append(chain)
        else:
            exemptions.append({"entity_id": entity_id, "reason": reason, "declared_by": "compiler"})

    return {
        "assets": assets,
        "iteration_chains": iteration_chains,
        "exemptions": exemptions,
        "policy": {
            "node_count_is_not_target": True,
            "iteration_is_required_for_reuse_or_state": True,
        },
    }


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.contract, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    contract = payload.get("production_contract", payload)
    result = compile_asset_graph(contract)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
