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
import os
import subprocess
import sys

try:
    from .asset_manifest import _state
except ImportError:
    from asset_manifest import _state

RC_OK, RC_FAIL, RC_USAGE, RC_ENV, RC_WARN = 0, 1, 2, 3, 4
try:
    from .apply_libtv_plan import resolve_libtv_binary
except ImportError:
    from apply_libtv_plan import resolve_libtv_binary

LIBTV = str(resolve_libtv_binary())
ROLE_CN = {"face": "脸部特写", "body": "无头身体", "anchor": "主图", "closeup": "近距版",
           "plan": "平面图", "design": "设计板"}
VIEW_CN = {"front": "前视", "back": "后视", "left": "左视", "right": "右视", "top": "俯视"}
FACE_VIEWS = {"front", "left", "right"}


def _run(args):
    r = subprocess.run([LIBTV] + args, capture_output=True)
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


def _block(f):
    """40–70 字身份锚点：全部物理事实，不写气质。"""
    who = []
    if f.get("age"):
        who.append("%s岁" % f["age"])
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
                         "层高" + str(f.get("height")) if f.get("height") else "",
                         "进深" + str(f.get("depth")) if f.get("depth") else "",
                         str(f.get("openings")), "地面" + str(f.get("floor")),
                         "无透视、无人、无文字", "空间指纹：" + str(f.get("fingerprint"))), []
        need = [k for k in ("walls", "floor", "fingerprint") if not f.get(k)]
        if need:
            return None, need
        return _join("内景，%s 方向" % (a.get("variant") or "主"), str(f.get("walls")),
                     "地面" + str(f.get("floor")), "可见空间指纹：" + str(f.get("fingerprint")),
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


def validate(doc):
    """返回 (错误列表, 警告列表)。错误＝不许建。"""
    errs, warns = [], []
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
        if a.get("role") != "design" and not a.get("prompt"):
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
        if not sh.get("prompt"):
            errs.append("%s 缺 prompt（镜头提示词是站 6 的活）" % sh.get("id"))
    return errs, warns


def build_commands(doc, project=None, canvas_name=None):
    """按依赖序生成 CLI 命令列表。"""
    names = _names(doc)
    assets = [a for a in doc.get("assets") or [] if isinstance(a, dict)]
    node_of = {a.get("asset_id"): node_name(a, names) for a in assets}

    def is_l1(a):
        return a.get("layer") == 1 or a.get("role") in ("face", "anchor", "plan")

    ordered = [a for a in assets if is_l1(a)] + [a for a in assets if not is_l1(a)]
    cmds = []
    if project is None:
        cmds.append(["project", "create", canvas_name or doc.get("title") or "资产画布"])
    for a in ordered:
        aid = a.get("asset_id")
        c = ["node", "create", node_of[aid], "-t", "image"]
        if project:
            c += ["-p", project]
        parent = a.get("parent")
        if parent and parent in node_of:
            c += ["-s", "modeType=image2image", "--left", node_of[parent]]
        c += ["--prompt", str(a.get("prompt"))]
        cmds.append(c)
    for sh in doc.get("shots") or []:
        plan = sh.get("reference_plan") or {}
        c = ["node", "create", video_name(sh), "-t", "video"]
        if project:
            c += ["-p", project]
        c += ["-s", "modeType=mixed2video", "-s", "enableSound=off", "--prompt", str(sh.get("prompt"))]
        for aid in plan.get("assets") or []:
            c += ["--left", node_of.get(aid, aid)]
        cmds.append(c)
    return cmds, node_of


def apply(doc, args):
    errs, warns = validate(doc)
    for w in warns:
        print("[WARN]", w)
    if errs:
        for e in errs:
            print("[FAIL]", e)
        print("校验未过：不建画布。先补清单，不要靠手工补节点。")
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
    created = []
    for c in cmds:
        if c[0] == "project":
            rc, out = _run(c)
            project = (out.get("projectMeta") or {}).get("uuid")
            print("[canvas]", project)
            if not project:
                print("[FAIL]", out)
                return RC_FAIL
            continue
        rc, out = _run(c + (["-p", project] if project and "-p" not in c else []))
        key = out.get("newNodeKey") or out.get("nodeKey")
        ok = rc == 0 and bool(key)
        created.append({"cmd": c[:3], "ok": ok, "key": key})
        print("[%s] %s" % ("ok" if ok else "FAIL", c[2]), "" if ok else out)
        if not ok:
            return RC_FAIL
    if not args.verify:
        print("建成：%s" % json.dumps({"project": project, "nodes": len(created)}, ensure_ascii=False))
        return RC_OK
    return verify(project, doc, strict_effective=args.strict_effective)


def verify(project, doc, node_of=None, strict_effective=False):
    names = _names(doc)
    node_of = node_of or {a.get("asset_id"): node_name(a, names) for a in doc.get("assets") or []}
    rc, lst = _run(["node", "list", "-p", project])
    if rc != 0:
        print("[FAIL] 读不到节点列表", lst)
        return RC_FAIL
    id2name = {n["id"]: n["name"] for n in lst.get("nodes", [])}
    bad = []
    checked = 0

    def order_of(name):
        rc2, d = _run(["node", name, "-p", project])
        if rc2 != 0:
            bad.append({"node": name, "want": "成功回读", "got": {"exit": rc2, "response": d}})
            return []
        p = (d.get("data") or {}).get("params") or {}
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
        urls = (d.get("data") or {}).get("url") or []
        if not urls:
            empty.append(name)
    print("回读：%d 条边组，%d 不一致；引用产物 %d/%d 非空" %
          (checked, len(bad), len(ref_ids) - len(empty), len(ref_ids)))
    for b in bad:
        print("  [FAIL]", b["node"], "期望", b["want"], "实得", b["got"])
    if empty:
        print("  [WARN] 这些被引用的资产还没有产物（引用已连、尚未生效）：%s" % "、".join(empty))
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
