#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""numbering —— 交割单编号撞号检查（只读 · 2026-10-07 收编进 scripts/）

★ 为什么有它：三作的交割单按「第 NN 号」编号，编号是**全局检索键**。
  同号两单会让检索静默丢一条（W2 第 45/46/47/58 号、W3 第 01 号都真撞过）。

★ 与原版（`work/numbering.py`）的差别
  原版把四个目录**写死在脚本里**、并要求 cwd 是项目根，且无条件写 `work/numbering.txt`。
  本版：**目录由 `--root` 指定**、默认目录名可用 `--dirs` 覆盖、**默认不落盘**（只打印）。
  **判据不变**：文件名里的「第 N 号」在同一目录内必须唯一。

★ 只读：不联网、不改任何交割单；只在显式给 `--out` 时才写一份报告。

用法：
  python3 scripts/numbering.py --root <项目根>
  python3 scripts/numbering.py --root <项目根> --json [--out report.json]
  python3 scripts/numbering.py --self-test

退出码：0 无撞号 ｜ 1 有撞号 ｜ 2 用法错 ｜ 3 没扫到（≠通过）
"""
from __future__ import print_function

import glob
import io
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3

# 相对 `--root`（项目根，即含 outputs/ 的那一层）；用 `--dirs` 可整体覆盖
DEFAULT_DIRS = ("outputs/00_方法层_跨作品", "outputs/01_弥寿计划_W1",
                "outputs/02_抵达之前_W2", "outputs/03_THE_TURN_W3")
NUM_RE = re.compile(r"第\s*(\d+)\s*号")


def scan(root, dirs):
    """返回 [(dir, {编号: [文件名,…]}), …] —— 只读。"""
    out = []
    for d in dirs:
        path = os.path.join(root, d)
        nums = defaultdict(list)
        if os.path.isdir(path):
            for p in sorted(glob.glob(os.path.join(path, "*.md"))):
                name = os.path.basename(p)
                m = NUM_RE.search(name)
                if m:
                    nums[int(m.group(1))].append(name)
        out.append((d, dict(nums)))
    return out


def report(scan_result):
    lines, payload, total_coll = [], [], 0
    for d, nums in scan_result:
        coll = dict((k, v) for k, v in sorted(nums.items()) if len(v) > 1)
        total_coll += len(coll)
        lines.append("=" * 78)
        lines.append("%s   编号 %s" % (d, sorted(nums)))
        if coll:
            lines.append("  [!] 撞号 %d 组:" % len(coll))
            for k in sorted(coll):
                lines.append("    第%d号:" % k)
                for n in coll[k]:
                    lines.append("      - %s" % n)
        else:
            lines.append("  [OK] 无撞号")
        payload.append({"dir": d, "numbers": sorted(nums),
                        "collisions": dict((str(k), v) for k, v in coll.items())})
    return "\n".join(lines), payload, total_coll


def run(root, dirs):
    if not os.path.isdir(root):
        print("找不到项目根：%s" % root)
        return RC_USAGE, None, None
    res = scan(root, dirs)
    text, payload, coll = report(res)
    if not any(p["numbers"] for p in payload):
        print("四个目录里一个「第 N 号」文件都没扫到")
        return RC_EMPTY, text, payload
    return (RC_FAIL if coll else RC_OK), text, payload


def self_test():
    ok = True
    tmp = tempfile.mkdtemp()
    try:
        d = os.path.join(tmp, DEFAULT_DIRS[0])
        os.makedirs(d)
        for name in ("_单_第45号.md", "_单_第46号.md"):
            io.open(os.path.join(d, name), "w", encoding="utf-8").close()
        rc, _, payload = run(tmp, (DEFAULT_DIRS[0],))
        print("self-test [no-collision] rc=%d expect=%d %s"
              % (rc, RC_OK, "ok" if rc == RC_OK else "MISMATCH"))
        ok = ok and rc == RC_OK
        io.open(os.path.join(d, "_另一单_第46号.md"), "w", encoding="utf-8").close()
        rc, _, payload = run(tmp, (DEFAULT_DIRS[0],))
        hit = payload[0]["collisions"].get("46")
        print("self-test [collision] rc=%d expect=%d hit=%s %s"
              % (rc, RC_FAIL, bool(hit), "ok" if (rc == RC_FAIL and hit) else "MISMATCH"))
        ok = ok and rc == RC_FAIL and bool(hit)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("self-test 通过" if ok else "self-test 失败")
    return RC_OK if ok else RC_FAIL


def main(argv):
    if not argv:
        print(__doc__)
        return RC_USAGE
    if argv[0] in ("--self-test", "-t"):
        return self_test()
    root = None
    dirs = DEFAULT_DIRS
    out_path = None
    as_json = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]; i += 2; continue
        if a == "--dirs" and i + 1 < len(argv):
            dirs = tuple(x for x in argv[i + 1].split(",") if x); i += 2; continue
        if a == "--out" and i + 1 < len(argv):
            out_path = argv[i + 1]; i += 2; continue
        if a == "--json":
            as_json = True; i += 1; continue
        print("未知参数：%s" % a)
        return RC_USAGE
    if not root:
        print("必须给 --root <项目根>")
        return RC_USAGE
    rc, text, payload = run(root, dirs)
    if as_json:
        body = json.dumps({"root": os.path.abspath(root), "dirs": list(dirs),
                           "collisions_total": (None if payload is None else
                                                sum(len(p["collisions"]) for p in payload)),
                           "detail": payload}, ensure_ascii=False, indent=2)
        if out_path:
            with io.open(out_path, "w", encoding="utf-8") as f:
                f.write(body)
            print("已写出编号报告：%s" % out_path)
        else:
            print(body)
    else:
        if text:
            print(text)
        if out_path and text:
            with io.open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            print("已写出编号报告：%s" % out_path)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
