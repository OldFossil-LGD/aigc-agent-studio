#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Production IR：提示词系统的唯一事实来源 + 12 块确定性编译 + 规则化校验。

为什么要有它（`references/prompt-ir-contract.md` / 通用化改造建议书 P1）：
此前 12 块是**多个 Agent 各自往提示词里填**，于是同一条事实能在两处被定义成两个值，
事后谁也说不清哪一处算数。本模块按"先数据、后视图"重排：

    artifacts(01–04) / intent  ──build──▶  production-ir/v1（字段级来源 + 锁定）
                                            │
                                            ├─ validate ──▶ issues（rule_id / severity / affected_paths）
                                            └─ render ────▶ 12 块 Canonical Markdown（确定性）

三条纪律：
  ① 12 块是**编译结果**，不是权威数据；下游不许反向覆盖 IR。
  ② 每个值带 `source_type`；用户原话（user_explicit）默认 locked，Agent 补的只能是 agent_proposed。
  ③ 缺证据就 `UNKNOWN` / N/A，不编。空镜写 `人物：不适用`（character_refs=[]），不补人。

退出码（与库内其它门禁一致）：0 通过 ｜ 1 有 BLOCK ｜ 2 用法错误 ｜ 3 没有镜头 ｜ 4 只有 WARN/UNKNOWN

用法：
  python scripts/production_ir.py build --artifacts out/ --out out/16_production_ir.json [--intent intent.json]
  python scripts/production_ir.py validate --ir out/16_production_ir.json
  python scripts/production_ir.py render --ir out/16_production_ir.json --out out/15_Canonical_Prompt.md
  python scripts/production_ir.py --self-test
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys

try:
    from .filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN
    from .filmdsl_bridge import _tmpdir, load_artifacts, asset_index, contract_of
except ImportError:
    from filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN
    from filmdsl_bridge import _tmpdir, load_artifacts, asset_index, contract_of

IR_VERSION = "1.0.0"
VALIDATOR_VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PERSON_WORDS = ("他", "她", "人物", "面部", "手指", "人影", "孩子", "男人", "女人", "少年", "老人")
MOTION_WORDS = ("推", "拉", "摇", "移", "跟", "环绕", "变焦", "升降")
VAGUE_WORDS = ("电影感", "高级感", "氛围拉满", "大片感", "质感拉满", "震撼")
PERSON_FORBID = ("人声", "对白", "台词", "口型", "说话")
MUSIC_FORBID = ("音乐", "配乐", "BGM", "bgm")

CANON = [
    ("1", "后期特效"), ("2", "统一提质层"), ("3", "风险移除 + 禁止出现"),
    ("4", "本镜目的"), ("5", "镜头规格"), ("6", "构图"), ("7", "人物与环境"),
    ("8", "光位与影调"), ("9", "时间线"), ("10", "摄影机"), ("11", "声音"), ("12", "过渡压力"),
]


def _issue(rule_id, severity, message, paths=None, evidence=None, suggestion=None):
    return {
        "issue_id": "ISSUE_%s" % hashlib.sha256(("%s|%s" % (rule_id, message)).encode("utf-8")).hexdigest()[:8],
        "rule_id": rule_id,
        "severity": severity,
        "affected_paths": list(paths or []),
        "evidence": [str(x) for x in (evidence or [])],
        "suggestion": suggestion or "",
        "message": message,
        "validator_version": VALIDATOR_VERSION,
    }


def _v(value, source_type, source_ref=None, locked=False, reason=None):
    return {"value": value, "source_type": source_type, "source_ref": source_ref,
            "locked": bool(locked), "approval_status": "approved" if locked else "proposed",
            "confidence": None, "reason": reason}


def _num(x, default=None):
    try:
        value = float(x)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


# ───────────────────────── build ─────────────────────────

def _audio_policy(contract, shot=None):
    shot = shot or {}
    sound = shot.get("sound")
    if not isinstance(sound, dict):
        sound = contract.get("sound")
    legacy = contract.get("audio")
    legacy = legacy if isinstance(legacy, dict) else {}
    sound = sound if isinstance(sound, dict) else {}
    mode = sound.get("mode") or ("ambience_only" if legacy.get("no_dialogue") else "inherit_project")
    mode = {"dialogue_allowed": "custom", "unspecified": "inherit_project"}.get(mode, mode)
    deny = list(sound.get("forbidden", legacy.get("deny") or []))
    if legacy.get("no_dialogue") is True and "人声" not in deny:
        deny.append("人声")
    return {"mode": mode, "allow": list(sound.get("allowed", legacy.get("layers") or [])),
            "deny": list(dict.fromkeys(deny)),
            "dialogue": "none" if mode in ("silent", "ambience_only") or legacy.get("no_dialogue") else "unspecified",
            "sound_events": [], "source_type": sound.get("source") or "script"}


def build(art_dir, intent=None, project_id=None):
    art = load_artifacts(art_dir)
    contract = contract_of(art)
    shots_doc = art.get("shots") or {}
    assets, chain_owner = asset_index(art)
    intent = intent or {}
    decisions = intent.get("decisions") or {}

    def decision(field, fallback=None, fb_source="library_default"):
        row = decisions.get(field)
        if isinstance(row, dict) and row.get("value") is not None:
            return _v(row["value"], row.get("source") or "agent_proposed",
                      row.get("evidence"), bool(row.get("locked")))
        if fallback is not None:
            return _v(fallback, fb_source, "01_production_contract.json")
        return _v(None, "library_default", None, False, "未提供")

    aspect = decision("aspect_ratio", contract.get("aspect_ratio"))
    fps = decision("fps", contract.get("fps"))
    duration = decision("duration_sec", contract.get("duration_sec"))
    style = decision("visual_style", contract.get("visual_style"))

    requirements = []
    n = 0
    for field, row in decisions.items():
        n += 1
        value = row.get("value")
        if isinstance(value, dict):
            value = value.get("text") or ""
        requirements.append({
            "requirement_id": "REQ_%03d" % n,
            "scope": "project",
            "field_path": "delivery.%s" % field,
            "operator": "equals",
            "value": value,
            "strength": "hard" if row.get("locked") else "soft",
            "source_type": row.get("source") or "agent_proposed",
            "source_ref": row.get("evidence") or "intent.json",
            "locked": bool(row.get("locked")),
            "status": "active",
        })
    for c in intent.get("constraints") or []:
        n += 1
        requirements.append({
            "requirement_id": "REQ_%03d" % n,
            "scope": "shot",
            "field_path": "shots.*.%s" % (c.get("kind") or "other"),
            "operator": "prohibits" if c.get("kind") == "negative" else "contains",
            "value": c.get("text") or "",
            "strength": "hard" if c.get("locked") else "soft",
            "source_type": c.get("source") or "agent_proposed",
            "source_ref": c.get("id") or "constraint",
            "shots": list(c.get("shots") or []),
            "locked": bool(c.get("locked")),
            "status": "active",
        })

    chars = [{"character_id": aid, "identity_version": "v%03d" % v.get("version", 1), "look_id": None,
              "declared": bool(v.get("declared", True))}
             for aid, v in assets.items() if str(v.get("kind")).lower() == "character"]
    locs = [{"id": aid, "kind": v.get("kind"), "version": "v%03d" % v.get("version", 1)}
            for aid, v in assets.items() if str(v.get("kind")).lower() in ("scene", "location")]
    props = [{"id": aid, "kind": v.get("kind"), "version": "v%03d" % v.get("version", 1)}
             for aid, v in assets.items() if str(v.get("kind")).lower() == "prop"]

    shots = []
    raw_shots = [s for s in (shots_doc.get("shots") or []) if isinstance(s, dict)]
    for i, shot in enumerate(raw_shots):
        sid = str(shot.get("id") or "shot_%02d" % (i + 1))
        dur = _num(shot.get("duration_sec") or (shot.get("shot_timing") or {}).get("duration_sec"))
        cam = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
        movement = cam.get("movement") or shot.get("camera_movement") or "未给"
        selected = []
        explicit_refs = shot.get("asset_refs")
        if isinstance(explicit_refs, list):
            for ref in explicit_refs:
                matches = [aid for aid, asset in assets.items()
                           if asset.get("base_entity_id", aid) == ref.get("entity_id")
                           and asset.get("version", 1) == ref.get("version")]
                if len(matches) != 1:
                    raise ValueError("Unresolved asset version reference: %r" % ref)
                selected.append(matches[0])
        else:
            for ent in shot.get("entities") or []:
                aid = ent.get("asset_id") if isinstance(ent, dict) else ent
                selected.append(chain_owner.get(aid, aid))
        char_refs = [{"character_id": c["character_id"],
                      "identity_version": c["identity_version"], "look_id": c["look_id"]}
                     for c in chars if c["character_id"] in selected]
        location_id = shot.get("environment_id") or next(
            (loc["id"] for loc in locs if loc["id"] in selected), None)
        prop_refs = [p["id"] for p in props
                     if p["id"] in selected or p["id"] in (shot.get("props") or [])]
        next_id = str(raw_shots[i + 1].get("id")) if i + 1 < len(raw_shots) else "END"
        shots.append({
            "shot_id": sid,
            "scene_id": location_id,
            "order": i,
            "screen_order": i,
            "story_time": shot.get("story_time") or None,
            "purpose": _v(shot.get("purpose") or shot.get("description") or "", "script",
                          "03_shot_graph_plan.json#%s.description" % sid,
                          False),
            "delivery": {"duration_sec": _v(dur if dur is not None else 0, "script",
                                            "03_shot_graph_plan.json#%s.duration_sec" % sid),
                         "aspect_ratio": aspect.get("value"), "fps": fps.get("value")},
            "camera_spec": _v({
                "shot_size": cam.get("shot_scale") or "未给",
                "camera_angle": cam.get("angle") or "未给",
                "lens_status": "selected" if cam.get("lens") else "unknown",
                "lens": cam.get("lens"),
                "height_m": cam.get("height_m"),
            }, "script" if cam else "library_default",
                "03_shot_graph_plan.json#%s.camera" % sid, False,
                None if cam else "镜头参数未给：器材包须站 3 裁决"),
            "composition": _v(shot.get("composition"), "script" if shot.get("composition") else "library_default",
                              "03_shot_graph_plan.json#%s.composition" % sid),
            "lighting": _v(shot.get("lighting"), "script" if shot.get("lighting") else "library_default",
                           "03_shot_graph_plan.json#%s.lighting" % sid),
            "camera_movement": _v(movement, "script" if cam.get("movement") else "library_default",
                                  "03_shot_graph_plan.json#%s.camera.movement" % sid),
            "timeline": {"beats": [{"start_sec": 0, "end_sec": dur or 0,
                                    "action": shot.get("description") or ""}]},
            "asset_refs": {
                "character_refs": char_refs,
                "location_id": location_id,
                "prop_refs": prop_refs,
                "continuity_state_id": None,
            },
            "audio_policy": _audio_policy(contract, shot),
            "transition": {"kind": "cut", "target_shot_id": None if next_id == "END" else next_id,
                           "end_state": "END" if next_id == "END" else None},
        })

    ir = {
        "schema_version": IR_VERSION,
        "project": {
            "project_id": project_id or ("PRJ_%s" % hashlib.sha256(
                (contract.get("goal") or "untitled").encode("utf-8")).hexdigest()[:8]),
            "title": contract.get("goal"),
            "delivery": {"duration_sec": duration.get("value"), "aspect_ratio": aspect,
                         "fps": fps, "resolution": contract.get("resolution")},
            "quality_profile": style,
            "postproduction_plan": _v(None, "library_default", None, False, "调色/后期未给：站 3 裁决"),
            "audio_policy": _audio_policy(contract),
        },
        "requirements": requirements,
        "assets": {"characters": chars, "locations": locs, "props": props},
        "shots": shots,
        "origin": {"artifacts": art.get("files") or {}, "artifacts_sha256": art.get("hashes") or {}},
    }
    return ir


# ───────────────────────── validate ─────────────────────────

def _locked_requirements(ir, field_prefix):
    return [r for r in ir.get("requirements") or []
            if r.get("locked") and str(r.get("field_path", "")).startswith(field_prefix)]


STORY_TIME_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?|\d+(?:\.\d+)?s?)$")


def validate(ir, registry=None):
    issues = []
    shots = ir.get("shots") or []
    assets = ir.get("assets") or {}
    char_ids = {c.get("character_id") for c in assets.get("characters") or []}
    shot_ids = [s.get("shot_id") for s in shots]

    if not shots:
        issues.append(_issue("SHOTS_EMPTY", "BLOCK", "IR 里没有镜头", ["shots"]))
        return issues

    delivery = (ir.get("project") or {}).get("delivery") or {}
    project_dur = (delivery.get("duration_sec") or {}).get("value") \
        if isinstance(delivery.get("duration_sec"), dict) else delivery.get("duration_sec")
    total = 0.0

    for shot in shots:
        sid = shot.get("shot_id")
        base = "shots.%s" % sid
        for field in ("purpose", "camera_spec"):
            row = shot.get(field) or {}
            if not row.get("source_type"):
                issues.append(_issue("REQ_SOURCE_MISSING", "BLOCK",
                                     "%s 的 %s 没有来源" % (sid, field), ["%s.%s" % (base, field)]))
        dur_row = (shot.get("delivery") or {}).get("duration_sec") or {}
        dur = _num(dur_row.get("value"))
        if not dur or dur <= 0:
            issues.append(_issue("SHOT_DURATION_INVALID", "BLOCK", "%s 时长无效" % sid,
                                 ["%s.delivery.duration_sec" % base]))
        else:
            total += dur
        beats = ((shot.get("timeline") or {}).get("beats") or [])
        for b in beats:
            if _num(b.get("end_sec"), 0) > (_num(dur, 0) + 1e-6) or _num(b.get("start_sec"), 0) < 0:
                issues.append(_issue("SHOT_DURATION_INVALID", "BLOCK",
                                     "%s 的 beat 越界" % sid, ["%s.timeline.beats" % base]))
        if beats and dur:
            span = sum(max(0.0, _num(b.get("end_sec"), 0) - _num(b.get("start_sec"), 0)) for b in beats)
            if abs(span - dur) > 0.01:
                issues.append(_issue("BLOCK_DUPLICATE_AUTHORITY", "BLOCK",
                                     "%s 的时长在 delivery(%.2f) 与 beats(%.2f) 两处定义不一致" % (sid, dur, span),
                                     ["%s.delivery.duration_sec" % base, "%s.timeline.beats" % base]))
        refs = (shot.get("asset_refs") or {}).get("character_refs") or []
        for ref in refs:
            cid = ref.get("character_id") if isinstance(ref, dict) else ref
            if cid not in char_ids:
                issues.append(_issue("ASSET_REF_UNRESOLVED", "BLOCK",
                                     "%s 引用了不存在的角色 %s" % (sid, cid),
                                     ["%s.asset_refs.character_refs" % base]))
        text = " ".join([str((shot.get("purpose") or {}).get("value") or ""),
                         " ".join(str(b.get("action") or "") for b in beats)])
        if not refs and any(w in text for w in PERSON_WORDS):
            issues.append(_issue("SHOT_PRESENCE_CONFLICT", "BLOCK",
                                 "%s 声明无角色（character_refs=[]），但动作里出现人物" % sid,
                                 ["%s.asset_refs.character_refs" % base, "%s.timeline.beats" % base],
                                 ["空镜不得要求人物/局部/影子出现；需要局部请标 partial_human_presence"]))
        cam = (shot.get("camera_spec") or {}).get("value") or {}
        move = str((shot.get("camera_movement") or {}).get("value") or "")
        locked_off = str(cam.get("camera_movement") or "").lower() in ("locked_off", "static", "fixed", "固定")
        if locked_off and any(w in move for w in MOTION_WORDS):
            issues.append(_issue("CAMERA_MOTION_CONFLICT", "BLOCK",
                                 "%s 镜头规格写固定机位，摄影机块却写了运动：%s" % (sid, move),
                                 ["%s.camera_spec" % base, "%s.camera_movement" % base]))
        ag = shot.get("audio_policy") or {}
        deny = " ".join(ag.get("deny") or [])
        audio_text = " ".join(str(e.get("name") or e) for e in ag.get("sound_events") or []) + " " + text
        if any(w in deny for w in PERSON_FORBID) and any(w in audio_text for w in ("对白", "台词", "说话")):
            issues.append(_issue("AUDIO_POLICY_VIOLATION", "BLOCK",
                                 "%s 声音策略禁人声，但内容里出现对白/台词" % sid,
                                 ["%s.audio_policy.deny" % base]))
        if any(w in deny for w in MUSIC_FORBID) and any(w in audio_text for w in ("配乐", "BGM", "bgm", "音乐")):
            issues.append(_issue("AUDIO_POLICY_VIOLATION", "BLOCK",
                                 "%s 声音策略禁音乐，但内容里出现配乐" % sid, ["%s.audio_policy.deny" % base]))
        tr = shot.get("transition") or {}
        tgt = tr.get("target_shot_id")
        if tgt and tgt != "END" and tgt not in shot_ids:
            issues.append(_issue("TRANSITION_TARGET_INVALID", "BLOCK",
                                 "%s 的过渡目标 %s 不存在" % (sid, tgt), ["%s.transition.target_shot_id" % base]))
        if not tr.get("target_shot_id") and not tr.get("end_state"):
            issues.append(_issue("TRANSITION_TARGET_INVALID", "BLOCK",
                                 "%s 既无过渡目标也未声明 END" % sid, ["%s.transition" % base]))
        if str(cam.get("lens_status")) == "unknown":
            issues.append(_issue("EQUIPMENT_UNRESOLVED", "WARN",
                                 "%s 器材未定（lens_status=unknown）：站 3 裁决前不落生成" % sid,
                                 ["%s.camera_spec" % base]))
        if any(w in text for w in VAGUE_WORDS):
            issues.append(_issue("CRAFT_VAGUE_LANGUAGE", "WARN",
                                 "%s 出现抽象审美词，缺可执行细节" % sid, ["%s.timeline.beats" % base]))

    for shot in shots:
        st = shot.get("story_time")
        if st not in (None, "") and not STORY_TIME_RE.match(str(st)):
            issues.append(_issue("STORY_TIME_INVALID", "WARN",
                                 "%s 的 story_time=%r 无法解析（要求 YYYY-MM-DD 或秒数）" % (shot.get("shot_id"), st),
                                 ["shots.%s.story_time" % shot.get("shot_id")]))
    if len(shots) > 1 and any((s.get("asset_refs") or {}).get("continuity_state_id") in (None, "")
                              for s in shots):
        issues.append(_issue("CONTINUITY_UNRESOLVED", "WARN",
                             "存在未绑定连续性状态的镜头：跨镜状态变更无法追踪",
                             ["shots.*.asset_refs.continuity_state_id"]))
    model_id = (ir.get("project") or {}).get("model_id")
    if registry and model_id:
        known = {m.get("model_id") for m in registry.get("models") or []}
        if model_id not in known:
            issues.append(_issue("CAPABILITY_UNREGISTERED", "WARN",
                                 "模型 %s 未登记能力卡：先行预检前请补注册表" % model_id,
                                 ["project.model_id"]))

    locked_aspect = _locked_requirements(ir, "delivery.aspect_ratio")
    for req in locked_aspect:
        got = (delivery.get("aspect_ratio") or {}).get("value")
        if got and str(got) != str(req.get("value")):
            issues.append(_issue("REQ_LOCK_OVERRIDDEN", "BLOCK",
                                 "锁定画幅 %s 被写成 %s" % (req.get("value"), got),
                                 ["project.delivery.aspect_ratio"], [req.get("requirement_id")]))
    if project_dur and abs(total - float(project_dur)) > 0.01:
        issues.append(_issue("PROJECT_DURATION_MISMATCH", "BLOCK",
                             "全片时长锁定 %.2fs，镜头合计 %.2fs" % (float(project_dur), total),
                             ["project.delivery.duration_sec", "shots"],
                             ["调整镜头或显式修订锁定时长"]))
    return issues


def report(ir, issues, stage="pre_generation"):
    status = "BLOCK" if any(i["severity"] == "BLOCK" for i in issues) else (
        "WARN" if issues else "PASS")
    return {"schema_version": IR_VERSION, "validation_id": "VAL_%s" % hashlib.sha256(
        json.dumps(issues, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8],
        "target_id": (ir.get("project") or {}).get("project_id"),
        "stage": stage, "status": status, "validator_version": VALIDATOR_VERSION,
        "issues": issues}


# ───────────────────────── render 12 blocks ─────────────────────────

def _na(reason):
    return "N/A（%s）" % reason


def render_shot(shot, ir):
    cam = (shot.get("camera_spec") or {}).get("value") or {}
    comp = (shot.get("composition") or {})
    light = (shot.get("lighting") or {})
    move = (shot.get("camera_movement") or {})
    refs = (shot.get("asset_refs") or {})
    chars = refs.get("character_refs") or []
    ag = shot.get("audio_policy") or {}
    tr = shot.get("transition") or {}
    beats = (shot.get("timeline") or {}).get("beats") or []
    dur = ((shot.get("delivery") or {}).get("duration_sec") or {}).get("value")
    project = ir.get("project") or {}
    style = (project.get("quality_profile") or {})
    style_text = style.get("value") if isinstance(style, dict) else None
    if isinstance(style_text, dict):
        style_text = style_text.get("text")

    def val(row):
        if isinstance(row, dict) and row.get("value") not in (None, ""):
            return str(row["value"])
        return None

    lines = []
    lines.append("【1 · 后期特效】\n" + (val(project.get("postproduction_plan")) or
                                       _na("调色与后期未给，站 3 裁决（postproduction_plan）")))
    lines.append("【2 · 统一提质层】\n" + (style_text or _na("全片质感未给，站 3 定风格编号后回填")))
    negatives = [r for r in ir.get("requirements") or [] if r.get("operator") == "prohibits"]
    lines.append("【3 · 风险移除 + 禁止出现】\n" + (
        "禁止出现：" + "、".join(str(r.get("value")) for r in negatives) if negatives
        else _na("未登记禁止项（requirements 里无 prohibits）")))
    lines.append("【4 · 本镜目的】\n" + (val(shot.get("purpose")) or _na("本镜目的未给")))
    spec_bits = []
    if cam.get("shot_size") and cam.get("shot_size") != "未给":
        spec_bits.append("景别 %s" % cam["shot_size"])
    if cam.get("lens"):
        spec_bits.append("镜头 %s" % cam["lens"])
    spec_bits.append("焦段 %s" % ("未给（lens_status=%s）" % cam.get("lens_status") if cam.get("lens_status") == "unknown" else "已定"))
    if cam.get("height_m"):
        spec_bits.append("机位高度 %s 米" % cam["height_m"])
    if cam.get("camera_angle"):
        spec_bits.append("角度 %s" % cam["camera_angle"])
    spec_bits += ["时长 %ss" % dur if dur else "时长 未给",
                  "画幅 %s" % (((shot.get("delivery") or {}).get("aspect_ratio")) or "未给"),
                  "fps %s" % (((shot.get("delivery") or {}).get("fps")) or "未给")]
    lines.append("【5 · 镜头规格】\n" + "；".join(spec_bits))
    lines.append("【6 · 构图】\n" + (val(comp) or _na("构图未给（composition）")))
    if chars:
        lines.append("【7 · 人物与环境】\n" + "；".join(
            "角色 %s（identity %s / look %s）" % (c.get("character_id"), c.get("identity_version"), c.get("look_id"))
            for c in chars) + ("；场景 %s" % refs.get("location_id") if refs.get("location_id") else ""))
    else:
        lines.append("【7 · 人物与环境】\n人物：不适用（character_refs=[]）")
    lines.append("【8 · 光位与影调】\n" + (val(light) or _na("光位未给（lighting）")))
    lines.append("【9 · 时间线】\n" + ("；".join(
        "%.1f–%.1fs %s" % (_num(b.get("start_sec"), 0), _num(b.get("end_sec"), 0), b.get("action"))
        for b in beats) or _na("时间线未给")))
    lines.append("【10 · 摄影机】\n" + (val(move) or _na("运镜未给（camera_movement）")))
    allow = "、".join(ag.get("allow") or []) or "无"
    deny = "、".join(ag.get("deny") or []) or "无"
    lines.append("【11 · 声音】\n模式 %s；允许 %s；禁止 %s；对白 %s" % (
        ag.get("mode"), allow, deny, ag.get("dialogue")))
    lines.append("【12 · 过渡压力】\n" + (
        ("接 %s（%s）" % (tr.get("target_shot_id"), tr.get("kind"))) if tr.get("target_shot_id")
        else ("END：%s" % (tr.get("end_state") or "结束画面未写"))))
    return "## %s\n\n" % shot.get("shot_id") + "\n\n".join(lines)


def render(ir):
    head = ["# 12 块 Canonical Prompt（由 Production IR 编译，勿手改）", "",
            "> 权威：`production-ir/v1`（%s）。本文件是派生视图；改动必须回 IR 再重编。" % IR_VERSION, ""]
    body = [render_shot(s, ir) for s in ir.get("shots") or []]
    return "\n".join(head + body).rstrip() + "\n"


# ───────────────────────── CLI / self-test ─────────────────────────

def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def run_build(args):
    intent = _load(args.intent) if args.intent else None
    ir = build(args.artifacts, intent, args.project_id)
    rep = report(ir, validate(ir))
    if args.out:
        _write(args.out, json.dumps(ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("IR：%s（%d 镜 / %d 条要求 / 状态 %s）" % (
        args.out or "-", len(ir["shots"]), len(ir["requirements"]), rep["status"]))
    for i in rep["issues"]:
        print("[%s] %-26s %s" % (i["severity"], i["rule_id"], i["message"]))
    return _rc(rep)


def run_validate(args):
    ir = _load(args.ir)
    reg = _load(args.registry) if getattr(args, "registry", None) else None
    rep = report(ir, validate(ir, reg))
    print(json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True))
    return _rc(rep)


def run_render(args):
    ir = _load(args.ir)
    text = render(ir)
    if args.out:
        _write(args.out, text)
    print(text)
    return RC_OK


def _rc(rep):
    if rep["status"] == "BLOCK":
        return RC_FAIL
    if not (rep.get("issues")):
        return RC_OK
    return RC_WARN


def self_test():
    base = {
        "schema_version": IR_VERSION,
        "project": {"project_id": "PRJ_T", "delivery": {
            "duration_sec": {"value": 6, "source_type": "user_explicit", "locked": True},
            "aspect_ratio": {"value": "2.39:1", "source_type": "user_explicit", "locked": True},
            "fps": {"value": 24, "source_type": "user_explicit", "locked": True}}},
        "requirements": [
            {"requirement_id": "REQ_001", "scope": "project", "field_path": "delivery.aspect_ratio",
             "operator": "equals", "value": "2.39:1", "strength": "hard",
             "source_type": "user_explicit", "source_ref": "input", "locked": True, "status": "active"},
            {"requirement_id": "REQ_002", "scope": "shot", "field_path": "shots.*.sound",
             "operator": "prohibits", "value": "人声", "strength": "hard",
             "source_type": "user_explicit", "source_ref": "input", "locked": True, "status": "active"},
        ],
        "assets": {"characters": [{"character_id": "char_01", "identity_version": "v001"}],
                   "locations": [], "props": []},
        "shots": [{
            "shot_id": "shot_01", "order": 0,
            "purpose": {"value": "让她看见车里有人", "source_type": "script"},
            "delivery": {"duration_sec": {"value": 6, "source_type": "script"},
                         "aspect_ratio": "2.39:1", "fps": 24},
            "camera_spec": {"value": {"shot_size": "MCU", "lens_status": "selected", "camera_movement": "static"},
                            "source_type": "script"},
            "composition": {"value": "主体画面左半", "source_type": "script"},
            "lighting": {"value": "顶灯为主", "source_type": "script"},
            "camera_movement": {"value": "固定", "source_type": "script"},
            "timeline": {"beats": [{"start_sec": 0, "end_sec": 6, "action": "擦镜面后停住"}]},
            "asset_refs": {"character_refs": [{"character_id": "char_01"}], "location_id": None},
            "audio_policy": {"mode": "ambience_only", "allow": ["水声"], "deny": ["人声"], "dialogue": "none"},
            "transition": {"kind": "cut", "target_shot_id": "END"},
        }],
    }
    import copy
    cases = []

    def case(name, mutate, expect):
        ir = copy.deepcopy(base)
        mutate(ir)
        cases.append((name, ir, expect))

    case("baseline", lambda ir: None, [])
    case("no_source", lambda ir: ir["shots"][0].pop("purpose"), ["REQ_SOURCE_MISSING"])
    case("dur_zero", lambda ir: ir["shots"][0]["delivery"]["duration_sec"].update({"value": 0}),
         ["PROJECT_DURATION_MISMATCH", "SHOT_DURATION_INVALID"])
    case("dup_authority", lambda ir: ir["shots"][0]["timeline"]["beats"][0].update({"end_sec": 5}),
         ["BLOCK_DUPLICATE_AUTHORITY"])
    case("presence", lambda ir: (ir["shots"][0]["asset_refs"].update({"character_refs": []}),
                                 ir["shots"][0]["timeline"]["beats"][0].update({"action": "她的手停住"})),
         ["SHOT_PRESENCE_CONFLICT"])
    case("motion", lambda ir: (ir["shots"][0]["camera_movement"].update({"value": "缓慢推近"}),
                               ir["shots"][0]["camera_spec"]["value"].update({"camera_movement": "locked_off"})),
         ["CAMERA_MOTION_CONFLICT"])
    case("audio", lambda ir: ir["shots"][0]["timeline"]["beats"][0].update({"action": "她说台词"}),
         ["AUDIO_POLICY_VIOLATION"])
    case("asset", lambda ir: ir["shots"][0]["asset_refs"].update(
        {"character_refs": [{"character_id": "char_99"}]}), ["ASSET_REF_UNRESOLVED"])
    case("transition", lambda ir: ir["shots"][0]["transition"].update({"target_shot_id": "shot_99"}),
         ["TRANSITION_TARGET_INVALID"])
    case("locked_aspect", lambda ir: ir["project"]["delivery"].update(
        {"aspect_ratio": {"value": "16:9", "source_type": "agent_proposed", "locked": False}}),
         ["REQ_LOCK_OVERRIDDEN"])
    case("project_dur", lambda ir: ir["project"]["delivery"].update(
        {"duration_sec": {"value": 20, "source_type": "user_explicit", "locked": True}}),
         ["PROJECT_DURATION_MISMATCH"])

    bad = 0
    for name, ir, expect in cases:
        got = sorted({i["rule_id"] for i in validate(ir)})
        if got != sorted(expect):
            bad += 1
            print("[FAIL] %-16s expected=%s got=%s" % (name, expect, got))
        else:
            print("[PASS] %-16s %s" % (name, got or "-"))
    # 确定性 + 渲染断言
    text1, text2 = render(base), render(copy.deepcopy(base))
    checks = [
        ("编译确定性", text1 == text2),
        ("12 块齐全", sum(1 for l in text1.splitlines() if re.match(r"^【\d+ · ", l)) == 12),
        ("空镜写 N/A", "人物：不适用" in render({**base, "shots": [{**base["shots"][0],
                                                                    "asset_refs": {"character_refs": []}}]})),
    ]
    for label, ok in checks:
        if not ok:
            bad += 1
            print("[FAIL] %s" % label)
        else:
            print("[PASS] %s" % label)
    print("自检：%d 项，%d 失败" % (len(cases) + len(checks), bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="Production IR（唯一事实来源 + 12 块编译 + 规则校验）")
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build")
    b.add_argument("--artifacts", required=True)
    b.add_argument("--out")
    b.add_argument("--intent")
    b.add_argument("--project-id")
    v = sub.add_parser("validate")
    v.add_argument("--ir", required=True)
    v.add_argument("--registry")
    r = sub.add_parser("render")
    r.add_argument("--ir", required=True)
    r.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "build":
        return run_build(args)
    if args.cmd == "validate":
        return run_validate(args)
    if args.cmd == "render":
        return run_render(args)
    ap.print_help()
    return RC_USAGE


if __name__ == "__main__":
    sys.exit(main())
