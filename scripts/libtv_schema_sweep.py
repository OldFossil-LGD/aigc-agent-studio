#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""libtv_schema_sweep —— **拿随册的模型 schema 集，把门禁的边界层扫一遍**。

为什么要有它（2026-10-16 立）：
  门禁 `libtv_model_rules_gate.py` 有四层（区间 / 收紧 / 素材 / 规则）。
  前两轮用一次性脚本把四层都扫过（**563 个边界探针 + 154 次规则层，0 处不符**），
  但那是**一次性**的——**schema 集刷新之后没人再扫**。
  本脚本把那次扫描固化成**常驻能力**：**`schemas/libtv-models/` 一换，重跑它就再核一遍**。

判据（**期望值取自"模型自己声明的边界"**）：
  · 区间层：`properties.modeType.items[mode] = [lo, hi]` ⟹ **`n=lo`/`n=hi` 放行 · `n=lo-1`/`n=hi+1` 拦**；
  · 收紧层：`*Config` 的 `videoMax`/`imageMax`/`imageMaxWithVideo`/`audioMax` ⟹ **`=max` 放行 · `max+1` 拦**；
  · 素材层：`properties.mediaConstraints` 的 `duration`/`height`/`width`/`longSide`/`shortSide`/`size`/`formats`
    ⟹ **边界内不拦 · 边界外按 `action`（`block`→fail · `warn`→warn）**。
  · 规则层：**不变量**——**ctx 全真（prompt/image/video/audio/media 都有）时，每条 `require` 都满足
    ⟹ 规则层必 `pass`**（`forModeTypes`/`whenHas` 只会"跳过"，`all`/`any` 在全真下都满足）。

**⚠ 这条只证"门与声明一致"，不证"声明与服务端一致"**——后者要真提交（需批准）。

退出码：`0` 零不符 ｜ `1` 有探针不符 ｜ `2` 用法错 ｜ `3` 没扫到（schema 目录不存在或为空，≠ 通过）。
"""
import argparse
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_DIR = os.path.join(ROOT, "schemas", "libtv-models")

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3


def _load_gate():
    """把同目录的门禁当模块载进来——**不复制它的判据**（L2：一个定义）。"""
    spec = importlib.util.spec_from_file_location(
        "libtv_model_rules_gate", os.path.join(HERE, "libtv_model_rules_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _counts(list_key, kind, n):
    c = {"image": 0, "video": 0, "audio": 0}
    if list_key == "mixedList":
        c["image"] = max(n, 0)
    else:
        c[kind] = max(n, 0)
    return c


def sweep_range(g, schemas):
    rows = []
    for key, s in schemas:
        items = (((s.get("properties") or {}).get("modeType") or {}).get("items")) or {}
        for mode, entry in items.items():
            if mode in ("text2video", "text2image"):
                continue  # 这两条在门里是特判，不按区间判
            lo, hi = int(entry[0]), int(entry[1])
            if hi == 0:
                continue  # 占位不可用，门直接判 fail，不属边界语义
            list_key = g.LIST_KEY_BY_MODE_TYPE.get(mode)
            kind = g.LIST_KIND.get(list_key)
            if list_key != "mixedList" and not kind:
                continue
            probes = [(lo, "pass"), (hi, "pass"), (hi + 1, "fail")]
            if lo > 0:
                probes.append((lo - 1, "fail"))
            for n, expect in probes:
                r = g.evaluate_ranges(s, mode, _counts(list_key, kind, n))
                got = r.get("state")
                rows.append({"layer": "range", "model": key, "mode": mode, "n": n,
                             "expect": expect, "got": got, "ok": got == expect})
    return rows


def sweep_configs(g, schemas):
    rows = []
    for key, s in schemas:
        mt = (s.get("properties") or {}).get("modeType") or {}
        for mode, cfgkey in (("mixed2video", "mixed2videoConfig"),
                             ("videoEdit2video", "videoEdit2videoConfig")):
            cfg = mt.get(cfgkey)
            if not isinstance(cfg, dict):
                continue
            if mode == "mixed2video" and mode not in g.MIXED_LIST_PROTOCOL:
                continue
            for field, kind, need_video in (("videoMax", "video", False),
                                            ("imageMax", "image", False),
                                            ("imageMaxWithVideo", "image", True),
                                            ("audioMax", "audio", False)):
                m = cfg.get(field)
                if not isinstance(m, int):
                    continue
                if field == "audioMax" and mode == "videoEdit2video" and not g._is_seedance_25(s):
                    continue  # 门只在 Seedance 2.5 上走这一步
                for n, expect in ((m, "pass"), (m + 1, "fail")):
                    c = {"image": 0, "video": 0, "audio": 0}
                    c[kind] = n
                    if need_video and n > 0:
                        c["video"] = 1  # 该字段只在"有视频"时生效
                    r = g.evaluate_configs(s, mode, c)
                    got = r.get("state")
                    rows.append({"layer": "config", "model": key, "mode": mode, "field": field,
                                 "n": n, "expect": expect, "got": got, "ok": got == expect})
    return rows


def sweep_media(g, schemas):
    rows = []
    for key, s in schemas:
        cs = (s.get("properties") or {}).get("mediaConstraints")
        if not cs:
            continue
        for mode, block in cs.items():
            video = (block or {}).get("video") or {}
            for field in ("duration", "height", "width", "longSide", "shortSide", "size"):
                c = video.get(field)
                if not isinstance(c, dict):
                    continue
                hit = "fail" if c.get("action") == "block" else "warn"
                for label, val, expect in (
                        ("at_min", c.get("min"), "pass"),
                        ("at_max", c.get("max"), "pass"),
                        ("below_min", (c.get("min") - 1) if isinstance(c.get("min"), (int, float)) else None, hit),
                        ("above_max", (c.get("max") + 1) if isinstance(c.get("max"), (int, float)) else None, hit)):
                    if val is None:
                        continue
                    mat = {"url": "https://example.invalid/clip.mp4"}
                    if field == "duration":
                        mat["durationSec"] = val
                    elif field in ("height", "width"):
                        mat[field] = val
                    elif field in ("longSide", "shortSide"):
                        mat["height"], mat["width"] = val, 1
                    elif field == "size":
                        mat["sizeBytes"] = val
                    r = g.evaluate_media(s, mode, [mat])
                    got = r.get("state")
                    rows.append({"layer": "media", "model": key, "mode": mode, "field": field,
                                 "case": label, "expect": expect, "got": got, "ok": got == expect})
            fmt = video.get("formats")
            if isinstance(fmt, dict) and fmt.get("allowed"):
                hit = "fail" if fmt.get("action") == "block" else "warn"
                for label, url, expect in (("allowed_ext", "https://example.invalid/clip.mp4", "pass"),
                                           ("disallowed_ext", "https://example.invalid/clip.avi", hit)):
                    r = g.evaluate_media(s, mode, [{"url": url}])
                    got = r.get("state")
                    rows.append({"layer": "media", "model": key, "mode": mode, "field": "formats",
                                 "case": label, "expect": expect, "got": got, "ok": got == expect})
    return rows


def sweep_rules(g, schemas):
    """第④层：`rules`。**不变量**：**ctx 全真 ⟹ 每条 `require` 都满足 ⟹ 规则层必 `pass`**。

    （`forModeTypes` / `whenHas` 只会"跳过"、不会"拦"；`mode` 是 `all` 或 `any`，
    在"全真"下两者都满足 ⟹ **这一层在"什么都有"时不该拦任何模型**。）
    """
    rows = []
    all_true = {k: True for k in ("prompt", "image", "video", "audio", "media")}
    for key, s in schemas:
        r = g.evaluate(s, dict(all_true), None)
        st = ((r.get("layers") or {}).get("rules") or {}).get("state")
        rows.append({"layer": "rules", "model": key, "case": "all_true",
                     "expect": "pass", "got": st, "ok": st == "pass"})
    return rows


def load_schemas(directory):
    if not os.path.isdir(directory):
        return None
    out = []
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".json") or fn == "_manifest.json":
            continue
        with io.open(os.path.join(directory, fn), encoding="utf-8") as f:
            d = json.load(f)
        s = d.get("schema")
        if isinstance(s, dict):
            out.append((d.get("modelKey") or fn[:-5], s))
    return out


def run(directory):
    schemas = load_schemas(directory)
    if schemas is None:
        print("[SKIP] schema 目录不存在：%s —— **没验到（≠ 通过）**" % directory)
        return RC_EMPTY
    if not schemas:
        print("[SKIP] schema 目录里没有 schema 文件 —— **没验到（≠ 通过）**")
        return RC_EMPTY
    g = _load_gate()
    rows = sweep_range(g, schemas) + sweep_configs(g, schemas) + sweep_media(g, schemas) + sweep_rules(g, schemas)
    bad = [r for r in rows if not r["ok"]]
    by_layer = {}
    for r in rows:
        b = by_layer.setdefault(r["layer"], [0, 0])
        b[0] += 1
        if not r["ok"]:
            b[1] += 1
    print("── 门禁边界扫描（期望值 = 模型自己声明的边界）──")
    print("  schema：**%d 份** · 探针：**%d 个** · 不符：**%d 处**" % (len(schemas), len(rows), len(bad)))
    for layer in ("range", "config", "media", "rules"):
        n, b = by_layer.get(layer, [0, 0])
        print("    %-8s %4d 探针 │ %d 不符" % (layer, n, b))
    for r in bad[:15]:
        print("    ✗ %s" % json.dumps(r, ensure_ascii=False))
    if bad:
        print("  **⚠ 有探针不符 —— 门与 schema 声明不一致，先看是门错了还是 schema 变了。**")
    print("  ★ 这只证「门与声明一致」；「声明与服务端一致」要真提交（需批准）。")
    return RC_FAIL if bad else RC_OK


def _self_test():
    """自检：用合成 schema 验三件事——**不符会被抓到** · **相符不误报** · **空目录记没验到**。"""
    import tempfile
    ok = bad = 0

    def case(name, cond):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s" % name)

    g = _load_gate()
    s_ok = {"properties": {"modeType": {"items": {"image2video": [1, 3]}}}}
    rows = sweep_range(g, [("m", s_ok)])
    case("区间：合规 schema 零不符", all(r["ok"] for r in rows) and len(rows) == 4)
    s_bad = {"properties": {"modeType": {"items": {"image2video": [1, 3]}}}}
    # 人为把门判据换成一个"边界外也放行"的桩，验证扫描会抓到不符
    real = g.evaluate_ranges
    try:
        g.evaluate_ranges = lambda sch, mode, counts: {"state": "pass"}
        rows_bad = sweep_range(g, [("m", s_bad)])
        case("区间：门恒放行时扫描报不符", any(not r["ok"] for r in rows_bad))
    finally:
        g.evaluate_ranges = real
    s_cfg = {"properties": {"modeType": {"mixed2videoConfig": {"videoMax": 2},
                                         "items": {"mixed2video": [1, 5]}}}}
    case("收紧：合规 schema 零不符", all(r["ok"] for r in sweep_configs(g, [("m", s_cfg)])))
    s_media = {"properties": {"mediaConstraints": {"mixed2video": {"video": {
        "duration": {"min": 3, "max": 10, "action": "block"}}}}}}
    case("素材：block 边界内外都判对", all(r["ok"] for r in sweep_media(g, [("m", s_media)])))
    s_rule = {"properties": {}, "rules": [{"require": ["prompt", "media"], "mode": "any"}]}
    case("规则：ctx 全真 ⟹ 规则层 pass", all(r["ok"] for r in sweep_rules(g, [("m", s_rule)])))
    with tempfile.TemporaryDirectory() as td:
        case("空目录 → 记没验到（rc=3）", run(td) == RC_EMPTY)
    print("\n自检：%d 通过 / %d 失败" % (ok, bad))
    return RC_OK if bad == 0 else RC_FAIL


def main(argv):
    ap = argparse.ArgumentParser(description="拿随册 schema 集扫门禁的边界层")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="schema 目录（默认 schemas/libtv-models）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    return run(args.dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
