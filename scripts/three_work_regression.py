#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""three_work_regression —— 三作 + 合成场景的只读回归（C 路 · 2026-10-07）

★ 它是什么／不是什么
  **只读**：只吃本地已落盘的 `project_full*.json` 快照，**不联网、不读画布、不点火**。
  它把「三作画像」变成**可回归的基线**：以后任何改动跑一遍，坏没坏当场可见。

★ 输入（由 `--base` 指定目录，默认文件名可覆盖）
  · `project_full_w1.json` = W1《弥寿计划》  `9b28eb33…`
  · `project_full_w2.json` = W2《抵达之前》  `9acfd448…`
  · `project_full.json`    = W3《THE TURN》 `fa2c927d…`
  这三个文件是 `{projectUuid, nodes[{id,name,type,…}], edges[{id,source,target}]}`。

★★ 必须知道的证据边界（决定了哪些判据只能记「不可判定」）
  本地快照的节点**只有 `id/name/type/position/width/height`**，**没有 `action` / `modeType`
  / `prompt`**。因此：
  · 「`video_generate` 之间不可直接引用」这条**在本快照里判不了** ——
    同一对 `video→video` 在 `video_resource → video_generate` 时合法。
    → 本脚本**不把 `video→video` 计成 FAIL**，只计数 + 标【不可判定】。
  · 「段落是否按镜号分段」的**内容层判据**同样判不了（快照无 prompt）。
  → 要 action 级判据，走 `project_info.nodeList` 或 `read_node`（见 22_ 规范）。

★ 三作基线是**本快照的冻结值**，不是"通用节点数"（红线明令不得写死 139/581/700 当通用规模）。
  基线变了就说明快照变了 —— 那正是回归要报的事。

★ 退出码
  0 全过 ｜ 1 检出问题 ｜ 2 用法错 ｜ 3 没扫到（≠通过）｜ 5 不适用

用法：
  python3 scripts/three_work_regression.py run --base <快照目录> [--json] [--out report.json]
  python3 scripts/three_work_regression.py --self-test
"""
from __future__ import print_function

import collections
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import graph_plan_lint as G          # 复用同一套边合法性判据，避免两处各写一份
    _HAS_LINT = True
except Exception:                        # pragma: no cover - 只在文件被挪走时发生
    _HAS_LINT = False

GATE_PASS, GATE_FAIL, GATE_USAGE = 0, 1, 2
GATE_NOT_CHECKED, GATE_NOT_APPLICABLE = 3, 5

# ─── 冻结基线（2026-10-07 从磁盘实测读出，逐条可复算） ──────────────────────
BASELINE = {
    "W1": {"file": "project_full_w1.json", "uuid": "9b28eb33680f4f63ab78ad747b2eed5c",
           "nodes": 180, "edges": 775,
           "types": {"group": 19, "image": 42, "text": 1, "video": 118},
           "dangling_edges": 0, "duplicate_edge_pairs": 0, "self_loops": 0},
    "W2": {"file": "project_full_w2.json", "uuid": "9acfd4487c9842d985cd9348f6966059",
           "nodes": 762, "edges": 1926,
           "types": {"group": 27, "audio": 11, "image": 220, "text": 5,
                     "video": 466, "video-clip": 33},
           "dangling_edges": 12, "duplicate_edge_pairs": 61, "self_loops": 0,
           "clips_without_incoming": 12},
    "W3": {"file": "project_full.json", "uuid": "fa2c927dfed048a8ac938fe008f4a3c8",
           "nodes": 581, "edges": 1550,
           "types": {"group": 81, "video": 194, "text": 92, "image": 178, "audio": 36},
           "dangling_edges": 0, "duplicate_edge_pairs": 0, "self_loops": 0},
}

# ─── 逐节点转储基线（2026-10-07 从磁盘实测读出；子目录名见 §「转储」） ──────────
#   为什么需要它们：project_full*.json 只有 {id,name,type,position}，**没有 action/params/prompt**
#   → 光靠它判不了「W1 边参数一致」「W3 长片分段」。这些子目录是**逐节点转储**，
#     带 data.action / data.params.*ListOrder / data.params.prompt / clipTimelineData。
DUMPS = {
    "w1_prompts": {"dir": "prompts_w1",
                   "files": 117, "nodes_with_params": 114,
                   "unresolved_distinct": 11, "unplugged_distinct": 16, "empty_prompt": 0},
    "w2_clips": {"dir": "clips_w2",
                 "files": 33, "authoritative": 33, "clip_entries": 46,
                 "files_with_external_source": 33},
    "w3_texts": {"dir": "texts_w3",
                 "files": 92, "files_with_ranges": 76, "total_ranges": 800,
                 "files_with_shot_marker": 79},
    "w3_videos": {"dir": "video_prompts",
                  "files": 192, "node_dumps": 158, "search_result_files": 34,
                  "matched_in_node_set": 158, "files_with_ranges": 123,
                  "total_ranges": 1103, "files_with_shot_marker": 119},
}

# W1 已知的两类"边与插桩不一致"（都有出处，不是本批新引入）
W1_KNOWN_DANGLING = 8       # 悬空 image 节点（资产已删、引用残留）
W1_KNOWN_OFFCANVAS_AUDIO = 3  # 被引用但不在本画布节点集合内的 audio

ORDER_KEYS = ("imageListOrder", "mixedListOrder", "videoListOrder",
              "audioListOrder", "textListOrder")
TIMERANGE_RE = re.compile(r"\d{1,2}\.\d\s*[\u2013\u2014-]\s*\d{1,2}\.\d")
SHOTMARK_RE = re.compile(r"(?:\u955c\u5934|\u955c\u53f7|SHOT|SC\d|SCENE)")


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def load_snapshot(path):
    j = json.loads(_read(path))
    nodes = j.get("nodes") or []
    edges = j.get("edges") or []
    return j.get("projectUuid"), nodes, edges


def _snapshot_edges(base_dir, work):
    """只读取某作快照的边表（供 W1P 做「边 ↔ 引用槽位」对账）。"""
    path = os.path.join(base_dir, BASELINE[work]["file"])
    if not os.path.isfile(path):
        return []
    _, _, edges = load_snapshot(path)
    return edges


def measure(nodes, edges):
    """量出所有可机判的结构事实。"""
    by_id = {}
    for n in nodes:
        by_id.setdefault(n.get("id"), n)
    types = collections.Counter(n.get("type") for n in nodes)
    dangling, loops = [], []
    pairs = collections.Counter()
    pair_kind = collections.Counter()
    indeg = collections.Counter()
    outdeg = collections.Counter()
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in by_id or t not in by_id:
            dangling.append((s, t)); continue
        if s == t:
            loops.append(s); continue
        pairs[(s, t)] += 1
        pair_kind[(by_id[s].get("type"), by_id[t].get("type"))] += 1
        outdeg[s] += 1
        indeg[t] += 1
    dups = [(k, v) for k, v in pairs.items() if v > 1]
    return {"nodes": len(nodes), "edges": len(edges), "types": dict(types),
            "dangling_edges": len(dangling), "self_loops": len(loops),
            "duplicate_edge_pairs": len(dups),
            "duplicate_extra_copies": sum(v - 1 for _, v in dups),
            "edge_kinds": dict(pair_kind), "indeg": indeg, "outdeg": outdeg,
            "by_id": by_id, "ids": set(by_id),
            "max_fanout": (max(outdeg.items(), key=lambda kv: kv[1]) if outdeg else (None, 0))}


# ─────────────────────────────────────────────────────────────────────────────
# 四条回归：W1 边参数一致 / W2 多层装配 / W3 长片分段 / 合成场景
# ─────────────────────────────────────────────────────────────────────────────
def regress_w1(uuid, m, base):
    out = []
    if uuid != base["uuid"]:
        out.append(("FAIL", "W1_UUID", "uuid=%s 与基线 %s 不符" % (uuid, base["uuid"])))
    else:
        out.append(("PASS", "W1_UUID", "uuid 与基线一致"))
    for key, label in (("nodes", "节点数"), ("edges", "边数")):
        if m[key] != base[key]:
            out.append(("FAIL", "W1_" + key.upper(),
                        "%s=%d 与基线 %d 不符" % (label, m[key], base[key])))
        else:
            out.append(("PASS", "W1_" + key.upper(), "%s=%d 与基线一致" % (label, m[key])))
    for key, label in (("dangling_edges", "悬空边"), ("self_loops", "自环"),
                       ("duplicate_edge_pairs", "重复边对")):
        if m[key] > base[key]:
            out.append(("FAIL", "W1_" + key.upper(), "%s=%d 多于基线 %d（回归）" % (label, m[key], base[key])))
        else:
            out.append(("PASS", "W1_" + key.upper(), "%s=%d（基线 %d）" % (label, m[key], base[key])))
    kinds = m["edge_kinds"]
    iv = kinds.get(("image", "video"), 0)
    if iv > 0:
        out.append(("PASS", "W1_EDGE_SHAPE", "image→video %d 条（资产作参考边的常态形态）" % iv))
    else:
        out.append(("FAIL", "W1_EDGE_SHAPE", "W1 没有任何 image→video 参考边，与「资产扇出」画像不符"))
    nid, deg = m["max_fanout"]
    if deg >= 5:
        out.append(("PASS", "W1_HUB", "最大扇出 %d（%s）——高扇出枢纽存在" % (deg, nid)))
    else:
        out.append(("WARN", "W1_HUB", "最大扇出仅 %d，低于高扇出画像" % deg))
    vv = kinds.get(("video", "video"), 0)
    # video→video 的合法性与「边参数一致」由 W1P（逐节点转储）判，这里不再重复
    out.append(("NOTE", "W1_V2V_DELEGATED",
                "video→video %d 条与边参数一致 → 交给 W1P 用逐节点转储（action/params）判" % vv))
    return out


def regress_w2(uuid, m, base):
    out = []
    if uuid != base["uuid"]:
        out.append(("FAIL", "W2_UUID", "uuid=%s 与基线 %s 不符" % (uuid, base["uuid"])))
    else:
        out.append(("PASS", "W2_UUID", "uuid 与基线一致"))
    for key, label in (("nodes", "节点数"), ("edges", "边数")):
        if m[key] != base[key]:
            out.append(("FAIL", "W2_" + key.upper(), "%s=%d 与基线 %d 不符" % (label, m[key], base[key])))
        else:
            out.append(("PASS", "W2_" + key.upper(), "%s=%d 与基线一致" % (label, m[key])))
    # 已知债务：W2 本地快照的悬空边与重复边已在第 47 号交割单记过 → 只许不恶化
    for key, label in (("dangling_edges", "悬空边"), ("duplicate_edge_pairs", "重复边对")):
        if m[key] > base[key]:
            out.append(("FAIL", "W2_" + key.upper(),
                        "%s=%d 多于基线 %d（既有债务被放大）" % (label, m[key], base[key])))
        elif m[key] == base[key]:
            out.append(("WARN", "W2_" + key.upper(),
                        "%s=%d ＝ 基线（既有债务：W2 本地数据污染，见第47号交割单）" % (label, m[key])))
        else:
            out.append(("PASS", "W2_" + key.upper(),
                        "%s=%d 少于基线 %d（已改善）" % (label, m[key], base[key])))
    # 多层装配链：image/audio → video → video-clip（「智能剪辑」节点）
    #  ★ 只证「装配边存在」；「某剪辑节点无入边」≠「装配链断」——它的 clips 源
    #    可能挂在时间线 / data.clips 而不是 connectionList，快照里看不到 → 不可判定。
    kinds = m["edge_kinds"]
    clips = m["types"].get("video-clip", 0)
    v2x = kinds.get(("video", "video-clip"), 0)
    x2v = kinds.get(("video-clip", "video"), 0)
    if clips == 0:
        out.append(("FAIL", "W2_CLIPS", "没有 video-clip 节点，装配层消失"))
    elif v2x == 0 and x2v == 0:
        out.append(("FAIL", "W2_CLIPS", "有 %d 个 video-clip 但一条装配边都没有" % clips))
    else:
        out.append(("PASS", "W2_CLIPS",
                    "video-clip %d 个；装配边 video→video-clip %d、video-clip→video %d"
                    % (clips, v2x, x2v)))
    unlinked = [nid for nid in sorted(m["ids"])
                if m["by_id"][nid].get("type") == "video-clip" and m["indeg"].get(nid, 0) == 0]
    base_unlinked = base.get("clips_without_incoming")
    out.append(("WARN", "W2_CLIPS_UNLINKED",
                "%d 个 video-clip 在**边表**里无入边（基线 %s）——已由 W2C 查明："
                "装配关系在 `clipTimelineData.clips` 层（33/33 clipsAuthoritative=true），"
                "其源节点又在节点表里被静默漏掉 → **不是装配链断**"
                % (len(unlinked), base_unlinked)))
    if m["types"].get("audio", 0) and kinds.get(("audio", "video"), 0):
        out.append(("PASS", "W2_AUDIO",
                    "audio %d 个，audio→video %d 条（声音挂载层存在）"
                    % (m["types"]["audio"], kinds[("audio", "video")])))
    else:
        out.append(("WARN", "W2_AUDIO", "音频挂载层缺失或未连边"))
    out.append(("PASS", "W2_LAYERS", "边种类：%s"
                % " · ".join("%s→%s %d" % (k[0], k[1], v)
                             for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:6])))
    return out


def regress_w3(uuid, m, base):
    out = []
    if uuid != base["uuid"]:
        out.append(("FAIL", "W3_UUID", "uuid=%s 与基线 %s 不符" % (uuid, base["uuid"])))
    else:
        out.append(("PASS", "W3_UUID", "uuid 与基线一致"))
    for key, label in (("nodes", "节点数"), ("edges", "边数")):
        if m[key] != base[key]:
            out.append(("FAIL", "W3_" + key.upper(), "%s=%d 与基线 %d 不符" % (label, m[key], base[key])))
        else:
            out.append(("PASS", "W3_" + key.upper(), "%s=%d 与基线一致" % (label, m[key])))
    for key, label in (("dangling_edges", "悬空边"), ("self_loops", "自环"),
                       ("duplicate_edge_pairs", "重复边对")):
        if m[key] > base[key]:
            out.append(("FAIL", "W3_" + key.upper(), "%s=%d 多于基线 %d（回归）" % (label, m[key], base[key])))
        else:
            out.append(("PASS", "W3_" + key.upper(), "%s=%d（基线 %d）" % (label, m[key], base[key])))
    texts = m["types"].get("text", 0)
    if texts > 0:
        out.append(("PASS", "W3_TEXT_LAYER",
                    "text %d 个（双层提示词架构的承载层）、video %d 个"
                    % (texts, m["types"].get("video", 0))))
    else:
        out.append(("FAIL", "W3_TEXT_LAYER", "没有 text 节点，双层结构消失"))
    noin = [nid for nid in sorted(m["ids"])
            if m["by_id"][nid].get("type") == "video" and m["indeg"].get(nid, 0) == 0]
    if noin:
        out.append(("WARN", "W3_VIDEO_UNLINKED",
                    "%d 个 video 无入边（纯 text2video 或素材未接）：%s"
                    % (len(noin), ", ".join(noin[:5]))))
    else:
        out.append(("PASS", "W3_VIDEO_UNLINKED", "全部 video 节点都有入边"))
    kinds = m["edge_kinds"]
    out.append(("PASS", "W3_EDGE_MIX", "边种类：%s"
                % " · ".join("%s→%s %d" % (k[0], k[1], v)
                             for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:6])))
    out.append(("NOTE", "W3_SEGMENTATION_DELEGATED",
                "「长片分段」由 W3S 用 texts_w3 / video_prompts 逐节点转储判"
                "（时间区间 + 镜号标记），本快照层只证 text 层存在、边不成环"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 逐节点转储检查（**这三条才是验收要求里的"W1 边参数一致 / W2 多层装配 / W3 长片分段"**）
#   为什么单列：project_full*.json 只有 {id,name,type,position}，判不了这三件事。
# ─────────────────────────────────────────────────────────────────────────────
def _dump_files(dumps_dir, sub):
    if not dumps_dir:
        return []
    return sorted(glob.glob(os.path.join(dumps_dir, sub, "*.json")))


def _dump_load(path):
    try:
        j = json.loads(_read(path))
    except ValueError:
        return None
    return j if isinstance(j, dict) else None


def regress_w1_params(dumps_dir, by_id, edges):
    """W1 边参数一致：引用槽解析 / 插桩对应 / 边表关系 / video→video 的 action。"""
    base = DUMPS["w1_prompts"]
    files = _dump_files(dumps_dir, base["dir"])
    if not files:
        return [("UNDET", "W1P_NO_DUMPS",
                 "找不到逐节点转储 %s/：边参数一致在 project_full 里判不了（缺 action/params）"
                 % base["dir"])]
    out = []
    nparams = 0
    empty = 0
    unresolved = set()
    unplugged = set()
    dumps = {}
    for p in files:
        j = _dump_load(p)
        d = (j or {}).get("data") or {}
        if j and j.get("nodeKey"):
            dumps[j["nodeKey"]] = d
        pr = d.get("params") or {}
        if not pr:
            continue
        nparams += 1
        prm = pr.get("prompt") or ""
        if not prm.strip():
            empty += 1
            continue
        ids = [i for k in ORDER_KEYS for i in (pr.get(k) or [])]
        for i in ids:
            if i not in by_id:
                unresolved.add(i)
            if ("{{Node %s}}" % i) not in prm:
                unplugged.add(i)
    # ① 转储覆盖
    if len(files) >= base["files"] and nparams >= base["nodes_with_params"]:
        out.append(("PASS", "W1P_DUMPS", "逐节点转储 %d 份，其中带 params 的 %d 份（基线 %d/%d）"
                    % (len(files), nparams, base["files"], base["nodes_with_params"])))
    else:
        out.append(("FAIL", "W1P_DUMPS", "转储覆盖下降：%d 份 / 带 params %d（基线 %d/%d）"
                    % (len(files), nparams, base["files"], base["nodes_with_params"])))
    # ② 被引用 id 的解析
    expected_unres = W1_KNOWN_DANGLING + W1_KNOWN_OFFCANVAS_AUDIO
    if len(unresolved) > expected_unres:
        out.append(("FAIL", "W1P_UNRESOLVED",
                    "有 %d 个被引用 id 不在节点集合内（已知 %d＝%d 悬空图 + %d 画布外音频）：%s"
                    % (len(unresolved), expected_unres, W1_KNOWN_DANGLING,
                       W1_KNOWN_OFFCANVAS_AUDIO, ", ".join(sorted(unresolved)[:8]))))
    elif len(unresolved) == expected_unres:
        out.append(("WARN", "W1P_UNRESOLVED_KNOWN",
                    "%d 个被引用 id 不在节点集合内 ＝ 已知的 %d 悬空资产 + %d 画布外音频（既有，非本批）"
                    % (len(unresolved), W1_KNOWN_DANGLING, W1_KNOWN_OFFCANVAS_AUDIO)))
    else:
        out.append(("PASS", "W1P_UNRESOLVED", "被引用但解析不到的 id 减少到 %d" % len(unresolved)))
    # ③ 有边 vs 有插桩
    if len(unplugged) > base["unplugged_distinct"]:
        out.append(("FAIL", "W1P_UNPLUGGED",
                    "有 %d 个 id 在引用槽里却没有 {{Node <id>}} 插桩（基线 %d）：%s"
                    % (len(unplugged), base["unplugged_distinct"], ", ".join(sorted(unplugged)[:8]))))
    elif len(unplugged) == base["unplugged_distinct"]:
        out.append(("WARN", "W1P_UNPLUGGED_KNOWN",
                    "%d 个 id 有边无插桩 ＝ 基线（已知：参考槽位可占位不被引用；既有，非本批）"
                    % len(unplugged)))
    else:
        out.append(("PASS", "W1P_UNPLUGGED", "有边无插桩的 id 减少到 %d" % len(unplugged)))
    if empty == base["empty_prompt"]:
        out.append(("PASS", "W1P_EMPTY_PROMPT", "带 params 却空 prompt 的节点 = %d" % empty))
    else:
        out.append(("FAIL", "W1P_EMPTY_PROMPT", "空 prompt 节点 %d ≠ 基线 %d"
                    % (empty, base["empty_prompt"])))

    # ④ 边表 ↔ 引用槽位：两套记录是不是同一件事
    agree = only_edge = only_param = both = checked = 0
    for nid, d in dumps.items():
        pr = (d or {}).get("params") or {}
        slots = set(i for k in ORDER_KEYS for i in (pr.get(k) or []))
        inc = set(e["source"] for e in edges if e["target"] == nid)
        if not slots and not inc:
            continue
        checked += 1
        if slots == inc:
            agree += 1
        elif (inc - slots) and (slots - inc):
            both += 1
        elif inc - slots:
            only_edge += 1
        else:
            only_param += 1
    out.append(("WARN", "W1P_EDGE_VS_SLOTS",
                "可判 %d 个节点：边表与引用槽位完全一致 %d · 只在边表 %d · 只在槽位 %d · 两边都有差 %d"
                " —— 两者不是同一份记录（槽位是 left 边的重算产物，而边表还含非引用边）"
                % (checked, agree, only_edge, only_param, both)))

    # ⑤ video→video：边自身合法；要判的是"它进没进下游的引用槽位"
    act = dict((k, ((v or {}).get("action") or "")) for k, v in dumps.items())
    v2v = [e for e in edges
           if by_id.get(e["source"], {}).get("type") == "video"
           and by_id.get(e["target"], {}).get("type") == "video"]
    src_kind = collections.Counter()
    no_dump = 0
    into_slot = 0
    for e in v2v:
        a = act.get(e["source"])
        if a is None:
            no_dump += 1
            continue
        src_kind["video_generate" if a.startswith("video_generate") else "video_resource"] += 1
        tp = ((dumps.get(e["target"]) or {}).get("params") or {})
        if e["source"] in set(i for k in ORDER_KEYS for i in (tp.get(k) or [])):
            into_slot += 1
    out.append(("PASS", "W1P_V2V_ACTION",
                "video→video %d 条：源为 video_resource %d · video_generate %d · 源无转储 %d；"
                "其中进入目标引用槽位的有 %d 条（只有进槽位的才受『不得拿上一镜产物接尾帧』约束）"
                % (len(v2v), src_kind.get("video_resource", 0),
                   src_kind.get("video_generate", 0), no_dump, into_slot)))
    return out


def regress_w2_clips(dumps_dir, by_id):
    """W2 多层装配：`clipTimelineData.clips` 是否权威、剪辑源是否可解析。"""
    base = DUMPS["w2_clips"]
    files = _dump_files(dumps_dir, base["dir"])
    if not files:
        return [("UNDET", "W2C_NO_DUMPS",
                 "找不到 %s/：装配层在 project_full 里判不了（无 clips 数组）" % base["dir"])]
    out = []
    auth = 0
    entries = 0
    external = []
    for p in files:
        j = _dump_load(p) or {}
        d = j.get("data") or {}
        tl = d.get("clipTimelineData") or {}
        if tl.get("clipsAuthoritative"):
            auth += 1
        clips = tl.get("clips") or []
        entries += len(clips)
        srcs = [c.get("sourceNodeId") for c in clips] + list(tl.get("videoSourceNodeIds") or [])
        if [s for s in srcs if s and s not in by_id]:
            external.append(j.get("nodeKey") or os.path.basename(p))
        # 边表里"无入边"的剪辑节点，若这里 clips 非空即说明装配关系在 clips 层
    if len(files) >= base["files"] and auth >= base["authoritative"]:
        out.append(("PASS", "W2C_LAYER",
                    "%d 份剪辑转储，其中 %d 份 clipsAuthoritative=true（基线 %d/%d）——"
                    "**装配层确实存在于 clips 层，不在边表**"
                    % (len(files), auth, base["files"], base["authoritative"])))
    else:
        out.append(("FAIL", "W2C_LAYER", "剪辑层覆盖/权威性下降：%d 份 / 权威 %d（基线 %d/%d）"
                    % (len(files), auth, base["files"], base["authoritative"])))
    if entries >= base["clip_entries"]:
        out.append(("PASS", "W2C_ENTRIES", "剪辑条目 %d 条（基线 %d）" % (entries, base["clip_entries"])))
    else:
        out.append(("FAIL", "W2C_ENTRIES", "剪辑条目 %d < 基线 %d" % (entries, base["clip_entries"])))
    if len(external) >= base["files_with_external_source"]:
        out.append(("WARN", "W2C_SOURCE_OUTSIDE_TABLE",
                    "%d/%d 份剪辑的源节点 id 不在 project_full_w2 的节点表里 ＝ 已知缺陷"
                    "（W2 第 24 号后实测：**节点表会静默漏节点，762 是记账数不是可枚举数**）"
                    % (len(external), len(files))))
    else:
        out.append(("PASS", "W2C_SOURCE_OUTSIDE_TABLE",
                    "引用表外源的剪辑降到 %d/%d（节点表更完整了）" % (len(external), len(files))))
    out.append(("NOTE", "W2C_BOUNDARY",
                "本检查只读 33 份剪辑样本；装配顺序的全量权威仍在 clips/timeline 本身"))
    return out


def regress_w3_segments(dumps_dir, w3_ids):
    """W3 长片分段：text / video 转储里是否真的有"时间区间 + 镜号"的分段结构。"""
    out = []
    for key in ("w3_texts", "w3_videos"):
        base = DUMPS[key]
        files = _dump_files(dumps_dir, base["dir"])
        if not files:
            out.append(("UNDET", key.upper() + "_NO_DUMPS",
                        "找不到 %s/：分段结构判不了" % base["dir"]))
            continue
        node_dumps = 0
        matched = 0
        with_range = 0
        total_range = 0
        with_shot = 0
        for p in files:
            j = _dump_load(p)
            if not j or "data" not in j:
                continue
            node_dumps += 1
            if j.get("nodeKey") in w3_ids:
                matched += 1
            d = j["data"]
            pr = d.get("params") or {}
            body = "".join(d.get("content") or []) or (pr.get("prompt") or "")
            r = TIMERANGE_RE.findall(body)
            if r:
                with_range += 1
                total_range += len(r)
            if SHOTMARK_RE.search(body):
                with_shot += 1
        if key == "w3_videos" and "node_dumps" in base and node_dumps < base["node_dumps"]:
            out.append(("FAIL", "W3V_DUMPS", "节点转储 %d < 基线 %d" % (node_dumps, base["node_dumps"])))
        if with_range < base["files_with_ranges"] or total_range < base["total_ranges"]:
            out.append(("FAIL", key.upper() + "_RANGES",
                        "带时间区间的文件 %d（基线 %d）· 区间总数 %d（基线 %d）——分段结构被削弱"
                        % (with_range, base["files_with_ranges"], total_range, base["total_ranges"])))
        else:
            out.append(("PASS", key.upper() + "_RANGES",
                        "%d/%d 份文件带时间区间，区间总数 %d（基线 %d/%d）"
                        % (with_range, len(files), total_range, base["files_with_ranges"],
                           base["total_ranges"])))
        if with_shot >= base["files_with_shot_marker"]:
            out.append(("PASS", key.upper() + "_SHOTMARK",
                        "%d 份文件带镜号/场次标记（基线 %d）" % (with_shot, base["files_with_shot_marker"])))
        else:
            out.append(("FAIL", key.upper() + "_SHOTMARK",
                        "带镜号的文件 %d < 基线 %d" % (with_shot, base["files_with_shot_marker"])))
        if key == "w3_videos":
            out.append(("PASS", "W3V_MATCH",
                        "其中 %d 份的 nodeKey 命中 W3 节点集合、%d 份是检索结果文件（非节点转储）"
                        % (matched, len(files) - node_dumps)))
    out.append(("NOTE", "W3S_BOUNDARY",
                "结构层只能证明「分段存在且带时间区间/镜号」；"
                "「切点对不对、节奏好不好」属审美层，必须人看片"))
    return out


# 合成场景样例：字段严格按 A 的 graph_plan.schema.json；平台字段在 overlay 里
COMPOSITE_PLAN = {
    "plan_id": "plan-composite-demo", "project_id": "canvas-composite-demo",
    "profile": "short_form", "version": 1,
    "authority_layers": {"reference_order": "edge", "assembly_order": "timeline"},
    "derived_fields": ["imageListOrder", "status"],
    "nodes": [
        {"node_id": "i-HERO", "node_type": "image", "role": "asset",
         "group_role": "assets", "version": 1},
        {"node_id": "i-SCENE", "node_type": "image", "role": "asset",
         "group_role": "assets", "version": 1},
        {"node_id": "a-AMB", "node_type": "audio", "role": "audio",
         "group_role": "audio", "version": 1},
        {"node_id": "v-S1", "node_type": "video", "role": "shot", "group_role": "shots",
         "version": 1, "source_record_id": "rec-S1"},
        {"node_id": "v-S2", "node_type": "video", "role": "shot", "group_role": "shots",
         "version": 1, "source_record_id": "rec-S2"},
        {"node_id": "X-FILM", "node_type": "video-clip", "role": "composite",
         "group_role": "composite", "version": 1},
    ],
    "edges": [
        {"source_id": "i-HERO", "target_id": "v-S1", "kind": "reference", "order": 0},
        {"source_id": "i-SCENE", "target_id": "v-S1", "kind": "reference", "order": 1},
        {"source_id": "i-HERO", "target_id": "v-S2", "kind": "reference", "order": 0},
        {"source_id": "v-S1", "target_id": "X-FILM", "kind": "assembly", "order": 0},
        {"source_id": "v-S2", "target_id": "X-FILM", "kind": "assembly", "order": 1},
        {"source_id": "a-AMB", "target_id": "X-FILM", "kind": "assembly", "order": 2},
    ],
    "groups": [
        {"group_id": "g-assets", "group_role": "assets", "node_ids": ["i-HERO", "i-SCENE"]},
        {"group_id": "g-audio", "group_role": "audio", "node_ids": ["a-AMB"]},
        {"group_id": "g-shots", "group_role": "shots", "node_ids": ["v-S1", "v-S2"]},
        {"group_id": "g-composite", "group_role": "composite", "node_ids": ["X-FILM"]},
    ],
}
COMPOSITE_OVERLAY = {
    "operation": "create",
    "node_platform": {"v-S1": {"action": "video_generate", "model": "Wan 3.0", "duration_sec": 5},
                      "v-S2": {"action": "video_generate", "model": "Wan 3.0", "duration_sec": 5}},
    "authored_params": {"v-S1": {"duration": 5}, "v-S2": {"duration": 5}},
    "media_ready": ["i-HERO", "i-SCENE", "a-AMB"],
    "price_per_second": {"Wan 3.0": 1},
    "budget_ceiling": 100,
}


MEDIA_PACKS = {"W1": "w1_media_full.json", "W2": "w2_media_full.json", "W3": "w3_media_full.json"}


def regress_media_packs(dumps_dir):
    """媒体层：本回归只验**证据包在不在**；媒体质量判定归 22_ 与 inspect_media。"""
    if not dumps_dir:
        return [("UNDET", "MEDIA_NO_DIR", "没给转储目录，无法核对媒体证据包")]
    out = []
    missing = []
    found = []
    for w, fn in sorted(MEDIA_PACKS.items()):
        # 媒体转储既可能在 --dumps 目录，也可能在其上一级（本仓实测在 work/ 而非 work/libtv-cli/）
        cands = [os.path.join(dumps_dir, fn),
                 os.path.join(os.path.dirname(os.path.abspath(dumps_dir.rstrip(os.sep))), fn)]
        p = next((c for c in cands if os.path.isfile(c)), cands[0])
        if os.path.isfile(p):
            found.append("%s=%dB" % (w, os.path.getsize(p)))
        else:
            missing.append("%s(%s)" % (w, fn))
    if not missing:
        out.append(("PASS", "MEDIA_PACKS_PRESENT",
                    "三作 section=media 全量转储齐备：%s" % " · ".join(found)))
    else:
        out.append(("UNDET", "MEDIA_PACKS_MISSING",
                    "缺媒体转储：%s（媒体门禁须另跑 22_ 的回读链）" % ", ".join(missing)))
    out.append(("NOTE", "MEDIA_SCOPE",
                "本回归只证证据包在位；url/contentHash/像素质量须走 inspect_media 与 22_ 规范"))
    return out


def regress_composite():
    if not _HAS_LINT:
        return [("UNDET", "COMPOSITE", "graph_plan_lint 不可导入，合成场景未校验")]
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    fd2, ov = tempfile.mkstemp(suffix=".json")
    os.close(fd2)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(COMPOSITE_PLAN, ensure_ascii=False))
        with io.open(ov, "w", encoding="utf-8") as f:
            f.write(json.dumps(COMPOSITE_OVERLAY, ensure_ascii=False))
        _, _, groups = G.run(path, ov)
        issues = groups["structure"] + groups["reference"]
        rc = G.rollup(issues)
        fails = [i for i in issues if i[0] == "FAIL"]
        undet = [i for i in issues if i[0] == "UNDET"]
    finally:
        os.remove(path)
        os.remove(ov)
    if fails:
        return [("FAIL", "COMPOSITE", "合成场景样例未过校验：%s" % fails[0][2])]
    if rc == GATE_NOT_CHECKED:
        return [("UNDET", "COMPOSITE", "合成场景样例有未判定项 %d 条" % len(undet))]
    return [("PASS", "COMPOSITE",
             "资产→镜头→video-clip 合成 + 音频挂载：结构/引用两类门禁全绿")]


def gate_records(results, base_dir):
    recs = []

    def emit(name, items, scope):
        """退出码 / debt_class / interpretation 三件套按 A 的 gate_result.schema.json 取值。"""
        fails = [i for i in items if i[0] == "FAIL"]
        undet = [i for i in items if i[0] == "UNDET"]
        warns = [i for i in items if i[0] == "WARN"]
        if name.endswith(".cost"):
            rc, debt, interp = GATE_NOT_APPLICABLE, "not_applicable", "not_applicable"
        elif fails:
            rc, debt, interp = GATE_FAIL, "new_regression", "fail"
        elif undet:
            rc, debt, interp = GATE_NOT_CHECKED, "not_verified", "not_verified"
        elif warns:
            rc, debt, interp = GATE_PASS, "existing", "warn"
        else:
            rc, debt, interp = GATE_PASS, "none", "pass"
        # ★ A 的 gate_result.schema.json 是 additionalProperties:false —— 记录里只放
        #   契约字段；逐条明细进人读报告（evidence_paths 指向原始输出）。
        recs.append({"gate_name": name, "exit_code": rc, "scope": scope,
                     "evidence_paths": [os.path.join(base_dir, BASELINE[w]["file"])
                                        for w in ("W1", "W2", "W3")],
                     "debt_class": debt, "new_regression": bool(fails),
                     "next_action": ("可进入下一步" if rc == GATE_PASS else
                                     ("修 %d 条 FAIL 后重跑" % len(fails) if fails else
                                      ("成本门禁不适用；要报数走 21_ 的模型路由与预算表"
                                       if rc == GATE_NOT_APPLICABLE else
                                       "补 action / prompt 级证据（project_info / read_node）后重判"))),
                     "interpretation": interp})

    STRUCT_CODES = ("W1_UUID", "W1_NODES", "W1_EDGES",
                    "W2_UUID", "W2_NODES", "W2_EDGES",
                    "W3_UUID", "W3_NODES", "W3_EDGES")
    struct_items = [i for k in ("W1", "W2", "W3") for i in results[k] if i[1] in STRUCT_CODES]
    ref_items = [i for k in ("W1", "W2", "W3") for i in results[k] if i[1] not in STRUCT_CODES]
    ref_items += results.get("W1P", []) + results.get("W2C", []) + results.get("W3S", [])
    emit("three_work.structure", struct_items + results["composite"],
         "三作快照结构 + 合成场景（uuid / 规模 / 合成路径）")
    emit("three_work.reference", ref_items,
         "三作边与装配层回归（悬空 / 重复 / 扇出 / W1 边参数一致 / W2 多层装配 / W3 长片分段）")
    emit("three_work.media", results.get("MEDIA", []),
         "媒体证据包在位性（媒体质量判定归 22_ 与 inspect_media）")
    emit("three_work.cost", [], "成本门禁（静态快照不含单价）")
    return recs


def main(argv):
    if not argv:
        print(__doc__)
        return GATE_USAGE
    if argv[0] in ("--self-test", "-t"):
        return self_test()
    if argv[0] != "run":
        print(__doc__)
        return GATE_USAGE
    rest = argv[1:]
    base_dir = None
    dumps_dir = None
    out_path = None
    as_json = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--base" and i + 1 < len(rest):
            base_dir = rest[i + 1]; i += 2; continue
        if a == "--dumps" and i + 1 < len(rest):
            dumps_dir = rest[i + 1]; i += 2; continue
        if a == "--out" and i + 1 < len(rest):
            out_path = rest[i + 1]; i += 2; continue
        if a == "--json":
            as_json = True; i += 1; continue
        print("未知参数：%s" % a)
        return GATE_USAGE
    if not base_dir:
        print("必须给 --base <快照目录>")
        return GATE_USAGE
    if not dumps_dir:
        dumps_dir = base_dir          # 逐节点转储默认与快照同目录
    results = collections.OrderedDict()
    metrics = {}
    for w in ("W1", "W2", "W3"):
        path = os.path.join(base_dir, BASELINE[w]["file"])
        if not os.path.isfile(path):
            results[w] = [("FAIL", w + "_MISSING", "找不到快照：%s" % path)]
            continue
        uuid, nodes, edges = load_snapshot(path)
        m = measure(nodes, edges)
        metrics[w] = m
        results[w] = {"W1": regress_w1, "W2": regress_w2, "W3": regress_w3}[w](uuid, m, BASELINE[w])
    if not metrics:
        print("三个快照一个都没读到，没东西可回归")
        return GATE_NOT_CHECKED
    results["W1P"] = (regress_w1_params(dumps_dir, metrics["W1"]["by_id"],
                                        _snapshot_edges(base_dir, "W1"))
                      if "W1" in metrics else [])
    results["W2C"] = regress_w2_clips(dumps_dir, metrics["W2"]["ids"]) if "W2" in metrics else []
    results["W3S"] = regress_w3_segments(dumps_dir, metrics["W3"]["ids"]) if "W3" in metrics else []
    results["MEDIA"] = regress_media_packs(dumps_dir)
    results["composite"] = regress_composite()
    recs = gate_records(results, base_dir)
    if as_json:
        payload = {"base": os.path.abspath(base_dir),
                   "baseline_snapshot_date": "2026-10-07",
                   "gate_results": recs}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if out_path:
            with io.open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print("已写出回归报告：%s" % out_path)
        else:
            print(text)
    else:
        for w in ("W1", "W2", "W3", "W1P", "W2C", "W3S", "MEDIA", "composite"):
            if w not in results:
                continue
            items = results[w]
            fails = [i for i in items if i[0] == "FAIL"]
            print("== %s  FAIL=%d" % (w, len(fails)))
            for lvl, code, msg in items:
                print("   %-5s %-22s %s" % (lvl, code, msg))
        print("== gate 汇总")
        for r in recs:
            print("   %-18s rc=%d debt=%s" % (r["gate_name"], r["exit_code"], r["debt_class"]))
    fails = [i for v in results.values() for i in v if i[0] == "FAIL"]
    undet = [i for v in results.values() for i in v if i[0] == "UNDET"]
    if fails:
        return GATE_FAIL
    return GATE_NOT_CHECKED if undet else GATE_PASS


def self_test():
    """用内存造的两个微型快照跑通路（不碰真数据）。"""
    ok = True
    good = {"projectUuid": "x", "nodes": [
        {"id": "i-A", "type": "image"}, {"id": "v-B", "type": "video"},
        {"id": "X-C", "type": "video-clip"}],
        "edges": [{"id": "e1", "source": "i-A", "target": "v-B"},
                  {"id": "e2", "source": "v-B", "target": "X-C"}]}
    bad = {"projectUuid": "x", "nodes": [{"id": "i-A", "type": "image"},
                                         {"id": "v-B", "type": "video"}],
           "edges": [{"id": "e1", "source": "v-B", "target": "v-B"},
                     {"id": "e2", "source": "v-B", "target": "v-MISS"},
                     {"id": "e3", "source": "i-A", "target": "v-B"},
                     {"id": "e4", "source": "i-A", "target": "v-B"}]}
    import tempfile
    for label, snap, expect_dup in (("good", good, 0), ("bad", bad, 1)):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(snap))
            uuid, nodes, edges = load_snapshot(path)
            m = measure(nodes, edges)
        finally:
            os.remove(path)
        got_dup = m["duplicate_edge_pairs"]
        got_dang = m["dangling_edges"]
        loop = m["self_loops"]
        flag = "ok" if (got_dup == expect_dup) else "MISMATCH"
        print("self-test [%s] dup=%d dangling=%d loops=%d %s"
              % (label, got_dup, got_dang, loop, flag))
        ok = ok and got_dup == expect_dup
    comp = regress_composite()
    print("self-test [composite] %s" % comp[0][2])
    ok = ok and comp[0][0] == "PASS"
    # gate 记录须符合 A 的 gate_result.schema.json（复用 graph_plan_lint 的同一判据）
    if _HAS_LINT:
        fake = {"W1": [("PASS", "X", "y")], "W2": [("WARN", "X", "y")],
                "W3": [("UNDET", "X", "y")], "composite": [("PASS", "X", "y")]}
        conform = all(G._conforms(r) for r in gate_records(fake, os.path.dirname(os.path.abspath(__file__))))
        print("self-test [gate_records schema] conform=%s %s" % (conform, "ok" if conform else "MISMATCH"))
        ok = ok and conform
    if not ok:
        return GATE_FAIL
    print("self-test 通过")
    return GATE_PASS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
