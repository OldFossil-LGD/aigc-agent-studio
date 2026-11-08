"""Shared production timing resolution."""

from __future__ import annotations

import math
from typing import Any


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def resolve_shot_timing(shot: Any) -> dict[str, Any]:
    """Resolve and validate the three production clocks for one shot.

    The returned dictionaries are newly allocated. The input is not mutated.
    """
    if not isinstance(shot, dict):
        raise ValueError("shot must be an object")

    duration = shot.get("duration_sec")
    if duration is not None:
        if not _is_number(duration) or duration <= 0:
            raise ValueError("shot duration_sec must be a finite positive non-bool number")

    if "generation_duration_sec" in shot:
        generation = shot.get("generation_duration_sec")
        if generation is None or not _is_number(generation) or generation <= 0:
            raise ValueError("shot generation_duration_sec must be a finite positive non-bool number")
    else:
        generation = None

    has_cut = "cut_range" in shot
    cut_raw = shot.get("cut_range") if has_cut else None
    start: Any = None
    end: Any = None
    cut_provided = False

    if has_cut:
        if cut_raw is None or cut_raw == "":
            raise ValueError("shot cut_range must be an object")
        if not isinstance(cut_raw, dict):
            raise ValueError("shot cut_range must be an object")
        if set(cut_raw) != {"start_sec", "end_sec"}:
            raise ValueError("shot cut_range must contain exactly start_sec and end_sec")
        if "start_sec" not in cut_raw or "end_sec" not in cut_raw:
            raise ValueError("shot cut_range must contain start_sec and end_sec")
        start = cut_raw.get("start_sec")
        end = cut_raw.get("end_sec")
        if not _is_number(start) or start < 0:
            raise ValueError("shot cut_range start_sec must be a finite non-negative non-bool number")
        if not _is_number(end) or end <= start:
            raise ValueError("shot cut_range end_sec must be greater than start_sec")
        cut_provided = True

    if generation is None:
        generation = duration

    if cut_provided:
        if duration is None or generation is None:
            raise ValueError("shot duration_sec is required when cut_range is provided")
        if not (0 <= start < end <= generation):
            raise ValueError("shot cut_range must satisfy 0 <= start < end <= generation_duration_sec")
        if abs(float(end) - float(start) - float(duration)) > 1e-6:
            raise ValueError("shot cut_range length must equal shot duration_sec")
        cut_range = {"start_sec": start, "end_sec": end}
    else:
        if duration is None or generation is None:
            cut_range = None
        else:
            if generation < duration:
                raise ValueError("shot generation_duration_sec must not be shorter than shot duration_sec")
            cut_range = {"start_sec": 0, "end_sec": duration}

    return {
        "duration_sec": duration,
        "generation_duration_sec": generation,
        "cut_range": cut_range,
    }
