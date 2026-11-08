#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FilmDSL 交换视图：把本库 01–04 产物投影成 `filmdsl/v1`，再独立复核回来。

为什么要有它（`filmdsl-interchange.md`）：CineCrew（ECCV 2026）证明了一件事——
长片一致性的瓶颈不在生成模型，而在**剧本与视频模型之间缺一层可机判的结构**。
本库的权威产物（`01_production_contract` → `04_prompt_packages`）已经是那层结构，
但格式是本库私有的，别的 crew（CineCrew 的十个角色）读不懂。

于是本脚本只做一件事：**投影**。它不生产计划、不改权威产物、不生成媒体、不联网。

  ① export ：artifacts 目录 → `filmdsl/v1`（SceneBlueprint 形状：metadata / global_style /
              assets / memory / clips[4 层]），并附 `import_report`（哪些字段映射不到、
              每个字段的来源文件）。
  ② check  ：拿一份既有 `filmdsl/v1` 与**当前** artifacts 对账——重投影后逐键比对，
              丢字段 / 改口径 / 资产引用悬空 / 夹带生成许可 一律 FAIL。
  ③ 双向纪律：未识别的镜头字段**保留**在 `clip.studio`，不静默丢弃（治理 L2/L6）。

权威边界（不可越过）：
  - `filmdsl/v1` 是**派生视图**，不是新权威；本库 01–04 仍为唯一裁决源。
  - 交换视图永不携带生成权：`studio.generation_authorized` 恒为 false，
    任何 `run: true` / `ignition_allowed: true` 都判 `AUTHORITY_LEAK`。

退出码（与本库其它门禁一致）：
  0 通过 ｜ 1 有 FAIL ｜ 2 用法错误 ｜ 3 没有可投影的镜头（≠通过） ｜ 4 只有 WARN

用法：
  python scripts/filmdsl_bridge.py export --artifacts out/ --out out/09_filmdsl.json
  python scripts/filmdsl_bridge.py check --filmdsl out/09_filmdsl.json --artifacts out/ [--require-complete]
  python scripts/filmdsl_bridge.py --self-test
"""
from __future__ import print_function

import argparse
import glob
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = 0, 1, 2, 3, 4

FORMAT = "filmdsl/v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "agentic_backends")

ARTIFACT_FILES = {
    "contract": ("01_production_contract.json",),
    "assets": ("02_asset_graph_plan.json",),
    "shots": ("03_shot_graph_plan.json", "03_mirror_graph.json"),
    "prompts": ("04_prompt_packages.jsonl",),
}

# 镜头级别的已知字段。不在表里的键**不丢弃**，写进 clip.studio 并报 WARN。
KNOWN_SHOT_KEYS = {
    "id", "description", "duration_sec", "shot_timing", "risk", "candidate_count",
    "shot_kind", "roles", "required_roles", "entities", "camera", "lighting",
    "environment_id", "dialogue", "no_dialogue", "consistency_constraints",
    "resolved_t2i", "resolved_i2v", "transition_in", "transition_out",
    "asset_reference_scope", "asset_refs", "version",
}


# ───────────────────────────── 基础 I/O ─────────────────────────────

def _err(code, message, level="fail", **where):
    row = {"code": code, "level": level, "message": message}
    row.update({k: v for k, v in where.items() if v is not None})
    return row


def _load_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tmpdir(prefix="filmdsl_"):
    """本库纪律：tempfile 在某些沙箱里会失败，逐级回退并给出可读诊断。"""
    tried = []
    for attempt in (
        lambda: tempfile.mkdtemp(prefix=prefix),
        lambda: _mkdtemp_under(os.environ.get("TEMP"), prefix),
        lambda: _mkdtemp_under(os.environ.get("TMP"), prefix),
        lambda: _mkdtemp_under(os.environ.get("TMPDIR"), prefix),
        lambda: _mkdtemp_under(os.environ.get("CODEX_TMPDIR"), prefix),
        lambda: _mkdtemp_under(os.path.join(ROOT, ".orchestrator_tmp"), prefix),
        lambda: _mkdtemp_under(os.getcwd(), prefix),
    ):
        try:
            path = attempt()
            if path:
                return path
        except Exception as exc:  # noqa: BLE001 - 逐级回退，最后统一报错
            tried.append(repr(exc))
    raise RuntimeError("无法创建临时目录：%s" % "; ".join(tried or ["全部为空"]))


def _mkdtemp_under(base, prefix):
    if not base:
        return None
    if not os.path.isdir(base):
        os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=base)


# ───────────────────────────── 读权威产物 ─────────────────────────────

def load_artifacts(art_dir):
    """读 01–04。缺失不算异常——缺了就没有可投影的东西，由 validate 报码。"""
    art_dir = os.path.abspath(art_dir)
    if not os.path.isdir(art_dir):
        raise ValueError("artifacts 目录不存在：%s" % art_dir)
    out = {"dir": art_dir, "files": {}, "hashes": {}}
    for key, names in ARTIFACT_FILES.items():
        found = None
        for name in names:
            path = os.path.join(art_dir, name)
            if os.path.isfile(path):
                found = path
                break
        out[key] = None
        if found:
            out["files"][key] = os.path.basename(found)
            out["hashes"][key] = _sha256(found)
            if key == "prompts":
                out[key] = _load_jsonl(found)
            else:
                out[key] = _load_json(found)
    return out


def contract_of(art):
    """01 有两种历史形状：包一层 `production_contract`，或直接平铺。两种都认。"""
    doc = art.get("contract")
    if not isinstance(doc, dict):
        return {}
    inner = doc.get("production_contract")
    return inner if isinstance(inner, dict) else doc


def prompt_index(art):
    """把 04 按 (shot_id, role) 索引；asset 级记录（shot_id=None）单列。"""
    idx, assets = {}, {}
    for rec in art.get("prompts") or []:
        if not isinstance(rec, dict):
            continue
        shot_id = rec.get("shot_id")
        if not shot_id:
            assets[rec.get("node_id")] = rec
            continue
        idx.setdefault(shot_id, {})[rec.get("role")] = rec
    return idx, assets


def asset_index(art):
    """02 → {asset_id: {..., chain_node_ids}}；链上节点 id 反向索引用于解析镜头实体。"""
    plan = art.get("assets") or {}
    assets, chain_owner = {}, {}
    for item in plan.get("assets") or []:
        if isinstance(item, dict) and item.get("id"):
            assets[str(item["id"])] = dict(item)
    for chain in plan.get("iteration_chains") or []:
        if not isinstance(chain, dict):
            continue
        owner = chain.get("entity_id")
        for node in chain.get("nodes") or []:
            if isinstance(node, dict) and node.get("id") and owner:
                chain_owner[str(node["id"])] = str(owner)
        if owner in assets:
            assets[owner]["iteration_chain"] = [
                n.get("id") for n in chain.get("nodes") or [] if isinstance(n, dict)
            ]
    return assets, chain_owner


def _shot_duration(shot):
    dur = shot.get("duration_sec")
    if dur is None:
        timing = shot.get("shot_timing")
        if isinstance(timing, dict):
            dur = timing.get("duration_sec")
    try:
        return float(dur) if dur is not None else None
    except (TypeError, ValueError):
        return None


def _shot_nodes(shot, nodes_by_shot):
    return nodes_by_shot.get(shot.get("id"), [])


def _clip_entities(shot, nodes, chain_owner):
    """实体来源三档，按可信度取：显式 entities > 节点自带 asset_id > 迭代链反查。

    反查不到的**不编**——留给 validate 报 UNRESOLVED_ASSET 或 UNMAPPED_SHOT_FIELD。
    """
    rows, seen = [], set()

    def push(asset_id, source, **extra):
        aid = str(asset_id)
        if aid in seen:
            return
        seen.add(aid)
        row = {"asset_id": aid, "source": source}
        row.update({k: v for k, v in extra.items() if v is not None})
        rows.append(row)

    for item in shot.get("entities") or []:
        if isinstance(item, dict) and item.get("asset_id"):
            push(item["asset_id"], "shot.entities",
                 position=item.get("position"), action_state=item.get("action_state"))
        elif isinstance(item, str):
            push(item, "shot.entities")

    for node in nodes:
        if node.get("asset_id"):
            push(node["asset_id"], "node.asset_id", node_id=node.get("id"))
        elif node.get("id") in chain_owner:
            push(chain_owner[node["id"]], "iteration_chain", node_id=node.get("id"))
    return rows


def _dialogue_of(shot):
    raw = shot.get("dialogue")
    if isinstance(raw, dict):
        return {
            "has_dialogue": bool(raw.get("has_dialogue")),
            "speaker_asset_id": raw.get("speaker_asset_id"),
            "listener_asset_id": raw.get("listener_asset_id"),
            "text": raw.get("text"),
            "voice_preset": raw.get("voice_preset"),
        }
    text = shot.get("line")
    if text:
        return {"has_dialogue": True, "speaker_asset_id": shot.get("speaker_asset_id"),
                "listener_asset_id": None, "text": text, "voice_preset": None}
    return {"has_dialogue": False, "speaker_asset_id": None, "listener_asset_id": None,
            "text": None, "voice_preset": None}


def _block(rec, key):
    if not isinstance(rec, dict):
        return None
    blocks = rec.get("blocks")
    if isinstance(blocks, dict):
        val = blocks.get(key)
        if isinstance(val, list):
            return "\n".join(str(v) for v in val)
        return val
    return None


# ───────────────────────────── 投影 ─────────────────────────────

def export(art, blueprint_id=None):
    """artifacts → (filmdsl 文档, 违规表)。纯函数，不写盘。"""
    contract = contract_of(art)
    plan = art.get("assets") or {}
    shots_doc = art.get("shots") or {}
    assets, chain_owner = asset_index(art)
    prompts, _ = prompt_index(art)

    violations = []
    if not art.get("contract"):
        violations.append(_err("CONTRACT_MISSING", "缺 01_production_contract.json，无法确定风格与画幅", level="warn"))
    if not art.get("shots"):
        violations.append(_err("SHOTS_MISSING", "缺 03_shot_graph_plan.json：没有可投影的镜头", level="warn"))

    style = contract.get("visual_style") or shots_doc.get("style")
    if not style:
        violations.append(_err("STYLE_MISSING", "没有 visual_style：风格是资产与提示词的量级前提，不许留空"))

    shots = [s for s in (shots_doc.get("shots") or []) if isinstance(s, dict)]
    nodes_by_shot = {}
    for node in shots_doc.get("nodes") or []:
        if isinstance(node, dict) and node.get("shot_id"):
            nodes_by_shot.setdefault(node["shot_id"], []).append(node)

    asset_rows = {"characters": [], "locations": [], "props": [], "other": []}
    for aid, item in assets.items():
        kind = str(item.get("kind") or "").lower()
        row = {
            "id": aid,
            "name": item.get("name") or aid,
            "kind": item.get("kind"),
            "anchor_role": item.get("anchor_role"),
            "requires_iteration": bool(item.get("requires_iteration")),
            "state_versions": item.get("state_versions", 1),
            "reference_purpose": item.get("reference_purpose") or [],
            "iteration_chain": item.get("iteration_chain") or [],
            "visible": item.get("visible", True),
        }
        if kind == "character":
            asset_rows["characters"].append(row)
        elif kind in ("scene", "location"):
            asset_rows["locations"].append(row)
        elif kind == "prop":
            asset_rows["props"].append(row)
        else:
            asset_rows["other"].append(row)
            violations.append(_err("ASSET_KIND_UNMAPPED", "资产 %s 的 kind=%r 不在 character/scene/location/prop 内，原样保留" % (aid, item.get("kind")), level="warn", where=aid))

    known_asset_ids = set(assets)
    clips = []
    for order, shot in enumerate(shots):
        sid = str(shot.get("id") or "shot_%02d" % (order + 1))
        nodes = _shot_nodes(shot, nodes_by_shot)
        shot_prompts = prompts.get(sid, {})
        cand_rec = shot_prompts.get("candidate_image")
        vid_rec = shot_prompts.get("video_candidate")
        board_rec = shot_prompts.get("storyboard")

        duration = _shot_duration(shot)
        if duration is None or duration <= 0:
            violations.append(_err("CLIP_DURATION_MISSING", "镜头 %s 没有正的 duration_sec" % sid, where=sid))

        action = shot.get("description") or _block(board_rec, "shot_contract")
        if not action:
            violations.append(_err("NARRATIVE_ACTION_MISSING", "镜头 %s 既无 description 也无 storyboard 契约行" % sid, where=sid))

        entities = _clip_entities(shot, nodes, chain_owner)
        env_id = shot.get("environment_id")
        for ent in entities:
            if ent["asset_id"] not in known_asset_ids:
                violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 引用了 02 里不存在的资产 %s（来源 %s）" % (sid, ent["asset_id"], ent["source"]), where=sid))
        if env_id and env_id not in known_asset_ids:
            violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 的 environment_id=%s 不在 02 资产表" % (sid, env_id), where=sid))

        dialogue = _dialogue_of(shot)
        if dialogue["has_dialogue"] and not (dialogue.get("speaker_asset_id") and dialogue.get("text")):
            violations.append(_err("DIALOGUE_SPEAKER_MISSING", "镜头 %s 声明有对白，但缺 speaker_asset_id 或 text；不许补写" % sid, where=sid))

        if not cand_rec:
            violations.append(_err("PROMPT_PACKAGE_MISSING", "镜头 %s 没有 candidate_image 提示词包，t2i_template 留空" % sid, level="warn", where=sid))

        unknown = sorted(set(shot) - KNOWN_SHOT_KEYS)
        if unknown:
            violations.append(_err("UNMAPPED_SHOT_FIELD", "镜头 %s 有未识别字段 %s，已原样保留在 clip.studio" % (sid, ", ".join(unknown)), level="warn", where=sid))

        clip = {
            "shot_id": sid,
            "order": order,
            "plan": {
                "risk": shot.get("risk"),
                "candidate_count": shot.get("candidate_count"),
                "shot_kind": shot.get("shot_kind"),
                "roles": shot.get("roles") or [],
                "required_roles": shot.get("required_roles") or [],
                "shot_timing": shot.get("shot_timing"),
            },
            "narrative_layer": {
                "narrative_action": action,
                "emotional_beat": shot.get("emotional_beat") or "",
                "dialogue": dialogue,
                "performance_emotion": shot.get("performance_emotion"),
                "performance_intensity": shot.get("performance_intensity"),
            },
            "staging_layer": {
                "duration_seconds": duration,
                "camera": shot.get("camera") or {},
                "lighting": shot.get("lighting"),
                "environment_id": env_id,
                "entities": entities,
                "consistency_constraints": list(shot.get("consistency_constraints") or [])
                + [x for x in [_block(vid_rec, "continuity")] if x],
            },
            "render_layer": {
                "keyframe_policy": "keyframe_first",
                "image_render_spec": {
                    "engine": _node_model(nodes, "candidate_image"),
                    "t2i_template": _block(cand_rec, "visual"),
                    "resolved_t2i": shot.get("resolved_t2i"),
                    "negative_prompt": _block(cand_rec, "negative"),
                },
                "video_render_spec": {
                    "engine": _node_model(nodes, "video_candidate"),
                    "i2v_template": _block(vid_rec, "action") or _block(vid_rec, "visual"),
                    "resolved_i2v": shot.get("resolved_i2v"),
                    "negative_prompt": _block(vid_rec, "negative"),
                    "audio_desc": _block(vid_rec, "sound"),
                },
                "duration_seconds": duration,
            },
            "assembly_layer": {
                "transition_in": shot.get("transition_in") or "cut",
                "transition_out": shot.get("transition_out") or "cut",
                "cut_range": (shot.get("shot_timing") or {}).get("cut_range"),
                "audio_tracks": [],
            },
            "studio": {k: shot[k] for k in unknown},
        }
        clips.append(clip)

    if not clips:
        violations.append(_err("SHOTS_EMPTY", "没有镜头可投影：没验到 ≠ 验过了", level="empty"))

    for node_list in nodes_by_shot.values():
        for node in node_list:
            if node.get("run") is True:
                violations.append(_err("AUTHORITY_LEAK", "节点 %s 带 run=true：交换视图不得携带点火许可" % node.get("id")))

    if shots_doc.get("generation_authorized") is True:
        violations.append(_err("AUTHORITY_LEAK", "03 声明 generation_authorized=true：交换不得携带生成权"))
    delivery = contract.get("delivery") or {}
    if delivery.get("ignition_allowed") is True:
        violations.append(_err("AUTHORITY_LEAK", "01 的 delivery.ignition_allowed=true：交换不得携带点火许可"))

    revision = shots_doc.get("source_revision") or ""
    if blueprint_id is None:
        seed = revision or _canon({
            "style": style, "clips": [[c["shot_id"], c["staging_layer"]["duration_seconds"]] for c in clips],
            "assets": sorted(known_asset_ids),
        })
        blueprint_id = "bp_%s" % hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

    total = sum(c["staging_layer"]["duration_seconds"] or 0 for c in clips)
    doc = {
        "format": FORMAT,
        "blueprint_id": blueprint_id,
        "origin": {
            "projection": "aigc-agent-studio/01-04 -> filmdsl",
            "authority": "studio_artifacts_are_authoritative",
            "source_revision": revision or None,
            "artifacts": dict(art.get("hashes") or {}),
        },
        "metadata": {
            "project_name": contract.get("goal") or contract.get("project") or "untitled",
            "goal": contract.get("goal"),
            "target_aspect_ratio": contract.get("aspect_ratio"),
            "global_fps": contract.get("fps"),
            "duration_sec": contract.get("duration_sec"),
            "projected_duration_sec": round(total, 3),
            "production_mode": contract.get("production_mode"),
            "task_type": contract.get("task_type"),
            "deliverable": shots_doc.get("deliverable") or (contract.get("delivery") or {}).get("deliverable"),
        },
        "global_style": style,
        "assets": asset_rows,
        "memory": {
            "continuity": [
                {"asset_id": c.get("entity_id"), "reason": c.get("reason"),
                 "chain": [n.get("id") for n in c.get("nodes") or [] if isinstance(n, dict)]}
                for c in plan.get("iteration_chains") or [] if isinstance(c, dict)
            ],
            "rulebook": [str(x) for x in contract.get("constraints") or []],
            "world_state": {"scope": shots_doc.get("world_state_scope")},
        },
        "clips": clips,
        # ★ 2026-10-31 补：CineCrew 的 `SceneBlueprint` 只认 `shots`（extra 字段被忽略，
        #   于是"校验通过"但读到 0 镜——实测踩过）。同一份列表双写，概念上 clips==shots。
        "shots": clips,
        "studio": {
            "generation_authorized": False,
            "gate_artifacts": sorted(art.get("files", {}).items()),
        },
    }
    doc["import_report"] = _report(violations, art)
    return doc, violations


def _node_model(nodes, role):
    for node in nodes:
        if node.get("role") == role and node.get("model"):
            return node["model"]
    return None


def _report(violations, art):
    fails = [v for v in violations if v["level"] == "fail"]
    warns = [v for v in violations if v["level"] == "warn"]
    empty = [v for v in violations if v["level"] == "empty"]
    status = "empty" if empty else ("partial" if (fails or warns) else "complete")
    return {
        "status": status,
        "codes": sorted({v["code"] for v in violations}),
        "unmapped_or_missing": [
            {"code": v["code"], "where": v.get("where"), "message": v["message"]}
            for v in violations if v["level"] != "warn" or v["code"] in ("ASSET_KIND_UNMAPPED", "UNMAPPED_SHOT_FIELD")
        ],
        "artifacts_used": dict(art.get("files") or {}),
    }


# ───────────────────────────── 复核 ─────────────────────────────

def validate(doc, art, require_complete=False):
    """对既有 filmdsl 文档做结构 + 权威 + 资产引用检查（不重投影）。"""
    violations = []
    if not isinstance(doc, dict):
        return [_err("FORMAT_MISSING", "filmdsl 必须是 JSON 对象")]
    if doc.get("format") != FORMAT:
        violations.append(_err("VERSION_UNSUPPORTED", "format=%r，本库只认 %s" % (doc.get("format"), FORMAT)))

    studio = doc.get("studio") or {}
    if studio.get("generation_authorized") is not False:
        violations.append(_err("AUTHORITY_LEAK", "交换视图必须显式声明 generation_authorized=false"))

    if not doc.get("global_style"):
        violations.append(_err("STYLE_MISSING", "filmdsl.global_style 为空"))

    assets = doc.get("assets") or {}
    ids = set()
    for bucket in ("characters", "locations", "props", "other"):
        for row in assets.get(bucket) or []:
            if isinstance(row, dict) and row.get("id"):
                ids.add(str(row["id"]))
            else:
                violations.append(_err("ASSET_ROW_BAD", "%s 里有不带 id 的资产行" % bucket))
    if not ids:
        violations.append(_err("ASSETS_EMPTY", "filmdsl 没有任何资产：长片一致性无从谈起"))

    if "clips" in doc and "shots" in doc and _canon(doc["clips"]) != _canon(doc["shots"]):
        violations.append(_err("DROPPED_FIELD", "clips 与 shots 同时存在但不一致，交换视图的两份镜头正文必须相同"))

    clips = doc.get("clips") or doc.get("shots") or []
    if not clips:
        violations.append(_err("SHOTS_EMPTY", "filmdsl 没有 clips", level="empty"))
    seen = set()
    for clip in clips:
        if not isinstance(clip, dict):
            violations.append(_err("CLIP_BAD", "clips 里有非对象元素"))
            continue
        sid = clip.get("shot_id")
        if not sid:
            violations.append(_err("CLIP_ID_MISSING", "有 clip 缺 shot_id"))
            continue
        if sid in seen:
            violations.append(_err("CLIP_DUPLICATE", "shot_id=%s 重复" % sid, where=sid))
        seen.add(sid)
        staging = clip.get("staging_layer") or {}
        dur = staging.get("duration_seconds")
        if not isinstance(dur, (int, float)) or dur <= 0:
            violations.append(_err("CLIP_DURATION_MISSING", "镜头 %s 时长非正" % sid, where=sid))
        if not (clip.get("narrative_layer") or {}).get("narrative_action"):
            violations.append(_err("NARRATIVE_ACTION_MISSING", "镜头 %s 没有 narrative_action" % sid, where=sid))
        for ent in staging.get("entities") or []:
            aid = ent.get("asset_id") if isinstance(ent, dict) else ent
            if aid not in ids:
                violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 的实体 %s 不在 assets" % (sid, aid), where=sid))
        env = staging.get("environment_id")
        if env and env not in ids:
            violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 的 environment_id=%s 不在 assets" % (sid, env), where=sid))
        dlg = (clip.get("narrative_layer") or {}).get("dialogue") or {}
        if dlg.get("has_dialogue") and not (dlg.get("speaker_asset_id") and dlg.get("text")):
            violations.append(_err("DIALOGUE_SPEAKER_MISSING", "镜头 %s 有对白但缺 speaker/text" % sid, where=sid))
        leaked = [k for k, v in (clip.get("studio") or {}).items() if k == "run" and v is True]
        if leaked:
            violations.append(_err("AUTHORITY_LEAK", "镜头 %s 的 studio 里带了 run=true" % sid, where=sid))

    if art is not None:
        violations.extend(diff_against_artifacts(doc, art))

    if require_complete:
        for row in (doc.get("import_report") or {}).get("unmapped_or_missing") or []:
            violations.append(_err("REQUIRE_COMPLETE_FAILED",
                                   "开启 --require-complete，但仍有 %s：%s" % (row.get("code"), row.get("message")),
                                   where=row.get("where")))
        if (doc.get("import_report") or {}).get("status") != "complete":
            violations.append(_err("REQUIRE_COMPLETE_FAILED", "import_report.status=%r≠complete" % ((doc.get("import_report") or {}).get("status"))))
    return violations


def diff_against_artifacts(doc, art):
    """重投影 → 逐键比对。这是 check 的核心：证明视图没被改口径，也没吞字段。"""
    violations = []
    fresh, _ = export(art, blueprint_id=doc.get("blueprint_id"))
    origin = doc.get("origin") or {}
    if (origin.get("artifacts") or {}) != (fresh.get("origin") or {}).get("artifacts"):
        violations.append(_err("STALE_EXPORT", "artifacts 已变（sha256 不同）：这份 filmdsl 不是当前产物的投影，重导"))

    if doc.get("global_style") != fresh.get("global_style"):
        violations.append(_err("DROPPED_FIELD", "global_style 被改：%r ≠ 权威 %r" % (doc.get("global_style"), fresh.get("global_style"))))

    got = {c.get("shot_id"): c for c in (doc.get("clips") or doc.get("shots") or []) if isinstance(c, dict)}
    want = {c["shot_id"]: c for c in fresh["clips"]}
    for sid in sorted(set(want) - set(got)):
        violations.append(_err("DROPPED_FIELD", "权威里有镜头 %s，视图里没有" % sid, where=sid))
    for sid in sorted(set(got) - set(want)):
        violations.append(_err("DROPPED_FIELD", "视图里有权威没有的镜头 %s（不许自造镜头）" % sid, where=sid))
    for sid in sorted(set(got) & set(want)):
        g, w = got[sid], want[sid]
        for path in (("staging_layer", "duration_seconds"), ("render_layer", "image_render_spec", "t2i_template"),
                     ("render_layer", "video_render_spec", "i2v_template")):
            a, b = _dig(g, path), _dig(w, path)
            if _canon(a) != _canon(b):
                violations.append(_err("DROPPED_FIELD", "镜头 %s 的 %s 与权威投影不一致" % (sid, ".".join(path)), where=sid))
        if _canon((g.get("narrative_layer") or {}).get("narrative_action")) != _canon((w.get("narrative_layer") or {}).get("narrative_action")):
            violations.append(_err("DROPPED_FIELD", "镜头 %s 的 narrative_action 与权威投影不一致" % sid, where=sid))

    got_assets = {a.get("id") for bucket in ("characters", "locations", "props", "other")
                  for a in ((doc.get("assets") or {}).get(bucket) or []) if isinstance(a, dict)}
    want_assets = {a.get("id") for bucket in ("characters", "locations", "props", "other")
                   for a in (fresh.get("assets") or {}).get(bucket, [])}
    if got_assets != want_assets:
        extra = sorted(got_assets - want_assets)
        miss = sorted(want_assets - got_assets)
        violations.append(_err("DROPPED_FIELD", "资产集合被改：多 %s / 少 %s" % (extra, miss)))
    return violations


def _dig(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


# ───────────────────────────── CLI ─────────────────────────────

def _emit(doc, out_path):
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
    if out_path:
        parent = os.path.dirname(os.path.abspath(out_path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)


def _summary(violations):
    fails = [v for v in violations if v["level"] == "fail"]
    warns = [v for v in violations if v["level"] == "warn"]
    empty = [v for v in violations if v["level"] == "empty"]
    for v in violations:
        print("[%s] %-26s %s" % (v["level"].upper(), v["code"], v["message"]))
    print("合计：%d FAIL / %d WARN / %d EMPTY" % (len(fails), len(warns), len(empty)))
    if empty and not fails:
        return RC_EMPTY
    if fails:
        return RC_FAIL
    return RC_WARN if warns else RC_OK


def run_export(art_dir, out_path, blueprint_id=None):
    art = load_artifacts(art_dir)
    doc, violations = export(art, blueprint_id=blueprint_id)
    _emit(doc, out_path)
    return _summary(violations)


def run_check(filmdsl_path, art_dir, require_complete=False):
    doc = _load_json(filmdsl_path)
    art = load_artifacts(art_dir) if art_dir else None
    return _summary(validate(doc, art, require_complete))


# ───────────────────────────── 自检 ─────────────────────────────

def _load_cases():
    path = os.path.join(FIXTURES, "cases.json")
    doc = _load_json(path)
    cases = doc.get("cases") if isinstance(doc, dict) else doc
    if not isinstance(cases, list):
        raise ValueError("cases.json 必须是 {cases: [...]} 或数组")
    return cases


def _apply(art_dir, op):
    """按声明式 mutation 改临时副本，不改 fixtures。"""
    if not op or op == "none":
        return
    contract_path = os.path.join(art_dir, "01_production_contract.json")
    shots_path = os.path.join(art_dir, "03_shot_graph_plan.json")
    if op == "drop_style":
        doc = _load_json(contract_path)
        doc["production_contract"].pop("visual_style", None)
        _write_json(contract_path, doc)
    elif op == "zero_duration":
        doc = _load_json(shots_path)
        doc["shots"][0]["duration_sec"] = 0
        _write_json(shots_path, doc)
    elif op == "bad_asset_ref":
        doc = _load_json(shots_path)
        doc["shots"][0].setdefault("entities", []).append({"asset_id": "char_ghost"})
        _write_json(shots_path, doc)
    elif op == "auth_leak":
        doc = _load_json(contract_path)
        doc["production_contract"]["delivery"]["ignition_allowed"] = True
        _write_json(contract_path, doc)
    elif op == "dialogue_broken":
        doc = _load_json(shots_path)
        doc["shots"][0]["dialogue"] = {"has_dialogue": True, "text": None, "speaker_asset_id": None}
        _write_json(shots_path, doc)
    elif op == "drop_shots":
        path = os.path.join(art_dir, "03_shot_graph_plan.json")
        if os.path.isfile(path):
            os.remove(path)
    else:
        raise ValueError("未知 mutation：%s" % op)


def _write_json(path, doc):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _codes(violations):
    return sorted({v["code"] for v in violations if v["level"] != "warn"})


def self_test():
    cases = _load_cases()
    base = os.path.join(FIXTURES, "base")
    if not os.path.isdir(base):
        print("fixtures 缺失：%s" % base)
        return RC_USAGE
    bad = 0
    for case in cases:
        tmp = _tmpdir()
        try:
            art = os.path.join(tmp, "artifacts")
            shutil.copytree(base, art)
            _apply(art, case.get("mutation"))
            doc, export_violations = export(load_artifacts(art))
            check_violations = validate(doc, load_artifacts(art), case.get("require_complete", False))
            if case.get("tamper") == "drop_clip_in_view":
                doc["clips"] = doc["clips"][1:]
                check_violations = validate(doc, load_artifacts(art), case.get("require_complete", False))
            elif case.get("tamper") == "strip_style_in_view":
                doc["global_style"] = None
                check_violations = validate(doc, load_artifacts(art), case.get("require_complete", False))
            violations = list(export_violations) + list(check_violations)
            got = _codes(violations) + sorted({v["code"] for v in violations if v["level"] == "empty"})
            got = sorted(set(got))
            want = sorted(set(case.get("expected_codes") or []))
            if got != want:
                bad += 1
                print("[FAIL] %-28s expected=%s got=%s" % (case.get("name"), want, got))
            else:
                print("[PASS] %-28s %s" % (case.get("name"), got or "-"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("自检：%d 例，%d 失败" % (len(cases), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="FilmDSL 交换视图（filmdsl-interchange.md）")
    sub = ap.add_subparsers(dest="cmd")
    ex = sub.add_parser("export", help="把 01–04 投影成 filmdsl/v1")
    ex.add_argument("--artifacts", required=True)
    ex.add_argument("--out")
    ex.add_argument("--blueprint-id")
    ch = sub.add_parser("check", help="既有 filmdsl 与当前 artifacts 对账")
    ch.add_argument("--filmdsl", required=True)
    ch.add_argument("--artifacts", required=True)
    ch.add_argument("--require-complete", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    try:
        if args.cmd == "export":
            return run_export(args.artifacts, args.out, args.blueprint_id)
        if args.cmd == "check":
            return run_check(args.filmdsl, args.artifacts, args.require_complete)
    except ValueError as exc:
        print("用法错误：%s" % exc)
        return RC_USAGE
    ap.print_help()
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
