#!/usr/bin/env python3
"""Read camera motion and subject motion out of a finished clip — **not from stills**.

Why this exists (E234, 实测 2026-10-12): 静帧只能读**构图 / 景别 / 光色 / 内容**，
读不出**运镜**与**人物调度**。任何人凭静帧写下的"贴地跟随 / 缓慢推近 / 机位固定"
都是推断，不是证据。本脚本把这两件事变成可复算的数字。

方法（全本地，ffmpeg + 纯 Python）：
  · 抽 6 fps、96×54 灰度帧
  · 逐对在 [-8..8] 内搜索使 SAD 最小的**全局平移** → **画面边缘区域**的结果估机位
    （边缘多半是环境），**中央区域**的能量估主体动作
  · 远处小主体在低分辨率下测不到 → 可用 `--roi x,y,w,h`（归一化）提高分辨率复测

用法：
  python scripts/motion_readback.py --video in.mp4 --shots shots.json
  python scripts/motion_readback.py --video in.mp4 --shots shots.json --roi 0.36,0.30,0.18,0.28
  python scripts/motion_readback.py --self-test

shots.json: [{"id":"V1","start":0.0,"end":6.93}, ...]

退出码：0 有读数 · 1 无有效读数 · 2 用法 · 3 读不到视频/帧
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


W, H, FPS, MAX_SHIFT, STRIDE = 96, 54, 6, 8, 3
STATIC_PX_PER_S = 6.0        # 边缘位移低于此值判"机位静止"
SUBJECT_RATIO = 2.0          # 中央能量 / 边缘能量 超过此值判"主体动作为主"


def grab(path: str, start: float, end: float, w: int = W, h: int = H, fps: int = FPS) -> list[bytes]:
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-to", str(end), "-i", path,
           "-vf", "fps=%d,scale=%d:%d,format=gray" % (fps, w, h), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE).stdout
    size = w * h
    return [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]


def sad(a: bytes, b: bytes, dx: int, dy: int, w: int, h: int, region: str) -> float:
    total, count = 0, 0
    bx0, bx1, by0, by1 = int(w * 0.20), int(w * 0.80), int(h * 0.20), int(h * 0.80)
    for y in range(max(0, -dy), min(h, h - dy), STRIDE):
        if region == "border" and by0 <= y <= by1:
            continue
        if region == "center" and not (by0 <= y <= by1):
            continue
        base_a, base_b = y * w, (y + dy) * w + dx
        for x in range(max(0, -dx), min(w, w - dx), STRIDE):
            if region == "border" and bx0 <= x <= bx1:
                continue
            if region == "center" and not (bx0 <= x <= bx1):
                continue
            total += abs(a[base_a + x] - b[base_b + x])
            count += 1
    return total / max(1, count)


def best_shift(a: bytes, b: bytes, w: int, h: int, region: str) -> tuple[int, int]:
    best, best_value = (0, 0), 1e9
    for dy in range(-MAX_SHIFT, MAX_SHIFT + 1):
        for dx in range(-MAX_SHIFT, MAX_SHIFT + 1):
            value = sad(a, b, dx, dy, w, h, region)
            if value < best_value:
                best, best_value = (dx, dy), value
    return best


def analyse(video: str, shots: list[dict], w: int = W, h: int = H, fps: int = FPS) -> dict:
    out = {}
    for shot in shots:
        frames = grab(video, shot["start"], shot["end"], w, h, fps)
        if len(frames) < 2:
            out[shot["id"]] = {"status": "NOT_VERIFIED", "reason": "帧数不足"}
            continue
        pans, tilts, center, border = [], [], [], []
        for i in range(len(frames) - 1):
            a, b = frames[i], frames[i + 1]
            dx, dy = best_shift(a, b, w, h, "border")
            pans.append(dx)
            tilts.append(dy)
            center.append(sad(a, b, 0, 0, w, h, "center"))
            border.append(sad(a, b, 0, 0, w, h, "border"))
        pan = sum(pans) / len(pans) * fps
        tilt = sum(tilts) / len(tilts) * fps
        c = sum(center) / len(center)
        e = sum(border) / len(border)
        camera = "static" if abs(pan) < STATIC_PX_PER_S and abs(tilt) < STATIC_PX_PER_S else "moving"
        subject = "dominant" if c > e * SUBJECT_RATIO else "minor"
        out[shot["id"]] = {
            "status": "measured", "window": [shot["start"], shot["end"]], "frames": len(frames),
            "fps": fps, "scale": [w, h],
            "camera_pan_px_per_s": round(pan, 2), "camera_tilt_px_per_s": round(tilt, 2),
            "camera": camera, "center_energy": round(c, 2), "border_energy": round(e, 2),
            "subject_motion": subject,
            "note": "边界位移估机位（边缘多半是环境）；中央能量估主体。支撑方式（手持/稳定器/轨道）与焦段不可判定。",
        }
    return out


def roi_energy(video: str, start: float, end: float, box) -> dict:
    w, h = 480, 270
    frames = grab(video, start, end, w, h, 12)
    if len(frames) < 2:
        return {"status": "NOT_VERIFIED"}
    x0, y0 = int(w * box[0]), int(h * box[1])
    x1, y1 = int(w * (box[0] + box[2])), int(h * (box[1] + box[3]))
    vals = []
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        total = sum(abs(a[y * w + x] - b[y * w + x]) for y in range(y0, y1) for x in range(x0, x1))
        vals.append(total / max(1, (y1 - y0) * (x1 - x0)))
    return {"status": "measured", "roi": [x0, y0, x1, y1],
            "roi_energy": round(sum(vals) / len(vals), 2), "roi_peak": round(max(vals), 2)}


# ── 相似变换拟合：平移 + 旋转 + 缩放 ──────────────────────────────
# ★ 为什么必须有：只搜平移的估计器会把**环绕/推拉**都近似成平移，
#   于是"环绕上升"会被误报成"横移 + 升降"（2026-10-12 实测被用户当场纠正）。
#   环绕会体现为**显著旋转**；推/拉体现为**缩放偏离 1**；升降/俯仰体现为**纵向平移**。
SAMPLE_STRIDE = 4


def _sample_pairs(a: bytes, b: bytes, w: int, h: int, angle: float, scale: float, dx: int, dy: int) -> float:
    cx, cy = w / 2.0, h / 2.0
    th = math.radians(angle)
    cos_t, sin_t = math.cos(th), math.sin(th)
    total, count = 0, 0
    for y in range(0, h, SAMPLE_STRIDE):
        for x in range(0, w, SAMPLE_STRIDE):
            rel_x, rel_y = x - cx, y - cy
            bx = cx + scale * (cos_t * rel_x - sin_t * rel_y) + dx
            by = cy + scale * (sin_t * rel_x + cos_t * rel_y) + dy
            ix, iy = int(round(bx)), int(round(by))
            if 0 <= ix < w and 0 <= iy < h:
                total += abs(a[y * w + x] - b[iy * w + ix])
                count += 1
    return total / max(1, count)


def similarity_fit(a: bytes, b: bytes, w: int, h: int) -> dict:
    """粗到细搜索 (angle, scale, dx, dy)；返回最优参数与残差。"""
    best = {"angle": 0.0, "scale": 1.0, "dx": 0, "dy": 0, "sad": 1e9}
    for angle in (-6.0, -3.0, 0.0, 3.0, 6.0):
        for scale in (0.94, 0.97, 1.0, 1.03, 1.06):
            for dx in range(-12, 13, 3):
                for dy in range(-12, 13, 3):
                    value = _sample_pairs(a, b, w, h, angle, scale, dx, dy)
                    if value < best["sad"]:
                        best = {"angle": angle, "scale": scale, "dx": dx, "dy": dy, "sad": value}
    base = dict(best)
    for angle in (base["angle"] - 1.5, base["angle"], base["angle"] + 1.5):
        for scale in (base["scale"] - 0.015, base["scale"], base["scale"] + 0.015):
            for dx in range(base["dx"] - 2, base["dx"] + 3):
                for dy in range(base["dy"] - 2, base["dy"] + 3):
                    value = _sample_pairs(a, b, w, h, angle, scale, dx, dy)
                    if value < best["sad"]:
                        best = {"angle": angle, "scale": scale, "dx": dx, "dy": dy, "sad": value}
    best["sad"] = round(best["sad"], 2)
    return best


def move_type(angle_per_s: float, scale_per_s: float, pan: float, tilt: float) -> str:
    """把拟合结果翻成运镜类型（保守：分不清就写"复合/不可判定"）。"""
    parts = []
    if abs(angle_per_s) >= 1.0:
        parts.append("环绕/摇（有旋转）")
    if abs(scale_per_s) >= 0.01:
        parts.append("推近" if scale_per_s > 0 else "拉远")
    if abs(tilt) >= 6 and abs(angle_per_s) < 1.0:
        parts.append("升降/俯仰")
    if abs(pan) >= 6 and abs(angle_per_s) < 1.0:
        parts.append("横移/平摇")
    if not parts:
        return "机位基本静止"
    if len(parts) > 1:
        return "复合运镜：" + " + ".join(parts)
    return parts[0]


def similarity_readback(video: str, shots: list[dict], w: int = 120, h: int = 68, fps: int = 6) -> dict:
    out = {}
    for shot in shots:
        frames = grab(video, shot["start"], shot["end"], w, h, fps)
        if len(frames) < 2:
            out[shot["id"]] = {"status": "NOT_VERIFIED", "reason": "帧数不足"}
            continue
        pairs = [(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
        step = max(1, len(pairs) // 4)
        picked = pairs[::step][:4]
        fits = [similarity_fit(a, b, w, h) for a, b in picked]
        angle = sum(f["angle"] for f in fits) / len(fits) * fps
        scale = sum(f["scale"] - 1.0 for f in fits) / len(fits) * fps
        pan = sum(f["dx"] for f in fits) / len(fits) * fps
        tilt = sum(f["dy"] for f in fits) / len(fits) * fps
        out[shot["id"]] = {
            "status": "measured", "frames": len(frames), "fitted_pairs": len(fits),
            "fps": fps, "scale_px": [w, h],
            "rotation_deg_per_s": round(angle, 2),
            "zoom_per_s": round(scale, 4),
            "pan_px_per_s": round(pan, 2),
            "tilt_px_per_s": round(tilt, 2),
            "move_type": move_type(angle, scale, pan, tilt),
            "caveat": "相似变换只能分到「有无旋转/缩放/平移」；具体支撑与弧线半径不可判定，需人工看片确认。",
        }
    return out


def self_test() -> int:
    cases = []
    ffmpeg_ok = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL).returncode == 0
    if not ffmpeg_ok:
        print(json.dumps({"self_test": "warn", "reason": "ffmpeg unavailable"}, ensure_ascii=False))
        return 3
    with tempfile.TemporaryDirectory() as tmp:
        static = Path(tmp) / "static.mp4"
        moving = Path(tmp) / "moving.mp4"
        rotating = Path(tmp) / "rotating.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "smptebars=size=320x180:duration=2", "-r", "10", str(static)],
                       stdout=subprocess.DEVNULL)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "smptebars=size=640x180:duration=2",
                        "-vf", "crop=320:180:x='t*120'", "-r", "10", str(moving)],
                       stdout=subprocess.DEVNULL)
        # ★ 旋转用例：**没有它，工具漏掉"环绕"时自检照样是绿的**（2026-10-12 实撞）
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "smptebars=size=420x240:duration=2",
                        "-vf", "rotate='t*30*PI/180':fillcolor=black,crop=320:180",
                        "-r", "10", str(rotating)],
                       stdout=subprocess.DEVNULL)
        s = analyse(str(static), [{"id": "S", "start": 0.0, "end": 2.0}])["S"]
        m = analyse(str(moving), [{"id": "M", "start": 0.0, "end": 2.0}])["M"]
        r = similarity_readback(str(rotating), [{"id": "R", "start": 0.0, "end": 2.0}])["R"]
        cases.append(("static_clip_reads_static", s.get("camera") == "static"))
        cases.append(("panning_clip_reads_moving", m.get("camera") == "moving"))
        cases.append(("pan_magnitude_positive", abs(m.get("camera_pan_px_per_s", 0)) > 3))
        cases.append(("rotating_clip_reads_rotation",
                      abs(r.get("rotation_deg_per_s", 0)) > 12))
        cases.append(("rotating_clip_is_not_reported_as_translation_only",
                      "环绕" in (r.get("move_type") or "") or "旋转" in (r.get("move_type") or "")))
    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail",
                      "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video")
    parser.add_argument("--shots", help="shots.json：[{id,start,end}]")
    parser.add_argument("--roi", help="归一化 x,y,w,h，用于远处小主体复测")
    parser.add_argument("--fps", type=int, default=FPS, help="采样帧率（短镜请提高，如 15）")
    parser.add_argument("--scale", default="%dx%d" % (W, H), help="采样尺寸，如 160x90")
    parser.add_argument("--similarity", action="store_true",
                        help="拟合 平移+旋转+缩放（识别环绕/推拉；纯平移估计会把环绕误判成横移）")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.video or not args.shots:
        parser.error("--video and --shots are required unless --self-test")

    shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    if args.similarity:
        result = {"video": args.video, "mode": "similarity", "shots": similarity_readback(args.video, shots)}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        measured = [v for v in result["shots"].values() if v.get("status") == "measured"]
        return 0 if measured else 1

    sw, sh = (int(x) for x in args.scale.lower().split("x"))
    result = {"video": args.video, "shots": analyse(args.video, shots, sw, sh, args.fps)}
    if args.roi:
        box = [float(x) for x in args.roi.split(",")]
        result["roi"] = {shot["id"]: roi_energy(args.video, shot["start"], shot["end"], box)
                         for shot in shots}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    measured = [v for v in result["shots"].values() if v.get("status") == "measured"]
    return 0 if measured else 1


if __name__ == "__main__":
    sys.exit(main())
