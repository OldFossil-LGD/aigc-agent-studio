#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""offline_package_lint —— 离线生成包门禁。

用途：对“剧本 -> Production Record / Graph Plan / Prompt Package”的离线包做统一机检。
它不联网、不建节点、不点火、不导出。

用法：
  python3 scripts/offline_package_lint.py <package_dir> --schema-dir outputs/统一基准
  python3 scripts/offline_package_lint.py --self-test

退出码：
  0 通过
  1 检出问题
  2 用法错
  3 包不完整，无法完成全部检查
  4 子检查警告，需要复核
"""
import argparse
import glob
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


class DuplicateKeyError(ValueError):
    pass


def _no_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError("重复 JSON 键：%s" % key)
        out[key] = value
    return out


def load_json_strict(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=_no_duplicate_pairs)


def load_jsonl_strict(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line, object_pairs_hook=_no_duplicate_pairs))
            except DuplicateKeyError as exc:
                raise DuplicateKeyError("%s:%d %s" % (path, line_no, exc))
    return rows


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", env=CHILD_ENV)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def find_one(package, pattern):
    hits = sorted(glob.glob(os.path.join(package, pattern)))
    return hits[0] if hits else None


def require_file(package, name):
    path = os.path.join(package, name)
    return path if os.path.isfile(path) else None


def _add(results, name, rc, detail):
    results.append({"name": name, "rc": rc, "detail": detail})


def _schema_validate(path, schema_path, rows):
    try:
        import jsonschema
    except ImportError as exc:
        return 3, "缺 jsonschema：%s" % exc
    schema = load_json_strict(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    for idx, row in enumerate(rows, 1):
        try:
            validator.validate(row)
        except Exception as exc:
            return 1, "%s 第 %d 条不符合 schema：%s" % (path, idx, exc)
    return 0, "%d/%d 符合 schema" % (len(rows), len(rows))


def _find_ignition_fields(obj, path="$"):
    findings = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = "%s.%s" % (path, key)
            if key in ("taskId", "providerTaskId"):
                findings.append("%s=%r" % (here, value))
            if key == "taskInfo" and isinstance(value, dict):
                findings.append("%s 是实际 taskInfo 对象" % here)
            if key == "run" and value is True:
                findings.append("%s=true" % here)
            if key == "state" and value in ("generated", "reviewed", "assembled", "delivered"):
                findings.append("%s=%r" % (here, value))
            if key in ("url", "previewPath", "resourceUrl") and isinstance(value, str) and value.startswith(("http://", "https://")):
                findings.append("%s=%r" % (here, value[:80]))
            findings += _find_ignition_fields(value, here)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            findings += _find_ignition_fields(value, "%s[%d]" % (path, idx))
    return findings


def _semantic_checks(package, records, plan, packages):
    checks = []
    plan_nodes = {n.get("node_id"): n for n in plan.get("nodes") or []}
    package_by_id = {p.get("prompt_id"): p for p in packages}
    map_path = os.path.join(package, "04_Source_Node_Map.json")
    source_map = {}
    if os.path.isfile(map_path):
        try:
            source_map = load_json_strict(map_path)
        except Exception:
            source_map = {}
    observed_map = source_map.get("observed_w2_nodes") or {}
    required_targets = {"asset", "storyboard", "video", "audio", "composite"}
    targets = {p.get("target_type") for p in packages}
    missing_targets = sorted(required_targets - targets)
    checks.append(("semantic.required_target_types", 0 if not missing_targets else 1,
                   "齐全" if not missing_targets else "缺 " + ", ".join(missing_targets)))

    bad_records = []
    duration_by_package = {}
    for record in records:
        sid = record.get("shot_id")
        pid = record.get("prompt_package_id")
        if pid not in package_by_id:
            bad_records.append("%s.prompt_package_id=%r 不存在" % (sid, pid))
        duration_by_package.setdefault(pid, 0)
        duration_by_package[pid] += record.get("duration_sec", 0)
        for asset_id in record.get("asset_ids") or []:
            mapped = asset_id in plan_nodes or (observed_map.get(asset_id) or {}).get("plan_node") in plan_nodes
            if not mapped:
                bad_records.append("%s.asset_id=%r 不在 Graph Plan" % (sid, asset_id))
    checks.append(("semantic.record_to_plan", 0 if not bad_records else 1,
                   "通过" if not bad_records else "; ".join(bad_records[:5])))

    bad_refs = []
    for package_row in packages:
        for ref in package_row.get("reference_nodes") or []:
            nid = ref.get("node_id")
            if nid not in plan_nodes:
                bad_refs.append("%s reference=%r 不在 Graph Plan" % (package_row.get("prompt_id"), nid))
    checks.append(("semantic.package_references", 0 if not bad_refs else 1,
                   "通过" if not bad_refs else "; ".join(bad_refs[:5])))

    bad_duration = []
    for pid, seconds in sorted(duration_by_package.items()):
        package_row = package_by_id.get(pid)
        if not package_row:
            continue
        if package_row.get("target_type") in ("asset", "storyboard"):
            continue
        pkg_sec = (package_row.get("duration") or {}).get("seconds")
        if pkg_sec != seconds:
            bad_duration.append("%s package=%r records=%r" % (pid, pkg_sec, seconds))
    checks.append(("semantic.duration", 0 if not bad_duration else 1,
                   "通过" if not bad_duration else "; ".join(bad_duration)))

    locked_bad = []
    for package_row in packages:
        if package_row.get("target_type") not in ("video", "audio"):
            continue
        all_text = "\n".join((b.get("text") or "") for b in package_row.get("blocks") or [])
        for locked in package_row.get("locked_text") or []:
            if locked.get("text") and locked["text"] not in all_text:
                locked_bad.append("%s locked_text=%r 未进入 blocks" % (package_row.get("prompt_id"), locked["text"][:40]))
    checks.append(("semantic.locked_text", 0 if not locked_bad else 1,
                   "通过" if not locked_bad else "; ".join(locked_bad[:5])))

    craft_bad = []
    for package_row in packages:
        if package_row.get("target_type") != "video":
            continue
        craft_blocks = [b for b in package_row.get("blocks") or []
                        if b.get("source") == "craft_prior"]
        text = "\n".join((b.get("text") or "") for b in package_row.get("blocks") or [])
        families = [k for k in ("人物", "动作", "时间线", "光位", "风格", "声音", "色彩", "表演") if k in text]
        if not craft_blocks or len(families) < 2:
            craft_bad.append("%s craft_prior=%d families=%s" % (
                package_row.get("prompt_id"), len(craft_blocks), ",".join(families)))
    checks.append(("semantic.craft_prior", 0 if not craft_bad else 1,
                   "通过" if not craft_bad else "; ".join(craft_bad[:5])))

    if os.path.isfile(map_path):
        try:
            record_map = source_map.get("records") or {}
            package_map = source_map.get("prompt_packages") or {}
            bad_map = []
            for record in records:
                sid = record.get("shot_id")
                if sid not in record_map:
                    bad_map.append("record %s missing source map" % sid)
            for package_row in packages:
                pid = package_row.get("prompt_id")
                mapped = package_map.get(pid)
                if not mapped or not mapped.get("plan_video_node"):
                    continue
                plan_node = mapped.get("plan_video_node")
                refs = sorted([r for r in package_row.get("reference_nodes") or []
                               if r.get("order") is not None], key=lambda x: x["order"])
                plan_refs = sorted([e for e in plan.get("edges") or []
                                    if e.get("target_id") == plan_node and e.get("kind") == "reference"],
                                   key=lambda x: x.get("order", 0))
                if [r.get("node_id") for r in refs] != [e.get("source_id") for e in plan_refs]:
                    bad_map.append("%s package refs != plan refs" % pid)
            checks.append(("semantic.source_map", 0 if not bad_map else 1,
                           "通过" if not bad_map else "; ".join(bad_map[:5])))
        except Exception as exc:
            checks.append(("semantic.source_map", 1, str(exc)))
    else:
        checks.append(("semantic.source_map", 3, "无 04_Source_Node_Map.json"))

    return checks


def _render_manifest_check(package):
    manifest_path = os.path.join(package, "prompt_render_manifest.json")
    if not os.path.isfile(manifest_path):
        return 1, "缺 prompt_render_manifest.json（先跑 render_offline_prompts.py）"
    try:
        manifest = load_json_strict(manifest_path)
        src = os.path.join(package, manifest.get("source", ""))
        if not os.path.isfile(src) or sha256_file(src) != manifest.get("source_sha256"):
            return 1, "Prompt Package 源哈希与 manifest 不一致"
        for rel, expected in (manifest.get("generated") or {}).items():
            path = os.path.join(package, rel)
            if not os.path.isfile(path) or sha256_file(path) != expected:
                return 1, "生成文档漂移：%s" % rel
        for rel, expected in (manifest.get("audit_sources") or {}).items():
            path = os.path.join(package, rel)
            if not os.path.isfile(path) or sha256_file(path) != expected:
                return 1, "审计载体漂移：%s" % rel
        total = len(manifest.get("generated") or {}) + len(manifest.get("audit_sources") or {})
        return 0, "%d/%d 生成与审计文档与 manifest 一致" % (total, total)
    except Exception as exc:
        return 1, str(exc)


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def lint(package, schema_dir):
    results = []
    if not os.path.isdir(package):
        _add(results, "package", 2, "目录不存在：%s" % package)
        return results
    component_manifest = {}
    component_path = os.path.join(package, "offline_package_manifest.json")
    if os.path.isfile(component_path):
        try:
            component_manifest = (load_json_strict(component_path).get("components") or {})
        except Exception as exc:
            _add(results, "offline_package_manifest", 1, str(exc))

    required = [
        "01_Production_Records.jsonl",
        "02_Graph_Plan.json",
        "03_Prompt_Packages.jsonl",
    ]
    for name in required:
        p = require_file(package, name)
        if not p:
            _add(results, name, 3, "缺失")
    if any(x["rc"] != 0 for x in results):
        return results

    prod_path = os.path.join(package, required[0])
    plan_path = os.path.join(package, required[1])
    pack_path = os.path.join(package, required[2])
    try:
        records = load_jsonl_strict(prod_path)
        plan = load_json_strict(plan_path)
        packages = load_jsonl_strict(pack_path)
        _add(results, "json.duplicate_keys", 0,
             "Production/Graph/Prompt 无重复键")
    except DuplicateKeyError as exc:
        _add(results, "json.duplicate_keys", 1, str(exc))
        return results
    except Exception as exc:
        _add(results, "json.parse", 1, str(exc))
        return results

    prod_schema = os.path.join(schema_dir, "production_record.schema.json")
    pack_schema = os.path.join(schema_dir, "prompt_package.schema.json")
    if os.path.isfile(prod_schema):
        rc, detail = _schema_validate(prod_path, prod_schema, records)
        _add(results, "production_record.schema", rc, detail)
    else:
        _add(results, "production_record.schema", 3, "schema 不存在：%s" % prod_schema)
    if os.path.isfile(pack_schema):
        rc, detail = _schema_validate(pack_path, pack_schema, packages)
        _add(results, "prompt_package.schema", rc, detail)
    else:
        _add(results, "prompt_package.schema", 3, "schema 不存在：%s" % pack_schema)

    semantic = _semantic_checks(package, records, plan, packages)
    for name, rc, detail in semantic:
        _add(results, name, rc, detail)

    rc, detail = _render_manifest_check(package)
    _add(results, "prompt.render_manifest", rc, detail)

    ignition = []
    ignition += _find_ignition_fields(records, "01_Production_Records")
    ignition += _find_ignition_fields(plan, "02_Graph_Plan")
    ignition += _find_ignition_fields(packages, "03_Prompt_Packages")
    _add(results, "offline.no_ignition", 0 if not ignition else 1,
         "未发现点火/生成字段" if not ignition else "; ".join(ignition[:5]))

    overlay = find_one(package, "10*Overlay*.json")
    graph_script = os.path.join(HERE, "graph_plan_lint.py")
    if os.path.isfile(graph_script):
        tmp_gate = None
        try:
            cmd = [PY, graph_script, "gate", "--plan", plan_path]
            if overlay:
                cmd += ["--overlay", overlay]
            fd, tmp_gate = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            cmd += ["--out", tmp_gate]
            rc, out = run(cmd)
            if rc in (0, 3):
                gates = load_json_strict(tmp_gate).get("gate_results", [])
                by_name = {g.get("gate_name"): g for g in gates}
                structure = by_name.get("graph_plan.structure", {}).get("exit_code")
                reference = by_name.get("graph_plan.reference", {}).get("exit_code")
                if structure == 0 and reference == 0:
                    _add(results, "graph_plan.structure_reference", 0,
                         "structure/reference 通过；media/cost 按未点火分账")
                else:
                    _add(results, "graph_plan.structure_reference", 1,
                         "structure=%r reference=%r" % (structure, reference))
            else:
                _add(results, "graph_plan.gate", 1, out[-2000:])
        finally:
            if tmp_gate and os.path.exists(tmp_gate):
                os.remove(tmp_gate)
    else:
        _add(results, "graph_plan.gate", 3, "缺 graph_plan_lint.py")

    audit_script = os.path.join(HERE, "audit_prompt.py")
    audit_files = sorted(glob.glob(os.path.join(package, "*_audit.md")))
    if audit_files and os.path.isfile(audit_script):
        for path in audit_files:
            rc, out = run([PY, audit_script, "blocks", path])
            _add(results, "prompt.blocks:" + os.path.basename(path),
                 rc if rc in (0, 1, 2, 3, 4, 5) else 1, out[-1200:])
    else:
        _add(results, "prompt.blocks", 3, "没有 *_audit.md 载体")

    sound_script = os.path.join(HERE, "sound_lint.py")
    sound_file = find_one(package, "18*.md")
    if sound_file and os.path.isfile(sound_script):
        rc, out = run([PY, sound_script, sound_file])
        _add(results, "sound_lint", rc, out[-1200:])
    elif component_manifest.get("sound_table") == "not_applicable":
        _add(results, "sound_lint", 5, "manifest 声明 sound_table=not_applicable")
    else:
        _add(results, "sound_lint", 3, "没有 18*.md 声音表")

    timeline_file = find_one(package, "19*.md")
    if timeline_file and os.path.isfile(audit_script):
        rc, out = run([PY, audit_script, "timeline", timeline_file])
        _add(results, "timeline", rc, out[-1200:])
    elif component_manifest.get("composite_timeline") == "not_applicable":
        _add(results, "timeline", 5, "manifest 声明 composite_timeline=not_applicable")
    else:
        _add(results, "timeline", 3, "没有 19*.md 时间线")

    smell_script = os.path.join(HERE, "ai_smell_check.py")
    if os.path.isfile(smell_script):
        rc, out = run([PY, smell_script, package])
        _add(results, "ai_smell", rc, out[-1200:])
    else:
        _add(results, "ai_smell", 3, "缺 ai_smell_check.py")
    return results


def self_test():
    try:
        load_json_strict
    except Exception:
        return 1
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write('{"a":1,"a":2}')
        try:
            load_json_strict(path)
            return 1
        except DuplicateKeyError:
            pass
        if not _find_ignition_fields({"taskId": "x"}):
            return 1
        if not _find_ignition_fields({"state": "generated"}):
            return 1
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("self-test 通过")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["--self-test"], ["-t"]):
        return self_test()
    parser = argparse.ArgumentParser(description="离线生成包门禁")
    parser.add_argument("package", nargs="?", help="离线生成包目录")
    parser.add_argument("--schema-dir", default=os.path.join(os.getcwd(), "outputs", "统一基准"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.package:
        parser.print_help()
        return 2
    results = lint(os.path.abspath(args.package), os.path.abspath(args.schema_dir))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print("[%s] %s  %s" % (
                {0: "PASS", 1: "FAIL", 2: "USAGE", 3: "UNDET", 4: "WARN", 5: "NA"}.get(item["rc"], item["rc"]),
                item["name"], item["detail"].replace("\n", " ")[:300]))
    for status in (1, 2, 3, 4):
        if any(item["rc"] == status for item in results):
            return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
