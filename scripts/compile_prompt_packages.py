"""Compile node plans into role-specific prompt packages.

Prompt packages are artifacts, not prose reports. Each package carries
structured blocks so downstream gates can validate missing constraints.
"""

from __future__ import annotations

import copy

from typing import Any

try:
    from scripts.compile_shot_graph import EMPTY_SHOT_KINDS, SILENT_SHOT_KINDS, world_state_blocks
except ImportError:
    from compile_shot_graph import EMPTY_SHOT_KINDS, SILENT_SHOT_KINDS, world_state_blocks


REQUIRED_BLOCKS = {
    # ★ 2026-10-31 补（改造书 §10.2）：12 块标准要求这五块也有归属，此前只有 7 块，
    #   于是 4 本镜目的 / 5 镜头规格 / 6 构图 / 8 光位 / 10 摄影机 只能由人手写。
    "video_candidate": ["material_roles", "continuity", "visual", "action", "sound", "negative", "duration",
                        "purpose", "camera_spec", "composition", "lighting", "camera_movement",
                        "style_detail", "transition"],
    "candidate_image": ["material_roles", "visual", "composition", "negative"],
    "refined_image": ["source_role", "refine_goal", "continuity", "negative"],
    "asset_anchor": ["entity", "identity", "state", "background", "negative"],
    "asset_refine": ["source_role", "refine_goal", "state", "negative"],
    "audio": ["sound_layers", "language", "duration", "negative"],
    "storyboard": ["shot_contract", "visual", "duration"],
    "prompt": ["source_contract", "compiled_constraints"],
    "scene_ref": ["scene", "lighting", "negative"],
    "identity_ref": ["identity", "wardrobe", "negative"],
    "composition_ref": ["composition", "camera", "negative"],
    "state_ref": ["state", "continuity", "negative"],
    "selection": ["candidate_set", "decision_rule"],
    "assembly": ["timeline", "sound", "duration"],
}

# Creative craft directives that may be attached to a shot and consumed into
# prompt blocks.  This is an explicit allowlist: source/audit metadata and
# arbitrary fields are NOT routed into the delivered prompt, even if they
# happen to be strings.  Agent-authored craft directives should use one of
# these keys (or a documented synonym added here).
CREATIVE_CRAFT_KEYS = frozenset(
    {
        "performance",
        "action_feedback",
        "continuity_state",
        "transition",
        "style_detail",
        "sound_craft",
        "motion_path",
        "style_notes",
    }
)
# Which prompt block carries which constraint kind, **per consuming role**.
#
# is not a consumer of that kind simply does not receive it (no noise). A role
# that IS a consumer but has no matching block is reported as `pending` — it
# is never silently dropped.
CONSTRAINT_DELIVERY_BY_KIND = {
    "camera": {
        "video_candidate": "visual",
        "composition_ref": "camera",
        "storyboard": "visual",
        "candidate_image": "visual",
    },
    "composition": {
        "video_candidate": "visual",
        "composition_ref": "composition",
        "candidate_image": "composition",
        "storyboard": "visual",
    },
    "visual": {
        "video_candidate": "visual",
        "candidate_image": "visual",
        "scene_ref": "scene",
        "storyboard": "visual",
    },
    "action": {
        "video_candidate": "action",
        "storyboard": "shot_contract",
    },
    "negative": {
        "video_candidate": "negative",
        "candidate_image": "negative",
        "refined_image": "negative",
        "scene_ref": "negative",
        "composition_ref": "negative",
        "identity_ref": "negative",
        "state_ref": "negative",
        "asset_anchor": "negative",
        "asset_refine": "negative",
    },
    "duration": {
        "video_candidate": "duration",
        "storyboard": "duration",
        "assembly": "duration",
        "audio": "duration",
    },
    "ratio": {
        "video_candidate": "visual",
        "candidate_image": "visual",
        "scene_ref": "scene",
        "composition_ref": "composition",
        "storyboard": "visual",
    },
    "sound": {
        "video_candidate": "sound",
        "assembly": "sound",
        "audio": "sound_layers",
    },
    "performance": {
        "video_candidate": "action",
        "storyboard": "shot_contract",
        "candidate_image": "visual",
    },
    "continuity": {
        "video_candidate": "continuity",
        "state_ref": "continuity",
        "refined_image": "continuity",
        "assembly": "timeline",
    },
    "transition": {
        "video_candidate": "continuity",
        "storyboard": "shot_contract",
        "assembly": "timeline",
    },
    "style": {
        "video_candidate": "visual",
        "candidate_image": "visual",
        "scene_ref": "scene",
        "storyboard": "visual",
    },
    "sound_craft": {
        "video_candidate": "sound",
        "audio": "sound_layers",
        "assembly": "sound",
    },
    "craft": {
        "video_candidate": "action",
        "storyboard": "shot_contract",
        "candidate_image": "visual",
    },
    "other": {
        "prompt": "compiled_constraints",
        "video_candidate": "visual",
        "candidate_image": "visual",
    },
}

# The prompt package is the single source of truth for prompt delivery. Its
# format version is stamped on every package so a consumer can tell which
# dialect it is reading instead of guessing from field names.
PROMPT_PACKAGE_FORMAT = "prompt-package/v1"

# Legacy offline renderer target names. Kept so the offline renderer can be
# fed by the canonical packages through a one-way adapter.
TARGET_TYPE_BY_ROLE = {
    "asset_anchor": "asset",
    "asset_refine": "asset",
    "candidate_image": "asset",
    "refined_image": "asset",
    "scene_ref": "asset",
    "identity_ref": "asset",
    "composition_ref": "asset",
    "state_ref": "asset",
    "storyboard": "storyboard",
    "prompt": "storyboard",
    "video_candidate": "video",
    "assembly": "video",
    "audio": "audio",
    "selection": "selection",
}



def _base_package(
    node: dict[str, Any],
    contract: dict[str, Any],
    incoming: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    style = contract.get("visual_style", "写实电影")
    goal = contract.get("goal", "")
    return {
        "prompt_format": PROMPT_PACKAGE_FORMAT,
        "node_id": node["id"],
        "shot_id": node.get("shot_id"),
        "role": node["role"],
        "node_type": node.get("node_type", "text"),
        "target_type": TARGET_TYPE_BY_ROLE.get(node["role"], "asset"),
        "blocks": {},
        "unresolved": [],
        "style": style,
        "goal": goal,
        "references": incoming or [],
        "constraint_evidence": [],
    }


def _shot_seconds(contract: dict[str, Any], shot_id: Any) -> Any:
    for shot in contract.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        if str(shot.get("id") or "") == str(shot_id):
            return shot.get("duration_sec")
    return None


def _package_timing(node: dict[str, Any], package: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    timing = node.get("shot_timing") or package.get("shot_timing") or {}
    seconds = timing.get("generation_duration_sec") or timing.get("duration_sec")
    if seconds is None:
        seconds = _shot_seconds(contract, node.get("shot_id"))
    if seconds is None:
        seconds = contract.get("duration_sec")
    shots = contract.get("shots") or []
    mode = "single_shot" if len(shots) <= 1 else "sequence"
    return {"seconds": seconds, "mode": mode}


def _package_route(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": node.get("model"),
        "mode": node.get("mode_type"),
    }


def _append_block_text(package: dict[str, Any], block: str, text: str) -> None:
    """Append a line to a block, keeping the block non-empty and readable."""

    blocks = package.setdefault("blocks", {})
    current = blocks.get(block)
    if not isinstance(current, str):
        current = "" if current is None else str(current)
    line = text.strip()
    if not line:
        return
    if line in current:
        return
    blocks[block] = (current.rstrip() + "\n" + line).strip() if current else line


def _normalise_constraints(raw_constraints: Any) -> list[dict[str, Any]]:
    """Return constraints as dicts.

    Legacy inputs carry plain strings; they stay supported and are treated as
    `user_explicit` text constraints that must reach the prompt.
    """

    items: list[dict[str, Any]] = []
    if not isinstance(raw_constraints, list):
        return items
    for index, raw in enumerate(raw_constraints):
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                continue
            items.append(
                {
                    "id": "constraint_%02d" % (index + 1),
                    "kind": "other",
                    "text": text,
                    "delivery": "prompt",
                    "source": "user_explicit",
                    "locked": True,
                    "shots": [],
                    "semantics": {},
                    "legacy_string": True,
                }
            )
            continue
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        kind = raw.get("kind") or "other"
        item = {
            "id": str(raw.get("id") or "constraint_%02d" % (index + 1)),
            "kind": kind,
            "text": text,
            "delivery": raw.get("delivery") or "prompt",
            "source": raw.get("source") or "user_explicit",
            "locked": bool(raw.get("locked")),
            "shots": list(raw.get("shots") or []),
            "semantics": dict(raw.get("semantics") or {}),
            "legacy_string": False,
        }
        items.append(item)
    return items


def _constraint_applies(constraint: dict[str, Any], shot_id: Any) -> bool:
    shots = constraint.get("shots") or []
    if not shots:
        return True
    if shot_id is None:
        return False
    return str(shot_id) in {str(item) for item in shots}


def _sound_intent_for(contract: dict[str, Any], shot_id: Any) -> dict[str, Any] | None:
    """Effective structured sound intent for a shot (shot overrides project)."""

    shots = contract.get("shots") or []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        if str(shot.get("id") or "") != str(shot_id):
            continue
        if isinstance(shot.get("sound"), dict):
            return shot["sound"]
        break
    sound = contract.get("sound")
    return sound if isinstance(sound, dict) else None


def _orientation_label(ratio: Any) -> str:
    """Human orientation of an aspect ratio ("9:16" → 竖屏)."""

    text = str(ratio or "")
    if ":" not in text:
        return ""
    try:
        width, height = text.split(":", 1)
        width_value = float(width)
        height_value = float(height)
    except ValueError:
        return ""
    if height_value > width_value:
        return "（竖屏）"
    if width_value > height_value:
        return "（横屏）"
    return "（方形）"


def _delivery_settings_text(
    node: dict[str, Any], package: dict[str, Any], contract: dict[str, Any]
) -> str:
    """The copyable delivery settings of one candidate: ratio and duration.

    These are the *authoritative* values: the node's own settings carry the
    aspect ratio the compiler resolved, and the duration is the one the
    compiler resolved for that shot (node timing first, then the package
    duration, then the contract). Both are written into the prompt body so
    the delivered text really carries the decision — a decision that only
    lives in the contract is not a delivered decision.

    Returns an empty string when nothing authoritative is known; the caller
    then leaves the block out entirely rather than shipping a placeholder.
    """

    settings = node.get("settings") or {}
    ratio = settings.get("ratio") or contract.get("aspect_ratio")
    seconds: Any = None
    timing = node.get("shot_timing") or package.get("shot_timing") or {}
    if isinstance(timing, dict):
        seconds = timing.get("duration_sec") or timing.get("generation_duration_sec")
    if seconds is None:
        seconds = (package.get("duration") or {}).get("seconds")
    if seconds is None:
        seconds = node.get("duration")
    if seconds is None:
        seconds = contract.get("duration_sec")
    parts: list[str] = []
    if ratio:
        parts.append("画幅 %s%s" % (ratio, _orientation_label(ratio)))
    if seconds is not None:
        parts.append("时长 %s 秒" % seconds)
    if not parts:
        return ""
    return "；".join(parts) + "。"


def _apply_delivery_settings(
    blocks: dict[str, Any],
    node: dict[str, Any],
    package: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    """Write the copyable delivery settings, if they are known.

    An unknown value means **no block at all** — an empty or placeholder
    block would be a promise the compiler cannot keep.
    """

    text = _delivery_settings_text(node, package, contract)
    if text:
        blocks["delivery_settings"] = text


def _style_register(contract: dict[str, Any]) -> str:
    register = contract.get("visual_style_register")
    if isinstance(register, str) and register.strip():
        return register.strip().lower()
    style = str(contract.get("visual_style") or "")
    if any(marker in style for marker in ("剪纸", "拼贴", "剪影", "纸艺", "版画", "拼贴画", "动画")):
        return "stylized"
    return "photoreal"


def _visual_block(package: dict[str, Any], contract: dict[str, Any]) -> str:
    """Style-aware visual line.

    A stylized task must not receive the photoreal template (that is how an
    "剪纸空镜" silently turns into a live-action shot).
    """

    register = _style_register(contract)
    style = package.get("style") or ""
    technique = contract.get("visual_style_technique")
    if register == "stylized":
        style_text = str(style)
        papercut_markers = ("剪纸", "拼贴", "剪影", "纸艺", "版画")
        if any(marker in style_text for marker in papercut_markers):
            base = "%s；纸艺剪裁的平面层次，边缘干净，色块平涂不追求照片级纹理。" % style
        else:
            base = style_text
        if technique:
            base += " 技法：%s。" % technique
        return base
    if register == "illustration":
        # register is an interface classification only; it must not append a
        # concrete craft (flat colour blocks etc.) that the text did not ask for.
        base = str(style)
        if technique:
            base += " 技法：%s。" % technique
        return base
    if register == "graphic":
        base = str(style)
        if technique:
            base += " 技法：%s。" % technique
        return base
    # Keep the legacy default for explicitly named photoreal styles only.
    # A classification alone cannot supply material or lighting instructions.
    photoreal_styles = ("写实", "写实风格", "photoreal", "photorealistic", "realistic")
    if str(style).strip().lower() in photoreal_styles:
        base = "%s，真实材质，自然光，避免塑料感和拼贴感。" % style
    else:
        base = str(style)
    if technique:
        base += " 技法：%s。" % technique
    return base



def _fill_blocks(node: dict[str, Any], package: dict[str, Any], assets_by_id: dict[str, Any], contract: dict[str, Any] | None = None) -> None:
    contract = contract if isinstance(contract, dict) else {}
    role = node["role"]
    shot_id = node.get("shot_id") or "global"
    shot_description = node.get("shot_description") or ""
    shot_kind = str(node.get("shot_kind") or "").lower()
    is_empty = shot_kind in EMPTY_SHOT_KINDS
    text_only = contract.get("task_type") == "prompt_only"
    blocks = package["blocks"]
    if role == "video_candidate":
        placeholders = [f'{{{{Node "{ref["source"]}"}}}}' for ref in package.get("references") or []]
        if text_only:
            blocks["material_roles"] = [
                "空间、材质、光线、机位、景别、遮挡和留白以本镜文字描述为准。",
                "本镜为空镜：只拍环境与物件，不出现人物、面孔、人体或身份线索。"
                if is_empty else "主体外观、服装与道具沿用本镜文字设定。",
            ]
        elif is_empty:
            blocks["material_roles"] = [
                "场景参考：空间、材质、光线，不采用图中文字或 UI。",
                "构图参考：机位、景别、遮挡和留白。",
                "本镜为空镜：只拍环境与物件，不出现人物、面孔、人体或身份线索。",
            ]
        else:
            blocks["material_roles"] = [
                "场景参考：空间、材质、光线，不采用图中文字或 UI。",
                "身份参考：角色五官、年龄、服装身份，不采用背景。",
                "构图参考：机位、景别、遮挡和留白。",
            ]
        if placeholders and not text_only:
            blocks["material_roles"].append("引用： " + " / ".join(placeholders))
        if is_empty:
            blocks["continuity"] = "保持空间、材质、光线方向和物件位置连续；本镜无人物，不新增人物身份或人物穿着；已声明物件及其状态照常保留。"
        else:
            blocks["continuity"] = "保持人物身份、服装、道具归属、空间方向、光线和声音连续；不交换角色特征。"
        blocks["visual"] = _visual_block(package, contract)
        if is_empty:
            blocks["action"] = "呈现镜头 %s 的画面内容：%s；画面内不出现人物或人体动作，物理关系可信，段内不硬切。" % (
                shot_id,
                shot_description or "按分镜契约执行",
            )
        else:
            blocks["action"] = f"完成镜头 {shot_id} 的主要动作：{shot_description or '按分镜契约执行'}；动作物理可信，段内不硬切。"
        blocks["sound"] = (
            "本镜声音以已声明的要求为准；未声明的人声或配乐不擅自加入。"
            if is_empty else "保留环境声、动作声和必要的人声层；除非镜头要求，不加入现代音乐。"
        )
        na = "N/A（%s 未给：%s）"
        blocks["purpose"] = (node.get("purpose") or shot_description or
                             na % ("本镜目的", "站 1 命题"))
        cam = node.get("camera") if isinstance(node.get("camera"), dict) else {}
        spec_bits = []
        if cam.get("shot_scale"):
            spec_bits.append("景别 %s" % cam["shot_scale"])
        if cam.get("angle"):
            spec_bits.append("角度 %s" % cam["angle"])
        if cam.get("lens"):
            spec_bits.append("镜头 %s" % cam["lens"])
        else:
            spec_bits.append("焦段 %s" % (na % ("焦段/器材", "站 3 器材包裁决")))
        spec_bits.append("画幅 %s" % ((contract.get("aspect_ratio") or na % ("画幅", "输入未给"))))
        blocks["camera_spec"] = "；".join(spec_bits)
        blocks["composition"] = node.get("composition") or na % ("构图", "站 6 构图")
        blocks["lighting"] = node.get("lighting") or na % ("光位与影调", "站 6 光位")
        blocks["camera_movement"] = (node.get("camera_movement") or cam.get("movement") or
                                     na % ("运镜", "站 6 运镜"))
        # 块 1 与块 12 也进块表（2026-10-31）：此前只有 craft 才写，无 craft 时整块缺席，
        # 12 块在机器侧只有 10 块。缺的写 N/A，craft 若存在会在后面覆盖/追加。
        blocks.setdefault("style_detail", na % ("后期特效/调色方向", "站 3 调色族"))
        blocks.setdefault("transition", na % ("过渡压力", "站 6 过渡"))
        blocks["negative"] = "禁止字幕、LOGO、UI、水印、多余人物、肢体畸变、重复主体和参考图边框。"
        if is_empty:
            blocks["negative"] = blocks["negative"].replace("、多余人物", "").rstrip("；。 ") + "；禁止人物、面孔、人体、说话者。"
        if "shot_timing" in node:
            package["shot_timing"] = copy.deepcopy(node["shot_timing"])
        timing = node.get("shot_timing") or package.get("shot_timing") or {}
        used_duration = timing.get("duration_sec")
        if used_duration is None:
            used_duration = node.get("duration")
        source_duration = timing.get("generation_duration_sec")
        if source_duration is None:
            source_duration = used_duration
        cut_range = timing.get("cut_range") or {}
        cut_start = cut_range.get("start_sec")
        if cut_start is None:
            cut_start = 0
        cut_end = cut_range.get("end_sec")
        if cut_end is None:
            cut_end = used_duration
        blocks["duration"] = (
            "成片时长 %s 秒（生成 %s 秒，裁切 %s–%s 秒）。"
            % (used_duration, source_duration, cut_start, cut_end)
        )
        _apply_delivery_settings(blocks, node, package, contract)
    elif role == "candidate_image":
        placeholders = [f'{{{{Node "{ref["source"]}"}}}}' for ref in package.get("references") or []]
        blocks["material_roles"] = (
            "场景、主体与构图以本镜文字设定为准。" if text_only else
            "使用视频参考图集合中的场景、身份与构图来源，每个来源只承担一个用途。"
        )
        if placeholders and not text_only:
            blocks["material_roles"] += " 引用：" + " / ".join(placeholders)
        blocks["visual"] = "%s 镜头 %s 的候选关键帧：%s。" % (
            _visual_block(package, contract),
            shot_id,
            shot_description or "按分镜契约执行",
        )
        blocks["composition"] = "主体位置清楚，前中后景分层明确，留出后续运动空间。"
        blocks["negative"] = "禁止拼贴、画中画、分格线、文字和参考图外框。"
        _apply_delivery_settings(blocks, node, package, contract)
    elif role == "refined_image":
        placeholders = [f'{{{{Node "{ref["source"]}"}}}}' for ref in package.get("references") or []]
        blocks["source_role"] = "以上游候选图为唯一构图基准。" + (
            " 引用：" + " / ".join(placeholders) if placeholders else ""
        )
        blocks["refine_goal"] = "只修正身份、状态、材质或局部结构；不改变机位和主体数量。"
        blocks["continuity"] = "保持主体身份、服装、道具和背景拓扑不变。"
        blocks["negative"] = "禁止重新设计场景、增加主体、改变轴线或重建构图。"
    elif role in {"asset_anchor", "asset_refine"}:
        entity_id = node.get("entity_id")
        asset = assets_by_id.get(entity_id) if entity_id else None
        name = (asset or {}).get("name") or entity_id or "未命名实体"
        kind = (asset or {}).get("kind") or "other"
        description = (asset or {}).get("description")
        state_versions = (asset or {}).get("state_versions", 1)
        state_content = (asset or {}).get("state")
        reference_purpose = (asset or {}).get("reference_purpose") or []
        blocks["entity"] = "对应资产实体：%s（%s）。" % (name, kind) + (
            " 实体描述：%s。" % description if description else " 实体描述：未提供。"
        )
        if description:
            blocks["identity"] = "保持可见身份信号：%s；轮廓、年龄、服装、材质、色彩、比例与该描述一致。" % description
        else:
            blocks["identity"] = "身份描述未提供：必须补充实体的可见身份信号（五官、年龄、服装、材质、色彩、比例），不能以“保持人物身份”替代。"
            if "missing_entity_identity" not in package["unresolved"]:
                package["unresolved"].append("missing_entity_identity")
        if state_content:
            blocks["state"] = "记录当前状态：%s（共 %s 版）；状态只向前变化，不从其他状态自动回滚。" % (state_content, state_versions)
        else:
            blocks["state"] = "记录当前状态版本（共 %s 版）；状态只向前变化，不从其他状态自动回滚。" % state_versions
        blocks["background"] = "中性背景或场景专用背景，按资产类型限定。"
        blocks["source_role"] = "以上游资产节点为参考来源。" + (
            " 参考用途：" + "、".join(str(item) for item in reference_purpose) if reference_purpose else ""
        )
        blocks["refine_goal"] = "只做一个维度的定向修图。"
        blocks["negative"] = "禁止身份漂移、多余主体、文字和参考图边框。"
        if not description:
            if "missing_entity_description" not in package["unresolved"]:
                package["unresolved"].append("missing_entity_description")
    elif role == "audio":
        blocks["sound_layers"] = "环境床、拟音、硬效、人声/旁白、设计声按需分层。"
        blocks["language"] = "按项目语言设置。"
        blocks["duration"] = "按镜头发声段落或独立声音层时长填写。"
        blocks["negative"] = "不混入无关音乐，不使用未授权音色。"
    elif role == "storyboard":
        blocks["shot_contract"] = f"镜头 {shot_id}：{shot_description or '按分镜契约执行'}。"
        blocks["visual"] = "景别、机位、构图、动作瞬间和光影结构。"
        blocks["duration"] = "与 settings.duration 一致。"
    elif role == "prompt":
        blocks["source_contract"] = f"由分镜 {shot_id} 编译。"
        blocks["compiled_constraints"] = "素材职责、连续性、动作、声音、负面约束和时长。"
    elif role == "scene_ref":
        blocks["scene"] = "场景空间、建筑、地貌、道具与可见边界。"
        blocks["lighting"] = "光源方向、色温、时间、对比和阴影结构。"
        blocks["negative"] = "不采用图中人物、文字、UI 或参考图边框。"
    elif role == "identity_ref":
        blocks["identity"] = "角色年龄、脸部结构、发型、比例和身份锚点。"
        blocks["wardrobe"] = "服装、银饰、配饰和材质状态。"
        blocks["negative"] = "不采用图片背景、道具或第二人物。"
    elif role == "composition_ref":
        blocks["composition"] = "机位、景别、主体位置、遮挡、前中后景和留白。"
        blocks["camera"] = "镜头焦段、高度、朝向和运动趋势。"
        blocks["negative"] = "不把构图参考误当身份参考，不继承图中人物脸。"
    elif role == "state_ref":
        blocks["state"] = "角色、道具或场景的当前状态版本。"
        blocks["continuity"] = "保持状态只向前变化，不回滚到旧状态。"
        blocks["negative"] = "禁止自动恢复默认造型、干净状态或丢失道具。"
    elif role == "selection":
        blocks["candidate_set"] = "列出所有候选图/视频及其版本。"
        blocks["decision_rule"] = "按身份、构图、动作、声音和连续性选择，不只按好看。"
    elif role == "assembly":
        blocks["timeline"] = "按镜头顺序拼接候选；必要时记录裁切。"
        blocks["sound"] = "声音按时间线与视频装配对齐。"
        blocks["duration"] = "总时长等于各片段时长之和。"
    else:
        blocks["description"] = f"{role} node for {shot_id}"


    # --- shot-level creative craft directives ------------------------------
    _shot = None
    for _candidate in (contract.get("shots") or []):
        if isinstance(_candidate, dict) and str(_candidate.get("id") or "") == str(shot_id):
            _shot = _candidate
            break
    if isinstance(_shot, dict):
        _STANDARD_SHOT_KEYS = {
            "id", "duration_sec", "description", "shot_kind", "kind", "sound",
            "risk", "no_dialogue", "generation_duration_sec", "cut_range",
        }
        for _key, _value in _shot.items():
            if _key in _STANDARD_SHOT_KEYS:
                continue
            # Only documented creative craft directives may reach the prompt
            # blocks. Source/audit metadata and arbitrary fields are dropped so
            # they cannot masquerade as creative content.
            if _key not in CREATIVE_CRAFT_KEYS:
                continue
            text = _value
            if isinstance(text, (list, tuple)):
                text = "；".join(str(item) for item in text if str(item).strip())
            if not isinstance(text, str) or not text.strip():
                continue
            lowered = _key.lower()
            if any(marker in lowered for marker in ("sound", "audio", "voice")):
                target_block = "sound"
            elif any(marker in lowered for marker in ("style", "look", "render", "visual")):
                target_block = "visual"
            elif any(marker in lowered for marker in ("continuity", "state", "transition")):
                target_block = "continuity"
            else:
                target_block = "action"
            if target_block in package["blocks"]:
                _append_block_text(package, target_block, text.strip())

    missing = [name for name in REQUIRED_BLOCKS.get(role, []) if name not in package["blocks"]]
    for name in list(package["blocks"]):
        if not _block_has_content(package["blocks"][name]):
            if name not in missing:
                missing.append(name)
    package["missing_blocks"] = missing
    if package["unresolved"]:
        package["status"] = "INCOMPLETE"
    else:
        package["status"] = "READY" if not missing else "INCOMPLETE"


def _block_has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0 and all(_block_has_content(item) for item in value)
    if isinstance(value, dict):
        return len(value) > 0 and all(_block_has_content(v) for v in value.values())
    return True


def compile_prompt_packages(
    contract: dict[str, Any],
    assets: dict[str, Any],
    graph: dict[str, Any],
) -> list[dict[str, Any]]:
    assets_by_id = {a.get("id"): a for a in assets.get("assets") or []}
    incoming_by_target: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges") or []:
        incoming_by_target.setdefault(edge.get("target"), []).append(
            {"source": edge.get("source"), "purpose": edge.get("purpose")}
        )
    shot_kind_by_id: dict[str, str] = {}
    contract_shots = contract.get("shots") if isinstance(contract, dict) else []
    for index, shot in enumerate(contract_shots or []):
        if not isinstance(shot, dict):
            continue
        kind = str(shot.get("shot_kind") or shot.get("kind") or "standard").lower()
        shot_id = shot.get("id")
        if not shot_id:
            shot_id = f"shot_{index + 1:02d}"
        shot_kind_by_id[str(shot_id)] = kind

    project_no_dialogue = False
    contract_no_dialogue_by_id: dict[str, Any] = {}
    if isinstance(contract, dict):
        project_no_dialogue = contract.get("no_dialogue") is True
        for index, shot in enumerate(contract_shots or []):
            if not isinstance(shot, dict):
                continue
            shot_id = shot.get("id")
            if not shot_id:
                shot_id = f"shot_{index + 1:02d}"
            if "no_dialogue" in shot:
                contract_no_dialogue_by_id[str(shot_id)] = shot.get("no_dialogue") is True
            else:
                contract_no_dialogue_by_id[str(shot_id)] = None

    graph_shots = graph.get("shots") if isinstance(graph, dict) else []
    for index, shot in enumerate(graph_shots or []):
        if not isinstance(shot, dict):
            continue
        kind = str(shot.get("shot_kind") or shot.get("kind") or "standard").lower()
        shot_id = shot.get("id")
        if not shot_id:
            shot_id = f"shot_{index + 1:02d}"
        shot_kind_by_id.setdefault(str(shot_id), kind)

    constraints = _normalise_constraints(contract.get("constraints") if isinstance(contract, dict) else None)

    graph_no_dialogue_by_id: dict[str, bool] = {}
    for index, shot in enumerate(graph_shots or []):
        if not isinstance(shot, dict):
            continue
        shot_id = shot.get("id")
        if not shot_id:
            shot_id = f"shot_{index + 1:02d}"
        if "no_dialogue" in shot:
            graph_no_dialogue_by_id[str(shot_id)] = shot.get("no_dialogue") is True

    def _shot_no_dialogue(shot_id):
        if shot_id is None:
            return project_no_dialogue
        sid = str(shot_id)
        if sid in contract_no_dialogue_by_id:
            value = contract_no_dialogue_by_id[sid]
            return project_no_dialogue if value is None else value
        if sid in graph_no_dialogue_by_id:
            value = graph_no_dialogue_by_id[sid]
            return project_no_dialogue if value is None else value
        return project_no_dialogue

    world_shots = {str(shot["id"]): shot for shot in graph_shots or [] if isinstance(shot, dict) and "id" in shot}
    packages: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        role = node.get("role")
        if role not in REQUIRED_BLOCKS:
            continue
        package = _base_package(node, contract, incoming_by_target.get(node.get("id"), []))
        _fill_blocks(node, package, assets_by_id, contract)
        package["duration"] = _package_timing(node, package, contract)
        package["model_route"] = _package_route(node)
        shot_id = node.get("shot_id")
        if shot_id is None:
            shot_id = package.get("shot_id")
        shot_kind = shot_kind_by_id.get(str(shot_id)) if shot_id is not None else None
        no_dialogue = _shot_no_dialogue(shot_id)
        is_silent = shot_kind in SILENT_SHOT_KINDS
        is_empty = shot_kind in EMPTY_SHOT_KINDS
        sound_intent = _sound_intent_for(contract, shot_id) if isinstance(contract, dict) else None

        # --- structured sound intent (intent-handoff/v1) -------------------------
        # It is authoritative when present: it beats the generic template and
        # beats the legacy no_dialogue boolean for the same shot.
        if sound_intent and isinstance(package.get("blocks"), dict):
            mode = sound_intent.get("mode")
            allowed = [item for item in (sound_intent.get("allowed") or []) if item]
            forbidden = [item for item in (sound_intent.get("forbidden") or []) if item]
            if mode == "silent":
                package["blocks"]["sound"] = "完全无声；禁止人声、对白、旁白、环境声、拟音、音效、音乐。"
            elif mode == "ambience_only":
                layers = "、".join(allowed) if allowed else "环境声"
                text = "只保留 %s；禁止人声、对白、旁白、口型说话与歌词。" % layers
                if forbidden:
                    text += "禁止：%s。" % "、".join(forbidden)
                package["blocks"]["sound"] = text
                if isinstance(package["blocks"].get("negative"), str):
                    negative = package["blocks"]["negative"]
                    if "禁止人声" not in negative:
                        package["blocks"]["negative"] = negative.rstrip("；。 ") + "；禁止人声、对白、旁白。"
            elif mode == "dialogue_allowed":
                text = "允许对白与人声；除镜头要求外不加入现代音乐。"
                if forbidden:
                    text += "禁止：%s。" % "、".join(forbidden)
                package["blocks"]["sound"] = text
        elif is_silent and package.get("role") in {"video_candidate", "assembly"}:
            if isinstance(package.get("blocks"), dict):
                package["blocks"]["sound"] = "完全无声；禁止人声、对白、旁白、环境声、拟音、音效、音乐。"
        elif no_dialogue and package.get("role") in {"video_candidate", "assembly"}:
            if isinstance(package.get("blocks"), dict):
                package["blocks"]["sound"] = "保留环境声、拟音、音效；禁止人声、对白、旁白；除非镜头要求，不加入现代音乐。"
                if isinstance(package["blocks"].get("negative"), str) and "禁止人声" not in package["blocks"]["negative"]:
                    package["blocks"]["negative"] = package["blocks"]["negative"].rstrip("；。 ") + "；禁止人声、对白、旁白。"
        if (sound_intent or no_dialogue) and package.get("role") == "audio":
            if isinstance(package.get("blocks"), dict):
                mode = (sound_intent or {}).get("mode") if isinstance(sound_intent, dict) else None
                if mode == "silent":
                    if "sound_layers" in package["blocks"]:
                        package["blocks"]["sound_layers"] = "完全无声；禁止人声、对白、旁白、环境声、拟音、音效、音乐。"
                    if isinstance(package["blocks"].get("negative"), str) and "禁止人声" not in package["blocks"]["negative"]:
                        package["blocks"]["negative"] = package["blocks"]["negative"].rstrip("；。 ") + "；禁止人声、对白、旁白。"
                    if isinstance(package["blocks"].get("language"), str):
                        package["blocks"]["language"] = "非语音说明：完全无声。"
                elif mode == "ambience_only":
                    allowed = [item for item in ((sound_intent or {}).get("allowed") or []) if item]
                    layers = "、".join(allowed) if allowed else "环境声"
                    if "sound_layers" in package["blocks"]:
                        package["blocks"]["sound_layers"] = "保留 %s；禁止人声、对白、旁白。" % layers
                    if isinstance(package["blocks"].get("negative"), str) and "禁止人声" not in package["blocks"]["negative"]:
                        package["blocks"]["negative"] = package["blocks"]["negative"].rstrip("；。 ") + "；禁止人声、对白、旁白。"
                    if isinstance(package["blocks"].get("language"), str):
                        package["blocks"]["language"] = "非语音说明：仅 %s。" % layers
                elif mode == "dialogue_allowed":
                    if "sound_layers" in package["blocks"]:
                        package["blocks"]["sound_layers"] = "允许对白与人声；环境声与拟音按镜头要求。"
                    if isinstance(package["blocks"].get("language"), str):
                        package["blocks"]["language"] = "非语音说明：允许对白与人声。"
                else:
                    if "sound_layers" in package["blocks"]:
                        package["blocks"]["sound_layers"] = "环境声、拟音、音效层；禁止人声、对白、旁白。"
                    if isinstance(package["blocks"].get("negative"), str) and "禁止人声" not in package["blocks"]["negative"]:
                        package["blocks"]["negative"] = package["blocks"]["negative"].rstrip("；。 ") + "；禁止人声、对白、旁白。"
                    if isinstance(package["blocks"].get("language"), str):
                        package["blocks"]["language"] = "非语音说明：仅环境声与拟音。"

        # --- re-apply shot-level sound craft directives -------------------------
        # Structured sound intent owns the sound block template and would
        # otherwise displace craft directives (e.g. "滴答余响延续2秒").  Re-append
        # them so the timing/positioning detail survives in the delivered body.
        if isinstance(package.get("blocks"), dict) and package.get("role") in {"video_candidate", "audio", "assembly"}:
            _shot = None
            for _candidate in (contract.get("shots") or []):
                if isinstance(_candidate, dict) and str(_candidate.get("id") or "") == str(shot_id):
                    _shot = _candidate
                    break
            if isinstance(_shot, dict):
                for _key, _value in _shot.items():
                    if _key in {"id", "duration_sec", "description", "shot_kind", "kind", "sound", "risk", "no_dialogue", "generation_duration_sec", "cut_range"} or _key not in CREATIVE_CRAFT_KEYS:
                        continue
                    lowered = _key.lower()
                    if not any(marker in lowered for marker in ("sound", "audio", "voice", "craft")):
                        continue
                    if isinstance(_value, (list, tuple)):
                        _text = "；".join(str(item) for item in _value if str(item).strip())
                    else:
                        _text = str(_value).strip()
                    if _text:
                        _append_block_text(package, "sound", _text)

        # --- constraint delivery ------------------------------------------------
        # A constraint that is declared for the prompt has to land in a prompt
        # block of every role that consumes it. If a consuming role has no
        # matching block, it is reported as pending — never stored and
        # forgotten.
        if isinstance(package.get("blocks"), dict):
            for constraint in constraints:
                if not _constraint_applies(constraint, shot_id):
                    continue
                if constraint.get("delivery") != "prompt":
                    continue
                kind = constraint.get("kind") or "other"
                routing = CONSTRAINT_DELIVERY_BY_KIND.get(kind)
                if not routing:
                    package.setdefault("constraint_evidence", []).append(
                        {
                            "constraint_id": constraint.get("id"),
                            "kind": kind,
                            "delivery": "pending",
                            "block": None,
                            "reason": "unknown constraint kind %r has no delivery route" % kind,
                        }
                    )
                    if "constraint_pending" not in package["unresolved"]:
                        package["unresolved"].append("constraint_pending")
                    continue
                block = routing.get(package.get("role"))
                if not block:
                    # This role is not a consumer of that constraint kind.
                    continue
                if block not in package["blocks"]:
                    package.setdefault("constraint_evidence", []).append(
                        {
                            "constraint_id": constraint.get("id"),
                            "kind": kind,
                            "delivery": "pending",
                            "block": None,
                            "reason": "role %s consumes %s constraints but has no '%s' block"
                            % (package.get("role"), kind, block),
                        }
                    )
                    if "constraint_pending" not in package["unresolved"]:
                        package["unresolved"].append("constraint_pending")
                    continue
                _append_block_text(package, block, constraint.get("text") or "")
                package.setdefault("constraint_evidence", []).append(
                    {
                        "constraint_id": constraint.get("id"),
                        "kind": kind,
                        "delivery": "prompt",
                        "block": block,
                        "source": constraint.get("source"),
                        "locked": constraint.get("locked"),
                    }
                )

        state_blocks, _ = world_state_blocks(world_shots.get(str(shot_id)), role)
        for block, text in state_blocks.items():
            _append_block_text(package, block, text)

        # --- shot-level creative craft directives are handled in _fill_blocks ---

        missing = [name for name in REQUIRED_BLOCKS.get(role, []) if name not in package["blocks"]]
        for name in list(package["blocks"]):
            if not _block_has_content(package["blocks"][name]):
                if name not in missing:
                    missing.append(name)
        package["missing_blocks"] = missing
        if package["unresolved"]:
            package["status"] = "INCOMPLETE"
        else:
            package["status"] = "READY" if not missing else "INCOMPLETE"
        packages.append(package)


    return packages


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("contract")
    parser.add_argument("assets")
    parser.add_argument("graph")
    parser.add_argument("--out")
    args = parser.parse_args()
    with open(args.contract, "r", encoding="utf-8") as handle:
        contract_payload = json.load(handle)
    with open(args.assets, "r", encoding="utf-8") as handle:
        assets = json.load(handle)
    with open(args.graph, "r", encoding="utf-8") as handle:
        graph = json.load(handle)
    contract = contract_payload.get("production_contract", contract_payload)
    packages = compile_prompt_packages(contract, assets, graph)
    text = "\n".join(json.dumps(item, ensure_ascii=False) for item in packages)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + ("\n" if text else ""))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
