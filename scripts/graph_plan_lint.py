#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_plan_lint —— 统一 graph plan 的只读静态门禁（C 路 · 2026-10-07）

★ 它是什么／不是什么
  它是**在点火之前跑的静态门禁**：把 A 路冻结的图不变量 + C 路的平台硬规则，
  变成可机检的判定。它**不是执行器**——**全脚本不含任何网络调用**
  （无 HTTP 客户端、无 MCP 工具调用、无子进程），
  **不联网、不建节点、不点火、不生成、不导出、不写画布**；
  唯一的写动作是显式 `--out` 落盘与自检用的临时文件。

★ 输入契约（**消费 A 的 schema，不改它**）
  · `--plan`  ：`outputs/统一基准/graph_plan.schema.json` 定义的 Graph Plan
     （`plan_id` / `project_id` / `profile` / `nodes` / `edges` / `groups` /
       `authority_layers` / `derived_fields` / `version`）。
  · `--overlay`：**C 路自己的**平台事实覆盖层（可选；A 的 schema 是
     `additionalProperties:false`，平台字段不允许塞进 plan，故单独一个文件）：
     ```json
     {"operation": "create|update",
      "node_platform": {"v-S1": {"action": "video_generate", "modeType": "mixed2video"}},
      "authored_params": {"v-S1": {"duration": 5}},
      "media_ready": ["i-HERO"],
      "price_per_second": {"Wan 3.0": 5},
      "budget_ceiling": 1000}
     ```

★ C 路新增的两张映射表（这是 A 的图语义落到平台层的唯一一步）
  · 节点类型：A 允许 `storyboard`，**平台 create_node 的 6 档里没有它** → 落成 `image`。
  · 边类型：`reference`→`left` 建边；`assembly`→`video-clip` 的 `left`/clips 顺序；
    `dependency` 与 `lineage` **不落平台边**（lineage 走纯文本血缘登记，见 §30.6 裁决）。

★ 退出码（与 A 的 `gate_result.schema.json` 对齐）
  0 通过 ｜ 1 检出问题 ｜ 2 用法错 ｜ 3 没验到（≠通过）｜ 5 不适用
  ★ 库内老脚本另有 `4=WARN`；本脚本不发 4。

用法：
  python3 scripts/graph_plan_lint.py validate --plan plan.json [--overlay ov.json] [--json]
  python3 scripts/graph_plan_lint.py gate     --plan plan.json [--overlay ov.json] [--out gate_results.json]
  python3 scripts/graph_plan_lint.py --self-test
"""
from __future__ import print_function

import io
import json
import os
import sys

RC_PASS, RC_FAIL, RC_USAGE, RC_NOT_VERIFIED, RC_NOT_APPLICABLE = 0, 1, 2, 3, 5

# ── A 的 schema 枚举（必须逐字对齐；改了要同步 graph_plan.schema.json） ──────────
PLAN_NODE_TYPES = ("text", "image", "video", "audio", "script", "storyboard",
                   "video-clip", "group")
PLAN_ROLES = ("source", "asset", "storyboard", "shot", "audio", "composite",
              "qa", "archive", "group")
EDGE_KINDS = ("reference", "dependency", "assembly", "lineage")
AUTHORITY_LAYERS = ("edge", "params", "timeline", "prompt", "ledger")
GROUP_ROLES = ("source", "assets", "storyboard", "shots", "audio", "composite",
               "qa", "archive")
PLAN_PROFILES = ("generic", "short_form", "mid_form", "long_form", "W1", "W2", "W3")

# ── C 路映射：A 的图语义 → 平台执行面 ────────────────────────────────────────
# 平台 create_node 的 nodeType 只有 6 档（doctor.toolRegistry 实测），没有 storyboard
TYPE_TO_PLATFORM = {"text": "text", "image": "image", "storyboard": "image",
                    "video": "video", "audio": "audio", "script": "script",
                    "video-clip": "video-clip", "group": "group"}

# 边类型 → 平台机制。None ＝ **不落平台边**（这是本库最容易被写错的一条）
KIND_TO_MECHANISM = {
    "reference": "create_node/update_node 的 left（leftAdd/leftEnsure/leftRemove）+ prompt 里 {{node_key}} 插桩",
    "assembly": "video-clip 节点的 left 顺序（或导出 clips 数组顺序）",
    "dependency": None,
    "lineage": None,
}
KIND_NEEDS_ORDER = ("reference", "assembly")

# 由平台/执行层重算 → 只读，不得当人工输入
WRITE_FORBIDDEN = ("imageList", "imageListOrder", "mixedList", "mixedListOrder",
                   "videoList", "videoListOrder", "audioList", "audioListOrder",
                   "textList", "textListOrder", "status", "taskInfo", "resourceMeta")

DEBT_BY_RC = {RC_PASS: "none", RC_FAIL: "new_regression", RC_NOT_VERIFIED: "not_verified",
              RC_NOT_APPLICABLE: "not_applicable"}
INTERP_BY_RC = {RC_PASS: "pass", RC_FAIL: "fail", RC_NOT_VERIFIED: "not_verified",
                RC_NOT_APPLICABLE: "not_applicable"}


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def platform_type(node):
    return TYPE_TO_PLATFORM.get((node.get("node_type") or "").strip())


# ─────────────────────────────────────────────────────────────────────────────
# 判据
# ─────────────────────────────────────────────────────────────────────────────
def check_structure(plan):
    """A §7.1/§7.3/§7.6 + C 节点类型映射。"""
    out = []
    nodes = plan.get("nodes") or []
    groups = plan.get("groups") or []
    if plan.get("profile") not in PLAN_PROFILES:
        out.append(("FAIL", "STRUCT_PROFILE", "profile=%r 不在 %s"
                    % (plan.get("profile"), " / ".join(PLAN_PROFILES))))
    seen = {}
    for n in nodes:
        nid, nt, role = n.get("node_id"), n.get("node_type"), n.get("role")
        if not nid:
            out.append(("FAIL", "STRUCT_NO_ID", "存在缺 node_id 的节点")); continue
        if nid in seen:
            out.append(("FAIL", "STRUCT_DUP_ID", "node_id 重复：%s" % nid))
        seen[nid] = n
        if nt not in PLAN_NODE_TYPES:
            out.append(("FAIL", "STRUCT_BAD_TYPE",
                        "%s node_type=%r 不在 %s" % (nid, nt, " / ".join(PLAN_NODE_TYPES))))
        if role not in PLAN_ROLES:
            out.append(("FAIL", "STRUCT_BAD_ROLE", "%s role=%r 不在 %s"
                        % (nid, role, " / ".join(PLAN_ROLES))))
        v = n.get("version")
        if not isinstance(v, int) or v < 1:
            out.append(("FAIL", "STRUCT_BAD_VERSION", "%s version=%r 须为 ≥1 的整数" % (nid, v)))
        if role == "shot" and not n.get("source_record_id"):
            out.append(("FAIL", "STRUCT_SHOT_NO_RECORD",
                        "%s 是 shot 但缺 source_record_id（A §7.6：每镜须能追溯 production_record）" % nid))
        gr = n.get("group_role")
        if gr is not None and gr not in GROUP_ROLES:
            out.append(("FAIL", "STRUCT_BAD_GROUP_ROLE",
                        "%s group_role=%r 不在 %s" % (nid, gr, " / ".join(GROUP_ROLES))))
    # 分组：成员必须存在；group_role 必须声明
    known_roles = dict((g.get("group_id"), g.get("group_role")) for g in groups)
    if len(known_roles) != len(groups):
        out.append(("FAIL", "STRUCT_DUP_GROUP_ID", "groups 里有重复或缺失的 group_id"))
    member_of = {}
    for g in groups:
        gid = g.get("group_id")
        if g.get("group_role") not in GROUP_ROLES:
            out.append(("FAIL", "STRUCT_GROUP_ROLE", "group %s group_role=%r 不在 %s"
                        % (gid, g.get("group_role"), " / ".join(GROUP_ROLES))))
        ids = g.get("node_ids") or []
        if len(set(ids)) != len(ids):
            out.append(("FAIL", "STRUCT_GROUP_DUP_MEMBER", "group %s 的 node_ids 有重复" % gid))
        for mid in ids:
            if mid not in seen:
                out.append(("FAIL", "STRUCT_GROUP_MEMBER_MISSING",
                            "group %s 的成员 %s 不是已声明节点" % (gid, mid)))
                continue
            member_of.setdefault(mid, []).append(gid)
            if seen[mid].get("group_role") != g.get("group_role"):
                out.append(("FAIL", "STRUCT_GROUP_ROLE_MISMATCH",
                            "%s 的 group_role=%r 与所在 group %s 的 %r 不一致"
                            % (mid, seen[mid].get("group_role"), gid, g.get("group_role"))))
        if not ids:
            out.append(("WARN", "STRUCT_EMPTY_GROUP", "group %s 无成员" % gid))
    for nid, n in seen.items():
        if n.get("node_type") == "group":
            continue
        gr = n.get("group_role")
        if gr is None:
            out.append(("WARN", "STRUCT_NO_GROUP", "%s 未声明 group_role（不属任何分区）" % nid))
        elif not member_of.get(nid):
            out.append(("FAIL", "STRUCT_NOT_IN_GROUP",
                        "%s 声明 group_role=%s 但不在任何 group 的 node_ids 里" % (nid, gr)))
    return out


def _video_action(node):
    """从节点（含 params/settings/model_config/overlay）提取视频动作三态。

    返回 (action, evidence)：
      "video_generate" —— 本节点产物是「生成」出来的视频，放进下游引用槽位＝平台禁止；
      "video_resource"  —— 平台资源型视频，可作参考素材；
      "unknown"        —— 找不到可验证 action，**不得**推定为安全资源（I-04）。
    """
    texts = []
    for key in ("action", "task_action", "op", "operation"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            texts.append(val)
    for holder_key in ("params", "settings", "model_config", "overlay", "meta"):
        holder = node.get(holder_key)
        if isinstance(holder, dict):
            for key in ("action", "task", "operation", "modeType", "mode_type"):
                val = holder.get(key)
                if isinstance(val, str) and val.strip():
                    texts.append(val)
    text = " ".join(texts).strip().lower()
    if not text:
        return "unknown", None
    if "video_generate" in text or "generate_video" in text or "text2video" in text or "image2video" in text:
        return "video_generate", text
    if "video_resource" in text or "resource" in text:
        return "video_resource", text
    return "unknown", text


def check_edges(plan):
    """A §7.2 + C 平台边合法性。"""
    out = []
    nodes = dict((n.get("node_id"), n) for n in (plan.get("nodes") or []) if n.get("node_id"))
    pairs = {}
    for e in (plan.get("edges") or []):
        s, t, kind = e.get("source_id"), e.get("target_id"), e.get("kind")
        if kind not in EDGE_KINDS:
            out.append(("FAIL", "EDGE_BAD_KIND", "边 %s→%s kind=%r 不在 %s"
                        % (s, t, kind, " / ".join(EDGE_KINDS)))); continue
        if s == t:
            out.append(("FAIL", "EDGE_SELF_LOOP", "自环边：%s（kind=%s）" % (s, kind))); continue
        miss = [x for x in (s, t) if x not in nodes]
        if miss:
            out.append(("FAIL", "EDGE_DANGLING", "边 %s→%s 端点不存在（缺 %s）"
                        % (s, t, ",".join(miss)))); continue
        pairs[(s, t, kind)] = pairs.get((s, t, kind), 0) + 1
        st, tt = platform_type(nodes[s]), platform_type(nodes[t])
        # mechanics：dependency / lineage 不落平台边
        if KIND_TO_MECHANISM[kind] is None:
            if platform_type(nodes[t]) == "group":
                out.append(("FAIL", "EDGE_LINEAGE_TO_GROUP",
                            "lineage 不得指向 group（%s→%s）：A §2 禁止用边表达归属" % (s, t)))
            continue
        if st == "group" or tt == "group":
            out.append(("FAIL", "EDGE_GROUP_AS_EDGE",
                        "%s→%s（kind=%s）：group 只表归属，不得出现在 %s 边里（A §2 禁止项）"
                        % (s, t, kind, kind)))
            continue
        if (st, tt) == ("video", "video"):
            # ★ 2026-10-07 修正：video→video **边本身合法**（三作实测 112/101/33 条真实存在）。
            #   平台管的是**引用槽位**：不要把上一镜的产物放进下游的引用槽位来接尾帧。
            #   所以只在 kind=="reference"（＝它确实是引用）时才判。
            if kind != "reference":
                out.append(("PASS", "EDGE_V2V_NONREF",
                            "%s→%s（kind=%s）：非引用边，合法（三作实测这类边大量存在）" % (s, t, kind)))
            else:
                action, evidence = _video_action(nodes[s])
                if action == "video_generate":
                    out.append(("FAIL", "EDGE_V2V_REF_FORBIDDEN",
                                "%s→%s：把 video_generate 的产物放进下游引用槽位（接尾帧）＝平台禁止；"
                                "要接尾帧请先截成 image 节点再引用" % (s, t)))
                elif action == "video_resource":
                    out.append(("PASS", "EDGE_V2V_RESOURCE",
                                "%s→%s：video_resource 当参考素材，合法" % (s, t)))
                else:
                    out.append(("UNDET", "EDGE_V2V_UNDETERMINED",
                                "%s→%s 是 reference 但 action 不可知（evidence=%r）：分不出 "
                                "video_resource（合法）与 video_generate（禁止入引用槽位）——不猜"
                                % (s, t, evidence)))
        if (st, tt) == ("video", "image") and kind == "reference":
            out.append(("FAIL", "EDGE_VIDEO_TO_IMAGE",
                        "%s→%s：video→image 参考边被禁（首尾帧血缘须先截成 image 节点）" % (s, t)))
    for (s, t, kind), cnt in sorted(pairs.items()):
        if cnt > 1:
            out.append(("FAIL", "EDGE_DUPLICATE",
                        "%s→%s(%s) 重复 %d 次（重复会放大权重或引发校验异常）" % (s, t, kind, cnt)))
    # 环（只算落平台边的两类 + dependency）——A §7.8「没有未标记的循环依赖」
    adj = {}
    for e in (plan.get("edges") or []):
        if e.get("source_id") in nodes and e.get("target_id") in nodes \
                and e.get("source_id") != e.get("target_id"):
            adj.setdefault(e["source_id"], []).append(e["target_id"])
    state = {}

    def walk(nid, stack):
        state[nid] = 1
        for nxt in adj.get(nid, []):
            if state.get(nxt) == 1:
                return stack + [nid, nxt]
            if state.get(nxt) is None:
                got = walk(nxt, stack + [nid])
                if got:
                    return got
        state[nid] = 2
        return None

    for nid in list(adj):
        if state.get(nid) is None:
            cyc = walk(nid, [])
            if cyc:
                out.append(("FAIL", "EDGE_CYCLE", "依赖成环：%s" % " → ".join(cyc)))
                break
    return out


def check_reference_order(plan):
    """A §7.4/§7.7 + C：顺序权威层必须声明，且 order 不得重复/跳号。"""
    out = []
    nodes = dict((n.get("node_id"), n) for n in (plan.get("nodes") or []) if n.get("node_id"))
    layers = plan.get("authority_layers") or {}
    by_target = {}
    for e in (plan.get("edges") or []):
        if e.get("kind") in KIND_NEEDS_ORDER:
            by_target.setdefault(e["target_id"], []).append(e)
    # 权威层按边类型取：reference 走 reference_order，assembly 走 assembly_order
    def layer_for(es):
        for key in ("reference_order", "reference", "assembly_order", "assembly", "order"):
            if layers.get(key):
                return layers[key]
        return ""

    for tid, es in sorted(by_target.items()):
        layer = layer_for(es)
        orders = [e.get("order") for e in es]
        if any(o is None for o in orders):
            out.append(("FAIL", "REF_ORDER_MISSING",
                        "%s 有 %d 条 %s 边但未给 order（权威层=%r）"
                        % (tid, len(es), "/".join(sorted(set(e["kind"] for e in es))), layer)))
            continue
        if layer not in ("edge", "params", "timeline", "prompt", "mixed"):
            out.append(("FAIL", "REF_AUTHORITY_UNSET",
                        "%s 的参考顺序未在 authority_layers 里声明权威层（A §4：不许靠猜）" % tid))
        if len(set(orders)) != len(orders):
            out.append(("FAIL", "REF_ORDER_DUP", "%s 的 order 有重复值 %s" % (tid, orders)))
        elif sorted(orders) != list(range(len(orders))):
            out.append(("FAIL", "REF_ORDER_GAP",
                        "%s 的 order=%s 不是 0..%d 的连续位次" % (tid, orders, len(orders) - 1)))
        # 平台位次＝建节点时 left 数组顺序，**事后不可重排** → 声明 edge 权威时必须显式
        if layer in ("edge", "mixed"):
            out.append(("WARN", "REF_ORDER_IMMUTABLE",
                        "%s 的参考位次由建节点时的 left 数组顺序决定，事后 leftAdd 排不到前面"
                        "（要换位只能重建节点，见 20_ 规范 §5）" % tid))
    return out


def check_derived(plan, overlay):
    """A §7.5 + C：派生字段只读；update 时把字段包进 params.settings 会被静默忽略。"""
    out = []
    declared = set(plan.get("derived_fields") or [])
    for n in (plan.get("nodes") or []):
        declared |= set(n.get("derived_fields") or [])
    unknown = sorted(d for d in declared if d not in WRITE_FORBIDDEN
                     and d not in ("derived_urls", "group_child_bounds"))
    if unknown:
        out.append(("WARN", "DERIVED_UNKNOWN", "声明了平台侧未见的派生字段：%s" % ", ".join(unknown)))
    if not overlay:
        out.append(("UNDET", "DERIVED_NO_OVERLAY",
                    "未给 --overlay：无法核对「params 是否直写派生字段」，也无法判 update 的 settings 陷阱"))
        return out
    op = (overlay.get("operation") or "").strip()
    for nid, params in sorted((overlay.get("authored_params") or {}).items()):
        if not isinstance(params, dict):
            continue
        bad = [k for k in WRITE_FORBIDDEN if k in params]
        if bad:
            out.append(("FAIL", "DERIVED_WRITTEN",
                        "%s 直写了派生字段 %s（应由 left/right 边重算；直写报 NODE_VALIDATION_FAILED）"
                        % (nid, ",".join(bad))))
        nested = params.get("settings")
        if isinstance(nested, dict) and nested:
            if op == "update":
                out.append(("FAIL", "PARAMS_NESTED_SETTINGS",
                            "%s 是 update 且把字段包进 params.settings —— 会被静默忽略"
                            "（update 的 params 是扁平补丁；实测据此白烧过一笔视频积分）" % nid))
            elif op != "create":
                out.append(("UNDET", "PARAMS_OP_UNKNOWN",
                            "%s 的 params 内嵌 settings，但 overlay 未声明 operation，无法判是否踩坑" % nid))
    return out


def check_media(plan, overlay):
    """媒体门禁：需要真实回读 url / inspect_media；静态计划只能给未验到。"""
    if not overlay or not overlay.get("media_ready"):
        return [("UNDET", "MEDIA_NOT_READ",
                 "静态计划不含媒体落盘事实（url/contentHash）；媒体验收须走 read_node / "
                 "export_readiness（见 22_ 规范）")]
    out = []
    ready = set(overlay["media_ready"])
    for e in (plan.get("edges") or []):
        if e.get("kind") == "reference" and e.get("source_id") not in ready:
            out.append(("FAIL", "MEDIA_SOURCE_NOT_READY",
                        "参考边来源 %s 未生效（平台要求：被引用节点必须已生效/有产物）"
                        % e.get("source_id")))
    return out


def check_cost(plan, overlay):
    """成本门禁：单价必须由外部带进来，**脚本不编单价**。"""
    if not overlay or not overlay.get("price_per_second") or overlay.get("budget_ceiling") is None:
        return [("NA", "COST_NO_PRICE",
                 "未给 price_per_second + budget_ceiling：脚本**不编积分单价**，成本不适用"
                 "（路由与量级见 21_ 规范；要算就给 overlay 补这两项）")]
    out = []
    total = 0.0
    for n in (plan.get("nodes") or []):
        if n.get("role") != "shot":
            continue
        plat = (overlay.get("node_platform") or {}).get(n.get("node_id")) or {}
        d = plat.get("duration_sec")
        model = plat.get("model")
        if d is None or model not in overlay["price_per_second"]:
            out.append(("UNDET", "COST_LINE_UNKNOWN",
                        "%s 缺 duration_sec 或 model 无单价 → 这一镜算不出来" % n.get("node_id")))
            continue
        total += float(d) * float(overlay["price_per_second"][model])
    ceiling = float(overlay["budget_ceiling"])
    if total > ceiling:
        out.append(("FAIL", "COST_OVER_BUDGET",
                    "估算 %.2f 超预算上限 %.2f（镜数=%d）"
                    % (total, ceiling, sum(1 for n in plan["nodes"] if n.get("role") == "shot"))))
    else:
        out.append(("PASS", "COST_WITHIN_BUDGET", "估算 %.2f ≤ 上限 %.2f" % (total, ceiling)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 输出
# ─────────────────────────────────────────────────────────────────────────────
SUITES = ("structure", "reference", "media", "cost")


def rollup(items):
    if any(i[0] == "FAIL" for i in items):
        return RC_FAIL
    if any(i[0] == "UNDET" for i in items):
        return RC_NOT_VERIFIED
    if items and all(i[0] == "NA" for i in items):
        return RC_NOT_APPLICABLE
    return RC_PASS


def gate_records(groups, evidence):
    recs = []
    for name in SUITES:
        items = groups[name]
        rc = rollup(items)
        recs.append({
            "gate_name": "graph_plan." + name,
            "exit_code": rc,
            "scope": {"structure": "图结构（节点类型/role/version/分组归属/分镜可追溯）",
                      "reference": "引用与顺序（边合法性/order/权威层/派生字段/成环）",
                      "media": "媒体落盘与引用生效（raw 回读）",
                      "cost": "生成成本估算（外部单价 + 预算上限）"}[name],
            "evidence_paths": [evidence],
            "debt_class": DEBT_BY_RC[rc],
            "new_regression": rc == RC_FAIL,
            "next_action": ("可进入下一步" if rc == RC_PASS else
                            ("修 %d 条 FAIL 后重跑" % sum(1 for i in items if i[0] == "FAIL")
                             if rc == RC_FAIL else
                             ("补齐 overlay / 回读证据后重跑" if rc == RC_NOT_VERIFIED
                              else "本阶段不适用，跳过后须在点火前补做"))),
            "interpretation": INTERP_BY_RC[rc],
        })
    return recs


def run(plan_path, overlay_path=None):
    plan = json.loads(_read(plan_path))
    if not isinstance(plan, dict):
        raise ValueError("graph plan 顶层须是 object")
    overlay = json.loads(_read(overlay_path)) if overlay_path else None
    groups = {
        "structure": check_structure(plan),
        "reference": check_edges(plan) + check_reference_order(plan) + check_derived(plan, overlay),
        "media": check_media(plan, overlay),
        "cost": check_cost(plan, overlay),
    }
    return plan, overlay, groups


def main(argv):
    if not argv:
        print(__doc__)
        return RC_USAGE
    if argv[0] in ("--self-test", "-t"):
        return self_test()
    cmd, rest = argv[0], argv[1:]
    if cmd not in ("validate", "gate"):
        print(__doc__)
        return RC_USAGE
    plan_path = overlay_path = out_path = None
    as_json = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--plan" and i + 1 < len(rest):
            plan_path = rest[i + 1]; i += 2; continue
        if a == "--overlay" and i + 1 < len(rest):
            overlay_path = rest[i + 1]; i += 2; continue
        if a == "--out" and i + 1 < len(rest):
            out_path = rest[i + 1]; i += 2; continue
        if a == "--json":
            as_json = True; i += 1; continue
        print("未知参数：%s" % a)
        return RC_USAGE
    if not plan_path or not os.path.isfile(plan_path):
        print("缺少或找不到 --plan：%s" % plan_path)
        return RC_USAGE
    try:
        plan, overlay, groups = run(plan_path, overlay_path)
    except ValueError as exc:
        print("计划不是合法 JSON：%s" % exc)
        return RC_USAGE
    if not plan.get("nodes"):
        print("计划里没有节点，没东西可校验")
        return RC_NOT_VERIFIED
    evidence = os.path.abspath(plan_path)
    if as_json or cmd == "gate":
        recs = gate_records(groups, evidence)
        payload = {"plan": evidence, "overlay": (os.path.abspath(overlay_path) if overlay_path else None),
                   "profile": plan.get("profile"), "nodes": len(plan.get("nodes") or []),
                   "edges": len(plan.get("edges") or []),
                   "gate_results": recs}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if out_path:
            with io.open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print("已写出 gate results：%s" % out_path)
        else:
            print(text)
    else:
        for name in SUITES:
            rc = rollup(groups[name])
            fails = sum(1 for i in groups[name] if i[0] == "FAIL")
            print("[%-9s] rc=%d FAIL=%d" % (name, rc, fails))
            for lvl, code, msg in groups[name]:
                print("   %-5s %-28s %s" % (lvl, code, msg))
    return rollup([i for name in SUITES for i in groups[name]])


# ─────────────────────────────────────────────────────────────────────────────
# 自检：顺带核对产出符合 A 的 gate_result.schema.json
# ─────────────────────────────────────────────────────────────────────────────
def _conforms(rec):
    if set(rec) - {"gate_name", "exit_code", "scope", "evidence_paths", "debt_class",
                   "new_regression", "next_action", "interpretation", "captured_at"}:
        return False
    req = ("gate_name", "exit_code", "scope", "evidence_paths", "debt_class",
           "new_regression", "next_action")
    if any(k not in rec for k in req):
        return False
    if rec["exit_code"] not in (0, 1, 2, 3, 4, 5):
        return False
    if rec["debt_class"] not in ("none", "existing", "new_regression", "not_verified",
                                 "not_applicable", "unknown"):
        return False
    if not isinstance(rec["evidence_paths"], list) or not rec["evidence_paths"]:
        return False
    if not isinstance(rec["new_regression"], bool):
        return False
    return rec.get("interpretation") in ("pass", "fail", "not_verified", "not_applicable", "warn")


GOOD = {
    "plan_id": "p-demo", "project_id": "canvas-demo", "profile": "generic", "version": 1,
    "authority_layers": {"reference_order": "edge", "assembly_order": "timeline"},
    "derived_fields": ["imageListOrder", "status"],
    "nodes": [
        {"node_id": "i-HERO", "node_type": "image", "role": "asset", "group_role": "assets", "version": 1},
        {"node_id": "a-AMB", "node_type": "audio", "role": "audio", "group_role": "audio", "version": 1},
        {"node_id": "v-S1", "node_type": "video", "role": "shot", "group_role": "shots",
         "version": 1, "source_record_id": "rec-1"},
        {"node_id": "X-FILM", "node_type": "video-clip", "role": "composite",
         "group_role": "composite", "version": 1},
    ],
    "edges": [
        {"source_id": "i-HERO", "target_id": "v-S1", "kind": "reference", "order": 0,
         "authority_layer": "edge"},
        {"source_id": "v-S1", "target_id": "X-FILM", "kind": "assembly", "order": 0,
         "authority_layer": "timeline"},
        {"source_id": "a-AMB", "target_id": "X-FILM", "kind": "assembly", "order": 1,
         "authority_layer": "timeline"},
    ],
    "groups": [
        {"group_id": "g-assets", "group_role": "assets", "node_ids": ["i-HERO"]},
        {"group_id": "g-audio", "group_role": "audio", "node_ids": ["a-AMB"]},
        {"group_id": "g-shots", "group_role": "shots", "node_ids": ["v-S1"]},
        {"group_id": "g-comp", "group_role": "composite", "node_ids": ["X-FILM"]},
    ],
}
GOOD_OVERLAY = {"operation": "create",
                "node_platform": {"v-S1": {"action": "video_generate", "model": "Wan 3.0",
                                           "duration_sec": 5}},
                "authored_params": {"v-S1": {"duration": 5}},
                "media_ready": ["i-HERO", "a-AMB"],
                "price_per_second": {"Wan 3.0": 1}, "budget_ceiling": 100}

BAD = {
    "plan_id": "p-bad", "project_id": "c", "profile": "generic", "version": 1,
    "authority_layers": {},
    "derived_fields": ["imageListOrder"],
    "nodes": [
        {"node_id": "i-A", "node_type": "png", "role": "asset", "version": 1},
        {"node_id": "v-C", "node_type": "video", "role": "shot", "version": 0,
         "group_role": "assets"},
        {"node_id": "v-C", "node_type": "video", "role": "nope", "version": 1},
    ],
    "edges": [
        {"source_id": "v-C", "target_id": "i-A", "kind": "reference", "order": 0},
        {"source_id": "v-C", "target_id": "v-NOPE", "kind": "reference", "order": 1},
        {"source_id": "i-A", "target_id": "i-A", "kind": "assembly"},
        {"source_id": "v-C", "target_id": "i-A", "kind": "widget"},
        {"source_id": "i-A", "target_id": "v-C", "kind": "reference", "order": 0},
        {"source_id": "i-A", "target_id": "v-C", "kind": "reference", "order": 0},
    ],
    "groups": [{"group_id": "g", "group_role": "assets", "node_ids": ["i-MISSING", "i-A", "i-A"]}],
}
BAD_OVERLAY = {"operation": "update",
               "authored_params": {"v-C": {"settings": {"duration": 5}, "imageListOrder": ["i-A"]}},
               "media_ready": []}


def _tmp(obj):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
    return path


def self_test():
    ok = True
    for label, plan, ov, expect in (("good", GOOD, GOOD_OVERLAY, RC_PASS),
                                    ("bad", BAD, BAD_OVERLAY, RC_FAIL)):
        pp, po = _tmp(plan), _tmp(ov)
        try:
            _, _, groups = run(pp, po)
            allitems = [i for name in SUITES for i in groups[name]]
            rc = rollup(allitems)
            recs = gate_records(groups, pp)
            conform = all(_conforms(r) for r in recs)
        finally:
            os.remove(pp); os.remove(po)
        got = {0: "PASS", 1: "FAIL", 3: "NOT_VERIFIED", 5: "NOT_APPLICABLE"}.get(rc, str(rc))
        flag = "ok" if (rc == expect and conform) else "MISMATCH"
        print("self-test [%s] expect=%d got=%s gate_records_schema_conform=%s %s"
              % (label, expect, got, conform, flag))
        ok = ok and rc == expect and conform
        if label == "bad":
            for lvl, code, msg in allitems:
                print("      %-5s %-28s %s" % (lvl, code, msg[:96]))
    print("self-test 通过" if ok else "self-test 失败")
    return RC_PASS if ok else RC_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
