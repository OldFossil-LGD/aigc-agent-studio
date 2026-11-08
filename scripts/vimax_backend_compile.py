#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ViMax 后端作业单：把本库已定稿的计划绑成一份**不执行**的 `vimax-job/v1`。

为什么要有它（`vimax-runtime.md`）：ViMax（HKUDS）是"idea/script/novel → 成片"的
agent runtime，它自带三个工作流和一条硬规矩——**用户不明确点名工作流就不许规划**。
本库的站 6.5 也有同样的界线（点火必须显式批准）。两者叠在一起才是可用后端：

  ① 工作流 = 显式参数，没有默认值。缺了就退出，不猜（`WORKFLOW_NOT_CONFIRMED`）。
  ② 源必须是真的：`script2video` 要一份实存且非空的剧本，`novel2video` 要小说原文；
     `idea2video` 允许用 01 的目标句，但标注"源非用户直给"（`IDEA_SOURCE_IMPLICIT`）。
  ③ 产物目录权威：`.working_dir/<session_id>/<workflow>/` 是 ViMax 的产物账本；
     本脚本只在 `<out>/vimax_session/` 下放**本库提供的源**，绝不预造 ViMax 该生成的文件
     （预造＝假状态，读回时会骗人）。
  ④ 永不执行：`render.run` 恒 false；`--approve-render` 只**记录**批准，不代为点火。

退出码：0 通过 ｜ 1 有 FAIL ｜ 2 用法/来源不满足 ｜ 3 没有可绑的计划（≠通过） ｜ 4 只有 WARN

用法：
  python scripts/vimax_backend_compile.py --artifacts out/ --out out/ --workflow script2video --script script.txt
  python scripts/vimax_backend_compile.py --artifacts out/ --out out/ --workflow idea2video
  python scripts/vimax_backend_compile.py --self-test
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import shutil
import sys

try:
    from .filmdsl_bridge import (RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN, _tmpdir,
                                 asset_index, contract_of, load_artifacts, prompt_index)
except ImportError:
    from filmdsl_bridge import (RC_EMPTY, RC_FAIL, RC_OK, RC_USAGE, RC_WARN, _tmpdir,
                                asset_index, contract_of, load_artifacts, prompt_index)

FORMAT = "vimax-job/v1"
WORKFLOWS = ("idea2video", "script2video", "novel2video")
SOURCE_REQUIRED = {"script2video": "script", "novel2video": "novel", "idea2video": "idea"}

AUTHORITY_README = """# ViMax 会话目录 · 权威分界

本目录由 `scripts/vimax_backend_compile.py` 生成，只放**本库提供的源**。

| 路径 | 谁写 | 说明 |
|---|---|---|
| `{workflow}/{source_name}` | 本库（aigc-agent-studio） | 用户已确认的源原文，逐字复制，不改写 |
| `characters.json` | ViMax | 角色抽取结果；本库不预造 |
| `storyboard.json` / `camera_tree.json` | ViMax | 分镜与机位树；本库不预造 |
| `shots/<idx>/shot_description.json` | ViMax | 逐镜描述；本库不预造 |
| `shots/<idx>/first_frame.png` / `video.mp4` | ViMax | 关键帧与片段；本库不预造 |
| `final_video.mp4` | ViMax | 合成结果 |

规矩：
1. `.working_dir/<session_id>/<workflow>/` 是产物权威，`.vimax/sessions.json` 只是索引。
2. 本库的 01–04 仍是计划权威；ViMax 的产物是**执行结果**，回读只用于核验，不反过来改写计划。
3. 预造 ViMax 该生成的文件＝假状态。缺就报缺，读回不存在的产物要判 FAIL。
4. 本目录不含任何 API key；密钥走环境变量或本机 `configs/agent.local.yaml`（不进库）。
"""


def _err(code, message, level="fail", **where):
    row = {"code": code, "level": level, "message": message}
    row.update({k: v for k, v in where.items() if v is not None})
    return row


def _read_text(path):
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


def _count_prompts(prompts, shot_ids, roles):
    n = 0
    for sid in shot_ids:
        for role in roles:
            if (prompts.get(sid) or {}).get(role):
                n += 1
    return n


def build_stage_bindings(art, workflow):
    """十个 ViMax 阶段 ← 本库哪份产物。provided=计划里有据；missing=没有；backend=ViMax 自己产。"""
    contract = contract_of(art)
    assets, _ = asset_index(art)
    prompts, _ = prompt_index(art)
    shots_doc = art.get("shots") or {}
    shots = [s for s in (shots_doc.get("shots") or []) if isinstance(s, dict)]
    shot_ids = [str(s.get("id")) for s in shots if s.get("id")]
    characters = [a for a, v in assets.items() if str(v.get("kind")).lower() == "character"]
    has_camera = any(isinstance(s.get("camera"), dict) and s.get("camera") for s in shots)
    n_frame = _count_prompts(prompts, shot_ids, ("candidate_image",))
    n_video = _count_prompts(prompts, shot_ids, ("video_candidate",))

    def row(stage, source, state, evidence=None):
        return {"vimax_stage": stage, "studio_source": source, "state": state, "evidence": evidence}

    rows = [
        row("input_" + ("idea" if workflow == "idea2video" else "script" if workflow == "script2video" else "novel"),
            "%s/源原文" % workflow, "provided" if workflow != "idea2video" else "derived"),
    ]
    if workflow == "idea2video":
        rows.insert(0, row("project_brief", "01_production_contract.json#goal",
                           "provided" if contract.get("goal") else "missing", contract.get("goal")))
    rows += [
        row("characters", "02_asset_graph_plan.json#kind=character",
            "provided" if characters else "missing", "%d 个角色" % len(characters)),
        row("storyboard", "03_shot_graph_plan.json#shots",
            "provided" if shots else "missing", "%d 镜" % len(shots)),
        row("shot_decomposition", "03_shot_graph_plan.json#shots[].shot_timing",
            "derived" if any(s.get("shot_timing") for s in shots) else ("derived" if shots else "missing"),
            "%d 镜有时长表" % len([s for s in shots if s.get("shot_timing")])),
        row("camera_tree", "03_shot_graph_plan.json#shots[].camera",
            "derived" if has_camera else "missing", "%d 镜有机位" % len([s for s in shots if s.get("camera")])),
        row("frame_prompts", "04_prompt_packages.jsonl#role=candidate_image",
            "provided" if n_frame else "missing", "%d/%d 镜" % (n_frame, len(shot_ids))),
        row("keyframes", "04_prompt_packages.jsonl#role=candidate_image|refined_image",
            "backend_generated", "ViMax 关键帧生成 + 选帧"),
        row("video_clips", "04_prompt_packages.jsonl#role=video_candidate",
            "provided" if n_video else "missing", "%d/%d 镜" % (n_video, len(shot_ids))),
        row("final_video", "assembly_layer#cut_range",
            "backend_generated", "ViMax 合成"),
    ]
    return rows


def required_stages(workflow):
    base = {"characters", "storyboard", "shot_decomposition", "frame_prompts", "video_clips"}
    if workflow == "idea2video":
        base.add("project_brief")
    return base


def compile_job(art, workflow, source, out_dir, session_id=None, approve_render=None, stamp=False, force=False):
    """art + 源 → (job 文档, 违规表)。source = {kind, path, text, explicit}。"""
    violations, warnings = [], []
    source = dict(source)
    source_bytes = source.get("bytes", source["text"].encode("utf-8"))
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source.get("sha256") and source["sha256"] != source_hash:
        violations.append(_err("SOURCE_HASH_MISMATCH", "源字节与声明 sha256 不一致，作业单未写入"))
    source["sha256"] = source_hash
    source["text"] = source_bytes.decode("utf-8")
    contract = contract_of(art)
    shots_doc = art.get("shots") or {}
    shots = [s for s in (shots_doc.get("shots") or []) if isinstance(s, dict)]
    if not shots:
        violations.append(_err("PLAN_EMPTY", "03 里没有镜头：绑不出作业单", level="empty"))

    if shots_doc.get("generation_authorized") is True or (contract.get("delivery") or {}).get("ignition_allowed") is True:
        violations.append(_err("AUTHORITY_LEAK", "计划带 generation_authorized/ignition_allowed=true：后端作业单不得继承点火许可"))

    if not source.get("explicit") and source.get("kind") == "idea":
        warnings.append(_err("IDEA_SOURCE_IMPLICIT", "创意源取自 01 的 goal，不是用户直给的原文；idea2video 只在已点名工作流时成立", level="warn"))

    bindings = build_stage_bindings(art, workflow)
    states = {b["vimax_stage"]: b["state"] for b in bindings}
    for stage in sorted(required_stages(workflow)):
        if states.get(stage) == "missing":
            warnings.append(_err("STAGE_MISSING", "工作流 %s 需要 %s，但本库计划里没有，ViMax 会自行补全（须在回读时核）" % (workflow, stage), level="warn", where=stage))

    if session_id is None:
        seed = "%s|%s|%s" % (workflow, source.get("sha256") or "nohash", shots_doc.get("source_revision") or "")
        session_id = "vmx_%s" % hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

    job_path = os.path.join(out_dir, "vimax_job.json")
    session_root = os.path.join(out_dir, "vimax_session", workflow)
    session_rel = ".working_dir/%s/%s" % (session_id, workflow)
    if os.path.isfile(job_path) and not force:
        try:
            prev = json.loads(_read_text(job_path))
        except ValueError:
            prev = {}
        same = (prev.get("session", {}).get("session_id") == session_id
                and prev.get("source", {}).get("sha256") == source.get("sha256"))
        if not same:
            violations.append(_err("SESSION_EXISTS_CONFLICT",
                                   "同目录已有另一份作业单（session=%s, sha=%s…）；换 --out 或显式 --force"
                                   % (prev.get("session", {}).get("session_id"),
                                      str(prev.get("source", {}).get("sha256"))[:12])))

    if violations and any(v["level"] == "fail" for v in violations):
        return None, violations + warnings

    source_name = {"script": "script.txt", "novel": os.path.join("novel", "novel.txt"),
                   "idea": "idea.txt"}[source["kind"]]
    session_file = os.path.join(session_root, source_name)
    os.makedirs(os.path.dirname(session_file), exist_ok=True)
    with io.open(session_file, "wb") as handle:
        handle.write(source_bytes)
    _write(os.path.join(session_root, "README.authority.md"),
           AUTHORITY_README.format(workflow=workflow, source_name=source_name))

    commands = [
        {"cmd": "vimax tui new", "run": False, "why": "在 ViMax 根目录起一个新会话（人工执行）"},
        {"cmd": "vimax tui resume %s" % session_id, "run": False, "why": "复用本作业单指向的会话"},
    ]
    render = {"run": False, "approval": None, "note": "本脚本永不点火；真实生成须在显式批准后由人或 ViMax agent 触发"}
    if approve_render:
        render["approval"] = {"granted": True, "note": approve_render, "scope": "recorded_not_executed"}

    job = {
        "format": FORMAT,
        "workflow": workflow,
        "workflow_confirmation": {"explicit": True, "by": "cli_flag", "value": workflow},
        "session": {"session_id": session_id, "root": session_rel, "mode": "new",
                    "artifact_authority": ".working_dir/<session_id>/<workflow>"},
        "source": {"kind": source["kind"], "path": session_rel + "/" + source_name.replace(os.sep, "/"),
                   "sha256": source.get("sha256"), "chars": len(source["text"]),
                   "explicit": bool(source.get("explicit"))},
        "studio": {
            "artifacts": art.get("files") or {},
            "artifacts_sha256": art.get("hashes") or {},
            "authoritative": True,
            "generation_authorized": False,
        },
        "stage_bindings": bindings,
        "render": render,
        "commands": commands,
        "config_template": {
            "llm": {"model_provider": "openai", "model": "", "base_url": "", "api_key": ""},
            "image": {"model": "", "base_url": "", "api_key": ""},
            "video": {"model": "", "base_url": "", "api_key": ""},
            "image_selection": {"num_candidates": 2},
        },
        "warnings": [w["message"] for w in warnings],
    }
    if stamp:
        job["generated_by"] = "scripts/vimax_backend_compile.py"
    _write_json(job_path, job)
    return job, violations + warnings


def _source_from_args(args, art):
    contract = contract_of(art)
    kind = SOURCE_REQUIRED[args.workflow]
    if kind == "script":
        if not args.script:
            return None, [_err("SCRIPT_SOURCE_REQUIRED", "script2video 需要显式剧本（--script 指向实存文件）；不许拿模糊创意顶替")]
        if not os.path.isfile(args.script):
            return None, [_err("SCRIPT_SOURCE_REQUIRED", "剧本文件不存在：%s" % args.script)]
        with io.open(args.script, "rb") as handle:
            source_bytes = handle.read()
        text = source_bytes.decode("utf-8")
        if not text.strip():
            return None, [_err("SOURCE_EMPTY", "剧本文件为空：%s" % args.script)]
        return {"kind": "script", "path": os.path.abspath(args.script), "text": text,
                "bytes": source_bytes, "sha256": hashlib.sha256(source_bytes).hexdigest(), "explicit": True}, []
    if kind == "novel":
        if not args.novel or not os.path.isfile(args.novel):
            return None, [_err("NOVEL_SOURCE_REQUIRED", "novel2video 需要显式小说原文（--novel 指向实存文件）")]
        with io.open(args.novel, "rb") as handle:
            source_bytes = handle.read()
        text = source_bytes.decode("utf-8")
        if not text.strip():
            return None, [_err("SOURCE_EMPTY", "小说文件为空：%s" % args.novel)]
        return {"kind": "novel", "path": os.path.abspath(args.novel), "text": text,
                "bytes": source_bytes, "sha256": hashlib.sha256(source_bytes).hexdigest(), "explicit": True}, []
    idea = args.idea
    explicit = bool(idea)
    if not idea:
        idea = contract.get("goal") or ""
    if not idea.strip():
        return None, [_err("IDEA_SOURCE_REQUIRED", "idea2video 需要一个创意句：--idea，或 01 里可用的 goal")]
    digest = hashlib.sha256(idea.encode("utf-8")).hexdigest()
    return {"kind": "idea", "path": None, "text": idea, "sha256": digest, "explicit": explicit}, []


def _summary(violations):
    fails = [v for v in violations if v["level"] == "fail"]
    warns = [v for v in violations if v["level"] == "warn"]
    empty = [v for v in violations if v["level"] == "empty"]
    for v in violations:
        print("[%s] %-26s %s" % (v["level"].upper(), v["code"], v["message"]))
    print("合计：%d FAIL / %d WARN / %d EMPTY" % (len(fails), len(warns), len(empty)))
    if fails:
        return RC_FAIL
    if empty and not warns:
        return RC_EMPTY
    return RC_WARN if warns else RC_OK


def run(args):
    if args.workflow not in WORKFLOWS:
        print("[FAIL] WORKFLOW_NOT_CONFIRMED 必须显式指定 --workflow %s：ViMax 与本库都不猜工作流" % "|".join(WORKFLOWS))
        return RC_USAGE
    art = load_artifacts(args.artifacts)
    source, problems = _source_from_args(args, art)
    if problems:
        _summary(problems)
        return RC_USAGE
    job, violations = compile_job(art, args.workflow, source, args.out,
                                  session_id=args.session_id, approve_render=args.approve_render,
                                  stamp=args.stamp, force=args.force)
    if any(v["level"] == "fail" for v in violations):
        rc = _summary(violations)
        if any(v["code"] == "SESSION_EXISTS_CONFLICT" for v in violations):
            return RC_USAGE
        return rc
    if args.json:
        print(json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True))
    print("作业单：%s" % os.path.join(os.path.abspath(args.out), "vimax_job.json"))
    print("会话目录：%s（只放本库提供的源）" % os.path.join(os.path.abspath(args.out), "vimax_session"))
    return _summary(violations)


def self_test():
    from filmdsl_bridge import FIXTURES  # 同一 fixtures 根
    base = os.path.join(FIXTURES, "base")
    script = os.path.join(base, "script.txt")
    cases = [
        ("no_workflow", {"workflow": None, "out": "out_a"}),
        ("script_without_source", {"workflow": "script2video", "script": None, "out": "out_b"}),
        ("script_ok", {"workflow": "script2video", "script": script, "out": "out_c"}),
        ("idea_from_contract", {"workflow": "idea2video", "out": "out_d"}),
        ("session_conflict", {"workflow": "script2video", "script": script, "session_id": "other_session", "out": "out_c"}),
    ]
    bad = 0
    tmp = _tmpdir(prefix="vimaxjob_")
    try:
        for name, spec in cases:
            out = os.path.join(tmp, spec["out"])
            os.makedirs(out, exist_ok=True)
            ns = argparse.Namespace(artifacts=base, out=out, workflow=spec.get("workflow"),
                                    script=spec.get("script"), novel=None, idea=None,
                                    session_id=spec.get("session_id"), approve_render=None,
                                    stamp=False, force=False, json=False)
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                rc = run(ns)
            finally:
                sys.stdout = old
            text = buf.getvalue()
            expected = {
                "no_workflow": (RC_USAGE, "WORKFLOW_NOT_CONFIRMED"),
                "script_without_source": (RC_USAGE, "SCRIPT_SOURCE_REQUIRED"),
                "script_ok": (RC_OK, "作业单"),
                "idea_from_contract": (RC_WARN, "IDEA_SOURCE_IMPLICIT"),
                "session_conflict": (RC_USAGE, "SESSION_EXISTS_CONFLICT"),
            }[name]
            ok = rc == expected[0] and expected[1] in text
            if not ok:
                bad += 1
                print("[FAIL] %-22s rc=%s 期望 %s / %r\n%s" % (name, rc, expected[0], expected[1], text.strip()[:400]))
            else:
                print("[PASS] %-22s rc=%s %s" % (name, rc, expected[1]))
        # 结构断言：作业单永不点火，且不预造后端产物
        job = json.loads(_read_text(os.path.join(out, "vimax_job.json")))
        checks = [
            ("render.run=false", job["render"]["run"] is False),
            ("studio.generation_authorized=false", job["studio"]["generation_authorized"] is False),
            ("commands 全部 run=false", all(c["run"] is False for c in job["commands"])),
            ("无 api_key 泄漏", "api_key" in json.dumps(job) and all(
                not m for m in [job["config_template"][k]["api_key"] for k in ("llm", "image", "video")])),
            ("不预造 characters.json", not os.path.exists(os.path.join(out, "vimax_session", "script2video", "characters.json"))),
            ("源逐字落盘", os.path.isfile(os.path.join(out, "vimax_session", "script2video", "script.txt"))),
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
    ap = argparse.ArgumentParser(description="ViMax 后端作业单（vimax-runtime.md）")
    ap.add_argument("--artifacts", help="01–04 所在目录")
    ap.add_argument("--out", help="作业单与会话目录写到哪")
    ap.add_argument("--workflow", choices=list(WORKFLOWS), help="必须显式点名：idea2video/script2video/novel2video")
    ap.add_argument("--script", help="script2video 的源剧本文件")
    ap.add_argument("--novel", help="novel2video 的源小说文件")
    ap.add_argument("--idea", help="idea2video 的创意句（缺省取 01 的 goal 并标为隐含源）")
    ap.add_argument("--session-id")
    ap.add_argument("--approve-render", metavar="NOTE", help="记录一次显式批准（只记录，不执行）")
    ap.add_argument("--stamp", action="store_true", help="写入生成者字段（默认不写时间戳，保持可复现）")
    ap.add_argument("--force", action="store_true", help="覆盖同目录既有作业单")
    ap.add_argument("--json", action="store_true", help="额外打印完整作业单")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.artifacts or not args.out:
        ap.print_help()
        return RC_USAGE
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
