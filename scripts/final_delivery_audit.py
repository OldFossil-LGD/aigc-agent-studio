"""Last, read-only delivery firewall. The Agent repairs and reruns this audit.

All paths in the manifest are relative to that manifest. Existing source-review,
prompt, canvas and media validators remain the owners of their respective checks.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path
import unicodedata
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.delivery_contract import derive as derive_contract
from scripts.delivery_contract import exemption_reasons, load_contract, validate as validate_contract
from scripts.delivery_review import evaluate_delivery_review, task_fingerprint
from scripts.compile_intent_delivery import grill_gate_for, GRILL_PASS_STATUSES
from scripts.verify_delivery_semantics import verify_delivery
from scripts.libtv_canvas_build import audit_canvas
from scripts.media_qc import run_gate
from scripts.film_qc_gate import verify_review_binding
from scripts.production_capability_gate import evaluate as evaluate_production


PLACEHOLDER_WORDS = {"TODO", "TBD", "FIXME", "XXX", "待补", "待定", "待补充", "待完善"}


DECORATION = "".join(chr(code) for code in (
    9, 35, 62, 45, 42, 43, 91, 93, 40, 41, 0xFF08, 0xFF09, 0x3010, 0x3011,
    0x300C, 0x300D, 0x27, 0x22, 0x3A, 0xFF1A, 0x60))


def _is_placeholder(body):
    core = unicodedata.normalize("NFKC", body).strip().strip(DECORATION).strip()
    if not core:
        return False
    token = core.split(chr(58), 1)[0].split(chr(65306), 1)[0].strip()
    if token.upper() not in PLACEHOLDER_WORDS:
        return False
    return core == token or core[len(token):].lstrip().startswith(":")


def _placeholder_line(text, *, allow_examples=False):
    """A document with a placeholder paragraph is unfinished, not merely short."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if allow_examples:
            if stripped.startswith(("```", "~~~")):
                marker = stripped[:3]
                fence = None if fence == marker else marker
                continue
            if fence or stripped.startswith(">"):
                continue
        body = line.strip().lstrip("#>-*+ \t").strip()
        if not body:
            continue
        if _is_placeholder(body):
            return number, body
    return None


def _file_digest(path):
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def audit_manifest(manifest_path):
    """Return evidence for current bytes. No writes, generation or repair calls."""
    checks, fingerprints = [], {}
    result = {"audit_format": "final-delivery-audit/v1", "status": "BLOCKED",
              "delivery_ready": False, "checks": checks, "inputs": fingerprints,
              "generation_authorized": False, "creative_quality_verified": False,
              "media_quality_verified": False, "manifest": str(Path(manifest_path).resolve())}
    base = Path(manifest_path).resolve().parent

    def read(path):
        resolved = (base / path).resolve()
        previous = fingerprints.setdefault(str(resolved), None)
        data = resolved.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if previous is not None and previous != digest:
            raise ValueError("Input changed during audit: " + str(resolved))
        fingerprints[str(resolved)] = digest
        return data

    def load(path):
        data = json.loads(read(path).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object: " + str(path))
        return data

    def check(name, callback):
        try:
            detail = callback()
            passed = detail.get("status") == "PASS"
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
            detail, passed = {"error": str(exc)}, False
        checks.append({"name": name, "status": "PASS" if passed else "BLOCKED", "detail": detail})

    try:
        manifest = load(str(Path(manifest_path).resolve()))
        kind = manifest.get("kind")
        if manifest.get("audit_format") != "final-delivery-audit/v1" or kind not in {"text", "prompt", "plan", "canvas", "film"}:
            raise ValueError("Unknown audit format or delivery kind")
        task = load(manifest["task"])
        result["task_sha256"] = task_fingerprint(task)
        task_type = task.get("task_type")
        if task.get("intent_format") and kind == "text":
            raise ValueError("An intent/prompt task cannot bypass checks as a text review")
        if task_type in {"prompt_only", "single_shot"} and kind != "prompt":
            raise ValueError("Prompt-only endpoint requires the prompt audit")
        delivery = task.get("delivery") or {}
        if delivery.get("requires_export") and kind != "film":
            raise ValueError("Export delivery requires the film audit")
        paths = manifest.get("artifacts")
        if not isinstance(paths, list) or not paths:
            raise ValueError("Declare the actual delivery files")
        artifacts, resolved_artifacts = {}, set()
        video = (base / manifest["video"]).resolve() if manifest.get("video") else None
        for path in paths:
            if not isinstance(path, str) or not path.strip():
                raise ValueError("Invalid artifact path")
            resolved = (base / path).resolve()
            if resolved.name in artifacts or resolved in resolved_artifacts:
                raise ValueError("Ambiguous or duplicate artifact: " + path)
            if resolved == video:
                fingerprints[str(resolved)] = None
                digest, size = _file_digest(resolved)
                fingerprints[str(resolved)] = digest
                if not size:
                    raise ValueError("Empty artifact: " + path)
                text = "sha256:" + digest + ";bytes:" + str(size)
            else:
                data = read(path)
                if not data.strip():
                    raise ValueError("Empty artifact: " + path)
                # Match Path.read_text's universal-newline convention used by
                # the existing creative-review CLI. Raw-byte hashes stay exact.
                text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                if text.strip() in PLACEHOLDER_WORDS:
                    raise ValueError("Placeholder artifact: " + path)
                unfinished = _placeholder_line(text, allow_examples=kind == "text")
                if unfinished is not None:
                    raise ValueError("Unfinished section at line %d of %s: %s"
                                     % (unfinished[0], path, unfinished[1]))
                if resolved.suffix == ".json":
                    json.loads(text)
                elif resolved.suffix == ".jsonl":
                    for line in text.splitlines():
                        if line.strip():
                            json.loads(line)
            artifacts[resolved.name] = text
            resolved_artifacts.add(resolved)
        if manifest.get("contract"):
            read(manifest["contract"])  # a contract is evidence too: hash it
            contract = load_contract(base / manifest["contract"])
            # A contract may add scope; it may never drop a delivery the task
            # already states. Otherwise a minimal contract becomes the bypass.
            stated = derive_contract(task, kind)
            declared = {item.get("name") for item in contract.get("required_artifacts") or []
                        if isinstance(item, dict)}
            for item in stated["required_artifacts"]:
                if item["name"] not in declared:
                    contract.setdefault("required_artifacts", []).append(item)
        else:
            contract = derive_contract(task, kind)
        required = derive_contract(task, kind)["required_checks"]
        declared_checks = contract.get("required_checks") or []
        if not isinstance(declared_checks, list) or any(not isinstance(name, str) for name in declared_checks):
            raise ValueError("Contract required_checks must contain check names")
        contract["required_checks"] = list(dict.fromkeys(required + declared_checks))
        scope = validate_contract(contract, task, kind, manifest.get("project"), paths, root=base)
        checks.append({"name": "delivery_contract_scope_and_target",
                       "status": scope["status"], "detail": scope})
        checks.append({"name": "actual_files_and_scope", "status": "PASS", "count": len(artifacts)})
        if scope["status"] != "PASS":
            return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        checks.append({"name": "actual_files_and_scope", "status": "BLOCKED", "error": str(exc)})
        return result

    def review_check():
        review = load(manifest["review"])
        for item in (review.get("context_plan") or {}).get("files") or []:
            read(str(ROOT / item["path"]))
        for item in (review.get("read_receipt") or {}).get("reads") or []:
            read(str((base / manifest["capture_root"]) / item["capture_path"]))
        checked = evaluate_delivery_review(
            ROOT, task, artifacts, review,
            capture_root=base / manifest["capture_root"], session_id=manifest["session"])
        return dict(checked, status="PASS" if checked["delivery_ready"] else "BLOCKED")

    check("current_task_sources_and_decisions", review_check)

    required_checks = set(contract["required_checks"])
    if "production" in required_checks:
        def production_check():
            directory = Path(manifest["prompt_dir"])
            for filename in ("01_production_contract.json", "02_asset_graph_plan.json",
                             "03_shot_graph_plan.json", "04_prompt_packages.jsonl"):
                if (base / directory / filename).resolve() not in resolved_artifacts:
                    raise ValueError("Review must include compiled input: " + filename)
            contract = load(directory / "01_production_contract.json")
            contract = contract.get("production_contract", contract)
            assets = load(directory / "02_asset_graph_plan.json")
            graph = load(directory / "03_shot_graph_plan.json")
            packages = [json.loads(line) for line in read(directory / "04_prompt_packages.jsonl").decode("utf-8").splitlines() if line.strip()]
            grill = grill_gate_for(task, load(manifest["grill"]))
            if grill["status"] not in GRILL_PASS_STATUSES:
                return {"status": "BLOCKED", "grill": grill}
            return evaluate_production(contract, assets, graph, packages)
        check("production_contract_roles_dependencies_and_prompts", production_check)

    if "prompt" in required_checks:
        def prompt_check():
            directory = Path(manifest["prompt_dir"])
            packages = [json.loads(line) for line in read(directory / "04_prompt_packages.jsonl").decode("utf-8").splitlines() if line.strip()]
            graph = load(directory / "03_shot_graph_plan.json")
            markdown_path = (base / manifest["prompt_markdown"]).resolve()
            if markdown_path not in resolved_artifacts:
                raise ValueError("Audited prompt Markdown must be a delivered artifact")
            grill = grill_gate_for(task, load(manifest["grill"]))
            if grill["status"] not in GRILL_PASS_STATUSES:
                return {"status": "BLOCKED", "grill": grill}
            return verify_delivery(task, packages, graph, read(manifest["prompt_markdown"]).decode("utf-8"))
        check("prompt_packages_graph_and_constraints", prompt_check)

    if kind == "canvas" or manifest.get("canvas_plan"):
        def canvas_check():
            if not manifest.get("canvas_plan"):
                raise ValueError("A canvas plan is required for this delivery kind")
            if (base / manifest["canvas_plan"]).resolve() not in resolved_artifacts:
                raise ValueError("Review must include the current canvas plan")
            plan = load(manifest["canvas_plan"])
            project = manifest["project"]
            if not isinstance(project, str) or not project.strip():
                raise ValueError("A current target project is required")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = audit_canvas(project, plan, strict_effective=kind == "film")
            # Empty references can be expected in an ungenerated canvas. Keep
            # that warning visible, while film delivery requires effective refs.
            passed = code == 0 or (code == 4 and kind == "canvas")
            return {"status": "PASS" if passed else "BLOCKED",
                    "exit": code, "readback": output.getvalue(), "project": project}
        check("actual_canvas_nodes_parameters_and_references", canvas_check)

    if kind == "film" and not manifest.get("canvas_plan"):
        exempt = exemption_reasons(contract)
        if not exempt.get("canvas"):
            checks.append({
                "name": "actual_canvas_nodes_parameters_and_references",
                "status": "BLOCKED",
                "error": "The film branch must audit the canvas unless the contract states an exemption reason",
            })

    if kind == "film":
        def media_check():
            if video is None or video not in resolved_artifacts:
                raise ValueError("The actual delivered video must be listed as an artifact")
            decisions = task.get("decisions") or {}
            expect = {"duration": (decisions.get("duration_sec") or {}).get("value"),
                      "ratio": (decisions.get("aspect_ratio") or {}).get("value")}
            code, qc = run_gate(str(video), expect)
            binding = verify_review_binding(str(video), load(manifest["media_record"]), load(manifest["media_review"]))
            return {"status": "PASS" if code == 0 and qc.get("status") == "PASS" and binding["status"] == "PASS" else "BLOCKED",
                    "technical": qc, "review_binding": binding}
        check("actual_media_and_review_binding", media_check)

    registry = {"review": "current_task_sources_and_decisions",
                "production": "production_contract_roles_dependencies_and_prompts",
                "prompt": "prompt_packages_graph_and_constraints",
                "canvas": "actual_canvas_nodes_parameters_and_references",
                "film": "actual_media_and_review_binding"}
    specialist_scripts = {"shotlist": "shotlist_lint.py", "prompt_style": "audit_prompt.py",
                          "ai_smell": "ai_smell_check.py"}
    for name in sorted(required_checks & specialist_scripts.keys()):
        def specialist_check(name=name):
            specification = (manifest.get("specialists") or {}).get(name) or {}
            path = (base / specification["path"]).resolve()
            if path not in resolved_artifacts:
                raise ValueError("Specialist input must be a reviewed artifact")
            read(str(path))
            arguments = [str(path)]
            if name == "shotlist":
                mode = specification.get("mode", "cut")
                if mode not in {"cut", "gen"}:
                    raise ValueError("Unknown shotlist mode")
                arguments += ["--mode", mode]
            elif name == "prompt_style":
                arguments.insert(0, "blocks")
                if specification.get("asset") is True:
                    arguments.append("--asset")
            script = ROOT / "scripts" / specialist_scripts[name]
            read(str(script))
            try:
                executed = subprocess.run([sys.executable, str(script)] + arguments,
                    capture_output=True, text=True, encoding="utf-8", timeout=120,
                    env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
            except subprocess.TimeoutExpired:
                return {"status": "BLOCKED", "error": "Specialist check timed out"}
            return {"status": "PASS" if executed.returncode == 0 else "BLOCKED",
                    "exit": executed.returncode, "stdout": executed.stdout, "stderr": executed.stderr}
        key = "specialist_" + name
        registry[name] = key
        check(key, specialist_check)

    completed = {item["name"]: item["status"] for item in checks}
    exempt = exemption_reasons(contract)
    absent = [name for name in required_checks if name not in registry
              or (not exempt.get(name) and completed.get(registry[name]) != "PASS")]
    checks.append({"name": "required_check_execution_receipts",
                   "status": "BLOCKED" if absent else "PASS", "missing_or_failed": sorted(absent),
                   "exemptions": exempt})

    def freshness_check():
        changed = [path for path, digest in fingerprints.items()
                   if _file_digest(path)[0] != digest]
        return {"status": "BLOCKED" if changed else "PASS", "changed": changed}
    check("inputs_unchanged_at_end", freshness_check)
    ready = all(item["status"] == "PASS" for item in checks)
    result.update(status="PASS" if ready else "BLOCKED", delivery_ready=ready, kind=kind)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = audit_manifest(args.manifest)
    target = Path(args.report).resolve()
    if str(target) in result["inputs"]:
        parser.error("The report must not overwrite an audited input")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, pending = tempfile.mkstemp(prefix=target.name + ".", suffix=".pending", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        os.replace(pending, target)
    finally:
        Path(pending).unlink(missing_ok=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["delivery_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
