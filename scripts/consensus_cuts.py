"""consensus_cuts.py - second opinion for reverse-engineered shot boundaries.

Takes the OpenCV shot list produced by reverse_shotlist.py and cross-checks it
against ffmpeg's independent scene detector (bundled with imageio_ffmpeg).
Writes a consensus report and a contact sheet for every disputed boundary so
the boundaries can be confirmed by looking at frames instead of trusting one
algorithm.

Read-only: no LibTV calls, nothing generated or ignited.

Usage:
  python consensus_cuts.py <video> --shots <shotlist.json> --out <dir>
                            [--scene 0.30] [--tol 0.25]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg


def ffmpeg_scene_times(video: Path, scene: float) -> list[float]:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [exe, "-hide_banner", "-i", str(video),
         "-filter:v", f"select='gt(scene,{scene})',showinfo", "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    text = proc.stdout.decode("utf-8", "replace")
    return sorted(float(m) for m in re.findall(r"pts_time:([0-9.]+)", text))


def contact_sheet(video: Path, times: list[float], out: Path, width: int = 240):
    """For each time, one strip: frame-2 / frame-1 / frame / frame+1 (at 30fps)."""
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    strips = []
    for t in times:
        row = []
        for off in (-0.10, 0.0, 0.10):
            f = max(0, int(round((t + off) * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, fr = cap.read()
            if not ok:
                row.append(None)
                continue
            h = max(1, int(width * fr.shape[0] / fr.shape[1]))
            row.append(cv2.resize(fr, (width, h), interpolation=cv2.INTER_AREA))
        if any(r is not None for r in row):
            blank = next((r for r in row if r is not None), None)
            row = [blank if r is None else r for r in row]
            strips.append(cv2.hconcat(row))
    cap.release()
    if not strips:
        return None
    h = max(s.shape[0] for s in strips)
    strips = [s if s.shape[0] == h else cv2.copyMakeBorder(s, 0, h - s.shape[0], 0, 0, cv2.BORDER_CONSTANT) for s in strips]
    grid = cv2.vconcat(strips)
    cv2.imwrite(str(out), grid, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--shots", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scene", type=float, default=0.30)
    ap.add_argument("--tol", type=float, default=0.25)
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    cv2_cuts = [s["start"] for s in shots][1:]
    ff_cuts = ffmpeg_scene_times(video, args.scene)

    def nere(a: float, seq: list[float]) -> bool:
        return any(abs(a - b) <= args.tol for b in seq)

    confirmed = [c for c in cv2_cuts if nere(c, ff_cuts)]
    cv2_only = [c for c in cv2_cuts if not nere(c, ff_cuts)]
    ff_only = [c for c in ff_cuts if not nere(c, cv2_cuts)]

    report = {
        "scene_threshold": args.scene,
        "tolerance_sec": args.tol,
        "cv2_cuts": len(cv2_cuts),
        "ffmpeg_cuts": len(ff_cuts),
        "confirmed": len(confirmed),
        "cv2_only": len(cv2_only),
        "ffmpeg_only": len(ff_only),
        "confirmed_times": [round(c, 3) for c in confirmed],
        "cv2_only_times": [round(c, 3) for c in cv2_only],
        "ffmpeg_only_times": [round(c, 3) for c in ff_only],
    }
    (out / "consensus.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    disputed = sorted(set([round(c, 3) for c in cv2_only] + [round(c, 3) for c in ff_only]))
    if disputed:
        contact_sheet(video, disputed[:24], out / "disputed_sheet.jpg")
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("_times")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
