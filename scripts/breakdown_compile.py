#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剧本拆解：把一份中文剧本拆成**可对账的资产清单 + 可编译的分镜输入**。

为什么要有它（`script-breakdown-bridge.md`）：本库原先的链是
`01_production_contract → 08`，可 01 是**人写好的计划**。真正卡住人的一步是
"剧本 → 哪些资产、几镜、每镜什么景别"——此前只有 `compile_text_input.py` 的
极简解析（认 `镜头N` 行 + 一份写死的关键词表），中文剧本一进来就只剩段落占位。

本脚本补的就是这一环，且**只做拆解、不做创作**：

  ① 输入：剧本 `.txt`/`.md`（场景标题 + 动作段 + 对白），或外部已结构化好的 JSON。
  ② 输出三件（同一份拆解派生的三个视图，权威是 `10_breakdown.json`）：
     - `10_breakdown.json`  拆解单：scenes / characters / props / shots / camera_tree
                            —— 直接喂 `scripts/asset_manifest.py` 做资产对账（资产要不要出、出几张）
     - `11_compiler_input.json`  编译输入：直接喂 `scripts/compile_production.py` 出 01–08
     - `12_shotlist.md`  人读分镜表：景别/机位/时长/出场/台词/未解
  ③ 纪律：**未解不许编**。文本里没写景别就记 `UNSPECIFIED` 并列进 unresolved；
     没有时长就按总时长均分并标 `DURATION_DERIVED`；台词只许逐字取自剧本（改一个字即 FAIL）。

三方分工（各自只出自己那一份）：
  - 本库：字段口径、资产四层与数量裁决、站序与门禁（唯一权威）。
  - CineCrew：**资产先行**（先建 AssetLibrary 再写镜）+ 景别/角度枚举 + 回修梯度。
  - ViMax：`shot_brief` 字段（idx / is_last / cam_idx / visual_desc / audio_desc）+
    `<角色>` 标记纪律 + 场景→镜头的相机树。

退出码：0 通过 ｜ 1 有 FAIL ｜ 2 用法错误 ｜ 3 没有拆出镜头（≠通过） ｜ 4 只有 WARN

用法：
  python scripts/breakdown_compile.py --script script.md --out out/ [--duration 90] [--aspect 16:9] [--style 写实电影纪录片]
  python scripts/breakdown_compile.py --script script.md --out out/ --json
  python scripts/breakdown_compile.py --self-test
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys

try:
    from .filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN, _tmpdir
except ImportError:
    from filmdsl_bridge import RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN, _tmpdir

FORMAT = "breakdown/v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "breakdown")

SCALE_MAP = [
    (("大特写", "ECU"), ("特写", "CU"), ("中近景", "MCU"), ("近景", "MCU"),
     ("中景", "MS"), ("中全景", "MLS"), ("全景", "LS"), ("远景", "ELS"), ("大远景", "ELS"),
     ("过肩", "OTS"), ("主观", "POV")),
]
SCALE_TABLE = dict(SCALE_MAP[0])
ANGLE_TABLE = {"仰": "low", "俯": "high", "平视": "eye_level", "荷兰": "dutch", "斜": "dutch"}
MOVE_TABLE = {"固定": "static", "静止": "static", "推": "push", "拉": "pull", "摇": "pan",
              "移": "truck", "跟": "follow", "升降": "crane", "手持": "handheld"}
TIME_WORDS = ("清晨", "早晨", "上午", "中午", "下午", "傍晚", "黄昏", "雨夜", "深夜", "夜", "日", "晨")
SPEAKER_BAN = {"镜头", "场景", "道具", "人物", "角色", "时间", "地点", "景别", "机位", "备注",
               "内景", "外景", "音效", "旁白", "字幕", "画外", "画面", "音乐", "标题", "转场",
               "黑场", "淡出", "叠化", "闪回", "字卡", "镜头拉远", "镜头推近", "镜头切换",
               "说明", "注", "结构", "数据", "一句话", "定稿数据", "类型", "篇幅", "写法"}
PARTICLES = "的了着是在和与就都也这那他她它把被给让对从"
NAME_STOP = {"他", "她", "它", "两人", "众人", "男人", "女人", "孩子", "有人", "大家", "老人",
             "镜头", "画面", "门外", "屋里", "手上", "抬头", "低头", "转身", "抬手", "回身",
             "侧身", "俯身", "伸手", "脚步", "目光", "然后", "接着", "同时", "声音", "雨水",
             "冷柜", "玻璃", "门轴", "灯管", "小票", "招牌", "雨棚", "眉骨", "手掌", "手指"}

SCENE_RE = re.compile(r"^\s*(?:场景|场次|SCENE)\s*[一二三四五六七八九十百零0-9]+\s*[：:\s]*(.*)$", re.I)
HEADING_RE = re.compile(r"^\s*(?:(?:内外景|内景|外景|INT|EXT)[\.．]?\s*)(.*)$", re.I)
SHOT_RE = re.compile(r"^\s*(?:镜头|shot)\s*(\d+)\s*[\.、:：\|]?\s*(.*)$", re.I)
NUMBERED_RE = re.compile(r"^\s*(\d+)\s*[\.、\)）]\s*(?![\d])(.*)$")
DIALOGUE_RE = re.compile(r"^\s*([^\s：:（）()]{1,10})\s*(?:[（(][^）)]*[）)])?\s*[：:]\s*(.+)$")
DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s\b|sec)", re.I)
ROSTER_RE = re.compile(r"^\s*(?:人物|角色|出场人物)\s*[：:]\s*(.+)$")
PROP_RE = re.compile(r"^\s*道具\s*[：:]\s*(.+)$")
TAG_RE = re.compile(r"<([^<>\s]{1,10})>")


def _err(code, message, level="fail", **where):
    row = {"code": code, "level": level, "message": message}
    row.update({k: v for k, v in where.items() if v is not None})
    return row


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_json(path, doc):
    _write(path, json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _split_roster(text):
    clean = re.sub(r"[（(][^）)]*[）)]", "", text)  # 先去掉括号里的年龄/身份，免得被当成人名
    parts = re.split(r"[、，,／/；;]\s*", clean)
    names = []
    for part in parts:
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def _scene_meta(title):
    """从场景标题里取 内外景 / 时间。取不到留 None，不猜。"""
    interior = None
    if re.search(r"内外景|INT[\s/]*EXT", title, re.I):
        interior = "INT/EXT"
    elif re.search(r"内景|INT", title, re.I):
        interior = "INT"
    elif re.search(r"外景|EXT", title, re.I):
        interior = "EXT"
    tokens = [t for t in re.split(r"\s+", title.strip()) if t]
    if interior is None and tokens and tokens[-1] in ("内", "外", "内外"):
        interior = {"内": "INT", "外": "EXT", "内外": "INT/EXT"}[tokens[-1]]
    time_of_day = next((w for w in TIME_WORDS if w in title), None)
    return interior, time_of_day


def _plain(line):
    """去掉 markdown 记号（**、__、`）后用于识别的文本；原文另存用于逐字校验。"""
    return re.sub(r"\*\*|__|`", "", line).strip()


def _is_struct(plain):
    return (not plain) or plain in ("---", "***", "___") or plain.startswith("#") \
        or plain.startswith("|") or plain.startswith(">")


def _name_like(token):
    """像人名的短 token：2–6 个汉字，不含虚词/数字/标点。用来挡住 `画面：`/`结构：` 这类假对白。"""
    if not token or len(token) > 6:
        return False
    if not re.fullmatch(r"[\u4e00-\u9fa5·]{2,6}", token):
        return False
    return not any(ch in token for ch in PARTICLES)


def _slug_heading(plain, bold):
    """场景标题：`场景一 …` / `内景 …` / markdown 加粗的剧作 slugline（… 日 外）。"""
    if SCENE_RE.match(plain) or HEADING_RE.match(plain):
        return True
    if not bold:
        return False
    tokens = plain.split()
    if tokens and tokens[-1] in ("内", "外", "内外", "INT", "EXT"):
        return True
    if re.match(r"^(?:序幕|尾声|第[一二三四五六七八九十0-9]+幕)", plain):
        return len(tokens) >= 2
    return bool(re.match(r"^\d+\s*[-—–]\s*\d+\s", plain))


def parse_screenplay(text, title=None):
    """剧本 → 拆解单（未校验）。纯文本解析，不联网、不调模型。

    认的版式（真实剧本里三种并存）：
      · 场景标题：`场景一 …`、`内景 日 客厅`、markdown 加粗的 `**1-1 港口 日 外**`
      · 人物表：`人物：A、B` 一行式，或 `**人物**` + `- **周正华（老周）**，41岁…` 列表式
      · 对白：`名字：台词`（含 `**名字**：台词`，括号里的情绪词允许）
    前导信息（标题/类型/人物/场景说明）**不成镜**；只有场景标题之后才切镜。
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    script_lines, scenes, characters, props, shots = [], [], [], [], []
    aliases = {}
    current_scene, current = None, None
    in_roster = in_props = False
    heading_mode = any(
        _slug_heading(_plain(ln), ln.strip().startswith("**") and ln.strip().endswith("**"))
        for ln in lines if ln.strip() and not _is_struct(_plain(ln)))
    heading_seen = False
    paragraph_mode = not any(re.match(r"^\s*(?:\*\*)?\s*(?:镜头|shot)\s*\d+", ln, re.I) for ln in lines)

    def resolve(name):
        cid = aliases.get(name)
        if not cid:
            return None
        return next((c for c in characters if c["id"] == cid), None)

    def add_character(name, declared, extra_aliases=()):
        name = (name or "").strip()
        if not name:
            return None
        existing = resolve(name)
        if existing:
            for alias in (name,) + tuple(extra_aliases):
                aliases.setdefault(alias, existing["id"])
            if declared:
                existing["declared"] = True
            return existing
        cid = "char_%02d" % (len(characters) + 1)
        row = {"id": cid, "name": name, "declared": bool(declared),
               "aliases": list(dict.fromkeys([name] + [a for a in extra_aliases if a])),
               "states": [], "base_state": "基准"}
        characters.append(row)
        for alias in row["aliases"]:
            aliases[alias] = cid
        return row

    def new_scene(slug):
        nonlocal current_scene
        interior, tod = _scene_meta(slug)
        sid = "loc_%02d" % (len(scenes) + 1)
        current_scene = {"id": sid, "name": slug.strip() or "未命名场景",
                         "type": interior or "UNKNOWN", "time_of_day": tod,
                         "slug": slug.strip(), "shots": []}
        scenes.append(current_scene)
        return current_scene

    def new_shot(desc, source_line):
        nonlocal current
        sid = "shot_%02d" % (len(shots) + 1)
        current = {
            "id": sid,
            "scene": current_scene["id"] if current_scene else None,
            "description": desc.strip(),
            "scale": None, "camera": None, "angle": None,
            "duration_sec": None,
            "characters": [], "props": [],
            "dialogue": {"has_dialogue": False, "speaker_id": None, "speaker_name": None, "text": None},
            "dialogues": [],
            "shot_kind": "empty",
            "source_line": source_line,
            "unresolved": [],
        }
        shots.append(current)
        if current_scene:
            current_scene["shots"].append(sid)
        return current

    def drop_empty_current():
        nonlocal current
        if current is not None and not current["description"].strip() and not current["dialogue"]["has_dialogue"]:
            if current in shots:
                shots.remove(current)
            if current_scene and current["id"] in current_scene["shots"]:
                current_scene["shots"].remove(current["id"])
            current = None

    if not heading_mode:
        new_scene("未命名场景")
        heading_seen = True

    for idx, line in enumerate(lines, 1):
        raw = line.strip()
        plain = _plain(raw)
        if not _is_struct(plain):
            script_lines.append({"line": idx, "text": plain})
        if not plain:
            if paragraph_mode and heading_seen and not in_roster and not in_props:
                current = None
            continue

        if plain in ("人物", "角色", "出场人物"):
            in_roster, in_props = True, False
            continue
        if plain in ("道具", "道具表", "关键道具"):
            in_props, in_roster = True, False
            continue
        inline_roster = ROSTER_RE.match(plain)
        if inline_roster:
            for name in _split_roster(inline_roster.group(1)):
                add_character(name, True)
            continue
        inline_props = PROP_RE.match(plain)
        if inline_props:
            for name in _split_roster(inline_props.group(1)):
                if name not in [p["name"] for p in props]:
                    props.append({"id": "prop_%02d" % (len(props) + 1), "name": name, "evidence": True})
            continue
        if in_roster:
            if raw.startswith("-") or raw.startswith("•"):
                item = raw.lstrip("-• \t")
                mark = re.match(r"^\*\*(.+?)\*\*", item)
                label = mark.group(1) if mark else re.split(r"[，,。]", item)[0]
                primary = re.split(r"[（(]", label)[0].strip()
                alias_names = []
                for part in re.findall(r"[（(]([^）)]*)[）)]", label):
                    alias_names += _split_roster(part)
                if "·" in primary:
                    alias_names.append(primary.split("·")[0])
                add_character(primary, True, alias_names)
                continue
            in_roster = False
        if in_props:
            if raw.startswith("-") or raw.startswith("•"):
                item = raw.lstrip("-• \t")
                mark = re.match(r"^\*\*(.+?)\*\*", item)
                label = mark.group(1) if mark else re.split(r"[，,。：:]", item)[0]
                for name in _split_roster(label):
                    if name not in [p["name"] for p in props]:
                        props.append({"id": "prop_%02d" % (len(props) + 1), "name": name, "evidence": True})
                continue
            in_props = False

        bold = raw.startswith("**") and raw.endswith("**")
        if _slug_heading(plain, bold):
            drop_empty_current()
            current = None
            new_scene(plain)
            heading_seen = True
            continue

        shot_hit = SHOT_RE.match(plain)
        if not shot_hit and paragraph_mode and heading_mode and NUMBERED_RE.match(plain) and len(plain) > 6:
            shot_hit = NUMBERED_RE.match(plain)
        if shot_hit:
            body = shot_hit.group(2) if (shot_hit.lastindex or 0) >= 2 else ""
            drop_empty_current()
            new_shot(body, idx)
            continue

        dialogue = DIALOGUE_RE.match(plain)
        speaker = line_text = None
        accepted = False
        if dialogue and heading_seen:
            speaker = dialogue.group(1).strip()
            line_text = dialogue.group(2).strip()
            accepted = speaker not in SPEAKER_BAN and (resolve(speaker) is not None or _name_like(speaker))
        if accepted:
            host = current
            if host is None and current_scene and current_scene["shots"]:
                cand = next((x for x in shots if x["id"] == current_scene["shots"][-1]), None)
                if cand is not None and cand["description"].strip() and not cand["dialogue"]["has_dialogue"]:
                    host = cand
            if host is None:
                host = new_shot("", idx)
            current = host
            char = add_character(speaker, False)
            current["dialogue"] = {"has_dialogue": True, "speaker_id": char["id"],
                                   "speaker_name": char["name"], "text": line_text}
            current["dialogues"].append(current["dialogue"])
            current["shot_kind"] = "dialogue"
            if char["id"] not in current["characters"]:
                current["characters"].append(char["id"])
            continue

        if not heading_seen:
            continue
        if current is None:
            new_shot(plain, idx)
        else:
            current["description"] = (current["description"] + " " + plain).strip()

    drop_empty_current()
    for shot in shots:
        _enrich_shot(shot, characters, props)

    doc = {
        "format": FORMAT,
        "title": title or "未命名项目",
        "detect": {"heading_mode": heading_mode, "paragraph_mode": paragraph_mode},
        "scenes": [{"id": s["id"], "name": s["name"], "slug": s["slug"], "type": s["type"],
                    "time_of_day": s["time_of_day"], "shots": s["shots"]} for s in scenes],
        "characters": characters,
        "props": props,
        "shots": shots,
        "script_lines": script_lines,
        "camera_tree": _camera_tree(scenes, shots),
        "assumptions": [],
        "unresolved": [],
    }
    if paragraph_mode:
        doc["assumptions"].append("SHOT_SPLIT_FROM_PARAGRAPH：剧本无 `镜头N` 标记，按段落切镜；镜数须人核")
    if not heading_mode:
        doc["assumptions"].append("NO_SCENE_HEADINGS：没有场景标题，全部落在一个未命名场景")
    return doc


def _enrich_shot(shot, characters, props):
    text = shot["description"]
    for word, scale in SCALE_TABLE.items():
        if word in text:
            shot["scale"] = scale
            break
    for word, angle in ANGLE_TABLE.items():
        if word in text:
            shot["angle"] = angle
            break
    for word, move in MOVE_TABLE.items():
        if word in text:
            shot["camera"] = move
            break
    if shot["scale"] is None:
        shot["unresolved"].append("scale：文本未写景别")
    if shot["camera"] is None:
        shot["unresolved"].append("camera：文本未写机位运动")
    dur = DURATION_RE.search(text)
    if dur:
        shot["duration_sec"] = float(dur.group(1))
    tagged = [t for t in TAG_RE.findall(text)]
    for name in tagged:
        char = next((c for c in characters if c["name"] == name), None)
        if char is None:
            char = {"id": "char_%02d" % (len(characters) + 1), "name": name, "declared": False,
                    "states": [], "base_state": "基准"}
            characters.append(char)
        if char["id"] not in shot["characters"]:
            shot["characters"].append(char["id"])
    for char in characters:
        if char["name"] and char["name"] in text and char["id"] not in shot["characters"]:
            shot["characters"].append(char["id"])
    for prop in props:
        if prop["name"] and prop["name"] in text and prop["id"] not in shot["props"]:
            shot["props"].append(prop["id"])
    if shot["characters"] or shot["dialogue"]["has_dialogue"]:
        shot["shot_kind"] = "character" if shot["characters"] else shot["shot_kind"]
    shot["scale"] = shot["scale"] or "UNSPECIFIED"
    shot["camera"] = shot["camera"] or "UNSPECIFIED"
    shot["angle"] = shot["angle"] or "UNSPECIFIED"
    shot["feed_plan"] = _feed_plan(shot)


def _feed_plan(shot):
    """站 5.5 的参考计划草案：本镜该挂哪几张、各担什么职责（≤4 张）。"""
    scale = shot["scale"]
    entries = []
    if shot.get("scene"):
        entries.append({"asset_id": shot["scene"], "role": "view", "why": "场景层：本镜所在空间"})
    for cid in shot["characters"][:2]:
        role = "face" if scale in ("CU", "ECU", "MCU") else "body"
        entries.append({"asset_id": cid, "role": role, "why": "身份锚点：%s" % ("脸" if role == "face" else "全身")})
    for pid in shot["props"][:2]:
        role = "closeup" if scale in ("CU", "ECU") else "anchor"
        entries.append({"asset_id": pid, "role": role, "why": "道具：%s" % ("近距版" if role == "closeup" else "主图")})
    return entries[:4]


def _camera_tree(scenes, shots):
    """ViMax 的相机树：场景为父，镜为子，标 cam_idx 与 is_last。"""
    tree = []
    for scene in scenes:
        children = []
        for order, sid in enumerate(scene["shots"], 1):
            shot = next((s for s in shots if s["id"] == sid), None)
            if not shot:
                continue
            children.append({"shot_id": sid, "cam_idx": 0, "order": order,
                             "is_last": order == len(scene["shots"])})
        tree.append({"scene_id": scene["id"], "scene": scene["name"], "shots": children})
    return tree


def _dialogue_rows(shot):
    """Ordered spoken lines; legacy documents provide a single dialogue object."""
    rows = shot.get("dialogues")
    return rows if isinstance(rows, list) and rows else [shot["dialogue"]]


def validate(doc, script_text, brief=None):
    brief = brief or {}
    violations = []
    if not doc.get("shots"):
        return [_err("SHOTS_EMPTY", "没有拆出任何镜头：没拆出来 ≠ 没有内容，先查场景标题与镜头标记", level="empty")]

    ids = [s["id"] for s in doc["shots"]]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        violations.append(_err("DUPLICATE_SHOT_ID", "镜号重复：%s" % sorted(dup)))

    char_ids = {c["id"] for c in doc["characters"]}
    prop_ids = {p["id"] for p in doc["props"]}
    if not char_ids:
        violations.append(_err("CHARACTERS_NONE", "一个角色都没识别到：剧本里没有人物行也没有对白说话人", level="warn"))
    if not prop_ids:
        violations.append(_err("PROPS_NONE", "没有道具行：道具只能由人显式给出，脚本不替你猜", level="warn"))
    if all(s["scene"] is None for s in doc["shots"]) or all(
            sc["name"] == "未命名场景" for sc in doc["scenes"]):
        violations.append(_err("NO_SCENE_HEADINGS", "没有场景标题：全部落在同一个未命名场景", level="warn"))

    total = 0.0
    unspecified = []
    for shot in doc["shots"]:
        if not shot["description"].strip() and not shot["dialogue"]["has_dialogue"]:
            violations.append(_err("SHOT_WITHOUT_ACTION", "镜头 %s 既无动作描述也无对白" % shot["id"], where=shot["id"]))
        for cid in shot["characters"]:
            if cid not in char_ids:
                violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 引用了不存在的角色 %s" % (shot["id"], cid), where=shot["id"]))
        for pid in shot["props"]:
            if pid not in prop_ids:
                violations.append(_err("UNRESOLVED_ASSET", "镜头 %s 引用了不存在的道具 %s" % (shot["id"], pid), where=shot["id"]))
        for dlg in _dialogue_rows(shot):
            if dlg["has_dialogue"]:
                if not dlg.get("speaker_id") or not dlg.get("text"):
                    violations.append(_err("DIALOGUE_SPEAKER_MISSING", "镜头 %s 有对白但缺说话人或台词" % shot["id"], where=shot["id"]))
                elif dlg["text"] and dlg["text"] not in script_text:
                    violations.append(_err("DIALOGUE_NOT_VERBATIM", "镜头 %s 的台词不是剧本原文（改写过）：%r" % (shot["id"], dlg["text"][:24]), where=shot["id"]))
        if shot["scale"] == "UNSPECIFIED":
            unspecified.append(shot["id"])
        if shot["duration_sec"]:
            total += float(shot["duration_sec"])

    if unspecified:
        sample = "、".join(unspecified[:6]) + ("…" if len(unspecified) > 6 else "")
        violations.append(_err("CAMERA_UNSPECIFIED",
                               "%d 镜未写景别（%s）：已记 UNSPECIFIED 并列进各镜 unresolved，站 6 补" % (len(unspecified), sample),
                               level="warn", where=",".join(unspecified[:6])))

    for scene in doc["scenes"]:
        if not scene["shots"]:
            violations.append(_err("SCENE_EMPTY", "场景 %s 没有镜头" % scene["name"], level="warn", where=scene["id"]))

    target = brief.get("duration_sec")
    if target:
        if total and abs(total - float(target)) > max(2.0, float(target) * 0.2):
            violations.append(_err("DURATION_SUM_MISMATCH", "镜头时长合计 %.1fs 与目标 %ss 相差过大" % (total, target), level="warn"))
        if total == 0:
            violations.append(_err("DURATION_MISSING", "全片没有标时长：需按目标时长均分或补写", level="warn"))

    for char in doc["characters"]:
        if not char.get("declared"):
            violations.append(_err(
                "ENTITY_CANDIDATE",
                "「%s」说过话但不在人物表里：先确认是同一个人还是漏登，确认后再补进人物表" % char["name"],
                level="warn", where=char["id"]))
    return violations


def apply_brief(doc, brief):
    """时长/画幅/风格只进 doc 头，不改成片事实；缺时长的镜按剩余时长均分并标假设。"""
    target = brief.get("duration_sec")
    if not target:
        return doc
    missing = [s for s in doc["shots"] if not s["duration_sec"]]
    known = sum(float(s["duration_sec"]) for s in doc["shots"] if s["duration_sec"])
    if missing and known < float(target):
        share = round((float(target) - known) / len(missing), 2)
        for shot in missing:
            shot["duration_sec"] = share
            shot["unresolved"].append("duration：按目标时长均分 %.2fs，须人核" % share)
        doc["assumptions"].append("DURATION_DERIVED：%d 镜缺时长，按目标 %ss 均分" % (len(missing), target))
    doc["brief"] = dict(brief)
    return doc


def to_compiler_input(doc, goal=None, asset_spec=None):
    """拆解单 → compile_production 的简单输入（形状对齐 compile_text_input.parse_text_input）。

    `asset_spec` 是站 5 的接口：`{"char_01": "描述"}` 或 `{"林": {"description": "…"}}`。
    没有描述的资产**不编**——编译门禁会停在 PROMPT_UNRESOLVED，这是站 5 该补的活。
    """
    spec = asset_spec or {}

    def _desc(asset_id, name):
        for key in (asset_id, name):
            if key in spec:
                val = spec[key]
                if isinstance(val, dict):
                    return val.get("description")
                return val
        return None

    entities = []
    for char in doc["characters"]:
        entities.append({"id": char["id"], "kind": "character", "name": char["name"],
                         "description": _desc(char["id"], char["name"]), "inferred_keywords": [],
                         "shared": True,
                         "identity_status": "declared_in_script", "reuse_count": 1,
                         "state_versions": 1, "needs_confirmation": char.get("declared") is not True})
    for scene in doc["scenes"]:
        entities.append({"id": scene["id"], "kind": "scene", "name": scene["name"],
                         "description": _desc(scene["id"], scene["name"]), "inferred_keywords": [],
                         "shared": True,
                         "identity_status": "declared_in_script", "reuse_count": 1,
                         "state_versions": 1, "needs_confirmation": False})
    for prop in doc["props"]:
        entities.append({"id": prop["id"], "kind": "prop", "name": prop["name"],
                         "description": _desc(prop["id"], prop["name"]), "inferred_keywords": [],
                         "shared": True,
                         "identity_status": "declared_in_script", "reuse_count": 1,
                         "state_versions": 1, "needs_confirmation": True})
    shots = []
    for shot in doc["shots"]:
        desc = shot["description"].strip()
        spoken = ["%s：%s" % (dlg.get("speaker_name") or dlg.get("speaker_id"), dlg["text"])
                  for dlg in _dialogue_rows(shot) if dlg.get("has_dialogue")]
        if spoken:
            desc = ("%s 对白：%s" % (desc, "\n".join(spoken))).strip()
        row = {"id": shot["id"], "description": desc or "未命名镜头", "risk": "medium"}
        row["camera"] = {key: value for key, value in (
            ("shot_scale", shot.get("scale")), ("movement", shot.get("camera")),
            ("angle", shot.get("angle"))) if value not in (None, "", "UNSPECIFIED")}
        subjects = list(dict.fromkeys(shot["characters"] + [shot.get("scene")] + shot["props"]))
        row["asset_refs"] = [{"entity_id": subject, "version": 1} for subject in subjects if subject]
        if shot.get("duration_sec"):
            row["duration_sec"] = float(shot["duration_sec"])
        shots.append(row)
    brief = doc.get("brief") or {}
    duration = brief.get("duration_sec") or sum(float(s.get("duration_sec") or 0) for s in shots) or 120
    payload = {
        "goal": goal or doc.get("title") or "未命名生产目标",
        "duration_sec": int(round(float(duration))),
        "entities": entities,
        "shots": shots,
        "production_mode": "production_build",
        "delivery": {"ignition_allowed": False},
    }
    if brief.get("aspect_ratio"):
        payload["aspect_ratio"] = brief["aspect_ratio"]
    if brief.get("visual_style"):
        payload["visual_style"] = brief["visual_style"]
    return payload


def to_shotlist_md(doc):
    names = {c["id"]: c["name"] for c in doc["characters"]}
    props = {p["id"]: p["name"] for p in doc["props"]}
    scenes = {s["id"]: s["name"] for s in doc["scenes"]}
    lines = ["# 分镜表（拆解派生 · 非终稿）", "",
             "| 镜号 | 场景 | 景别 | 机位 | 时长 | 出场 | 道具 | 台词 | 未解 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for shot in doc["shots"]:
        cast = "、".join(names.get(c, c) for c in shot["characters"]) or "—"
        pr = "、".join(props.get(p, p) for p in shot["props"]) or "—"
        dlg = " / ".join("%s：%s" % (row.get("speaker_name") or row.get("speaker_id"), row["text"])
                         for row in _dialogue_rows(shot) if row.get("has_dialogue")) or "—"
        dur = ("%.1fs" % shot["duration_sec"]) if shot.get("duration_sec") else "—"
        unresolved = "；".join(shot["unresolved"]) or "—"
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            shot["id"], scenes.get(shot["scene"], shot["scene"] or "—"), shot["scale"],
            shot["camera"], dur, cast, pr, (dlg or "—").replace("|", "／"), unresolved))
    lines += ["", "> 本表由 `scripts/breakdown_compile.py` 从剧本拆解派生；景别/机位写 `UNSPECIFIED` 的镜必须在站 6 补。",
              "> 台词逐字取自剧本，改字会触发 `DIALOGUE_NOT_VERBATIM`。"]
    return "\n".join(lines) + "\n"


def _summary(violations):
    fails = [v for v in violations if v["level"] == "fail"]
    warns = [v for v in violations if v["level"] == "warn"]
    empty = [v for v in violations if v["level"] == "empty"]
    for v in violations:
        print("[%s] %-28s %s" % (v["level"].upper(), v["code"], v["message"]))
    print("合计：%d FAIL / %d WARN / %d EMPTY" % (len(fails), len(warns), len(empty)))
    if empty and not fails:
        return RC_EMPTY
    if fails:
        return RC_FAIL
    return RC_WARN if warns else RC_OK


def run(script_path, out_dir, duration=None, aspect=None, style=None, title=None, goal=None,
        echo=False, asset_spec_path=None):
    if not os.path.isfile(script_path):
        print("找不到剧本：%s" % script_path)
        return RC_USAGE
    text = _read(script_path)
    if not text.strip():
        print("[FAIL] SCRIPT_EMPTY 剧本是空的")
        return RC_USAGE
    asset_spec = {}
    if asset_spec_path:
        if not os.path.isfile(asset_spec_path):
            print("找不到资产描述文件：%s" % asset_spec_path)
            return RC_USAGE
        with io.open(asset_spec_path, encoding="utf-8") as f:
            asset_spec = json.load(f)
    brief = {}
    if duration:
        brief["duration_sec"] = float(duration)
    if aspect:
        brief["aspect_ratio"] = aspect
    if style:
        brief["visual_style"] = style
    doc = parse_screenplay(text, title=title or os.path.splitext(os.path.basename(script_path))[0])
    doc["source"] = {"script": os.path.abspath(script_path),
                     "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     "chars": len(text)}
    doc = apply_brief(doc, brief)
    violations = validate(doc, text, brief)
    doc["codes"] = sorted({v["code"] for v in violations})
    doc["unresolved"] = sorted({u for s in doc["shots"] for u in s["unresolved"]})

    os.makedirs(out_dir, exist_ok=True)
    payload = to_compiler_input(doc, goal, asset_spec)
    described = len([e for e in payload["entities"] if e.get("description")])
    doc["asset_spec_coverage"] = {"entities": len(payload["entities"]), "described": described}
    _write_json(os.path.join(out_dir, "10_breakdown.json"), doc)
    _write_json(os.path.join(out_dir, "11_compiler_input.json"), payload)
    _write(os.path.join(out_dir, "12_shotlist.md"), to_shotlist_md(doc))
    if echo:
        print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True))
    print("拆解单：%s" % os.path.join(os.path.abspath(out_dir), "10_breakdown.json"))
    print("编译输入：%s → 交给 scripts/compile_production.py" % os.path.join(os.path.abspath(out_dir), "11_compiler_input.json"))
    print("资产对账：交给 scripts/asset_manifest.py（%d 角色 / %d 道具 / %d 场景 / %d 镜）"
          % (len(doc["characters"]), len(doc["props"]), len(doc["scenes"]), len(doc["shots"])))
    print("资产描述：%d/%d 已给（没给的会在编译门禁 PROMPT_UNRESOLVED 处停下，那是站 5 的活）"
          % (described, len(payload["entities"])))
    return _summary(violations)


def _load_cases():
    with io.open(os.path.join(FIXTURES, "cases.json"), encoding="utf-8") as f:
        doc = json.load(f)
    return doc["cases"] if isinstance(doc, dict) else doc


def _codes(violations):
    return sorted({v["code"] for v in violations})


def self_test():
    cases = _load_cases()
    bad = 0
    tmp = _tmpdir(prefix="breakdown_")
    try:
        for case in cases:
            script = os.path.join(FIXTURES, case["script"])
            if not os.path.isfile(script):
                print("[FAIL] %-24s fixtures 缺 %s" % (case["name"], case["script"]))
                bad += 1
                continue
            text = _read(script)
            brief = {"duration_sec": float(case["duration"])} if case.get("duration") else {}
            doc = apply_brief(parse_screenplay(text, title=case["name"]), brief)
            violations = validate(doc, text, brief)
            mutation = case.get("mutation")
            if mutation == "duplicate_shot_id":
                doc["shots"].append(dict(doc["shots"][0]))
                violations = validate(doc, text, brief)
            elif mutation == "dialogue_altered":
                for shot in doc["shots"]:
                    if shot["dialogue"]["has_dialogue"]:
                        shot["dialogue"]["text"] = shot["dialogue"]["text"] + "（改）"
                        break
                violations = validate(doc, text, brief)
            elif mutation == "unresolved_asset":
                doc["shots"][0]["characters"].append("char_99")
                violations = validate(doc, text, brief)
            got = _codes(violations)
            want = sorted(set(case.get("expected_codes") or []))
            if got != want:
                bad += 1
                print("[FAIL] %-24s expected=%s got=%s" % (case["name"], want, got))
            else:
                print("[PASS] %-24s %s" % (case["name"], got or "-"))
        # 结构断言：编译输入可被 compile_production 读、拆解单可被 asset_manifest 读
        text = _read(os.path.join(FIXTURES, "cn_three_scenes.txt"))
        doc = apply_brief(parse_screenplay(text, title="结构用例"), {"duration_sec": 15})
        payload = to_compiler_input(doc, "结构用例")
        with io.open(os.path.join(FIXTURES, "asset_spec.json"), encoding="utf-8") as f:
            spec = json.load(f)
        payload_spec = to_compiler_input(doc, "结构用例", spec)
        checks = [
            ("编译输入含 shots/entities", bool(payload["shots"]) and bool(payload["entities"])),
            ("编译输入不含执行许可", payload["delivery"]["ignition_allowed"] is False),
            ("拆解单镜头都有 scene", all(s["scene"] for s in doc["shots"])),
            ("拆解单有相机树", bool(doc["camera_tree"])),
            ("分镜表含表头", "| 镜号 |" in to_shotlist_md(doc)),
            ("参考计划 ≤4 张/镜", all(len(s["feed_plan"]) <= 4 for s in doc["shots"])),
            ("资产描述可按 id 注入",
             all(e["description"] for e in payload_spec["entities"] if e["kind"] in ("character", "scene"))),
        ]
        for label, ok in checks:
            if not ok:
                bad += 1
                print("[FAIL] %s" % label)
            else:
                print("[PASS] %s" % label)
        total = len(cases) + len(checks)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("自检：%d 项，%d 失败" % (total, bad))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="剧本拆解（script-breakdown-bridge.md）")
    ap.add_argument("--script")
    ap.add_argument("--out")
    ap.add_argument("--duration", type=float, help="成片目标时长（秒），用于时长均分与差值预警")
    ap.add_argument("--aspect", help="画幅，如 16:9 / 2.39:1")
    ap.add_argument("--style", help="风格编号或写实描述，原样传给编译输入")
    ap.add_argument("--asset-spec", help="站 5 的资产描述表（JSON：id/名称 → 描述），补齐后编译门禁才可能全绿")
    ap.add_argument("--title")
    ap.add_argument("--goal")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.script or not args.out:
        ap.print_help()
        return RC_USAGE
    return run(args.script, args.out, args.duration, args.aspect, args.style,
               args.title, args.goal, args.json, args.asset_spec)


if __name__ == "__main__":
    sys.exit(main())
