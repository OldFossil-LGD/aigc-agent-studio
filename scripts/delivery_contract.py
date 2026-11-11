"""The delivery contract: the authoritative scope of one delivery.

The manifest maps actual files. The contract decides what must exist, where it
must land and which checks must run. Derivation never guesses: it only reads
declarations that are already explicit in the task.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CONTRACT_FORMAT = "delivery-contract/v1"
ENDPOINTS = ("text", "prompt", "plan", "canvas", "film")

# Auxiliary recognition for explicitly named outputs. Source/reference mentions
# are not output declarations; richer requirements use required_artifacts.
FILE_HINT = re.compile(r"([A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,5})\b")

REQUIRED_CHECKS = {
    "text": ("review",),
    "prompt": ("review", "production", "prompt"),
    "plan": ("review", "production"),
    "canvas": ("review", "canvas"),
    "film": ("review", "canvas", "film"),
}


def load_contract(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    if data.get("contract_format") != CONTRACT_FORMAT:
        raise ValueError("Unknown delivery contract format: %r" % (data.get("contract_format"),))
    return data


def _declared_artifacts(value):
    required = []
    for item in value:
        if isinstance(item, str) and item.strip():
            required.append({"name": item.strip(), "requirement_ids": []})
        elif isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
            required.append({"name": item["name"].strip(),
                             "requirement_ids": [str(x) for x in (item.get("requirement_ids") or [])]})
    return required


def derive(task, kind):
    """Build the contract from what the task already states. No inference."""
    delivery = task.get("delivery") or {}
    endpoint = delivery.get("endpoint", kind)
    if endpoint not in ENDPOINTS:
        raise ValueError("Unknown task delivery endpoint")
    declared = delivery.get("required_artifacts")
    required = _declared_artifacts(declared) if isinstance(declared, list) else []
    source = "task.delivery.required_artifacts+requirements" if required else "requirements"
    # A declaration may add deliveries; it may never remove one the requirements
    # already name. An empty list is not permission to skip a stated delivery.
    for requirement in task.get("requirements") or []:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("text"), str):
            continue
        for clause in re.split(r"[，,。；;\n]", requirement["text"]):
            verb = re.search(r"交付|输出|导出|\bdeliver\b|\boutput\b|\bexport\b", clause, re.IGNORECASE)
            if verb is None or re.search(r"不要|不需要|无需|\bnot\b", clause[:verb.start()], re.IGNORECASE):
                continue
            for name in FILE_HINT.findall(clause[verb.end():]):
                if name not in {item["name"] for item in required}:
                    required.append({"name": name,
                                     "requirement_ids": [str(requirement["id"])] if requirement.get("id") else []})
    project = task.get("project_uuid") or task.get("project") or delivery.get("project_uuid")
    extra_checks = delivery.get("required_checks") or []
    if not isinstance(extra_checks, list) or any(not isinstance(name, str) or not name.strip() for name in extra_checks):
        raise ValueError("delivery.required_checks must be a list of check names")
    if kind == "film" and task.get("intent_format"):
        extra_checks = extra_checks + ["production"]
    return {
        "contract_format": CONTRACT_FORMAT,
        "source": "derived:" + source,
        "endpoint": endpoint,
        "project_uuid": project,
        "required_artifacts": required,
        "required_checks": list(dict.fromkeys(list(REQUIRED_CHECKS.get(kind, ("review",))) + extra_checks)),
        "exemptions": [],
    }


def exemption_reasons(contract):
    reasons = {}
    for item in contract.get("exemptions") or []:
        if isinstance(item, dict) and isinstance(item.get("check"), str):
            reasons[item["check"]] = (item.get("reason") or "").strip()
    return reasons


def validate(contract, task, kind, project, artifact_names, *, root=None):
    """Compare the declared scope against what the delivery actually is."""
    errors = []
    task_endpoint = (task.get("delivery") or {}).get("endpoint")
    if task_endpoint is not None and task_endpoint != kind:
        errors.append("Audited kind does not match the task delivery endpoint")
    if contract.get("endpoint") != kind:
        errors.append("Contract endpoint %r does not match audited kind %r"
                      % (contract.get("endpoint"), kind))

    present = {Path(str(name)).name for name in artifact_names}
    anchor = Path(root or ".").resolve()
    actual_paths = {(anchor / str(name)).resolve() for name in artifact_names}
    for item in contract.get("required_artifacts") or []:
        name = item.get("name") if isinstance(item, dict) else None
        if not name:
            errors.append("Contract artifact entry without a name")
        elif Path(name).name not in present:
            errors.append("Required delivery is missing: " + name)
        elif (Path(name).is_absolute() or Path(name).parent != Path(".")) and (anchor / name).resolve() not in actual_paths:
            errors.append("Required delivery path is missing: " + name)

    reasons = exemption_reasons(contract)
    explicit_checks = set((task.get("delivery") or {}).get("required_checks") or [])
    authorized = exemption_reasons({"exemptions": (task.get("delivery") or {}).get("exemptions") or []})
    for name in explicit_checks & reasons.keys():
        if not authorized.get(name):
            errors.append("A contract cannot waive an explicit task check: " + name)
    for name in contract.get("required_checks") or list(REQUIRED_CHECKS.get(kind, ("review",))):
        if name in reasons and not reasons[name]:
            errors.append("Exemption for check %r needs a stated reason" % name)

    # A platform project only exists for canvas and film deliveries. The task
    # outranks the contract: a contract may not retarget someone else's canvas.
    task_target = task.get("project_uuid") or task.get("project") or (task.get("delivery") or {}).get("project_uuid")
    contract_target = contract.get("project_uuid")
    if kind in {"canvas", "film"}:
        if task_target and contract_target and str(task_target) != str(contract_target):
            errors.append("Contract retargets the task project %r to %r" % (task_target, contract_target))
        target = task_target or contract_target
        if not target and not (kind == "film" and reasons.get("canvas")):
            errors.append("No authoritative target project for a canvas or film delivery")
    else:
        target = None
    if target:
        if not project:
            errors.append("No audited project to bind against target " + str(target))
        elif str(target) != str(project):
            errors.append("Audited project %r is not the task target %r" % (project, target))

    return {
        "status": "BLOCKED" if errors else "PASS",
        "errors": errors,
        "endpoint": contract.get("endpoint"),
        "source": contract.get("source"),
        "required_artifacts": [item.get("name") for item in contract.get("required_artifacts") or []
                               if isinstance(item, dict)],
        "required_checks": list(contract.get("required_checks") or []),
        "exemptions": reasons,
        "project": project,
        "target_project": target,
    }
