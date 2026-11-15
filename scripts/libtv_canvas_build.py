#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「资产清单」一步建成画布：节点 + 资产内派生边 + 每镜投喂边（零提醒）。

为什么有它：用户只会丢一份剧本说"生成"，不会提醒"人物要七件""六件要挂脸""投喂要按顺序"。
本工具把 asset-standard / asset-pipeline 的规则变成**默认执行链**：

  ① 校验清单（七件齐、L2 有 parent、每镜 ≤1 张脸、无设计板）
  ② 按依赖序建节点：L1（脸/主图/平面图）→ L2（五视角/无头/机位）
  ③ 建**资产内边**：L2 ← L1（modeType=image2image）；机位 ← 平面图
  ④ 建**镜头边**：视频 ← reference_plan.assets（顺序即 imageListOrder）
  ⑤ 回读校验：每条边的 imageListOrder 是否与计划一致

默认 **dry-run**（只打印命令，不改画布）；写入必须 `--apply --yes`。
不点火：只建节点与边，不触发任何生成。

用法：
  python scripts/libtv_canvas_build.py plan.json --dry-run
  python scripts/libtv_canvas_build.py plan.json --apply --yes --name "雪与热土_1-5"
  python scripts/libtv_canvas_build.py --verify-only <project_uuid> plan.json
退出码：0 成功 ｜ 1 校验/回读失败 ｜ 2 用法错误 ｜ 3 环境缺失（无 libtv）
"""
from __future__ import print_function

import argparse
import json
import math
import re
from graphlib import CycleError, TopologicalSorter
import os
import subprocess
import sys

try:
    from .asset_manifest import _state
except ImportError:
    from asset_manifest import _state

RC_OK, RC_FAIL, RC_USAGE, RC_ENV, RC_WARN = 0, 1, 2, 3, 4
try:
    from .apply_libtv_plan import (resolve_libtv_binary, _detail_key, _existing_nodes,
                                   _geometry, _node_name, _node_params, _setting_value)
    from .compile_libtv_commands import build_binding_map
except ImportError:
    from apply_libtv_plan import (resolve_libtv_binary, _detail_key, _existing_nodes,
                                  _geometry, _node_name, _node_params, _setting_value)
    from compile_libtv_commands import build_binding_map

LIBTV = str(resolve_libtv_binary())
ROLE_CN = {"face": "脸部特写", "body": "无头身体", "anchor": "主图", "closeup": "近距版",
           "plan": "平面图", "design": "设计板"}
VIEW_CN = {"front": "前视", "back": "后视", "left": "左视", "right": "右视", "top": "俯视"}
FACE_VIEWS = {"front", "left", "right"}


def _run(args):
    try:
        r = subprocess.run([LIBTV] + args, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RC_ENV, {"_raw": "LibTV CLI unavailable or connection timed out: %s. "
                       "See docs/LIBTV_SETUP.md for installation and login." % exc}
    out = r.stdout.decode("utf-8", "replace").strip()
    if not out:
        err = r.stderr.decode("utf-8", "replace").strip()
        return r.returncode, {"_raw": err or "(empty)"}
    try:
        return r.returncode, json.loads(out)
    except ValueError:
        return r.returncode, {"_raw": out[:400]}


def _names(doc):
    """subject id → 展示名（人物/道具/场景）。"""
    out = {}
    for key in ("characters", "props", "scenes"):
        for row in doc.get(key) or []:
            if row.get("id"):
                out[str(row["id"])] = str(row.get("name") or row["id"])
    return out


def _prompt_text(value):
    """提示词：没有就是没有，不能变成字符串 "None"。

    设计板（role=design）合法地没有提示词（校验对它们豁免），但它们照样要建节点；
    无条件 str() 会把 "None" 写进画布，并让回读比对拿 "None" 当期望值。
    """
    if isinstance(value, str):
        return value if value.strip() else None
    return None


def node_name(a, names):
    subj = names.get(str(a.get("subject")), str(a.get("subject")))
    role = str(a.get("role") or "")
    if role == "view":
        tag = VIEW_CN.get(str(a.get("variant")), str(a.get("variant") or "视角"))
    else:
        tag = ROLE_CN.get(role, role)
    state = a.get("state")
    return "资产_%s_%s%s" % (subj, tag, ("_" + str(state)) if state else "")


def video_name(sh):
    return "镜头_%s" % sh.get("id")


PURPOSE = {"face": "面部身份", "body": "身体基准", "anchor": "道具外观",
           "closeup": "道具细节", "plan": "空间布局"}


def _join(*parts):
    return "，".join([str(x).strip() for x in parts if x and str(x).strip()])


def _labelled(label, value):
    """带标签的事实：值里已经写了这个标签就不再重复加一次。

    真机组装实测（2026-11-12）：height="层高约三米" 会变成 "层高层高约三米"。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    text = str(value).strip()
    return text if text.startswith(label) else label + text


def _block(f):
    """40–70 字身份锚点：全部物理事实，不写气质。"""
    who = []
    if f.get("age"):
        # 只在年龄是纯数字时补"岁"：事实自带单位（如"二十岁上下"）再加一次会变成
        # "二十岁上下岁"（2026-11-12 真机组装实测）。
        age = str(f["age"]).strip()
        who.append("%s岁" % age if age.isdigit() else age)
    if f.get("ethnicity") or f.get("gender"):
        gen = str(f.get("gender") or "")
        if gen in ("男", "女"):
            gen += "性"
        who.append("%s%s" % (f.get("ethnicity") or "", gen))
    return _join("，".join(who), f.get("face"), f.get("hair"), f.get("marks"), f.get("clothing"))


def _compose_one(a, names):
    """从 facts 组装这件资产的提示词；缺必填事实返回 (None, 缺失列表)。"""
    f = a.get("facts") or {}
    kind, role = a.get("kind"), a.get("role")
    if kind == "character":
        need = [k for k in ("age", "face", "hair", "clothing") if not f.get(k)]
        if need:
            return None, need
        if role == "view" and a.get("covers"):
            views = a["covers"]
            if (not isinstance(views, list)
                    or any(not isinstance(view, str) or view not in VIEW_CN for view in views)
                    or len(set(views)) != len(views)):
                return None, ["covers 必须是有效且不重复的视角列表"]
            parts = []
            for view in views:
                single = dict(a, variant=view)
                single.pop("covers")
                prompt, missing = _compose_one(single, names)
                if missing:
                    return None, missing
                parts.append(("【%s区域】" % VIEW_CN[view] if len(views) > 1 else "") + prompt)
            if len(parts) == 1:
                return parts[0], []
            return _join("同一画布、同背景同平光，无分格线，各视角保持同一身份与服装", *parts), []
        blk = _block(f)
        body = f.get("body") or f.get("height") or ""
        v = a.get("variant") if role == "view" else role
        if role == "face":
            return _join(blk, "胸以上，正对镜头，85mm 感，中性表情，双耳可见",
                         "正面平光，18% 中性灰底，无投影"), []
        if v == "front":
            return _join(blk, "正面全身，双臂自然下垂，双脚并拢", body,
                         "中性灰底、平光无影"), []
        if v == "back":
            return _join(blk, "背面全身，不回头", "后脑发缝与后领、衣摆自然下垂",
                         "任何面部不可见", "中性灰底、平光"), []
        if v in ("left", "right"):
            side = "正左侧90度" if v == "left" else "正右侧90度（镜像）"
            return _join(blk, side, "视线正前，侧缝与肩线可见", "中性灰底、平光"), []
        if v == "top":
            return _join(blk, "正上方90度垂直俯拍，两臂微张不遮躯干",
                         "发旋、肩线、鞋面可见", "无面部", "光从相机方向来"), []
        if role == "body":
            return _join(blk, "去头，保留完整头顶留白", "领口结构、服装轮廓、体型",
                         "无头无颈无发，切口干净，无模糊无残端"), []
        return None, ["role:%s" % role]
    if kind == "prop":
        need = [k for k in ("material", "era") if not f.get(k)]
        wear = [w for w in (f.get("wear") or []) if w]
        if len(wear) < 3:
            need.append("wear>=3")
        if need:
            return None, need
        if role == "closeup":
            return _join("%s近距" % (f.get("name") or ""), "逐处写脏：" + "、".join(wear),
                         "浅景深，柔光"), []
        return _join(f.get("name"), f.get("material"), f.get("era"),
                     "逐处写脏：" + "、".join(wear), f.get("scale"),
                     "柔光，底部接触阴影"), []
    if kind == "scene":
        if role == "plan":
            need = [k for k in ("walls", "floor", "size", "openings", "fingerprint") if not f.get(k)]
            if need:
                return None, need
            return _join("俯视正投影平面图：" + str(f.get("walls")), str(f.get("size")),
                         _labelled("层高", f.get("height")),
                         _labelled("进深", f.get("depth")),
                         str(f.get("openings")), _labelled("地面", f.get("floor")),
                         "无透视、无人、无文字",
                         _labelled("空间指纹：", f.get("fingerprint"))), []
        need = [k for k in ("walls", "floor", "fingerprint") if not f.get(k)]
        if need:
            return None, need
        return _join("内景，%s 方向" % (a.get("variant") or "主"), str(f.get("walls")),
                     _labelled("地面", f.get("floor")),
                     _labelled("可见空间指纹：", f.get("fingerprint")),
                     "空镜无人物", "正面平光"), []
    return None, ["kind:%s" % kind]


def _shot_prompt(sh, assets_by_id, names):
    """镜头提示词：brief + 按顺序的"图N只供X"声明。"""
    brief = sh.get("brief") or ""
    if not brief:
        return None
    ids = list((sh.get("reference_plan") or {}).get("assets") or [])
    decls = []
    for i, aid in enumerate(ids, 1):
        a = assets_by_id.get(aid) or {}
        role = a.get("role")
        if a.get("kind") == "scene":
            tag = "空间与光位"
        elif role == "view":
            tag = "该朝向的结构与服装"
        elif role == "body":
            tag = "身体比例"
        else:
            tag = PURPOSE.get(role, "参考")
        decls.append("图%d只供%s" % (i, tag))
    return (brief.rstrip("。") + "。" + "，".join(decls) + "。") if decls else brief


def compose_all(doc):
    """补全 assets[].prompt 与 shots[].prompt；返回未解清单。"""
    names = _names(doc)
    unresolved = []
    assets = doc.get("assets") or []
    by_id = {a.get("asset_id"): a for a in assets}
    for a in assets:
        if a.get("role") == "design" or a.get("prompt"):
            continue
        p, missing = _compose_one(a, names)
        if p:
            a["prompt"] = p
        else:
            unresolved.append({"asset_id": a.get("asset_id"), "missing": missing})
    for sh in doc.get("shots") or []:
        if sh.get("prompt"):
            continue
        p = _shot_prompt(sh, by_id, names)
        if p:
            sh["prompt"] = p
        else:
            unresolved.append({"shot": sh.get("id"), "missing": ["brief"]})
    return unresolved


def _identity_errors(doc):
    errors = []
    if not isinstance(doc, dict):
        return ["清单必须是 JSON 对象"]
    for collection, key in (("characters", "id"), ("props", "id"), ("scenes", "id"),
                            ("assets", "asset_id"), ("shots", "id")):
        rows = doc.get(collection, [])
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            errors.append("%s 必须是列表" % collection)
            continue
        seen = set()
        for row in rows:
            identifier = row.get(key) if isinstance(row, dict) else None
            if not isinstance(identifier, str) or not identifier.strip():
                errors.append("%s 包含无效的 %s" % (collection, key))
            elif identifier in seen:
                errors.append("%s 包含重复的 %s %s" % (collection, key, identifier))
            else:
                seen.add(identifier)
    return errors


def _ordered_assets(doc):
    errors = _identity_errors(doc)
    if errors:
        raise ValueError("\n".join(errors))
    assets = doc.get("assets") or []
    base = [a for a in assets if a.get("layer") == 1 or a.get("role") in ("face", "anchor", "plan")]
    base_ids = {a["asset_id"] for a in base}
    ordered = base + [a for a in assets if a["asset_id"] not in base_ids]
    by_id = {a["asset_id"]: a for a in assets}
    graph = {}
    for asset in ordered:
        parent = asset.get("parent")
        if parent is None or parent == "":
            graph[asset["asset_id"]] = []
            continue
        if not isinstance(parent, str) or parent not in by_id:
            raise ValueError("%s 的 parent 无效或不存在" % asset["asset_id"])
        graph[asset["asset_id"]] = [parent]
    try:
        return [by_id[aid] for aid in TopologicalSorter(graph).static_order()]
    except CycleError as exc:
        raise ValueError("资产存在循环依赖：%s" % exc) from exc


def _asset_names(doc):
    names = _names(doc)
    preferred = {a["asset_id"]: node_name(a, names) for a in doc.get("assets") or []}
    return build_binding_map({"nodes": [{"id": aid} for aid in preferred]}, preferred)


def validate(doc):
    """返回 (错误列表, 警告列表)。错误＝不许建。"""
    errs, warns = _identity_errors(doc), []
    if errs:
        return errs, warns
    for entry in (doc.get("assets") or []) + (doc.get("shots") or []):
        settings = entry.get("settings")
        if settings is None:
            continue
        if not isinstance(settings, dict):
            errs.append("settings 必须是对象")
            continue
        reserved = {"model", "prompt", "modeType", "imageList", "imageListOrder"}
        if any(not isinstance(key, str) or not key.strip() or key in reserved for key in settings):
            errs.append("settings 含无效或由专用字段/引用维护的参数")
        if "id" in entry and settings.get("enableSound", "off") != "off":
            errs.append("当前镜头构建器要求 enableSound=off，声音另按制作方案处理")
        try:
            json.dumps(settings, allow_nan=False)
        except (TypeError, ValueError):
            errs.append("settings 含无效 JSON 值或非有限数字")
    if errs:
        return errs, warns
    try:
        _ordered_assets(doc)
    except ValueError as exc:
        return [str(exc)], warns
    assets = [a for a in doc.get("assets") or [] if isinstance(a, dict)]
    chars = [c for c in doc.get("characters") or [] if c.get("id")]
    by_subject = {}
    for a in assets:
        by_subject.setdefault(str(a.get("subject")), []).append(a)
    for c in chars:
        cid = str(c["id"])
        got = by_subject.get(cid, [])
        roles = [str(a.get("role")) for a in got]
        derived = [a for a in got if a.get("role") in ("view", "body")]
        base = c.get("base_state") or "基准"
        looks = {None} | {_state(a, base) for a in derived}
        looks.update(_state({"state": state}, base) for state in (c.get("states") or []))
        for look in looks:
            look_assets = [a for a in derived if _state(a, base) == look]
            covered = set()
            for a in look_assets:
                if a.get("role") == "view":
                    covered.update(a.get("covers") or [a.get("variant")])
            missing = sorted(set(VIEW_CN) - covered)
            if not any(a.get("role") == "body" for a in look_assets):
                missing.append("body")
            if missing:
                errs.append("角色 %s 造型 %r 标准要求五视角与无头身体，缺少 %s" %
                            (cid, look, ", ".join(missing)))
        if "face" not in roles:
            errs.append("角色 %s 没有脸部特写（L1）" % cid)
        face_id = next((a.get("asset_id") for a in got if a.get("role") == "face"), None)
        for a in got:
            if a.get("role") in ("view", "body"):
                if str(a.get("parent") or "") != str(face_id or ""):
                    errs.append("%s 的 parent 不是脸部特写（%r）" % (a.get("asset_id"), a.get("parent")))
    for a in assets:
        if a.get("kind") == "scene" and a.get("role") == "view":
            plan = next((p for p in assets if p.get("kind") == "scene"
                         and p.get("role") == "plan" and p.get("subject") == a.get("subject")), None)
            if not plan or str(a.get("parent") or "") != str(plan.get("asset_id")):
                errs.append("%s 没有指向同空间平面图" % a.get("asset_id"))
        # subject 是 asset_system schema 的必填项，也是节点名的来源：
        # 缺了会让节点被命名成「资产_None_…」并写进画布。
        if not isinstance(a.get("subject"), str) or not a["subject"].strip():
            errs.append("%s 缺 subject（schema 必填；节点名由 subject 组成）" % a.get("asset_id"))
        if (a.get("role") != "design"
                and (not isinstance(a.get("prompt"), str) or not a["prompt"].strip())):
            errs.append("%s 缺 prompt（资产描述是站 5 的活，脚本不代写）" % a.get("asset_id"))
        if a.get("status") not in (None, "approved"):
            warns.append("%s 状态是 %r：能建节点，但生成前必须 approved" % (a.get("asset_id"), a.get("status")))
    for sh in doc.get("shots") or []:
        plan = sh.get("reference_plan") or {}
        ids = list(plan.get("assets") or [])
        if not ids:
            errs.append("%s 没有 reference_plan.assets" % sh.get("id"))
            continue
        faces, subjects = {}, set()
        for aid in ids:
            a = next((x for x in assets if x.get("asset_id") == aid), None)
            if not a:
                errs.append("%s 引用了不存在的资产 %s" % (sh.get("id"), aid))
                continue
            subjects.add(str(a.get("subject")))
            if a.get("role") == "design":
                errs.append("%s 把设计板放进了参考（%s）" % (sh.get("id"), aid))
            n = 0
            if a.get("role") == "face":
                n = 1
            elif a.get("role") == "view":
                n = len([v for v in (a.get("covers") or [a.get("variant")]) if v in FACE_VIEWS])
            if n:
                faces[str(a.get("subject"))] = faces.get(str(a.get("subject")), 0) + n
        for subj, n in faces.items():
            if n > 1:
                errs.append("%s 同一身份 %s 有 %d 张脸" % (sh.get("id"), subj, n))
        if plan.get("primary_asset_id") != ids[0]:
            errs.append("%s primary_asset_id 不是 assets[0]" % sh.get("id"))
        ff = plan.get("first_frame")
        if ff and (ff not in ids or ids[0] != ff):
            errs.append("%s 声明了首帧 %s，但它不是 assets[0]" % (sh.get("id"), ff))
        if len(plan.get("prompt_refs") or []) != len(ids):
            errs.append("%s prompt_refs 与 assets 数量不一致" % sh.get("id"))
        if not isinstance(sh.get("prompt"), str) or not sh["prompt"].strip():
            errs.append("%s 缺 prompt（镜头提示词是站 6 的活）" % sh.get("id"))
    return errs, warns


def _create_args(name, node_type, entry):
    command = ["node"]
    if entry.get("position") is not None:
        rectangle = _rect(entry)
        if rectangle is None:
            raise ValueError("Invalid planned node position: " + name)
        command += ["--x", str(rectangle[0]), "--y", str(rectangle[1])]
    return command + ["create", name, "-t", node_type]


def build_commands(doc, project=None, canvas_name=None):
    """按依赖序生成 CLI 命令列表。"""
    ordered = _ordered_assets(doc)
    node_of = _asset_names(doc)
    cmds = []
    if project is None:
        cmds.append(["project", "create", canvas_name or doc.get("title") or "资产画布"])
    for a in ordered:
        aid = a.get("asset_id")
        c = _create_args(node_of[aid], "image", a)
        if project:
            c += ["-p", project]
        parent = a.get("parent")
        if parent:
            c += ["-s", "modeType=image2image", "--left", node_of[parent]]
        prompt = _prompt_text(a.get("prompt"))
        if prompt:
            c += ["--prompt", prompt]
        if a.get("model"):
            c += ["-s", "model=%s" % a["model"]]
        for key, value in _declared_params(a).items():
            c += ["-s", "%s=%s" % (key, _setting_value(value))]
        cmds.append(c)
    for sh in doc.get("shots") or []:
        plan = sh.get("reference_plan") or {}
        c = _create_args(video_name(sh), "video", sh)
        if project:
            c += ["-p", project]
        c += ["-s", "modeType=mixed2video", "-s", "enableSound=off"]
        shot_prompt = _prompt_text(sh.get("prompt"))
        if shot_prompt:
            c += ["--prompt", shot_prompt]
        if sh.get("model"):
            c += ["-s", "model=%s" % sh["model"]]
        for key, value in _declared_params(sh).items():
            if key == "enableSound":
                continue
            c += ["-s", "%s=%s" % (key, _setting_value(value))]
        for aid in plan.get("assets") or []:
            c += ["--left", node_of.get(aid, aid)]
        cmds.append(c)
    return cmds, node_of


UNSUPPORTED_PLAN_FIELDS = ("group", "layout", "order")


def _rect(entry):
    """Read a declared rectangle. Positions are geometry, not decoration."""
    position = entry.get("position")
    if position is None:
        return None
    try:
        if isinstance(position, dict):
            if any(isinstance(position.get(key), bool) for key in ("x", "y", "w", "h", "width", "height")):
                return None
            x, y = float(position.get("x")), float(position.get("y"))
            width = float(position.get("w", position.get("width", 1)))
            height = float(position.get("h", position.get("height", 1)))
        elif isinstance(position, (list, tuple)) and len(position) >= 2:
            if len(position) > 4 or any(isinstance(value, bool) for value in position):
                return None
            x, y = float(position[0]), float(position[1])
            width = float(position[2]) if len(position) > 2 else 1.0
            height = float(position[3]) if len(position) > 3 else 1.0
        else:
            return None
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, width, height)) or width <= 0 or height <= 0:
        return None
    return (x, y, width, height)


def _overlaps(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _layout_errors(doc, node_of):
    """Two planned nodes may not occupy the same rectangle on the canvas."""
    errors, placed = [], []
    # null 与"没写"同义（建节点与核验都这么处理），所以判无效只看**值**，不看键在不在。
    for asset in doc.get("assets") or []:
        rect = _rect(asset)
        if asset.get("position") is not None and rect is None:
            errors.append("节点位置无效：%s" % node_of.get(asset.get("asset_id")))
        if rect is not None:
            placed.append((str(node_of.get(asset.get("asset_id"))), rect))
    for shot in doc.get("shots") or []:
        rect = _rect(shot)
        if shot.get("position") is not None and rect is None:
            errors.append("节点位置无效：%s" % video_name(shot))
        if rect is not None:
            placed.append((video_name(shot), rect))
    for index, (name, rect) in enumerate(placed):
        for other_name, other in placed[index + 1:]:
            if _overlaps(rect, other):
                errors.append("节点位置重合：%s 与 %s" % (name, other_name))
    return errors


def _workflow_errors(doc):
    """The production order must be expressible as the graph it claims."""
    errors = []
    assets = [a for a in doc.get("assets") or []]
    by_id = {str(a.get("asset_id")): a for a in assets}
    if len(by_id) != len(assets):
        errors.append("资产 asset_id 有重复，工作流无法确定依赖")
    for asset in assets:
        parent = asset.get("parent")
        if parent is not None and str(parent) not in by_id:
            errors.append("%s 的 parent %r 不在计划里" % (asset.get("asset_id"), parent))
        if asset.get("parent") is not None and str(asset.get("parent")) == str(asset.get("asset_id")):
            errors.append("%s 把自己当作 parent" % asset.get("asset_id"))
    shot_ids = {str(shot.get("id")) for shot in doc.get("shots") or []}
    for shot in doc.get("shots") or []:
        for reference in (shot.get("reference_plan") or {}).get("assets") or []:
            if str(reference) in by_id:
                continue
            if str(reference) in shot_ids:
                errors.append("%s 引用了另一个镜头 %r：视频不能作为视频的输入" % (shot.get("id"), reference))
            elif str(reference) not in by_id:
                errors.append("%s 引用了不存在的资产 %r" % (shot.get("id"), reference))
    try:
        _ordered_assets(doc)
    except ValueError as exc:
        errors.append("依赖顺序无法成立：%s" % exc)
    return errors


def _declared_params(entry):
    """Parameters a plan states explicitly; flat, as the platform stores -s keys."""
    flat = {}
    for key, value in (entry.get("settings") or {}).items():
        flat[str(key)] = value
    return flat


def _expected_nodes(doc, node_of):
    commands = []
    for asset in doc.get("assets") or []:
        parent = asset.get("parent")
        expected = {"name": node_of[asset["asset_id"]], "node_type": "image",
                    "prompt": _prompt_text(asset.get("prompt")),
                    "mode_type": "image2image" if parent else None,
                    "refs": [node_of.get(parent, parent)] if parent else []}
        if asset.get("model"):
            expected["model"] = asset["model"]
        flat = _declared_params(asset)
        if flat:
            expected["params"] = flat
        if asset.get("position") is not None:
            expected["position"] = asset["position"]
        commands.append(expected)
    for shot in doc.get("shots") or []:
        refs = (shot.get("reference_plan") or {}).get("assets") or []
        flat = dict({"enableSound": "off"}, **_declared_params(shot))
        expected = {"name": video_name(shot), "node_type": "video",
                    "prompt": _prompt_text(shot.get("prompt")), "mode_type": "mixed2video",
                    "params": flat,
                    "refs": [node_of[aid] for aid in refs]}
        if shot.get("model"):
            expected["model"] = shot["model"]
        if shot.get("position") is not None:
            expected["position"] = shot["position"]
        commands.append(expected)
    return commands


def _unsupported_fields(doc, node_of):
    errors = []
    for asset in doc.get("assets") or []:
        for key in UNSUPPORTED_PLAN_FIELDS:
            if key in asset:
                errors.append("资产 %s 声明了当前无法核对的字段 %s" % (node_of.get(asset.get("asset_id")), key))
    for shot in doc.get("shots") or []:
        for key in UNSUPPORTED_PLAN_FIELDS:
            if key in shot:
                errors.append("镜头 %s 声明了当前无法核对的字段 %s" % (video_name(shot), key))
    return errors


def _read_existing(command):
    rc, result = _run(command[1:])
    if rc != 0 or not isinstance(result, dict) or "_raw" in result:
        raise RuntimeError("LibTV 回读失败，先检查连接、账号授权与目标画布。见 docs/LIBTV_SETUP.md")
    return result


def apply(doc, args):
    errs, warns = validate(doc)
    for w in warns:
        print("[WARN]", w)
    if errs:
        for e in errs:
            print("[FAIL]", e)
        print("校验未过：不建画布。先补清单，不要靠手工补节点。")
        return RC_FAIL
    structural = _layout_errors(doc, _asset_names(doc)) + _workflow_errors(doc)
    if structural:
        for error in structural:
            print("[FAIL]", error)
        print("结构自相矛盾：不写画布。")
        return RC_FAIL
    uncarvable = _unsupported_fields(doc, _asset_names(doc))
    if uncarvable:
        for error in uncarvable:
            print("[FAIL]", error)
        print("计划里有当前无法核对的字段：不写画布。")
        return RC_FAIL
    cmds, node_of = build_commands(doc, args.project, args.name)
    if args.dry_run or not args.apply:
        for c in cmds:
            print(" ".join(c))
        print("dry-run：%d 条命令（加 --apply --yes 才写画布）" % len(cmds))
        return RC_OK
    if not args.yes:
        print("--apply 需要同时给 --yes：会写画布节点与边")
        return RC_USAGE
    project = args.project
    skip_names = set()
    try:
        if project:
            skip_names = _existing_nodes(project, _expected_nodes(doc, node_of),
                                         read_json=_read_existing)
        else:
            _read_existing([LIBTV, "project", "list", "--page-size", "1"])
    except RuntimeError as exc:
        print("[FAIL] 写入前检查失败：%s" % exc)
        return RC_FAIL
    created = []
    for c in cmds:
        if c[0] == "project":
            rc, out = _run(c)
            metadata = out.get("projectMeta") if isinstance(out, dict) else None
            project = metadata.get("uuid") if isinstance(metadata, dict) else None
            if rc != 0 or not isinstance(project, str) or not project.strip():
                print("[FAIL] 新建画布失败", out)
                return RC_FAIL
            print("[canvas]", project)
            continue
        name = c[c.index("create") + 1]
        if name in skip_names:
            print("[skip] 已回读确认 %s" % name)
            continue
        rc, out = _run(c + (["-p", project] if project and "-p" not in c else []))
        key = (out.get("newNodeKey") or out.get("nodeKey")) if isinstance(out, dict) else None
        ok = rc == 0 and isinstance(key, str) and bool(key.strip())
        created.append({"cmd": ["node", "create", name], "ok": ok, "key": key})
        print("[%s] %s" % ("ok" if ok else "FAIL", name), "" if ok else out)
        if not ok:
            return RC_FAIL
    if not args.verify:
        print("建成：%s" % json.dumps({"project": project, "nodes": len(created)}, ensure_ascii=False))
        return RC_OK
    return verify(project, doc, strict_effective=args.strict_effective)


def _platform_snapshot(project, names, expected=None):
    """Full normalized readback of the canvas, for before/after comparison."""
    rc, listing = _run(["node", "list", "-p", project])
    if rc != 0 or not isinstance(listing, dict):
        raise RuntimeError("读不到节点列表")
    rows = listing.get("nodes")
    if not isinstance(rows, list):
        raise RuntimeError("节点列表格式无效")
    snapshot = {}
    owned_ids = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise RuntimeError("节点列表格式无效")
        # 列表投影的 name 可能是空串（MCP 形态），真实名字在 data.name。
        row_name = _node_name(row)
        if row_name not in names:
            continue
        if row_name in owned_ids or row['id'] in owned_ids.values():
            raise RuntimeError("节点身份有歧义")
        owned_ids[row_name] = row['id']
        detail = _read_existing(["unused", "node", row["id"], "-p", project])
        if "nodes" in detail:
            items = detail["nodes"]
            if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
                raise RuntimeError("节点详情格式无效")
            detail = items[0]
        if _detail_key(detail) != row["id"] or _node_name(detail) != row_name:
            raise RuntimeError("节点身份回读不一致")
        snapshot[row_name] = {'detail': detail}
    if expected is None:
        return {name: json.dumps(value['detail'], sort_keys=True, ensure_ascii=False, allow_nan=False)
                for name, value in snapshot.items()}
    if set(owned_ids) != names:
        raise RuntimeError("缺少计划节点")
    meta = _read_existing(['unused', 'project', project])
    graph_nodes, edges = meta.get('nodes'), meta.get('edges')
    if not isinstance(graph_nodes, list) or not isinstance(edges, list):
        raise RuntimeError("画布图结构格式无效")
    by_id = {}
    for row in graph_nodes:
        if (not isinstance(row, dict) or not isinstance(row.get('id'), str)
                or not row['id'].strip() or row['id'] in by_id):
            raise RuntimeError("画布节点身份格式无效")
        by_id[row['id']] = row
    incoming = {node_id: [] for node_id in owned_ids.values()}
    owned_edge_ids = set()
    for edge in edges:
        if (not isinstance(edge, dict)
                or any(not isinstance(edge.get(key), str) or not edge[key].strip()
                       for key in ('source', 'target'))):
            raise RuntimeError("画布边格式无效")
        if edge['target'] in incoming:
            edge_id = edge.get('id')
            if not isinstance(edge_id, str) or not edge_id.strip() or edge_id in owned_edge_ids:
                raise RuntimeError("计划节点入边身份无效或有歧义")
            owned_edge_ids.add(edge_id)
            if edge['source'] not in by_id:
                raise RuntimeError("计划节点存在悬空入边")
            incoming[edge['target']].append(edge)
    for command in expected:
        name = command['name']
        node_id = owned_ids[name]
        row = by_id.get(node_id)
        if row is None or _node_name(row) != name:
            raise RuntimeError("画布与节点列表身份不一致")
        actual_edges = incoming[node_id]
        actual_sources = [edge['source'] for edge in actual_edges]
        wanted_sources = [owned_ids[ref] for ref in command['refs']]
        if (len(actual_sources) != len(set(actual_sources))
                or sorted(actual_sources) != sorted(wanted_sources)):
            raise RuntimeError("节点实际入边与计划不一致：" + name)
        snapshot[name].update(
            position=row.get('position'), width=row.get('width'), height=row.get('height'),
            edges=sorted(actual_edges, key=lambda edge: json.dumps(edge, sort_keys=True)))
        snapshot[name] = json.dumps(snapshot[name], sort_keys=True, ensure_ascii=False, allow_nan=False)
    return snapshot


def audit_canvas(project, doc, strict_effective=False):
    """Final read-only reconciliation of all planned node content and references."""
    errors, _ = validate(doc)
    if isinstance(doc, dict) and not doc.get("assets") and not doc.get("shots"):
        errors.append("没有可审计的计划节点")
    if errors:
        print("[FAIL]", "\n".join(errors))
        return RC_FAIL
    node_of = _asset_names(doc)
    bad_fields = _unsupported_fields(doc, node_of)
    if bad_fields:
        print("[FAIL]", "\n".join(bad_fields))
        return RC_FAIL
    structural = _layout_errors(doc, node_of) + _workflow_errors(doc)
    if structural:
        print("[FAIL]", "\n".join(structural))
        return RC_FAIL
    expected = _expected_nodes(doc, node_of)
    names = {node["name"] for node in expected}
    try:
        before = _platform_snapshot(project, names, expected=expected)
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        print("[FAIL] 审计前快照失败：%s" % exc)
        return RC_FAIL
    try:
        matched = _existing_nodes(project, expected, read_json=_read_existing)
        unmatched = {node["name"] for node in expected} - matched
        if unmatched:
            inventory = _read_existing(["unused", "node", "list", "-p", project])
            # 同样要认 data.name（MCP 形态），否则真实的"存在但不一致"会被算成"缺失"。
            present = {name_value for name_value in
                       (_node_name(row) for row in (inventory.get("nodes") or []) if isinstance(row, dict))
                       if isinstance(name_value, str) and name_value.strip()}
            absent = sorted(unmatched - present)
            mismatched = sorted(unmatched & present)
            parts = []
            if absent:
                parts.append("缺少计划节点：" + "、".join(absent))
            if mismatched:
                parts.append("节点参数与计划不一致：" + "、".join(mismatched))
            raise RuntimeError("；".join(parts))
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        print("[FAIL] 最终节点审计：%s" % exc)
        return RC_FAIL
    code = verify(project, doc, strict_effective=strict_effective)
    try:
        after = _platform_snapshot(project, names, expected=expected)
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        print("[FAIL] 审计后快照失败：%s" % exc)
        return RC_FAIL
    # Two reads bracketing the audit: if the platform moved underneath us, the
    # result cannot be claimed for the delivery.
    drifted = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    if drifted:
        print("[FAIL] 审计期间平台内容发生变化：%s" % "、".join(drifted))
        return RC_FAIL
    return code


_COLLISION_SUFFIX = re.compile(r"_[0-9a-f]{6,}$")


def _collision_hint(missing):
    """带哈希后缀的计划名，多半是同名资产碰撞导致全部改名，而不是节点真的没建。

    build_binding_map 的规则是"同名全部加哈希、不做先来后到"，所以只要新增一个
    重名资产，原先已建好的那个也会改名——用户看到的就是"缺少计划节点"。
    """
    suffixed = [name for name in missing if _COLLISION_SUFFIX.search(name)]
    if not suffixed:
        return ""
    return ("名称带哈希后缀（%s），通常是新增了同名资产：按 build_binding_map 规则，"
            "同名资产全部改名（不做先来后到），已建节点会变成孤儿。"
            % "、".join(suffixed[:3]))


def _missing_artifact_line(empty, strict_effective):
    """严格模式下这一条会真的失败，措辞必须跟着改，否则日志说 WARN、退出码说失败。"""
    if strict_effective:
        return ("  [FAIL] 这些被引用的资产还没有产物（引用已连、尚未生效；"
                "--strict-effective 按失败处理）：%s" % "、".join(empty))
    return "  [WARN] 这些被引用的资产还没有产物（引用已连、尚未生效）：%s" % "、".join(empty)


def verify(project, doc, node_of=None, strict_effective=False):
    errors = _identity_errors(doc)
    if errors:
        print("[FAIL]", "\n".join(errors))
        return RC_FAIL
    node_of = node_of if node_of is not None else _asset_names(doc)
    rc, lst = _run(["node", "list", "-p", project])
    if rc != 0:
        print("[FAIL] 读不到节点列表", lst)
        return RC_FAIL
    rows = lst.get("nodes") if isinstance(lst, dict) else None
    if not isinstance(rows, list):
        print("[FAIL] 节点列表格式无效")
        return RC_FAIL
    id2name = {}
    observed_names = set()
    for node in rows:
        node_id = node.get("id") if isinstance(node, dict) else None
        name = _node_name(node) if isinstance(node, dict) else None
        if (not isinstance(node_id, str) or not node_id.strip()
                or not isinstance(name, str) or not name.strip()
                or node_id in id2name or name in observed_names):
            print("[FAIL] 节点身份缺失或有歧义")
            return RC_FAIL
        id2name[node_id] = name
        observed_names.add(name)
    expected_names = list(node_of.values()) + [video_name(s) for s in doc.get("shots") or []]
    if len(expected_names) != len(set(expected_names)):
        print("[FAIL] 计划节点名称有歧义")
        return RC_FAIL
    missing = sorted(set(expected_names) - observed_names)
    if missing:
        print("[FAIL] 缺少计划节点：%s" % "、".join(missing))
        hint = _collision_hint(missing)
        if hint:
            print("       " + hint)
        return RC_FAIL
    expected_types = {name: "image" for name in node_of.values()}
    expected_types.update({video_name(shot): "video" for shot in doc.get("shots") or []})
    # 列表投影的 name 可能是空串，真实名字在 data.name（MCP 形态）。用同一个取名字器，
    # 否则 by_name 里全是 ""，下面按计划名取节点会 KeyError（2026-11-12 审计指出）。
    by_name = {}
    for node in rows:
        row_name = _node_name(node)
        if isinstance(row_name, str) and row_name.strip():
            by_name[row_name] = node
    for name, expected_type in expected_types.items():
        node = by_name[name]
        if node.get("type") is None:
            rc_detail, detail = _run(["node", node["id"], "-p", project])
            if isinstance(detail, dict) and "nodes" in detail:
                details = detail["nodes"]
                detail = details[0] if isinstance(details, list) and len(details) == 1 else None
            if (rc_detail != 0 or not isinstance(detail, dict)
                    or _detail_key(detail) != node["id"] or _node_name(detail) != name):
                print("[FAIL] 节点身份回读不一致：%s" % name)
                return RC_FAIL
            node = detail
        # 详情投影把类型放在 nodeType（实测）；只读 type 会让这条分支报出误导性的"类型不一致"。
        if node.get("type", node.get("nodeType")) != expected_type:
            print("[FAIL] 节点类型不一致：%s，期望 %s" % (name, expected_type))
            return RC_FAIL
    # 声明了坐标就必须核对落点：建节点时 --x/--y 是"发出去"，这一步是"收回来"。
    # 真实 CLI 只在 project 回包里给 position（且只有 x/y，没有宽高）。
    # 资产与镜头都用 _create_args 发 --x/--y，所以两者都要回读核对。
    declared = {}
    pending = [(node_of.get(a.get("asset_id")), a) for a in doc.get("assets") or []
               if isinstance(a, dict) and a.get("position") is not None]
    pending += [(video_name(s), s) for s in doc.get("shots") or []
                if isinstance(s, dict) and s.get("position") is not None]
    for name, entry in pending:
        # 声明了坐标却连节点名都映射不出来，同样不能静默放过。
        if not name:
            print("[FAIL] 声明的坐标找不到对应节点名")
            return RC_FAIL
        rect = _geometry(entry)
        # 声明了却解析不出有限的 x/y，不能静默跳过——那等于"声明了却从不核验"。
        if not rect or "x" not in rect or "y" not in rect:
            print("[FAIL] 声明的坐标无法解析：%s（需要有限的 x 与 y）" % name)
            return RC_FAIL
        declared[name] = rect
    if declared:
        rc_pos, meta = _run(["project", project])
        positions = {}
        if rc_pos == 0 and isinstance(meta, dict):
            for row in meta.get("nodes") or []:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    geom = _geometry(row)
                    if geom is not None:
                        positions[row["id"]] = geom
        if not positions:
            print("[FAIL] 读不到画布坐标，声明的位置无法核对")
            return RC_FAIL
        for name, rect in declared.items():
            actual = positions.get(by_name[name]["id"])
            if actual is None:
                print("[FAIL] 节点没有坐标：%s" % name)
                return RC_FAIL
            if any(actual.get(key) != rect[key] for key in ("x", "y")):
                print("[FAIL] 节点位置与计划不一致：%s" % name)
                return RC_FAIL

    bad = []
    checked = 0

    def order_of(name):
        rc2, d = _run(["node", name, "-p", project])
        if rc2 != 0:
            bad.append({"node": name, "want": "成功回读", "got": {"exit": rc2, "response": d}})
            return []
        p = _node_params(d) if isinstance(d, dict) else None
        if not isinstance(p, dict):
            bad.append({"node": name, "want": "有效参数回读", "got": d})
            return []
        return [id2name.get(x, x) for x in (p.get("imageListOrder") or [])]

    for a in doc.get("assets") or []:
        if not a.get("parent"):
            continue
        checked += 1
        want = [node_of.get(a["parent"], a["parent"])]
        got = order_of(node_of[a["asset_id"]])
        if got != want:
            bad.append({"node": node_of[a["asset_id"]], "want": want, "got": got})
    for sh in doc.get("shots") or []:
        checked += 1
        want = [node_of.get(x, x) for x in ((sh.get("reference_plan") or {}).get("assets") or [])]
        got = order_of(video_name(sh))
        if got != want:
            bad.append({"node": video_name(sh), "want": want, "got": got})
    # 引用是否真的能成立：被引用的资产节点有没有产物（url 非空）
    ref_ids = set()
    for sh in doc.get("shots") or []:
        ref_ids |= set((sh.get("reference_plan") or {}).get("assets") or [])
    empty = []
    for aid in sorted(ref_ids):
        name = node_of.get(aid, aid)
        rc3, d = _run(["node", name, "-p", project])
        if rc3 != 0:
            bad.append({"node": name, "want": "成功回读产物", "got": {"exit": rc3, "response": d}})
            empty.append(name)
            continue
        if isinstance(d, dict) and isinstance(d.get("nodes"), list) and len(d["nodes"]) == 1:
            d = d["nodes"][0]
        data = d.get("data") if isinstance(d, dict) else None
        urls = data.get("url") if isinstance(data, dict) else None
        if isinstance(urls, str):
            urls = [urls]
        if (not isinstance(urls, list)
                or not any(isinstance(url, str) and url.strip() for url in urls)):
            empty.append(name)
    print("回读：%d 条边组，%d 不一致；引用产物 %d/%d 非空" %
          (checked, len(bad), len(ref_ids) - len(empty), len(ref_ids)))
    for b in bad:
        print("  [FAIL]", b["node"], "期望", b["want"], "实得", b["got"])
    if empty:
        print(_missing_artifact_line(empty, strict_effective))
    if bad or (strict_effective and empty):
        return RC_FAIL
    return RC_WARN if empty else RC_OK


def _self_test():
    """离线自检：校验器与命令生成器不联网也能验。"""
    import copy

    def A(aid, kind, subject, role, layer, parent=None, variant=None):
        a = {"asset_id": aid, "kind": kind, "subject": subject, "role": role,
             "layer": layer, "status": "approved", "parent": parent, "prompt": "p-" + aid}
        if variant:
            a["variant"] = variant
        return a

    def doc():
        assets = [A("C1F", "character", "C1", "face", 1)]
        for v in ("front", "back", "left", "right", "top"):
            assets.append(A("C1V" + v[0], "character", "C1", "view", 2, "C1F", v))
        assets.append(A("C1B", "character", "C1", "body", 2, "C1F"))
        assets.append(A("S1P", "scene", "S1", "plan", 1))
        assets.append(A("S1VA", "scene", "S1", "view", 2, "S1P", "A"))
        return {"title": "self-test",
                "characters": [{"id": "C1", "name": "她", "states": ["基准"]}],
                "scenes": [{"id": "S1", "name": "屋"}],
                "shots": [{"id": "S1", "scene": "S1", "characters": ["C1"], "scale": "中景",
                           "prompt": "p", "reference_plan": {"primary_asset_id": "C1F",
                                                             "assets": ["C1F", "S1VA"],
                                                             "prompt_refs": ["{{Image 1}}", "{{Image 2}}"]}}],
                "assets": assets}

    bad = 0
    d = doc()
    errs, _ = validate(d)
    if errs:
        bad += 1
        print("[FAIL] 干净清单被误判：", errs)
    short = copy.deepcopy(d)
    short["assets"] = [a for a in short["assets"] if a["asset_id"] != "C1B"]
    errs, _ = validate(short)
    if not any("标准要求" in e for e in errs):
        bad += 1
        print("[FAIL] 缺无头身体未被拦：", errs)
    two_face = copy.deepcopy(d)
    two_face["shots"][0]["reference_plan"]["assets"] = ["C1F", "C1Vf"]
    two_face["shots"][0]["reference_plan"]["prompt_refs"] = ["{{Image 1}}", "{{Image 2}}"]
    errs, _ = validate(two_face)
    if not any("张脸" in e for e in errs):
        bad += 1
        print("[FAIL] 同身份两张脸未被拦：", errs)
    cmds, node_of = build_commands(d, project="P", canvas_name="x")
    if len(cmds) != 10:
        bad += 1
        print("[FAIL] 命令数应为 10（7 人物 + 平面图 + 机位图 + 1 镜头），实得 %d" % len(cmds))
    l2 = next(c for c in cmds if c[2] == node_of["C1Vf"] or "前视" in c[2])
    if "modeType=image2image" not in l2 or "--left" not in l2:
        bad += 1
        print("[FAIL] L2 没有图生图 + 父边：", l2)
    video = cmds[-1]
    if "modeType=mixed2video" not in video or "enableSound=off" not in video:
        bad += 1
        print("[FAIL] 视频边参数不全：", video)
    # 以下四条覆盖 2026-11-12 新增/修复的行为，doctor 每次都会跑。
    no_subject = copy.deepcopy(d)
    del no_subject["assets"][0]["subject"]
    errs, _ = validate(no_subject)
    if not any("subject" in e for e in errs):
        bad += 1
        print("[FAIL] 缺 subject 未被拦：", errs)

    overlap = copy.deepcopy(d)
    for entry in overlap["assets"][:2]:
        entry["position"] = {"x": 0, "y": 0, "w": 100, "h": 100}
    lay = _layout_errors(overlap, _asset_names(overlap))
    if not any("位置重合" in e for e in lay):
        bad += 1
        print("[FAIL] 位置重合未被拦：", lay)

    board = {"title": "t", "shots": [],
             "assets": [{"asset_id": "B1", "kind": "board", "subject": "S9",
                         "role": "design", "layer": 0}]}
    bcmds, _ = build_commands(board, project="P", canvas_name="x")
    flat = [token for command in bcmds for token in command]
    if "--prompt" in flat or "None" in " ".join(flat):
        bad += 1
        print("[FAIL] 无提示词被渲染成字面量 None：", flat)

    if _prompt_text(None) is not None or _prompt_text("   ") is not None:
        bad += 1
        print("[FAIL] _prompt_text 未把缺失/空白当作没有")
    # 只断言"除首尾空白外内容完全不变"：_prompt_text 保留原始空白，不做 strip。
    kept = _prompt_text("  一把椅子  ")
    if kept is None or kept.strip() != "一把椅子":
        bad += 1
        print("[FAIL] _prompt_text 改动了正常提示词：%r" % (kept,))

    print("自检：%d 失败" % bad)
    return RC_OK if not bad else RC_FAIL


def main(argv=None):
    ap = argparse.ArgumentParser(description="资产清单 → LibTV 画布（节点 + 派生边 + 投喂边）")
    ap.add_argument("plan", nargs="?", help="asset-system/2 清单 JSON（含 assets[].prompt / shots[].prompt）")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令（默认）")
    ap.add_argument("--apply", action="store_true", help="真写画布")
    ap.add_argument("--yes", action="store_true", help="确认写入")
    ap.add_argument("--name", help="新画布名")
    ap.add_argument("--project", help="已有画布 uuid（不给则新建）")
    ap.add_argument("--verify", action="store_true", help="建完回读校验")
    ap.add_argument("--strict-effective", action="store_true",
                    help="回读时把「资产无产物」也判失败（默认只 WARN）")
    ap.add_argument("--verify-only", help="只回读某个已有画布的 uuid")
    ap.add_argument("--self-test", action="store_true", help="离线自检（不联网）")
    ap.add_argument("--compose", action="store_true",
                    help="缺 prompt 的资产/镜头由 facts/brief 自动组装（资产描述脚本执行）")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    needs_platform = args.verify_only or (args.apply and not args.dry_run)
    if needs_platform and not os.path.isfile(LIBTV):
        print("找不到 libtv：%s（设 LIBTV_BIN）" % LIBTV)
        return RC_ENV
    if not args.plan:
        ap.print_help()
        return RC_USAGE
    try:
        with open(args.plan, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        print("清单读不了：%s" % exc)
        return RC_USAGE
    identity_errors = _identity_errors(doc)
    if identity_errors:
        for error in identity_errors:
            print("[FAIL]", error)
        return RC_FAIL
    if args.compose:
        missing = compose_all(doc)
        if missing:
            for m in missing:
                print("[FAIL] 自动描述缺事实：", json.dumps(m, ensure_ascii=False))
            print("缺事实就停下补 spec，不要用通用描述顶替（那会得到一张模板脸）。")
            return RC_FAIL
        print("已按 facts 组装 %d 件资产 / %d 条镜头的描述" %
              (len(doc.get("assets") or []), len(doc.get("shots") or [])))
    if args.verify_only:
        return verify(args.verify_only, doc, strict_effective=args.strict_effective)
    return apply(doc, args)


if __name__ == "__main__":
    sys.exit(main())
