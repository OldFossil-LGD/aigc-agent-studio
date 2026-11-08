#!/usr/bin/env python3
"""Machine acceptance gate for a finished cut (站 6.7 产物门).

Replaces "看着像" with numbers: container facts via ffprobe, black frames and
silence via ffmpeg filters, hard-cut count via scene detection.

Read-only over local media. No LibTV call, no generation, no upload.

Exit codes: 0 PASS · 1 FAIL · 2 usage · 3 not_verified (no expectation given)
            4 WARN (ffmpeg/ffprobe unavailable — never judged as PASS)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = 0, 1, 2, 3, 4

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

DURATION_TOLERANCE_SEC = 0.35


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def probe(path: str) -> dict | None:
    if not FFPROBE:
        return None
    code, out = run([FFPROBE, "-v", "error", "-print_format", "json",
                     "-show_format", "-show_streams", path])
    if code != 0:
        return None
    data = json.loads(out)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fps = 0.0
    if video and video.get("r_frame_rate", "0/0") != "0/0":
        num, _, den = video["r_frame_rate"].partition("/")
        try:
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
    return {
        "duration": float((data.get("format") or {}).get("duration") or 0.0),
        "width": int(video.get("width") or 0) if video else 0,
        "height": int(video.get("height") or 0) if video else 0,
        "fps": round(fps, 3),
        "video_streams": sum(1 for s in streams if s.get("codec_type") == "video"),
        "audio_streams": len(audio),
        "audio_codecs": [s.get("codec_name") for s in audio],
    }


def black_segments(path: str) -> list[dict]:
    if not FFMPEG:
        return []
    _, out = run([FFMPEG, "-i", path, "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-"])
    rows = []
    for line in out.splitlines():
        if "black_start:" not in line:
            continue
        row = {}
        for key in ("black_start", "black_end", "black_duration"):
            match = re.search(r"%s:([0-9.]+)" % key, line)
            if match:
                row[key] = float(match.group(1))
        if row:
            rows.append(row)
    return rows


def silence_segments(path: str) -> list[dict]:
    if not FFMPEG:
        return []
    _, out = run([FFMPEG, "-i", path, "-af", "silencedetect=noise=-50dB:d=0.5", "-f", "null", "-"])
    rows, current = [], {}
    for line in out.splitlines():
        if "silence_start:" in line:
            match = re.search(r"silence_start:\s*(-?[0-9.]+)", line)
            if match:
                current = {"start": float(match.group(1))}
        elif "silence_end:" in line and current:
            match = re.search(r"silence_end:\s*(-?[0-9.]+)", line)
            duration = re.search(r"silence_duration:\s*(-?[0-9.]+)", line)
            current["end"] = float(match.group(1)) if match else None
            current["duration"] = float(duration.group(1)) if duration else None
            rows.append(current)
            current = {}
    return rows


def hard_cuts(path: str) -> int | None:
    if not FFMPEG:
        return None
    _, out = run([FFMPEG, "-i", path, "-filter:v", "select='gt(scene,0.30)',showinfo", "-f", "null", "-"])
    return len(re.findall(r"pts_time:", out))


def evaluate(path: str, expect: dict) -> dict:
    if not FFPROBE or not FFMPEG:
        return {
            "status": "WARN",
            "exit_code": RC_WARN,
            "failures": [{"code": "FFMPEG_UNAVAILABLE", "ffmpeg": bool(FFMPEG), "ffprobe": bool(FFPROBE)}],
            "message": "ffmpeg/ffprobe 不可用 → 判 WARN（EXIT=4），不判 PASS，也不判 FAIL。",
            "path": path,
        }
    facts = probe(path)
    if facts is None:
        return {"status": "FAIL", "exit_code": RC_FAIL, "path": path,
                "failures": [{"code": "UNREADABLE_MEDIA"}]}
    if not expect:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "path": path, "facts": facts,
                "failures": [{"code": "NO_EXPECTATION_GIVEN"}]}

    blacks = black_segments(path)
    silences = silence_segments(path)
    cuts = hard_cuts(path)
    failures, warnings = [], []

    expected_duration = expect.get("duration")
    if expected_duration is not None:
        delta = abs(facts["duration"] - float(expected_duration))
        if delta > DURATION_TOLERANCE_SEC:
            failures.append({"code": "DURATION_MISMATCH", "expected": expected_duration,
                             "actual": round(facts["duration"], 3), "delta": round(delta, 3),
                             "tolerance": DURATION_TOLERANCE_SEC})

    expected_ratio = expect.get("ratio")
    if expected_ratio and facts["height"]:
        actual_ratio = facts["width"] / facts["height"]
        want_w, _, want_h = str(expected_ratio).partition(":")
        try:
            want = float(want_w) / float(want_h)
        except (ValueError, ZeroDivisionError):
            want = None
        if want and abs(actual_ratio - want) / want > 0.02:
            failures.append({"code": "RATIO_MISMATCH", "expected": expected_ratio,
                             "actual": round(actual_ratio, 4)})

    expected_fps = expect.get("fps")
    if expected_fps and abs(facts["fps"] - float(expected_fps)) > 0.5:
        failures.append({"code": "FPS_MISMATCH", "expected": expected_fps, "actual": facts["fps"]})

    expected_cuts = expect.get("cuts")
    if expected_cuts is not None and cuts is not None:
        if abs(cuts - int(expected_cuts)) > 1:
            failures.append({"code": "CUT_COUNT_MISMATCH", "expected": expected_cuts, "actual": cuts})

    if blacks:
        failures.append({"code": "BLACK_FRAMES", "segments": blacks[:5],
                         "total_sec": round(sum(s.get("black_duration") or 0 for s in blacks), 3)})
    if silences:
        total = sum(s.get("duration") or 0 for s in silences)
        if total >= 1.0:
            failures.append({"code": "SILENCE", "segments": silences[:5], "total_sec": round(total, 3)})
        else:
            warnings.append({"code": "SHORT_SILENCE", "total_sec": round(total, 3)})
    # 平台导出会强制加一条静音 aac，所以"零音轨"不能当交付判据（站 6.6 实测）
    if facts["audio_streams"] == 0:
        warnings.append({"code": "NO_AUDIO_TRACK",
                         "message": "无音轨不等于无声；平台导出通常强制带一条 aac。这条只记 WARN。"})

    return {
        "status": "FAIL" if failures else "PASS",
        "exit_code": RC_FAIL if failures else RC_OK,
        "path": path,
        "facts": facts,
        "cuts": cuts,
        "black_segments": blacks,
        "silence_segments": silences,
        "failures": failures,
        "warnings": warnings,
    }


def verify_review_binding(path: str, record: dict, review: dict | None = None) -> dict:
    """Check receipt integrity against local bytes, not the truth of its observations.

    The four existing review layers and six creative passes remain separate.
    No receipt, including a structurally consistent one, proves that a reviewer
    actually observed this media. This checker never enters reviewed.
    """
    failures, pending = [], []
    result = {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "state": "generated",
              "review_status": "NOT_VERIFIED", "scope": "review_binding_only", "path": path,
              "failures": failures, "pending": pending}
    try:
        digest = hashlib.sha256()
        byte_count = 0
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
                byte_count += len(block)
        actual_hash = digest.hexdigest()
    except OSError:
        pending.append({"code": "MEDIA_NOT_AVAILABLE"})
        return result
    if not byte_count:
        pending.append({"code": "MEDIA_NOT_AVAILABLE"})
        return result
    result["media_sha256"] = actual_hash
    if not isinstance(record, dict):
        failures.append({"code": "INVALID_PRODUCTION_RECORD"})
        record = {}
    if not isinstance(record.get("record_id"), str) or not record.get("record_id"):
        failures.append({"code": "MISSING_RECORD_ID"})
    if type(record.get("version")) is not int or record["version"] < 1:
        failures.append({"code": "INVALID_RECORD_VERSION"})
    if record.get("media_sha256") != actual_hash:
        failures.append({"code": "MEDIA_HASH_MISMATCH"})
    if review is None:
        pending.append({"code": "REVIEW_NOT_AVAILABLE"})
    elif not isinstance(review, dict):
        failures.append({"code": "INVALID_REVIEW_RECEIPT"})
    else:
        if review.get("status") == "FAIL":
            failures.append({"code": "REVIEW_NOT_PASSED", "layer": "summary"})
        elif review.get("status") in ("INCONCLUSIVE", "NOT_VERIFIED"):
            pending.append({"code": "REVIEW_INCONCLUSIVE", "layer": "summary"})
        if review.get("record_id") != record.get("record_id"):
            failures.append({"code": "REVIEW_RECORD_MISMATCH"})
        if type(review.get("version")) is not int or review.get("version") != record.get("version"):
            failures.append({"code": "REVIEW_VERSION_MISMATCH"})
        if "source_revision" in record and review.get("source_revision") != record["source_revision"]:
            failures.append({"code": "REVIEW_SOURCE_REVISION_MISMATCH"})
        if review.get("media_sha256") != actual_hash:
            failures.append({"code": "REVIEW_MEDIA_MISMATCH"})

        def check_item(item, label, allow_na=False):
            if not isinstance(item, dict):
                failures.append({"code": "REVIEW_LAYER_MISSING", "layer": label})
                return
            status = item.get("status")
            if status in ("INCONCLUSIVE", "NOT_VERIFIED"):
                pending.append({"code": "REVIEW_INCONCLUSIVE", "layer": label})
            elif status == "NOT_APPLICABLE" and allow_na:
                if not isinstance(item.get("reason"), str) or not item["reason"].strip():
                    failures.append({"code": "REVIEW_NA_WITHOUT_REASON", "layer": label})
            elif status != "PASS":
                failures.append({"code": "REVIEW_NOT_PASSED", "layer": label})
            elif any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("evidence", "decision")):
                failures.append({"code": "REVIEW_EVIDENCE_MISSING", "layer": label})

        layers = review.get("layers") if isinstance(review.get("layers"), dict) else {}
        for name in ("structure", "instruction", "technical", "creative"):
            check_item(layers.get(name), name)
        creative = layers.get("creative") if isinstance(layers.get("creative"), dict) else {}
        passes = creative.get("passes") if isinstance(creative.get("passes"), list) else []
        numbers = [item.get("pass") for item in passes if isinstance(item, dict)]
        if len(passes) != 6 or any(type(number) is not int for number in numbers) or sorted(numbers) != list(range(1, 7)):
            failures.append({"code": "REVIEW_PASSES_INCOMPLETE"})
        for item in passes:
            check_item(item, "creative.%s" % (item.get("pass") if isinstance(item, dict) else "unknown"), allow_na=True)
        if passes and not any(isinstance(item, dict) and item.get("status") == "PASS" for item in passes):
            pending.append({"code": "NO_CREATIVE_PASS_REVIEWED"})
    if failures:
        result.update(status="FAIL", exit_code=RC_FAIL)
    elif not pending:
        result.update(status="PASS", exit_code=RC_OK)
    return result


def _make(path: Path, args: list[str]) -> bool:
    if not FFMPEG:
        return False
    code, _ = run([FFMPEG, "-y", "-v", "error"] + args + [str(path)])
    return code == 0 and path.is_file()


def self_test() -> int:
    import tempfile
    cases = []
    if not FFMPEG or not FFPROBE:
        print(json.dumps({"self_test": "warn", "reason": "ffmpeg/ffprobe unavailable",
                          "exit_code": RC_WARN}, ensure_ascii=False))
        return RC_WARN
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        good = tmpdir / "good.mp4"
        ok_good = _make(good, ["-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=3",
                               "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"])
        if ok_good:
            result = evaluate(str(good), {"duration": 3, "ratio": "16:9", "fps": 24})
            cases.append(("good_clip_passes", result["status"] == "PASS"))
            cases.append(("good_clip_reports_numbers", result["facts"]["width"] == 320 and result["facts"]["audio_streams"] >= 1))
            wrong = evaluate(str(good), {"duration": 9})
            cases.append(("wrong_duration_fails", any(f["code"] == "DURATION_MISMATCH" for f in wrong["failures"])))
            blind = evaluate(str(good), {})
            cases.append(("no_expectation_not_verified", blind["exit_code"] == RC_EMPTY))

            black = tmpdir / "black.mp4"
            ok_black = _make(black, ["-f", "lavfi", "-i", "color=c=black:size=320x180:rate=24:duration=3",
                                     "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                                     "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
            if ok_black:
                bad = evaluate(str(black), {"duration": 3})
                codes = {f["code"] for f in bad["failures"]}
                cases.append(("black_frames_detected", "BLACK_FRAMES" in codes))
                cases.append(("silence_detected", "SILENCE" in codes))

            four_three = tmpdir / "four_three.mp4"
            if _make(four_three, ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2",
                                  "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                                  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]):
                ratio_result = evaluate(str(four_three), {"ratio": "16:9"})
                cases.append(("ratio_mismatch_detected",
                              any(f["code"] == "RATIO_MISMATCH" for f in ratio_result["failures"])))

            slow = tmpdir / "slow.mp4"
            if _make(slow, ["-f", "lavfi", "-i", "testsrc=size=320x180:rate=12:duration=2",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]):
                fps_result = evaluate(str(slow), {"fps": 24})
                cases.append(("fps_mismatch_detected",
                              any(f["code"] == "FPS_MISMATCH" for f in fps_result["failures"])))

            if ok_good:
                cut_result = evaluate(str(good), {"cuts": 6})
                cases.append(("cut_count_mismatch_detected",
                              any(f["code"] == "CUT_COUNT_MISMATCH" for f in cut_result["failures"])))
    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed and cases else "fail",
                      "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return RC_OK if not failed and cases else RC_FAIL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video")
    parser.add_argument("--expect-duration", type=float)
    parser.add_argument("--expect-ratio")
    parser.add_argument("--expect-fps", type=float)
    parser.add_argument("--expect-cuts", type=int)
    parser.add_argument("--json-out")
    parser.add_argument("--review-record", help="Production Record JSON for offline review binding")
    parser.add_argument("--review-receipt", help="Four-layer review receipt JSON (requires --review-record)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.video:
        parser.error("--video is required unless --self-test")

    expect = {}
    if args.expect_duration is not None:
        expect["duration"] = args.expect_duration
    if args.expect_ratio:
        expect["ratio"] = args.expect_ratio
    if args.expect_fps is not None:
        expect["fps"] = args.expect_fps
    if args.expect_cuts is not None:
        expect["cuts"] = args.expect_cuts

    if args.review_receipt and not args.review_record:
        parser.error("--review-receipt requires --review-record")
    if args.review_record and expect:
        parser.error("--review-record cannot be combined with --expect-*; run technical QC separately")
    if args.review_record:
        record = json.loads(Path(args.review_record).read_text(encoding="utf-8"))
        review = json.loads(Path(args.review_receipt).read_text(encoding="utf-8")) if args.review_receipt else None
        result = verify_review_binding(args.video, record, review)
    else:
        result = evaluate(args.video, expect)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
