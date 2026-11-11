"""film_contact_sheets.py - dense, timestamped contact sheets for visual
segmentation of a finished film.

Cut detection alone is unreliable on dark / cross-faded / fast-montage
sections (measured: cv2 77 vs ffmpeg 54 vs manual 45, only 26 in agreement).
This tool does not try to be clever: it samples the film at a fixed interval,
burns the timecode into every frame, and tiles them so a viewer can read the
film and decide the shot boundaries by looking.

Usage:
  python film_contact_sheets.py <video> --out <dir> [--interval 1.0] [--cols 5]
                               [--rows 4] [--tile-width 320] [--start 0] [--end 0]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys

try:  # 可选视频后端：pip install aigc-agent-studio[video]
    import cv2
except ImportError:  # 缺后端时模块仍可导入，只有入口拒绝运行
    cv2 = None


VIDEO_BACKEND_HINT = "本功能需要视频后端：pip install aigc-agent-studio[video]"


def _require_video_backend():
    missing = [name for name, mod in (("cv2", cv2),) if mod is None]
    if missing:
        print("%s（缺 %s）" % (VIDEO_BACKEND_HINT, ", ".join(missing)), file=sys.stderr)
        return False
    return True



def ts(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"


def main() -> int:
    if not _require_video_backend():
        return 2
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--tile-width", type=int, default=320)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0, help="0 = to the end")
    ap.add_argument("--prefix", default="sheet")
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

    per_sheet = args.cols * args.rows
    tiles: list = []
    sheet_no = 0
    written = []
    t = args.start
    while t < t_end:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, fr = cap.read()
        if not ok:
            break
        h = max(1, int(args.tile_width * fr.shape[0] / fr.shape[1]))
        small = cv2.resize(fr, (args.tile_width, h), interpolation=cv2.INTER_AREA)
        label = ts(t)
        scale = max(0.45, args.tile_width / 640.0)
        cv2.rectangle(small, (0, 0), (int(96 * scale) + 8, int(20 * scale) + 6), (0, 0, 0), -1)
        cv2.putText(small, label, (4, int(16 * scale) + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(small)
        if len(tiles) == per_sheet:
            sheet_no += 1
            grid = _grid(tiles, args.cols, args.rows)
            p = out / f"{args.prefix}_{sheet_no:02d}_{int(args.start):04d}.jpg"
            cv2.imwrite(str(p), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
            written.append(p.name)
            tiles = []
        t += args.interval
    if tiles:
        sheet_no += 1
        grid = _grid(tiles, args.cols, args.rows)
        p = out / f"{args.prefix}_{sheet_no:02d}_{int(args.start):04d}.jpg"
        cv2.imwrite(str(p), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
        written.append(p.name)
    cap.release()
    print(f"duration={duration:.2f}s fps={fps:.3f} interval={args.interval}s sheets={len(written)}")
    for n in written:
        print("  ", n)
    return 0


def _grid(tiles: list, cols: int, rows: int):
    import numpy as np

    h = max(t.shape[0] for t in tiles)
    w = max(t.shape[1] for t in tiles)
    padded = []
    for t in tiles:
        if t.shape[0] != h or t.shape[1] != w:
            t = cv2.copyMakeBorder(
                t, 0, h - t.shape[0], 0, w - t.shape[1], cv2.BORDER_CONSTANT, value=(0, 0, 0)
            )
        padded.append(t)
    while len(padded) < cols * rows:
        padded.append(np.zeros((h, w, 3), dtype=padded[0].dtype))
    sheet_rows = []
    for r in range(rows):
        sheet_rows.append(np.hstack(padded[r * cols:(r + 1) * cols]))
    return np.vstack(sheet_rows)


if __name__ == "__main__":
    raise SystemExit(main())
