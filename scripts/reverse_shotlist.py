"""reverse_shotlist.py - finished film -> shot list (reverse engineering step 1).

Decodes a video locally (OpenCV), detects hard cuts with an adaptive
median+MAD threshold, enforces a minimum shot length, then writes:

  <out>/shotlist.json    one row per shot: index / start / end / duration / cut_score
  <out>/shotlist.md      human-readable table
  <out>/frames/shot_XXX.jpg  one sampled still per shot
  <out>/probe.json       container-level facts (fps / frames / duration / size)

Read-only with respect to LibTV: nothing is uploaded, generated or ignited.

Usage:
  python reverse_shotlist.py <video path or URL> --out <dir> [--min-shot 0.35]
                             [--width 320] [--mad-k 8] [--abs-min 8]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np


def fetch(url: str, workdir: Path) -> Path:
    name = url.rstrip("/").split("/")[-1].split("?")[0] or "input.mp4"
    dest = workdir / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    workdir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "reverse-shotlist/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def frame_diffs(path: Path, width: int):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    grays: list[np.ndarray] = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        h = max(1, int(width * fr.shape[0] / fr.shape[1]))
        small = cv2.resize(fr, (width, h), interpolation=cv2.INTER_AREA)
        grays.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    cap.release()
    if not grays:
        raise RuntimeError(f"no frames decoded from {path}")
    g = np.stack(grays).astype(np.float32)
    diff = np.zeros(len(g), dtype=np.float32)
    if len(g) > 1:
        diff[1:] = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))
    return fps, total, diff


def detect_cuts(diff: np.ndarray, mad_k: float, abs_min: float) -> list[tuple[int, float]]:
    med = float(np.median(diff))
    mad = float(np.median(np.abs(diff - med)))
    thr = max(abs_min, med + mad_k * (mad + 1e-6))
    raw = [i for i in range(1, len(diff)) if diff[i] > thr]
    cuts: list[tuple[int, float]] = []
    for i in raw:
        lo, hi = max(0, i - 4), min(len(diff), i + 5)
        others = np.delete(diff[lo:hi], i - lo)
        if len(others) == 0 or float(others.max()) < float(diff[i]) * 0.5:
            cuts.append((i, float(diff[i])))
    return cuts


def local_threshold_mask(diff: np.ndarray, window: int, mad_k: float, floor: float) -> np.ndarray:
    """Per-frame threshold from its own neighbourhood.

    A global median+MAD fails on long dark / low-contrast stretches: real cuts
    there sit below the global bar. Comparing each frame-diff against the
    statistics of a local window keeps sensitivity inside quiet sections.
    """
    n = len(diff)
    half = max(2, window // 2)
    padded = np.pad(diff, (half, half), mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(padded, 2 * half + 1)
    med = np.median(win, axis=1)
    mad = np.median(np.abs(win - med[:, None]), axis=1)
    local_thr = med + mad_k * (mad + 1e-6)
    return diff > np.maximum(floor, local_thr)


def detect_cuts_combined(
    diff: np.ndarray, mad_k: float, abs_min: float, window: int
) -> list[tuple[int, float]]:
    """Union of the global rule and the local-adaptive rule, then peak-filter."""
    global_mask = np.zeros(len(diff), dtype=bool)
    med = float(np.median(diff))
    mad = float(np.median(np.abs(diff - med)))
    global_mask[1:] = diff[1:] > max(abs_min, med + mad_k * (mad + 1e-6))

    local_mask = np.zeros(len(diff), dtype=bool)
    if window > 0:
        local_mask[1:] = local_threshold_mask(diff, window, mad_k, abs_min * 0.5)[1:]

    mask = global_mask | local_mask
    cuts: list[tuple[int, float]] = []
    for i in np.nonzero(mask)[0]:
        lo, hi = max(0, i - 4), min(len(diff), i + 5)
        others = np.delete(diff[lo:hi], i - lo)
        if len(others) == 0 or float(others.max()) < float(diff[i]) * 0.5:
            cuts.append((int(i), float(diff[i])))
    return cuts


def enforce_min_shot(cuts: list[tuple[int, float]], fps: float, min_shot: float):
    if fps <= 0:
        return cuts
    min_frames = max(1, int(round(min_shot * fps)))
    kept: list[tuple[int, float]] = []
    for idx, score in cuts:
        if not kept or idx - kept[-1][0] >= min_frames:
            kept.append((idx, score))
        elif score > kept[-1][1]:
            kept[-1] = (idx, score)
    return kept


def sample_frame(cap: cv2.VideoCapture, frame_idx: int, width: int):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, fr = cap.read()
    if not ok:
        return None
    h = max(1, int(width * fr.shape[0] / fr.shape[1]))
    return cv2.resize(fr, (width, h), interpolation=cv2.INTER_AREA)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-shot", type=float, default=0.35)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--mad-k", type=float, default=8.0)
    ap.add_argument("--abs-min", type=float, default=8.0)
    ap.add_argument(
        "--local-window",
        type=int,
        default=49,
        help="local adaptive window in frames (0 disables); fixes dark-section misses",
    )
    ap.add_argument("--frame-out-width", type=int, default=480)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)

    if args.video.startswith(("http://", "https://")):
        src = fetch(args.video, out)
    else:
        src = Path(args.video)
        if not src.exists():
            print(f"missing input: {src}", file=sys.stderr)
            return 2

    fps, total, diff = frame_diffs(src, args.width)
    cuts = enforce_min_shot(
        detect_cuts_combined(diff, args.mad_k, args.abs_min, args.local_window),
        fps,
        args.min_shot,
    )
    n_frames = len(diff)
    duration = n_frames / fps if fps else 0.0

    bounds = [0] + [c[0] for c in cuts] + [n_frames]
    shots = []
    cap = cv2.VideoCapture(str(src))
    for n in range(len(bounds) - 1):
        a, b = bounds[n], bounds[n + 1]
        if b <= a:
            continue
        mid = (a + b) // 2
        img = sample_frame(cap, mid, args.frame_out_width)
        png = frames_dir / f"shot_{len(shots) + 1:03d}.jpg"
        if img is not None:
            cv2.imwrite(str(png), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        shots.append(
            {
                "index": len(shots) + 1,
                "start": round(a / fps, 3),
                "end": round(b / fps, 3),
                "duration": round((b - a) / fps, 3),
                "start_frame": a,
                "end_frame": b,
                "cut_score": round(cuts[n - 1][1], 3) if n > 0 else None,
                "still": png.name,
            }
        )
    cap.release()

    probe = {
        "source": str(src),
        "fps": round(fps, 4),
        "frames": n_frames,
        "reported_frames": total,
        "duration_sec": round(duration, 3),
        "width_sample": args.width,
        "mad_k": args.mad_k,
        "abs_min": args.abs_min,
        "min_shot_sec": args.min_shot,
        "local_window": args.local_window,
        "cut_count": len(cuts),
        "shot_count": len(shots),
    }
    (out / "probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "shotlist.json").write_text(json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 反推镜头表（自动切点）",
        "",
        f"- 源：`{src.name}`",
        f"- 时长：{duration:.2f}s ｜ fps {fps:.3f} ｜ 帧 {n_frames}",
        f"- 检出切点：{len(cuts)} ｜ 镜头数：{len(shots)}",
        "",
        "| # | 入点 | 出点 | 时长 | 切点分数 | 静帧 |",
        "|---|---|---|---|---|---|",
    ]
    for s in shots:
        lines.append(
            f"| {s['index']} | {s['start']:.2f} | {s['end']:.2f} | {s['duration']:.2f} | "
            f"{'' if s['cut_score'] is None else s['cut_score']} | {s['still']} |"
        )
    (out / "shotlist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(probe, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
