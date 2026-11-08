"""subtitle_bands.py - capture the subtitle / dialogue track of a finished film.

Contact sheets sample whole frames; a subtitle may be absent on the sampled
frame, so dialogue gets lost. This tool crops only the bottom band (where
subtitles sit), samples it densely, and stacks the crops vertically with a
burned timecode, so the spoken/on-screen text can be read in one pass.

Read-only. No LibTV calls.

Usage:
  python subtitle_bands.py <video> --out <dir> [--start 0] [--end 0]
                           [--interval 0.5] [--band 0.16] [--rows 24] [--width 900]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def ts(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


def label(img: np.ndarray, text: str, scale: float) -> np.ndarray:
    cv2.rectangle(img, (0, 0), (int(110 * scale) + 10, int(20 * scale) + 6), (0, 0, 0), -1)
    cv2.putText(img, text, (4, int(16 * scale) + 2),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def content_bounds(frame: np.ndarray, thresh: float = 8.0) -> tuple[int, int]:
    """Return (top, bottom) row bounds of the picture, skipping letterbox bars."""
    rows = frame.mean(axis=(1, 2))
    live = np.nonzero(rows > thresh)[0]
    if len(live) == 0:
        return 0, frame.shape[0]
    return int(live[0]), int(live[-1]) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--band", type=float, default=0.16, help="bottom fraction of the frame")
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--width", type=int, default=900)
    args = ap.parse_args()

    src = Path(args.video)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {src}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if fps else 0.0
    t_end = args.end if args.end > 0 else duration

    rows: list[np.ndarray] = []
    sheets = []
    t = args.start
    while t < t_end:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, fr = cap.read()
        if not ok:
            break
        h, w = fr.shape[:2]
        top, bottom = content_bounds(fr)
        ch = bottom - top
        # crop the bottom slice *of the picture*, not of the letterboxed frame
        band = fr[max(top, bottom - int(ch * args.band)):bottom, :]
        scale = args.width / w
        band = cv2.resize(band, (args.width, max(1, int(band.shape[0] * scale))),
                          interpolation=cv2.INTER_AREA)
        rows.append(label(band, ts(t), max(0.5, scale)))
        if len(rows) == args.rows:
            sheets.append(rows)
            rows = []
        t += args.interval
    if rows:
        sheets.append(rows)
    cap.release()

    names = []
    for i, block in enumerate(sheets, start=1):
        h = max(r.shape[0] for r in block)
        w = max(r.shape[1] for r in block)
        block = [
            r if r.shape[:2] == (h, w)
            else cv2.copyMakeBorder(r, 0, h - r.shape[0], 0, w - r.shape[1],
                                    cv2.BORDER_CONSTANT, value=(0, 0, 0))
            for r in block
        ]
        grid = np.vstack(block)
        p = out / f"subs_{i:02d}.jpg"
        cv2.imwrite(str(p), grid, [cv2.IMWRITE_JPEG_QUALITY, 92])
        names.append(p.name)
    print(f"duration={duration:.2f}s interval={args.interval}s band={args.band} sheets={len(names)}")
    for n in names:
        print("  ", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
