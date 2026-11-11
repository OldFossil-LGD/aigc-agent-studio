"""Creative Intent GrillMe — session engine, question selection and contract compiler.

Implements the interaction layer from the spec:

* a persisted session state machine (`RECEIVED → PARSING → NEEDS_QUESTION ↔
  ANSWERING → COMPILING → READY_FOR_PLANNING`, plus `BLOCKED_CONFLICT`,
  `VALIDATION_FAILED`, `CANCELLED`);
* **one main question per round**, chosen from `grill_bank` by the relative
  priority score (spec §4.3) — never a fixed questionnaire;
* L0/L1/L2 interaction depths, skips that become traceable presets, explicit
  revisions that never overwrite history;
* a **Creative Intent Contract** (`creative-intent-contract/v1`) with
  field-level provenance, unresolved items and blocking conflicts, validated
  against `schemas/creative_intent_contract.schema.json`;
* a ledger view so the existing compilers' station-0 gate keeps working.

Rejected on purpose: asking for facts the library can answer, asking several
questions in one round, and inventing a value where the only honest answer is
`null`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from ._common import RC_FAIL, RC_OK, RC_USAGE, RC_WARN
    from .grill_bank import (MODES, QUESTION_BANK, QUESTION_INDEX, STOPS,
                             STOPS_BY_TASK, answer_errors, cic_mappings,
                             priority_score)
except ImportError:
    from _common import RC_FAIL, RC_OK, RC_USAGE, RC_WARN
    from grill_bank import (MODES, QUESTION_BANK, QUESTION_INDEX, STOPS,
                            STOPS_BY_TASK, answer_errors, cic_mappings,
                            priority_score)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "creative_intent_contract.schema.json"

SESSION_FORMAT = "grill-session/v1"
CONTRACT_FORMAT = "creative-intent-contract/v1"
SCHEMA_VERSION = "1.0.0"

STATES = ("RECEIVED", "PARSING", "NEEDS_QUESTION", "ANSWERING", "COMPILING",
          "READY_FOR_PLANNING", "BLOCKED_CONFLICT", "VALIDATION_FAILED", "CANCELLED")

# spec §6
SOURCE_TYPES = ("user_original", "grillme_answer", "project_preset",
                "agent_proposed", "inherited_project")
DECISION_STATUSES = ("confirmed", "proposed", "defaulted", "unresolved", "conflicted")
SETTLED_STATUSES = ("resolved", "out_of_scope", "not_applicable")

# source_type -> grill-ledger basis (the gate's vocabulary)
BASIS_BY_SOURCE = {
    "user_original": "user_explicit",
    "grillme_answer": "user_explicit",
    "project_preset": "craft_default",
    "agent_proposed": "agent_proposal",
    # An inherited contract value was frozen by an upstream user decision;
    # pretending it is merely a craft default would let a downstream default
    # silently overwrite it.
    "inherited_project": "user_explicit",
}

BLOCK_SHAPES: dict[str, dict[str, Any]] = {
    "creative_intent": {
        "deliverable": None, "content_type": None, "genre": [],
        "emotional_target": None, "theme": None, "core_conflict": None,
        "narrative_preference": None, "ending_tone": None,
        "visual_style": None, "visual_register": None,
        "character_invariants": [], "cast_relations": [], "relationship_axis": None,
        "clue_policy": None, "horror_source": None, "intent_fork": None,
        "reverse_contract": None,
    },
    "production_constraints": {
        "duration_seconds": None, "aspect_ratio": None, "target_platform": None,
        "spoken_language": None, "audio_policy": "unspecified", "music_policy": None,
        "shot_count": None, "consistency_chain": None, "channel": None,
    },
    "creative_authority": {
        "mode": "auto_with_escalation", "allow_agent_defaults": True,
        "confirmation_required_for": ["user_locked_conflicts", "material_scope_change"],
        "budget_ceiling": None, "ignition_approval": None,
    },
    "creative_constraints": {
        "must_have": [], "must_never": [], "scope_out": [],
        "consistency_anchors": [], "dialogue_rules": [], "acceptance": [],
        "asset_scope": [], "rights_status": None,
    },
}

SOUND_TOKENS = ("雨声", "水声", "环境声", "配乐", "音乐", "对白", "旁白", "人声", "风声", "现场音")
PEOPLE_TOKENS = ("不出现人物", "禁止人物", "不出现人", "禁止人", "画面无人", "无人", "不出现人脸", "禁止人脸")


class GrillSessionError(ValueError):
    """Raised when a session operation cannot be honoured."""

    def __init__(self, code: str, message: str):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


# ---------- session lifecycle ----------

ALLOWED_MODES = ("auto", "L0", "L1", "L2")


def resolve_mode(session: dict[str, Any], required_count: int) -> str:
    """`auto` means: a complete brief is L0 (0 questions), otherwise L1."""

    mode = session.get("mode") or "auto"
    if mode == "auto":
        return "L0" if required_count == 0 else "L1"
    return mode


def new_session(request: str, *, mode: str = "auto", kind: str = "original",
                project_id: str = "PROJ_LOCAL") -> dict[str, Any]:
    if not request.strip():
        raise GrillSessionError("GRILL_EMPTY_REQUEST", "original request must not be empty")
    if mode not in ALLOWED_MODES:
        raise GrillSessionError("GRILL_MODE", "mode must be one of %s" % ", ".join(ALLOWED_MODES))
    if kind not in ("original", "reverse"):
        raise GrillSessionError("GRILL_JOB_KIND", "job kind must be original or reverse")
    digest = hashlib.sha1(("%s|%s|%s" % (request.strip(), mode, kind)).encode("utf-8")).hexdigest()
    return {
        "session_format": SESSION_FORMAT,
        "session_id": "GS_" + digest[:10],
        "project_id": project_id,
        "state": "RECEIVED",
        "mode": mode,
        "job": {"kind": kind, "original_request": request.strip()},
        "revision": 1,
        "entries": {},
        "turns": [],
        "history": [],
        "applied_keys": {},
        "asked": [],
        "last_question": None,
    }


def load_session(path: str | Path) -> dict[str, Any]:
    try:
        session = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise GrillSessionError("GRILL_UNREADABLE", str(exc))
    except ValueError as exc:
        raise GrillSessionError("GRILL_UNREADABLE", "not JSON: %s" % exc)
    if not isinstance(session, dict) or session.get("session_format") != SESSION_FORMAT:
        raise GrillSessionError("GRILL_SESSION_FORMAT",
                                "expected %r" % SESSION_FORMAT)
    session.setdefault("entries", {})
    session.setdefault("turns", [])
    session.setdefault("history", [])
    session.setdefault("applied_keys", {})
    session.setdefault("asked", [])
    return session


def same_file(left, right) -> bool:
    """同一文件的判定要看 inode，不能只比路径。

    resolve() 能拆符号链接，但拆不了硬链接：同一份内容挂在两个名字下时，
    按路径比较会放行，随后 write_text 会截断并覆盖受保护的文件（2026-11-12 审计指出）。
    """
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


def resolve_contract_target(contract_path: Path, contract: dict[str, Any]) -> tuple[Path, str | None]:
    """已发布的合同修订不可覆盖；返回 (落盘路径, 冲突说明)。

    原先只在不相等时换名，换名后的目标存在与否没检查；同修订号但正文不同也会直接覆盖。
    """
    if not contract_path.is_file():
        return contract_path, None
    try:
        existing = json.loads(contract_path.read_text(encoding="utf-8"))
    except ValueError:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    if existing.get("revision") == contract.get("revision"):
        if existing == contract:
            return contract_path, None
        return contract_path, ("同一修订号 %s 已有不同内容；拒绝覆盖已发布修订"
                               % contract.get("revision"))
    candidate = contract_path.with_name("%s.r%s%s" % (contract_path.stem,
                                                      contract.get("revision"),
                                                      contract_path.suffix))
    if candidate.is_file():
        return candidate, "改写目标 %s 已存在；拒绝覆盖" % candidate
    return candidate, None


def save_session(path: str | Path, session: dict[str, Any]) -> None:
    """原子写：先写同目录临时文件再替换。

    直接 write_text 覆盖时，写入中断会留下空文件或半截 JSON（2026-11-12 审计指出）。
    """
    target = Path(path)
    text = json.dumps(session, ensure_ascii=False, indent=2) + "\n"
    # 临时名不可预测：固定 "<session>.tmp" 会被 --contract/--ledger 撞上并被覆盖
    # （2026-11-12 审计指出）。mkstemp 在同一目录建唯一文件，替换仍是原子的。
    handle, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp",
                                        dir=str(target.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _entry(question: dict[str, Any], value: Any, source_type: str,
           decision_status: str, *, locked: bool, source_ref: str = "",
           note: str = "", evidence: list | None = None) -> dict[str, Any]:
    return {
        "id": question["id"],
        "status": "resolved",
        "answer": value,
        "source_type": source_type,
        "source_ref": source_ref,
        "decision_status": decision_status,
        "locked": locked,
        "note": note,
        "evidence": evidence or [],
        "confidence": None,
    }


def _settled(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and entry.get("status") in SETTLED_STATUSES


def _when_applies(question: dict[str, Any], session: dict[str, Any]) -> bool:
    when = question.get("when") or {}
    if "job_kind" in when:
        return (session.get("job") or {}).get("kind") in when["job_kind"]
    if "question" in when:
        dependency = session["entries"].get(when["question"])
        if not dependency or dependency.get("status") != "resolved":
            return False
        answer = dependency.get("answer")
        if isinstance(answer, list):
            return any(item in when["values"] for item in answer)
        return answer in when["values"]
    return True


def _reachable_stops(session: dict[str, Any]) -> frozenset[str]:
    root = session["entries"].get("G01")
    task_type = root.get("answer") if root and root.get("status") == "resolved" else None
    if task_type == "prompt_only":
        return frozenset(("prompt",))
    if task_type == "single_shot":
        return frozenset(("prompt", "generation"))
    return frozenset(STOPS)


def stop_for(session: dict[str, Any]) -> str:
    root = session["entries"].get("G01")
    task_type = root.get("answer") if root and root.get("status") == "resolved" else None
    return STOPS_BY_TASK.get(task_type, "prompt")


def content_type_of(session: dict[str, Any]) -> str | None:
    entry = session["entries"].get("I01")
    if entry and entry.get("status") == "resolved":
        return entry.get("answer")
    return None


def frontier(session: dict[str, Any]) -> list[dict[str, Any]]:
    entries = session["entries"]
    reachable = _reachable_stops(session)
    pending = []
    for question in QUESTION_BANK:
        entry = entries.get(question["id"])
        if entry is not None and entry.get("status") in SETTLED_STATUSES + ("deferred",):
            continue
        if not set(question["stops"]) & reachable:
            continue
        if not _when_applies(question, session):
            continue
        if any(not _settled(entries.get(required)) for required in question["requires"]):
            continue
        pending.append(question)
    return pending


def _asked_optional(session: dict[str, Any], stop: str) -> int:
    count = 0
    for turn in session["turns"]:
        question = QUESTION_INDEX.get(turn.get("id"))
        if not question:
            continue
        if stop in question["blocking_for"]:
            continue
        if turn.get("action") in ("answer", "skip"):
            count += 1
    return count


def select(session: dict[str, Any]) -> dict[str, Any]:
    """Return the single highest-value question, or a stop verdict (spec §4.3–4.4)."""

    stop = stop_for(session)
    pending = frontier(session)
    content_type = content_type_of(session)

    def score(question):
        return priority_score(question, content_type)

    required = [question for question in pending if stop in question["blocking_for"]]
    mode_name = resolve_mode(session, len(required))
    mode = MODES[mode_name]
    if required:
        best = max(required, key=score)
        return {"status": "QUESTION", "reason": "blocking", "stop": stop,
                "score": score(best), "question": best,
                "mode": session.get("mode"), "mode_effective": mode_name}
    if not pending:
        return {"status": "FRONTIER_EMPTY", "reason": "all in-scope questions settled",
                "stop": stop, "mode": session.get("mode"), "mode_effective": mode_name}
    best = max(pending, key=score)
    asked = _asked_optional(session, stop)
    if score(best) >= mode["threshold"] and asked < mode["optional_budget"]:
        return {"status": "QUESTION", "reason": "priority", "stop": stop,
                "score": score(best), "question": best,
                "mode": session.get("mode"), "mode_effective": mode_name}
    return {"status": "READY_TO_FINISH", "reason":
            "top remaining score %s < threshold %s and no blocking gap"
            % (score(best), mode["threshold"]),
            "stop": stop, "top": best["id"], "score": score(best),
            "mode": session.get("mode"), "mode_effective": mode_name}


def _touch(session: dict[str, Any], state: str) -> None:
    session["state"] = state


def _bump_revision(session: dict[str, Any], qid: str, previous: Any, value: Any,
                   action: str) -> None:
    session["revision"] = int(session.get("revision", 1)) + 1
    session["history"].append({"revision": session["revision"], "id": qid,
                               "previous": previous, "value": value, "action": action})


def _guard(session: dict[str, Any], key: str | None, revision: int | None) -> bool:
    """Return False when the idempotency key was already applied (a retry, not a new answer)."""

    if revision is not None and int(revision) != int(session.get("revision", 1)):
        raise GrillSessionError("GRILL_STALE_SESSION",
                                "revision %s is stale (current %s)"
                                % (revision, session.get("revision", 1)))
    if key and key in session["applied_keys"]:
        return False
    return True


def inherit_contract(session: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    """Seed a session from a published contract (rework / continuation).

    Inherited values stay `inherited_project`: still a user constraint, but the
    provenance points upstream instead of pretending the user just said it.
    """

    by_path = {decision["field_path"]: decision
               for decision in contract.get("decisions") or []
               if isinstance(decision, dict) and isinstance(decision.get("field_path"), str)}
    inherited = []
    for question in QUESTION_BANK:
        mappings = cic_mappings(question)
        if not mappings or not all(mapping["path"] in by_path for mapping in mappings):
            continue
        if len(mappings) == 1:
            value = by_path[mappings[0]["path"]].get("value")
        else:
            value = {mapping.get("pick", "value"): by_path[mapping["path"]].get("value")
                     for mapping in mappings}
        errors = answer_errors(question, value)
        if errors:
            continue
        first = by_path[mappings[0]["path"]]
        session["entries"][question["id"]] = _entry(
            question, value, "inherited_project", "confirmed",
            locked=bool(first.get("locked")),
            source_ref="contract:%s" % contract.get("contract_id", ""),
            note="继承自已发布契约")
        inherited.append(question["id"])
    if inherited:
        session["turns"].append({"turn": 1, "id": "*", "action": "inherit",
                                 "value": inherited})
        _touch(session, "NEEDS_QUESTION")
    return inherited


def record_facts(session: dict[str, Any], values: dict[str, Any],
                 source_ref: str = "original_request") -> list[str]:
    """Write what the user's own words already settled (never asks these again)."""

    changed = []
    for index, (qid, value) in enumerate(values.items(), start=1):
        question = QUESTION_INDEX.get(qid)
        if question is None:
            raise GrillSessionError("GRILL_UNKNOWN_QUESTION", qid)
        errors = answer_errors(question, value)
        if errors:
            raise GrillSessionError("GRILL_INVALID_ANSWER", "%s: %s" % (qid, "; ".join(errors)))
        session["entries"][qid] = _entry(
            question, value, "user_original", "confirmed", locked=True,
            source_ref="%s:span_%d" % (source_ref, index),
            note="用户原话")
        changed.append(qid)
    _touch(session, "NEEDS_QUESTION")
    return changed


def answer(session: dict[str, Any], qid: str, value: Any, *, note: str = "",
           key: str | None = None, revision: int | None = None) -> dict[str, Any]:
    if not _guard(session, key, revision):
        return {"status": "DUPLICATE", "id": qid, "revision": session["revision"]}
    question = QUESTION_INDEX.get(qid)
    if question is None:
        raise GrillSessionError("GRILL_UNKNOWN_QUESTION", qid)
    errors = answer_errors(question, value)
    if errors:
        raise GrillSessionError("GRILL_INVALID_ANSWER", "%s: %s" % (qid, "; ".join(errors)))
    previous = session["entries"].get(qid)
    if previous and previous.get("status") == "resolved" and previous.get("answer") != value:
        _bump_revision(session, qid, previous.get("answer"), value, "revise")
        action = "revise"
    else:
        action = "answer"
    session["entries"][qid] = _entry(question, value, "grillme_answer", "confirmed",
                                     locked=True, source_ref="turn_%03d" % (len(session["turns"]) + 1),
                                     note=note)
    session["turns"].append({"turn": len(session["turns"]) + 1, "id": qid,
                             "action": action, "value": value})
    if key:
        session["applied_keys"][key] = session["revision"]
    session["asked"] = list(dict.fromkeys(session.get("asked", []) + [qid]))
    session["last_question"] = qid
    _touch(session, "ANSWERING")
    return {"status": "ANSWERED", "id": qid, "action": action,
            "revision": session["revision"]}


def skip(session: dict[str, Any], qid: str, value: Any = None, *, note: str = "",
         key: str | None = None) -> dict[str, Any]:
    if not _guard(session, key, None):
        return {"status": "DUPLICATE", "id": qid, "revision": session["revision"]}
    question = QUESTION_INDEX.get(qid)
    if question is None:
        raise GrillSessionError("GRILL_UNKNOWN_QUESTION", qid)
    if question.get("authority") == "user_only":
        raise GrillSessionError("GRILL_USER_ONLY",
                                "%s is a paid-ignition decision; only the user may settle it" % qid)
    if value is None:
        if "default" not in question:
            raise GrillSessionError("GRILL_NO_SAFE_DEFAULT",
                                    "%s has no safe default; pass --value to propose one" % qid)
        value = question["default"]
        source, status = "project_preset", "defaulted"
        note = note or "用户交由库内预设"
    else:
        source, status = "agent_proposed", "proposed"
        note = note or "用户交由 AI 决定"
    errors = answer_errors(question, value)
    if errors:
        raise GrillSessionError("GRILL_INVALID_ANSWER", "%s: %s" % (qid, "; ".join(errors)))
    session["entries"][qid] = _entry(question, value, source, status, locked=False,
                                     source_ref="preset:%s@bank-v2" % qid if source == "project_preset"
                                     else "agent_%s" % qid,
                                     note=note)
    session["turns"].append({"turn": len(session["turns"]) + 1, "id": qid,
                             "action": "skip", "value": value})
    if key:
        session["applied_keys"][key] = session["revision"]
    session["asked"] = list(dict.fromkeys(session.get("asked", []) + [qid]))
    session["last_question"] = qid
    _touch(session, "ANSWERING")
    return {"status": "DEFAULTED", "id": qid, "source_type": source,
            "decision_status": status, "value": value}


def default_rest(session: dict[str, Any]) -> list[str]:
    """Fill every untouched question that has a safe library preset."""

    filled = []
    for question in QUESTION_BANK:
        qid = question["id"]
        if qid in session["entries"]:
            continue
        if "default" not in question or question.get("authority") == "user_only":
            continue
        if not set(question["stops"]) & _reachable_stops(session):
            continue
        if not _when_applies(question, session):
            continue
        session["entries"][qid] = _entry(question, question["default"], "project_preset",
                                         "defaulted", locked=False,
                                         source_ref="preset:%s@bank-v2" % qid,
                                         note="批量默认（用户选择直接开始）")
        filled.append(qid)
    if filled:
        session["turns"].append({"turn": len(session["turns"]) + 1, "id": "*",
                                 "action": "default_rest", "value": filled})
        _touch(session, "NEEDS_QUESTION")
    return filled


def defer(session: dict[str, Any], qid: str, reason: str) -> dict[str, Any]:
    question = QUESTION_INDEX.get(qid)
    if question is None:
        raise GrillSessionError("GRILL_UNKNOWN_QUESTION", qid)
    if not reason.strip():
        raise GrillSessionError("GRILL_REASON", "defer needs a reason")
    session["entries"][qid] = {"id": qid, "status": "deferred", "reason": reason,
                               "source_type": None, "decision_status": "unresolved",
                               "locked": False, "note": reason, "evidence": [],
                               "confidence": None}
    session["turns"].append({"turn": len(session["turns"]) + 1, "id": qid,
                             "action": "defer", "value": reason})
    session["last_question"] = qid
    return {"status": "DEFERRED", "id": qid}


def revise(session: dict[str, Any], qid: str, value: Any, *, note: str = "") -> dict[str, Any]:
    question = QUESTION_INDEX.get(qid)
    if question is None:
        raise GrillSessionError("GRILL_UNKNOWN_QUESTION", qid)
    previous = session["entries"].get(qid)
    if not previous or previous.get("status") != "resolved":
        raise GrillSessionError("GRILL_NOT_ANSWERED", "%s has no earlier answer to revise" % qid)
    errors = answer_errors(question, value)
    if errors:
        raise GrillSessionError("GRILL_INVALID_ANSWER", "%s: %s" % (qid, "; ".join(errors)))
    _bump_revision(session, qid, previous.get("answer"), value, "revise")
    session["entries"][qid] = _entry(question, value, "grillme_answer", "confirmed",
                                     locked=True,
                                     source_ref="turn_%03d" % (len(session["turns"]) + 1),
                                     note=note or "用户修改了自己的回答")
    session["turns"].append({"turn": len(session["turns"]) + 1, "id": qid,
                             "action": "revise", "value": value})
    return {"status": "REVISED", "id": qid, "revision": session["revision"]}


# ---------- contract ----------

def _pick(value: Any, mapping: dict[str, str]) -> Any:
    key = mapping.get("pick")
    if key is None:
        return value
    if isinstance(value, dict):
        return value.get(key)
    return None


def _set_path(contract: dict[str, Any], path: str, value: Any) -> None:
    block, _, field = path.partition(".")
    if not _:
        contract[path] = value
        return
    contract.setdefault(block, {})
    contract[block][field] = value


def _normalise(token: str) -> str:
    return str(token).strip().lower()


def detect_conflicts(contract: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = {decision["field_path"]: decision for decision in contract.get("decisions", [])}

    def value(path, default=None):
        decision = decisions.get(path)
        return decision.get("value") if decision else default

    must_have = [str(item) for item in (value("creative_constraints.must_have") or [])]
    must_never = [str(item) for item in (value("creative_constraints.must_never") or [])]
    audio = value("production_constraints.audio_policy")
    music = value("production_constraints.music_policy")
    invariants = value("creative_intent.character_invariants") or []
    authority = contract.get("creative_authority") or {}

    conflicts: list[dict[str, Any]] = []

    def add(code: str, fields: list[str], message: str) -> None:
        conflicts.append({"code": code, "fields": fields, "message": message,
                          "severity": "blocking"})

    overlap = sorted({_normalise(item) for item in must_have}
                     & {_normalise(item) for item in must_never})
    if overlap:
        add("CONFLICT_REQUIRED_AND_FORBIDDEN",
            ["creative_constraints.must_have", "creative_constraints.must_never"],
            "同一项同时进了「必须有」与「绝对不能有」：%s" % "、".join(overlap))

    if audio == "silent":
        wanted = [item for item in must_have
                  if any(token in item for token in SOUND_TOKENS)]
        if wanted:
            add("CONFLICT_SILENT_REQUIRES_SOUND",
                ["production_constraints.audio_policy", "creative_constraints.must_have"],
                "声音政策是无声，但必有项里要求了声音：%s" % "、".join(wanted))

    if audio == "dialogue_allowed":
        banned = [item for item in must_never if any(token in item for token in ("对白", "人声", "台词"))]
        if banned:
            add("CONFLICT_DIALOGUE_FORBIDDEN",
                ["production_constraints.audio_policy", "creative_constraints.must_never"],
                "声音政策允许对白，禁有项却禁止人声：%s" % "、".join(banned))

    if music in ("score", "source_music"):
        banned = [item for item in must_never if any(token in item for token in ("配乐", "音乐"))]
        if banned:
            add("CONFLICT_MUSIC_FORBIDDEN",
                ["production_constraints.music_policy", "creative_constraints.must_never"],
                "配乐政策要求有音乐，禁有项却禁止：%s" % "、".join(banned))

    if any(token in item for item in must_never for token in PEOPLE_TOKENS) and invariants:
        add("CONFLICT_PEOPLE_AND_INVARIANTS",
            ["creative_constraints.must_never", "creative_intent.character_invariants"],
            "禁有项要求不出现人物，却又给出了人物不可变特征")

    if authority.get("allow_agent_defaults") is False:
        defaulted = [decision["field_path"] for decision in contract.get("decisions", [])
                     if decision.get("decision_status") in ("defaulted", "proposed")]
        if defaulted:
            add("CONFLICT_DEFAULT_FORBIDDEN",
                ["creative_authority.allow_agent_defaults"] + defaulted,
                "用户选择每步确认，但仍有 %d 项走了默认或 AI 提议" % len(defaulted))

    return conflicts


def compile_contract(session: dict[str, Any], *, contract_id: str | None = None) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_format": CONTRACT_FORMAT,
        "contract_id": contract_id or ("CIC_" + session["session_id"][3:]),
        "project_id": session.get("project_id", "PROJ_LOCAL"),
        "original_request": (session.get("job") or {}).get("original_request", ""),
        "creative_intent": {},
        "production_constraints": {},
        "creative_authority": {},
        "creative_constraints": {},
        "decisions": [],
        "unresolved": [],
        "blocking_conflicts": [],
        "status": "needs_question",
        "revision": int(session.get("revision", 1)),
        "revision_history": [],
        "authorization": {
            "generation_authorized": False,
            "note": "GrillMe 只产创作意图契约；付费点火另需用户显式批准（L7）。",
        },
        "grill_policy": {
            "mode": resolve_mode(session, len([question for question in frontier(session)
                                               if stop_for(session) in question["blocking_for"]])),
            "threshold": MODES[resolve_mode(session, len([question for question in frontier(session)
                                                          if stop_for(session) in question["blocking_for"]]))]["threshold"],
            "questions_asked": len([turn for turn in session["turns"]
                                    if turn.get("action") in ("answer", "skip")]),
        },
    }

    for block, shape in BLOCK_SHAPES.items():
        contract[block] = {key: (list(value) if isinstance(value, list) else value)
                           for key, value in shape.items()}

    entries = session["entries"]
    decisions: list[dict[str, Any]] = []
    unresolved: list[str] = []
    stop = stop_for(session)
    reachable = _reachable_stops(session)

    for question in QUESTION_BANK:
        entry = entries.get(question["id"])
        mappings = cic_mappings(question)
        if not mappings:
            continue
        applies = (set(question["stops"]) & reachable) and _when_applies(question, session)
        if not applies:
            continue
        if entry and entry.get("status") == "resolved":
            for mapping in mappings:
                value = _pick(entry.get("answer"), mapping)
                if value is None:
                    continue
                _set_path(contract, mapping["path"], value)
                decisions.append({
                    "field_path": mapping["path"],
                    "value": value,
                    "source_type": entry.get("source_type"),
                    "source_ref": entry.get("source_ref") or "",
                    "locked": bool(entry.get("locked")),
                    "confidence": entry.get("confidence"),
                    "decision_status": entry.get("decision_status") or
                                       ("confirmed" if entry.get("source_type") in
                                        ("user_original", "grillme_answer", "inherited_project")
                                        else "defaulted"),
                })
        else:
            for mapping in mappings:
                unresolved.append(mapping["path"])

    mode = (entries.get("I14") or {}).get("answer") if entries.get("I14") else None
    if mode:
        contract["creative_authority"]["mode"] = mode
        contract["creative_authority"]["allow_agent_defaults"] = mode != "confirm_each_node"

    contract["decisions"] = decisions
    contract["unresolved"] = sorted(set(unresolved))
    contract["blocking_conflicts"] = detect_conflicts(contract)
    contract["revision_history"] = list(session.get("history") or [])

    blocking_gaps = [question["id"] for question in frontier(session)
                     if stop in question["blocking_for"]]
    if contract["blocking_conflicts"]:
        contract["status"] = "blocked_conflict"
    elif blocking_gaps:
        contract["status"] = "needs_question"
        contract["next_question"] = blocking_gaps[0]
    else:
        contract["status"] = "ready_for_planning"
    contract["validation"] = validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Internal validator; the JSON Schema is the published authority."""

    errors: list[str] = []
    if contract.get("contract_format") != CONTRACT_FORMAT:
        errors.append("contract_format must be %r" % CONTRACT_FORMAT)
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be %r" % SCHEMA_VERSION)
    for key in ("contract_id", "project_id", "original_request"):
        if not str(contract.get(key) or "").strip():
            errors.append("missing %s" % key)
    if contract.get("status") not in ("needs_question", "ready_for_planning", "blocked_conflict"):
        errors.append("invalid status %r" % contract.get("status"))
    if not isinstance(contract.get("revision"), int) or contract["revision"] < 1:
        errors.append("revision must be a positive integer")
    for decision in contract.get("decisions", []):
        if decision.get("source_type") not in SOURCE_TYPES:
            errors.append("decision %s has invalid source_type" % decision.get("field_path"))
        if decision.get("decision_status") not in DECISION_STATUSES:
            errors.append("decision %s has invalid decision_status" % decision.get("field_path"))
        if decision.get("locked") and decision.get("source_type") not in (
                "user_original", "grillme_answer", "inherited_project"):
            errors.append("decision %s is locked but was not user-confirmed" % decision.get("field_path"))
    if contract.get("status") == "ready_for_planning" and contract.get("blocking_conflicts"):
        errors.append("ready_for_planning cannot carry blocking conflicts")

    result = {"status": "PASS" if not errors else "FAIL", "errors": errors}
    try:
        import jsonschema
    except ImportError:
        # jsonschema 是声明依赖；缺它说明安装坏了，正式校验没做成就不能报 PASS。
        result["schema"] = "ENGINE_SKIPPED_NO_JSONSCHEMA"
        result["status"] = "FAIL"
        result["errors"] = errors + ["schema: jsonschema 未安装，正式校验未完成"]
        return result
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(contract, schema)
        result["schema"] = "VALID"
    except FileNotFoundError:
        result["schema"] = "SCHEMA_MISSING"
        result["status"] = "FAIL"
        result["errors"] = errors + ["schema: 找不到 %s，正式校验未完成" % SCHEMA_PATH]
    except Exception as exc:  # jsonschema.ValidationError and friends
        errors.append("schema: %s" % str(exc).splitlines()[0])
        result["status"] = "FAIL"
    return result


def export_ledger(session: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for question in QUESTION_BANK:
        entry = session["entries"].get(question["id"])
        if not entry:
            continue
        status = entry.get("status")
        if status == "resolved":
            source = entry.get("source_type")
            ledger_entry = {
                "id": question["id"],
                "status": "resolved",
                "basis": BASIS_BY_SOURCE.get(source, "agent_proposal"),
                "answer": entry.get("answer"),
                "locked": bool(entry.get("locked")),
                "note": entry.get("note") or "%s → %s" % (source, entry.get("decision_status")),
                "evidence": entry.get("evidence") or [],
            }
        else:
            ledger_entry = {"id": question["id"], "status": status,
                            "reason": entry.get("reason") or entry.get("note") or "未定"}
        entries.append(ledger_entry)
    return {
        "grill_format": "grill-ledger/v1",
        "job": {"kind": (session.get("job") or {}).get("kind", "original"),
                "request": (session.get("job") or {}).get("original_request", "")},
        "entries": entries,
        "session_ref": session.get("session_id"),
    }


def finish(session: dict[str, Any], *, contract_id: str | None = None) -> dict[str, Any]:
    _touch(session, "COMPILING")
    contract = compile_contract(session, contract_id=contract_id)
    if contract["validation"]["status"] != "PASS":
        _touch(session, "VALIDATION_FAILED")
        contract["status"] = "needs_question" if contract["status"] != "blocked_conflict" else contract["status"]
        return {"status": "VALIDATION_FAILED", "contract": contract}
    if contract["blocking_conflicts"]:
        _touch(session, "BLOCKED_CONFLICT")
        return {"status": "BLOCKED_CONFLICT", "contract": contract}
    if contract["status"] != "ready_for_planning":
        _touch(session, "NEEDS_QUESTION")
        return {"status": "NEEDS_QUESTION", "contract": contract}
    _touch(session, "READY_FOR_PLANNING")
    return {"status": "READY_FOR_PLANNING", "contract": contract}


def status(session: dict[str, Any]) -> dict[str, Any]:
    selection = select(session)
    settled = [qid for qid, entry in session["entries"].items() if _settled(entry)]
    return {
        "session_id": session.get("session_id"),
        "state": session.get("state"),
        "mode": session.get("mode"),
        "revision": session.get("revision"),
        "stop": stop_for(session),
        "settled": sorted(settled),
        "answered": [turn["id"] for turn in session["turns"]
                     if turn.get("action") in ("answer", "revise")],
        "defaulted": sorted(qid for qid, entry in session["entries"].items()
                            if entry.get("decision_status") == "defaulted"),
        "unresolved": [question["id"] for question in frontier(session)],
        "next": (selection.get("question") or {}).get("id"),
        "next_status": selection.get("status"),
    }


def metrics(session: dict[str, Any]) -> dict[str, Any]:
    """Observability without wall-clock: counts and rates only (deterministic)."""

    turns = session["turns"]
    answered = sum(1 for turn in turns if turn.get("action") in ("answer", "revise"))
    skipped = sum(1 for turn in turns if turn.get("action") == "skip")
    asked = answered + skipped
    entries = session["entries"].values()
    return {
        "session_id": session.get("session_id"),
        "state": session.get("state"),
        "mode": session.get("mode"),
        "questions_asked": asked,
        "answered": answered,
        "skipped": skipped,
        "skip_rate": round(skipped / asked, 3) if asked else 0.0,
        "defaulted_fields": sum(1 for entry in entries
                                if entry.get("decision_status") == "defaulted"),
        "proposed_fields": sum(1 for entry in entries
                               if entry.get("decision_status") == "proposed"),
        "revisions": len(session.get("history") or []),
        "unresolved": len(frontier(session)),
        "stop": stop_for(session),
    }


def show(session: dict[str, Any]) -> str:
    lines = ["会话 %s · %s · %s（revision %s）"
             % (session.get("session_id"), session.get("state"),
                MODES.get(session.get("mode"), {}).get("label", session.get("mode")),
                session.get("revision"))]
    lines.append("原话：%s" % (session.get("job") or {}).get("original_request", ""))
    lines.append("")
    lines.append("已定（%d）：" % len([e for e in session["entries"].values() if _settled(e)]))
    for question in QUESTION_BANK:
        entry = session["entries"].get(question["id"])
        if not entry or not _settled(entry):
            continue
        mark = "🔒" if entry.get("locked") else "▫️"
        lines.append("  %s %s %s = %s  （%s / %s）"
                     % (mark, question["id"], question["title"],
                        json.dumps(entry.get("answer"), ensure_ascii=False),
                        entry.get("source_type"), entry.get("decision_status")))
    pending = [question["id"] for question in frontier(session)]
    lines.append("")
    lines.append("未定（%d）：%s" % (len(pending), "、".join(pending) or "无"))
    return "\n".join(lines)


# ---------- self-test ----------

def self_test() -> int:
    passed = failed = 0
    lines: list[str] = []

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            lines.append("  PASS %s" % name)
        else:
            failed += 1
            lines.append("  FAIL %s" % name)

    session = new_session("出租车司机深夜遇到神秘乘客的悬疑短剧")
    check("empty session asks exactly one root question",
          select(session)["question"]["id"] == "G01")

    record_facts(session, {"G01": "prompt_only", "G03": 15, "G04": "9:16"})
    nxt = select(session)
    check("one question per round", isinstance(nxt.get("question"), dict))
    check("style outranks scope-out", nxt["question"]["id"] in ("G06", "G08"))

    answer(session, "G06", {"style_id": "写实", "register": "photoreal"})
    answer(session, "G08", "ambience_only")
    answer(session, "G10", "他最后垮掉。")
    answer(session, "I17", "none")
    default_rest(session)
    result = finish(session)
    check("prompt job can finish with traceable defaults",
          result["status"] == "READY_FOR_PLANNING", )
    check("defaults are marked, never user_original",
          any(d["decision_status"] == "defaulted" and d["source_type"] == "project_preset"
              for d in result["contract"]["decisions"]))
    check("ledger view keeps locked user decisions",
          any(entry.get("basis") == "user_explicit" and entry.get("locked")
              for entry in export_ledger(session)["entries"]))

    branched = new_session("x")
    record_facts(branched, {"G01": "full_film", "I02": "emotional_twist"})
    ids = [q["id"] for q in frontier(branched)]
    check("emotional twist opens the relationship branch", "I06" in ids and "I07" not in ids)
    branched2 = new_session("y")
    record_facts(branched2, {"G01": "full_film", "I02": "intellectual_mystery"})
    ids2 = [q["id"] for q in frontier(branched2)]
    check("mystery opens the clue branch", "I07" in ids2 and "I06" not in ids2)

    conflicted = new_session("only water sound")
    record_facts(conflicted, {"G01": "prompt_only", "G08": "ambience_only",
                              "I17": "none"})
    answer(conflicted, "G10", "他走了。")
    answer(conflicted, "I11", {"must_have": ["雨声"], "must_never": ["配乐"]})
    conflicted["entries"]["I17"] = _entry(QUESTION_INDEX["I17"], "score",
                                          "project_preset", "defaulted", locked=False)
    default_rest(conflicted)
    blocked = finish(conflicted)
    check("music preset versus banned music is blocked",
          blocked["status"] == "BLOCKED_CONFLICT")

    revised = new_session("revision test")
    record_facts(revised, {"G01": "prompt_only", "G03": 15})
    before = revised["revision"]
    revise(revised, "G03", 10)
    check("revision increments and keeps history",
          revised["revision"] == before + 1 and revised["history"][-1]["previous"] == 15)

    resumed = load_session_from_dict(json.loads(json.dumps(revised)))
    check("resume keeps the same next question",
          status(resumed)["next"] == status(revised)["next"])

    try:
        skip(revised, "G16")
    except GrillSessionError as exc:
        check("paid ignition cannot be skipped by the agent", exc.code == "GRILL_USER_ONLY")

    print("\n".join(lines))
    print("\n%d passed / %d failed" % (passed, failed))
    return RC_OK if failed == 0 else RC_FAIL


def load_session_from_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Session from an already-parsed dict (resume path used by tests/CLI)."""

    if payload.get("session_format") != SESSION_FORMAT:
        raise GrillSessionError("GRILL_SESSION_FORMAT", "expected %r" % SESSION_FORMAT)
    for key, shape in (("turns", []), ("history", []), ("applied_keys", {}),
                       ("entries", {}), ("asked", [])):
        payload.setdefault(key, shape)
    return payload


# ---------- CLI ----------

def _parse_value(raw: str) -> Any:
    text = raw.strip()
    if text in ("true", "false"):
        return text == "true"
    try:
        return json.loads(text)
    except ValueError:
        return raw


def _load(path: str) -> tuple[dict[str, Any], Path]:
    session = load_session(path)
    return session, Path(path)


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _render_question(selection: dict[str, Any], session: dict[str, Any]) -> str:
    question = selection["question"]
    mode = selection.get("mode_effective") or session.get("mode")
    lines = ["第 %d 问 · %s %s（%s · 评分 %s）"
             % (len(session["turns"]) + 1, question["id"], question["title"],
                DIMENSIONS_LABEL.get(question["dimension"], question["dimension"]),
                selection["score"])]
    lines.append("  %s" % question["question"])
    if question["kind"] == "choice":
        for index, value in enumerate(question["choices"]):
            lines.append("    %s %s" % ("ABCDEFG"[index], question["labels"][value]))
    elif question["kind"] == "object":
        for name, spec in question["fields"].items():
            if spec["type"] == "choice":
                lines.append("    %s：%s" % (name, " / ".join(spec["labels"][v]
                                                               for v in spec["choices"])))
            else:
                lines.append("    %s：%s" % (name, spec.get("hint", "文本")))
    elif question.get("examples"):
        lines.append("    例：%s" % question["examples"])
    lines.append("  ➡️ 推荐：%s" % question["recommendation"])
    lines.append("  📌 为什么问：%s" % question["why"])
    lines.append("  ⤷ 也可以：回复「你定」由 AI 决定（记 defaulted/proposed，不锁）"
                 "；或回复「直接开始」，其余按库内预设记档。")
    lines.append("  （模式 %s；每轮只问一个主问题。）" % mode)
    return "\n".join(lines)


DIMENSIONS_LABEL = {
    "goal": "创作目标", "story": "故事意图", "structure": "叙事结构",
    "visual": "视觉风格", "people": "人物与关系", "delivery": "交付规格",
    "constraints": "创作约束", "authority": "AI 自主权",
    "production": "生产闸（非创作意图）",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Creative Intent GrillMe session (one main question per round)")
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="create a session from the user's original words")
    start.add_argument("--out", required=True)
    start.add_argument("--force", action="store_true",
                       help="allow overwriting an existing session file")
    start.add_argument("--request", required=True)
    start.add_argument("--mode", default="auto", choices=list(ALLOWED_MODES))
    start.add_argument("--job-kind", default="original", choices=("original", "reverse"))
    start.add_argument("--project-id", default="PROJ_LOCAL")
    start.add_argument("--inherit", default=None,
                       help="seed the session from a published creative-intent contract")

    record = sub.add_parser("record", help="record facts the user already stated")
    record.add_argument("--session", required=True)
    record.add_argument("--set", action="append", default=[], metavar="ID=VALUE")
    record.add_argument("--source-ref", default="original_request")

    next_cmd = sub.add_parser("next", help="show the single next question")
    next_cmd.add_argument("--session", required=True)
    next_cmd.add_argument("--json", action="store_true")

    ans = sub.add_parser("answer", help="answer the current question")
    ans.add_argument("--session", required=True)
    ans.add_argument("--id", required=True)
    ans.add_argument("--value", required=True)
    ans.add_argument("--note", default="")
    ans.add_argument("--key", default=None)
    ans.add_argument("--revision", type=int, default=None)
    ans.add_argument("--json", action="store_true")

    skip_cmd = sub.add_parser("skip", help="let the AI decide (traceable preset)")
    skip_cmd.add_argument("--session", required=True)
    skip_cmd.add_argument("--id", required=True)
    skip_cmd.add_argument("--value", default=None)
    skip_cmd.add_argument("--note", default="")
    skip_cmd.add_argument("--key", default=None)
    skip_cmd.add_argument("--json", action="store_true")

    default_cmd = sub.add_parser("default-rest", help="fill every safe preset")
    default_cmd.add_argument("--session", required=True)
    default_cmd.add_argument("--json", action="store_true")

    defer_cmd = sub.add_parser("defer", help="explicitly postpone with a reason")
    defer_cmd.add_argument("--session", required=True)
    defer_cmd.add_argument("--id", required=True)
    defer_cmd.add_argument("--reason", required=True)

    rev = sub.add_parser("revise", help="change an earlier answer (new revision)")
    rev.add_argument("--session", required=True)
    rev.add_argument("--id", required=True)
    rev.add_argument("--value", required=True)
    rev.add_argument("--note", default="")

    fin = sub.add_parser("finish", help="compile and validate the Creative Intent Contract")
    fin.add_argument("--session", required=True)
    fin.add_argument("--contract", default=None)
    fin.add_argument("--ledger", default=None)
    fin.add_argument("--json", action="store_true")

    stat = sub.add_parser("status", help="session status")
    stat.add_argument("--session", required=True)
    stat.add_argument("--json", action="store_true")

    show_cmd = sub.add_parser("show", help="decision summary a user can correct")
    show_cmd.add_argument("--session", required=True)

    metrics_cmd = sub.add_parser("metrics", help="question / skip / default counts")
    metrics_cmd.add_argument("--session", required=True)

    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.command:
        parser.print_usage(sys.stderr)
        return RC_USAGE

    try:
        if args.command == "start":
            session = new_session(args.request, mode=args.mode, kind=args.job_kind,
                                  project_id=args.project_id)
            if args.inherit:
                inherited = inherit_contract(
                    session, json.loads(Path(args.inherit).read_text(encoding="utf-8")))
            else:
                inherited = []
            # 覆盖已有会话就是丢数据：没有 --force 一律拒绝。
            existing = Path(args.out)
            if existing.exists() and not getattr(args, "force", False):
                print(json.dumps({"status": "SESSION_EXISTS",
                                  "path": args.out,
                                  "message": "该路径已有会话；覆盖请显式加 --force"},
                                 ensure_ascii=False, indent=2))
                return RC_USAGE
            save_session(args.out, session)
            print(json.dumps({"status": "STARTED", "session_id": session["session_id"],
                              "state": session["state"], "path": args.out,
                              "inherited": inherited},
                             ensure_ascii=False, indent=2))
            return RC_OK

        session, path = _load(args.session)

        if args.command == "record":
            values = {}
            for item in args.set:
                if "=" not in item:
                    raise GrillSessionError("GRILL_USAGE", "--set expects ID=VALUE, got %r" % item)
                qid, _, raw = item.partition("=")
                values[qid.strip()] = _parse_value(raw)
            changed = record_facts(session, values, source_ref=args.source_ref)
            save_session(path, session)
            print(json.dumps({"status": "RECORDED", "ids": changed}, ensure_ascii=False))
            return RC_OK

        if args.command == "next":
            selection = select(session)
            if args.json:
                _emit({"status": selection["status"], "reason": selection.get("reason"),
                       "stop": selection.get("stop"),
                       "question": {key: selection["question"].get(key)
                                    for key in ("id", "dimension", "title", "question", "kind",
                                                "choices", "labels", "fields", "recommendation", "why")}
                       if selection.get("question") else None,
                       "score": selection.get("score"), "mode": selection.get("mode")}, True)
            elif selection["status"] == "QUESTION":
                print(_render_question(selection, session))
            else:
                print("%s：%s（stop=%s）——可以 finish 编契约；剩余未定项会写进 unresolved。"
                      % (selection["status"], selection.get("reason"), selection.get("stop")))
            return RC_OK

        if args.command == "answer":
            result = answer(session, args.id, _parse_value(args.value), note=args.note,
                            key=args.key, revision=args.revision)
            save_session(path, session)
            _emit(result, True)
            return RC_OK

        if args.command == "skip":
            result = skip(session, args.id,
                          _parse_value(args.value) if args.value is not None else None,
                          note=args.note, key=args.key)
            save_session(path, session)
            _emit(result, True)
            return RC_OK

        if args.command == "default-rest":
            filled = default_rest(session)
            save_session(path, session)
            print(json.dumps({"status": "DEFAULTED", "ids": filled}, ensure_ascii=False))
            return RC_OK

        if args.command == "defer":
            result = defer(session, args.id, args.reason)
            save_session(path, session)
            _emit(result, True)
            return RC_OK

        if args.command == "revise":
            result = revise(session, args.id, _parse_value(args.value), note=args.note)
            save_session(path, session)
            _emit(result, True)
            return RC_OK

        if args.command == "finish":
            result = finish(session)
            contract_path = Path(args.contract) if args.contract else path.with_suffix(".contract.json")
            # A published contract revision is immutable: never overwrite a
            # different revision at the same path.
            contract_requested = contract_path
            contract_path, contract_conflict = resolve_contract_target(
                contract_path, result["contract"])
            if contract_conflict:
                print(json.dumps({"status": "CONTRACT_CONFLICT",
                                  "path": str(contract_path),
                                  "message": contract_conflict},
                                 ensure_ascii=False, indent=2))
                return RC_USAGE
            ledger_path = Path(args.ledger) if args.ledger else path.with_suffix(".ledger.json")
            # 三个输出互相同路径时，后写的会覆盖先写的，而流程照样报成功（2026-11-12 审计指出）。
            targets = [contract_path, ledger_path, path]
            resolved_targets = [item.resolve() for item in targets]
            if len(set(resolved_targets)) != len(resolved_targets):
                print(json.dumps({"status": "EXPORT_PATH_COLLISION",
                                  "paths": [str(item) for item in targets],
                                  "message": "合同/台账/会话输出到同一路径会互相覆盖；请改其中一个路径"},
                                 ensure_ascii=False, indent=2))
                return RC_USAGE
            ledger_payload = export_ledger(session)
            # 台账不能落在合同的位置上：那会静默销毁已发布的修订（2026-11-12 审计指出）。
            # 注意只拦"覆盖合同"，不拦台账自身的正常更新。
            if same_file(ledger_path, contract_requested) or same_file(ledger_path, contract_path):
                print(json.dumps({"status": "LEDGER_CONFLICT",
                                  "path": str(ledger_path),
                                  "message": "台账目标与合同路径相同；请改其中一个路径"},
                                 ensure_ascii=False, indent=2))
                return RC_USAGE
            contract_path.write_text(json.dumps(result["contract"], ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
            ledger_path.write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
            save_session(path, session)
            if args.json:
                _emit({"status": result["status"], "contract": str(contract_path),
                       "ledger": str(ledger_path),
                       "contract_status": result["contract"]["status"],
                       "unresolved": result["contract"]["unresolved"],
                       "blocking_conflicts": result["contract"]["blocking_conflicts"]}, True)
            else:
                print("%s · 契约 %s · 台账 %s" % (result["status"], contract_path, ledger_path))
                conflicts = result["contract"]["blocking_conflicts"]
                if conflicts:
                    for conflict in conflicts:
                        print("  [BLOCK] %s %s" % (conflict["code"], conflict["message"]))
                elif result["contract"]["unresolved"]:
                    print("  未定：%s" % "、".join(result["contract"]["unresolved"][:8]))
            return {"READY_FOR_PLANNING": RC_OK, "BLOCKED_CONFLICT": RC_FAIL,
                    "NEEDS_QUESTION": RC_WARN, "VALIDATION_FAILED": RC_FAIL}[result["status"]]

        if args.command == "status":
            payload = status(session)
            _emit(payload, True)
            return RC_OK

        if args.command == "show":
            print(show(session))
            return RC_OK

        if args.command == "metrics":
            _emit(metrics(session), True)
            return RC_OK

    except GrillSessionError as exc:
        sys.stderr.write("%s\n" % exc)
        return RC_FAIL

    parser.print_usage(sys.stderr)
    return RC_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
