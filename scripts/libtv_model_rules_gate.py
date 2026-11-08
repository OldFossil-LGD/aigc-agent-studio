#!/usr/bin/env python3
"""Gate a LibTV model schema before spending a round-trip.

Three layers, all replicating client-side code read from LibTV's own bundles:

  ranges   properties.modeType.items[modeType] = [min, max], plus
           config.excludeModeTypes            (module 469850)
  configs  mixed2videoConfig / videoEdit2videoConfig tightenings
                                              (module 469850)
  rules    the per-model rules array          (module 61637, chunk
           `16epsx7bp027x.js`, 33,094 bytes, SHA-256
           `d2c655635d566fe74c69dc74c3935b142996ba8540b51a590a588c93393a734d`)

`mediaConstraints` is implemented offline when caller supplies material attributes
(duration, format, height, etc.); platform aggregation semantics remain unverified.

The ranges and configs layers only run when material counts are supplied, so a
caller that passes only `--has-*` gets exactly the old rules-only behaviour.

Input is the JSON printed by the read-only command `libtv model <modelKey>`.
No LibTV call is made here and nothing is generated.

Rule shape: { require, mode = "all", forModeTypes, whenHas, message, messageI18nKey }
  require       one or more of prompt | image | video | audio | media
  mode          "any" = at least one satisfied, "all" (or omitted) = every one
  forModeTypes  when non-empty and a modeType is supplied that is not listed,
                the rule does not apply and passes
  whenHas       when non-empty and not every listed kind is present, the rule
                does not apply and passes

Exit codes: 0 can generate · 1 blocked (a layer failed) · 2 usage
            3 not_verified (no layer had anything to judge) · 4 no schema read
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_NOSCHEMA = 0, 1, 2, 3, 4

KINDS = ("prompt", "image", "video", "audio", "media")

# 默认规则表（模块 821992 导出 f 逐字）。节点**没带 rules** 时用它。
DEFAULT_RULES = {
    "video": [{"require": ["prompt", "media"], "mode": "any"},
              {"require": ["prompt"], "forModeTypes": ["text2video"]}],
    "image": [{"require": ["prompt", "media"], "mode": "any"}],
    "text": [{"require": ["prompt"]}],
    "audio": [{"require": ["prompt"]}],
    "enhanceVideo": [{"require": ["media"]}],
    "enhanceImage": [{"require": ["media"]}],
}

# 模块 838978 顶部那三个正则（逐字）。
RE_CAMERA_PRESET = re.compile(r"\{\{CameraPreset\s+\d+\}\}")
RE_PANORAMA720 = re.compile(r"\{\{Panorama720\}\}")
RE_SLASH_PRESET = re.compile(r"\{\{SlashPreset:[^}]+\}\}")
# 模块 469850 导出 U：只有这两个 modeType 走 X。
X_MODE_TYPES = ("frames2video", "videoEdit2video")


def normalize_prompt(prompt: Any, mode_type: str | None) -> str:
    """模块 838978 的 `X` / `F` / `b` 逐字复刻（报告 77）。

    `frames2video` / `videoEdit2video` 走 `X`：删 CameraPreset + Panorama720 + SlashPreset，只 trim；
    其余走 `b(F(...))`：删 SlashPreset + Panorama720，并把 `[ \\t]+` 压成单空格。
    **插桩（`{{Image N}}` / `{{Mixed N}}` / `{{magic:…}}`）一律不删**——
    所以"只写插桩"也算写了提示词。
    """
    text = prompt if isinstance(prompt, str) else ""
    if mode_type in X_MODE_TYPES:
        out = RE_CAMERA_PRESET.sub("", text)
        out = RE_PANORAMA720.sub("", out)
        out = RE_SLASH_PRESET.sub("", out)
        return out.strip()
    f = re.sub(r"[ \t]+", " ", RE_PANORAMA720.sub("", text)).strip()
    return re.sub(r"[ \t]+", " ", RE_SLASH_PRESET.sub("", f)).strip()


def normalize_text_content(value: Any) -> list[str]:
    """`normalizeTextContentField`（孪生版 `S`）的复刻。

    `collectIncomingNodeData` 的 TEXT 分支收的是 `{nodeId, content: S(e.content)}`——
    **`content` 一律是"字符串数组"**：字符串包成单元素数组、空串给 `[]`、数组只留字符串项。
    """
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str)]
    return []


def clean_rules(rules: Any) -> list[dict[str, Any]]:
    """模块 503357 导出 f 的逐字复刻：**清洗 + 归一化**，不是"按模型过滤"。

    客户端原函数收 `(rules, model)`，但 `model` 被内层循环变量遮蔽、**一次都没读**。
    它实际做的是：丢非对象项 · 丢 `require` 非数组或为空 · `require` 只留五种合法 kind ·
    `mode` 非 `"any"` 一律变 `"all"` · `forModeTypes` 只留数组 · `whenHas` 只留合法 kind ·
    `message` / `messageI18nKey` 只留字符串。
    """
    if rules is None or not isinstance(rules, list):
        return []
    out: list[dict[str, Any]] = []
    for item in rules:
        if not isinstance(item, dict):
            continue
        require = item.get("require")
        if not isinstance(require, list) or not require:
            continue
        kept = [k for k in require if isinstance(k, str) and k in KINDS]
        if not kept:
            continue
        mode = item.get("mode")
        when_has = item.get("whenHas")
        kept_when = None
        if when_has is not None and isinstance(when_has, list):
            filtered = [k for k in when_has if isinstance(k, str) and k in KINDS]
            kept_when = filtered or None
        for_mode = item.get("forModeTypes")
        out.append({
            "require": kept,
            "mode": "any" if mode == "any" else "all",
            "forModeTypes": for_mode if isinstance(for_mode, list) else None,
            "whenHas": kept_when,
            "message": item.get("message") if isinstance(item.get("message"), str) else None,
            "messageI18nKey": item.get("messageI18nKey")
            if isinstance(item.get("messageI18nKey"), str) else None,
        })
    return out


# i18n values read from LibTV's shipped `common` namespace.
KIND_LABEL = {
    "prompt": "提示词",
    "image": "参考图片",
    "video": "参考视频",
    "audio": "参考音频",
    "media": "参考素材",
}

# modeType -> label, using the mapping table the validator itself uses.
MODE_TYPE_LABEL = {
    "text2video": "文生视频",
    "singleImage2video": "图生视频",
    "frames2video": "首尾帧",
    "image2video": "图片参考",
    "video2video": "视频参考",
    "videoEdit2video": "视频编辑",
    "audio2video": "音频驱动",
    "mixed2video": "全能参考",
    "text2image": "文生图",
    "image2image": "图生图",
}

# modeType -> which material list it consumes (module 469850's catalogue).
LIST_KEY_BY_MODE_TYPE = {
    "text2video": None,
    "singleImage2video": "imageList",
    "frames2video": "imageList",
    "image2video": "imageList",
    "video2video": "videoList",
    "videoEdit2video": "videoList",
    "audio2video": "audioList",
    "mixed2video": "mixedList",
    "videoExtend2video": "mixedList",
    "longVideo2video": "mixedList",
    # ★ 2026-10-16 补（报告 81）：**图生图按 `imageList` 数**——
    #   CLI 载荷的图片入边门 `imageGeneratorReferenceCountViolationMessage` 读的就是
    #   `collectIncomingNodeDataCli(incomingNodes).imageList.length`，再拿它比 `items.image2image` 的区间。
    #   **补之前这两个键缺席 ⟹ 图类模型的区间层恒按 0 张判**（`qwen-image-3 [1,3]` 会被误拦）。
    "text2image": None,
    "image2image": "imageList",
}

MIXED_LIST_PROTOCOL = {"mixed2video", "longVideo2video", "videoExtend2video"}
SEEDANCE_25_KEYS = ("star-video2.5", "star-video2.5-draft")

LIST_KIND = {"imageList": "image", "videoList": "video", "audioList": "audio"}
LIST_LABEL = {"imageList": "参考图片", "videoList": "参考视频",
              "audioList": "参考音频", "mixedList": "参考素材"}

T_NEED_CONNECT = "需要连接{mediaLabel}节点（{rangeText}个）"
T_COUNT_MISMATCH = "当前{mediaLabel}数量 {count} 个，需要 {rangeText} 个"
T_TEXT2VIDEO_MEDIA = "已连接媒体输入，无法使用纯文生视频"
T_VIDEO_MAX = "视频最多 {max} 个，当前 {count} 个"
T_IMAGE_MAX = "图片最多 {max} 个，当前 {count} 个"
T_IMAGE_MAX_WITH_VIDEO = "有视频时，图片最多 {max} 个，当前 {count} 个"
T_AUDIO_MAX = "音频最多 {max} 个，当前 {count} 个"


def _range_text(lo: int, hi: int) -> str:
    """客户端原样：lo==hi 或 lo==0 时只写上限，否则写 lo~hi。"""
    return "%d" % hi if (lo == hi or lo == 0) else "%d~%d" % (lo, hi)


def _is_seedance_25(schema: dict[str, Any]) -> bool:
    key = schema.get("modelKey") or ""
    vendor = schema.get("modelVendor") or ""
    return key in SEEDANCE_25_KEYS or vendor == "star-video2.5"


def _ext(url: str) -> str:
    """客户端同款：取 pathname 最后一段的扩展名，小写。"""
    tail = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[-1].lower() if "." in tail else ""


MATERIAL_LIST_BY_TYPE = {
    "text": "textList",
    "image": "imageList",
    "video": "videoList",
    "audio": "audioList",
}

GROUP_TYPES = ("group", "video_group", "video-story")
GROUP_EXPAND_DEPTH_CAP = 8


def _is_expandable_group(node: dict[str, Any]) -> bool:
    """`expandGroupSourceNodes` 的判定：是组类、**且不是 `characterAsset`**。"""
    d = node.get("data") or {}
    return isinstance(d.get("type"), str) and d["type"] in GROUP_TYPES and not d.get("characterAsset")


def expand_group_source_nodes(sources: list[dict[str, Any]], nodes: list[dict[str, Any]],
                              excluded: set[str] | None) -> list[dict[str, Any]]:
    """`expandGroupSourceNodes` 的复刻：递归展开普通分组，**深度上限 8**。

    逐字对照：没有"可展开的组"时原样返回；展开时按 `parentId` 建子表，
    遇到组类且非 `characterAsset` 就递归（`depth >= 8` 停），
    否则把该节点收进结果；**`excluded` 里的节点在 `depth > 0` 时"只标记不展开"**。
    """
    if not any(_is_expandable_group(s) for s in sources):
        return list(sources)
    children: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        pid = n.get("parentId")
        if not pid:
            continue
        children.setdefault(pid, []).append(n)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], depth: int) -> None:
        nid = node.get("id")
        if nid in seen:
            return
        if depth > 0 and excluded and nid in excluded:
            seen.add(nid)
            return
        if _is_expandable_group(node):
            seen.add(nid)
            if depth >= GROUP_EXPAND_DEPTH_CAP:
                return
            for child in children.get(nid, []):
                walk(child, depth + 1)
            return
        seen.add(nid)
        out.append(node)

    for s in sources:
        walk(s, 0)
    return out


def collect_character_reference_items(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`collectCharacterReferenceItems` 的复刻。

    **⚠ 它读的是 `edge.data.characterRef`（逐边字段），不是分组节点**——
    `characterAsset` 是上游模块把它**写进边**的（`persistCharacterReference`）。
    """
    out: list[dict[str, Any]] = []
    for e in edges:
        ref = (e.get("data") or {}).get("characterRef")
        if isinstance(ref, dict) and ref.get("mainReferenceImageUrl"):
            out.append({"nodeId": e.get("source"), "url": ref["mainReferenceImageUrl"],
                        "label": ref.get("roleName")})
    return out


def _group_ref_excluded(node: dict[str, Any] | None) -> set[str] | None:
    """`getGroupRefExcludedNodeIds(data)` 的复刻。"""
    raw = (node or {}).get("data", {}).get("groupRefExcludedNodeIds")
    if not isinstance(raw, list) or not raw:
        return None
    kept = {x for x in raw if isinstance(x, str)}
    return kept or None


def counts_from_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """按 `collectIncomingNodeDataForTarget` 的语义数素材（报告 79）。

    输入：`{nodes:[{id,data:{type,...}}], edges:[{source,target,data?}], targetId}`
    规则（逐字对照客户端）：
      · 只算 `edge.target === targetId` 的入边；
      · **排除 `edge.data.portraitVirtual` / `assetVirtual` 两类虚拟边**；
      · 按 source 节点的 `data.type` 分桶：`text` / `image` / `video` / `audio`；
      · **`reference` 跳过**（不进任何列表）；**`director-studio` 不进素材列表**；
      · **`group`/`video_group`/`video-story` 且非 `characterAsset` 的入边会被递归展开**（深度上限 8）；
      · **边上的 `data.characterRef` 收成 imageList 条目**（`collectCharacterReferenceItems`）；
      · 目标节点自己的 **`data.refImages`** 补进 `imageList`（**★ 不在 `params` 里**）；
      · **`data.params.focusRegion.nodeId` 命中时，把该 nodeId 从 `imageList` 里剔掉**。
      · **★ 提交侧覆盖**：目标是 `data.type === "image"` 且 `data.params.scene === "camera_focus"`
        且有 `data.params.originImage` 时，**实际提交的 `modeType` 被强制成 `"image2image"`，
        `imageList` 被整条替换成 `[originImage]`**（报告 31 / 报告 36；写入方见报告 81）。

    **⚠ 一处客户端间差异**：**网页版**判虚拟边用"真值"（`!e.data?.portraitVirtual`），
    **CLI 版**（`isStructuralUserEdgeCli`）用**严格等值**（`=== true`）。
    **本函数跟网页版**（真值），因为它是按 `collectIncomingNodeDataForTarget` 复刻的。
    """
    node_list = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    nodes = {n.get("id"): n for n in node_list}
    target_id = graph.get("targetId")
    lists: dict[str, list[Any]] = {"textList": [], "imageList": [], "videoList": [], "audioList": []}
    skipped: dict[str, int] = {}
    target_edges: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for edge in (graph.get("edges") or []):
        if not isinstance(edge, dict) or edge.get("target") != target_id:
            continue
        target_edges.append(edge)
        ed = edge.get("data") or {}
        if ed.get("portraitVirtual") or ed.get("assetVirtual"):
            continue
        src = nodes.get(edge.get("source"))
        if not src:
            continue
        sources.append(src)
    target = nodes.get(target_id) or {}
    for src in expand_group_source_nodes(sources, node_list, _group_ref_excluded(target)):
        _sd = src.get("data") or {}
        dtype = _sd.get("type")
        if not dtype:
            continue
        bucket = MATERIAL_LIST_BY_TYPE.get(dtype)
        if bucket:
            entry: dict[str, Any] = {"nodeId": src.get("id"), "type": dtype}
            if dtype == "text":
                # ★ 客户端 `collectIncomingNodeData` 的 TEXT 分支：`{nodeId, content: S(e.content)}`
                entry["content"] = normalize_text_content(_sd.get("content"))
            if dtype == "video":
                if "url" in _sd:
                    _url = _sd.get("url")
                else:
                    _url = src.get("url")
                if isinstance(_url, list):
                    _url = _url[0] if _url else None
                entry["url"] = _url
                _rm = src.get("resourceMeta")
                if isinstance(_rm, dict):
                    _items = _rm.get("items")
                    if isinstance(_items, list) and _items and isinstance(_items[0], dict):
                        _first = _items[0]
                        for _k in ("durationSec", "width", "height", "sizeBytes"):
                            if _k in _first:
                                entry[_k] = _first[_k]
            lists[bucket].append(entry)
        else:
            skipped[dtype] = skipped.get(dtype, 0) + 1
    lists["imageList"].extend(collect_character_reference_items(target_edges))
    # ★ 更正（2026-10-16）：`refImages` 在 `node.data.refImages`，**不在 `data.params` 里**。
    #   孪生版逐字：`let a=o?.data, l=Array.isArray(a?.refImages)?a.refImages:[]`；
    #   `1o5crmb53tqh1.js` 也写 `refImages: e.data.refImages`（与 `params` 平级）。
    ref_images = (target.get("data") or {}).get("refImages")
    if isinstance(ref_images, list):
        for i, url in enumerate(ref_images):
            lists["imageList"].append({"nodeId": "%s:ref-%d" % (target_id, i), "url": url})
    # ★ 新增：`focusRegion.nodeId` 是**排除项**，不是补充项。
    #   孪生版逐字：`let d=a?.params, u=d?.focusRegion?.nodeId; return u&&(s.imageList=s.imageList.filter(e=>e.nodeId!==u)),s`
    _params = (target.get("data") or {}).get("params")
    _focus = _params.get("focusRegion") if isinstance(_params, dict) else None
    focus_id = _focus.get("nodeId") if isinstance(_focus, dict) else None
    if focus_id:
        lists["imageList"] = [x for x in lists["imageList"] if x.get("nodeId") != focus_id]
    # ★ 提交侧覆盖（报告 31 / 36；写入方＝网页画布的 focus-region 处理器，报告 81）：
    #   `type === "image" && rest.scene === "camera_focus"` 时，
    #   `finalImageList = [rest.originImage]`，且结果里 `...isCameraFocus ? { modeType: "image2image" } : {}`。
    mode_override = None
    _dtype = (target.get("data") or {}).get("type")
    if _dtype == "image" and isinstance(_params, dict) \
            and _params.get("scene") == "camera_focus" and _params.get("originImage"):
        lists["imageList"] = [{"nodeId": "%s:originImage" % target_id, "url": _params["originImage"]}]
        mode_override = "image2image"
    # ★ `ctx` 也能从图里推（客户端 `buildEvalContextCli`，报告 76 / 81）：
    #   `hasImage = imageList 非空 || (scene === "camera_focus" && originImage)`
    #   `hasPrompt = 归一化提示词非空 || textList 有非空 content || scene === "camera_focus"`
    #   `hasMedia = hasImage || hasVideo || hasAudio`（**不含提示词**）
    _scene_focus = isinstance(_params, dict) and _params.get("scene") == "camera_focus"
    _has_img = bool(lists["imageList"]) or (_scene_focus and bool(_params.get("originImage")))
    _has_vid = bool(lists["videoList"])
    _has_aud = bool(lists["audioList"])
    _has_txt = any(x.get("content") for x in lists["textList"])
    ctx_from_graph = {
        "prompt": _has_txt or _scene_focus,
        "image": _has_img,
        "video": _has_vid,
        "audio": _has_aud,
        "media": _has_img or _has_vid or _has_aud,
    }
    return {
        "counts": {"image": len(lists["imageList"]), "video": len(lists["videoList"]),
                   "audio": len(lists["audioList"]), "text": len(lists["textList"])},
        "lists": lists,
        "skippedTypes": skipped,
        "notImplemented": [],
        "modeTypeOverride": mode_override,
        "ctxFromGraph": ctx_from_graph,
    }


def evaluate_media(schema: dict[str, Any], mode_type: str | None,
                   materials: list[dict[str, Any]] | None) -> dict[str, Any]:
    """第④层：`mediaConstraints`。**逐条素材判**，与客户端一致。

    客户端会去探测媒体拿 `durationSec` / `height` / `width`，并对 `size.max` 发 HEAD。
    **本脚本不发网络请求**，所以只判调用方喂进来的那些属性；缺的属性按客户端同款"跳过"。
    """
    if materials is None:
        return {"state": "skipped", "detail": "没给 --video-materials → 这一层没跑（≠ 通过）",
                "complete": False, "unchecked": [], "gaps": []}
    cs = (schema.get("properties") or {}).get("mediaConstraints")
    if not cs:
        return {"state": "skipped", "detail": "该模型没有 mediaConstraints",
                "complete": True, "unchecked": [], "gaps": []}
    video = None
    if mode_type:
        video = (cs.get(mode_type) or {}).get("video")
    if video is None:
        video = cs.get("video")
    if not video:
        return {"state": "skipped",
                "detail": "%s 没有 video 约束，也没有顶层 video 兜底" % (mode_type or "(未给模式)"),
                "complete": True, "unchecked": [], "gaps": []}
    blocks: list[str] = []
    warns: list[str] = []
    unchecked: list[str] = []

    def add(action: Any, msg: str) -> None:
        target = blocks if action == "block" else warns
        if msg and msg not in target:
            target.append(msg)

    def _msg(entry: dict[str, Any], fallback: str) -> str:
        return str(entry.get("message") or fallback)

    def _gap(name: str) -> None:
        if name not in unchecked:
            unchecked.append(name)

    for mat in materials:
        url = str(mat.get("url") or "")
        if not url:
            _gap("url")
            continue
        fmt = video.get("formats")
        if fmt:
            allowed = [str(x).lower() for x in (fmt.get("allowed") or [])]
            ext = _ext(url)
            if allowed:
                if not ext:
                    _gap("extension")
            if ext and allowed and ext not in allowed:
                add(fmt.get("action"), _msg(fmt, "输入视频格式不在白名单内"))
        dur = mat.get("durationSec")
        dur_c = video.get("duration")
        if dur_c:
            lo, hi = dur_c.get("min"), dur_c.get("max")
            if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                if not isinstance(dur, (int, float)):
                    _gap("durationSec")
        if dur_c and isinstance(dur, (int, float)):
            lo, hi = dur_c.get("min"), dur_c.get("max")
            if (isinstance(lo, (int, float)) and dur < lo) or \
               (isinstance(hi, (int, float)) and dur > hi):
                add(dur_c.get("action"), _msg(dur_c, "输入视频时长不在允许区间内"))
        for key, val in (("height", mat.get("height")), ("width", mat.get("width"))):
            entry = video.get(key)
            if entry:
                lo, hi = entry.get("min"), entry.get("max")
                if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                    if not isinstance(val, (int, float)):
                        _gap(key)
            if entry and isinstance(val, (int, float)):
                lo, hi = entry.get("min"), entry.get("max")
                if (isinstance(lo, (int, float)) and val < lo) or \
                   (isinstance(hi, (int, float)) and val > hi):
                    add(entry.get("action"), _msg(entry, "输入视频尺寸不在允许区间内"))
        h, w = mat.get("height"), mat.get("width")
        for _side_key in ("longSide", "shortSide"):
            _side_entry = video.get(_side_key)
            if not _side_entry:
                continue
            _slo, _shi = _side_entry.get("min"), _side_entry.get("max")
            if isinstance(_slo, (int, float)) or isinstance(_shi, (int, float)):
                if not isinstance(h, (int, float)):
                    _gap("height")
                if not isinstance(w, (int, float)):
                    _gap("width")
        if isinstance(h, (int, float)) and isinstance(w, (int, float)):
            for key, side in (("longSide", max(w, h)), ("shortSide", min(w, h))):
                entry = video.get(key)
                if not entry:
                    continue
                lo, hi = entry.get("min"), entry.get("max")
                if (isinstance(lo, (int, float)) and side < lo) or \
                   (isinstance(hi, (int, float)) and side > hi):
                    add(entry.get("action"), _msg(entry, "输入视频边长不在允许区间内"))
        size_c = video.get("size")
        size_bytes = mat.get("sizeBytes")
        if size_c and isinstance(size_c.get("max"), (int, float)):
            if isinstance(size_bytes, (int, float)):
                if size_bytes > size_c["max"]:
                    add(size_c.get("action"), _msg(size_c, "输入视频体积超过上限"))
            else:
                _gap("sizeBytes")

    complete = len(unchecked) == 0
    if blocks:
        return {"state": "fail", "reasons": blocks, "warns": warns,
                "complete": complete, "unchecked": unchecked, "gaps": list(unchecked)}
    if warns:
        return {"state": "warn", "reasons": [], "warns": warns,
                "complete": complete, "unchecked": unchecked, "gaps": list(unchecked)}
    return {"state": "pass", "warns": warns,
            "complete": complete, "unchecked": unchecked, "gaps": list(unchecked)}


T_MODE_TYPE_IN_MODE = "{modeType}模式下，"
T_PLEASE = "请"
T_VERB_INPUT = "输入"
T_VERB_ADD = "添加"
T_WHEN_HAS_PREFIX = "添加{items}时，需同时"
T_AND = "并"
T_OR = "或"


def unwrap(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Accept either `libtv model` output or a bare schema object."""
    if not isinstance(payload, dict):
        return None
    schema = payload.get("schema")
    if isinstance(schema, dict):
        return schema
    if "rules" in payload or "properties" in payload:
        return payload
    return None


def has(kind: str, ctx: dict[str, bool]) -> bool:
    return bool(ctx.get(kind))


def kind_label(kind: str) -> str:
    return KIND_LABEL.get(kind, kind)


def mode_type_label(mode_type: str) -> str:
    return MODE_TYPE_LABEL.get(mode_type, mode_type)


def build_reason(rule: dict[str, Any]) -> str:
    require = list(rule.get("require") or [])
    if not require:
        return ""
    mode = rule.get("mode") or "all"
    for_mode = list(rule.get("forModeTypes") or [])
    when_has = list(rule.get("whenHas") or [])
    head = ""
    if len(for_mode) == 1:
        head = T_MODE_TYPE_IN_MODE.format(modeType=mode_type_label(for_mode[0]))
    parts = [((T_VERB_INPUT if k == "prompt" else T_VERB_ADD) + kind_label(k)) for k in require]
    if when_has:
        items = T_AND.join(kind_label(k) for k in when_has)
        tail = T_WHEN_HAS_PREFIX.format(items=items)
        joiner = T_OR if mode == "any" else T_AND
        return head + tail + joiner.join(parts)
    if len(require) == 1:
        return head + T_PLEASE + parts[0]
    joiner = T_OR if mode == "any" else T_AND
    return head + T_PLEASE + joiner.join(parts)


def evaluate_rule(rule: dict[str, Any], ctx: dict[str, bool], mode_type: str | None) -> dict[str, Any]:
    require = list(rule.get("require") or [])
    mode = rule.get("mode") or "all"
    for_mode = list(rule.get("forModeTypes") or [])
    when_has = list(rule.get("whenHas") or [])

    # The client only skips a scoped rule when a modeType is actually known.
    if for_mode and mode_type and mode_type not in for_mode:
        return {"pass": True, "reason": "", "skipped": "forModeTypes"}
    if when_has and not all(has(k, ctx) for k in when_has):
        return {"pass": True, "reason": "", "skipped": "whenHas"}

    checks = [has(k, ctx) for k in require]
    passed = any(checks) if mode == "any" else all(checks)
    if passed:
        return {"pass": True, "reason": "", "skipped": None}
    custom = rule.get("message") or rule.get("messageI18nKey") or ""
    return {"pass": False, "reason": custom or build_reason(rule), "skipped": None}


def evaluate_ranges(schema: dict[str, Any], mode_type: str | None,
                    counts: dict[str, int]) -> dict[str, Any]:
    """第①层：`modeType.items` 的区间 + `config.excludeModeTypes`。"""
    if not mode_type:
        return {"state": "skipped", "detail": "没给 --mode-type → 区间层无从判"}
    cfg = schema.get("config") or {}
    excluded = [str(x) for x in (cfg.get("excludeModeTypes") or [])]
    if mode_type in excluded:
        return {"state": "fail",
                "reasons": ["config.excludeModeTypes 里含 %s → 该模型不提供这个模式" % mode_type]}
    items = (((schema.get("properties") or {}).get("modeType") or {}).get("items")) or {}
    if mode_type == "text2video":
        if any(counts.get(k, 0) > 0 for k in ("image", "video", "audio")):
            return {"state": "fail", "reasons": [T_TEXT2VIDEO_MEDIA]}
        return {"state": "pass", "detail": "text2video：无素材且未被 excludeModeTypes 排除"}
    if mode_type == "text2image":
        # ★ 2026-10-16（报告 81）：**客户端从不校验 `text2image`**——
        #   CLI 载荷里它只被 `computeImageModeTypeForCli` 推导（`imageList` 空 → `text2image`），
        #   从没进过任何 schema 门。所以这里**不判 fail，也不冒充 pass**。
        return {"state": "not_verified",
                "detail": "text2image：客户端只按 `imageList` 为空推导它，从不对它做 schema 门"
                          "——**没验到 ≠ 通过**"}
    if mode_type not in items:
        return {"state": "fail",
                "reasons": ["modeType.items 里没有 %s → 这个模式在该模型上不可用" % mode_type]}
    entry = items[mode_type]
    lo, hi = int(entry[0]), int(entry[1])
    if hi == 0:
        return {"state": "fail", "reasons": ["%s 的上限是 0（占位但不可用）" % mode_type]}
    list_key = LIST_KEY_BY_MODE_TYPE.get(mode_type)
    if list_key == "mixedList":
        n = counts.get("image", 0) + counts.get("video", 0)
        label = LIST_LABEL["mixedList"]
    else:
        kind = LIST_KIND.get(list_key)
        n = counts.get(kind, 0) if kind else 0
        label = LIST_LABEL.get(list_key, str(list_key))
    if not (lo <= n <= hi):
        rng = _range_text(lo, hi)
        if n == 0:
            return {"state": "fail",
                    "reasons": [T_NEED_CONNECT.format(mediaLabel=label, rangeText=rng)]}
        return {"state": "fail",
                "reasons": [T_COUNT_MISMATCH.format(mediaLabel=label, count=n, rangeText=rng)]}
    return {"state": "pass", "detail": "%s 数量 %d 落在 [%d,%d]" % (label, n, lo, hi)}


def evaluate_configs(schema: dict[str, Any], mode_type: str | None,
                     counts: dict[str, int]) -> dict[str, Any]:
    """第②层：`mixed2videoConfig` / `videoEdit2videoConfig` 的收紧。"""
    if not mode_type:
        return {"state": "skipped", "detail": "没给 --mode-type → 收紧层无从判"}
    mt = (schema.get("properties") or {}).get("modeType") or {}
    imgs = counts.get("image", 0)
    vids = counts.get("video", 0)
    auds = counts.get("audio", 0)
    reasons: list[str] = []
    touched = False

    cfg = mt.get("mixed2videoConfig")
    if cfg and mode_type in MIXED_LIST_PROTOCOL:
        touched = True
        vmax = cfg.get("videoMax")
        if isinstance(vmax, int) and vids > vmax:
            reasons.append(T_VIDEO_MAX.format(max=vmax, count=vids))
        imax = cfg.get("imageMax")
        if isinstance(imax, int) and imgs > imax:
            reasons.append(T_IMAGE_MAX.format(max=imax, count=imgs))
        imw = cfg.get("imageMaxWithVideo")
        if isinstance(imw, int) and vids > 0 and imgs > imw:
            reasons.append(T_IMAGE_MAX_WITH_VIDEO.format(max=imw, count=imgs))
        amax = cfg.get("audioMax")
        if isinstance(amax, int) and auds > amax:
            reasons.append(T_AUDIO_MAX.format(max=amax, count=auds))

    vcfg = mt.get("videoEdit2videoConfig")
    if vcfg and mode_type == "videoEdit2video":
        touched = True
        vmax = vcfg.get("videoMax")
        if isinstance(vmax, int) and vids > vmax:
            reasons.append(T_VIDEO_MAX.format(max=vmax, count=vids))
        imw = vcfg.get("imageMaxWithVideo")
        if isinstance(imw, int) and vids > 0 and imgs > imw:
            reasons.append(T_IMAGE_MAX_WITH_VIDEO.format(max=imw, count=imgs))
        # 音频这一步客户端只在 Seedance 2.5 上走得到（p() 的硬编码特判）。
        if _is_seedance_25(schema):
            amax = (cfg or {}).get("audioMax")
            if isinstance(amax, int) and auds > amax:
                reasons.append(T_AUDIO_MAX.format(max=amax, count=auds))

    if not touched:
        return {"state": "skipped", "detail": "该模式没有可用的 *Config（或模式不适用）"}
    return {"state": "fail", "reasons": reasons} if reasons else {"state": "pass"}


def evaluate(payload: dict[str, Any], ctx: dict[str, bool], mode_type: str | None,
             counts: dict[str, int] | None = None,
             materials: list[dict[str, Any]] | None = None,
             node_kind: str | None = None,
             prompt: str | None = None,
             graph: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = unwrap(payload)
    if schema is None:
        return {
            "exit_code": RC_NOSCHEMA,
            "verdict": "no_schema",
            "canGenerate": None,
            "reasons": [],
            "detail": "输入里找不到 schema（既不是 `libtv model` 输出，也不是裸 schema）。",
        }
    reasons: list[str] = []
    layers: dict[str, Any] = {}
    graph_info = None
    if graph is not None:
        # ★ 按 `collectIncomingNodeDataForTarget` 的语义自己数，而不是让调用方手填。
        graph_info = counts_from_graph(graph)
        counts = dict(graph_info["counts"])
        if graph_info.get("modeTypeOverride"):
            # ★ 提交侧覆盖：camera_focus 的 image 节点**实际按 `image2image` 提交**，
            #   所以下面四层都要按覆盖后的 `modeType` 判（报告 31 / 报告 81）。
            mode_type = graph_info["modeTypeOverride"]
        # ★ 从图里推出来的 `ctx` 与调用方给的 `--has-*` **取"或"**——
        #   `hasImage`/`hasVideo`/`hasAudio` 的真来源就是列表非空（`buildEvalContextCli`），
        #   `hasPrompt` 的另两条来路（`textList.content` / `camera_focus`）也在图里（报告 81）。
        _derived = graph_info.get("ctxFromGraph") or {}
        ctx = dict((k, bool(ctx.get(k)) or bool(_derived.get(k))) for k in KINDS)
    normalized = None
    if prompt is not None:
        # 客户端：hasPrompt = 归一化后非空 || textList 有非空 content || scene==="camera_focus"。
        # 后两条本脚本拿不到，所以按"或"叠加调用方给的 --has-prompt。
        normalized = normalize_prompt(prompt, mode_type)
        if normalized:
            ctx = dict(ctx, prompt=True)

    if counts is not None:
        layers["ranges"] = evaluate_ranges(schema, mode_type, counts)
        layers["configs"] = evaluate_configs(schema, mode_type, counts)
    else:
        _skip = {"state": "skipped",
                 "detail": "没给 --images/--videos/--audios → 这一层没跑（≠ 通过）"}
        layers["ranges"] = dict(_skip)
        layers["configs"] = dict(_skip)

    if materials is None and graph is not None and graph_info is not None:
        materials = [dict(_m) for _m in ((graph_info.get("lists") or {}).get("videoList") or [])]
    layers["media"] = evaluate_media(schema, mode_type, materials)

    raw_rules = schema.get("rules")
    rules_source = "schema"
    if raw_rules is None:
        raw_rules = DEFAULT_RULES.get(node_kind or "")
        rules_source = "default_table" if raw_rules is not None else "none"
    if raw_rules is None:
        layers["rules"] = {"state": "not_verified",
                           "detail": "该 schema 没有 rules 字段，也没给 --node-kind 走默认表"
                                     "——没验到 ≠ 通过"}
    else:
        # ★ 先清洗再判：客户端在 `tl()` 里也是先过模块 503357 再交给 61637。
        rules = clean_rules(raw_rules)
        evaluated: list[dict[str, Any]] = []
        rule_reasons: list[str] = []
        for rule in rules:
            outcome = evaluate_rule(rule, ctx, mode_type)
            evaluated.append({"require": rule.get("require"),
                              "mode": rule.get("mode") or "all", **outcome})
            if not outcome["pass"] and outcome["reason"]:
                rule_reasons.append(outcome["reason"])
        layers["rules"] = {"state": "fail" if rule_reasons else "pass",
                           "source": rules_source,
                           "rule_count": len(rules), "rules": evaluated,
                           "reasons": rule_reasons}
        reasons += rule_reasons

    for name in ("ranges", "configs", "media"):
        if layers[name].get("state") == "fail":
            reasons += list(layers[name].get("reasons") or [])

    checked = any(l.get("state") in ("pass", "fail", "warn") for l in layers.values())
    if not checked:
        return {
            "exit_code": RC_EMPTY,
            "verdict": "not_verified",
            "canGenerate": None,
            "modeType": mode_type,
            "reasons": [],
            "layers": layers,
            "normalizedPrompt": normalized,
            "graphInfo": graph_info,
            "detail": "三层里没有一层有东西可判（没给 counts、没有 rules）——没验到 ≠ 通过。",
        }
    return {
        "exit_code": RC_OK if not reasons else RC_FAIL,
        "verdict": "can_generate" if not reasons else "blocked",
        "canGenerate": not reasons,
        "modeType": mode_type,
        "counts": counts,
        "context": {k: bool(ctx.get(k)) for k in KINDS},
        "normalizedPrompt": normalized,
        "graphInfo": graph_info,
        "reasons": reasons,
        "layers": layers,
    }


def self_test() -> int:
    cases: list[dict[str, Any]] = []

    def case(name: str, payload: dict[str, Any], ctx: dict[str, bool], mode_type: str | None,
             expect_rc: int, expect_reason: str | None = None) -> None:
        got = evaluate(payload, ctx, mode_type)
        ok = got["exit_code"] == expect_rc
        if expect_reason is not None:
            ok = ok and any(expect_reason in reason for reason in got["reasons"])
        cases.append({"name": name, "ok": ok, "exit_code": got["exit_code"], "reasons": got["reasons"]})

    case("empty rules pass", {"schema": {"rules": []}}, {}, None, RC_OK)
    case("no rules key is not verified", {"schema": {"properties": {}}}, {}, None, RC_EMPTY)
    case("bare schema accepted", {"rules": [{"require": ["prompt"]}]}, {"prompt": True}, None, RC_OK)
    case("any satisfied", {"schema": {"rules": [{"require": ["prompt", "media"], "mode": "any"}]}},
         {"media": True}, None, RC_OK)
    case("any unsatisfied", {"schema": {"rules": [{"require": ["prompt", "media"], "mode": "any"}]}},
         {}, None, RC_FAIL, "请输入提示词或添加参考素材")
    case("all unsatisfied", {"schema": {"rules": [{"require": ["image", "video"], "mode": "all"}]}},
         {"image": True}, None, RC_FAIL, "请添加参考图片并添加参考视频")
    case("omitted mode means all",
         {"schema": {"rules": [{"require": ["image", "video"]}]}}, {"image": True}, None, RC_FAIL)
    case("explicit message wins",
         {"schema": {"rules": [{"require": ["image"], "message": "该模型需要参考图片才能生成视频"}]}},
         {}, None, RC_FAIL, "该模型需要参考图片才能生成视频")
    case("forModeTypes mismatch skips",
         {"schema": {"rules": [{"require": ["prompt"], "forModeTypes": ["text2video"]}]}},
         {}, "mixed2video", RC_OK)
    case("forModeTypes match evaluates",
         {"schema": {"rules": [{"require": ["prompt"], "forModeTypes": ["text2video"]}]}},
         {}, "text2video", RC_FAIL, "文生视频模式下，请输入提示词")
    case("unknown modeType does not skip",
         {"schema": {"rules": [{"require": ["prompt"], "forModeTypes": ["text2video"]}]}},
         {}, None, RC_FAIL)
    case("whenHas unsatisfied skips",
         {"schema": {"rules": [{"require": ["image", "video"], "mode": "any", "whenHas": ["audio"]}]}},
         {}, None, RC_OK)
    case("whenHas satisfied evaluates",
         {"schema": {"rules": [{"require": ["image", "video"], "mode": "any", "whenHas": ["audio"]}]}},
         {"audio": True}, None, RC_FAIL, "添加参考音频时，需同时添加参考图片或添加参考视频")
    case("audio2video uses 音频驱动 label",
         {"schema": {"rules": [{"require": ["image"], "forModeTypes": ["audio2video"]}]}},
         {}, "audio2video", RC_FAIL, "音频驱动模式下，")

    def case_counts(name: str, schema: dict[str, Any], mode_type: str,
                    counts: dict[str, int], expect_rc: int,
                    expect_reason: str | None = None) -> None:
        got = evaluate({"schema": schema}, {}, mode_type, counts)
        ok = got["exit_code"] == expect_rc
        if expect_reason is not None:
            ok = ok and any(expect_reason in r for r in got["reasons"])
        cases.append({"name": name, "ok": ok, "exit_code": got["exit_code"],
                      "reasons": got["reasons"]})

    _MTS = {"properties": {"modeType": {"items": {"text2video": None, "image2video": [1, 30],
                                                  "image2image": [0, 14], "mixed2video": [1, 50],
                                                  "videoEdit2video": [1, 1], "audio2video": [0, 0]},
                                       "mixed2videoConfig": {"videoMax": 10, "imageMax": 30,
                                                             "audioMax": 10},
                                       "videoEdit2videoConfig": {"videoMax": 1,
                                                                 "imageMaxWithVideo": 4}}},
            "config": {}}
    _MTS["properties"]["modeType"]["items"].pop("text2video")
    case_counts("区间：text2video 带素材被拦",
                dict(_MTS, config={}), "text2video", {"image": 1}, RC_FAIL, T_TEXT2VIDEO_MEDIA)
    case_counts("区间：text2video 无素材放行",
                dict(_MTS, config={}), "text2video", {"image": 0}, RC_OK)
    case_counts("区间：image2video 0 张被拦",
                _MTS, "image2video", {"image": 0}, RC_FAIL, "需要连接参考图片节点（1~30个）")
    case_counts("区间：image2video 5 张放行",
                _MTS, "image2video", {"image": 5}, RC_OK)
    case_counts("区间：image2image 下限 0 放行",
                _MTS, "image2image", {"image": 0}, RC_OK)
    _MTS_IMG = {"properties": {"modeType": {"items": {"image2image": [1, 3]}}}, "config": {}}
    case_counts("区间：image2image 必须按 imageList 数（下限 1 · 给 1 张放行）",
                _MTS_IMG, "image2image", {"image": 1}, RC_OK)
    case_counts("区间：image2image 必须按 imageList 数（下限 1 · 给 0 张拦）",
                _MTS_IMG, "image2image", {"image": 0}, RC_FAIL, "需要连接参考图片节点")
    case_counts("区间：text2image 不做 schema 门（客户端只推导、不校验）",
                _MTS_IMG, "text2image", {"image": 0}, RC_EMPTY)
    case_counts("区间：上限 0 等于不可用",
                _MTS, "audio2video", {"audio": 1}, RC_FAIL, "上限是 0")
    case_counts("区间：模式不在 items 里",
                _MTS, "videoExtend2video", {"video": 1}, RC_FAIL, "modeType.items 里没有")
    case_counts("区间：excludeModeTypes 排除",
                dict(_MTS, config={"excludeModeTypes": ["text2video"]}),
                "text2video", {"image": 0}, RC_FAIL, "excludeModeTypes 里含 text2video")
    case_counts("收紧：mixed2video 视频超 videoMax",
                _MTS, "mixed2video", {"video": 11, "image": 1}, RC_FAIL, "视频最多 10 个，当前 11 个")
    case_counts("收紧：mixed2video 音频超 audioMax",
                _MTS, "mixed2video", {"video": 1, "image": 1, "audio": 11}, RC_FAIL,
                "音频最多 10 个，当前 11 个")
    case_counts("收紧：videoEdit2video 视频超 videoMax",
                _MTS, "videoEdit2video", {"video": 2, "image": 1}, RC_FAIL, "视频最多 1 个，当前 2 个")
    case_counts("收紧：videoEdit2video 有视频时图片超 imageMaxWithVideo",
                _MTS, "videoEdit2video", {"video": 1, "image": 5}, RC_FAIL,
                "有视频时，图片最多 4 个，当前 5 个")

    _MC = {"properties": {"mediaConstraints": {"mixed2video": {"video": {
        "formats": {"allowed": ["mp4", "mov"], "message": "输入视频仅支持MP4和MOV格式",
                    "action": "block"},
        "duration": {"min": 3, "max": 10, "message": "输入视频需要在3s-10s之间", "action": "block"},
        "height": {"min": 720, "max": 2160, "message": "视频高度需在720~2160之间",
                   "action": "warn"},
        "size": {"max": 100, "message": "输入视频体积超过上限", "action": "block"}}}}}}

    def case_media(name: str, materials: list[dict[str, Any]] | None, expect_rc: int,
                   expect_reason: str | None = None, expect_state: str | None = None) -> None:
        got = evaluate({"schema": _MC}, {}, "mixed2video", None, materials)
        layer = got["layers"]["media"]
        ok = got["exit_code"] == expect_rc
        if expect_state is not None:
            ok = ok and layer.get("state") == expect_state
        if expect_reason is not None:
            ok = ok and any(expect_reason in r for r in
                            (list(layer.get("reasons") or []) + list(layer.get("warns") or [])))
        cases.append({"name": name, "ok": ok, "exit_code": got["exit_code"],
                      "media_state": layer.get("state"),
                      "reasons": layer.get("reasons"), "warns": layer.get("warns")})

    case_media("media：没给素材 → skipped", None, RC_EMPTY, expect_state="skipped")
    case_media("media：格式不在白名单 → block",
               [{"url": "https://x/a.avi"}], RC_FAIL, "输入视频仅支持MP4和MOV格式", "fail")
    case_media("media：时长越界 → block",
               [{"url": "https://x/a.mp4", "durationSec": 2}], RC_FAIL, "输入视频需要在3s-10s之间",
               "fail")
    case_media("media：时长合规 → pass",
               [{"url": "https://x/a.mp4", "durationSec": 5}], RC_OK, None, "pass")
    case_media("media：高度越界但 action=warn → warn 且不拦",
               [{"url": "https://x/a.mp4", "durationSec": 5, "height": 500}], RC_OK,
               "视频高度需在720~2160之间", "warn")
    case_media("media：体积超上限 → block",
               [{"url": "https://x/a.mp4", "durationSec": 5, "sizeBytes": 200}], RC_FAIL,
               "输入视频体积超过上限", "fail")
    case_media("media：逐条判（第一条合规第二条越界）",
               [{"url": "https://x/a.mp4", "durationSec": 5},
                {"url": "https://x/b.mp4", "durationSec": 99}], RC_FAIL,
               "输入视频需要在3s-10s之间", "fail")

    def case_kind(name: str, schema: dict[str, Any], ctx: dict[str, bool],
                  mode_type: str | None, node_kind: str | None, expect_rc: int,
                  expect_reason: str | None = None, expect_count: int | None = None) -> None:
        got = evaluate({"schema": schema}, ctx, mode_type, None, None, node_kind)
        layer = got["layers"]["rules"]
        ok = got["exit_code"] == expect_rc
        if expect_count is not None:
            ok = ok and layer.get("rule_count") == expect_count
        if expect_reason is not None:
            ok = ok and any(expect_reason in r for r in got["reasons"])
        cases.append({"name": name, "ok": ok, "exit_code": got["exit_code"],
                      "rule_count": layer.get("rule_count"), "source": layer.get("source")})

    case_kind("清洗：require 里的非法 kind 被删、规则保留",
              {"rules": [{"require": ["prompt", "bogus"]}]}, {"prompt": True}, None, None, RC_OK,
              expect_count=1)
    case_kind("清洗：require 全是非法 kind → 整条丢弃",
              {"rules": [{"require": ["bogus"]}]}, {}, None, None, RC_OK, expect_count=0)
    case_kind("清洗：mode 非 any 一律变 all",
              {"rules": [{"require": ["prompt", "image"], "mode": "ANY"}]}, {"prompt": True},
              None, None, RC_FAIL, "请输入提示词并添加参考图片")
    case_kind("清洗：非字符串 message 被丢掉、回落模板句",
              {"rules": [{"require": ["prompt"], "message": {"a": 1}}]}, {}, None, None,
              RC_FAIL, "请输入提示词")
    case_kind("清洗：whenHas 里的非法 kind 被删",
              {"rules": [{"require": ["image"], "whenHas": ["bogus"]}]}, {}, None, None,
              RC_FAIL, expect_count=1)
    case_kind("默认表：schema 无 rules + node-kind=video → 走默认表",
              {"properties": {}}, {}, "text2video", "video", RC_FAIL,
              "文生视频模式下，请输入提示词", expect_count=2)
    case_kind("默认表：node-kind=enhanceImage → 只要求 media",
              {"properties": {}}, {}, None, "enhanceImage", RC_FAIL, "请添加参考素材")
    case_kind("默认表：没给 node-kind 仍记 not_verified",
              {"properties": {}}, {}, None, None, RC_EMPTY)

    def case_norm(name: str, prompt: str, mode_type: str | None,
                  expect_norm: str, expect_has_prompt: bool) -> None:
        got = normalize_prompt(prompt, mode_type)
        eff = evaluate({"schema": {"rules": [{"require": ["prompt"]}]}}, {},
                       mode_type, None, None, None, prompt)
        has_prompt = eff["context"]["prompt"]
        ok = got == expect_norm and has_prompt == expect_has_prompt
        cases.append({"name": name, "ok": ok, "normalized": got,
                      "hasPrompt": has_prompt, "exit_code": eff["exit_code"]})

    case_norm("归一化：只写 {{Image 1}} 仍算有提示词",
              "{{Image 1}}", "mixed2video", "{{Image 1}}", True)
    case_norm("归一化：CameraPreset 只在 X 那两个模式下被删（mixed2video 保留）",
              "{{CameraPreset 3}}", "mixed2video", "{{CameraPreset 3}}", True)
    case_norm("归一化：frames2video 走 X，CameraPreset 被清空",
              "{{CameraPreset 3}}", "frames2video", "", False)
    case_norm("归一化：只写 {{SlashPreset:x}} 被清空",
              "{{SlashPreset:x}}", "mixed2video", "", False)
    case_norm("归一化：只写 {{Panorama720}} 被清空",
              "{{Panorama720}}", "mixed2video", "", False)
    case_norm("归一化：非 X 模式把制表符压成空格",
              "a\t\tb", "mixed2video", "a b", True)
    case_norm("归一化：frames2video 走 X，不压空白",
              "a\t\tb", "frames2video", "a\t\tb", True)
    case_norm("归一化：两边都 trim",
              "   {{Image 1}}   ", "mixed2video", "{{Image 1}}", True)

    def case_graph(name: str, graph: dict[str, Any], expect: dict[str, int],
                   expect_skipped: dict[str, int] | None = None,
                   expect_mode: str | None = None, expect_no_mode: bool = False,
                   expect_ctx: dict[str, bool] | None = None) -> None:
        info = counts_from_graph(graph)
        ok = info["counts"] == expect
        if expect_skipped is not None:
            ok = ok and info["skippedTypes"] == expect_skipped
        if expect_mode is not None:
            ok = ok and info.get("modeTypeOverride") == expect_mode
        if expect_no_mode:
            ok = ok and info.get("modeTypeOverride") is None
        if expect_ctx is not None:
            ok = ok and info.get("ctxFromGraph") == expect_ctx
        cases.append({"name": name, "ok": ok, "counts": info["counts"],
                      "skipped": info["skippedTypes"], "mode": info.get("modeTypeOverride"),
                      "ctx": info.get("ctxFromGraph")})

    _N = lambda i, t, **kw: {"id": i, "data": dict({"type": t}, **kw)}
    case_graph("计数：image/video/audio 各按入边分桶",
               {"targetId": "V1",
                "nodes": [_N("i1", "image"), _N("i2", "image"), _N("v1", "video"),
                          _N("a1", "audio"), _N("V1", "video")],
                "edges": [{"source": "i1", "target": "V1"}, {"source": "i2", "target": "V1"},
                          {"source": "v1", "target": "V1"}, {"source": "a1", "target": "V1"}]},
               {"image": 2, "video": 1, "audio": 1, "text": 0})
    case_graph("计数：reference 不进任何列表",
               {"targetId": "V1", "nodes": [_N("r1", "reference"), _N("V1", "video")],
                "edges": [{"source": "r1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0}, {"reference": 1})
    case_graph("计数：director-studio 不进素材列表",
               {"targetId": "V1", "nodes": [_N("d1", "director-studio"), _N("V1", "video")],
                "edges": [{"source": "d1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0}, {"director-studio": 1})
    case_graph("计数：portraitVirtual / assetVirtual 两类虚拟边被排除",
               {"targetId": "V1", "nodes": [_N("i1", "image"), _N("i2", "image"), _N("V1", "video")],
                "edges": [{"source": "i1", "target": "V1", "data": {"portraitVirtual": True}},
                          {"source": "i2", "target": "V1", "data": {"assetVirtual": True}}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0})
    case_graph("计数：目标自己的 data.refImages 补进 imageList（★ 不在 params 里）",
               {"targetId": "V1",
                "nodes": [_N("V1", "video", refImages=["u1", "u2"])],
                "edges": []},
               {"image": 2, "video": 0, "audio": 0, "text": 0})
    case_graph("计数：refImages 放进 params 不算（负向对照）",
               {"targetId": "V1",
                "nodes": [_N("V1", "video", params={"refImages": ["u1", "u2"]})],
                "edges": []},
               {"image": 0, "video": 0, "audio": 0, "text": 0})
    case_graph("计数：focusRegion.nodeId 把该节点从 imageList 里剔掉",
               {"targetId": "V1",
                "nodes": [_N("i1", "image"), _N("i2", "image"),
                          _N("V1", "video", params={"focusRegion": {"nodeId": "i1"}})],
                "edges": [{"source": "i1", "target": "V1"}, {"source": "i2", "target": "V1"}]},
               {"image": 1, "video": 0, "audio": 0, "text": 0})
    case_graph("计数：focusRegion.nodeId 的过滤在 refImages 之后（顺序钉住）",
               {"targetId": "V1",
                "nodes": [_N("V1", "video", refImages=["u1", "u2"],
                             params={"focusRegion": {"nodeId": "V1:ref-0"}})],
                "edges": []},
               {"image": 1, "video": 0, "audio": 0, "text": 0})
    case_graph("计数：camera_focus 的 image 节点 → imageList 换成 [originImage] ＋ modeType 覆盖成 image2image",
               {"targetId": "I1",
                "nodes": [_N("i1", "image"), _N("i2", "image"),
                          _N("I1", "image", params={"scene": "camera_focus",
                                                    "originImage": "https://x/focus.png"})],
                "edges": [{"source": "i1", "target": "I1"}, {"source": "i2", "target": "I1"}]},
               {"image": 1, "video": 0, "audio": 0, "text": 0},
               expect_mode="image2image")
    case_graph("计数：scene 不是 camera_focus 时不做替换（负向对照）",
               {"targetId": "I1",
                "nodes": [_N("i1", "image"), _N("i2", "image"),
                          _N("I1", "image", params={"originImage": "https://x/focus.png"})],
                "edges": [{"source": "i1", "target": "I1"}, {"source": "i2", "target": "I1"}]},
               {"image": 2, "video": 0, "audio": 0, "text": 0},
               expect_no_mode=True)
    case_graph("计数：camera_focus 的 video 节点不做替换（type 必须是 image）",
               {"targetId": "V1",
                "nodes": [_N("i1", "image"),
                          _N("V1", "video", params={"scene": "camera_focus",
                                                    "originImage": "https://x/focus.png"})],
                "edges": [{"source": "i1", "target": "V1"}]},
               {"image": 1, "video": 0, "audio": 0, "text": 0},
               expect_no_mode=True)
    case_graph("计数：虚拟边按真值判（网页语义）——portraitVirtual 是真值字符串也算虚拟",
               {"targetId": "V1", "nodes": [_N("i1", "image"), _N("V1", "video")],
                "edges": [{"source": "i1", "target": "V1", "data": {"portraitVirtual": "1"}}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0},
               expect_no_mode=True)
    _NONE_CTX = {"prompt": False, "image": False, "video": False, "audio": False, "media": False}
    case_graph("ctx：文本节点的 content 非空 → hasPrompt",
               {"targetId": "V1",
                "nodes": [_N("t1", "text", content="一句台词"), _N("V1", "video")],
                "edges": [{"source": "t1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 1},
               expect_ctx=dict(_NONE_CTX, prompt=True))
    case_graph("ctx：文本节点 content 是空数组 → hasPrompt 不成立",
               {"targetId": "V1",
                "nodes": [_N("t1", "text", content=[]), _N("V1", "video")],
                "edges": [{"source": "t1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 1},
               expect_ctx=dict(_NONE_CTX))
    case_graph("ctx：图片入边 → hasImage 与 hasMedia",
               {"targetId": "V1",
                "nodes": [_N("i1", "image"), _N("V1", "video")],
                "edges": [{"source": "i1", "target": "V1"}]},
               {"image": 1, "video": 0, "audio": 0, "text": 0},
               expect_ctx=dict(_NONE_CTX, image=True, media=True))
    case_graph("ctx：camera_focus ＋ originImage → hasPrompt 与 hasImage 都由 scene 带出来",
               {"targetId": "I1",
                "nodes": [_N("I1", "image", params={"scene": "camera_focus",
                                                    "originImage": "https://x/f.png"})],
                "edges": []},
               {"image": 1, "video": 0, "audio": 0, "text": 0},
               expect_mode="image2image",
               expect_ctx=dict(_NONE_CTX, prompt=True, image=True, media=True))
    case_graph("计数：空 group 展开后不贡献任何素材",
               {"targetId": "V1", "nodes": [_N("g1", "group"), _N("V1", "video")],
                "edges": [{"source": "g1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0}, {})
    case_graph("计数：group 被递归展开，子节点才算素材",
               {"targetId": "V1",
                "nodes": [dict(_N("g1", "group"), parentId=None),
                          dict(_N("i1", "image"), parentId="g1"),
                          dict(_N("i2", "image"), parentId="g1"),
                          _N("V1", "video")],
                "edges": [{"source": "g1", "target": "V1"}]},
               {"image": 2, "video": 0, "audio": 0, "text": 0}, {})
    case_graph("计数：characterAsset 的组不展开，自己也不进素材列表",
               {"targetId": "V1",
                "nodes": [_N("g1", "group", characterAsset=True),
                          dict(_N("i1", "image"), parentId="g1"),
                          _N("V1", "video")],
                "edges": [{"source": "g1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0}, {"group": 1})
    case_graph("计数：groupRefExcludedNodeIds 里的节点只标记不展开",
               {"targetId": "V1",
                "nodes": [dict(_N("g1", "group"), parentId=None),
                          dict(_N("i1", "image"), parentId="g1"),
                          _N("V1", "video", groupRefExcludedNodeIds=["i1"])],
                "edges": [{"source": "g1", "target": "V1"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0}, {})
    case_graph("计数：边上的 data.characterRef 收成 imageList 条目",
               {"targetId": "V1", "nodes": [_N("g1", "group"), _N("V1", "video")],
                "edges": [{"source": "g1", "target": "V1",
                           "data": {"characterRef": {"mainReferenceImageUrl": "https://x/c.png",
                                                     "roleName": "主角"}}}]},
               {"image": 1, "video": 0, "audio": 0, "text": 0}, {})
    case_graph("计数：非目标入边不算",
               {"targetId": "V1", "nodes": [_N("i1", "image"), _N("V1", "video"), _N("V2", "video")],
                "edges": [{"source": "i1", "target": "V2"}]},
               {"image": 0, "video": 0, "audio": 0, "text": 0})

    failed = [c for c in cases if not c["ok"]]
    print(json.dumps({"cases": cases, "passed": len(cases) - len(failed), "failed": len(failed)},
                     ensure_ascii=False, indent=2))
    return RC_OK if not failed else RC_FAIL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", help="`libtv model <modelKey>` 的 JSON 输出，或裸 schema 文件")
    parser.add_argument("--mode-type", default=None)
    for kind in KINDS:
        parser.add_argument("--has-%s" % kind, action="store_true")
    parser.add_argument("--images", type=int, default=None,
                        help="已连的参考图片数量；与 --videos/--audios 一起决定区间层与收紧层跑不跑")
    parser.add_argument("--videos", type=int, default=None)
    parser.add_argument("--audios", type=int, default=None)
    parser.add_argument("--video-materials", default=None,
                        help="JSON 文件，数组，每项 {url, durationSec?, height?, width?, sizeBytes?}；"
                             "喂了才判 mediaConstraints 那一层（本脚本不探测媒体、不发请求）")
    parser.add_argument("--node-kind", default=None,
                        help="image|video|text|audio|enhanceVideo|enhanceImage；"
                             "schema 没有 rules 字段时，用客户端那张默认规则表（模块 821992）")
    parser.add_argument("--prompt", default=None,
                        help="原始提示词。给了就按模块 838978 的 X / b(F(...)) 归一化，"
                             "并用『归一化后非空』参与 hasPrompt 判定（插桩不会被删）")
    parser.add_argument("--prompt-file", default=None, help="从文件读原始提示词（与 --prompt 二选一）")
    parser.add_argument("--materials-from", default=None,
                        help="JSON 文件 {nodes:[{id,data:{type,...}}],edges:[{source,target,data?}],targetId}；"
                             "给了就按 collectIncomingNodeDataForTarget 的语义自己数 counts"
                             "（reference / director-studio 不计入；虚拟边排除；refImages 补进 imageList）")
    parser.add_argument("--materials-stdin", action="store_true",
                        help="从 stdin 读同一张 graph JSON（与 --materials-from 二选一）；"
                             "**编排器逐节点分流时用它，避免落临时文件**")
    parser.add_argument("--json-out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.schema:
        parser.error("--schema is required unless --self-test")

    path = Path(args.schema)
    if not path.exists():
        print(json.dumps({"exit_code": RC_NOSCHEMA, "verdict": "no_schema",
                          "detail": "文件不存在：%s" % path}, ensure_ascii=False, indent=2))
        return RC_NOSCHEMA
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                          "detail": "JSON 解析失败：%s" % exc}, ensure_ascii=False, indent=2))
        return RC_USAGE

    ctx = {kind: bool(getattr(args, "has_%s" % kind)) for kind in KINDS}
    counts = None
    if any(x is not None for x in (args.images, args.videos, args.audios)):
        counts = {"image": args.images or 0, "video": args.videos or 0, "audio": args.audios or 0}
    materials = None
    if args.video_materials:
        mp = Path(args.video_materials)
        if not mp.exists():
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--video-materials 文件不存在：%s" % mp},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
        try:
            materials = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--video-materials JSON 解析失败：%s" % exc},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
    prompt = args.prompt
    if prompt is None and args.prompt_file:
        pp = Path(args.prompt_file)
        if not pp.exists():
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--prompt-file 文件不存在：%s" % pp},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
        prompt = pp.read_text(encoding="utf-8")
    graph = None
    if args.materials_from:
        gp = Path(args.materials_from)
        if not gp.exists():
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--materials-from 文件不存在：%s" % gp},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
        try:
            graph = json.loads(gp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--materials-from JSON 解析失败：%s" % exc},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
    if args.materials_stdin:
        if args.materials_from:
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--materials-from 与 --materials-stdin 只能给一个"},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
        try:
            graph = json.loads(sys.stdin.read() or "null")
        except json.JSONDecodeError as exc:
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--materials-stdin 的 JSON 解析失败：%s" % exc},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
        if graph is None:
            print(json.dumps({"exit_code": RC_USAGE, "verdict": "usage",
                              "detail": "--materials-stdin 收到空输入"},
                             ensure_ascii=False, indent=2))
            return RC_USAGE
    result = evaluate(payload, ctx, args.mode_type, counts, materials, args.node_kind, prompt, graph)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
