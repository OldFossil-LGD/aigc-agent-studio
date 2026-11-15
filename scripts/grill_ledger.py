"""Grill ledger (grill-ledger/v1) — the pre-flight interrogation ledger.

**Why this file exists.** A vague brief is not a lack of taste; it is a set of
undecided branches wearing prose. The Agent can ask better questions than the
user can phrase them — but only if the asking respects dependency order and the
answers survive the conversation.

So this module mechanises the *deterministic* half of `references/grill-me.md`:

* **frontier** — which questions may be asked NOW (every prerequisite settled);
* **ledger validation** — an answer's basis, evidence and lock obey the same
  discipline as `intent-handoff/v1`: only a user-explicit decision may be
  locked, a verified fact needs a real in-package evidence file, and a paid
  ignition needs a user-explicit approval (an Agent proposal is refused);
* **gate** — at stop `prompt` / `film` / `generation`, name the blocking gaps;
* **patch** — emit only the intent fields this ledger can fill mechanically and
  hand everything else back as `carry_forward` instead of inventing it.

Rejected on purpose: asking the user for facts the library can answer, asking
downstream questions before their prerequisites, and treating `GRILL_PASS` as
permission to generate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def grill_session_same_file(left, right) -> bool:
    """同一文件判定看 inode：硬链接别名按路径比是查不出来的。"""
    left_path, right_path = Path(left), Path(right)
    try:
        if left_path.resolve() == right_path.resolve():
            return True
    except OSError:
        pass
    try:
        left_stat, right_stat = left_path.stat(), right_path.stat()
    except OSError:
        return False
    return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)

try:
    from ._common import RC_FAIL, RC_OK, RC_USAGE, RC_WARN
except ImportError:
    from _common import RC_FAIL, RC_OK, RC_USAGE, RC_WARN

try:
    from .grill_bank import (QUESTION_BANK, QUESTION_INDEX, STOPS, STOPS_BY_TASK,
                             STYLE_REGISTERS, TASK_TYPES)
except ImportError:
    from grill_bank import (QUESTION_BANK, QUESTION_INDEX, STOPS, STOPS_BY_TASK,
                            STYLE_REGISTERS, TASK_TYPES)

FORMAT = "grill-ledger/v1"
CONTRACT_FORMAT = "creative-intent-contract/v1"
CONTRACT_SCHEMA_VERSION = "1.0.0"
PATCH_FORMAT = "grill-intent-patch/v1"
ROOT = Path(__file__).resolve().parents[1]

STATUSES = ("resolved", "open", "deferred", "out_of_scope", "not_applicable")
SETTLED = ("resolved", "out_of_scope", "not_applicable")
BASES = ("user_explicit", "verified_fact", "craft_default", "agent_proposal")
EVIDENCE_TYPES = ("platform", "cross_work", "work_profile", "craft_prior",
                  "library_rule", "example", "unknown")
RATIO_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?\s*$")

# basis -> intent-handoff decision source. Only `user_explicit` may be locked;
# a fact or a craft default is a `default`, never the user's own decision.
SOURCE_BY_BASIS = {
    "user_explicit": "user_explicit",
    "verified_fact": "default",
    "craft_default": "default",
    "agent_proposal": "agent_proposed",
}



class GrillError(ValueError):
    """Raised when a ledger cannot be trusted as the interview record."""


# ---------- reading ----------

def load_ledger(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise GrillError("GRILL_UNREADABLE: %s" % exc)
    except ValueError as exc:
        raise GrillError("GRILL_UNREADABLE: not JSON: %s" % exc)
    if not isinstance(payload, dict):
        raise GrillError("GRILL_INVALID: ledger must be a JSON object")
    return payload


def _entry_map(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return {}
    return {entry["id"]: entry for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)}


def _settled(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and entry.get("status") in SETTLED


def _reachable_stops(ledger: dict[str, Any]) -> frozenset[str]:
    """Which stops this job can still reach, given its (possibly unset) delivery target.

    A prompt-only job never reaches the film stop, so film-stage branches must
    not appear on its frontier: asking them would be interrogation theatre.
    """

    root = _entry_map(ledger).get("G01")
    task_type = root.get("answer") if root and root.get("status") == "resolved" else None
    if task_type == "prompt_only":
        return frozenset(("prompt",))
    if task_type == "single_shot":
        return frozenset(("prompt", "generation"))
    return frozenset(STOPS)


def _in_scope(question: dict[str, Any], reachable: frozenset[str]) -> bool:
    return bool(set(question["stops"]) & reachable)


def _when_applies(question: dict[str, Any], ledger: dict[str, Any],
                  entries: dict[str, dict[str, Any]]) -> bool:
    when = question.get("when") or {}
    if "job_kind" in when:
        job = ledger.get("job") or {}
        return job.get("kind") in when["job_kind"]
    if "question" in when:
        dependency = entries.get(when["question"])
        if not _settled(dependency) or dependency.get("status") != "resolved":
            return False
        answer = dependency.get("answer")
        if isinstance(answer, list):
            return any(item in when["values"] for item in answer)
        return answer in when["values"]
    return True


# ---------- validation ----------

def _value_errors(question: dict[str, Any], answer: Any) -> list[str]:
    """Delegates to the bank so the session engine and the gate agree."""

    try:
        from .grill_bank import answer_errors
    except ImportError:
        from grill_bank import answer_errors
    return answer_errors(question, answer)


def _evidence_errors(entry: dict[str, Any], index: int) -> list[str]:
    label = "entry %d (%s)" % (index, entry.get("id"))
    evidence = entry.get("evidence")
    if evidence is None:
        return []
    if not isinstance(evidence, list):
        return ["%s evidence must be a list" % label]
    errors = []
    for position, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            errors.append("%s evidence %d must be an object" % (label, position))
            continue
        kind = item.get("type")
        if kind not in EVIDENCE_TYPES:
            errors.append("%s evidence %d type %r is not one of %s"
                          % (label, position, kind, ", ".join(EVIDENCE_TYPES)))
            continue
        ref = item.get("ref")
        if kind == "unknown":
            continue
        if not isinstance(ref, str) or not ref.strip():
            errors.append("%s evidence %d needs a package-relative ref" % (label, position))
            continue
        if Path(ref).is_absolute() or ".." in Path(ref).parts:
            errors.append("%s evidence %d ref must stay inside the package: %s"
                          % (label, position, ref))
            continue
        if not (ROOT / ref).is_file():
            errors.append("%s evidence %d ref does not exist: %s"
                          % (label, position, ref))
    return errors


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    """Return every problem with the ledger; an empty list means trustworthy."""

    errors: list[str] = []
    if ledger.get("grill_format") != FORMAT:
        errors.append("GRILL_FORMAT: expected grill_format %r, got %r"
                      % (FORMAT, ledger.get("grill_format")))
    job = ledger.get("job")
    if not isinstance(job, dict):
        errors.append("GRILL_JOB: job must be an object with kind")
    elif job.get("kind") not in ("original", "reverse"):
        errors.append("GRILL_JOB: job.kind must be 'original' or 'reverse'")
    entries = ledger.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        errors.append("GRILL_ENTRIES: entries must be a list")
        return errors

    mapped = _entry_map(ledger)
    if len(mapped) != len(entries):
        errors.append("GRILL_ENTRY_SHAPE: every entry needs a string id")
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append("GRILL_ENTRY_SHAPE: entry %d must be an object" % index)
            continue
        question_id = entry.get("id")
        if question_id in seen:
            errors.append("GRILL_DUPLICATE: entry %s appears twice" % question_id)
            continue
        if question_id in QUESTION_INDEX:
            seen.add(question_id)
        question = QUESTION_INDEX.get(question_id)
        if question is None:
            errors.append("GRILL_UNKNOWN_QUESTION: %r is not in the question bank; "
                          "an unmapped creative field must stay unresolved, not be dropped"
                          % (question_id,))
            continue

        if entry.get("projection_error"):
            errors.append(str(entry["projection_error"]))
            continue
        status = entry.get("status")
        if status not in STATUSES:
            errors.append("GRILL_STATUS: entry %s status %r is not one of %s"
                          % (question_id, status, ", ".join(STATUSES)))
            continue
        basis = entry.get("basis")
        locked = entry.get("locked", False)
        if not isinstance(locked, bool):
            errors.append("GRILL_LOCK: entry %s locked must be a boolean" % question_id)
            locked = False
        if status == "resolved":
            if basis not in BASES:
                errors.append("GRILL_BASIS: entry %s needs a basis in %s"
                              % (question_id, ", ".join(BASES)))
            if "answer" not in entry:
                errors.append("GRILL_ANSWER: resolved entry %s has no answer" % question_id)
            else:
                for message in _value_errors(question, entry.get("answer")):
                    errors.append("GRILL_ANSWER: entry %s %s" % (question_id, message))
            if basis == "user_explicit" and not locked:
                errors.append("GRILL_LOCK: entry %s is user_explicit and must be locked"
                              % question_id)
            if locked and basis != "user_explicit":
                errors.append("GRILL_LOCK: entry %s cannot be locked while its basis is %r; "
                              "only a user-explicit decision may be reported as locked"
                              % (question_id, basis))
            if basis == "verified_fact":
                usable = [item for item in entry.get("evidence") or []
                          if isinstance(item, dict) and item.get("type") not in (None, "unknown")]
                if not usable:
                    errors.append("GRILL_EVIDENCE: entry %s is verified_fact and needs at "
                                  "least one non-unknown evidence ref" % question_id)
            if basis in ("craft_default", "agent_proposal"):
                if not (entry.get("evidence") or entry.get("note")):
                    errors.append("GRILL_EVIDENCE: entry %s is %s and needs evidence or a note"
                                  % (question_id, basis))
            if question.get("authority") == "user_only" and basis != "user_explicit":
                errors.append("GRILL_AUTHORITY: entry %s is user-only (L7 paid ignition); "
                              "an Agent proposal cannot settle it" % question_id)
        else:
            if "answer" in entry:
                errors.append("GRILL_UNRESOLVED: entry %s is %r yet carries an answer; "
                              "an unsettled branch must not be filled in silently"
                              % (question_id, status))
            if not str(entry.get("reason") or "").strip():
                errors.append("GRILL_REASON: entry %s is %r and needs a reason"
                              % (question_id, status))
        errors.extend(_evidence_errors(entry, index))

    for question in QUESTION_BANK:
        entry = mapped.get(question["id"])
        if not entry or entry.get("status") != "resolved":
            continue
        if not _when_applies(question, ledger, mapped):
            errors.append("GRILL_NOT_APPLICABLE: entry %s answers a branch that does not "
                          "apply to this job" % question["id"])
    return errors


# ---------- frontier, gate, patch ----------

def frontier(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    entries = _entry_map(ledger)
    reachable = _reachable_stops(ledger)
    pending = []
    for question in QUESTION_BANK:
        entry = entries.get(question["id"])
        if entry is not None and entry.get("status") in SETTLED + ("deferred",):
            continue
        if not _in_scope(question, reachable):
            continue
        if not _when_applies(question, ledger, entries):
            continue
        if any(not _settled(entries.get(required)) for required in question["requires"]):
            continue
        pending.append(question)
    return pending


def _blocking_entries(ledger: dict[str, Any], stop: str) -> list[dict[str, Any]]:
    entries = _entry_map(ledger)
    reachable = _reachable_stops(ledger)
    open_ids = {question["id"] for question in frontier(ledger)}
    gaps = []
    for question in QUESTION_BANK:
        if stop not in question["blocking_for"]:
            continue
        if not _in_scope(question, reachable):
            continue
        if not _when_applies(question, ledger, entries):
            continue
        entry = entries.get(question["id"])
        if _settled(entry):
            continue
        if question["id"] in open_ids or (entry and entry.get("status") == "deferred"):
            gaps.append(question)
    return gaps


def _warning_entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Warnings are conscious deferrals only.

    An optional question nobody has asked yet is not a warning at a stop gate —
    the session's `unresolved` list carries it. A `deferred` entry is a decision
    the user already made; the receipt must keep it visible.
    """

    entries = _entry_map(ledger)
    reachable = _reachable_stops(ledger)
    warnings = []
    for question in QUESTION_BANK:
        if not set(question["stops"]) & reachable:
            continue
        if not _when_applies(question, ledger, entries):
            continue
        entry = entries.get(question["id"])
        if entry and entry.get("status") == "deferred":
            warnings.append(question)
    return warnings


def gate(ledger: dict[str, Any], stop: str) -> dict[str, Any]:
    if stop not in STOPS:
        raise GrillError("GRILL_USAGE: stop %r is not one of %s" % (stop, ", ".join(STOPS)))
    if is_contract(ledger):
        if ledger.get("status") == "blocked_conflict":
            conflicts = [conflict.get("code") for conflict in ledger.get("blocking_conflicts") or []]
            return {"status": "GRILL_CONFLICT", "stop": stop, "blocking": [],
                    "warnings": [], "errors": conflicts}
        ledger = ledger_from_contract(ledger)
    errors = validate_ledger(ledger)
    if errors:
        return {"status": "GRILL_INVALID", "stop": stop, "blocking": [], "warnings": [],
                "errors": errors}
    blocking = _blocking_entries(ledger, stop)
    warnings = _warning_entries(ledger)
    if blocking:
        status = "GRILL_BLOCKED"
    elif warnings:
        status = "GRILL_PASS_WITH_WARNINGS"
    else:
        status = "GRILL_PASS"
    return {"status": status, "stop": stop,
            "blocking": [question["id"] for question in blocking],
            "warnings": [question["id"] for question in warnings],
            "errors": []}


def decision_mismatches(grill: dict[str, Any], *, task_type: Any, duration_sec: Any,
                        aspect_ratio: Any, sound_mode: Any) -> list[str]:
    """Exact comparisons between a ledger and the artefact it is supposed to shape.

    A ledger that says 5 秒 while the intent says 15 秒 means the interview was
    theatre: the answers never reached the film. Style text may legitimately be
    elaborated, so it is not compared here.
    """

    entries = {entry.get("id"): entry for entry in grill.get("entries") or []
               if isinstance(entry, dict)}

    def resolved(question_id):
        entry = entries.get(question_id)
        return entry.get("answer") if entry and entry.get("status") == "resolved" else None

    problems: list[str] = []
    expected_task = resolved("G01")
    if expected_task is not None and expected_task != task_type:
        problems.append("G01 delivery_target=%r but artefact task_type=%r"
                        % (expected_task, task_type))
    expected_duration = resolved("G03")
    if expected_duration is not None and expected_duration != duration_sec:
        problems.append("G03 duration_sec=%r but artefact duration_sec=%r"
                        % (expected_duration, duration_sec))
    expected_ratio = resolved("G04")
    if expected_ratio is not None and expected_ratio != aspect_ratio:
        problems.append("G04 aspect_ratio=%r but artefact aspect_ratio=%r"
                        % (expected_ratio, aspect_ratio))
    expected_mode = resolved("G08")
    if expected_mode is not None and expected_mode != sound_mode:
        problems.append("G08 sound_mode=%r but artefact sound_mode=%r"
                        % (expected_mode, sound_mode))
    return problems


def is_contract(payload: Any) -> bool:
    return (isinstance(payload, dict)
            and payload.get("contract_format") == CONTRACT_FORMAT
            and "creative_intent" in payload
            and isinstance(payload.get("decisions"), list))


def ledger_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Project a Creative Intent Contract back onto the gate's ledger view.

    The contract is the published artefact; the ledger is how the existing
    compilers ask "did this stop's questions get answered?". Keeping one
    projection avoids a second source of truth.
    """

    try:
        from .grill_bank import QUESTION_BANK, cic_mappings
        from .grill_session import BASIS_BY_SOURCE, contract_question_provenance, GrillSessionError
    except ImportError:
        from grill_bank import QUESTION_BANK, cic_mappings
        from grill_session import BASIS_BY_SOURCE, contract_question_provenance, GrillSessionError
    by_path = {}
    for decision in contract.get("decisions") or []:
        if isinstance(decision, dict) and isinstance(decision.get("field_path"), str):
            by_path[decision["field_path"]] = decision

    entries = []
    for question in QUESTION_BANK:
        mappings = cic_mappings(question)
        if not mappings:
            continue
        found = [by_path.get(mapping["path"]) for mapping in mappings]
        if all(found):
            try:
                source, decision_status, locked = contract_question_provenance(question["id"], found)
            except GrillSessionError as exc:
                entries.append({"id": question["id"], "status": "open",
                                "reason": str(exc), "projection_error": str(exc)})
                continue
            if len(mappings) == 1:
                answer = found[0].get("value")
            else:
                answer = {mapping.get("pick", "value"): decision.get("value")
                          for mapping, decision in zip(mappings, found)}
            entries.append({
                "id": question["id"],
                "status": "resolved",
                "basis": BASIS_BY_SOURCE.get(source, "agent_proposal"),
                "answer": answer,
                "locked": locked,
                "note": "contract:%s/%s" % (source, decision_status),
                "evidence": [],
            })
        else:
            entries.append({"id": question["id"], "status": "open",
                            "reason": "contract did not settle this field"})
    kind = "reverse" if "creative_intent.reverse_contract" in by_path else "original"
    return {"grill_format": FORMAT,
            "job": {"kind": kind, "request": contract.get("original_request", "")},
            "entries": entries,
            "contract_ref": contract.get("contract_id")}


def as_ledger(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept either artefact and return the ledger view the gate/matcher speak."""

    return ledger_from_contract(payload) if is_contract(payload) else payload


def _decision_value(question: dict[str, Any], answer: Any) -> Any:
    if question["id"] == "G06":
        return {"text": answer["style_id"], "register": answer["register"]}
    return answer


def build_patch(ledger: dict[str, Any], stop: str) -> dict[str, Any]:
    entries = _entry_map(ledger)
    result = gate(ledger, stop)
    decisions: dict[str, Any] = {}
    sound = None
    task_type = None
    carry: list[dict[str, Any]] = []
    open_items: list[dict[str, Any]] = []

    for question in QUESTION_BANK:
        entry = entries.get(question["id"])
        if entry is None:
            continue
        if entry.get("status") != "resolved":
            open_items.append({"id": question["id"], "status": entry.get("status"),
                               "reason": entry.get("reason")})
            continue
        basis = entry["basis"]
        record = {"value": _decision_value(question, entry["answer"]),
                  "source": SOURCE_BY_BASIS[basis],
                  "locked": bool(entry.get("locked", False))}
        target = question.get("maps_to") or ()
        handled = False
        if "task_type" in target:
            task_type = entry["answer"]
            handled = True
        if "decisions.duration_sec" in target:
            decisions["duration_sec"] = record
            handled = True
        if "decisions.aspect_ratio" in target:
            decisions["aspect_ratio"] = record
            handled = True
        if "decisions.visual_style" in target:
            decisions["visual_style"] = record
            handled = True
        if "sound.mode" in target:
            sound = {"mode": entry["answer"],
                     "source": SOURCE_BY_BASIS[basis],
                     "locked": bool(entry.get("locked", False))}
            handled = True
        if not handled:
            carry.append({"id": question["id"], "branch": question["branch"],
                          "question": question["question"], "answer": entry["answer"],
                          "basis": basis, "locked": bool(entry.get("locked", False)),
                          "evidence": entry.get("evidence") or [],
                          "note": entry.get("note") or ""})

    return {
        "patch_format": PATCH_FORMAT,
        "task_type": task_type,
        "decisions": decisions,
        "sound": sound,
        "carry_forward": carry,
        "open_items": open_items,
        "gate": result,
        "authority": {
            "generation_authorized": False,
            "creative_quality": "NOT_VERIFIED",
            "note": "This patch fills task_type, material decisions and sound.mode only. "
                    "Everything else stays in carry_forward: constraints need real semantics "
                    "and the Agent must write them against the actual shots.",
        },
    }


# ---------- rendering ----------

def render_frontier(ledger: dict[str, Any], limit: int) -> str:
    pending = frontier(ledger)
    entries = _entry_map(ledger)
    settled = sum(1 for entry in entries.values() if _settled(entry))
    deferred = sum(1 for entry in entries.values() if entry.get("status") == "deferred")
    held = "，搁置 %d 题" % deferred if deferred else ""
    if not pending:
        return ("FRONTIER_EMPTY: 题库里没有可问的题了（已定 %d 题%s）。"
                " 下一步跑 --check 看当前终点的门禁回执。" % (settled, held))
    shown = pending if limit <= 0 else pending[:limit]
    lines = ["本轮 frontier %d 题（已定 %d / %d 题%s；%s）"
             % (len(shown), settled, len(QUESTION_BANK), held,
                "一次问完全部" if limit <= 0 else "本轮最多问 %d 题" % limit)]
    for position, question in enumerate(shown, start=1):
        lines.append("")
        lines.append("❓ Q%d · %s 「%s」" % (position, question["id"], question["title"]))
        lines.append("   %s" % question["question"])
        if question["kind"] == "choice":
            options = "；".join("%s（%s）" % (value, question["labels"][value])
                               for value in question["choices"])
            lines.append("   选项：%s" % options)
        elif question["kind"] == "object":
            for name, spec in question["fields"].items():
                if spec["type"] == "choice":
                    options = " / ".join("%s（%s）" % (value, spec["labels"][value])
                                         for value in spec["choices"])
                    lines.append("   字段 %s：%s" % (name, options))
                else:
                    lines.append("   字段 %s：%s" % (name, spec.get("hint", "文本")))
        elif question.get("examples"):
            lines.append("   例：%s" % question["examples"])
        lines.append("   ➡️ 推荐：%s" % question["recommendation"])
        lines.append("   📌 依据：%s" % question["why"])
        if question.get("maps_to"):
            lines.append("   🧩 记录到：%s" % "、".join(question["maps_to"]))
    hidden = len(pending) - len(shown)
    if hidden > 0:
        lines.append("")
        lines.append("（还有 %d 题在等前面的答案，下一轮再说——先问下游＝猜。）" % hidden)
    return "\n".join(lines)


def render_gate(result: dict[str, Any]) -> str:
    lines = ["%s（stop=%s）" % (result["status"], result["stop"])]
    titles = {question["id"]: question for question in QUESTION_BANK}
    for question_id in result["blocking"]:
        question = titles[question_id]
        lines.append("  [FAIL] %s %s：%s" % (question_id, question["title"], question["question"]))
    for question_id in result["warnings"]:
        question = titles[question_id]
        lines.append("  [WARN] %s %s 未定：%s" % (question_id, question["title"],
                                                 question["question"]))
    for message in result["errors"]:
        lines.append("  [FAIL] %s" % message)
    if result["status"] == "GRILL_PASS":
        lines.append("  门禁只说明该问的都答了：不证明原文已读，不证明创作对，也不批准点火。")
    return "\n".join(lines)


# ---------- self-test ----------

def _mini_ledger(entries: list[dict[str, Any]], kind: str = "original") -> dict[str, Any]:
    return {"grill_format": FORMAT, "job": {"kind": kind}, "entries": entries}


def self_test() -> int:
    passed = 0
    failed = 0
    lines: list[str] = []

    def check(name: str, condition: bool) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            lines.append("  PASS %s" % name)
        else:
            failed += 1
            lines.append("  FAIL %s" % name)

    empty = _mini_ledger([])
    check("empty ledger: root question only",
          [question["id"] for question in frontier(empty)] == ["G01"])
    check("empty ledger: gate blocked at root",
          gate(empty, "prompt")["status"] == "GRILL_BLOCKED")

    shaped = _mini_ledger([{"id": "G01", "status": "resolved", "basis": "user_explicit",
                            "answer": "prompt_only", "locked": True}])
    ids = [question["id"] for question in frontier(shaped)]
    check("delivery set: duration open", "G03" in ids)
    check("dependency order: shot band waits for duration", "G05" not in ids)
    check("prompt_only: asset branch does not apply", "G12" not in ids)

    check("user_explicit must be locked",
          any("must be locked" in error for error in validate_ledger(
              _mini_ledger([{"id": "G01", "status": "resolved", "basis": "user_explicit",
                             "answer": "prompt_only", "locked": False}]))))
    check("agent proposal cannot be locked",
          any("cannot be locked" in error for error in validate_ledger(
              _mini_ledger([{"id": "G01", "status": "resolved", "basis": "agent_proposal",
                             "answer": "prompt_only", "locked": True, "note": "x"}]))))
    check("verified fact needs evidence",
          any("verified_fact" in error for error in validate_ledger(
              _mini_ledger([{"id": "G03", "status": "resolved", "basis": "verified_fact",
                             "answer": 15, "locked": False}]))))
    check("evidence ref must exist",
          any("does not exist" in error for error in validate_ledger(
              _mini_ledger([{"id": "G03", "status": "resolved", "basis": "verified_fact",
                             "answer": 15, "locked": False,
                             "evidence": [{"type": "platform",
                                           "ref": "references/no-such-book.md"}]}]))))
    check("ignition needs the user, not the Agent",
          any("user-only" in error for error in validate_ledger(
              _mini_ledger([{"id": "G16", "status": "resolved", "basis": "agent_proposal",
                             "answer": "批准", "locked": False, "note": "assumed"}]))))
    check("unknown question is refused",
          any("GRILL_UNKNOWN_QUESTION" in error for error in validate_ledger(
              _mini_ledger([{"id": "G99", "status": "resolved", "basis": "user_explicit",
                             "answer": "x", "locked": True}]))))
    check("unsettled branch must not carry an answer",
          any("GRILL_UNRESOLVED" in error for error in validate_ledger(
              _mini_ledger([{"id": "G03", "status": "open", "answer": 15, "reason": "?"}]))))

    full = _mini_ledger([
        {"id": "G01", "status": "resolved", "basis": "user_explicit",
         "answer": "prompt_only", "locked": True},
        {"id": "G03", "status": "resolved", "basis": "user_explicit",
         "answer": 15, "locked": True},
        {"id": "G04", "status": "resolved", "basis": "user_explicit",
         "answer": "9:16", "locked": True},
        {"id": "G06", "status": "resolved", "basis": "user_explicit",
         "answer": {"style_id": "剪纸", "register": "stylized"}, "locked": True},
        {"id": "G08", "status": "resolved", "basis": "user_explicit",
         "answer": "ambience_only", "locked": True},
        {"id": "G10", "status": "resolved", "basis": "agent_proposal",
         "answer": "空镜不承担叙事落点", "locked": False, "note": "用户只给了画面"},
    ])
    result = gate(full, "prompt")
    check("prompt stop passes once the blocking set is answered", result["status"] == "GRILL_PASS")
    deferred = _mini_ledger([dict(entry) for entry in full["entries"]]
                            + [{"id": "G02", "status": "deferred", "reason": "用户没提范围外"}])
    deferred_result = gate(deferred, "prompt")
    check("a conscious deferral stays visible as a warning",
          deferred_result["status"] == "GRILL_PASS_WITH_WARNINGS"
          and deferred_result["warnings"] == ["G02"])
    patch = build_patch(full, "prompt")
    check("patch keeps the material decisions",
          patch["decisions"]["duration_sec"] == {"value": 15, "source": "user_explicit",
                                                 "locked": True})
    check("patch never claims generation authority",
          patch["authority"]["generation_authorized"] is False
          and build_patch(full, "prompt") == patch)

    reverse = _mini_ledger([{"id": "G01", "status": "resolved", "basis": "user_explicit",
                             "answer": "prompt_only", "locked": True}], kind="reverse")
    check("reverse job puts the contract on the frontier",
          "G17" in [question["id"] for question in frontier(reverse)])
    check("reverse job cannot pass without the contract",
          "G17" in gate(reverse, "prompt")["blocking"])

    print("\n".join(lines))
    print("\n%d passed / %d failed" % (passed, failed))
    return RC_OK if failed == 0 else RC_FAIL


# ---------- CLI ----------

def _print(errors: list[str]) -> None:
    for message in errors:
        print("FAIL %s" % message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-flight interrogation ledger (grill-ledger/v1); never grants generation")
    parser.add_argument("--ledger", help="path to the grill ledger JSON")
    parser.add_argument("--frontier", action="store_true",
                        help="print the questions that may be asked now")
    parser.add_argument("--check", action="store_true", help="run the stop gate")
    parser.add_argument("--patch", help="write a grill-intent-patch/v1 file")
    parser.add_argument("--stop", choices=STOPS, help="gate stop (default: derived from task_type)")
    parser.add_argument("--limit", type=int, default=1,
                        help="questions per round (default 1, per the spec; 0 = whole frontier)")
    parser.add_argument("--bank", action="store_true", help="dump the question bank")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.bank:
        print(json.dumps({"bank_format": "grill-bank/v1", "questions": list(QUESTION_BANK)},
                         ensure_ascii=False, indent=2))
        return RC_OK
    if not args.ledger:
        parser.print_usage(sys.stderr)
        sys.stderr.write("grill_ledger: --ledger is required (or --self-test / --bank)\n")
        return RC_USAGE

    try:
        ledger = load_ledger(args.ledger)
    except GrillError as exc:
        sys.stderr.write("%s\n" % exc)
        return RC_FAIL

    errors = validate_ledger(ledger)
    if errors:
        if args.json:
            print(json.dumps({"status": "GRILL_INVALID", "errors": errors}, ensure_ascii=False,
                             indent=2))
        else:
            _print(errors)
            print("GRILL_INVALID：台账不可信，先修台账再谈回答。")
        return RC_FAIL

    if args.frontier:
        if args.json:
            print(json.dumps({"status": "FRONTIER", "limit": args.limit,
                              "questions": frontier(ledger)}, ensure_ascii=False, indent=2))
        else:
            print(render_frontier(ledger, args.limit))
        return RC_OK

    entries = _entry_map(ledger)
    task_type = None
    root = entries.get("G01")
    if root and root.get("status") == "resolved":
        task_type = root.get("answer")
    stop = args.stop
    if stop is None:
        stop = STOPS_BY_TASK.get(task_type, "prompt")
    else:
        if stop == "film" and task_type and task_type != "full_film":
            sys.stderr.write("GRILL_USAGE: stop 'film' needs delivery_target full_film, "
                             "not %r\n" % (task_type,))
            return RC_USAGE
        if stop == "generation" and task_type == "prompt_only":
            sys.stderr.write("GRILL_USAGE: prompt_only does not generate media; "
                             "use --stop prompt\n")
            return RC_USAGE

    result = gate(ledger, stop)
    patch = build_patch(ledger, stop)
    if args.patch:
        patch_path = Path(args.patch)
        # 把 --patch 指到输入台账上会直接覆盖输入（2026-11-12 审计指出）。
        if args.ledger and grill_session_same_file(patch_path, Path(args.ledger)):
            sys.stderr.write("GRILL_USAGE: --patch 不能与 --ledger 指向同一文件\n")
            return RC_USAGE
        patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    if args.json:
        print(json.dumps({"gate": result, "frontier": [q["id"] for q in frontier(ledger)]},
                         ensure_ascii=False, indent=2))
    else:
        print(render_gate(result))
        if args.patch:
            print("patch → %s（只含脚本能机械映射的字段；其余在 carry_forward）" % args.patch)
    if result["status"] == "GRILL_PASS":
        return RC_OK
    if result["status"] == "GRILL_PASS_WITH_WARNINGS":
        return RC_WARN
    return RC_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
