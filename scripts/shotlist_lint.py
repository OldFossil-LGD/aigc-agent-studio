#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分镜表检查器（把「排镜表」从建议变成门禁）

为什么要有它：本库早就有排镜表（`shot-orchestration.md` §九）与九级景别（`sequence-craft.md` §八），
但它们是**建议**，没有任何工具检查 → 实操中一定会被跳过 → 症状就是"中近景一家独大、时长失控"。
这个脚本把那几条规则变成**机器可判的门禁**。

退出码（与 audit_prompt.py 一致）：
  0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN
  5 **判据不适用**（≠通过，也≠失败）：本表镜数 < 2，景别分布类判据的前提不满足。
    与 3 同构——都是「**没验到**」而不是「验过了」。详见 E164 / E221。

用法：
  python3 scripts/shotlist_lint.py <分镜表.md> [--mode cut|gen]
  python3 scripts/shotlist_lint.py --self-test

--mode 是什么（**这是本工具最关键的一条**）：
  gen = 生成单元（一次投喂给模型）→ 单段下限定为 2.0 秒（库规：压时长只会崩）
  cut = 成片镜头长度（剪辑后）     → 单段下限定为 0.4 秒（快切段允许）
  两者不是同一件事；用错模式会得到完全相反的结论。

★ 载体兼容（E33，2026-09-14）：本库的编号载体已由「镜几」改为「段落 / 组合」
  （`镜N` 自带"剪辑点"预设，会把段内的景别变化误读成硬切）。
  本脚本**两种写法都认**——首列「镜号」或「段落 / 组合」，分隔线 `──── 镜2 ────`
  或 `──── 段落B · 名字 ────`，时间线块名 `【时间线】` 或 `【★ 时间线 · 段内变化】`。
  **改任一个载体词都必须补一条对应的自检用例**——否则检查会"静默失效"（不报错、只是扫不到）。
"""
from __future__ import print_function

import io
import os
import re
import sys

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN, RC_INAPP = 0, 1, 2, 3, 4, 5

# 九级景别，从极远到极近，级差用于"相邻跨度"检查
SCALE_ORDER = [
    ("大远景", ["大远景", "ELS", "els"]),
    ("远景", ["远景", "LS", "ls"]),
    ("全景", ["全景", "主镜头", "FS", "fs"]),
    ("中景", ["中景", "MS", "ms"]),
    ("中近景", ["中近景", "MCU", "mcu"]),
    ("近景", ["近景"]),
    ("特写", ["特写", "CU", "Close", "close"]),
    ("大特写", ["大特写", "ECU", "ecu"]),
    ("插入", ["插入", "细节", "Insert", "insert"]),
]

MIDDLE = ("中景", "中近景")

# 表头里"镜号 / 景别 / 时长"三列的候选名
# ★ 2026-09-14 加「段落 / 组合」：E33 已把编号载体由「镜几」改为「段落 / 组合」，
#   排镜表首列也随之改叫「段落」——不加这条，段落式排镜表会被判成"没有分镜表"（实测踩过）。
COL_SHOT = ("镜号", "段落", "组合", "SH", "shot")
# ---- 两条路的载体分流（2026-09-15）----
# 库里现行规矩是**两条路**，首列是**分镜版还是段落版**，决定【时间线】该写什么：
#   分镜版（首列「镜号 / SH / shot」，＝单机位镜、**一镜一生成**）→ 时间线写**四相**
#        （起始 / 主动作 / 反应与呼吸 / 定格）——**这是规定的写法**，不是病灶。
#   段落版（首列「段落 / 组合」，一次生成多画面）→ 时间线写「先 / 随后 / 最后」，段内禁写切镜词。
# 检查 0c 只为**段落版**而设（它禁的是"段内借用切镜词"）；而**分镜版的四相本身就是切镜词那一族**，
# 不按载体分流 → 对合法的分镜版**每一镜误报一条**（2026-09-15 实测：6 镜 6 条 WARN）。
# **误报也算 bug**：这种 WARN 久了没人看，等于把关失效。
CARRIER_SHOT = ("镜号", "SH", "shot")   # 分镜版载体
CARRIER_SEG = ("段落", "组合")          # 段落版载体
COL_SIZE = ("景别",)
COL_DUR = ("时长", "成片时长", "长度")
# 叙事职能：这一镜**为叙事干了什么**（与景别是两回事——同一景别可以承担不同职能）
COL_FUNC = ("叙事职能", "职能")
# 信息列：这一镜提供的**唯一**新信息（库里排镜表模板叫「这一镜的唯一信息」）
COL_INFO = ("唯一信息", "画面内容", "信息")

# 七种叙事职能（与"景别"正交：同一景别可以是建立，也可以是反应）
FUNC_ORDER = ("建立", "推进", "揭示", "反应", "过渡", "峰值", "收束")

# ---- 检查 0c：单镜过载（一条里塞了整段动作弧）----
# 病灶：`镜N` 是二元的（在镜2 / 不在镜2），所以"同一镜里他先不动、随后眼睛动、最后手停住"
#   在镜序语法里**没有词可写** → 人会顺手借用**切镜的词**（准备/接触/落定、起始/触发）
#   → 模型读成"这是三个镜头" → 成片是一条里塞了整段动作弧，且首帧景别与后文打架。
# 这个词表命中的是**动作相位名**，不是普通动词——"他停住"不命中，"主动作"命中。
PHASE_WORDS = ("起始", "触发", "主动作", "前提", "落定", "定格", "反应与呼吸")
PHASE_PAIRS = (("准备", "接触"), ("接触", "落定"))
# 单镜时长上限（秒）：超了就该考虑拆镜，而不是把相位名堆进去
PHASE_DUR = 8.0

HDR = re.compile(r"^\s*\|")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_table(text):
    """返回 (rows, headers)。rows 为 dict 列表；找不到返回 ([], None)。

    注意：**表格结束后不能把 headers 清成 None**——否则前面已收进来的 rows 会失去表头
    （本脚本第一版就栽在这个坑里：表格后的空行触发了重置，直接 TypeError）。
    """
    lines = text.split("\n")
    headers = None
    out_headers = None
    rows = []
    for line in lines:
        if not HDR.match(line):
            # 一张表结束后就停——否则同文件里的第二张表（例如"时间轴校核表"）会被合并统计
            if rows:
                break
            headers = None
            continue
        cells = _cells(line)
        if not cells:
            headers = None
            continue
        # 分隔行
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue
        if headers is None:
            joined = "".join(cells)
            # 判据必须**同时满足三条**：有「景别」、有「时长」、**还有「镜号」**。
            # 为什么非要有「镜号」：库里还有一张"景别占比统计表"（列是 景别|镜数|时长|占比），
            # 它也含"景别 + 时长"。不加这条判据，检查器会把统计表当成排镜表——
            # 实测踩过：17 镜的分镜表被识别成"9 个镜头"（其实是 9 个景别的统计行）。
            has_size = "景别" in joined
            has_dur = ("时长" in joined or "长度" in joined)
            has_shot = any(c in joined for c in ("镜号", "段落", "组合", "SH", "shot"))
            if has_size and has_dur and has_shot:
                headers = cells
                out_headers = cells
            continue
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows, out_headers


def _col(headers, cands):
    for h in headers:
        for c in cands:
            if c in h:
                return h
    return None


def _carrier(c_shot):
    """从**已识别出的首列表头**判这一份是哪个载体（分镜版 / 段落版）。

    **复用 `COL_SHOT` 那一族的判断结果（`c_shot`），不另起一套判断**——否则两处判据会漂移。

      首列「段落 / 组合」     → "seg"（段落版：一次生成多画面 → 检查 0c 适用）
      首列「镜号 / SH / shot」→ "shot"（分镜版：一镜一生成 → 检查 0c **不适用**）
      认不出（c_shot 为空）   → "seg"（保守：保持 0c 照跑，宁可多一条人工确认，也不要静默失效）
    """
    if not c_shot:
        return "seg"
    if any(k in c_shot for k in CARRIER_SEG):
        return "seg"
    if any(k in c_shot for k in CARRIER_SHOT):
        return "shot"
    return "seg"


def _scale_level(text):
    """返回 (级别序号, 标准名)。0 起。找不到返回 (None, None)。

    **必须取"最长匹配"**：这些词互相包含——"大特写"含"特写"、"中近景"含"近景"、
    "大远景"含"远景"。按 SCALE_ORDER 顺序一遇到就返回，会把"大特写"误判成"特写"（实测踩过）。
    """
    best = None  # (匹配到的 key 长度, 级别, 标准名)
    for i, (name, keys) in enumerate(SCALE_ORDER):
        for k in keys:
            if k in text:
                if best is None or len(k) > best[0]:
                    best = (len(k), i, name)
    if best is None:
        return None, None
    return best[1], best[2]


def _to_float(s):
    m = re.search(r"([+-]?\d+(?:\.\d+)?)", s.replace("秒", ""))
    return float(m.group(1)) if m else None


def _timeline_segments(text):
    """按「──────── 镜N ────────」或「──────── 段落A · 名字 ────────」型分隔线切段，
    返回 [(段标签, 该段正文)]。

    为什么要按分隔线切：检查 0c 要判"**这一段**的时间线里塞了几个动作相位"，
    所以必须先知道每个【时间线】属于哪一段。找不到分隔线时，退化成
    "全文的【时间线】块都归同一个无名段"，仍能报出疑似过载（只是标签写"未标明段号"）。
    ★ 2026-09-14：分隔线标签由「镜几」扩到「段落 / 组合」（E33），否则段落式交付物扫不到。
    """
    lines = text.split("\n")
    # 标签形态：`镜2` / `段落B` / `组合A`，允许后面跟分隔用的 `· 名字` 或 `- 名字`
    # （段落名是 E33 指定的写法：`──────── 段落B · 停在枪套上的手 ────────`）
    seg_re = re.compile(
        r"^\s*[─—=\-]{2,}\s*((?:镜|段落|组合)\s*[0-9A-Za-z甲乙丙丁一二三四五六七八九十]+"
        r"(?:\s*[·・\-—]\s*[^─—=\-]*)?)\s*[─—=\-]{2,}\s*$")
    marks, cur = [], None
    for i, ln in enumerate(lines):
        m = seg_re.match(ln)
        if m:
            marks.append((i, m.group(1).strip()))
    out = []
    if not marks:
        body = "\n".join(lines)
        tl = _extract_timeline(body)
        if tl:
            out.append(("未标明段号", tl))
        return out
    for k, (i, lbl) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        tl = _extract_timeline("\n".join(lines[i:end]))
        if tl:
            out.append((lbl, tl))
    return out


def _extract_timeline(block):
    """取一个段里【时间线】那一块（到下一个【】为止）。

    ★ 2026-09-14：标签由 `【时间线】` 放宽到「**块名里含"时间线"**」——
    段落式模板的块名是 `【★ 时间线 · 段内变化】`（E33），
    只认死 `【时间线】` 会让**段落式的检查 0c 静默失效**（实测踩过：三段落只扫出 1 段）。
    """
    m = re.search(r"【[^】\n]{0,16}时间线[^】\n]{0,16}】([\s\S]*?)(?=\n\s*【|\Z)", block)
    return m.group(1) if m else ""


def lint(path, mode="cut"):
    text = read(path)
    rows, headers = parse_table(text)
    if not rows:
        print("[FAIL] 没找到分镜表（需要同时含「景别」与「时长 / 长度」两列的表）。")
        print("       若这份文件本来就没有分镜表，请忽略此命令。")
        return RC_EMPTY

    c_shot = _col(headers, COL_SHOT)
    c_size = _col(headers, COL_SIZE)
    c_dur = _col(headers, COL_DUR)
    c_func = _col(headers, COL_FUNC)
    c_info = _col(headers, COL_INFO)
    if not (c_size and c_dur):
        print("[FAIL] 表头缺「景别」或「时长」列。")
        return RC_FAIL

    gen = (mode == "gen")
    min_dur = 2.0 if gen else 0.4
    # 节奏对比阈值也要按模式区分：gen 模式单镜 ≥2 秒，要求 3 倍对比（需 6 秒长镜）不现实
    ratio_min = 2.0 if gen else 3.0
    fails, warns, notes = [], [], []

    shots = []
    for i, r in enumerate(rows, 1):
        size_raw = (r.get(c_size) or "").strip()
        dur_raw = (r.get(c_dur) or "").strip()
        if not size_raw or not dur_raw:
            warns.append("第 %d 行：景别或时长为空（跳过该行）" % i)
            continue
        lvl, sname = _scale_level(size_raw)
        d = _to_float(dur_raw)
        if lvl is None:
            warns.append("第 %d 行：认不出景别「%s」（应为大远景/远景/全景/中景/中近景/近景/特写/大特写/插入）" % (i, size_raw))
            continue
        if d is None:
            warns.append("第 %d 行：认不出时长「%s」" % (i, dur_raw))
            continue
        if d <= 0:
            fails.append("第 %d 行：时长必须大于 0，实际为 %s" % (i, dur_raw))
            continue
        label = (r.get(c_shot) or ("第%d镜" % i)).strip()
        shots.append({
            "label": label, "size": sname, "level": lvl, "dur": d,
            "func": (r.get(c_func) or "").strip() if c_func else "",
            "info": (r.get(c_info) or "").strip() if c_info else "",
        })

    # ---- 检查 0：叙事职能列（缺列只是 WARN，但**填了就必须填对**）----
    if not c_func:
        warns.append("缺「%s」列——景别管「框多大」，职能管「为叙事干了什么」，两者正交；建议补上"
                     % "/".join(COL_FUNC))
    else:
        for s in shots:
            if not s["func"]:
                warns.append("%s 的叙事职能为空（七选一：%s）" % (s["label"], "/".join(FUNC_ORDER)))
            elif not any(f in s["func"] for f in FUNC_ORDER):
                warns.append("%s 的叙事职能「%s」不在七种之内（%s）"
                             % (s["label"], s["func"], "/".join(FUNC_ORDER)))
        # 相邻两镜职能相同 = 叙事停滞（与"景别停滞"是两回事：景别换了但干的事一样，仍是停滞）
        for a, b in zip(shots, shots[1:]):
            if a["func"] and a["func"] == b["func"]:
                warns.append("%s → %s **叙事职能重复**（都是「%s」）——景别换了但干的事一样，仍是停滞"
                             % (a["label"], b["label"], a["func"]))
        # 峰值唯一
        peaks = [s["label"] for s in shots if s["func"] == "峰值"]
        if len(peaks) > 1:
            warns.append("峰值有 %d 个（%s）——一场戏通常只该有一个最高点" % (len(peaks), "、".join(peaks)))
        # 收束必须在最后
        ends = [i for i, s in enumerate(shots) if s["func"] == "收束"]
        if ends and ends[-1] != len(shots) - 1:
            warns.append("「收束」出现在 %s，但不是最后一镜——收束应在末尾" % shots[ends[-1]]["label"])

    # ---- 检查 0b：唯一信息（库里排镜表最难填也最值钱的一列）----
    if c_info:
        for s in shots:
            if not s["info"]:
                warns.append("%s 的「%s」为空——填不出具体信息，说明这一镜不该存在" % (s["label"], c_info))
        for a, b in zip(shots, shots[1:]):
            if a["info"] and a["info"] == b["info"]:
                fails.append("%s 与 %s 的信息完全一样——这就是「换个角度拍同一件事」，删掉一镜"
                             % (a["label"], b["label"]))
    else:
        warns.append("缺「唯一信息」列（或「画面内容」）——这一列是排镜表里最难填也最值钱的")

    # ---- 检查 0c：单段过载（**这一列在库里没有，正文里才有**）----
    # 排镜表只能看到"段落B = 中近景 / 5 秒 / 推进"，看不出这一段里塞了几件事；
    # 但**提示词的【时间线】里塞了相位名**（准备/接触/落定、起始/触发）就是铁证——
    # 那是**段与段之间**的词，写进一段 = 模型会读成"这里有好几个镜头"。
    # 本检查在整份文档上扫，与表格是否解析成功无关。
    # ★ 2026-09-15 按载体分流：本级**只为段落版而设**。分镜版的【时间线】按规定就写四相
    #   （起始 / 主动作 / 反应与呼吸 / 定格），而四相**本身就是切镜词那一族** → 不分流
    #   就会对合法的分镜版**每一镜误报一条**（实测 6 镜 6 条）。
    #   分镜版**跳过**即可："这一镜确实过载"（同一镜里塞了 2 个以上**各自完整**的动作）
    #   需要语义理解，本级本来就判不出来 → **不为它另造检查**。
    if _carrier(c_shot) != "seg":
        notes.append("首列「%s」＝**分镜版**（一镜一生成）——【时间线】按规定写四相"
                     "（起始 / 主动作 / 反应与呼吸 / 定格），检查 0c（单段过载）**对本版不适用，已跳过**"
                     % c_shot)
    else:
        for lbl, seg in _timeline_segments(text):
            hits = [w for w in PHASE_WORDS if w in seg]
            for a, b in PHASE_PAIRS:
                if a in seg and b in seg:
                    hits.append("%s→%s" % (a, b))
            if len(hits) >= 3:
                warns.append("【%s】的【时间线】**疑似单段过载**（命中 %d 个动作相位名：%s）"
                             "——「准备/接触/落定/起始/触发」是**段与段之间**的词，"
                             "写进一段会被模型读成「这是好几个镜头」，成片就是一段里塞了整段动作弧。"
                             "**改法：段内推进写「他先…；随后…；最后…」**（→ `segmented-shot.md` §三）"
                             "（分镜版请回 `shot-craft.md` 过「拆镜开关」）"
                             % (lbl, len(hits), "、".join(hits)))
            elif len(hits) >= 2:
                notes.append("【%s】的【时间线】出现 2 个相位名（%s）——留意是不是把切镜词汇写进了单段"
                             % (lbl, "、".join(hits)))

    # 另一条同源症状：单段很长，且**没有分段**（长段不是罪，长段里塞整条动作弧才是）
    for s in shots:
        if s["dur"] > PHASE_DUR:
            warns.append("%s 时长 %.1fs > %.0fs——单次生成的连贯性约 2 秒后开始衰减；"
                         "若这一段里还要演完整条动作弧，**先考虑拆成两段**"
                         % (s["label"], s["dur"], PHASE_DUR))

    if not shots:
        print("[FAIL] 表里没有一行能解析出有效的「景别 + 正时长」。")
        for failure in fails:
            print("  " + failure)
        return RC_FAIL

    total = sum(s["dur"] for s in shots)
    asl = total / len(shots)
    print("识别到镜头：%d 个｜总时长 %.1f 秒｜平均镜头 %.2f 秒（ASL）｜模式 --mode %s（单镜下限 %.1fs）\n" % (
        len(shots), total, asl, mode, min_dur))

    # ---- 检查 1：单镜下限 ----
    for s in shots:
        if s["dur"] < min_dur - 0.001:
            fails.append("%s 时长 %.1fs < 下限 %.1fs（--mode %s）" % (s["label"], s["dur"], min_dur, mode))

    # ---- 景别分布类判据的**前提**：镜数 ≥ 2 ----
    # 为什么要有这个前提（2026-10-03 补 · E164 复现两轮后落）：
    #   检查 2 / 3 / 3b 全部在问「分布是否失衡」，而**失衡这个词预设了至少两个取值**。
    #   一镜排练表里某种景别占比 100% 是**恒等式**，不是失衡——它不携带任何信息。
    #   原来把这种情况报成 FAIL，等于**每次单镜演练都误报一次**；
    #   按 E23（误报比漏报更隐蔽），一个天天喊狼来了的闸，两轮之后人就学会无视它，
    #   那时候真违规会跟着一起被忽略。
    #   → 正确处置是让「不适用」成为一个**独立状态**（与 E162 的 empty 同构），
    #     **判据一个字都没有改**，只是不再把它伪装成「失败」。
    n_shots = len(shots)
    dist_applicable = n_shots >= 2
    if not dist_applicable:
        print("[不适用] 本表只有 1 个镜头 → 景别分布类判据（检查 2 / 3 / 3b）**前提不满足**，"
              "已跳过。\n           单镜表里某种景别占比 100%% 是恒等式，不是失衡。"
              "（**判据未被放宽，只是本次没验到**）\n")

    # ---- 检查 2：单一景别占比（WARN，不是 FAIL）----
    # 为什么不是 FAIL：大远景独大也是一种"独大"，但在西部/史诗里常常是**有意的风格**；
    # 真正要一刀毙命的是"中景+中近景堆砌"（见下一条），那才是单调的主因。
    agg = {}
    for s in shots:
        agg[s["size"]] = agg.get(s["size"], 0.0) + s["dur"]
    for name, d in sorted(agg.items(), key=lambda x: -x[1]):
        pct = d / total * 100.0
        if pct > 35.0 and dist_applicable:
            warns.append("单一景别「%s」占 %.1f%% > 35%%（确认是不是有意的风格，而不是失控）" % (name, pct))

    # ---- 检查 3：中景 + 中近景合计（**唯一的一票否决**）----
    mid_d = sum(agg.get(m, 0.0) for m in MIDDLE)
    mid_pct = mid_d / total * 100.0
    if mid_pct > 40.0 and dist_applicable:
        fails.append("中景 + 中近景合计 %.1f%% > 40%%（中近景一家独大 —— 单调的主因）" % mid_pct)

    # ---- 检查 3b：两极各自的合计（WARN）----
    far_d = sum(agg.get(n, 0.0) for n in ("大远景", "远景"))
    near_d = sum(agg.get(n, 0.0) for n in ("大特写", "插入", "特写"))
    if dist_applicable and far_d / total * 100.0 > 50.0:
        warns.append("极远合计 %.1f%% > 50%%（两头失衡，中间被抽空）" % (far_d / total * 100.0))
    if dist_applicable and near_d / total * 100.0 > 50.0:
        warns.append("极近合计 %.1f%% > 50%%（两头失衡，观众会失去地理感）" % (near_d / total * 100.0))

    # ---- 检查 4：景别的"停滞"----
    # 规则说明（**这条是被实验修正过的**）：
    #   最初写的是"相邻跨度 ≥2 级"，结果把合法的**单向渐进**（大远景→远景→全景→中景＝建立/收紧）
    #   也误报了。真正该抓的是两种**停滞**：
    #     ① 同级连切（gap == 0）
    #     ② 来回摆动（a→b→c 中 a 与 c 同级、b 不同级）—— 例：中景→中近景→中景，
    #        这正是"中近景堆砌"的局部形态，靠占比统计抓不到，只能看相邻关系。
    #   **豁免**：只检查"时长 ≥1.5 秒"的镜头。为什么——快段（0.5–0.8 秒）本来就在
    #   大特写与插入之间交替，那是快切的正常语法；**在 0.5 秒的尺度上，速度本身已经提供了变化**，
    #   再按"停滞"判就是误报。停滞只可能发生在观众来得及比较的尺度上。
    SLOW = 1.5
    for a, b in zip(shots, shots[1:]):
        if a["level"] == b["level"] and min(a["dur"], b["dur"]) >= SLOW:
            warns.append("%s → %s **同级连切**（都是%s）——相邻两镜同景别，读起来像没换镜头"
                         % (a["label"], b["label"], a["size"]))
    for a, b, c in zip(shots, shots[1:], shots[2:]):
        if (a["level"] == c["level"] and b["level"] != a["level"]
                and min(a["dur"], b["dur"], c["dur"]) >= SLOW):
            warns.append("%s(%s) ↔ %s(%s) ↔ %s(%s) **来回摆动**——两级之间反复横跳，是停滞不是变化"
                         % (a["label"], a["size"], b["label"], b["size"], c["label"], c["size"]))

    # ---- 检查 5：有没有节奏对比（最长 / 最短） ----
    mx = max(s["dur"] for s in shots)
    mn = min(s["dur"] for s in shots)
    ratio = mx / mn if mn else 0
    if ratio < ratio_min - 0.001:
        warns.append("最长 %.1fs / 最短 %.1fs = %.1f× < %.1f×（缺节奏对比，容易平）" % (mx, mn, ratio, ratio_min))
    else:
        notes.append("节奏对比 %.1f×（最长 %.1fs / 最短 %.1fs）" % (ratio, mx, mn))

    # ---- 检查 6：ASL 与片种参考（只 WARN） ----
    if asl < 1.2:
        warns.append("ASL %.2fs 明显短于现代动作片（约 3s）——确认是不是「为了快而快」" % asl)
    elif asl > 12.0:
        warns.append("ASL %.2fs 偏长——短视频里容易掉完播" % asl)
    else:
        notes.append("ASL %.2fs 在合理区间" % asl)

    # ---- 输出 ----
    print("景别分布（按时间）：")
    for name, d in sorted(agg.items(), key=lambda x: -x[1]):
        print("   %-6s %5.1fs  %5.1f%%" % (name, d, d / total * 100.0))
    print("   中景+中近景合计 %.1f%%" % mid_pct)
    print()

    if notes:
        for n in notes:
            print("[INFO] " + n)
        print()
    if warns:
        print("[WARN] 需人工确认：")
        for w in warns:
            print("  " + w)
        print()
    if fails:
        print("[FAIL] 门禁未过：")
        for f in fails:
            print("  " + f)
        print("\n提示：先改排镜表再写提示词——在这一层改是免费的。")
        return RC_FAIL

    # ---- 收口：把「前提不满足」独立成一个状态，别混进 PASS ----
    # 「不适用」与「通过」是**两个事实**（E164）。混成一个绿灯 = 纸上正确但实质错。
    if not dist_applicable:
        print("[不适用] 其余硬线全过；仅景别分布类判据因**镜数 %d < 2**未验。"
              "→ 退出码 %d（不适用），**不是通过**。" % (n_shots, RC_INAPP))
        return RC_INAPP

    print("[PASS] 排镜表通过门禁（%d 项硬线 + 节奏对比）。" % 3)
    if warns:
        return RC_WARN
    return RC_OK


# ---------------------------------------------------------------- 自检
def _run(path, mode):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = lint(path, mode)
    finally:
        sys.stdout = old
    return rc


def cmd_self_test():
    import tempfile

    def w(name, body):
        fd, p = tempfile.mkstemp(suffix=".md", prefix="shotlist_")
        os.close(fd)
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    # 反例：中近景一家独大 + 职能重复 + 信息重复
    bad = """# 反例
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 中近景 | 2.5 | 推进 | 他在犹豫 |
| SH02 | 中景 | 2.5 | 推进 | 他在犹豫 |
| SH03 | 中近景 | 2.5 | 推进 | 他在犹豫 |
| SH04 | 中景 | 2.5 | 推进 | 他在犹豫 |
"""
    # 正例：平衡表（cut 模式）
    balanced = """# 正例·平衡
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 大远景 | 3.5 | 建立 | 空街两端，两个人影 |
| SH02 | 中景 | 2.0 | 揭示 | 他的手垂在枪套上 |
| SH03 | 大特写 | 1.5 | 反应 | 帽檐阴影里的眼 |
| SH04 | 中近景 | 2.0 | 推进 | 下颌绷紧 |
| SH05 | 插入 | 1.0 | 收束 | 指节松开，枪没拔 |
"""
    # 正例：生成单元模式（每镜 ≥2 秒）
    good_gen = """# 正例·生成单元
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 大远景 | 4.0 | 建立 | 街的全貌 |
| SH02 | 中景 | 2.0 | 揭示 | 手垂在枪套 |
| SH03 | 大特写 | 2.0 | 反应 | 眼 |
| SH04 | 中近景 | 2.0 | 推进 | 呼吸变浅 |
| SH05 | 插入 | 2.0 | 收束 | 枪套扣没开 |
"""
    # WARN：大远景偏重
    warn_case = """# 反例·大远景偏重
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 大远景 | 6.0 | 建立 | 街的全貌 |
| SH02 | 中景 | 2.0 | 揭示 | 手 |
| SH03 | 大特写 | 2.0 | 收束 | 眼 |
"""
    # WARN：叙事职能重复（景别换了，但干的事一样）
    func_dup = """# 反例·职能重复
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 大远景 | 3.0 | 推进 | 街 |
| SH02 | 中景 | 2.5 | 推进 | 手 |
| SH03 | 大特写 | 2.0 | 收束 | 眼 |
"""
    # WARN：收束不在最后一镜
    end_early = """# 反例·收束过早
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 大远景 | 3.0 | 建立 | 街 |
| SH02 | 中景 | 2.5 | 收束 | 手 |
| SH03 | 大特写 | 2.0 | 推进 | 眼 |
"""
    empty = "# 没有表\n\n随便一行文字。\n"

    # ★ 段落式排镜表：首列叫「段落」而不是「镜号」——E33 之后这是**正常写法**，
    #   必须认得出（否则段落式交付物会被判成"没有分镜表"）。
    para_ok = """# 正例·段落式排镜表
| 段落 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 段落A | 大远景 | 3.0 | 建立 | 隔着一条空街，谁都不动 |
| 段落B | 中景 | 2.0 | 揭示 | 他的手垂在枪套上 |
| 段落C | 大特写 | 1.0 | 反应 | 帽檐阴影里的眼 |
| 段落D | 近景 | 2.0 | 推进 | 呼吸变浅 |
| 段落E | 插入 | 1.0 | 收束 | 指节松开，枪没拔 |
"""

    # WARN：单段过载——排镜表看着没问题（中近景 5 秒），但【时间线】里塞了一整条动作弧
    # （用**段落**分隔线，验检查 0c 在段落式文档上同样生效）
    overload = """# 反例·单段过载
| 段落 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 段落A | 大远景 | 5.0 | 建立 | 隔着一条空街，谁都不动 |
| 段落B | 中近景 | 5.0 | 推进 | 他本来可以更快，手却停在枪套上 |
| 段落C | 大远景 | 5.0 | 收束 | 一枪之后街对面空了，他也没看 |

──────── 段落B · 停在枪套上的手 ────────
【光位与影调】光从左上方下来，硬、灼白。
【时间线】起始：他不动，右手垂在身侧；
触发：帽檐阴影里的眼睛先动了一下；
主动作：准备——指尖开始收拢；接触——指腹贴上枪套皮面；落定——手停在枪套上，没有拔；
反应与呼吸：那滴汗从下颌滑到颈侧；
定格：手停住的那个状态冻结下来。
【摄影机】固定不动。

──────── 段落C · 对面空了 ────────
【时间线】段首第一个词就是景别；他仍站在原地，头没有转向那边。
"""

    # 镜式分隔线仍要认（旧文档不因 E33 而失效）
    overload_mirror = """# 反例·单镜过载（旧式镜号）
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 镜1 | 大远景 | 5.0 | 建立 | 街 |
| 镜2 | 中近景 | 5.0 | 推进 | 手停在枪套上 |
| 镜3 | 大特写 | 5.0 | 收束 | 眼 |

──────── 镜2 ────────
【时间线】起始：他不动；触发：眼睛先动；主动作：准备——指尖收拢；接触——指腹贴上皮面；落定——手停住。
"""

    # ★ 2026-09-15 载体分流（分镜版）：「两条路」定下来后，首列「镜号」＝**分镜版**（一镜一生成），
    #   它的【时间线】按规定就写**四相**（起始 / 主动作 / 反应与呼吸 / 定格）——**这是规定的写法**，
    #   不是病灶。检查 0c 是给段落版的，必须跳过；否则对合法的分镜版**每一镜误报一条**（实测 6 镜 6 条）。
    #   这份表**其余各项全部干净** → 期望 0；一旦 0c 又跑起来，会立刻变成 WARN 而被抓到（这就是这条断言的作用）。
    shot_carrier = """# 正例·分镜版（首列「镜号」+ 四相时间线 → 检查 0c 不适用）
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 镜1 | 大远景 | 4.0 | 建立 | 隔着一条空街，谁都不动 |
| 镜2 | 中景 | 2.0 | 推进 | 他本来可以更快，手却停在枪套上 |
| 镜3 | 大特写 | 2.0 | 揭示 | 帽檐阴影里的眼 |
| 镜4 | 插入 | 2.0 | 反应 | 那滴汗滑到颈侧 |
| 镜5 | 近景 | 2.0 | 收束 | 指节松开，枪没拔 |

──────── 镜1 · 空街 ────────
【时间线】起始：他不动，右手垂在身侧；
主动作：准备——指尖开始收拢；接触——指腹贴上枪套皮面；落定——手停在枪套上，没有拔；
反应与呼吸：那滴汗从下颌滑到颈侧；定格：手停住的那个状态冻结下来。
"""

    # ★ 与上一条配对（防"分流改过头、把 0c 改死"）：首列「段落」＝**段落版**，
    #   段内借用了切镜词（准备 / 接触 / 落定）**仍必须报**。
    #   它同样其余各项干净 → WARN 只可能来自 0c，报出来才算这条检查还活着。
    #   （块名故意用段落式的 `【★ 时间线 · 段内变化】`，顺带锁住"块名含时间线"这条容忍度。）
    seg_overload = """# 反例·段落版段内借切镜词（检查 0c 仍须报）
| 段落 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 段落A | 大远景 | 4.0 | 建立 | 隔着一条空街，谁都不动 |
| 段落B | 中景 | 2.0 | 推进 | 他本来可以更快，手却停在枪套上 |
| 段落C | 大特写 | 2.0 | 揭示 | 帽檐阴影里的眼 |
| 段落D | 插入 | 2.0 | 反应 | 那滴汗滑到颈侧 |
| 段落E | 近景 | 2.0 | 收束 | 指节松开，枪没拔 |

──────── 段落B · 停在枪套上的手 ────────
【★ 时间线 · 段内变化】起始：他不动，右手垂在身侧；
主动作：准备——指尖开始收拢；接触——指腹贴上枪套皮面；落定——手停在枪套上，没有拔。
"""

    # 判据不适用：单镜表里某种景别必然占 100%——那是**恒等式**，不是失衡
    single_shot = """# 反例·单镜（景别分布判据的前提不满足）
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 中景 | 5.0 | 建立 | 抽屉已拉开一指宽 |
"""
    # 反证：**判据本身没被放过** —— 两镜全在中景，仍然必须 FAIL
    mid_heavy_2shot = """# 反例·两镜全中景（分布判据成立 → 仍须 FAIL）
| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| SH01 | 中景 | 3.0 | 建立 | 抽屉已拉开 |
| SH02 | 中景 | 3.0 | 揭示 | 钥匙露出来 |
"""

    cases = [
        ("lint·单镜表 → 5（景别分布**不适用**；≠通过也≠失败）",
         w("s1", single_shot), "cut", RC_INAPP),
        ("lint·两镜全中景 → 1（判据**没有被放过**：前提满足时照常开火）",
         w("mh", mid_heavy_2shot), "cut", RC_FAIL),
        ("lint·中近景一家独大 + 职能/信息重复 → FAIL", w("bad", bad), "cut", RC_FAIL),
        ("lint·平衡表（含职能与信息列）→ 0", w("bal", balanced), "cut", RC_OK),
        ("lint·生成单元模式（每镜 ≥2s）→ 0", w("g1", good_gen), "gen", RC_OK),
        ("lint·段落式排镜表（首列「段落」）→ 0", w("po", para_ok), "cut", RC_OK),
        ("lint·大远景偏重 → WARN（不判死，交人工）", w("wc", warn_case), "cut", RC_WARN),
        ("lint·叙事职能重复 → WARN（景别换了但干的事一样）", w("fd", func_dup), "cut", RC_WARN),
        ("lint·收束不在最后一镜 → WARN", w("ee", end_early), "cut", RC_WARN),
        ("lint·单段时间线塞整条动作弧 → WARN（检查 0c）", w("ol", overload), "gen", RC_WARN),
        ("lint·单镜时间线塞整条动作弧（旧式镜号＝分镜版）→ 0c 不适用；仍因节奏对比判 WARN",
         w("om", overload_mirror), "cut", RC_WARN),
        ("lint·分镜版（首列「镜号」+ 四相时间线）→ 0（检查 0c 按载体跳过，不再逐镜误报）",
         w("sc", shot_carrier), "gen", RC_OK),
        ("lint·段落版（首列「段落」）段内仍借切镜词 → WARN（检查 0c 未被改死）",
         w("so", seg_overload), "gen", RC_WARN),
        ("lint·没有分镜表 → 3（没扫到 ≠ 通过）", w("e", empty), "cut", RC_EMPTY),
    ]

    ok = fail = 0
    for name, path, mode, want in cases:
        got = _run(path, mode)
        if got == want:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            fail += 1
            print("  [NG]   %s（期望 %d，实得 %d）" % (name, want, got))
        try:
            os.remove(path)
        except OSError:
            pass

    print("\n自检：%d 通过 / %d 失败" % (ok, fail))
    return RC_OK if fail == 0 else RC_FAIL


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return cmd_self_test()
    args = argv[1:]
    mode = "cut"
    if "--mode" in args:
        i = args.index("--mode")
        try:
            mode = args[i + 1]
        except IndexError:
            die("--mode 缺值（cut|gen）", RC_USAGE)
        if mode not in ("cut", "gen"):
            die("--mode 只能是 cut 或 gen", RC_USAGE)
        args = args[:i] + args[i + 2:]
    if len(args) != 1:
        die(__doc__, RC_USAGE)
    target = args[0]
    if not os.path.exists(target):
        die("路径不存在：%s" % target, RC_USAGE)
    return lint(target, mode)


def die(msg, rc):
    print(msg)
    sys.exit(rc)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
