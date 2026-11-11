"""Portable question payload adapter. The host invokes its own native tool.

The inventory is supplied by actual host discovery. Preparing a payload only
persists a pending question. Recording a real response is the sole answer path.
No UI registration, network call or media generation occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .grill_bank import QUESTION_INDEX
    from .grill_session import answer, load_session, save_session, select, skip
except ImportError:
    from grill_bank import QUESTION_INDEX
    from grill_session import answer, load_session, save_session, select, skip

MORE = "更多选项"
CUSTOM = "填写自定义答案"
WAIT = "暂不回答"


def _fingerprint(session: dict[str, Any]) -> str:
    data = {key: session.get(key) for key in ("session_id", "revision", "entries", "turns", "mode")}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _tool_shape(tool: dict[str, Any]) -> str | None:
    if tool.get("available") is not True:
        return None
    schema = tool.get("input_schema") or tool.get("inputSchema") or {}
    item = ((schema.get("properties") or {}).get("questions") or {}).get("items") or {}
    fields = item.get("properties") or {}
    option = (fields.get("options") or {}).get("items") or {}
    if "title" in fields and option.get("type") == "string":
        return "title_options"
    if {"id", "header", "question", "options"} <= fields.keys() and option.get("type") == "object":
        return "codex_plan"
    return None


def prepare_question(session: dict[str, Any], available_tools: list[dict[str, Any]], *,
                     text_consent: str = "") -> dict[str, Any]:
    """Return a native tool call or pause for consent. Never submit an answer.

    tools.json entries contain name, available=true and the discovered input_schema.
    Supported question shapes are title/options strings and Codex Plan questions.
    Complex answers remain unresolved until interpreted against the original bank.
    """
    pending = session.get("ui_pending")
    if pending:
        if pending["fingerprint"] != _fingerprint(session):
            raise ValueError("GRILL_UI_STALE: session changed while waiting for its response")
        return pending["presentation"]
    selection = select(session)
    if selection["status"] != "QUESTION":
        return {"state": selection["status"], "selection": selection}
    question = selection["question"]
    chosen = next((tool for tool in available_tools if _tool_shape(tool)), None)
    if text_consent:
        if not isinstance(text_consent, str) or not text_consent.strip():
            raise ValueError("GRILL_UI_CONSENT: store the user's explicit text-fallback consent")
        session["ui_text_consent"] = text_consent.strip()
    if chosen is None and not session.get("ui_text_consent"):
        return {"state": "TEXT_CONSENT_REQUIRED", "explanation":
                "当前宿主未提供可用的原生交互提问工具。请先征得用户同意，再改用文字选项。"}

    shape = _tool_shape(chosen) if chosen else "text"
    choices = list(question.get("choices") or [])
    # Only bank-declared delegation choices can delegate. Production approvals
    # never receive an adapter-created 'AI decides' action.
    if question.get("authority") == "user_only":
        choices = [value for value in choices if value != "ai_decide"]
    labels = question.get("labels") or {}
    mapping = {labels.get(value, value): value for value in choices}
    page = int(session.get("ui_page", 0))
    visible = list(mapping)
    if shape == "codex_plan":
        schema = chosen.get("input_schema") or chosen.get("inputSchema")
        options_schema = schema["properties"]["questions"]["items"]["properties"]["options"]
        maximum = options_schema.get("maxItems", 3)
        if maximum < 2:
            raise ValueError("GRILL_UI_SCHEMA: native options capacity is unsupported")
        if len(visible) > maximum:
            size = maximum - 1
            start = page * size
            visible = visible[start:start + size]
            if start + size < len(mapping):
                visible.append(MORE)
        if len(visible) < 2:
            visible += [CUSTOM, WAIT][:2 - len(visible)]
    question_text = question["question"]
    question_text += "\n推荐方向\n" + question["recommendation"]
    question_text += "\n为什么问\n" + question["why"]
    if question["kind"] != "choice":
        question_text += " 请用自由文本作答。"
    if shape == "title_options":
        native_question = {"title": question_text}
        if visible:
            native_question["options"] = visible
        call = {"name": chosen["name"], "arguments": {"questions": [native_question]}}
    elif shape == "codex_plan":
        call = {"name": chosen["name"], "arguments": {"questions": [{
            "id": question["id"], "header": question["title"][:12],
            "question": question_text,
            "options": [{"label": label, "description": question["why"] if label in mapping else label}
                        for label in visible],
        }]}}
    else:
        call = None
    fingerprint = _fingerprint(session)
    token = "%s|%s|%s|%s" % (fingerprint, question["id"], page, len(session.get("ui_history", [])))
    pending_id = "GUI_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    presentation = {"state": "WAITING_FOR_USER", "pending_id": pending_id,
                    "revision": session["revision"], "question_id": question["id"]}
    if call:
        presentation["tool_call"] = call
    else:
        presentation["text_question"] = {"question": question_text, "choices": mapping}
    session["ui_pending"] = {"pending_id": pending_id, "revision": session["revision"],
                             "question_id": question["id"], "fingerprint": fingerprint,
                             "mapping": {label: mapping[label] for label in visible if label in mapping}
                             if shape == "codex_plan" else mapping,
                             "more": MORE in visible, "presentation": presentation}
    return presentation


def _response_values(result: Any, pending: dict[str, Any]) -> list[Any]:
    qid = pending["question_id"]
    if isinstance(result, list):
        call = pending["presentation"].get("tool_call") or {}
        question = ((call.get("arguments") or {}).get("questions") or [{}])[0]
        if "title" not in question or len(result) != 1 or not isinstance(result[0], dict):
            return []
        item = result[0]
        try:
            identity = json.loads(item.get("questionItemId") or "null")
        except (TypeError, ValueError):
            return []
        if (not isinstance(identity, list) or len(identity) != 3
                or identity[0] != call.get("name", "").split(".")[-1]
                or not isinstance(identity[1], str) or not identity[1]
                or identity[2] != 0 or item.get("question") != question["title"]):
            return []
        return [item["answer"]] if "answer" in item else []
    if not isinstance(result, dict) or result.get("cancelled") or result.get("status") in ("cancelled", "pending"):
        return []
    answers = result.get("answers")
    if isinstance(answers, dict):
        response = answers.get(qid)
        if isinstance(response, dict):
            return response.get("answers") or []
    return []


def record_response(session: dict[str, Any], response: dict[str, Any], *, proposal: Any = None,
                    interpreted_value: Any = None) -> dict[str, Any]:
    """Validate pending identity, then map a submitted host result to the bank.

    Unknown response formats and structured free text need Agent interpretation.
    The raw response stays in ui_pending for that handoff, never a guessed fact.
    """
    pending = session.get("ui_pending")
    if not pending or response.get("pending_id") != pending["pending_id"]:
        raise ValueError("GRILL_UI_IDENTITY: response does not match the pending question")
    if response.get("revision") != pending["revision"] or pending["fingerprint"] != _fingerprint(session):
        raise ValueError("GRILL_UI_STALE: response belongs to an older session state")
    result = response.get("result")
    pending["last_result"] = result
    values = _response_values(result, pending)
    if not values:
        return dict(pending["presentation"], state="WAITING_FOR_USER")
    if len(values) != 1 or not isinstance(values[0], str):
        return {"state": "NEEDS_INTERPRETATION", "pending_id": pending["pending_id"]}
    raw = values[0].strip()
    if not raw or raw in (CUSTOM, WAIT):
        return dict(pending["presentation"], state="WAITING_FOR_USER")
    receipt = {"pending_id": pending["pending_id"], "question_id": pending["question_id"],
               "tool_call": pending["presentation"].get("tool_call"), "result": result}
    if raw == MORE and pending["more"]:
        session.setdefault("ui_history", []).append(receipt)
        session["ui_page"] = int(session.get("ui_page", 0)) + 1
        del session["ui_pending"]
        return {"state": "QUESTION_PAGE_CHANGED"}
    question = QUESTION_INDEX[pending["question_id"]]
    value = pending["mapping"].get(raw, raw)
    if raw in ("你定", "AI decides", "由 AI 决定", "由 AI 设计", "ai_decide") and value != "ai_decide":
        return {"state": "NEEDS_INTERPRETATION", "pending_id": pending["pending_id"],
                "reason": "Delegation is unavailable for this question"}
    if value == "ai_decide":
        if question.get("authority") == "user_only" or value not in question.get("choices", ()):
            raise ValueError("GRILL_UI_AUTHORITY: this question cannot be delegated")
        if proposal is None:
            return {"state": "DELEGATED", "pending_id": pending["pending_id"],
                    "question_id": question["id"], "needs": "Agent proposal, recorded unlocked"}
        if proposal == "ai_decide":
            raise ValueError("GRILL_UI_PROPOSAL: supply the proposed creative value")
        applied = skip(session, question["id"], proposal, note="用户通过原生选项将此项交由 AI 提议")
    elif interpreted_value is not None and question.get("authority") != "user_only":
        applied = answer(session, question["id"], interpreted_value,
                         note="宿主响应 %s 经 Agent 映射，原始回答保存在 ui_history" % pending["pending_id"])
        receipt["interpreted_value"] = interpreted_value
    elif question["kind"] in ("text", "ratio", "choice"):
        if question["kind"] == "choice" and raw not in pending["mapping"]:
            return {"state": "NEEDS_INTERPRETATION", "pending_id": pending["pending_id"], "raw_response": raw}
        applied = answer(session, question["id"], value, note="真实宿主提问响应 %s" % pending["pending_id"])
    elif question["kind"] == "number":
        try:
            value = float(raw)
        except ValueError:
            return {"state": "NEEDS_INTERPRETATION", "pending_id": pending["pending_id"], "raw_response": raw}
        applied = answer(session, question["id"], value, note="真实宿主提问响应 %s" % pending["pending_id"])
    else:
        return {"state": "NEEDS_INTERPRETATION", "pending_id": pending["pending_id"], "raw_response": raw,
                "question_id": question["id"], "expected_kind": question["kind"]}
    session.setdefault("ui_history", []).append(receipt)
    session.pop("ui_page", None)
    del session["ui_pending"]
    return {"state": "ANSWERED", "applied": applied}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--session", required=True)
    prepare.add_argument("--tools", required=True, help="JSON list of actually available native tool metadata")
    prepare.add_argument("--text-consent", default="", help="Actual user consent quote after explaining missing native UI")
    record = commands.add_parser("record")
    record.add_argument("--session", required=True)
    record.add_argument("--response", required=True, help="JSON pending_id/revision/result envelope")
    record.add_argument("--proposal", help="JSON or string creative proposal after explicit bank delegation")
    record.add_argument("--interpreted-value", help="Typed JSON mapped from an actual free-text response; raw response is retained")
    args = parser.parse_args()
    session = load_session(args.session)
    if args.command == "prepare":
        result = prepare_question(session, json.loads(Path(args.tools).read_text(encoding="utf-8")),
                                  text_consent=args.text_consent)
    else:
        proposal = args.proposal
        if proposal is not None:
            try:
                proposal = json.loads(proposal)
            except ValueError:
                pass
        interpreted = json.loads(args.interpreted_value) if args.interpreted_value is not None else None
        result = record_response(session, json.loads(Path(args.response).read_text(encoding="utf-8")),
                                 proposal=proposal, interpreted_value=interpreted)
    save_session(args.session, session)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
