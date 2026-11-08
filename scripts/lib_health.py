#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""库体检：拆卷前后都要跑，防止"拆出新 bug"与"学了没用上"。

四类检查（每条都可判，全部只读）：
  1. 悬空指针 —— 文件里引用的 `xxx.md` 在 references/ 里不存在（拆卷最常见的后遗症）
  2. 孤立知识 —— 除 SKILL.md 索引外，没有任何其他册引用它（＝学了但没用上）
  3. 行数分布 —— 300 行是硬上限；≥290 是"将满"，会挡住后续增补
  4. 重复长句 —— 跨册完全相同的长句（≥28 字），通常是两处各写一遍的规则
  5. 台账撞号 —— E## 决策号必须在 key-decisions*.md 之间全局唯一

用法：
  python3 scripts/lib_health.py            # 全部检查
  python3 scripts/lib_health.py dangling    # 只看悬空指针
"""
import io
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(ROOT, "references")
MAX_LINES = 300
NEAR_FULL = 290
# 历史条目里的旧册名（已在 key-decisions 附「历史册名对照」登记）——不算悬空
OLD_NAMES = {"prompt-engineering.md", "acting-performance.md", "performance-micro-beats.md",
             "drama-scaling-shortform.md", "style-cores-c.md"}
# ★ 2026-10-16 补：**外部文档名白名单**——**按"目标身份"豁免**（同 L2·补7 / L2·补10），
#   不再靠"整行含关键词"（那是**行形状**）。这些名字来自官方插件文档 / 外部开源仓库，
#   在本库 `references/` 里不存在，但会以 `references/xxx.md` 前缀形态或来源行出现。
EXTERNAL_NAMES = {
    "music-direction.md", "repertoire.md",                 # 官方插件（music-driven-product-ad）
    "thumbnail-frameworks.md", "brand-lock.md", "qa-and-iteration.md",   # Higgsfield 开源 agent skills
    "camera-design.md", "camera-and-styles.md", "camera-emotion-sync.md",  # seedancer
    "image-prompt.md",                                     # LingyiChen-AI/image-prompts
    "zen-piano-production.md",                             # 官方文档举例（governance 里引作外部文档）
}
DUP_MIN = 28
# 导航行的判据：含 `→` 指向某册、且**不含**强制语气词——这类重复是设计（各册都带导航表），不算缺陷
NAV_MUST = re.compile(r"必须|不得|不许|禁止|一律|至少|必带|必写|缺一|只能说|只写|只许")


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _ref_files():
    return sorted(fn for fn in os.listdir(REFS) if fn.endswith(".md"))


def _strip_code(text):
    """去代码块：代码块里的是示例，不是交付文本，不参与重复句与引用检查。

    ★ 2026-10-16 修（**实测踩到，症状很隐蔽**）：原实现是 `re.sub(r"```.*?```", "", text, flags=re.S)`
    ——**它认不出"行内代码里引用的三反引号"**。`governance-law-part2.md` 的 L2·补6
    正好写了一条"围栏块内别写注释"的规则，**规则正文里引用了 ` ``` `**；
    于是全文三反引号出现 **3 次（奇数）**，**非贪婪配对把第 1 次和第 2 次配成一对**，
    **一次吞掉 2,468 个字符**（10,481 → 8,013）——**正好把第 187 行对 `libtv-node-topology.md`
    的反引号引用也吞了**，`check_orphan` 于是**报了一册假孤立**。

    → 判据：**真围栏一定在行首**。改成"行首围栏起、行首围栏止"：
    行内出现的三反引号**不再参与配对**。
    """
    return re.sub(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$", "", text)


def check_id_collision():
    """E## 台账撞号检查（2026-10-02 新增）。

    为什么只查 E##、且只查 key-decisions* 之间：
      · E## 是决策条目号，按定义全局唯一。撞号会让两条不同结论共用一个检索键，
        **静默丢掉其中一条** —— 2026-10-02 实测真撞过一次（E178），
        而当时 check_dup 只查跨册重复长句，**一条防线都没响**。
      · 不查 C##/K## 等：它们**有意**在多处出现（契约表在 libtv-model-params.md、
        导航表在 style-library-index.md），那是**引用不是定义**，混进来全是假警报。
    """
    pat = re.compile(r"^\|\s*\**(E\d+)\**\s*\|")
    seen = defaultdict(list)
    for fn in _ref_files():
        if not fn.startswith("key-decisions"):
            continue
        for i, ln in enumerate(_read(os.path.join(REFS, fn)).split("\n"), 1):
            m = pat.match(ln)
            if m:
                seen[m.group(1)].append("%s:%d" % (fn, i))
    return [(k, v) for k, v in sorted(seen.items(), key=lambda x: int(x[0][1:]))
            if len(v) > 1]


def _near_miss(tgt, names):
    """错后缀近似名：`X-N.md` 而 `X-partN.md` 存在。

    ★ 2026-10-16 补：本库 2026-10 做过一次批量改名 **`X-N.md` → `X-partN.md`**
      （108 处同一个错误），**这里就是那条改名规则的"残留探测器"**。
      用途：**豁免不能盖过"近似已有册的错名"**——`libtv-op-manual-2.md` 与 `外部` 同处一行，
      被关键词整行跳过漏掉；**判据是"豁免按目标身份、不按行形状"**（同 L2·补7）。
    """
    m = re.match(r"^(.*)-(\d+)\.md$", tgt)
    if not m:
        return False
    return "%s-part%s.md" % (m.group(1), m.group(2)) in names


def check_dangling():
    names = set(_ref_files())
    # 续册简写：`-cinema-2.md` 是 `style-library-cinema-2.md` 的省略写法（库里既有约定）→ 视为已存在
    tails = {n.lstrip("style-library-").replace(".md", ""): n for n in names}
    bad = []
    for fn in _ref_files():
        body = _read(os.path.join(REFS, fn))
        for ln in body.split("\n"):
            # 来源登记 / 外部仓库名下不是本库的册（实测误报来源）→ 跳过
            # ★ 2026-10-16 修：跳过只对"外部名 / 歧义简写"生效——**"近似已有册的错名"不豁免**
            #   （`libtv-op-manual-2.md` 与 `外部` 同处一行，原实现整行跳过 → 漏掉）
            ext = any(k in ln for k in ("转引自", "MIT", "外部", "来源登记", "公开仓库", "检索"))
            # 历史记账（key-decisions / sources）里的旧名与外部名 → 单独归类，不算悬空
            for m in re.finditer(r"`([A-Za-z0-9_\-]+\.md)`", ln):
                tgt = m.group(1)
                if tgt in names or tgt in OLD_NAMES or tgt in EXTERNAL_NAMES \
                        or tgt == "SKILL.md" or tgt == "MEMORY.md":
                    continue
                # ★ 2026-10-31 补：**项目产物名不是册**——`02_brief.md` / `06_shotlist.md`
                #   这类「两位数字前缀 + 下划线」是十站产物的固定命名（见 default-standard.md §1），
                #   写在 references/ 里会被当成悬空指针（实测：新增执行纪律册后 4 条假警报）。
                if re.match(r"^\d{2}_[A-Za-z0-9_\-]+\.md$", tgt):
                    continue
                if tgt.startswith("-") and tgt.lstrip("-") in tails:
                    continue
                if ext and not _near_miss(tgt, names):
                    continue
                bad.append((fn, tgt))
    # ★ 2026-10-16 补：**`references/xxx.md` 前缀形态**——原来只对 `SKILL.md` 查这种形态，
    #   参考册自己里的前缀引用**一处都不查**（`libtv-op-manual.md:247` 就是靠人工发现的，不是靠门禁）。
    for fn in _ref_files():
        body = _read(os.path.join(REFS, fn))
        for m in re.finditer(r"`references/([A-Za-z0-9_\-]+\.md)`", body):
            tgt = m.group(1)
            if tgt in names or tgt in OLD_NAMES or tgt in EXTERNAL_NAMES:
                continue
            if tgt.startswith("-") and tgt.lstrip("-") in tails:
                continue
            bad.append((fn, "references/%s" % tgt))
    skill = _read(os.path.join(ROOT, "SKILL.md"))
    for m in re.finditer(r"references/([A-Za-z0-9_\-]+\.md)", skill):
        if m.group(1) not in names:
            bad.append(("SKILL.md", m.group(1)))
    return bad


def check_orphan():
    """除 SKILL.md 外无人引用的册。"""
    names = _ref_files()
    cited = defaultdict(int)
    for fn in names:
        body = _strip_code(_read(os.path.join(REFS, fn)))
        for m in re.finditer(r"`([A-Za-z0-9_\-]+\.md)`", body):
            cited[m.group(1)] += 1
    # 风格卷这类"只被索引引用"的册单独列出来（它们本来就是一册一风格编号）
    style_like = re.compile(r"^style-(cards|cores|sources|library)-")
    out = []
    for fn in names:
        if cited.get(fn, 0) == 0:
            out.append((fn, "style" if style_like.match(fn) else "normal"))
    return out


def check_lines():
    near, over = [], []
    for fn in _ref_files():
        n = len(_read(os.path.join(REFS, fn)).splitlines())
        if n >= MAX_LINES:
            over.append((n, fn))
        elif n >= NEAR_FULL:
            near.append((n, fn))
    return sorted(over, reverse=True), sorted(near, reverse=True)


def check_dup():
    seen = defaultdict(list)
    # ★ 2026-10-16 补：**载体覆盖**（同 L2·补10 症状三）——原来只扫 `references/`，
    #   **`SKILL.md` 与参考册之间的逐字重复一句都不查**。`SKILL.md` 是入口册，
    #   按"同一概念全库只有一处定义"**不该复述参考册的规则句**。
    #   （实测：截至本轮 SKILL.md 与任何参考册共享的 ≥28 字行 = **0 条**，补上零误报。）
    sources = [(fn, os.path.join(REFS, fn)) for fn in _ref_files()
               if not fn.startswith("style-")]   # 风格卷是摘录体，重复句多属正常，不查
    sources.append(("SKILL.md", os.path.join(ROOT, "SKILL.md")))
    for fn, path in sources:
        body = _strip_code(_read(path))
        for ln in body.split("\n"):
            s = re.sub(r"^[>\-\|\*\s]+", "", ln.strip())
            if len(s) >= DUP_MIN:
                seen[s].append((fn, ln.strip()))
    return [(s, fs) for s, fs in seen.items() if len({f for f, _ in fs}) > 1]


def _is_nav(s, raw=None):
    """导航行：只回答"去哪 / 是谁的下一站"，不带规则内容 —— 各册都带导航表，重复是设计。

    三类：① 含 `→` 的指路句；② 路由/映射表格行（≤3 列）；③ 册头册尾的「一句话定位」横线项。
    边界：**带强制语气词的一律不算导航**（那是规则，重复就要修）；**≥4 列的表格行也不放过**
    （"# / 字段 / 取值 / 后果"那种四列表里出现跨册重复，通常是真重复）。
    ★ 表格与横线特征在去前缀后会被抹掉，所以判据读**原始行**。
    """
    r = raw if raw is not None else s
    if NAV_MUST.search(s):
        return False
    if "读完回哪" in s or "读完回" in s:
        return True
    # 出处行：`> **来源**：…` / `**出处**：…` —— **出处标注不是规则**，
    # 同一个外部来源被多册引用时必然逐字重复，属正常（2026-09-17 加：新落三条外部来源时实测撞到）。
    # ★ 判据要读**原始行** r（`**` 在去前缀时已被剥掉，用 s 会永远匹配不上——实测踩到）。
    if "来源**" in r or "**来源" in r or "**出处**" in r or "**出处" in r:
        return True
    if "→" in s:
        return True
    if r.startswith("|"):                       # 表格行：≤3 列＝路由/映射，视为导航
        cells = [c for c in r.strip("|").split("|") if c.strip()]
        if len(cells) <= 3:
            return True
    if re.match(r"^[>\s]*[-*]\s", r) and ".md" in r and len(r) < 90 and "。" not in r:
        return True                             # 册头/册尾的「一句话定位」短横线项（可带引用前缀 `> - `）
    cells = [c.strip() for c in r.strip("|").split("|")]
    return len(cells) == 2 and bool(re.match(r"^`?[A-Za-z0-9_\-]+\.md`?[^。]*$", cells[-1]))


# ★ 2026-10-16 补：**同源册族**——同一张画布的几册蒸馏，**必然逐字共享数据与结论**。
#   为什么必须单列一桶：实测 25 条"真重复"**全部**落在下面这一族内部
#   （`libtv-canvas-anatomy*` · `libtv-prompt-anatomy-distilled*` · `libtv-node-topology.md`
#   三册蒸馏的都是画布 `9b28eb33680f4f63ab78ad747b2eed5c`），
#   内容是**节点表 / 表头 / 实测记录**（如节点 id 清单、`status:2` 结论、四列计数表），
#   **不是"两册各写一遍的规则"** ⟹ 判"该修"是误报（**误报比漏报更隐蔽**，E23）。
SAME_SOURCE_FAMILIES = (
    ("libtv-canvas-anatomy", "libtv-prompt-anatomy-distilled", "libtv-node-topology"),
)


def _same_source_family(fs):
    """重复句的**全部出现册**都落在同一个「同源族」里 → 属设计，不算缺陷。"""
    names = {f for f, _ in fs}
    for fam in SAME_SOURCE_FAMILIES:
        if all(any(n.startswith(p) for p in fam) for n in names):
            return True
    return False


def check_entry():
    """只被「记账册」引用的册 ＝ 有出处、没入口（＝学了但用不上）。

    判据：一册若除了 `key-decisions.md` / `sources-and-credits.md`（记账与来源，不是工作入口）
    之外，没有任何**工作册**引用它，那么照着流程走的人永远到不了它。
    历史实例：`real-world-logic.md` 与 run-sheet 站 6 的五个动作册——规则写了、门禁有、
    **但执行清单上没有入口**，2026-09-17 补上后才从"死知识"变成"流程的一部分"。
    """
    book = {"key-decisions.md", "sources-and-credits.md"}
    skill = _read(os.path.join(ROOT, "SKILL.md"))
    out = []
    for fn in _ref_files():
        if fn.startswith("style-"):
            continue
        peers = set()
        for q in _ref_files():
            if q == fn:
                continue
            if fn in _read(os.path.join(REFS, q)):
                peers.add(q)
        if not (peers - book):
            out.append((fn, sorted(peers), fn in skill))
    return out


def check_refs():
    """全库 `文件:行号` 引用越界检查。

    这是拆卷/瘦身后**最容易静默腐烂**的一类 bug：把一份册切薄，引用它的行号全部指空，
    而所有既有门禁都不看行号 → 两天前那次瘦身打断的 9 处引用就是无人发现。
    只查**写全文件名**的引用（`xxx.md:NNN`）——零误报；裸 `:NNN` 归属有歧义，不在此判。
    """
    names = set(_ref_files())
    lines = {}
    for fn in names:
        lines[fn] = len(_read(os.path.join(REFS, fn)).splitlines())
    lines["SKILL.md"] = len(_read(os.path.join(ROOT, "SKILL.md")).splitlines())
    pat = re.compile(r"`([A-Za-z0-9_\-]+\.md):(\d+)(?:[–‑-](\d+))?`")
    bad = []
    total = 0
    for fn in sorted(names) + ["SKILL.md"]:
        body = _read(os.path.join(REFS, fn) if fn != "SKILL.md" else os.path.join(ROOT, "SKILL.md"))
        for i, ln in enumerate(body.split("\n"), 1):
            for m in pat.finditer(ln):
                n = lines.get(m.group(1))
                if n is None:
                    continue
                total += 1
                for g in (m.group(2), m.group(3)):
                    if g and int(g) > n:
                        bad.append((fn, i, m.group(0), m.group(1), int(g), n))
                        break
    return bad, total


def check_table_rows():
    """第五类检查（**2026-10-02 新增**）：表格行完整性。

    ★ 为什么要单独一类：**截断的表格行在 Markdown 里不报错。**
      行开头是 `|`、行尾没有 `|` → 渲染器把它当成普通文本，
      **“这条决定记录没了」——而且很容易被读成“就是写断了」而过去**。
      本轮扫出 **7 处**（包括 `key-decisions.md` 四行 E 条目的**尾部整段丢失**），
      而 `lib_doctor`、`claims`、`index`、`U+FFFD` 扫描**全部拿不到**——因为它们核的都是“文件在不在」，不是“内容完整不完整」。
      **这就是 P27/P28 的第三代：探针覆盖的维度不够，所以一直在漏。**

    判据：**以 `|` 开头的行，去掉尾部空白后必须以 `|` 结尾**。
    跳过：**合法**分隔行与代码块内内容（`_strip_code`）。

    ★★ 2026-10-16 修（**这条检查自己漏过一次，而且我先把漏的原因记错了**）：
      原实现**先判"是不是分隔行"、再判"行尾有没有 `|`"**，而分隔行的判据是
      `all(c and set(c) <= set("-: ") for c in cells)` —— **`|---` 恰好满足**
      （`s.strip("|")` → `---`，cells ＝ `["---"]`，全是 `-`）⟹ **它被当成合法分隔行跳过**，
      **行尾缺 `|` 那条判据根本没轮到**。
      实测现场：`SKILL.md` 第 46 行是 `|---`，**把「一页 brief」表格劈成两半**，
      而本检查一直报"全库以 `|` 开头的行都以 `|` 结尾"。

      **⟹ 两条修法**：① **行尾判据提到分隔行判据之前**；
      ② **分隔行只有在"紧跟在同列数的表头之后"时才合法**（列数对不上＝截断）。
      **教训**：**"跳过某类"的规则写在"检查"之前，就等于给那类开了后门**——
      **被跳过的那类里，恰好包含着要抓的坏样本。**
    """
    bad = []
    for fn in _ref_files() + ["../SKILL.md"]:
        path = os.path.join(REFS, fn) if not fn.startswith("..") else os.path.join(ROOT, "SKILL.md")
        try:
            text = _read(path)
        except Exception:
            continue
        prev_cells = None
        for i, line in enumerate(text.split("\n"), 1):
            s = line.rstrip()
            if not s.startswith("|"):
                prev_cells = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not s.endswith("|"):
                bad.append((fn, i, s[-60:], "行尾缺 `|`"))
                prev_cells = cells
                continue
            if cells and all(c and set(c) <= set("-: ") for c in cells):
                # ★ 分隔行必须紧跟在同列数的表头之后
                if prev_cells is None or len(prev_cells) != len(cells):
                    bad.append((fn, i, s[-60:], "分隔行没有同列数的表头（多半是标题与表头被粘成一行）"))
                prev_cells = cells
                continue
            prev_cells = cells
    return bad


def check_odd_chars():
    """第六类检查（2026-10-02 新增）：**库内从未出现过的汉字** = 疑似错字。

    ★ 为什么这条有用（它补的是 PF28 的一个盲区）：手写 反斜杠 + u + 四位十六进制 写错字时，错字**本身是合法汉字**，
    残留转义扫描找不到、`rc=0` 也不报。但**手写码位写错的那一类，往往落到生僻汉字上**
    （本轮实测：「中途绒的诊断」「也吣掉了」「不计费」）——生僻字在整个库（3.5k 个不同汉字）里几乎不出现。

    边界（为什么只报而不判 FAIL）：合法的**新术语**也会引入新字。
    所以这条**只能拿错，不能拿对**——它是「指出疑似点」的撬棍，不是「判定无端」的判据。
    真正能自动化的是「**手写码位**」那一类，而不是「常用错字」。
    """
    corpus = set()
    for fn in _ref_files():
        corpus |= set(_read(os.path.join(REFS, fn)))
    _sd = os.path.join(ROOT, "scripts")
    if os.path.isdir(_sd):
        for fn in os.listdir(_sd):
            if fn.endswith(".py"):
                corpus |= set(_read(os.path.join(_sd, fn)))
    hits = {}
    for fn in _ref_files() + ["../SKILL.md"]:
        path = os.path.join(REFS, fn) if not fn.startswith("..") else os.path.join(ROOT, "SKILL.md")
        if not os.path.isfile(path):
            continue
        for i, line in enumerate(_read(path).split("\n"), 1):
            for ch in line:
                if "\u4e00" <= ch <= "\u9fff" and ch not in corpus:
                    hits.setdefault(ch, []).append((fn, i))
    return hits

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    rc = 0
    if what in ("all", "dangling"):
        bad = check_dangling()
        print("=== 悬空指针（引用了不存在的册）===")
        if bad:
            rc = 1
            for fn, tgt in bad:
                print("  %-34s -> %s" % (fn, tgt))
        else:
            print("  无")
    if what in ("all", "orphan"):
        print("\n=== 孤立知识（除索引外无人引用）===")
        orph = check_orphan()
        norm = [f for f, k in orph if k == "normal"]
        sty = [f for f, k in orph if k == "style"]
        # ★ 2026-10-16 补：**这一节原来也只"显示"、不设退出码**（同第一百三十轮修的行数节）。
        #   ⚠ **不能靠 `check_entry` 兜底**：`check_entry` 的 peers 是**子串匹配**（`fn in read(q)`），
        #   而 `check_orphan` 数的是**反引号引用**——**"只在正文里被当普通文本提到、没进反引号"的册，
        #   orphan 报它、entry 不报它** ⟹ 不设 `rc` 就会漏拦。
        if norm:
            rc = 1
        print("  非风格卷：%s" % ("、".join(norm) if norm else "无"))
        print("  风格卷（正常，只被索引引用）：%d 册" % len(sty))
    if what in ("all", "entry"):
        ent = check_entry()
        print("\n=== 学了没用上（只有记账册引用 ＝ 有出处没入口）===")
        if ent:
            rc = 1
            for fn, peers, inskill in ent:
                print("  ✗ %-32s SKILL=%s  仅被：%s"
                      % (fn, "✔" if inskill else "✗", "、".join(peers) or "（无人引用）"))
        else:
            print("  无（每册都至少被一份工作册引用）")
    if what in ("all", "lines"):
        over, near = check_lines()
        print("\n=== 行数（上限 %d，≥%d 为将满）===" % (MAX_LINES, NEAR_FULL))
        print("  到上限（必须拆）：%s" % ("、".join("%s(%d)" % (f, n) for n, f in over) if over else "无"))
        print("  将满（%d–%d）：%s" % (NEAR_FULL, MAX_LINES - 1,
                                     "、".join("%s(%d)" % (f, n) for n, f in near) if near else "无"))
        # ★ 2026-10-16 补：**这一节原来只"显示"、不设退出码**——
        #   一本 300 行的册会被打印成"到上限（必须拆）"，`exit` 却仍是 0（同 `lib_doctor` 的 `> 300` 也对不上）。
        #   **口径以本节自己的标签为准**：**300 ＝ 到上限 ＝ 必须拆** ⟹ 这里要把 `rc` 立起来。
        if over:
            rc = 1
    if what in ("all", "dup"):
        d = check_dup()
        same = [x for x in d if _same_source_family(x[1])]
        rest = [x for x in d if not _same_source_family(x[1])]
        nav = [x for x in rest if _is_nav(x[0], x[1][0][1])]
        real = [x for x in rest if not _is_nav(x[0], x[1][0][1])]
        print("\n=== 跨册重复长句（≥%d 字）===" % DUP_MIN)
        print("  规则行（真重复，该修）：%d 条   导航/出处行（属设计）：%d 条   同源册数据行（属设计）：%d 条"
              % (len(real), len(nav), len(same)))
        if real:
            rc = 1
            pair = defaultdict(int)
            for s, fs in real:
                pair[tuple(sorted({f for f, _ in fs}))] += 1
            print("  —— 按册对 ——")
            for k, v in sorted(pair.items(), key=lambda x: -x[1]):
                print("     %-52s %d 条" % (" + ".join(k), v))
            print("  —— 明细 ——")
            for i, (s, fs) in enumerate(real, 1):
                print("  %3d [%s]" % (i, "、".join(sorted({f for f, _ in fs}))))
                print("      %s" % s[:100])
        if what == "dup" and nav:
            print("  —— 导航行（列出不计分）——")
            for s, fs in nav:
                print("      [%s] %s" % ("、".join(sorted({f for f, _ in fs})), s[:70]))
    if what in ("all", "id"):
        coll = check_id_collision()
        print("\n=== 台账撞号（E## 在 key-decisions* 之间必须唯一）===")
        if coll:
            rc = 1
            for k, locs in coll:
                print("  ✗ %s 定义了 %d 次：%s" % (k, len(locs), "、".join(locs)))
            print("     → **撞号＝两条结论共用一个检索键，会静默丢掉其中一条**；"
                  "改号时把引用它的人一起改（编号是检索键）。")
        else:
            print("  无：全部 E## 唯一")
    if what in ("all", "odd"):
        hits = check_odd_chars()
        print("\n=== 疑似错字（库内从未出现的汉字） ===")
        if hits:
            print("  ⚠️ 以下汉字在整个库里从未出现，**往往是手写码位写错的错字**：")
            for ch, locs in sorted(hits.items()):
                print("     %s (U+%04X) x%d  %s:%d" % (ch, ord(ch), len(locs), locs[0][0], locs[0][1]))
            print("     说明：**新术语也会引入新字**——本条只报不判 FAIL；确认是错字后直接改。")
        else:
            print("  无：全库无「库内从未出现的汉字」")
    if what in ("all", "table"):
        bad = check_table_rows()
        print("\n=== 表格行完整性（截断的行不报错） ===")
        if bad:
            rc = 1
            for fn, i, tail, why in bad:
                print("  ✗ [%-30s:%d] %s。尾部：%s" % (fn, i, why, tail))
        else:
            print("  无：全库以 `|` 开头的行都以 `|` 结尾")
    if what in ("all", "refs"):
        bad, total = check_refs()
        print("\n=== 行号引用（全库 `文件:行号` 是否越界）===")
        print("  写好文件名的引用共 %d 处" % total)
        if bad:
            rc = 1
            for fn, i, raw, tgt, num, n in bad:
                print("  ✗ [%s:%d] %s —— %s 只有 %d 行" % (fn, i, raw, tgt, n))
        else:
            print("  越界：无")
    return rc


if __name__ == "__main__":
    sys.exit(main())
