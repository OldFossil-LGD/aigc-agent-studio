# -*- coding: utf-8 -*-
"""门禁脚本的公共层（2026-09-15 新建 · 原四脚本；2026-09-16 增 `script_lint.py`，共五个）。

★ 本文件**只新增，不改动任何现有脚本**——这是"消除重复"的安全第一步：
  先把四份各自实现过的公共动作**统一到一处**，再让脚本逐个改为 import 它（逐个验证，见文末《迁移清单》）。

四脚本原本重复实现的东西（体检数据：4 文件 2548 行 / 51 函数）：
    read        4 份   die  2 份（**签名与输出流不一致，属真缺陷**）
    _run        4 份   代码块切分 3 份（**同名不同义，属最危险的重复**）
    数值/区间解析 4 份  退出码常量 4 份
"""
import io
import os
import sys
import re
import tempfile
import contextlib

# ---------- 退出码（原本四个文件各写一遍，取值一致，统一到这里） ----------
RC_OK = 0      # 通过
RC_FAIL = 1    # 未过门禁
RC_USAGE = 2   # 用法错误
RC_EMPTY = 3   # 扫不到可校验的内容（**正常**，不是失败）
RC_WARN = 4    # 结构没坏，但有 WARN 待人工定性


# ---------- 读文件 ----------
def read(path):
    """按 UTF-8 读文本。四脚本原本各有一份完全相同的实现。"""
    with io.open(path, encoding="utf-8") as f:
        return f.read()


# ---------- 报错退出（★ 这里修掉了一处真缺陷） ----------
def die(msg, rc=RC_USAGE, to_stderr=True):
    """报错并退出。

    ★ 原实现不一致（真缺陷）：
      `audit_prompt.py`   → `die(msg, code=RC_USAGE)` 写 **stderr**
      `shotlist_lint.py`  → `die(msg, rc)`（**无默认值**）写 **stdout**
    统一后：**默认写 stderr、默认 RC_USAGE**；
    需要保持旧行为的调用处显式传 `to_stderr=False`（迁移时按脚本逐个对）——
    这样"改一处不改行为"，而不是一次性全改。
    """
    if to_stderr:
        sys.stderr.write(msg + "\n")
    else:
        print(msg)
    sys.exit(rc)


# ---------- 跑一个 cmd 并把它的输出收回来（用于 --self-test） ----------
def run(cmd_fn, text, suffix=".md"):
    """把 text 写进临时文件、跑 cmd_fn(path)，返回 (退出码, 捕获到的 stdout)。

    四脚本原本各有一份等价实现（临时文件 + 重定向 stdout + finally 删除）。
    """
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(text)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_fn(path)
        return rc, buf.getvalue()
    finally:
        os.unlink(path)


# ---------- 代码围栏切分（★ 三份同名不同义，这里**分开命名**） ----------
def blocks_with_flags(text):
    """返回 ([块文本…], 围栏是否成对)。

    ← 对应 `ai_smell_check.split_blocks` 的语义（不收行号）。
    """
    blocks, cur, in_block = [], [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_block:
                blocks.append("\n".join(cur))
                cur = []
            in_block = not in_block
            continue
        if in_block:
            cur.append(line)
    if in_block:
        blocks.append("\n".join(cur))
    return blocks, (not in_block)


def blocks_with_lineno(text):
    """返回 ([(起始行号, 块内容)…], 是否停在未闭合的围栏里)。

    ← 对应 `audit_prompt._split_blocks` 的语义（**要行号**）。
    """
    blocks, cur, start, in_block = [], [], 0, False
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("```"):
            if not in_block:
                in_block, start, cur = True, i + 1, []
            else:
                blocks.append((start, "\n".join(cur)))
                in_block = False
            continue
        if in_block:
            cur.append(line)
    return blocks, in_block


# ---------- 数值与区间解析 ----------
NUM = r"\d+(?:\.\d+)?"
RANGE_PATTERNS = [
    # ★ 顺序有讲究：**`mm:ss` 必须排在"纯数字"之前**。
    #   否则 `00:00-00:04` 会先被数字规则切成 `00-00`（**本层自测抓到的真边界缺陷**）。
    re.compile(r"\d{1,2}:\d{2}\s*(?:[–—~-]|到|至)\s*\d{1,2}:\d{2}"),   # 00:00-00:04
    re.compile(NUM + r"\s*(?:[–—~-]|到|至)\s*" + NUM),                 # 0.0–2.4 / 0-5 / 0到5
]


def to_float(s, default=None):
    """把含数字的字符串取成 float；取不到返回 default。

    ← 对应 `shotlist_lint._to_float` 与 `audit_prompt._to_seconds` 的公共部分
      （后者额外处理 `mm:ss`，见下）。
    """
    m = re.search(NUM, s or "")
    return float(m.group(0)) if m else default


def to_seconds(s, default=None):
    """把 `2.5` / `2.5s` / `00:04` 取成秒。"""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return to_float(s, default)


def first_range(line):
    """取一行里第一个时间区间，返回 (起, 止, 原文) 或 None。"""
    for pat in RANGE_PATTERNS:
        m = pat.search(line or "")
        if m:
            raw = m.group(0)
            nums = re.findall(NUM, raw)
            if len(nums) == 2:
                return to_seconds(nums[0]), to_seconds(nums[1]), raw
            # mm:ss 形态
            parts = re.findall(r"\d{1,2}:\d{2}", raw)
            if len(parts) == 2:
                return to_seconds(parts[0]), to_seconds(parts[1]), raw
    return None


# ---------- 表格行 ----------
def cells(line):
    """把一行 Markdown 表格切成单元格（去首尾竖线与空白）。"""
    s = (line or "").strip()
    if not s.startswith("|"):
        return []
    return [c.strip() for c in s.strip("|").split("|")]


def col_index(header_cells, *keywords):
    """在表头里找同时包含任一组关键词的列号——命中返回下标，否则 -1。"""
    for i, h in enumerate(header_cells):
        if any(k in h for k in keywords):
            return i
    return -1


# ---------- 迁移清单（让脚本逐个改为 import 本模块） ----------
MIGRATION = """
按"影响面从小到大"逐个迁移，**每迁一个就跑一次自检，自检通过数必须与迁前完全一致**：

| 顺序 | 脚本 | 行数 | 迁什么 | 验收判据 |
|---|---|---|---|---|
| 1 | `ai_smell_check.py` | 578 | `read` · `_run`→`run` · `split_blocks`→`blocks_with_flags` | 自检 **29 通过 / 0 失败**（迁前同） |
| 2 | `storyboard_lint.py` | 589 | `read` · `_run`→`run` · `_split_blocks` | 自检 **17 / 0** |
| 3 | `shotlist_lint.py` | 684 | `read` · `die`（★ 显式 `to_stderr=False` 保旧行为）· `_run`→`run` · `_cells`→`cells` · `_col`→`col_index` · `_to_float`→`to_float` · `_timeline_segments` | 自检 **12 / 0** |
| 4 | `audit_prompt.py` | 697 | `read` · `die`（默认行为一致，可直接换）· `_run`→`run` · `_split_blocks`→`blocks_with_lineno` · `_to_seconds`→`to_seconds` · `_first_range`→`first_range` | 自检 **26 / 0** · 且 `index` 与 `blocks` 实跑输出不变 |

**纪律**：① **一次只迁一个脚本**；② **自检数不变才算成功**（这是"功能行为一致"的硬证据）；
③ 迁 `die` 时**保留旧输出流**（shotlist 走 stdout）——**统一签名不等于统一行为**，行为要显式保留。
"""
