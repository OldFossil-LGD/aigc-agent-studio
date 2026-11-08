#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""故事板检查器（把「平台自适应 + 可迭代」从文档变成门禁）

为什么要有它：`storyboard-frame.md` 里的"输出模式声明 / 张数 ≤ 平台上限 / 五段骨架 /
参数块 / 实测回写位"全是**规则**——而**一条规则若没有任何东西会因它失败而报错，它等于不存在**。
本库已经栽过一次：排镜表存在多年但没人检查，结果"中近景一家独大"照旧发生。
本脚本把那几条规则变成**机器可判的门禁**。

退出码（与 audit_prompt.py / shotlist_lint.py 一致）：
  0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN

用法：
  python3 scripts/storyboard_lint.py <故事板文件.md>
  python3 scripts/storyboard_lint.py --self-test

FAIL 与 WARN 的分工（**刻意只留两条 FAIL**，避免噪声淹没真问题）：
  FAIL ① 张数 > 平台上限        —— 硬撞墙，投出去就报错或默默截断
  FAIL ② 缺输出模式声明         —— 没有它，"张数对不对"根本无法判定
  其余一律 WARN（纯灰度 / 一致性锚点只写一次 / 参数块 / 回写位 / 长度档），需人工定性。

为什么"缺输出模式声明"要判 FAIL 而不是 WARN：
  它是**本文件唯一的结构性前提**——没有它，脚本无法选上限，人也无法判断这条提示词
  会在平台上超限还是被截断。它是"能不能用"的问题，不是"好不好"的问题。
"""
from __future__ import print_function

import io
import os
import re
import sys

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = 0, 1, 2, 3, 4

# ---------- 平台上限 ----------
# image2：官方分两档——普通/Instant 上限 4，Thinking 上限 8（未标模式按保守的 4 判）
# 即梦：官方接口文档「输出图最大数量 = 15 − 输入图数量」（火山引擎 docs/85621/1863351）
# 可灵：官方发布说明有组图模式，官方示例为 6 张分镜（未给硬上限 → 按示例值当尺子）
# Runway：官方帮助中心「outputs 2 panels」（固定值，H2 待验证是否可配）
IMAGE2_INSTANT = 4     # image2 普通/Instant 档
IMAGE2_THINKING = 8    # image2 Thinking 档（**必须显式声明，不声明不给 8**）
JIYANG_TOTAL = 15      # 即梦公式里的常数，**不要**把 15 当固定张数用
KLING_EXAMPLE = 6      # 可灵官方示例张数
RUNWAY_FIXED = 2       # Runway Story Panels 固定 2

# 平台识别（顺序敏感：更具体的先匹配）
PLATFORMS = [
    ("image2", ("image2", "Image2", "GPT Image 2", "GPT-Image-2", "gpt-image-2", "GPT Image2")),
    ("即梦", ("即梦", "seedream", "Seedream")),
    ("可灵", ("可灵", "kling", "Kling")),
    ("Runway", ("Runway", "runway", "Story Panels")),
    ("Midjourney", ("Midjourney", "midjourney", "--sref", "MJ ")),
    ("SD", ("Stable Diffusion", "SDXL", "ControlNet")),
]

# image2 的模式声明：`模式=Thinking`。**不写就不给 8**——8 是 Thinking 档才有的。
MODE_PAT = re.compile(r"模式\s*[=＝:：]\s*(Thinking|thinking|思考|普通|Instant|instant)")

# 输出模式声明：`输出模式：… | 平台=X | 张数=N | 单张比例=…`
DECL_PAT = re.compile(r"输出模式\s*[:：]")
PLAT_PAT = re.compile(r"平台\s*=\s*([^|｜\n]+)")
COUNT_PAT = re.compile(r"张数\s*=\s*(\d+)")
INPUT_PAT = re.compile(r"输入图数\s*=\s*(\d+)")

# 参数块 / 回写位（可迭代机制的两件"有地方落"的东西）
PARAM_PAT = re.compile(r"——\s*故事板参数\s*——")
WRITEBACK_PAT = re.compile(r"【实测回写】")

# 五段骨架的标志词
SEG_STYLE = ("风格锚点", "全组统一")
SEG_CONSIST = ("一致性锚点",)
SEG_GRID = re.compile(r"第\s*\d+\s*格")
SEG_BAN = ("禁止项", "禁止出现", "全组不出现")

# 灰度纪律：说了灰度才算写了；出现彩色词则报
GRAY_KEYS = ("纯灰度", "黑、白、灰", "黑白灰", "只有黑", "灰度")
COLOR_WORDS = ("彩色滤镜", "暖色", "冷色", "彩色光晕", "色温")

# 长度档：Runway 要短
LENGTH_LONG = ("长（即梦", "长度档：长", "长度档=长")
LENGTH_SHORT = ("短（Runway", "长度档：短", "长度档=短")

# 单画布多格（**禁止**）：拼版 / 分格线 / 九宫格。注意与"原生组图多文件"区分——
# 后者是本库**推荐**的路径 A，判据是"每格独立成文件"，不是"一张画布切几格"。
PANEL_BAN = ("拼版", "分格线", "九宫格", "四格一张", "漫画分格")
# 禁止语境的**开启词**：「禁止出现：」「【禁止出现】」「全组不出现：」等。
# ★ 含 `不拼版` / `各出一张` 这类**正面表述里的否定式**——本库模板真实写法是
#   「八个镜头各出一张独立画格，不拼版」，若不当成禁止语境会报假 WARN（实测踩到）。
BAN_OPENERS = ("禁止出现", "禁止：", "全组不出现", "不要出现", "不得出现",
               "避免出现", "不出现", "风险移除", "不要写", "禁止", "避免", "不得",
               "不拼版", "不合成", "不要合成", "各出一张", "独立画格", "独立文件")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _detect_platform(text):
    low = text
    for name, keys in PLATFORMS:
        for k in keys:
            if k in low:
                return name
    return None


def _cap_for(platform, n_input, decl=""):
    """返回 (上限, 说明)。image2 分模式；即梦走公式；可灵走官方示例值；Runway 固定；其余 None。

    **image2 的 cap 靠 `模式=` 声明定档**：声明 Thinking → 8；否则一律按**保守的 4** 判。
    刻意**不做"没声明就按 8 放行"**——那等于把"写了 8 却跑普通档"这个真实翻车点放过去。
    """
    if platform == "image2":
        m = MODE_PAT.search(decl or "")
        mode = m.group(1).lower() if m else ""
        if mode in ("thinking", "思考"):
            return IMAGE2_THINKING, "image2 Thinking 档上限 = %d" % IMAGE2_THINKING
        return IMAGE2_INSTANT, ("image2 普通档上限 = %d（未声明「模式=Thinking」，"
                                "故按保守档判——要用 8 必须在声明里写「模式=Thinking」）"
                                % IMAGE2_INSTANT)
    if platform == "即梦":
        return JIYANG_TOTAL - n_input, "即梦官方公式：15 − 输入图数(%d) = %d" % (n_input, JIYANG_TOTAL - n_input)
    if platform == "可灵":
        return KLING_EXAMPLE, "可灵官方示例张数 = %d" % KLING_EXAMPLE
    if platform == "Runway":
        return RUNWAY_FIXED, "Runway Story Panels 固定输出 = %d" % RUNWAY_FIXED
    return None, "该平台无原生故事板层（走路径 C：一镜一请求，张数=1）"


def _neg_ctx_scan(body, words):
    """返回"命中 words 但**不在禁止语境**里"的命中词列表。

    **为什么要 carry-forward（上下文跨行延续）**：
    提示词的禁止清单是**跨行**写的——本库自己的模板就是：

        禁止出现：彩色，颜色，彩色滤镜，色温，暖色，冷色，彩色光晕，
        分格，拼版，漫画分格线，文字，数字，字幕，水印，

    第二行**没有任何禁止标记**（标记在第一行行首）。按"逐行独立判定"会把第二行
    全部判成违规 → **假 WARN**。E23：误报与漏报都算 bug，固定假噪声会让人忽略 WARN。

    **规则**：某行出现禁止标记 → 该行与其后**连续非空行**都算禁止语境；遇空行复位。
    """
    bad, in_ban = [], False
    for ln in body.split("\n"):
        s = ln.strip()
        if not s:
            in_ban = False
            continue
        if any(c in s for c in BAN_OPENERS):
            in_ban = True
        if in_ban:
            continue
        hit = [w for w in words if w in s]
        if hit:
            bad.extend(hit)
    return bad


def _split_blocks(text):
    """返回 [(起始行号, 块内容)]——**只查围栏内的东西**。

    为什么必须限定在围栏内：本库的 `references/*.md` 是**规格文档**，正文里到处是
    示例句（"张数=6""不拼版"）。全文扫描会把这些示例当成真实声明 → **假 WARN**。
    E23 纪律：**误报与漏报都算 bug**——固定的假噪声会让人开始忽略 WARN。
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
    return blocks


def _is_meta_block(body):
    """判断一个围栏是不是**元信息块**（参数块 / 回写位 / 示例），而不是提示词块。

    参数块与回写位**也是围栏**（它们要能被整段复制进交付文档），但**不该有输出模式声明**。
    不做这个区分，每份合规交付物都会稳定吐 2 条假 FAIL → 与 E23（误报也 bug）冲突。
    """
    return bool(PARAM_PAT.search(body) or WRITEBACK_PAT.search(body))


def lint(text):
    """返回 (fails, warns, notes, n_blocks)。纯函数，便于自检。"""
    fails, warns, notes = [], [], []

    blocks = _split_blocks(text)
    n_blocks = len(blocks)
    if n_blocks == 0:
        return fails, warns, notes, 0

    # --- FAIL ① 输出模式声明（**逐块查**）---
    # 为什么逐块：一份交付物常有**多批组图**（17 镜 > 即梦 14 上限 → 拆两批）。
    # 只查全文第一个声明，会让"批 2 写错张数"完全逃过检查（实测踩到的覆盖漏洞）。
    #
    # **但不是每个围栏都是提示词块**：参数块与回写位也是围栏（它们同样要能被整段复制），
    # 却不该有输出模式声明。判据用它们的标志物排除——否则每份合规交付物稳定吐 2 条假 FAIL。
    prompt_blocks = [(s, b) for s, b in blocks if not _is_meta_block(b)]
    n_blocks = len(prompt_blocks)
    if not prompt_blocks:
        return fails, warns, notes, 0
    body = "\n".join(b for _s, b in prompt_blocks)
    for start, b in prompt_blocks:
        if not DECL_PAT.search(b):
            fails.append("L%d 提示词块内缺「输出模式：」声明——**这是本检查唯一的结构前提**："
                         "没有它就无法判定张数会不会超平台上限。写法见 storyboard-frame.md §4.1"
                         "　★ **先确认这一块是不是「视频提示词块」**（带着【镜头规格】【时间线】【声音】"
                         "那类块名的）——是的话，这就是**口径问题不是内容问题**：本脚本只吃故事板文件，"
                         "它会逐个检查故事板提示词围栏。**处置：把故事板块单独存一个文件再跑**"
                         "（正对上本库「两块分开给、各自可复制」的交付形态）。" % start)

    # 平台：取**第一个带声明的块**里的平台
    platform = None
    decl_line = None
    for _s, b in prompt_blocks:
        for ln in b.split("\n"):
            if DECL_PAT.search(ln):
                decl_line = ln
                break
        if decl_line:
            break
    m_plat = PLAT_PAT.search(decl_line) if decl_line else None
    if not m_plat:
        m_plat = PLAT_PAT.search(body)
    if m_plat:
        platform = m_plat.group(1).strip()
        for name, keys in PLATFORMS:
            if any(k in platform for k in keys):
                platform = name
                break

    # --- FAIL ② 张数 vs 平台上限（**逐提示词块查**：多批交付物每批各有自己的张数）---
    seen_count = False
    for start, b in prompt_blocks:
        m_cnt_b = COUNT_PAT.search(b)
        if not m_cnt_b:
            continue
        seen_count = True
        n_out = int(m_cnt_b.group(1))
        # 平台与输入图数优先取本块内的；取不到则回落到全文的
        m_plat_b = PLAT_PAT.search(b)
        plat_b = platform
        if m_plat_b:
            plat_b = m_plat_b.group(1).strip()
            for name, keys in PLATFORMS:
                if any(k in plat_b for k in keys):
                    plat_b = name
                    break
        m_in_b = INPUT_PAT.search(b) or INPUT_PAT.search(text)
        n_in = int(m_in_b.group(1)) if m_in_b else 0
        # image2 的档位来自**本块首行声明**（模式=Thinking）；取不到则回落到全文的声明行
        m_decl_b = None
        for _ln in b.split("\n"):
            if DECL_PAT.search(_ln):
                m_decl_b = _ln
                break
        cap, why = _cap_for(plat_b, n_in, m_decl_b or decl_line or "")
        if cap is not None and n_out > cap:
            fails.append("L%d 张数 %d **超过** %s 上限 %d（%s）——投出去会报错或被静默截断；"
                         "**拆成两批**，不硬塞（storyboard-frame.md §4.1）"
                         % (start, n_out, plat_b, cap, why))
        elif cap is not None:
            notes.append("L%d 张数 %d ≤ %s 上限 %d（%s）" % (start, n_out, plat_b, cap, why))

    if not seen_count and DECL_PAT.search(body):
        warns.append("输出模式声明里没写「张数= N」——张数是跨平台唯一会直接撞墙的变量")
    if seen_count and not platform:
        warns.append("写了张数但没写平台——**没有平台就无法判上限**（即梦 15 / 可灵 6 / Runway 2 差很多）")

    # 声明与参数块的平台不一致 → WARN（真实错配，比"没写平台"更隐蔽）
    m_param = re.search(r"平台与张数\s*[:：]\s*([^\n=＝]+)", text)
    if m_param and platform:
        p_norm = m_param.group(1).strip()
        for name, keys in PLATFORMS:
            if any(k in p_norm for k in keys):
                if name != platform:
                    warns.append("**声明与参数块的平台不一致**：声明=%s，参数块=%s"
                                 "——改平台时两处都要改，只改一处会让长度档与张数判错"
                                 % (platform, name))
                break

    # --- WARN：长度档与平台匹配（Runway 要短）---
    # 长度档写在**块外**的参数块里，故用全文 text
    if platform == "Runway":
        if any(k in text for k in LENGTH_LONG):
            warns.append("Runway 标了「长」长度档——官方明确「optimized…**focused description is enough**」"
                         "且上限 1000 字符，**该用短档**（storyboard-platforms.md §四）")
        elif any(k in text for k in LENGTH_SHORT):
            notes.append("Runway 用了短档，与官方要求一致")
        else:
            warns.append("Runway 未标长度档——它上限 1000 字符，建议显式写「短」")
    elif platform in ("即梦", "可灵"):
        if any(k in text for k in LENGTH_SHORT):
            warns.append("%s 标了「短」长度档——该平台可长，短档会丢掉构图与明暗细节" % platform)

    # --- WARN：五段骨架要素（只在块内查——正文里的说明不算）---
    if not any(k in body for k in SEG_STYLE):
        warns.append("提示词块内没看到**风格锚点行**（画法族 + 明暗结构 + 构图纪律）——跨格一致性靠它锁")
    if not any(k in body for k in SEG_CONSIST):
        warns.append("提示词块内没看到**一致性锚点行**——多格角色不像同一个人，多半是缺这一行")
    if not SEG_GRID.search(body) and platform in ("即梦", "可灵"):
        notes.append("未检出「第N格」逐格行——若这是单镜模板（路径 C）属正常")
    if not any(k in body for k in SEG_BAN):
        warns.append("提示词块内没看到**全组禁止项**——多格最常见的翻车是拼版线与文字混进画面")

    # --- WARN：灰度纪律（只查块内）---
    if not any(k in body for k in GRAY_KEYS):
        warns.append("提示词块内没看到「纯灰度 / 黑、白、灰」类字样——灰度没写死，出图容易带色")
    hits = [w for w in COLOR_WORDS if w in body]
    if hits:
        bad = _neg_ctx_scan(body, hits)
        if bad:
            warns.append("出现彩色相关词（%s）却没在禁止语境里——故事板只讲明暗，"
                         "色彩属板块二（storyboard-frame.md §7.1）" % "、".join(sorted(set(bad))[:3]))

    # --- WARN：单画布多格（要与"原生组图多文件"区分）---
    bad_panel = _neg_ctx_scan(body, PANEL_BAN)
    if bad_panel:
        warns.append("出现「%s」但不在禁止语境——**单画布多格是禁止的**"
                     "（原生组图出 N 张独立文件才是推荐路径，见 §二）" % bad_panel[0])

    # --- WARN：可迭代机制两件套（写在块外，故用全文）---
    if not PARAM_PAT.search(text):
        warns.append("缺「—— 故事板参数 ——」参数块——**迭代＝调旋钮**，没有参数块就只能重写全文")
    if not WRITEBACK_PAT.search(text):
        warns.append("缺「【实测回写】」位——经验**没有地方落**，下一轮还会踩同一个坑")

    return fails, warns, notes, n_blocks


def cmd_lint(path):
    if not os.path.exists(path):
        print("[用法错误] 文件不存在：%s" % path)
        return RC_USAGE
    text = read(path)

    # **用途守卫**：本脚本查的是**交付物的故事板文件**，不是 skill 的规格文档。
    # 规格文档里的代码围栏装的是**模板与示例**（含 `张数=[N]`、`长度档：长/短` 两个选项），
    # 拿它当提示词查会稳定产出假 WARN。E23：误报与漏报都算 bug。
    # 判据：文件在 skill 的 references/ 下，或首行是"何时读 / 读完回"的规格导语。
    in_refs = os.path.sep + "references" + os.path.sep in path or \
        path.replace("\\", "/").startswith("references/")
    head = "\n".join(text.split("\n")[:6])
    is_spec = "何时读" in head or "读完回" in head
    if in_refs or is_spec:
        print("文件：%s" % path)
        print("[SKIP] 这看起来是**规格文档**（模板与示例），不是交付物故事板。")
        print("       本脚本查的是交付文件的张数上限与五段骨架；规格文档的围栏里装的是模板，")
        print("       用提示词规则去查会稳定产出假 WARN（E23：误报也算 bug）。")
        print("       要查交付物，请指向实际交付的故事板 .md。")
        return RC_EMPTY

    fails, warns, notes, n_blocks = lint(text)

    if n_blocks == 0:
        print("文件：%s" % path)
        print("提示词块：0 个\n")
        print("[EMPTY] 没有找到任何提示词围栏——无法判定。")
        print("        可能原因：① 这不是故事板文件；② 提示词没放进 ``` 围栏；③ 贴错了文件。")
        print("        ⚠️ 这不是 PASS，是'没验到'——退出码 3。")
        return RC_EMPTY

    print("文件：%s" % path)
    print("提示词块：%d 个\n" % n_blocks)

    for n in notes:
        print("  [--]   %s" % n)
    for w in warns:
        print("  [WARN] %s" % w)
    for f in fails:
        print("  [FAIL] %s" % f)

    if fails:
        print("\n[FAIL] %d 条结构问题。" % len(fails))
        return RC_FAIL
    if warns:
        print("\n[WARN] %d 条需人工定性（脚本不判质量）。" % len(warns))
        return RC_WARN
    print("\n[PASS] 结构完整——**不等于**可以交付，最终判据仍在实跑与 review-passes.md。")
    return RC_OK


# ---------- 自检 ----------
def _run(fn, text):
    """把 text 写进临时文件再跑，返回 (rc, stdout)。"""
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return fn(p), p
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def self_test():
    print("storyboard_lint.py 自检\n")

    # 合格的组图故事板（五段齐 + 参数块 + 回写位 + 张数在上限内）
    GOOD = (
        "# 故事板 牛仔对决 1/4\n\n"
        "—— 故事板参数 ——\n"
        "路径：A 原生组图\n平台与张数：即梦=6\n长度档：长（即梦·可灵）\n"
        "风格锚点来源：资产图风格样张\n\n"
        "```\n"
        "输出模式：原生组图 | 平台=即梦4.0 | 张数=6 | 单张比例=16:9\n"
        "全组统一风格锚点：写实灰度，铅笔与炭笔质感；主光单侧硬光，明暗交界柔和；"
        "主体偏三分之一，反侧留大片暗部负空间。\n"
        "全组统一一致性锚点：戴宽檐帽的骑手，右颊一道旧疤；镇口土路与酒馆门廊；"
        "右手搭在枪套搭扣上。\n"
        "第1格（大远景｜建立）：骑手只剩一个黑影立在镇口路中，面朝左前方的酒馆。\n"
        "第2格（大特写｜揭示）：他的右手食指在枪套搭扣上，指节发白。\n"
        "第3格（中景｜推进）：酒馆门帘被掀起一道缝，里面有人影。\n"
        "第4格（近景｜反应）：骑手眼皮微微压下来，嘴角绷紧。\n"
        "第5格（全景｜推进）：两人在街道两端站定，间距大约二十步。\n"
        "第6格（大特写｜峰值）：搭扣弹开，金属反光最亮。\n"
        "全组统一：纯灰度，全画面只有黑、白、灰三种明度；"
        "全组不出现：分格，拼版，漫画分格线，文字，数字，彩色，暖色，冷色。\n"
        "```\n\n"
        "【实测回写】\n"
        "2026-09-14｜平台=即梦4.0｜张数=6｜结果=5张可用/1张崩手｜建议=张数降到5\n"
    )

    # 张数超即梦上限：写 16 张，输入 0 图 → 上限 15
    OVER_CAP = GOOD.replace("张数=6", "张数=16").replace("即梦=6", "即梦=16")

    # 缺输出模式声明
    NO_DECL = GOOD.replace(
        "输出模式：原生组图 | 平台=即梦4.0 | 张数=6 | 单张比例=16:9\n", "")

    # 空文件 → 3
    EMPTY = "# 只是正文，没有围栏\n"

    # Runway 标了长档 → WARN（**参数块也要改成 Runway**，否则测的是"声明与参数块不一致"）
    RUNWAY_LONG = GOOD.replace("平台与张数：即梦=6", "平台与张数：Runway=2") \
                      .replace("平台=即梦4.0", "平台=Runway") \
                      .replace("张数=6", "张数=2")

    # Runway 上限 2，写 6 → FAIL
    RUNWAY_OVER = GOOD.replace("平台与张数：即梦=6", "平台与张数：Runway=6") \
                      .replace("平台=即梦4.0", "平台=Runway")

    # 声明与参数块平台不一致 → WARN（改平台只改了一处）
    PLAT_MISMATCH = GOOD.replace("平台与张数：即梦=6", "平台与张数：Runway=2")

    # 即梦公式：1 图输入 → 上限 14；写 15 应 FAIL
    JIYANG_FORMULA = GOOD.replace("张数=6", "张数=15").replace("即梦=6", "即梦=15").replace(
        "平台=即梦4.0", "平台=即梦4.0 | 输入图数=1")

    # 即梦公式：9 图输入 → 上限 6；写 6 应 PASS（这条防"把 15 当固定张数"的回退）
    JIYANG_FORMULA_OK = GOOD.replace(
        "平台=即梦4.0", "平台=即梦4.0 | 输入图数=9")

    # 缺参数块与回写位 → WARN
    NO_ITER = GOOD.replace("—— 故事板参数 ——\n路径：A 原生组图\n平台与张数：即梦=6\n"
                           "长度档：长（即梦·可灵）\n风格锚点来源：资产图风格样张\n\n", "") \
                  .replace("【实测回写】\n"
                           "2026-09-14｜平台=即梦4.0｜张数=6｜结果=5张可用/1张崩手｜建议=张数降到5\n", "")

    # 出彩色词且**全文没有任何禁止语境** → WARN
    # 注意：原 GOOD 的禁止项行含「彩色，暖色，冷色」，会命中豁免——
    # 所以这个 fixture 必须**连禁止项行里的彩色词一起拿掉**，才是真的"不在禁止语境"。
    NO_BAN_LINE = GOOD.replace(
        "全组不出现：分格，拼版，漫画分格线，文字，数字，彩色，暖色，冷色。",
        "全组不出现：分格，拼版，漫画分格线，文字，数字。")
    COLORED = NO_BAN_LINE.replace("全组统一一致性锚点", "暖色调，冷色光晕；全组统一一致性锚点")

    # 禁止清单**跨行**书写（禁止标记在第一行行首）→ 第二行不该被判违规。
    # 这条防的正是本库模板的真实写法，且实测踩到过假 WARN。
    MULTILINE_BAN = (
        "—— 故事板参数 ——\n路径：A 原生组图\n平台与张数：即梦=6\n长度档：长（即梦·可灵）\n"
        "风格锚点来源：资产图风格样张\n\n"
        "```\n"
        "输出模式：原生组图 | 平台=即梦4.0 | 张数=6 | 单张比例=16:9\n"
        "全组统一风格锚点：写实灰度，铅笔与炭笔质感。\n"
        "全组统一一致性锚点：戴宽檐帽的骑手，右颊一道旧疤。\n"
        "第1格（大远景｜建立）：骑手立在镇口路中。\n"
        "禁止出现：彩色，颜色，色温，暖色，冷色，\n"
        "分格，拼版，漫画分格线，文字，数字，字幕，水印。\n"
        "```\n\n"
        "【实测回写】\n2026-09-14｜平台=即梦4.0｜张数=6｜结果=6张可用\n"
    )

    # ★ 防回退：**多批交付物**——批1 张数正常、批2 超限。
    # 早先只查全文第一个声明 → 批2 写错张数**完全逃过检查**（实测踩到的覆盖漏洞）。
    MULTI_BATCH = (
        "—— 故事板参数 ——\n路径：A 原生组图\n平台与张数：即梦=9（批1）＋ 即梦=99（批2）\n"
        "长度档：长（即梦·可灵）\n风格锚点来源：批1 第1格\n\n"
        "```\n"
        "输出模式：原生组图 | 平台=即梦4.0 | 张数=9 | 单张比例=16:9\n"
        "全组统一风格锚点：写实灰度，铅笔与炭笔质感。\n"
        "全组统一一致性锚点：戴宽檐帽的骑手。\n"
        "第1格（大远景｜建立）：骑手立在镇口路中。\n"
        "全组统一：纯灰度，只有黑、白、灰三种明度；\n"
        "全组不出现：分格，拼版，彩色，暖色。\n"
        "```\n\n"
        "```\n"
        "输出模式：原生组图 | 平台=即梦4.0 | 张数=99 | 单张比例=16:9\n"
        "全组统一风格锚点：写实灰度，铅笔与炭笔质感。\n"
        "全组统一一致性锚点：戴宽檐帽的骑手。\n"
        "第1格（插入｜峰值）：帽子飞起。\n"
        "全组统一：纯灰度，只有黑、白、灰三种明度；\n"
        "全组不出现：分格，拼版，彩色，暖色。\n"
        "```\n\n"
        "【实测回写】\n2026-09-14｜张数=9\n"
    )

    # ★ image2 分档：未声明 Thinking → 按保守的 4 判，写 8 应 FAIL
    IMAGE2_NO_MODE = GOOD.replace("平台与张数：即梦=6", "平台与张数：image2=8") \
                         .replace("平台=即梦4.0", "平台=image2").replace("张数=6", "张数=8")

    # ★ image2 分档：声明了 Thinking → 8 可达，写 8 应 PASS
    IMAGE2_THINKING = GOOD.replace("平台与张数：即梦=6", "平台与张数：image2=8") \
                          .replace("平台=即梦4.0", "平台=image2 | 模式=Thinking") \
                          .replace("张数=6", "张数=8")

    # ★ image2 分档：即使声明 Thinking，写 9 仍超 8 → FAIL
    IMAGE2_OVER = GOOD.replace("平台与张数：即梦=6", "平台与张数：image2=9") \
                      .replace("平台=即梦4.0", "平台=image2 | 模式=Thinking") \
                      .replace("张数=6", "张数=9")

    # ★ 防回退：正面表述里的否定式（「各出一张独立画格，不拼版」）**不该被当成
    #   非禁止语境的"拼版"命中**——实测在 image2 版交付物上报过一次假 WARN。
    PANEL_NEG_OK = GOOD.replace(
        "第1格（大远景｜建立）：骑手只剩一个黑影立在镇口路中，面朝左前方的酒馆。",
        "第1格（大远景｜建立）：骑手只剩一个黑影立在镇口路中。六镜各出一张独立画格，不拼版。")

    cases = [
        ("合格组图故事板 → 0", cmd_lint, GOOD, RC_OK),
        ("张数 16 > 即梦上限 15 → 1", cmd_lint, OVER_CAP, RC_FAIL),
        ("缺输出模式声明 → 1", cmd_lint, NO_DECL, RC_FAIL),
        ("没有围栏（贴错文件）→ 3", cmd_lint, EMPTY, RC_EMPTY),
        ("Runway 写 6 > 固定 2 → 1", cmd_lint, RUNWAY_OVER, RC_FAIL),
        ("即梦 输入1图 写15 > 上限14 → 1", cmd_lint, JIYANG_FORMULA, RC_FAIL),
        ("即梦 输入9图 写6 ≤ 上限6 → 0（公式而非固定15）", cmd_lint, JIYANG_FORMULA_OK, RC_OK),
        ("Runway 标长档 → 4", cmd_lint, RUNWAY_LONG, RC_WARN),
        ("声明=Runway 但参数块=即梦 → 4", cmd_lint, PLAT_MISMATCH, RC_WARN),
        ("缺参数块与回写位 → 4", cmd_lint, NO_ITER, RC_WARN),
        ("出彩色词且无禁止语境 → 4", cmd_lint, COLORED, RC_WARN),
        # ★ 防回退：禁止清单跨行书写，续行必须被豁免（实测踩到过假 WARN）
        ("禁止清单跨行续行 → 0（豁免延续）", cmd_lint, MULTILINE_BAN, RC_OK),
        # ★ 防回退：多批交付物，**批2 超限也要报**（早先只看全文第一个声明 → 漏报）
        ("多批交付物·批2 超限 → 1（逐块查）", cmd_lint, MULTI_BATCH, RC_FAIL),
        # ★ image2：**不声明模式就不给 8**（写 8 走普通档 → FAIL），这条防"以为 8 随便写"
        ("image2 未声明模式写 8 > 普通档 4 → 1", cmd_lint, IMAGE2_NO_MODE, RC_FAIL),
        # ★ image2：声明 Thinking 后 8 才是可达的
        ("image2 声明 Thinking 写 8 ≤ 8 → 0", cmd_lint, IMAGE2_THINKING, RC_OK),
        # ★ image2：声明 Thinking 也不是无限——9 > 8 仍 FAIL
        ("image2 Thinking 写 9 > 8 → 1", cmd_lint, IMAGE2_OVER, RC_FAIL),
        # ★ 防假报：「各出一张独立画格，不拼版」是正面表述，不该命中"拼版"违规
        ("「不拼版」正面表述 → 不报拼版 WARN（0/4 皆可，只要不是因拼版）",
         cmd_lint, PANEL_NEG_OK, RC_OK),
    ]

    ok = bad = 0
    for name, fn, text, expect in cases:
        got, _p = _run(fn, text)
        if got == expect:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s —— 期望 rc=%d，实得 rc=%d" % (name, expect, got))

    print("\n自检：%d 通过 / %d 失败（共 %d 条）" % (ok, bad, ok + bad))
    return RC_OK if bad == 0 else RC_FAIL


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return RC_USAGE
    if args[0] == "--self-test":
        return self_test()
    return cmd_lint(args[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
