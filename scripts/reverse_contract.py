# -*- coding: utf-8 -*-
"""Shared mode/evidence contract for reverse and production workflows."""

from __future__ import annotations

MODES = (
    "content_reverse",
    "copy_reverse",
    "source_replica",
    "rule_distill",
    "production_build",
)

SOURCE_ACCESS = (
    "original_readback",
    "copy_readback",
    "public_media",
    "text_only",
    "none",
)

EVIDENCE_CLASSES = (
    "source_readback",
    "copy_readback",
    "public_media",
    "text_explicit",
    "inferred",
    "unresolved",
)

MODE_ALIASES = {
    "film_reverse": "content_reverse",
}

# 反推类任务必须先有该作品自己的画像：跨作品迁移已实测不成立
# （model 命中 0.25 / 0.00 / 0.00，duration 0.67 / 0.07 / 0.00）。
PROFILE_REQUIRED_MODES = ("content_reverse", "copy_reverse", "source_replica", "rule_distill")


def normalize_mode(value: str | None, default: str = "production_build") -> tuple[str, list[str]]:
    """Return canonical mode plus warnings."""
    raw = (value or default).strip()
    warnings: list[str] = []
    if raw in MODE_ALIASES:
        mapped = MODE_ALIASES[raw]
        warnings.append("DEPRECATED_MODE:%s->%s" % (raw, mapped))
        return mapped, warnings
    if raw not in MODES:
        raise ValueError("invalid mode: %s" % raw)
    return raw, warnings


def infer_source_access(data: dict, mode: str) -> str:
    """Infer access level without granting original access to a copy."""
    explicit = (data.get("source_access") or "").strip()
    if explicit:
        if explicit not in SOURCE_ACCESS:
            raise ValueError("invalid source_access: %s" % explicit)
        return explicit
    if data.get("copy_project_uuid"):
        return "copy_readback"
    if data.get("source_project_uuid") and mode == "source_replica":
        return "original_readback"
    if data.get("source_film"):
        return "public_media"
    if mode in {"content_reverse", "copy_reverse", "source_replica", "rule_distill"}:
        return "none"
    return "none"


def evidence_default(mode: str, source_access: str) -> str:
    if mode == "source_replica" and source_access == "original_readback":
        return "source_readback"
    if mode == "copy_reverse" and source_access == "copy_readback":
        return "copy_readback"
    if mode == "content_reverse":
        return "public_media" if source_access == "public_media" else "text_explicit"
    if mode == "rule_distill":
        return "inferred"
    return "inferred"


def mode_errors(contract: dict) -> list[str]:
    """Validate mode/source-access coherence."""
    errors: list[str] = []
    mode = contract.get("mode") or contract.get("production_mode") or "production_build"
    try:
        mode, _ = normalize_mode(mode)
    except ValueError as exc:
        return [str(exc)]
    access = contract.get("source_access") or "none"
    if access not in SOURCE_ACCESS:
        errors.append("invalid source_access: %s" % access)
    if mode == "source_replica" and access != "original_readback":
        errors.append("SOURCE_ACCESS_NOT_ORIGINAL")
    if mode == "copy_reverse":
        if not contract.get("copy_project_uuid"):
            errors.append("COPY_UUID_MISSING")
        if not contract.get("source_project_uuid"):
            errors.append("SOURCE_UUID_MISSING")
    if mode == "content_reverse" and access == "none":
        errors.append("CONTENT_SOURCE_MISSING")
    if mode in PROFILE_REQUIRED_MODES and not contract.get("work_profile"):
        errors.append("WORK_PROFILE_MISSING")
    return errors
