"""Constraint semantics — does the *delivered* text honour a constraint?

**Why this module exists.** The capability gate used to check *fields*
(`consumed`, `READY`, `constraint_evidence`) and never checked *meaning*. A
final prompt could be rewritten to "平视" or a narration line and still report
READY. This module answers the meaning question instead:

* it never reads the generator's self-report — the caller passes the actual
  delivered text plus the authoritative constraint semantics;
* it accepts **synonyms**, not string equality: a "固定俯拍" requirement is met
  by "正上方俯视" or "自上而下固定";
* it separates **禁止人声** from **实际旁白**: a forbidden form that sits
  inside a prohibition ("禁止人声、对白、旁白") is a prohibition, not a
  violation; the same form stated as content ("旁白清晰朗读一段解说") is a
  violation.

Scope model — the part that decides PASS/FAIL
---------------------------------------------
Every mention of a concept is classified **individually** as *affirmative* or
*negated*, and that classification is what the requirement is judged on:

* a **required** concept counts as delivered only when it has at least one
  **affirmative** mention. "相机禁止俯拍" mentions 俯拍 but negates it → the
  requirement is **not** delivered → FAIL. "正上方俯视，固定机位" is an
  affirmative mention → delivered;
* a **forbidden** concept is a violation only when it has at least one
  **affirmative** mention ("旁白清晰朗读解说" → violation) and **not** when
  every mention is negated ("禁止人声、对白、旁白" → no violation).

Two rules keep the negation scope local and predictable instead of
clause-wide:

1. A negation marker negates **the enumeration it introduces**, i.e. the
   items of the list that follows it, up to the end of that list. It does not
   bleed into a later, independent assertion in the same clause.
   "禁止音乐，旁白清晰朗读解说。" → 音乐 is negated, 旁白 is affirmative →
   violation.
2. A negation marker directly preceding a term negates **that term only**
   ("禁止俯拍" / "不要出现人声" / "无对白").

A marker that lies *inside* the matched surface form does not negate it: the
required form "不出现人物" is satisfied by a text that says "不出现人物" —
the marker is part of the phrase being required, not a negation of it.

The scope rules are generic (marker → nearest enumerated term). They are not
keyed to any particular wording.

Nothing here imports the compiler, so a consumer can call it on any text.
"""

from __future__ import annotations

import re
from typing import Any

# Surface forms of the concepts the stage-1 constraints talk about.
# A marker is expanded through these groups, so legitimate paraphrase passes
# while a contradiction still fails.
CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "overhead_camera": (
        "俯拍", "俯视", "俯冲", "正上方", "正俯视", "顶视", "自上而下",
        "overhead", "top-down", "top down", "bird's eye", "birds eye",
    ),
    "fixed_camera": ("固定机位", "机位不移动"),
    "eye_level_camera": (
        "平视", "平角", "水平机位", "水平视角", "eye-level", "eye level",
    ),
    "low_angle_camera": ("仰拍", "仰视", "低角度仰视", "low-angle", "low angle"),
    "top_right_negative_space": (
        "右上角留白", "右上留白", "画面右上角", "右上角空白", "右上方留白",
        "右上区域留白", "upper-right negative space", "top-right negative space",
    ),
    "centered_composition": (
        "居中构图", "主体居中", "正中构图", "centered composition", "center framing",
    ),
    "rain_ambience": ("雨声", "雨音", "雨的环境声", "rain ambience", "rain sound"),
    "narration": (
        "旁白", "解说", "画外音", "口播", "narration", "voice-over", "voiceover",
        "voice over",
    ),
    "dialogue": ("对白", "台词", "说话者", "dialogue", "dialog"),
    "vocal": ("人声", "voice", "vocal"),
    "music": ("音乐", "配乐", "背景音乐", "music", "soundtrack"),
}

# Words that turn a mention into a prohibition. NOTE: this must be a real
# assignment — an annotation-only statement raises NameError at call time.
NEGATION_MARKERS: tuple[str, ...] = (
    "禁止", "严禁", "杜绝", "不得", "不能", "不要", "不许", "不可", "不含",
    "不出现", "不引入", "不包含", "没有", "无任何", "无", "免于", "避免", "排除", "去掉", "移除",
    "不",
    "not ", "no ", "without", "must not", "do not", "don't", "never",
)

# Connectors that may sit between a negation marker and the term it governs.
_NEGATION_CONNECTORS = ("出现", "带有", "加入", "包含", "使用", "加以")

# Characters that end a clause: a negation never reaches across them.
_CLAUSE_BREAK = "。；;.!?！？\n"

# Characters that separate two independent assertions inside a clause.
_ASSERTION_BREAK = "、,，。；;.!?！？"


def _norm(text: Any) -> str:
    """Whitespace-free, case-folded text for substring reasoning."""

    return re.sub(r"\s+", "", str(text or "")).lower()


def _surface_forms(marker: Any) -> list[str]:
    """Every surface form that expresses the same concept as ``marker``."""

    base = _norm(marker)
    if not base:
        return []
    forms = {base}
    for group in CONCEPT_SYNONYMS.values():
        if any(base == _norm(item) for item in group):
            forms.update(_norm(item) for item in group)
    return sorted(form for form in forms if form)


def _find_negation_markers(text: str) -> list[tuple[int, int, str]]:
    """(start, end, marker) of every negation marker inside ``text``."""

    lowered = text.lower()
    hits: list[tuple[int, int, str]] = []
    for marker in NEGATION_MARKERS:
        if marker.isascii():
            pattern = r"(?<![a-z])" + r"\s+".join(
                re.escape(word) for word in marker.split()
            ) + r"(?![a-z])"
            hits.extend((match.start(), match.end(), marker)
                        for match in re.finditer(pattern, lowered))
            continue
        start = 0
        while True:
            index = lowered.find(marker, start)
            if index < 0:
                break
            hits.append((index, index + len(marker), marker))
            start = index + len(marker)
    hits.sort()
    return hits


def _phrase_local_end(text: str, marker_start: int, marker_end: int) -> int | None:
    """Keep internal negation inside the finite fixed-camera surface form."""
    for phrase in re.finditer("机位不移动", text):
        if phrase.start() <= marker_start and marker_end <= phrase.end():
            return phrase.end()
    return None


def _enumeration_items(text: str, marker_end: int) -> list[tuple[int, int]]:
    """Character spans of the items of the enumeration a marker introduces.

    The enumeration starts right after the marker (skipping a connector such
    as "的" / "：" / "、") and runs over the following list items, which are
    separated by "、". It stops at the first character that ends a clause or
    separates an independent assertion ("，" ends the list: a comma starts a
    new assertion, not a new list item).
    """

    index = marker_end
    length = len(text)
    while index < length and text[index] in "的：:、，, ":
        index += 1
    items: list[tuple[int, int]] = []
    item_start = index
    while index < length:
        char = text[index]
        if char == "、":
            if index > item_start:
                items.append((item_start, index))
            item_start = index + 1
            index += 1
            continue
        if char in _CLAUSE_BREAK or char in ",，":
            break
        index += 1
    if index > item_start:
        items.append((item_start, index))
    return items


def _mentions(text: str, forms: list[str]) -> list[dict[str, Any]]:
    """Classify every mention of any surface form as affirmative or negated.

    A mention is *negated* when the nearest preceding negation marker either

    * directly governs it ("禁止俯拍", "无对白"), or
    * introduces an enumeration that contains it ("禁止人声、对白、旁白").

    A negation marker never reaches past the end of the enumeration it
    introduces, so an independent later assertion in the same clause stays
    affirmative ("禁止音乐，旁白清晰朗读解说。").

    A marker that lies inside the matched form does not negate it — the form
    itself carries the negation ("不出现人物" as a *required* phrase).
    """

    raw_text = str(text or "").lower()
    markers = [(len(_norm(raw_text[:start])), len(_norm(raw_text[:end])), marker)
               for start, end, marker in _find_negation_markers(raw_text)]
    text = _norm(raw_text)
    lowered = text
    enumerated: list[tuple[int, int]] = []
    for marker_start, end, _marker in markers:
        local_end = _phrase_local_end(text, marker_start, end)
        enumerated.extend((start, min(stop, local_end) if local_end is not None else stop)
                          for start, stop in _enumeration_items(text, end))

    mentions: list[dict[str, Any]] = []
    for form in forms:
        if not form:
            continue
        start = 0
        while True:
            index = lowered.find(form, start)
            if index < 0:
                break
            end = index + len(form)
            negated = False
            for item_start, item_end in enumerated:
                if item_start <= index and end <= item_end:
                    negated = True
                    break
            if not negated:
                for marker_start, marker_end, _marker in markers:
                    local_end = _phrase_local_end(text, marker_start, marker_end)
                    if local_end is not None and index >= local_end:
                        continue
                    # A marker inside the form itself is part of the phrase.
                    if marker_start >= index and marker_end <= end:
                        continue
                    if marker_end > index:
                        continue
                    gap = text[marker_end:index]
                    if gap in _NEGATION_CONNECTORS:
                        negated = True
                        break
                    if len(gap) <= 3 and not any(
                        char in gap for char in _ASSERTION_BREAK
                    ):
                        negated = True
                        break
            mentions.append(
                {
                    "form": form,
                    "start": index,
                    "end": end,
                    "negated": negated,
                }
            )
            start = end if end > index else index + 1
    return mentions


def _match_markers(text: str, markers: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split markers into (matched, missing) by *affirmative* surface-form presence."""

    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for marker in markers:
        forms = _surface_forms(marker)
        mentions = _mentions(text, forms)
        affirmative = [item for item in mentions if not item["negated"]]
        negated = [item for item in mentions if item["negated"]]
        record = {
            "marker": str(marker),
            "forms": forms,
            "hits": sorted({item["form"] for item in affirmative}),
            "negated_forms": sorted({item["form"] for item in negated}),
        }
        if affirmative:
            matched.append(record)
        else:
            missing.append(record)
    return matched, missing


def evaluate_constraint(text: Any, semantics: Any) -> dict[str, Any]:
    """Judge ``text`` against one constraint's semantics.

    Returns a machine-readable report:

    ```text
    {
      "ok": bool,
      "required": {"matched": [...], "missing": [...]},
      "required_satisfied": bool,
      "forbidden": {"violations": [...]},
    }
    ```

    `required_any` is satisfied by ONE alternative; `required_all` needs every
    item. A constraint with neither key imposes no positive requirement — it
    is then judged only on its `forbidden` list.

    A required marker that only ever appears **negated** ("相机禁止俯拍")
    counts as *missing*: the delivered text does not deliver the requirement.
    A forbidden marker that only ever appears **negated** ("禁止旁白") is not
    a violation.
    """

    semantics = semantics if isinstance(semantics, dict) else {}
    required_any = [item for item in (semantics.get("required_any") or []) if str(item).strip()]
    required_all = [item for item in (semantics.get("required_all") or []) if str(item).strip()]
    forbidden = [item for item in (semantics.get("forbidden") or []) if str(item).strip()]

    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    any_matched: list[dict[str, Any]] = []
    any_missing: list[dict[str, Any]] = []
    if required_any:
        any_matched, any_missing = _match_markers(text, required_any)
        matched.extend(any_matched)
        missing.extend(any_missing)

    all_matched: list[dict[str, Any]] = []
    all_missing: list[dict[str, Any]] = []
    if required_all:
        all_matched, all_missing = _match_markers(text, required_all)
        matched.extend(all_matched)
        missing.extend(all_missing)

    any_satisfied = (not required_any) or bool(any_matched)
    all_satisfied = (not required_all) or not all_missing
    required_satisfied = any_satisfied and all_satisfied

    violations: list[dict[str, Any]] = []
    normalised = _norm(text)
    for marker in forbidden:
        forms = _surface_forms(marker)
        mentions = _mentions(text, forms)
        affirmative = [item for item in mentions if not item["negated"]]
        if not affirmative:
            # Every mention sits inside a prohibition: that honours the
            # constraint ("禁止人声、对白、旁白").
            continue
        for item in affirmative:
            start = item["start"]
            end = item["end"]
            violations.append(
                {
                    "marker": str(marker),
                    "form": item["form"],
                    "segment": normalised[max(0, start - 24): end + 24].strip()[:120],
                    "context": normalised[max(0, start - 40): end + 40].strip()[:160],
                }
            )

    return {
        "ok": required_satisfied and not violations,
        "required": {"matched": matched, "missing": missing},
        "required_satisfied": required_satisfied,
        "forbidden": {"violations": violations},
    }


__all__ = ["CONCEPT_SYNONYMS", "NEGATION_MARKERS", "evaluate_constraint"]
