#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可追溯资产清单：剧本拆解 → 四层资产 → 每镜引用计划（asset-system/2）。

为什么有它（asset-standard.md §9 / asset-pipeline.md §7）：
"剧本→资产清单→视角→投喂"此前没有可执行契约；清单靠人记，漏与多余都发现不了。
本脚本只做**结构裁决**：不看画面、不生成、不联网。

契约（与 schemas/asset_system.schema.json 同一套字段）：
  资产   asset_id · kind · subject · role · layer · version · status · origin · sha256
         · source · parent · variant/covers · qc_report_id
  镜头   id · scene · characters[] · props[] · camera · scale · reverse · reference_plan{assets[],reasons[]}
  旧名（id / derives_from / feed）仍可读，但会报 LEGACY_FIELD（迁移用，不是第二套模型）。

退出码：0 全过 ｜ 1 有 FAIL ｜ 2 用法错误 ｜ 3 没扫到资产（≠通过） ｜ 4 只有 WARN
用法：
  python scripts/asset_manifest.py breakdown.json --out manifest.json
  python scripts/asset_manifest.py --self-test [--fixtures DIR]
"""
from __future__ import print_function

import argparse
import copy
import glob
import hashlib
import io
import json
import os
import re
import sys

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = 0, 1, 2, 3, 4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "asset_manifest")
SCHEMA = os.path.join(ROOT, "schemas", "asset_system.schema.json")
CANON = "asset-system/2"

VIEWS = ("front", "back", "left", "right", "top")
FACE_VIEWS = {"front", "left", "right"}
STATUSES = {"draft", "review", "approved", "deprecated", "stale"}
ORIGINS = {"user", "approved_asset", "project_preset", "llm_inferred"}
ROLE_LAYER = {
    ("character", "face"): 1, ("character", "view"): 2, ("character", "body"): 2,
    ("prop", "anchor"): 1, ("prop", "closeup"): 2,
    ("scene", "plan"): 1, ("scene", "view"): 2,
}
ROLE_ALLOWED = {
    "character": {"face", "view", "body"},
    "prop": {"anchor", "closeup"},
    "scene": {"plan", "view"},
    "board": {"design"},
}
WIDE = {"大远景", "远景", "全景", "全身", "ELS", "LS", "FS", "wide", "full"}
CLOSE = {"大特写", "特写", "近景", "CU", "ECU", "close", "closeup"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _err(code, msg, **where):
    row = {"code": code, "message": msg}
    row.update({k: v for k, v in where.items() if v is not None})
    return row


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _list(doc, key):
    val = doc.get(key) or []
    if not isinstance(val, list):
        raise ValueError("%s 必须是数组" % key)
    return val


def _aid(a):
    return str(a.get("asset_id") or a.get("id") or "")


def _parent(a):
    return a.get("parent") or a.get("derives_from")


def _state(a, base):
    st = a.get("state")
    return None if st in (None, "", base) else str(st)


def _variant_list(a):
    covers = a.get("covers")
    if isinstance(covers, list) and covers:
        return [str(v) for v in covers]
    v = a.get("variant")
    return [str(v)] if v else []


def _face_count(a):
    role = str(a.get("role") or "")
    if role == "face":
        return 1
    if role == "view":
        return len([v for v in _variant_list(a) if v in FACE_VIEWS])
    return 0


def _slots(a, base):
    kind = str(a.get("kind") or "")
    role = str(a.get("role") or "anchor")
    subj = str(a.get("subject") or "")
    st = _state(a, base)
    if kind == "character" and role == "view":
        return [(kind, subj, role, st, v) for v in _variant_list(a)]
    if kind == "scene" and role == "view":
        return [(kind, subj, role, st, a.get("variant"))]
    return [(kind, subj, role, st, a.get("variant"))]


def _scale(sh):
    s = str(sh.get("scale") or "").strip()
    if s in WIDE:
        return "wide"
    if s in CLOSE:
        return "close"
    return s or "medium"


def _feed(sh):
    """返回 (资产 id 列表, plan)。None ＝ 只有选择意图 feed_plan，尚未解析。"""
    plan = sh.get("reference_plan")
    if isinstance(plan, dict) and isinstance(plan.get("assets"), list):
        return [str(x) for x in plan["assets"]], plan
    if isinstance(sh.get("feed"), list):
        return [str(x) for x in sh["feed"]], None
    if isinstance(sh.get("feed_plan"), list):
        return None, "feed_plan"
    return [], plan


def _lines(doc):
    lines = doc.get("script_lines")
    if lines is None:
        return None
    ids = set()
    for row in lines:
        if isinstance(row, dict) and row.get("id"):
            ids.add(str(row["id"]))
        elif isinstance(row, str):
            ids.add(row)
    return ids


# ---------------------------------------------------------------- ① 派生
def derive(doc):
    shots = _list(doc, "shots")
    chars = {str(c["id"]): c for c in _list(doc, "characters") if isinstance(c, dict) and c.get("id")}
    props = {str(p["id"]): p for p in _list(doc, "props") if isinstance(p, dict) and p.get("id")}
    scenes = {str(s["id"]): s for s in _list(doc, "scenes") if isinstance(s, dict) and s.get("id")}
    req = {}

    def need(kind, subject, role, state=None, variant=None, reason=""):
        key = (kind, subject, role, state, variant)
        if key not in req:
            req[key] = {"kind": kind, "subject": subject, "role": role,
                        "state": state, "variant": variant, "reason": reason}

    for cid, ch in chars.items():
        base = ch.get("base_state") or "基准"
        need("character", cid, "face", reason="脸部特写＝唯一脸源（L1，只一件）")
        states = [None] + [str(s) for s in (ch.get("states") or []) if s and str(s) != base]
        for st in states:
            for v in VIEWS:
                need("character", cid, "view", state=st, variant=v, reason="五视角（L2，随造型）")
            need("character", cid, "body", state=st, reason="无头身体（L2，随造型）")
    for pid, pr in props.items():
        need("prop", pid, "anchor", reason="主图＝工艺身份（L1）")
    for sid in scenes:
        need("scene", sid, "plan", reason="平面图＝空间母版（L1）")

    cameras = {}
    for sh in shots:
        sc = str(sh.get("scene") or "")
        cam = str(sh.get("camera") or "main")
        if _scale(sh) != "close":
            cameras.setdefault(sc, set()).add(cam)
        for pid in sh.get("props") or []:
            pr = props.get(str(pid)) or {}
            if _scale(sh) == "close" and pr.get("evidence"):
                need("prop", str(pid), "closeup", reason="物证特写需要近距版（L2）")
    for sc, cams in cameras.items():
        for cam in sorted(cams):
            need("scene", sc, "view", variant=cam, reason="分镜里出现的每个机位各一张（L2）")
    return list(req.values())


# ---------------------------------------------------------------- ② 对账
def reconcile(doc, required):
    out = []
    lines = _lines(doc)
    assets = [a for a in _list(doc, "assets") if isinstance(a, dict)]
    bases = {str(c["id"]): (c.get("base_state") or "基准")
             for c in _list(doc, "characters") if isinstance(c, dict) and c.get("id")}
    if any("id" in a and not a.get("asset_id") for a in assets) or \
       any(sh.get("feed") is not None and not isinstance(sh.get("reference_plan"), dict) for sh in _list(doc, "shots")) or \
       any(a.get("derives_from") and not a.get("parent") for a in assets):
        out.append(_err("LEGACY_FIELD",
                        "使用了旧字段 id/feed/derives_from：可读但已迁移，新文件请用 asset_id/reference_plan/parent",
                        level="warn"))

    face_of = {}
    for a in assets:
        if a.get("kind") == "character" and a.get("role") == "face":
            face_of.setdefault((str(a.get("subject")), _state(a, bases.get(str(a.get("subject")), "基准"))), _aid(a))

    for a in assets:
        aid = _aid(a)
        kind, role = str(a.get("kind") or ""), str(a.get("role") or "")
        if not aid:
            out.append(_err("ID_MISSING", "资产没有 asset_id"))
        if kind not in ROLE_ALLOWED:
            out.append(_err("KIND_UNKNOWN", "未知类型 %r（character/prop/scene/board）" % kind, asset=aid))
        elif role and role not in ROLE_ALLOWED[kind]:
            out.append(_err("ROLE_UNKNOWN", "%s 不允许 role=%r" % (kind, role), asset=aid))
        if a.get("design_board") and role != "design":
            out.append(_err("BOARD_MISLABELED", "design_board=true 但 role 不是 design", asset=aid))
        if role == "design":
            if a.get("layer") not in (None, 0):
                out.append(_err("BOARD_MISLABELED", "设计板不属于 L1/L2（layer 应为 0 或缺省）", asset=aid))
            continue
        if a.get("status") not in STATUSES:
            out.append(_err("STATUS_INVALID", "status 缺失或非法（draft/review/approved/deprecated/stale）", asset=aid))
        if a.get("origin") not in ORIGINS:
            out.append(_err("ORIGIN_INVALID", "origin 缺失或非法（user/approved_asset/project_preset/llm_inferred）", asset=aid))
        ver = a.get("version")
        if type(ver) is not int or ver < 1:
            out.append(_err("VERSION_INVALID", "version 必须是 ≥1 的整数", asset=aid))
        want = ROLE_LAYER.get((kind, role))
        if want is not None and a.get("layer") != want:
            out.append(_err("LAYER_MISMATCH", "%s/%s 必须属于 L%d（收到 %r）" % (kind, role, want, a.get("layer")), asset=aid))
        if a.get("status") == "approved" and not a.get("qc_report_id"):
            out.append(_err("QC_MISSING", "approved 资产必须有 qc_report_id（没有报告＝没验过）", asset=aid))
        sha = str(a.get("sha256") or "")
        if not HEX64.match(sha):
            out.append(_err("SHA_INVALID", "sha256 必须是 64 位小写十六进制（当前 %r）" % sha[:12], asset=aid))
        src = a.get("source")
        if not src:
            out.append(_err("TRACE_MISSING", "资产没有任何剧本出处", asset=aid))
        elif lines is not None and str(src) not in lines:
            out.append(_err("TRACE_UNKNOWN", "出处 %r 不在 script_lines 里" % src, asset=aid))

    have = {}
    for a in assets:
        if a.get("role") == "design":
            continue
        for key in _slots(a, bases.get(str(a.get("subject")), "基准")):
            if key in have and _aid(have[key]) != _aid(a):
                out.append(_err("DUP_ASSET", "同一槽位有两件资产：先定正本，另一件退役或改版本号",
                                asset=_aid(a), subject=a.get("subject")))
            have[key] = a

    l1 = {}
    for a in assets:
        if ROLE_LAYER.get((str(a.get("kind") or ""), str(a.get("role") or ""))) != 1:
            continue
        key = (str(a.get("subject")), str(a.get("role")), a.get("version"))
        prev = l1.get(key)
        if prev is not None and prev.get("sha256") != a.get("sha256"):
            out.append(_err("IMMUTABLE_CONFLICT",
                            "L1 同一版本出现两件不同内容（%s）：已批身份不可覆盖，改内容＝新版本号" % (key,),
                            asset=_aid(a), subject=a.get("subject")))
        l1.setdefault(key, a)

    for a in assets:
        if a.get("kind") == "character" and a.get("role") in ("view", "body"):
            subj = str(a.get("subject"))
            st = _state(a, bases.get(subj, "基准"))
            want = face_of.get((subj, st)) or face_of.get((subj, None))
            if not want or str(_parent(a) or "") != want:
                out.append(_err("PARENT_NOT_FACE",
                                "L2 视图/身体必须 parent 指向同一造型的脸部特写（期望 %r）" % want,
                                asset=_aid(a), subject=subj))
        if a.get("kind") == "scene" and a.get("role") == "view":
            plans = {_aid(p) for p in assets if p.get("kind") == "scene" and p.get("role") == "plan"
                     and str(p.get("subject")) == str(a.get("subject"))}
            if not plans or str(_parent(a) or "") not in plans:
                out.append(_err("DERIVE_MISSING", "机位视图没指向同空间的平面图（parent）",
                                asset=_aid(a), subject=a.get("subject"), level="warn"))

    req_keys = set()
    for r in required:
        req_keys.add((r["kind"], r["subject"], r["role"], r["state"], r["variant"]))
    seen_orphan = set()
    for k, a in have.items():
        if k not in req_keys and _aid(a) not in seen_orphan and not a.get("orphan_ok"):
            seen_orphan.add(_aid(a))
            out.append(_err("ORPHAN_ASSET", "镜头里不会以该视角/状态出现，属多余（asset-standard §2）",
                            asset=_aid(a), subject=a.get("subject")))
    for r in required:
        if (r["kind"], r["subject"], r["role"], r["state"], r["variant"]) not in have:
            out.append(_err("MISSING_ASSET",
                            "应有而未见：%s %s %s%s%s（%s）" % (
                                r["kind"], r["subject"], r["role"],
                                ("/" + r["state"]) if r["state"] else "",
                                ("@" + str(r["variant"])) if r["variant"] else "", r["reason"]),
                            subject=r["subject"]))
    if any(sh.get("reverse") for sh in _list(doc, "shots")):
        if not any(a.get("kind") == "scene" and a.get("role") == "view" and a.get("reverse") is True
                   for a in assets):
            out.append(_err("REVERSE_MISSING", "有反切镜，但没有朝向相反的机位视图（scene view reverse=true）"))
    return out


# ---------------------------------------------------------------- ③ 投喂
def _check_plan(sid, plan, feed, by_id, names):
    """引用计划自身是否可成立：主参考在首位、插桩一一对应、画布绑定与边序正确。"""
    out = []
    assets = [str(x) for x in (plan.get("assets") or [])]
    primary = plan.get("primary_asset_id")
    if primary is None:
        out.append(_err("PRIMARY_MISSING", "引用计划没有 primary_asset_id", shot=sid))
    elif not assets or str(primary) != assets[0]:
        out.append(_err("PRIMARY_MISMATCH",
                        "primary_asset_id 必须是 assets[0]（位置权重最高，见 asset-consistency §二）",
                        shot=sid, asset=str(primary)))
    if not plan.get("order_reason"):
        out.append(_err("ORDER_RULE_MISSING", "没有 order_reason：说不出为什么是这个顺序", shot=sid, level="warn"))
    refs = plan.get("prompt_refs")
    resolved = plan.get("resolved")
    if not isinstance(refs, list) or len(refs) != len(assets):
        out.append(_err("PROMPT_REFS_MISMATCH",
                        "prompt_refs 必须与 assets 一一对应（%d vs %d）" % (len(refs or []), len(assets)),
                        shot=sid))
    else:
        for i, r in enumerate(refs):
            want = "{{Image %d}}" % (i + 1)
            node_key = None
            if isinstance(resolved, list) and i < len(resolved) and isinstance(resolved[i], dict):
                node_key = resolved[i].get("node_key")
            if str(r) != want and not (node_key and str(r) == "{{%s}}" % node_key):
                out.append(_err("PROMPT_REFS_MISMATCH",
                                "第 %d 个插桩应是 %r（或 {{node_key}}）" % (i + 1, want), shot=sid))
    ff = plan.get("first_frame")
    if ff:
        if str(ff) not in assets:
            out.append(_err("FIRST_FRAME_NOT_IN_PLAN",
                            "first_frame=%s 不在 assets 里" % ff, shot=sid))
        elif assets[0] != str(ff):
            out.append(_err("FIRST_FRAME_NOT_FIRST",
                            "声明了首帧，但它不是 assets[0]（首帧必须第一）", shot=sid, asset=str(ff)))
    if names and assets and not ff:
        a0 = by_id.get(assets[0]) or {}
        has_scene = any((by_id.get(x) or {}).get("kind") == "scene"
                        and (by_id.get(x) or {}).get("role") == "view" for x in assets)
        if has_scene and not (a0.get("kind") == "scene" and a0.get("role") == "view"):
            out.append(_err("ORDER_SUSPECT",
                            "实测口径：空间/首帧应在第一位（当前第一是 %s）" % assets[0],
                            shot=sid, asset=assets[0], level="warn"))
    if primary and names:
        a = by_id.get(str(primary))
        if a is None or a.get("role") in ("body", "design") or a.get("kind") == "board":
            out.append(_err("PRIMARY_NOT_IDENTITY",
                            "主参考应是本镜的构图锚（首帧 / 空间 master / 主体），不能是无头身体或设计板",
                            shot=sid, asset=str(primary)))
    if not isinstance(resolved, list):
        out.append(_err("REFS_UNBOUND",
                        "还没有画布绑定（resolved: asset_id→node_key）：引用尚未成立", shot=sid, level="warn"))
        return out
    got = {str(x.get("asset_id")): x for x in resolved if isinstance(x, dict)}
    for i, aid in enumerate(assets):
        x = got.get(aid)
        if not x or not x.get("node_key"):
            out.append(_err("RESOLVED_MISSING", "assets[%d]=%s 没有画布绑定" % (i, aid), shot=sid, asset=aid))
            continue
        if x.get("effective") is not True:
            out.append(_err("REF_NOT_EFFECTIVE",
                            "节点未生效（无产物）：引用会失败，先让上游跑完", shot=sid, asset=aid))
        if x.get("image_index") != i + 1:
            out.append(_err("IMAGE_INDEX_MISMATCH",
                            "image_index 必须是 %d（left 边序＝imageListOrder）" % (i + 1), shot=sid, asset=aid))
    return out


def check_feeds(doc, assets):
    out = []
    mode = str(doc.get("platform_mode") or "flat").lower()
    by_id = {_aid(a): a for a in assets if _aid(a)}
    unresolved = 0
    for sh in _list(doc, "shots"):
        sid = str(sh.get("id") or "")
        feed, plan = _feed(sh)
        if feed is None:          # 只有 feed_plan（选择意图），站 5.5 还没解析成 asset_id
            unresolved += 1
            continue
        if not feed:
            out.append(_err("FEED_EMPTY", "该镜没有任何投喂资产", shot=sid))
            continue
        names = [str(x) for x in (sh.get("characters") or [])]
        props = [str(x) for x in (sh.get("props") or [])]
        scene = str(sh.get("scene") or "")
        if isinstance(plan, dict):
            out.extend(_check_plan(sid, plan, feed, by_id, names))
        faces, has_scene, has_prop, has_body = {}, False, False, False
        char_assets = {n: 0 for n in names}
        only_body = {n: True for n in names}
        body_of = {n: False for n in names}
        for aid in feed:
            a = by_id.get(aid)
            if a is None:
                out.append(_err("FEED_UNKNOWN", "投喂了清单里不存在的资产 %r" % aid, shot=sid))
                continue
            kind, role = str(a.get("kind")), str(a.get("role") or "")
            subj = str(a.get("subject") or "")
            if a.get("status") not in (None, "approved"):
                out.append(_err("FEED_UNAPPROVED", "资产 %s 状态 %r：只有 approved 能进参考" % (aid, a.get("status")),
                                shot=sid, asset=aid, subject=a.get("subject")))
            if a.get("design_board") or role == "design":
                out.append(_err("DESIGN_IN_FEED", "设计板/网格/带字图不得进参考",
                                shot=sid, asset=aid, subject=a.get("subject")))
            if kind == "scene":
                if role == "plan":
                    out.append(_err("PLAN_IN_FEED", "平面图是布局母版，不当画面参考（要空镜请用该机位的 view）",
                                    shot=sid, asset=aid))
                    continue
                has_scene = True
                if subj != scene:
                    out.append(_err("FEED_FOREIGN", "投喂了别的空间的图（%s ≠ %s）" % (subj, scene), shot=sid, asset=aid))
            elif kind == "character":
                if subj not in names:
                    out.append(_err("FEED_FOREIGN", "投喂了本镜不出场的角色 %s" % subj, shot=sid, asset=aid))
                    continue
                char_assets[subj] += 1
                if role != "body":
                    only_body[subj] = False
                n = _face_count(a)
                if n:
                    faces[subj] = faces.get(subj, 0) + n
                if role == "body" or (role == "view" and "front" in _variant_list(a)):
                    has_body = True
                    body_of[subj] = True
            elif kind == "prop":
                if subj not in props:
                    out.append(_err("FEED_FOREIGN", "投喂了本镜不入画的道具 %s" % subj, shot=sid, asset=aid))
                    continue
                has_prop = True
        for subj in names:
            if char_assets.get(subj, 0) == 0:
                out.append(_err("FEED_THIN", "角色 %s 在本镜没有任何参考图" % subj, shot=sid, subject=subj))
            elif only_body.get(subj):
                out.append(_err("FEED_BODY_ONLY", "角色 %s 只挂了无头身体（无脸无视角）：只适用于剪影/极远景" % subj,
                                shot=sid, subject=subj, level="warn"))
        for subj, n in faces.items():
            if n > 1 and mode == "flat":
                out.append(_err("FACE_BATCH", "同一身份在一批里有 %d 张脸；合并图也按视角个数计" % n,
                                shot=sid, subject=subj))
        if props and not has_prop:
            if _scale(sh) == "close":
                out.append(_err("PROP_MISSING_IN_CLOSE", "道具特写必须挂该道具的资产", shot=sid))
            elif _scale(sh) != "wide":
                out.append(_err("FEED_PROP_ANCHOR", "道具入画但没挂道具资产（陈设/环境可略）",
                                shot=sid, level="warn"))
        if _scale(sh) == "wide":
            for subj in names:
                if not body_of.get(subj):
                    out.append(_err("FEED_NO_BODY", "全景/远景镜里角色 %s 没挂身体基准" % subj,
                                    shot=sid, subject=subj, level="warn"))
        if len(feed) > 4:
            out.append(_err("REF_OVERLOAD", "本镜投喂 %d 张，超过 2–4 张为宜" % len(feed),
                            shot=sid, level="warn"))
        if _scale(sh) != "close" and not has_scene:
            out.append(_err("SCENE_MISSING_IN_FEED", "非特写镜必须挂本空间的一个机位视图（平面图不算）", shot=sid))
    if unresolved:
        out.append(_err("FEED_PLAN_UNRESOLVED",
                        "%d 镜只有 feed_plan（选择意图），尚未解析成 reference_plan.assets：站 5.5 用 §2 的规则解析后再对账" % unresolved,
                        level="warn"))
    return out


# ---------------------------------------------------------------- 主流程
def analyze(doc):
    required = derive(doc)
    assets = [a for a in _list(doc, "assets") if isinstance(a, dict)]
    violations = reconcile(doc, required) + check_feeds(doc, assets)
    fails = [v for v in violations if v.get("level") != "warn"]
    return {
        "title": doc.get("title"),
        "required": sorted(required, key=lambda r: (r["kind"], r["subject"], r["role"],
                                                   r["state"] or "", str(r["variant"] or ""))),
        "counts": {"required": len(required),
                   "planned": len([a for a in assets if a.get("role") != "design"]),
                   "shots": len(_list(doc, "shots")),
                   "fail": len(fails),
                   "warn": len(violations) - len(fails)},
        "violations": violations,
        "ok": not fails,
    }


def _tup(v):
    return (v.get("code"), v.get("shot") or "", v.get("asset") or "", v.get("subject") or "")


def run(path, out_path=None, strict_trace=False):
    doc = load(path)
    if not isinstance(doc, dict):
        raise ValueError("拆解文件必须是 JSON 对象")
    if strict_trace and doc.get("script_lines") is None:
        print("[FAIL] --strict-trace 需要 script_lines")
        return RC_FAIL
    res = analyze(doc)
    if res["counts"]["shots"] == 0 and res["counts"]["planned"] == 0:
        print("[EMPTY] 既没有镜头也没有资产：没验到 ≠ 验过了")
        return RC_EMPTY
    text = json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True)
    if out_path:
        with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)
    if res["counts"]["fail"]:
        return RC_FAIL
    return RC_WARN if res["counts"]["warn"] else RC_OK


# ---------------------------------------------------------------- 自检
ALL_CODES = None


def _codes(res):
    return {v["code"] for v in res["violations"]}


def _split(res):
    fail = sorted(_tup(v) for v in res["violations"] if v.get("level") != "warn")
    warn = sorted(_tup(v) for v in res["violations"] if v.get("level") == "warn")
    return fail, warn


def _sha(tag):
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


def _base_doc():
    """干净的最小工程：1 角色 / 1 道具 / 1 空间 / 1 镜 / 10 件资产。"""
    assets = [
        {"asset_id": "C1F", "kind": "character", "subject": "C1", "role": "face", "layer": 1,
         "version": 1, "status": "approved", "origin": "user", "sha256": _sha("C1F"), "source": "M11.1",
         "parent": None, "qc_report_id": "qc-C1F"},
    ]
    for v in VIEWS:
        assets.append({"asset_id": "C1V" + v[0].upper(), "kind": "character", "subject": "C1",
                       "role": "view", "variant": v, "layer": 2, "version": 1, "status": "approved",
                       "origin": "user", "sha256": _sha("C1V" + v), "source": "M11.1",
                       "parent": "C1F", "qc_report_id": "qc-C1V" + v})
    assets += [
        {"asset_id": "C1B", "kind": "character", "subject": "C1", "role": "body", "layer": 2,
         "version": 1, "status": "approved", "origin": "user", "sha256": _sha("C1B"),
         "source": "M11.1", "parent": "C1F", "qc_report_id": "qc-C1B"},
        {"asset_id": "P1A", "kind": "prop", "subject": "P1", "role": "anchor", "layer": 1,
         "version": 1, "status": "approved", "origin": "user", "sha256": _sha("P1A"),
         "source": "M11.5", "parent": None, "qc_report_id": "qc-P1A"},
        {"asset_id": "S1P", "kind": "scene", "subject": "S1", "role": "plan", "layer": 1,
         "version": 1, "status": "approved", "origin": "user", "sha256": _sha("S1P"),
         "source": "M7.S1", "parent": None, "qc_report_id": "qc-S1P"},
        {"asset_id": "S1VA", "kind": "scene", "subject": "S1", "role": "view", "variant": "A",
         "layer": 2, "version": 1, "status": "approved", "origin": "user", "sha256": _sha("S1VA"),
         "source": "M7.S1", "parent": "S1P", "qc_report_id": "qc-S1VA"},
    ]
    return {
        "schema_version": CANON, "title": "mutation-base", "platform_mode": "flat",
        "script_lines": ["M11.1", "M11.5", "M7.S1"],
        "characters": [{"id": "C1", "name": "她", "states": ["基准"], "source": "M11.1"}],
        "props": [{"id": "P1", "name": "搪瓷杯", "class": "handheld", "evidence": False, "source": "M11.5"}],
        "scenes": [{"id": "S1", "name": "办公室", "states": ["日"], "source": "M7.S1"}],
        "shots": [{"id": "SH1", "scene": "S1", "characters": ["C1"], "props": [],
                   "camera": "A", "scale": "中景",
                   "reference_plan": {"selector_policy_version": "ref_v1",
                                      "primary_asset_id": "S1VA",
                                      "assets": ["S1VA", "C1F"],
                                      "order_reason": "空间 master 第一（成片口径）；人物第二",
                                      "prompt_refs": ["{{Image 1}}", "{{Image 2}}"],
                                      "resolved": [
                                          {"asset_id": "S1VA", "node_key": "n1", "image_index": 1, "effective": True},
                                          {"asset_id": "C1F", "node_key": "n2", "image_index": 2, "effective": True}],
                                      "reasons": ["face_visible"], "capability_check": "PASSED"}}],
        "assets": assets,
    }


def _mutations():
    def m(fn):
        return fn
    out = []

    def add(name, code, fn):
        out.append((name, code, fn))

    def asset(doc, aid):
        return next(a for a in doc["assets"] if _aid(a) == aid)

    add("ID_MISSING", "ID_MISSING", lambda d: asset(d, "C1VF").update(asset_id=""))
    add("KIND_UNKNOWN", "KIND_UNKNOWN", lambda d: asset(d, "C1VF").update(kind="vehicle"))
    add("ROLE_UNKNOWN", "ROLE_UNKNOWN", lambda d: asset(d, "C1VF").update(role="plan"))
    add("BOARD_MISLABELED", "BOARD_MISLABELED", lambda d: asset(d, "C1B").update(design_board=True))
    add("STATUS_INVALID", "STATUS_INVALID", lambda d: asset(d, "C1F").update(status="ok"))
    add("ORIGIN_INVALID", "ORIGIN_INVALID", lambda d: asset(d, "C1F").update(origin="web"))
    add("VERSION_INVALID", "VERSION_INVALID", lambda d: asset(d, "C1F").update(version=0))
    add("LAYER_MISMATCH", "LAYER_MISMATCH", lambda d: asset(d, "C1F").update(layer=2))
    add("QC_MISSING", "QC_MISSING", lambda d: asset(d, "C1F").pop("qc_report_id"))
    add("SHA_INVALID", "SHA_INVALID", lambda d: asset(d, "C1F").update(sha256="abc"))
    add("TRACE_MISSING", "TRACE_MISSING", lambda d: asset(d, "C1F").pop("source"))
    add("TRACE_UNKNOWN", "TRACE_UNKNOWN", lambda d: asset(d, "C1F").update(source="M99"))
    add("DUP_ASSET", "DUP_ASSET", lambda d: d["assets"].append(
        {"asset_id": "C1VL2", "kind": "character", "subject": "C1", "role": "view", "variant": "left",
         "layer": 2, "version": 1, "status": "approved", "origin": "user", "sha256": _sha("C1VL2"),
         "source": "M11.1", "parent": "C1F", "qc_report_id": "qc-C1VL2"}))
    add("IMMUTABLE_CONFLICT", "IMMUTABLE_CONFLICT", lambda d: d["assets"].append(
        {"asset_id": "C1F2", "kind": "character", "subject": "C1", "role": "face", "layer": 1,
         "version": 1, "status": "approved", "origin": "user", "sha256": _sha("C1F2"),
         "source": "M11.1", "parent": None, "qc_report_id": "qc-C1F2"}))
    add("PARENT_NOT_FACE", "PARENT_NOT_FACE", lambda d: asset(d, "C1VL").update(parent="S1P"))
    add("DERIVE_MISSING", "DERIVE_MISSING", lambda d: asset(d, "S1VA").update(parent=None))
    add("MISSING_ASSET", "MISSING_ASSET", lambda d: d.update(
        assets=[a for a in d["assets"] if _aid(a) != "C1VT"]))
    add("ORPHAN_ASSET", "ORPHAN_ASSET", lambda d: d["assets"].append(
        {"asset_id": "C1VQ", "kind": "character", "subject": "C1", "role": "view", "variant": "three_quarter",
         "layer": 2, "version": 1, "status": "approved", "origin": "user", "sha256": _sha("C1VQ"),
         "source": "M11.1", "parent": "C1F", "qc_report_id": "qc-C1VQ"}))
    add("FEED_EMPTY", "FEED_EMPTY", lambda d: d["shots"][0]["reference_plan"].update(assets=[]))
    add("FEED_UNKNOWN", "FEED_UNKNOWN", lambda d: d["shots"][0]["reference_plan"].update(assets=["NOPE"]))
    add("FEED_UNAPPROVED", "FEED_UNAPPROVED", lambda d: asset(d, "C1F").update(status="draft"))
    add("DESIGN_IN_FEED", "DESIGN_IN_FEED", lambda d: (
        d["assets"].append({"asset_id": "BD1", "kind": "board", "subject": "C1", "role": "design",
                            "layer": 0, "design_board": True, "version": 1, "status": "draft",
                            "origin": "user", "sha256": _sha("BD1"), "source": "M11.1", "parent": None}),
        d["shots"][0]["reference_plan"]["assets"].append("BD1")))
    add("PLAN_IN_FEED", "PLAN_IN_FEED", lambda d: d["shots"][0]["reference_plan"]["assets"].append("S1P"))
    add("FEED_FOREIGN", "FEED_FOREIGN", lambda d: (
        d["characters"].append({"id": "C2", "name": "他", "states": ["基准"], "source": "M11.2"}),
        d["script_lines"].append("M11.2"),
        [d["assets"].append({"asset_id": "C2F", "kind": "character", "subject": "C2", "role": "face",
                             "layer": 1, "version": 1, "status": "approved", "origin": "user",
                             "sha256": _sha("C2F"), "source": "M11.2", "parent": None,
                             "qc_report_id": "qc-C2F"}) for _ in (0,)],
        d["shots"][0]["reference_plan"]["assets"].append("C2F")))
    add("FACE_BATCH", "FACE_BATCH", lambda d: d["shots"][0]["reference_plan"]["assets"].append("C1VF"))
    add("FEED_THIN", "FEED_THIN", lambda d: d["shots"][0]["reference_plan"].update(assets=["S1VA"]))
    add("FEED_BODY_ONLY", "FEED_BODY_ONLY", lambda d: d["shots"][0]["reference_plan"].update(assets=["C1B", "S1VA"]))
    add("REF_OVERLOAD", "REF_OVERLOAD", lambda d: d["shots"][0]["reference_plan"].update(
        assets=["C1F", "C1VF", "C1VB", "C1VL", "S1VA"]))
    add("SCENE_MISSING_IN_FEED", "SCENE_MISSING_IN_FEED", lambda d: d["shots"][0]["reference_plan"].update(assets=["C1F"]))
    add("REVERSE_MISSING", "REVERSE_MISSING", lambda d: d["shots"][0].update(reverse=True))
    add("PROP_MISSING_IN_CLOSE", "PROP_MISSING_IN_CLOSE", lambda d: (
        d["shots"][0].update(props=["P1"], scale="特写"),
        d["shots"][0]["reference_plan"].update(assets=["C1F"])))
    add("FEED_PROP_ANCHOR", "FEED_PROP_ANCHOR", lambda d: (
        d["shots"][0].update(props=["P1"]),
        d["shots"][0]["reference_plan"].update(assets=["C1F", "S1VA"])))
    add("FEED_NO_BODY", "FEED_NO_BODY", lambda d: (
        d["shots"][0].update(scale="全景"),
        d["shots"][0]["reference_plan"].update(assets=["C1F", "S1VA"])))
    add("PRIMARY_MISSING", "PRIMARY_MISSING", lambda d: d["shots"][0]["reference_plan"].pop("primary_asset_id"))
    add("PRIMARY_MISMATCH", "PRIMARY_MISMATCH", lambda d: d["shots"][0]["reference_plan"].update(primary_asset_id="C1F"))
    add("FIRST_FRAME_NOT_FIRST", "FIRST_FRAME_NOT_FIRST", lambda d: d["shots"][0]["reference_plan"].update(first_frame="C1F"))
    add("FIRST_FRAME_NOT_IN_PLAN", "FIRST_FRAME_NOT_IN_PLAN", lambda d: d["shots"][0]["reference_plan"].update(first_frame="NOPE"))
    add("ORDER_SUSPECT", "ORDER_SUSPECT", lambda d: (
        d["shots"][0]["reference_plan"].update(assets=["C1F", "S1VA"]),
        d["shots"][0]["reference_plan"].update(prompt_refs=["{{Image 1}}", "{{Image 2}}"]),
        d["shots"][0]["reference_plan"].update(resolved=[
            {"asset_id": "C1F", "node_key": "n2", "image_index": 1, "effective": True},
            {"asset_id": "S1VA", "node_key": "n1", "image_index": 2, "effective": True}])))
    add("PRIMARY_NOT_IDENTITY", "PRIMARY_NOT_IDENTITY", lambda d: (
        d["shots"][0]["reference_plan"].update(primary_asset_id="C1B"),
        d["shots"][0]["reference_plan"].update(assets=["C1B", "S1VA"]),
        d["shots"][0]["reference_plan"].update(prompt_refs=["{{Image 1}}", "{{Image 2}}"]),
        d["shots"][0]["reference_plan"].update(resolved=[
            {"asset_id": "C1B", "node_key": "n1", "image_index": 1, "effective": True},
            {"asset_id": "S1VA", "node_key": "n2", "image_index": 2, "effective": True}])))
    add("PROMPT_REFS_MISMATCH", "PROMPT_REFS_MISMATCH", lambda d: d["shots"][0]["reference_plan"].update(
        prompt_refs=["{{Image 2}}", "{{Image 1}}"]))
    add("REF_NOT_EFFECTIVE", "REF_NOT_EFFECTIVE", lambda d: d["shots"][0]["reference_plan"]["resolved"][0].update(effective=False))
    add("IMAGE_INDEX_MISMATCH", "IMAGE_INDEX_MISMATCH", lambda d: d["shots"][0]["reference_plan"]["resolved"][0].update(image_index=2))
    add("RESOLVED_MISSING", "RESOLVED_MISSING", lambda d: d["shots"][0]["reference_plan"].update(resolved=[
        {"asset_id": "S1VA", "node_key": "n2", "image_index": 2, "effective": True}]))
    add("REFS_UNBOUND", "REFS_UNBOUND", lambda d: d["shots"][0]["reference_plan"].pop("resolved"))
    add("ORDER_RULE_MISSING", "ORDER_RULE_MISSING", lambda d: d["shots"][0]["reference_plan"].pop("order_reason"))
    add("FEED_PLAN_UNRESOLVED", "FEED_PLAN_UNRESOLVED", lambda d: (
        d["shots"][0].pop("reference_plan"),
        d["shots"][0].update(feed_plan=[{"asset_id": "C1", "role": "face", "why": "选择意图"}])))
    add("LEGACY_FIELD", "LEGACY_FIELD", lambda d: (
        asset(d, "C1F").update(id="C1F"), asset(d, "C1F").pop("asset_id"),
        d["shots"][0].update(feed=["C1F", "C1VF", "S1VA"]), d["shots"][0].pop("reference_plan")))
    return out


def _schema_errors(doc, schema):
    try:
        import jsonschema
    except ImportError:
        return None
    validator = jsonschema.Draft202012Validator(schema)
    payload = {k: v for k, v in doc.items() if k != "expected"}
    return ["%s: %s" % ("/".join(str(p) for p in e.path) or "$", e.message)
            for e in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))]


def self_test(fixtures_dir=None, schema_path=None):
    fixtures_dir = fixtures_dir or FIXTURES
    files = sorted(glob.glob(os.path.join(fixtures_dir, "*.json")))
    if not files:
        print("没有 fixtures：%s" % fixtures_dir)
        return RC_USAGE
    bad = 0
    seen = set()
    schema = None
    sp = schema_path or SCHEMA
    if os.path.isfile(sp):
        schema = load(sp)

    # 1) 四个叙事样例：比完整元组，不只比 code
    for path in files:
        doc = load(path)
        expected = doc.get("expected") or {}
        res = analyze(doc)
        got_f, got_w = _split(res)
        exp_f = sorted(tuple(x) for x in expected.get("fail", []))
        exp_w = sorted(tuple(x) for x in expected.get("warn", []))
        name = os.path.basename(path)
        ok = got_f == exp_f and got_w == exp_w
        seen |= {v["code"] for v in res["violations"]}
        if schema is not None:
            errs = _schema_errors(doc, schema)
            if errs is None:
                ok = False
                bad += 1
                print("[FAIL] %-34s schema 未检查（jsonschema 未安装，契约未验 ≠ 通过）" % name)
            elif errs:
                ok = False
                print("[FAIL] %-34s schema %d 条：%s" % (name, len(errs), errs[0]))
        if not ok:
            bad += 1
            print("[FAIL] %-34s fail=%s warn=%s" % (name, got_f, got_w))
            if got_f != exp_f:
                print("        期望 fail=%s" % (exp_f,))
            if got_w != exp_w:
                print("        期望 warn=%s" % (exp_w,))
        else:
            print("[PASS] %-34s fail=%d warn=%d" % (name, len(got_f), len(got_w)))

    # 2) 变异矩阵：每个错误码至少一个可复现样例
    base = _base_doc()
    base_res = analyze(base)
    if base_res["counts"]["fail"] or base_res["counts"]["warn"]:
        bad += 1
        print("[FAIL] mutation-base 不干净：%s" % (sorted(_tup(v) for v in base_res["violations"]),))
    for name, code, fn in _mutations():
        doc = copy.deepcopy(base)
        fn(doc)
        res = analyze(doc)
        seen |= _codes(res)
        if code not in _codes(res):
            bad += 1
            print("[FAIL] mutation %-24s 未产出 %s（得到 %s）" % (name, code, sorted(_codes(res))))
    print("自检：%d 例 fixture + %d 例变异；%d 失败" % (len(files), len(_mutations()), bad))

    # 3) 覆盖：所有声明的错误码都必须被至少一个样例触发
    missing = sorted(c for c in ALL_CODES if c not in seen)
    if missing:
        bad += 1
        print("[FAIL] 未被任何样例覆盖的错误码：%s" % "、".join(missing))
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="可追溯资产清单（asset-standard.md §9 / asset-system/2）")
    ap.add_argument("breakdown", nargs="?", help="剧本拆解 JSON")
    ap.add_argument("--out", help="把 manifest 写到这个路径")
    ap.add_argument("--strict-trace", action="store_true", help="必须有 script_lines 才允许通过")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--fixtures", help="自检用的 fixture 目录")
    ap.add_argument("--schema", help="自检用的 schema 路径")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test(args.fixtures, args.schema)
    if not args.breakdown:
        ap.print_help()
        return RC_USAGE
    if not os.path.isfile(args.breakdown):
        print("找不到文件：%s" % args.breakdown)
        return RC_USAGE
    try:
        return run(args.breakdown, args.out, args.strict_trace)
    except ValueError as exc:
        print("拆解文件不合法：%s" % exc)
        return RC_USAGE


ALL_CODES = {
    "ID_MISSING", "KIND_UNKNOWN", "ROLE_UNKNOWN", "BOARD_MISLABELED", "STATUS_INVALID",
    "ORIGIN_INVALID", "VERSION_INVALID", "LAYER_MISMATCH", "QC_MISSING", "SHA_INVALID",
    "TRACE_MISSING", "TRACE_UNKNOWN", "DUP_ASSET", "IMMUTABLE_CONFLICT", "PARENT_NOT_FACE",
    "DERIVE_MISSING", "MISSING_ASSET", "ORPHAN_ASSET", "LEGACY_FIELD",
    "FEED_EMPTY", "FEED_UNKNOWN", "FEED_UNAPPROVED", "DESIGN_IN_FEED", "PLAN_IN_FEED",
    "FEED_FOREIGN", "FACE_BATCH", "FEED_THIN", "FEED_BODY_ONLY", "REF_OVERLOAD",
    "SCENE_MISSING_IN_FEED", "REVERSE_MISSING", "PROP_MISSING_IN_CLOSE", "FEED_PROP_ANCHOR",
    "FEED_NO_BODY", "FEED_PLAN_UNRESOLVED",
    "PRIMARY_MISSING", "PRIMARY_MISMATCH", "PRIMARY_NOT_IDENTITY", "ORDER_RULE_MISSING",
    "FIRST_FRAME_NOT_IN_PLAN", "FIRST_FRAME_NOT_FIRST", "ORDER_SUSPECT",
    "PROMPT_REFS_MISMATCH", "REFS_UNBOUND", "RESOLVED_MISSING", "REF_NOT_EFFECTIVE",
    "IMAGE_INDEX_MISMATCH",
}

if __name__ == "__main__":
    sys.exit(main())
