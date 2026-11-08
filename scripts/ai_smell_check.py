#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai_smell_check.py — 提示词"AI 味"检测器

它查什么（只扫 ``` 围栏内的提示词正文）：
  1 空话形容词（含变体）—— 电影感 / 电影质感 / 大片感 / 细腻 / 高级感 / 4K …
  2 文件腔连接词 —— 综上所述 / 值得注意的是 / 旨在 / 呈现出 …
  3 块内元说明（思考残留）—— 另注： / 注： / （改成你的…） / *可选* …
  4 双语并列 —— 中文后面硬跟一个英文括注
  5 口水副词 —— 非常 / 极其 / 渐渐地 / 缓缓地 …

它**不查什么**：不判提案质量、不判结构完整（那是 audit_prompt.py 的活）、
不预测生成效果。**零命中 ≠ 提示词好**，只是"没踩这几个已知的坑"。

用法：
  python3 scripts/ai_smell_check.py <文件或目录> [更多路径…]
  python3 scripts/ai_smell_check.py --inline <文件或目录>   # 连行内代码句一起扫（见下）
  python3 scripts/ai_smell_check.py --self-test          # 跑内建回归用例
  python3 scripts/ai_smell_check.py --list-blocks <file> # 打印块与行号，便于定位

--inline 是给**风格库维护**用的：风格库每个条目的「可写句式」是单反引号包起来的一句话，
用户会直接复制进提示词，但它不是围栏块 → 默认模式扫不到。
打开后额外扫：带「可写句式 / 可复制 / 成套句」标签的非表格行里、长度 ≥6 且含中文的行内代码。
交付提示词本身仍用默认模式即可（交付物一律是围栏块）。

退出码：0 未检出 ｜ 1 检出错（含元说明等 FAIL 级）｜ 2 用法错误 ｜ 3 有输入未找到提示词块

与 CI 的关系（重要）：
  退出码按**最严重级别**给，不是"有输出就算过"。
  元说明（思考残留）是 FAIL 级 —— 它一定违规，必须清零；
  其余是 WARN 级 —— 需人工定性（比如"格外明显""手腕最后摆正"就属于正当写法，
  本脚本已用白名单上下文豁免，但真实文本里总有新的正当用法，
  所以 WARN 只报告、不自动判死）。
"""

import glob
import io
import os
import re
import sys

# ---------- 退出码 ----------
RC_OK = 0
RC_HIT = 1          # 检出（WARN 级）
RC_USAGE = 2        # 用法错误
RC_NO_BLOCK = 3     # 没有可检的提示词块（≠ 通过）

# ========== 词表 ==========

# A. 空话形容词（含变体）——「只禁原词 = 没禁」：电影感被禁后电影质感照样漏
HYPE = [
    "电影感", "电影质感", "电影级", "大片感", "大片质感", "院线感",
    "震撼", "震撼人心", "震撼力", "史诗感", "史诗级", "杰作", "巨作",
    "精致", "精美", "高级感", "高级", "质感十足", "质感拉满",
    "唯美", "唯美主义", "氛围感", "氛围拉满", "眼前一亮",
    "细腻", "极其细腻", "极致", "完美", "完美无瑕", "栩栩如生", "身临其境",
    "超高清", "高清画质", "4K", "8K", "HDR", "电影调色",
    "视觉盛宴", "极具冲击力", "冲击力十足", "美轮美奂", "令人惊叹", "叹为观止",
]

# A2. 否定形式豁免 —— HYPE 词直接跟在否定字后面 = 在**描述缺陷**，是正当写法。
#    实测误报：意大利新现实主义的可写句式「构图不完美，有人从镜头前挡住画面」——
#    「不完美」恰恰是这条风格要的东西，把它判成空话词会训练用户忽略工具。
#    注意：只把"否定字 + 词"里的**词**摘掉、留下否定字，
#    所以 `不完美` 不再计入 `完美`，而单独出现的 `完美` 照报。
NEG_PREFIX = "不无没未非"
_NEG_HYPE = {w: re.compile(r"([" + NEG_PREFIX + r"])" + re.escape(w)) for w in HYPE}


def _longest_match_counts(s, words):
    """按**最长匹配**计数，返回 {词: 次数}。

    为什么不能用 `s.count(w)` 逐词独立数（同 `shotlist_lint.py` 第 141 行同一坑，**实测踩过**）：
    HYPE 表里这些词互相包含——「完美⊂完美无瑕」「高级⊂高级感」「震撼⊂震撼人心 / 震撼力」
    「唯美⊂唯美主义」「细腻⊂极其细腻」共 6 组。一处词会被算成两处，总数虚高一倍
    （实测：`画面完美无瑕，高级感十足` 报 4 处，实为 2 处）。
    做法：按词长降序，从左到右扫，**每个位置只按最长的那个命中词计一次**，命中后跳过整词。
    """
    out = {}
    by_len = sorted(words, key=len, reverse=True)
    i, n = 0, len(s)
    while i < n:
        for w in by_len:
            if s.startswith(w, i):
                out[w] = out.get(w, 0) + 1
                i += len(w)
                break
        else:
            i += 1
    return out


def _strip_negated_hype(s):
    for pat in _NEG_HYPE.values():
        s = pat.sub(r"\1", s)
    return s

# B. 文件腔/报告腔 —— 最典型的"AI 写的"指纹
#    注意：只收「只有在写报告时才会用」的词。
#    「最后 / 同时 / 另外 / 又 / 既」在提示词里是正当的时序与并列描述
#    （实测误报：腕关节最后摆正 / 同时也是引导线），**已从表里剔除**。
#
#    ★ 2026-09-13 补漏（E23b 同类：漏报也算 bug）：
#    原表只收「XX出」形式，**漏掉了不带「出」的同义变体**
#    （实测：`整段呈现从犹豫到放手` 零命中，而 `整段呈现出…` 命中——
#     这两句是同一个毛病，只差一个「出」字）。
#
#    ⚠️ 但**不能**把「呈现/体现/展现/营造」裸词直接加进表——会误伤美术术语。
#    ★ 实测误报（2026-09-13，加了裸词后全库扫描立刻冒出 3 处）：
#        「同一个主体从多个视角同时呈现」   ← 立体主义的定义特征
#        「主体以线框与剖面呈现」           ← 工程蓝图风格
#        「[女性]以极强的侧影呈现」         ← 拉杰普特细密画
#    这三处都是**艺术史里的正当技术描述**（呈现＝被描绘/被表现），
#    不是报告腔。**误报会训练用户忽略工具**，必须排除。
#    → 正解：**裸词只在「报告腔句式」里才报**（见 DOC_TONE_PAT）。裸词本身放行。
DOC_TONE = [
    "综上所述", "总而言之", "值得注意的是", "需要注意的是", "请注意",
    "换言之", "也就是说", "不难看出", "由此可见",
    "旨在", "致力于", "具备", "呈现出", "展现出", "体现出", "营造出",
    "为的是", "从而", "进而", "以确保", "以便", "基于此", "在此基础",
    "使得", "让整个画面", "起到了", "发挥着",
]

# ★ 报告腔句式（2026-09-13）：裸词「呈现/体现/展现/营造」只有在这些**句式**里才判为文件腔。
#   判据：词前出现「整段/整体/本镜/画面/这里/全片/此处」这类**总结主语**，
#        或词后紧跟「出/了」再接抽象宾语。
#   为什么必须这样收窄：见上面 3 处实测误报——艺术史里的「呈现」是术语，
#   报告腔里的「呈现」是废话，区别在**主语是不是在"总结一段内容"**。
DOC_TONE_PAT = re.compile(
    r"(?:整段|整体|整个|本镜|本片|全片|这一段|画面|这里|此处|其|它)\s*"
    r"(?:呈现|体现|展现|营造)"
)

# C. 元说明/占位符（块内绝不允许）—— FAIL 级
META = [
    "（改成你的", "(改成你的", "（可替换", "(可替换", "*可选*", "可选*",
    "这里改成", "此处填", "填写你的", "按需修改", "根据需要", "示例：",
    "以下是", "如下所示", "//",
]
# 思考残留：行首出现这些 = 作者把"给自己的备注"写进了块里
META_LINE_PAT = re.compile(
    r"^\s*(?:【说明】|【注】|另注|注[:：]|备注|说明[:：]|附注|注意[:：]|提示[:：]|小注|PS[:：]|P\.S\.)|"
    r"^\s*[（(]\s*(?:说明|注|备注)\s*[:：)]|"
    r"^\s*#{1,6}\s*(?:说明|注|备注)\b"
)

# D. 双语并列：中文短语后面紧跟英文括注
BILINGUAL = re.compile(
    r"[\u4e00-\u9fff]{2,}\s*[（(]\s*[A-Za-z][A-Za-z0-9 ,/&'\-]{3,}\s*[)）]"
)

# E. 口水副词/程度副词堆砌
#    「非常 / 极其」这类单独出现时基本是把可测描述换成了情绪；
#    但若后面跟着**可测结果**（格外明显 / 十分清晰），是正当写法 → 见 GRADER_OK
FILLER = [
    "非常", "十分", "相当", "极其", "无比", "充分", "颇具",
    "渐渐地", "缓缓地", "静静地", "轻轻地", "默默地",
]
# 程度副词 + 可测结果 = 正当（实测：被低角度光照得格外明显）
GRADER_OK = re.compile(
    r"(?:格外|非常|十分|相当|极其|异常|无比)\s*"
    r"(?:明显|清晰|突出|锐利|平滑|干净|暗|亮|重|轻|慢|快|紧|松|薄|厚|干|湿)"
)

# F. 白名单：真术语，不算空话（词后跟了可测对象）
WHITELIST = [
    "细腻颗粒", "中间调细腻", "颗粒细腻", "细节插窗",
    "细腻灰度", "细腻过渡", "高光细腻", "暗部细腻",
]

# 负面语境标记：出现在「禁止/不要…」清单里的词是"要避免的东西"，不算正面使用
NEG_MARK = ("禁止", "禁用", "不要", "不得", "避免", "排除", "杜绝", "不允许", "规避", "反例", "无效写法")
# 反例标记行：整行是"✗ 电影感构图"这种教学对照
COUNTER_MARK = ("❌", "✗", "×", "反例", "无效写法", "不要写", "错误示例")

# 黑名单清单块：连续多行、行内**只有逗号分隔的词组**、且整块没有肯定句。
# 这类块是"漫剧黑名单 / 禁用词表"的排版形态（关键词在块首标题行，词本身没有标记词）——
# 若不识别，块内每个词都会被算成"正面使用"（实测误报：完美三点光 / 8K堆砌）。
BLOCKLIST_TITLE = ("黑名单", "禁用", "禁止", "不要用", "避免", "反例", "无效", "错误")
# 清单标签行："禁用：…" / "负向：…" / "禁止出现：" —— 命中后**其后连续行**都是清单
LIST_LABEL_PAT = re.compile(r"(?:禁用|负向|禁止|黑名单|不要|避免|排除|杜绝)\s*[:：]")
# 只在块内出现的"结构性提示词"——用户输入模板不是交付提示词，整块豁免
TEMPLATE_TITLE = ("模板", "填空", "话术", "你可以这样说", "开场句", "用户可", "口述",
                  "我说", "我做", "它给", "说想法", "拿到【")
# 填空位：整块含 ≥2 个【…】方括号槽位 → 是给用户填的模板，不是提示词
#   ★ 2026-09-20 修：**只数「行内」的槽位**——行首那一枚是**块头**，不算。
#   原因（实测假绿）：12 块提示词的块头天然有十几枚【…】，旧判据会把**整块豁免**，
#   于是 `【人物与环境】电影感十足、高级感、大片质感` 这种稿子报 PASS。
FILL_SLOT = re.compile(r"【[^】\n]{1,30}】")


def _fill_slot_count(text: str) -> int:
    """返回块内「行内填空槽」的数量：跳过每一行行首那枚块头。

    判据：块头＝行首的【…】；槽位＝同一行里非行首的【…】，或整行就是槽位（如 `【风格槽】`独占一行时
    仍算槽位——但那种行通常同时含"模板/话术"类字眼，会被 TEMPLATE_TITLE 命中）。
    """
    n = 0
    for ln in text.split("\n"):
        s = ln.lstrip()
        if s.startswith("【") and "】" in s:
            # 去掉行首的块头，只数这一行剩下的槽位
            s = s.split("】", 1)[1]
        n += len(FILL_SLOT.findall(s))
    return n
# 一行若是"逗号/顿号分隔、无句号、无动词性长句" → 判为清单项
_LIST_ITEM = re.compile(r"^[^。；;！!？?]{0,40}[，,、][^。；;！!？?]{0,40}$")


def _is_term_list(text):
    """判定这个块是不是"纯禁用词表 / 负向预置清单"（而非要提交的提示词）。

    排版实况：词表的标签常写在块**外面**的散文里（"## 十、AI 漫剧黑名单" / "规范负向预置："），
    块里只有一排逗号分隔的名词短语。所以判据必须**看块内的形态**，不能只看标记词：

      · 行内**没有句号**（有句号 = 是在写句子，不是列词）
      · 至少 2 行，且多数行是"逗号/顿号分隔的短词组"
      · 全块没有"：**"这类字段标签，也没有主谓结构

    命中则整块豁免——对它报"空话词"是噪音：它列的**正是要避免的词**。
    """
    lines = [s.strip() for s in text.split("\n") if s.strip()]
    if len(lines) < 2:
        return False
    if any("。" in s for s in lines):
        return False
    listy = sum(1 for s in lines if _LIST_ITEM.match(s))
    return listy >= max(2, int(len(lines) * 0.6))


def _is_template_note(text):
    """判定这个块是不是"给用户看的话术/填空模板"（而非交付给模型的提示词）。

    两条判据任一成立即豁免：
      ① 块内出现"模板 / 话术 / 我说 / 它给"这类字眼；
      ② 块内有 ≥2 个【…】填空槽位。
    为什么整块豁免：这类块里**故意**写着"电影感"这种词（给用户填空的示例），
    对它报 AI 味是噪音——**它不是要提交给模型的提示词**。
    """
    if any(k in text for k in TEMPLATE_TITLE):
        return True
    # 只数行内槽位：块头（行首的【…】）不算——否则 12 块稿会被整块豁免（2026-09-20 实测假绿）
    return _fill_slot_count(text) >= 2


# ========== 解析 ==========

def split_blocks(text):
    """返回 ([块文本…], 围栏是否成对)。"""
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


# 行内代码句：风格库的「可写句式」形态，以及各文件里的「写法 / 不要写」示范句。
# 只认带标签的行、跳过表格行与围栏标记，并要求长度 ≥6 且含中文
# —— 否则会把 `tone-realism.md` 这类文件名当提示词扫。
INLINE_PAT = re.compile(r"`([^`\n]+)`")
CJK_PAT = re.compile(r"[\u4e00-\u9fff]")
# 2026-09-12 补（E23 漏报）：原只认「可写句式/可复制/成套句」三种标签，
# 但 carrier-artifacts.md 等文件用「**写法**：`…`」给可直接复制的示范句 →
# 整类句子被静默跳过 = 假绿。这里把等价标签一并纳入。
INLINE_LABEL = ("可写句式", "可复制", "成套句", "写法：", "写法**：", "**写法**", "问法：", "**问法**")


def _inline_bodies(text):
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("|") or s.startswith("```"):
            continue
        if not any(k in s for k in INLINE_LABEL):
            continue
        for m in INLINE_PAT.finditer(s):
            t = m.group(1).strip()
            if len(t) >= 6 and CJK_PAT.search(t):
                out.append(t)
    return out


def _iter_lines_with_ctx(body):
    """逐行产出 (行内容, 是否处于负面/反例语境)。

    语境规则（按优先级）：
      ① 本行含负面标记词（禁止/不要…）或反例标记 → 该行起进入负向；
      ② 本行是**清单标签行**（"禁用：…" / "负向：…" / "黑名单："）→ 该行与**其后连续行**
         都算负向，直到空行。这是关键：黑名单常写成"禁用：完美三点光，8K堆砌，"
         然后**换行继续列词**，后续行本身没有标记词，逐行判会全部误报。
      ③ 空行 → 退出负向。
    """
    ctx_neg = False
    ctx_list = False
    for ln in body.split("\n"):
        s = ln.strip()
        if not s:
            ctx_neg = False
            ctx_list = False
            yield ln, False
            continue
        if ctx_list:
            yield ln, True
            continue
        if any(m in s for m in NEG_MARK) or any(m in s for m in COUNTER_MARK):
            ctx_neg = True
        if LIST_LABEL_PAT.search(s):
            ctx_list = True
            yield ln, True
            continue
        yield ln, ctx_neg


def scan(path, inline=False):
    """返回 (blocks, 提示词正文字符数, hits)。

    hits = [(类别, 词, 次数, 首个行号, 是否FAIL级)]

    inline=True 时，除 ``` 围栏块外，**把行内代码句也当提示词块扫**。
    为什么需要：风格库每个条目的「可写句式」是单反引号包起来的一句话，用户会直接复制
    进提示词，但它不是围栏块 → 默认模式扫不到，这批最该干净的句子长期无人检查。
    只收：带「可写句式 / 可复制 / 成套句」标签的**非表格行**里、长度 ≥6 且含中文的行内代码。
    """
    with io.open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    blocks, _balanced = split_blocks(text)
    if inline:
        blocks = blocks + _inline_bodies(text)

    hits = []
    total_len = 0
    for body in blocks:
        total_len += len(body)

        # 整块豁免①：用户话术/填空模板——这是给用户看的东西，不是交付的提示词
        if _is_template_note(body):
            continue
        # 整块豁免②：纯禁用词表 / 负向预置清单——它列的正是要避免的词，
        # 报"空话词"是噪音（标签常写在块外的散文里，所以看形态而非标记词）
        if _is_term_list(body):
            continue

        lines = list(_iter_lines_with_ctx(body))

        # 整块豁免②：黑名单/禁用词表——判定看块首标题行，命中则整块视为负面语境。
        # 为什么需要：黑名单常写成"标题行写『漫剧黑名单』+ 下面几行纯词表"，
        # 词表行本身没有"禁止/不要"，逐行判会全部误报成正面使用。
        head = "\n".join(body.split("\n")[:3])
        blocklist = any(k in head for k in BLOCKLIST_TITLE)
        if blocklist:
            lines = [(ln, True) for ln, _ in lines]

        # 元说明（FAIL 级）：负面语境里也照样违规
        for w in META:
            n = sum(ln.count(w) for ln, _ in lines)
            if n:
                first = next(i for i, (ln, _) in enumerate(lines, 1) if w in ln)
                hits.append(("元说明", w, n, first, True))
        for i, (ln, _) in enumerate(lines, 1):
            if META_LINE_PAT.search(ln):
                hits.append(("元说明", ln.strip()[:30], 1, i, True))

        # 其余（WARN 级）：负面语境豁免
        for cat, words in (("空话形容词", HYPE), ("文件腔", DOC_TONE), ("口水副词", FILLER)):
            cnt, first = {}, {}
            for i, (ln, isneg) in enumerate(lines, 1):
                if isneg:
                    continue
                s = ln
                # 白名单：先摘掉术语，再计数
                for wl in WHITELIST:
                    s = s.replace(wl, "")
                # 程度副词 + 可测结果 = 正当写法，从待检文本里摘掉
                s = GRADER_OK.sub("", s)
                # 否定形式（不完美 / 无瑕疵）＝ 描述缺陷，摘掉词、保留否定字
                if cat == "空话形容词":
                    s = _strip_negated_hype(s)
                # ★ 最长匹配（见 _longest_match_counts）：同一位置只按最长命中计一次
                found = _longest_match_counts(s, words)
                for w, c in found.items():
                    cnt[w] = cnt.get(w, 0) + c
                    first.setdefault(w, i)
            for w in words:
                if cnt.get(w):
                    hits.append((cat, w, cnt[w], first[w], False))

        # ★ 报告腔句式：裸词「呈现/体现/展现/营造」+ 总结主语（2026-09-13）
        #   只在这一句式里报，避免误伤「以轮廓呈现」这类美术术语。
        for i, (ln, isneg) in enumerate(lines, 1):
            if isneg:
                continue
            for m in DOC_TONE_PAT.finditer(ln):
                hits.append(("文件腔", m.group(0).strip(), 1, i, False))

        # 双语并列
        for i, (ln, isneg) in enumerate(lines, 1):
            if isneg:
                continue
            for m in BILINGUAL.finditer(ln):
                hits.append(("双语并列", m.group(0)[:40], 1, i, False))

    return blocks, total_len, hits


# ========== 报告 ==========

CAT_ORDER = ["元说明", "空话形容词", "文件腔", "双语并列", "口水副词"]


def report(files, inline=False):
    grand = {}
    worst = RC_OK
    scanned = 0
    for path in sorted(files):
        try:
            blocks, total, hits = scan(path, inline=inline)
        except (IOError, OSError) as e:
            sys.stderr.write("无法读取 %s：%s\n" % (path, e))
            worst = max(worst, RC_USAGE)
            continue
        if not blocks:
            print("=" * 70)
            print("文件：%s" % os.path.basename(path))
            print("  [SKIP] 没有 ``` 围栏内的提示词块 —— 无法检查（不等于通过）")
            worst = max(worst, RC_NO_BLOCK)
            continue

        scanned += 1
        print("=" * 70)
        print("文件：%s" % os.path.basename(path))
        print("代码块：%d 个 / 提示词正文字符：%d" % (len(blocks), total))
        if not hits:
            print("  [PASS] 未检出 AI 味特征")
            continue

        byc = {}
        for cat, w, n, line, is_fail in hits:
            byc.setdefault(cat, []).append((w, n, line, is_fail))
        for cat in CAT_ORDER:
            if cat not in byc:
                continue
            items = byc[cat]
            tot = sum(n for _, n, _, _ in items)
            is_fail = any(f for _, _, _, f in items)
            tag = "FAIL" if is_fail else "WARN"
            detail = "、".join(
                "%s×%d(L%d)" % (w, n, ln)
                for w, n, ln, _ in sorted(items, key=lambda x: -x[1])[:10]
            )
            print("  [%s|%s] 共 %d 处 → %s" % (tag, cat, tot, detail))
            grand[cat] = grand.get(cat, 0) + tot
            worst = max(worst, RC_HIT)

    print("=" * 70)
    if scanned == 0:
        print("[SKIP] 没有扫描到任何含提示词块的文件。")
        return max(worst, RC_NO_BLOCK)
    if not grand:
        if worst != RC_OK:
            print("总计：检查未完整完成，已检正文零命中")
            return worst
        print("总计：全部 PASS（零命中）")
        return RC_OK
    fail_cats = [c for c in CAT_ORDER if c in grand and c == "元说明"]
    print("总计：%s" % "，".join("%s %d 处" % (k, v) for k, v in sorted(grand.items(), key=lambda x: -x[1])))
    if fail_cats:
        print("[FAIL] 元说明（块内思考残留）必须清零——块内一切都会被当提示词执行。")
    print("[提醒] 零命中 ≠ 提示词好。WARN 级请人工定性；脚本不判质量。")
    return RC_HIT


# ========== 自检 ==========

SELF_TESTS = [
    # (说明, 文件内容, 期望命中的类别 or None)
    ("空话词与变体", "# t\n\n```\n电影感构图，电影质感调色，4K超高清\n```\n", "空话形容词"),
    ("元说明思考残留", "# t\n\n```\n另注：这里的风格可以调整\n```\n", "元说明"),
    ("双语并列", "# t\n\n```\n老陈坐在桌边 (Chen sitting at desk)\n```\n", "双语并列"),
    ("文件腔", "# t\n\n```\n综上所述，本镜旨在呈现出孤独\n```\n", "文件腔"),
    # --- 以下都应当"零命中"（曾经误报过的真实写法）---
    ("误报·时序[手腕最后摆正]", "# t\n\n```\n上臂先动、前臂跟随、手腕最后摆正\n```\n", None),
    ("误报·并列[同时也是引导线]", "# t\n\n```\n作为对峙的分界线，同时也是把视线牵引的引导线\n```\n", None),
    ("误报·程度副词+可测结果[格外明显]", "# t\n\n```\n眼下乌青被低角度光照得格外明显\n```\n", None),
    ("误报·负面清单[禁止电影感]", "# t\n\n```\n禁止出现：电影感调色、8K堆砌\n```\n", None),
    ("误报·反例行[✗ 电影感构图]", "# t\n\n```\n✗ 电影感构图\n✓ 低机位、主体偏画面一侧\n```\n", None),
    ("白名单术语[中间调细腻]", "# t\n\n```\n高光平滑滚降，中间调细腻颗粒，暗部成簇\n```\n", None),
    # --- 黑名单块 / 用户话术模板：都不算正面使用（实测误报）---
    ("误报·黑名单块[完美三点光/8K堆砌]", "# t\n\n```\n漫剧黑名单（出现即废）：\n大平光, 完美三点光, 处处补光,\n8K 超清堆砌, 超采样, 光线追踪\n```\n", None),
    ("误报·用户话术模板[写实电影感]", "# t\n\n```\n风格想要【写实电影感 / 美漫描边 / 其他】，整体感觉像【说一个你熟悉的作品】。\n```\n", None),
    ("误报·纯词表块[完美三点光/8K堆砌]", "# t\n\n```\n大平光, 完美三点光, 处处补光,\n8K 超清堆砌, 超采样, 光线追踪\n```\n", None),
    # --- 反例：不能因为"有逗号"就把真提示词误豁免 ---
    ("守正·真提示词不被误豁免", "# t\n\n```\n人物与环境：老陈坐在桌边，手平放在桌面。\n光位与影调：窗光从左上进入，光池边缘发脏。\n画面充满电影感。\n```\n", "空话形容词"),
    # ---- 否定形式（2026-09-12 加）----
    ("守正·否定形式[HYPE]不误报", "# t\n\n```\n构图随意、不完美，有人从镜头前挡住画面。\n```\n", None),
    ("守正·肯定形式仍照报", "# t\n\n```\n构图完美，皮肤纹理细腻。\n```\n", "空话形容词"),
    # ---- 行内代码句（--inline，2026-09-12 加）----
    ("默认·行内代码不扫", "# t\n\n- **可写句式**：`这是一句充满电影感的废话句子`\n", None),
    ("inline·行内可写句式扫到", "# t\n\n- **可写句式**：`这是一句充满电影感的废话句子`\n", "空话形容词", True),
    ("inline·表格行与短术语不扫", "# t\n\n| 量级 | `4K 超高清 电影感` |\n\n- **可写句式**：`黑泽明式`\n", None, True),
    ("inline·否定形式不误报", "# t\n\n- **可写句式**：`构图随意、不完美，有人从镜头前挡住画面`\n", None, True),
    # ---- 文件腔"无出"变体（2026-09-13 补漏）----
    ("守正·无出变体[整段呈现从…到…]", "# t\n\n```\n女孩把信放下。整段呈现从犹豫到放手的完整过程。\n```\n", "文件腔"),
    ("守正·无出变体[体现出]", "# t\n\n```\n女孩把信放下。这里体现出她内心的挣扎。\n```\n", "文件腔"),
    ("守正·有出变体[呈现出]", "# t\n\n```\n本镜旨在呈现出孤独\n```\n", "文件腔"),
    # ---- ★ 误报守正：美术术语里的「呈现」不得报（2026-09-13 实测 3 例）----
    ("误报·美术术语[多个视角同时呈现]", "# t\n\n```\n立体主义，同一个主体从多个视角同时呈现，形体被分解成几何切面\n```\n", None),
    ("误报·美术术语[以线框与剖面呈现]", "# t\n\n```\n工程蓝图风格，主体以线框与剖面呈现\n```\n", None),
    ("误报·美术术语[以极强的侧影呈现]", "# t\n\n```\n印度拉杰普特细密画风格，女性以极强的侧影呈现\n```\n", None),
    ("误报·'呈现'不在句尾不作报告腔?", "# t\n\n```\n画面里出现了一把伞\n```\n", None),
    # ---- 行内示范句标签扩展（2026-09-12 加，E23 漏报修复的守正用例）----
    ("inline·写法标签的示范句也扫到", "# t\n\n> **写法**：`画面右侧窗口的光源向上拖出一道唯美的淡影`\n", "空话形容词", True),
    ("inline·写法标签的干净句放行", "# t\n\n> **写法**：`画面右侧窗口的光源向上拖出一道淡影`\n", None, True),
]


def self_test():
    import tempfile
    ok = fail = 0
    for case in SELF_TESTS:
        name, content, expect = case[0], case[1], case[2]
        inline = case[3] if len(case) > 3 else False
        fd, path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(content)
            _b, _t, hits = scan(path, inline=inline)
        finally:
            os.unlink(path)
        cats = set(c for c, _w, _n, _l, _f in hits)
        if expect is None:
            good = not cats
        else:
            good = expect in cats
        if good:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            fail += 1
            print("  [NG]   %s —— 期望 %s，实得 %s" % (name, expect or "零命中", sorted(cats) or "零命中"))
    print("\n自检：%d 通过 / %d 失败" % (ok, fail))
    return RC_OK if fail == 0 else RC_HIT


def list_blocks(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    blocks, balanced = split_blocks(text)
    print("文件：%s" % path)
    print("围栏成对：%s ｜ 块数：%d" % ("是" if balanced else "否（有未闭合的 ```）", len(blocks)))
    for i, body in enumerate(blocks, 1):
        first = body.split("\n")[0][:60] if body.strip() else "（空块）"
        print("  块%d：%d 行 ｜ 首行：%s" % (i, len(body.split("\n")), first))
    return RC_OK


def main(argv):
    args = [a for a in argv[1:]]
    if not args:
        sys.stderr.write(__doc__)
        return RC_USAGE
    if "--self-test" in args:
        return self_test()
    if "--list-blocks" in args:
        rest = [a for a in args if a != "--list-blocks"]
        if not rest:
            sys.stderr.write("--list-blocks 需要一个文件路径\n")
            return RC_USAGE
        return list_blocks(rest[0])

    inline = "--inline" in args
    args = [a for a in args if a != "--inline"]

    files = []
    for p in args:
        if p.startswith("-"):
            sys.stderr.write("未知参数：%s\n" % p)
            return RC_USAGE
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.md"), recursive=True)
        elif os.path.isfile(p):
            files.append(p)
        else:
            sys.stderr.write("路径不存在：%s\n" % p)
            return RC_USAGE
    if not files:
        sys.stderr.write("没有找到任何 .md 文件。\n")
        return RC_USAGE
    return report(files, inline=inline)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
