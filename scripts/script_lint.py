#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""剧本模块门禁（把「剧本交付」从每次各写各的变成固定契约）

为什么要有它：本库的剧本板块此前只有**建议**（`script-craft.md` 的七件装订、`script-format.md` 的格式规格），
**没有任何工具检查** → 实操中一定会漂 → 症状就是"每次生成的剧本结构不一样、模块缺东少西、
格式时好时坏"。这个脚本把那几条变成**机器可判的门禁**，与 `shotlist_lint.py` 同族。

检查三组（**每一组都必须能被机器判定，不许猜**）：
  A 结构组：按 L0/L1/L2 检查必需模块、顺序不乱（模块规格见 `references/script-module.md`）
  B 格式组：场景标题四要素 · 人物名与场景标题加粗 · 括号不含情绪形容词且 ≤4 词 ·
            对白不用引号 · 简版格式（`人名：台词`）不给过 · 转场滥用
  C 口径组：语速 ≤ 每 1 秒 5 字（时长无关，故对任意时长都成立）· 节拍秒数累加 = 总时长 ·
            交接契约四键齐 · 诊断含"副作用"栏 · 块内无元说明 · 无空话词 · **俗套黑名单**（命中即 WARN，M12 写明「加了什么条件」则放行）

退出码（与其余四个门禁一致）：
  0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN

用法：
  python3 scripts/script_lint.py <剧本.md> [--mode full|body] [--level L0|L1|L2]
  python3 scripts/script_lint.py --self-test

--mode 是什么：
  full = 模块化交付（默认）→ 三组全查，默认 L2 十二模块齐备。L0/L1 显式传 --level
  body = 只发剧本正文（M8 单发）→ 只查对应组的格式，**不查模块齐备**
  两者判据不同；用错模式会得到完全相反的结论（把"单发正文"判成"缺十一个模块"）。

★ 时长无关（E37，2026-09-16）：本 skill 覆盖**任意时长**（15 秒短片 → 长片 → 剧集），
  所以**本脚本不写死任何时长上限**；只查"语速"这类与时长无关的量，
  以及"节拍秒数累加等于声明的总时长"这类**自洽性**。
  任何"60 秒片必须 ≤6 句"式的规则**不许进本脚本**——那是某一档位的容量，不是通用契约。
"""
from __future__ import print_function

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN,  # noqa: E402
                     cells, die, read, run, to_seconds)

# ---------- A 组：十二模块（规格权威源 = references/script-module.md） ----------
MODULES = [
    ("M1", "抬头", ["片名", "时长"]),
    ("M2", "前提", ["命题"]),
    ("M3", "梗概", ["Logline", "梗概"]),
    ("M4", "容量单", ["容量"]),
    ("M5", "结构骨架", ["结构"]),
    ("M6", "人物", ["人物"]),
    ("M7", "场景表", ["场景"]),
    ("M8", "剧本正文", ["正文"]),
    ("M9", "台词与旁白清单", ["台词"]),
    ("M10", "无对白版", ["无对白"]),
    ("M11", "交接契约", ["交接"]),
    ("M12", "诊断记录", ["诊断"]),
]

LEVEL_MODULES = {
    "L0": (1, 2, 4, 5, 6, 7, 8),
    "L1": (1, 2, 3, 4, 5, 6, 7, 8, 9, 11),
    "L2": tuple(range(1, 13)),
}

# ---------- B 组：格式 ----------
# 场景标题：内外景 + 地点 + 连字符 + 时间（四要素）。中英两档都认。
RE_SLUG = re.compile(r"^[ \t]*(\*\*)?[ \t]*(内景|外景|内景兼外景|内外景|外内景|内/外景|外/内景|INT\.?/EXT\.?|EXT\.?/INT\.?|INT\.?|EXT\.?)([ \t]*.*)?$")
TIME_WORDS = ("日", "夜", "晨", "昏", "白天", "黎明", "清晨", "黄昏", "傍晚", "深夜", "连续",
              "稍后", "同日", "翌日", "DAY", "NIGHT", "DAWN", "DUSK", "CONTINUOUS", "LATER",
              "MORNING", "EVENING", "MOMENTS")

# 括号里的情绪形容词（本库明令禁止：括号只放简短动作名词）
EMO_WORDS = ("愤怒", "生气", "悲伤", "难过", "高兴", "开心", "无奈", "痛苦", "激动", "紧张",
             "尴尬", "绝望", "兴奋", "冷漠", "温柔", "得意", "不屑", "焦急", "惊恐", "嘲讽",
             "痛苦地", "冷冷地", "轻轻地", "狠狠地")
RE_PAREN = re.compile(r"[（(]([^）)]{0,30})[）)]")

# 转场词
RE_TRANS = re.compile(r"^[ \t]*(淡入|淡出|切至|叠化|划入|划出|CUT TO|DISSOLVE TO|FADE IN|FADE OUT|SMASH CUT|MATCH CUT)")

# 简版格式残留（`人名：台词`）——脚本会把它判出来，提示改用标准档
RE_SIMPLE = re.compile(r"^[ \t]*(\*\*)?[\u4e00-\u9fa5A-Za-z·]{1,6}(\*\*)?[ \t]*[：:][ \t]*\S")

# 块内元说明（与 ai_smell_check 的 FAIL 级同族；这里只取**最不会误伤**的一小撮）
META_BAD = ("（改成", "（替换", "（这里", "（按需", "另注：", "注：", "*可选*", "（可选", "待定", "TBD")

# 空话词（提示词黑名单的同族；剧本正文里同样不该出现）
HYPE = ("电影感", "高级感", "大片感", "震撼", "唯美", "细腻", "质感十足", "氛围感拉满")

# 俗套黑名单（drama-plotcraft.md §4 的"致命档"里**最不会被误伤**的一小撮）。
# ★ 判 WARN 不判 FAIL：黑名单不是禁止表，是"必须付代价才能用"的表——
#   用了就要在 M12 写明「加了什么条件」；写了条件就放行（见 check 处的分流）。
CLICHE = ("原来一切都是梦", "一切都是梦", "原来是梦", "其实早就死了", "原来他早就死了",
          "其实他已经死了", "都是幻觉", "全是幻觉", "只是一场幻觉", "猛地惊醒",
          "突然下起了大雨", "被诊断出绝症", "得了绝症", "一场车祸", "车祸夺走了",
          "原来这只是一场游戏", "这就是人生")

# 语速上限（判据权威源：SKILL.md 第一步 —— 中文 3.5–5 字/秒）
MAX_CPS = 5.0

# 括号长度上限（4 个词；中文按字数近似折算为 8 字）
MAX_PAREN_CHARS = 8

# ---------- 交接契约四键 / 诊断必填 ----------
CONTRACT_KEYS = ("scene", "open_state", "close_state", "hard_facts")


def _bold(line):
    return "**" in line


def _cn_len(s):
    """数中文与英文词混排时的"字数"：中文字符 1 个算 1，连续的英文/数字串算 1。"""
    s = re.sub(r"[\s，。！？、；：（）()\[\]【】\*“”‘’「」]", "", s or "")
    return len(re.findall(r"[\u4e00-\u9fa5]", s)) + len(re.findall(r"[A-Za-z0-9]+", s))


def _modules(text):
    """抽出出现的模块编号与顺序。

    ★ 只在**行首**认模块标记（2026-09-16 实测抓到的真误报）：
      上一版允许"行内任何位置出现 M\\d"＋"该行含粗体/是表格行"即算命中，
      结果**正文与说明里对模块的顺带引用会被当成本模块出现**——
      实测《代哭》一稿报出顺序 `M1→M2→M8→M3→M4→M12→…`（M4 的说明里写了"M12"、
      M8 被别的行内引用抢先命中），把一份顺序完全正确的稿判成"顺序乱"。
      判据：**模块标记必须处在行首**（标题 `## M8 剧本正文` / 表格首格 `| M8 |` / 加粗 `**M8 …**`）。
    """
    found = []
    pats = (r"^#{1,6}[ \t]*\**M(\d{1,2})\b",
            r"^\|[ \t]*\**M(\d{1,2})\b",
            r"^[ \t]*\**M(\d{1,2})\b")
    for i, ln in enumerate(text.split("\n"), 1):
        for p in pats:
            m = re.match(p, ln)
            if not m:
                continue
            n = int(m.group(1))
            if 1 <= n <= 12 and n not in [x for x, _ in found]:
                found.append((n, "第 %d 行 %s" % (i, ln.strip()[:40])))
            break
    return found


def _body_span(lines):
    """圈出「剧本正文」那一段的下标区间 [start, end)。

    ★ 为什么必须圈段：正文之外全是**键值型元信息**（`片名：…`、`模型：…`、`命中：无`、
      `Logline：…`），它们天生就是「名字 + 冒号」，与简版格式「人名：台词」**字形相同**。
      不圈段就会把抬头行成排误报成"用了简版格式"（自检抓到的真误报）。
      找不到正文标题时，退化为"从第一条场景标题起、到下一个标题止"。
    """
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^#{1,6}[ \t]*\**M?8?[^#\n]*剧本正文", ln) or re.match(r"^#{1,6}[ \t]*\**M8\b", ln):
            start = i + 1
            break
    if start is None:
        for i, ln in enumerate(lines):
            if RE_SLUG.match(ln):
                start = i
                break
    if start is None:
        return (0, 0)
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^#{1,6}[ \t]", lines[j]):
            end = j
            break
    return (start, end)


def _density(text, b0, b1, total):
    """算「正文密度」＝ M8 正文字数 ÷ 成片分钟数。

    ★ 为什么要这条检查（2026-09-16 实测踩到）：本库的「3.5–5 字/秒」**只约束对白与旁白**，
      但交接时极易被误用成"整篇都要省" → 15 分钟的稿子正文只写约 900 字，
      **通篇一段一行 = 提纲，不是剧本**。《代哭》初稿即如此，用户当场指出"正文太过简单"。
      判据：**≥600 秒的稿子**低于 400 字/分钟判 FAIL（<600 秒的短片稿主要工作量在分镜，
      故不在此处卡，避免误伤）。
    """
    if total is None or total < 600 or b1 <= b0:
        return None
    body = "\n".join(text.split("\n")[b0:b1])
    chars = _cn_len(body)
    per_min = chars / (total / 60.0)
    return chars, per_min


def lint_full(text, level="L2"):
    """返回 (fails, warns, blank, infos)。

    ★ 为什么把"没扫到"与"信息提示"分成两个通道（自检抓到的真缺陷）：
      原先两者共用一个 notes 列表 → 「命中黑名单但已写明条件 → 放行」这种**信息提示**
      会把退出码拖成 `3`（没扫到）。而 3 的语义是"**没验到**"，与"验过且放行"完全相反。
      判据：**只有"什么都没扫到"才能进 blank（→ 3）；凡是"扫到了并给出结论"一律进 infos。**
    """
    required = LEVEL_MODULES[level]
    fails, warns, blank, infos = [], [], [], []

    # ---------- A 组：模块齐备与顺序 ----------
    lines = text.split("\n")
    has_slug = any(RE_SLUG.match(ln) for ln in lines)
    found = _modules(text)
    nums = [n for n, _ in found]
    if not nums and not has_slug:
        return [], [], ["没扫到模块标记，也没扫到场景标题"], []
    if level == "L0" and "本稿为 L0 可拍最小版" not in text:
        fails.append("L0 交付必须显式标注「本稿为 L0 可拍最小版」")
    if not nums:
        # 有场景标题、却没有模块标记：**完整交付缺全部模块**，是 FAIL。
        # （body 模式在 lint_body 里按前缀把这条丢掉——单发正文本来就不该有模块。）
        fails.append("模块缺失：未检出任何 M1–M12 模块标记（%s 必须包含 %s）"
                     % (level, "、".join("M%d" % n for n in required)))
    else:
        missing = [code for code, _, _ in MODULES
                   if int(code[1:]) in required and int(code[1:]) not in nums]
        if missing:
            fails.append("模块缺失：%s（十二模块规格见 script-module.md）" % "、".join(missing))
        if nums != sorted(nums):
            fails.append("模块顺序乱：出现顺序 %s，必须 M1→M12 递增" % "→".join("M%d" % n for n in nums))

    # ---------- B 组：格式 ----------
    b0, b1 = _body_span(lines)
    slug_count = 0
    for i, ln in enumerate(lines, 1):
        m = RE_SLUG.match(ln)
        if not m:
            continue
        slug_count += 1
        head = (m.group(2) or "").upper()
        is_en = head.startswith("INT") or head.startswith("EXT")
        body = ln
        if "-" not in body and "－" not in body:
            fails.append("第 %d 行 场景标题缺连字符（四要素：内外景 / 地点 / 连字符 / 时间）：%s" % (i, ln.strip()[:40]))
        if not any(t in body for t in TIME_WORDS):
            fails.append("第 %d 行 场景标题缺时间（日 / 夜 / 连续…）：%s" % (i, ln.strip()[:40]))
        if not is_en and not _bold(ln):
            fails.append("第 %d 行 中文档场景标题未加粗（中文用加粗代替英文全大写）：%s" % (i, ln.strip()[:40]))

    for i, ln in enumerate(lines, 1):
        # ★ 跳过"元信息形态"的行（表格行 / 列表项 / 引用 / 标题）：这些行出现在模块外壳里
        #   （M1 抬头、M4 容量单、M7 场景表、M12 诊断…），天生带括号与形容词，与正文括号不是一回事。
        #   实测拿规格文件当输入会吐 27 条 WARN——**误报比漏报更隐蔽（E23）**，故按行形态收窄。
        if ln.lstrip().startswith(("|", "-", "*", ">", "#", "+")):
            continue
        # ★ 再收窄一层（2026-09-16 补）：**括号是剧本正文的元素**，只在正文区判。
        #   模块外壳里的括号（如「15 拍表（完整档）」）是说明文字，不该按"括号 ≤4 词"卡。
        in_body = (b0 <= i - 1 < b1)
        if not in_body:
            continue
        for pm in RE_PAREN.finditer(ln):
            inner = pm.group(1)
            for w in EMO_WORDS:
                if w in inner:
                    fails.append("第 %d 行 括号里有情绪形容词「%s」——括号只放简短动作名词：%s"
                                 % (i, w, ln.strip()[:40]))
                    break
            if _cn_len(inner) > MAX_PAREN_CHARS:
                warns.append("第 %d 行 括号过长（%d 字，上限 %d）：%s"
                             % (i, _cn_len(inner), MAX_PAREN_CHARS, ln.strip()[:40]))
        if RE_SIMPLE.match(ln) and b0 <= i - 1 < b1:
            warns.append("第 %d 行 用了简版格式「人名：台词」——交付请改标准档（人物名独占一行、对白居中）：%s"
                         % (i, ln.strip()[:40]))

    trans = [ln for ln in lines if RE_TRANS.match(ln)]
    if slug_count >= 4 and len(trans) > max(1, slug_count // 2):
        warns.append("转场 %d 处 / 场景 %d 个——现代剧本极少写转场（切是默认的），只在转法本身有意义时写"
                     % (len(trans), slug_count))

    # ---------- C 组：口径 ----------
    # 语速：只认「字数 ÷ 秒数」这种可算的写法
    for i, ln in enumerate(lines, 1):
        if not ln.strip().startswith("|"):
            continue
        c = cells(ln)
        if len(c) < 3:
            continue
        # 找一列像"字数"、一列像"秒数"
        for j in range(len(c) - 1):
            wc = re.fullmatch(r"(\d{1,3})\s*字?", c[j])
            sec = re.fullmatch(r"(\d{1,2}(?:\.\d)?)\s*(?:秒|s)?", c[j + 1])
            if wc and sec:
                w, s = int(wc.group(1)), float(sec.group(1))
                if s > 0 and w / s > MAX_CPS:
                    fails.append("第 %d 行 语速超限：%d 字 / %.1f 秒 = %.2f 字每秒 > 上限 %.1f"
                                 % (i, w, s, w / s, MAX_CPS))
                break

    # 节拍秒数累加 = 声明的总时长（只在能解析到 ≥2 个区间时判，否则只提示）
    total = None
    m = re.search(r"总时长[^\d]{0,6}(\d{1,4})\s*(?:秒|s)", text)
    if m:
        total = float(m.group(1))
    spans = re.findall(r"(\d{1,2}:\d{2})\s*[–—~-]\s*(\d{1,2}:\d{2})", text)
    if total is not None and len(spans) >= 2:
        acc = sum(to_seconds(b, 0) - to_seconds(a, 0) for a, b in spans)
        if abs(acc - total) > 1.0:
            fails.append("节拍秒数累加 %.1f 秒 ≠ 声明总时长 %.1f 秒（无空档、无重叠是硬判据）" % (acc, total))
    elif total is None:
        warns.append("没找到「总时长 N 秒」——容量单（M4）必须写死总时长")

    # 交接契约四键 —— ★ **逐场判**（不是整篇判）：契约是"每一场都要写全四键"，
    #   整篇判会漏掉"某一场少写了 close_state"这种最常见的缺项（自检抓到的真缺陷）。
    if 11 in nums or (level == "L2" and "交接契约" in text):
        scene_lines = [(i, ln) for i, ln in enumerate(lines, 1)
                       if re.match(r"^[ \t]*[-*]?[ \t]*scene\b", ln, re.I)]
        if not scene_lines:
            fails.append("交接契约（M11）里没有逐场的 scene 行——每场一行，四键全要：%s"
                         % " / ".join(CONTRACT_KEYS))
        for i, ln in scene_lines:
            low_line = ln.lower()
            lack = [k for k in CONTRACT_KEYS if k not in low_line]
            if lack:
                fails.append("第 %d 行 交接契约缺键：%s（每场四键全要）" % (i, "、".join(lack)))

    # 诊断含"副作用"
    if 12 in nums or (level == "L2" and "诊断" in text):
        if "副作用" not in text:
            fails.append("诊断记录（M12）缺「副作用」栏——任何结构改动都会把问题推去别处，此栏不许空")

    # 密度组：正文是不是提纲（只对 ≥600 秒的稿子生效）
    d = _density(text, b0, b1, total)
    if d:
        chars, per_min = d
        if per_min < 400:
            fails.append("正文密度 %.0f 字/分钟（正文 %d 字 / %.0f 秒）——**低于 400 是提纲，不是剧本**："
                         "动作行不受 3.5–5 字/秒 约束，动作才是页面主体（script-format.md §2.1）"
                         % (per_min, chars, total))
        elif per_min < 500:
            warns.append("正文密度 %.0f 字/分钟（正文 %d 字 / %.0f 秒）——偏薄，合格线是 ≥500"
                         % (per_min, chars, total))

    # 俗套黑名单：命中即 WARN；**但 M12 里写明「加了什么条件」就放行**——
    # 这条分流是刻意的：黑名单管的是"不许无代价地用"，不是"不许用"。
    hits = sorted(set(w for w in CLICHE if w in text))
    if hits:
        shown = "、".join(hits[:3]) + ("（等 %d 处）" % len(hits) if len(hits) > 3 else "")
        if "加了什么条件" in text:
            infos.append("命中俗套黑名单 %s，但 M12 已写明「加了什么条件」→ 放行" % shown)
        else:
            warns.append("命中俗套黑名单：%s —— 要么删，要么在 M12 里写明「加了什么条件」（drama-plotcraft.md §4）" % shown)

    # 块内元说明 / 空话词（同样按行形态收窄：表格行与列表项属模块外壳，不是正文）
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith(("|", "-", "*", ">", "#", "+")):
            continue
        for w in META_BAD:
            if w in ln:
                fails.append("第 %d 行 块内元说明「%s」（会被当正文读）：%s" % (i, w, ln.strip()[:40]))
        for w in HYPE:
            if w in ln:
                warns.append("第 %d 行 空话词「%s」——换成可测约束：%s" % (i, w, ln.strip()[:40]))

    return fails, warns, blank, infos


def lint_body(text):
    """只查正文（M8 单发）：跳过模块齐备，其余 B/C 组照查。"""
    slug = [ln for ln in text.split("\n") if RE_SLUG.match(ln)]
    if not slug:
        return [], [], ["没扫到场景标题"], []
    # 复用 full 的格式与口径检查；模块类结论与"总时长"在正文模式下不适用，全部丢掉
    f2, w2, _blank, infos = lint_full(text)
    drop = ("模块缺失", "模块顺序乱", "没找到「总时长")
    fails = [x for x in f2 if not any(d in x for d in drop)]
    warns = [x for x in w2 if not any(d in x for d in drop)]
    return fails, warns, [], infos


def lint(path, mode="full", level="L2"):
    text = read(path)
    if mode == "full":
        fails, warns, blank, infos = lint_full(text, level)
    else:
        fails, warns, blank, infos = lint_body(text)

    print("=" * 70)
    print("文件：%s　模式：%s" % (os.path.basename(path), mode))
    if mode == "full":
        print("交付档位：%s" % level)
    print("=" * 70)
    for n in blank + infos:
        print("  [INFO] %s" % n)
    for w in warns:
        print("  [WARN] %s" % w)
    for f in fails:
        print("  [FAIL] %s" % f)
    print("-" * 70)
    if not fails and not warns and not blank and not infos:
        print("全过：模块齐备、格式合规、口径自洽。")
    elif not fails and not warns:
        print("无 FAIL / 无 WARN。另注：只有上面写着「没扫到」的 INFO 才算没验到。")
    else:
        print("FAIL %d ｜ WARN %d" % (len(fails), len(warns)))

    if blank and not fails and not warns:
        return RC_EMPTY
    if fails:
        return RC_FAIL
    if warns:
        return RC_WARN
    return RC_OK


# ==================== 自检 ====================
GOOD = """# 剧本（M1–M12 · 中文适配档）

## M1 抬头
片名：夜班 ｜ 总时长 60 秒 ｜ 画幅 16:9 ｜ 版式档：B 中文工作版

## M2 前提
她以为自己在替别人守夜，其实守的是自己不敢关的那盏灯。

## M3 梗概
Logline：一个便利店夜班店员用一个不肯卖的商品，等一个不会来的人。

## M4 容量单
总时长 60 秒 ｜ 拍数 5 ｜ 反转 1 ｜ 场数 2 ｜ 台词总量 ≤70 字

## M5 结构骨架
模型：故事圈 8 步（折叠为 5 拍）

| 拍 | 秒 | 功能 |
|---|---|---|
| ① | 00:00-00:12 | 建置与钩子 |
| ② | 00:12-00:26 | 主动选择 |
| ③ | 00:26-00:40 | 转折 |
| ④ | 00:40-00:52 | 谷底 |
| ⑤ | 00:52-01:00 | 支付 |

## M6 人物
林默：外在目标 卖掉那盒过期的糖；内在需求 承认自己在等；缺陷 不肯关灯；谎言「不麻烦别人就没人能伤我」；弧光型 C。

## M7 场景表

| 场 | 内外景 | 地点 | 时间 | 功能 | 进 → 出 |
|---|---|---|---|---|---|
| S1 | 内景 | 便利店 | 夜 | 建立与钩子 | 常态 → 裂缝 |
| S2 | 外景 | 便利店门口 | 连续 | 支付 | 停留 → 松手 |

## M8 剧本正文

**内景 便利店 - 夜**

冷柜的压缩机停了一下，又响起来。林默（32 岁）站在冷柜前，指间夹着一张没有递出去的纸币。

　　　　　　　林默
　　　（没有回头）
　　　结账。

　　　　　　　店员
　　　这个不卖。

**切至**

**外景 便利店门口 - 连续**

林默站在台阶上，没有走。

## M9 台词与旁白清单

| 说话人 | 台词 | 所在场 | 字数 | 秒数 |
|---|---|---|---|---|
| 林默 | 结账。 | S1 | 2 | 1.0 |
| 店员 | 这个不卖。 | S1 | 4 | 1.5 |

旁白：无

## M10 无对白版
1 冷柜的光在动 2 纸币被对折 3 店员摇头 4 门开了又关 5 台阶上有人站着

## M11 交接契约
scene S1 · open_state 冷柜灯亮着，他站在门前 · close_state 纸币被折过两次 · hard_facts 恰好两人、一盒糖、一盒过期糖不能被卖出
scene S2 · open_state 门在身后关上 · close_state 他还站着 · hard_facts 无台词、街道空

## M12 诊断记录
命中：无 ｜ 最小改动：把"他说了什么"改成"他折了几次" ｜ 副作用：信息量下降，靠折纸次数补 ｜ 只改一个变量：折纸次数
"""

MISS_MODULE = GOOD.replace("## M9 台词与旁白清单", "## 台词清单")

DISORDER = GOOD.replace("## M5 结构骨架", "## M9 结构骨架").replace("## M9 台词与旁白清单", "## M5 台词与旁白清单")

# ★ 配对用例（2026-09-16 实测误报的回归锁）：**行内顺带引用模块号，不算模块出现**。
#   实测《代哭》一稿因 M4 的说明里写了"M12"而被判"顺序乱"；只修不放用例 = 下次还会复发。
INLINE_MENTION = GOOD.replace(
    "## M4 容量单", "## M4 容量单（数值口径的回看见 M12 的副作用栏）").replace(
    "## M12 诊断记录", "## M12 诊断记录（本栏回看 M4 与 M8）")

SLUG_NO_TIME = GOOD.replace("**内景 便利店 - 夜**", "**内景 便利店**")

SLUG_NO_DASH = GOOD.replace("**内景 便利店 - 夜**", "**内景 便利店 夜**")

SLUG_NOT_BOLD = GOOD.replace("**外景 便利店门口 - 连续**", "外景 便利店门口 - 连续")

EMO_PAREN = GOOD.replace("（没有回头）", "（愤怒地）")

LONG_PAREN = GOOD.replace("（没有回头）", "（他慢慢转过身去看向门外的那条街）")

FAST_SPEECH = GOOD.replace("| 店员 | 这个不卖。 | S1 | 4 | 1.5 |", "| 店员 | 这个我真的不能卖给你你走吧。 | S1 | 14 | 1.0 |")

SIMPLE_FMT = re.sub(r"\n[ \t\u3000]*林默\n[ \t\u3000]*（没有回头）\n[ \t\u3000]*结账。", "\n林默：结账。", GOOD)

META_LEAK = GOOD.replace("冷柜的压缩机停了一下，又响起来。", "冷柜的压缩机停了一下（改成你想要的音效）。")

HYPE_WORD = GOOD.replace("林默站在台阶上，没有走。", "林默站在台阶上，画面充满电影感的孤独。")

NO_CONTRACT = GOOD.replace("close_state 他还站着 · ", "")

NO_SIDE_EFFECT = GOOD.replace("｜ 副作用：信息量下降，靠折纸次数补", "")

BAD_TOTAL = GOOD.replace("| ⑤ | 00:52-01:00 | 支付 |", "| ⑤ | 00:52-01:20 | 支付 |")

# 俗套黑名单两条（配对：证明"命中报"与"写了条件放行"都活着）
CLICHE_NO_COND = GOOD.replace("林默站在台阶上，没有走。", "林默站在台阶上，原来一切都是梦。")
CLICHE_WITH_COND = GOOD.replace(
    "林默站在台阶上，没有走。", "林默站在台阶上，原来一切都是梦。").replace(
    "命中：无", "命中：「一切都是梦」式捷径 ｜ 加了什么条件：梦只发生在他关灯后的三秒里")

# ★ 密度组两条配对用例（2026-09-16 补）：fixture 用**重复句在运行时生成**，
#   否则要在源码里塞几千字。《代哭》初稿就是这个病：15 分钟只写约 900 字正文。
NINE_HEAD = GOOD.replace("总时长 60 秒", "总时长 900 秒").replace(
    "| ① | 00:00-00:12 | 建置与钩子 |\n| ② | 00:12-00:26 | 主动选择 |\n| ③ | 00:26-00:40 | 转折 |\n| ④ | 00:40-00:52 | 谷底 |\n| ⑤ | 00:52-01:00 | 支付 |",
    "| ① | 00:00-03:00 | 建置与钩子 |\n| ② | 03:00-06:00 | 主动选择 |\n| ③ | 06:00-10:00 | 转折 |\n| ④ | 10:00-13:00 | 谷底 |\n| ⑤ | 13:00-15:00 | 支付 |")
_ONELINE = "他站在门口。走廊很长。灯光从上方落下来，影子贴在地面上。" * 800
DENSE_OK = NINE_HEAD.replace("## M9 台词与旁白清单", _ONELINE + "\n\n## M9 台词与旁白清单")
THIN_BODY = NINE_HEAD.replace("## M9 台词与旁白清单", "他进门。\n\n## M9 台词与旁白清单")

EMPTY = "# 随便一个文件\n\n这里没有剧本模块，也没有场景标题。\n"

BODY_ONLY = """**内景 便利店 - 夜**

冷柜的压缩机停了一下，又响起来。林默（32 岁）站在冷柜前。

　　　　　　　林默
　　　（没有回头）
　　　结账。

**切至**

**外景 便利店门口 - 连续**

林默站在台阶上，没有走。
"""


def cmd_self_test():
    print("自检：script_lint")
    cases = [
        ("lint·十二模块齐备 + 格式合规 + 口径自洽 → 0", GOOD, "full", RC_OK),
        ("lint·缺一个模块（M9）→ FAIL", MISS_MODULE, "full", RC_FAIL),
        ("lint·模块顺序乱 → FAIL", DISORDER, "full", RC_FAIL),
        ("lint·**行内**顺带引用模块号（如 M4 的说明里提到 M12）→ 不算顺序乱（0）",
         INLINE_MENTION, "full", RC_OK),
        ("lint·场景标题缺时间 → FAIL", SLUG_NO_TIME, "full", RC_FAIL),
        ("lint·场景标题缺连字符 → FAIL", SLUG_NO_DASH, "full", RC_FAIL),
        ("lint·中文档场景标题未加粗 → FAIL", SLUG_NOT_BOLD, "full", RC_FAIL),
        ("lint·括号里有情绪形容词 → FAIL", EMO_PAREN, "full", RC_FAIL),
        ("lint·括号过长 → WARN", LONG_PAREN, "full", RC_WARN),
        ("lint·语速超 5 字每秒 → FAIL", FAST_SPEECH, "full", RC_FAIL),
        ("lint·简版格式「人名：台词」→ WARN", SIMPLE_FMT, "full", RC_WARN),
        ("lint·块内元说明 → FAIL", META_LEAK, "full", RC_FAIL),
        ("lint·空话词（电影感）→ WARN", HYPE_WORD, "full", RC_WARN),
        ("lint·交接契约缺 close_state → FAIL", NO_CONTRACT, "full", RC_FAIL),
        ("lint·诊断缺「副作用」栏 → FAIL", NO_SIDE_EFFECT, "full", RC_FAIL),
        ("lint·节拍秒数累加 ≠ 总时长 → FAIL", BAD_TOTAL, "full", RC_FAIL),
        ("lint·命中俗套黑名单且未写条件 → WARN", CLICHE_NO_COND, "full", RC_WARN),
        ("lint·命中黑名单但 M12 写了「加了什么条件」→ 放行（0）", CLICHE_WITH_COND, "full", RC_OK),
        ("lint·≥600 秒的稿子正文密度达标（≥500 字/分钟）→ 0", DENSE_OK, "full", RC_OK),
        ("lint·≥600 秒的稿子正文过薄（<400 字/分钟＝提纲）→ FAIL", THIN_BODY, "full", RC_FAIL),
        ("lint·没有模块标记 → 3（没扫到 ≠ 通过）", EMPTY, "full", RC_EMPTY),
        ("lint·body 模式（单发正文）→ 0", BODY_ONLY, "body", RC_OK),
        ("lint·body 模式也要查格式（正文缺时间 → FAIL）",
         BODY_ONLY.replace("**内景 便利店 - 夜**", "**内景 便利店**"), "body", RC_FAIL),
    ]
    ok = fail = 0
    for name, text, mode, want in cases:
        got, _out = run(lambda p: lint(p, mode), text)
        got = int(got)
        if got == want:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            fail += 1
            print("  [NG]   %s（期望 %d，实得 %d）" % (name, want, got))
    print("\n自检：%d 通过 / %d 失败" % (ok, fail))
    return RC_OK if fail == 0 else RC_FAIL


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return cmd_self_test()
    args = argv[1:]
    mode = "full"
    if "--mode" in args:
        i = args.index("--mode")
        try:
            mode = args[i + 1]
        except IndexError:
            die("--mode 缺值（full|body）", RC_USAGE)
        if mode not in ("full", "body"):
            die("--mode 只能是 full 或 body", RC_USAGE)
        args = args[:i] + args[i + 2:]
    level = "L2"
    if "--level" in args:
        i = args.index("--level")
        try:
            level = args[i + 1]
        except IndexError:
            die("--level 缺值（L0|L1|L2）", RC_USAGE)
        if level not in LEVEL_MODULES:
            die("--level 只能是 L0、L1 或 L2", RC_USAGE)
        if mode == "body":
            die("--level 只用于 full 模式", RC_USAGE)
        args = args[:i] + args[i + 2:]
    if len(args) != 1:
        die(__doc__, RC_USAGE)
    target = args[0]
    if not os.path.exists(target):
        die("路径不存在：%s" % target, RC_USAGE)
    return lint(target, mode, level)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
