#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lib_doctor —— 一站式体检（**人只跑一条命令，只看一张表**）。

为什么要有它：本库的规矩散在 100+ 册里，过去靠"记得去查"+人工复核，**实测反复漏**（无工位册 119 册 · 调色方向 22/31 同款 · 改了正文没改表）。
本脚本把这些**能机判的**全接管，人只负责：**看结论 → 按"要改什么"改**。

三种用法：
  python3 lib_doctor.py                     # 库体检（八项）
  python3 lib_doctor.py --deliver <文件…>    # 对交付件跑全部门禁 + 跨块矛盾核
  python3 lib_doctor.py --grade   <文件…>    # 按「及格线」判及格/不及格（acceptance-check.md §五·补）
  python3 lib_doctor.py --rhythm  <排镜表>    # 算 ASL 与节奏密度，查「平/机械/过短/过长」（editing-rhythm.md）
  python3 lib_doctor.py --linkage <分镜表>    # 查景别序列 / 切点是否写全 / 情绪曲线（shot-linkage.md）
  python3 lib_doctor.py --design  <分镜表>    # 查「直白」：装置有无与种类 / 连续默认款 / 落点制造器 / 母题复现（shot-design.md）
  python3 lib_doctor.py --route <站号|关键词> # 该读哪几册（把 run-sheet-part2 的路由表变成机打）
  python3 lib_doctor.py --self-test          # 自检

退出码：0 全过 ｜ 1 有问题 ｜ 2 用法错 ｜ 3 没扫到东西（≠通过）
"""
import io
import os
import re
import sys
import glob
import json
import shutil
import subprocess

try:
    from .knowledge_routes import CatalogError, library_index_text
except ImportError:
    from knowledge_routes import CatalogError, library_index_text

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
REF = os.path.join(SKILL, "references")
PY = sys.executable
# ★ 2026-10-07 修：本机 stdio 编码实测为 gbk（locale cp936），而本脚本用
#   `text=True, encoding="utf-8"` 收回子进程输出 → 子进程一旦按 gbk 写中文就
#   `UnicodeDecodeError`（实测：不设 PYTHONIOENCODING 跑本脚本即在第 ③ 节崩）。
#   → 给所有子进程统一注入 UTF-8 stdout，父子的编解码口径对齐。
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

# 不需要工位的（设计如此）：查阅型风格册 / 续册 / 总入口 / 记账类
#   ★ 2026-10-16 修（两处都是实测出来的）：
#   ① **续册豁免原来是死代码**——`EXEMPT_TAIL = ("-2.md",)`，而本库 **0 册**以 `-2.md` 结尾；
#      真正的续册命名是 **`-part2.md`（18 册）** ⟹ 补上 `-part2.md`，
#      5 册 `*-part2.md` 不再被误判"无工位"。
#   ② **`run-sheet-2.md` 从来不存在**（E88 当年建的文件叫 `run-sheet-part2.md`，
#      几处引用把名字写成了 `run-sheet-2.md`）⟹ 从 ROUTE_FILES / EXEMPT_EXACT 里删掉这个不存在的名字，
#      并把引用它的册改指 `run-sheet-part2.md`。
EXEMPT_PREFIX = ("style-cards-", "style-cores-", "style-sources-", "style-library-")
EXEMPT_TAIL = ("-2.md", "-part2.md")
EXEMPT_EXACT = {"start-here.md", "key-decisions.md", "sources-and-credits.md",
                "lib-health-report.md", "governance-law.md", "run-sheet.md",
                "governance-law-part3.md", "libtv-official-qa-part9.md",
                "run-sheet-part3.md", "run-sheet-part4.md"}
ROUTE_FILES = ("run-sheet.md", "run-sheet-part2.md", "run-sheet-part3.md", "run-sheet-part4.md")

# 交付件的跨块矛盾判据（块内不许自相矛盾）
#   ★ 画幅那条**只看首行**：`画幅 2.39:1` 在【统一提质层】里必然出现，
#     拿全文搜等于恒不报（实测踩过：自检里这条一直不触发）。
def _first_line(body):
    return next((l for l in body.splitlines() if l.strip()), "")


CROSS_CHECKS = [
    ("首行画幅与包内不同值",
     lambda body: ("21:9" in _first_line(body)) and ("2.39" not in _first_line(body))
     and bool(re.search(r"画幅\s*2\.39", body))),
    ("本镜光学族与包冲突",
     lambda body: ("变形宽银幕" in body) and re.search(r"球面镜头", body)),
    ("焦段不在包内",
     lambda body: bool(re.search(r"变形宽银幕镜头（([^）]+)）", body)) and
     bool(re.search(r"（(\d{2,3})mm", body)) and
     (re.search(r"（(\d{2,3})mm", body).group(1) not in re.search(r"变形宽银幕镜头（([^）]+)）", body).group(1))),
    ("包是固定光圈却写了 f 值",
     lambda body: ("固定光圈" in body) and bool(re.search(r"光圈\s*f\s*[\d.]+", body))),
]


def _read(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


def _table(path, want):
    """在**一份文档**里找到目标表并**只取那一张表**。
    ★ 实测踩过：`--design` 原先取全篇所有 `|` 行 → 文档里其他表（`要求|实拍|AI` 那种）的行
      也被按列号取值，于是"读到 11 条构图"，而实际只有 6 条，并凭这 11 条报了假警。
      **分镜表通常是嵌在文档里的**，所以必须从表头起、到第一个非 `|` 行为止。
    want(cells) -> bool 用来认表头。返回 (表头 cells, 数据行 cells 列表)。"""
    lines = _read(path).split("\n")
    hi, hdr = None, None
    for i, l in enumerate(lines):
        if not l.strip().startswith("|"):
            continue
        # ★ 表头 = **下一行必须是分隔行**（`|---|---|`）。
        #   实测踩过：只按"这一行的单元格里有没有关键词"认表头，会把**数据行**当表头——
        #   旁表里有一格写着"一画面一动"，于是那行被当成构图表的表头，往下取到的全是旁表的行。
        if i + 1 >= len(lines) or not lines[i + 1].strip().startswith("|"):
            continue
        nc = [c.strip() for c in lines[i + 1].strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in nc):
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if want(cells):
            hi, hdr = i, cells
            break
    if hi is None:
        return None, []
    out = []
    for l in lines[hi:]:
        if not l.strip().startswith("|"):
            break
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if cells == hdr:
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue
        out.append(cells)
    return hdr, out


def refs():
    return sorted(os.path.basename(p) for p in glob.glob(REF + "/*.md"))


def doctor():
    """九项库体检。返回 (问题数, 输出行)。"""
    out, bad = [], 0
    files = refs()
    route = "".join(_read(os.path.join(REF, f)) for f in ROUTE_FILES if os.path.exists(os.path.join(REF, f)))
    skill = library_index_text(SKILL)

    def sec(title):
        out.append("\n── %s ──" % title)

    # 1 无工位册
    sec("① 无工位的册（流程里没有东西派你去读它）")
    miss = []
    for f in files:
        if f in EXEMPT_EXACT or f.startswith(EXEMPT_PREFIX) or f.endswith(EXEMPT_TAIL):
            continue
        if f not in route and f[:-3] not in route:
            miss.append(f)
    if miss:
        bad += len(miss)
        out.append("  [FAIL] %d 册无工位：%s" % (len(miss), "、".join(miss[:10])))
        out.append("         → 改法：在 `run-sheet.md` 的对应站补一行路由")
    else:
        out.append("  [OK]   所有非查阅型册都有工位")

    # 2 单册超 300 行
    sec("② 单册行数（上限 300）")
    # ★ 2026-10-16 补覆盖：**入口文件也要算**。
    #   此前本条只遍历 `files`（＝`references/*.md`），**`SKILL.md` 不在内**——
    #   于是它 326 行时本项仍报"无超限"（同形缺口：`lib_health` 的表格检查也漏过它，
    #   不过那条的根因不同，是"分隔行判据写在行尾判据之前"，见 `lib_health.check_table_rows`）。
    targets = [(os.path.join(REF, f), f) for f in files] + \
              [(os.path.join(SKILL, "SKILL.md"), "SKILL.md")]
    over = [(name, len(_read(path).splitlines())) for path, name in targets]
    # ★ 2026-10-16 修：**原来这里是 `> 300`**，而 `lib_health` 那边把 300 显示成"到上限（必须拆）"——
    #   **同一本 300 行的册，一个说"必须拆"、一个说"没事"，两条退出码都是 0**。
    #   **口径以标签为准：300 ＝ 到上限 ＝ 超限** ⟹ 这里改成 `>= 300`（与 `lib_health.check_lines` 的 `n >= MAX_LINES` 对齐）。
    over = [x for x in over if x[1] >= 300]
    if over:
        bad += len(over)
        out.append("  [FAIL] 超限：%s" % "、".join("%s(%d)" % x for x in over))
        out.append("         → 改法：按 L2·补 拆卷（切到 `*-partN.md` 并在正册留指针）")
    else:
        ready = [x for x in over] + \
                [x for x in [(name, len(_read(path).splitlines())) for path, name in targets] if x[1] >= 290]
        out.append("  [OK]   无超限；将满(≥290)：%d 册" % len(ready))

    # 3 悬空指针（**交给 lib_health 判** —— 单一权威源；
    #   本脚本不再自己实现一遍：实测两套口径会打架，且我这套会把"外部技能名带 .md"误判成悬空）
    sec("③ 悬空指针（口径来自 lib_health.py，本脚本不重复实现）")
    r = subprocess.run([PY, os.path.join(HERE, "lib_health.py")], capture_output=True, text=True, encoding="utf-8", env=CHILD_ENV)
    seg = (r.stdout or "")
    m = re.search(r"悬空指针（引用了不存在的册）===+\s*\n\s*(.+)", seg)
    line = (m.group(1).strip() if m else "")
    if line and line != "无":
        bad += 1
        out.append("  [FAIL] %s" % line[:160])
    else:
        out.append("  [OK]   无")

    # 4 新册未挂 SKILL 索引
    sec("④ 未挂 SKILL 索引的册")
    un = [f for f in files if f not in skill and f[:-3] not in skill]
    if un:
        bad += len(un)
        out.append("  [FAIL] %d 册：%s" % (len(un), "、".join(un[:8])))
        out.append("         → 改法：挂进 SKILL.md 的索引行（否则 index 门禁会 FAIL）")
    else:
        out.append("  [OK]   全部已挂")

    # 5 十脚本自检 + claims
    sec("⑤ 脚本自检 + claims")
    # ★ 2026-10-01 增 `libtv_orchestrate.py`（站 6.5/6.6/6.7 编排器）→ 六→七（+本脚本＝八）。
    # ★ 2026-10-07 增 `graph_plan_lint.py`（统一 graph plan 静态门禁）·
    #   `three_work_regression.py`（三作+合成只读回归）· `numbering.py`（编号撞号）·
    #   `offline_package_lint.py`（离线生成包总门禁）· `render_offline_prompts.py`（单一提示词源）→ 七→十二（+本脚本＝十三）。
    #   纪律：**新脚本不挂进这里就等于没门禁**——门禁清单是硬编码的，不自动发现。
    scripts = ["audit_prompt.py", "ai_smell_check.py", "storyboard_lint.py",
               "shotlist_lint.py", "script_lint.py", "sound_lint.py",
               "libtv_orchestrate.py", "graph_plan_lint.py",
               "three_work_regression.py", "numbering.py",
               "offline_package_lint.py", "render_offline_prompts.py",
               # ★ 2026-10-16 新增：**验证验证器**——给源码打一个已知坏改动，看门禁红不红。
               #   它的 --self-test 只在临时目录里动文件，**不碰本库任何脚本**，所以可以常驻。
               "mutation_check.py",
               # ★ 2026-10-16 新增：**拿随册 schema 集扫门禁的边界层**（区间/收紧/素材）。
               #   它只读 `schemas/libtv-models/`，**不改任何东西**；schema 集一刷新就重跑它。
               "libtv_schema_sweep.py",
               # ★ 2026-10-31 新增：**资产清单契约**（派生/对账/投喂三层，自带 4 例 fixtures）。
               #   只读 JSON、不生成、不联网；`asset-standard.md` §9 的落地门禁。
               "asset_manifest.py",
               # ★ 2026-10-31 新增：**清单→画布**（节点 + 资产内派生边 + 投喂边）。
               #   --self-test 只跑校验器与命令生成器，**不联网**；真写画布要 --apply --yes。
               "libtv_canvas_build.py",
               # ★ 2026-10-31 新增：**十站出口门**（默认值 + 豁免协议 + 反偷懒）。
               #   --self-test 只跑判据与临时工程，**不联网**。
               "stage_gate.py",
               # ★ 2026-10-31 新增：**上下游与连线顺序**（拓扑层 + 边理由 + 环/分量）。
               #   --self-test 只跑纯图算法，不读画布、不联网。
               "wiring_plan.py",
               # ★ 2026-10-31 新增：**交换层与后端作业单**（CineCrew FilmDSL / ViMax runtime）。
               #   两者都只投影与绑定：不产计划、不点火、不联网；无 jsonschema 依赖。
               "filmdsl_bridge.py", "vimax_backend_compile.py",
               # ★ 2026-10-31 新增：**剧本拆解桥**（站 4→5→6 的缝合点，14 项自检）。
               #   只解析文本与写 JSON：不写视觉描述、不联网、不点火。
               "breakdown_compile.py",
               # ★ 2026-10-31 新增：**统一 12 块提示词视图**（用户不选模板；缺块标未给）。
               "canonical_prompt.py",
               # ★ 2026-10-31 新增：**Production IR**（唯一事实源 + 12 块编译 + 规则校验）。
               "production_ir.py",
               # ★ 2026-10-31 新增：**适配器预检**（能力不足即拒；永不发请求）与
               #   **媒体 QC 归一 + 定向修复计划**（不自动重跑）。
               "model_adapter.py", "media_qc.py",
               # ★ 2026-10-31 新增：**一句话到交付的一条命令**（拆解→编译→IR→12 块）。
               "studio_run.py",
               # ★ 2026-10-31 新增：**错误契约 / 图权威 v2 / Prompt AST / Rule Registry**。
               "error_contract.py", "workflow_graph_ir.py", "prompt_ast.py", "rule_registry.py"]
    fails = []
    for s in scripts:
        r = subprocess.run([PY, os.path.join(HERE, s), "--self-test"], capture_output=True, env=CHILD_ENV)
        if r.returncode != 0:
            fails.append(s)
    if fails:
        bad += len(fails)
        out.append("  [FAIL] 自检不过：%s" % "、".join(fails))
    else:
        out.append("  [OK]   二十九脚本自检全过")
    r = subprocess.run([PY, os.path.join(HERE, "audit_prompt.py"), "claims", SKILL], capture_output=True, env=CHILD_ENV)
    out.append("  [%s] claims：%s" % ("OK" if r.returncode == 0 else "FAIL", "数字断言一致" if r.returncode == 0 else "与实际不符"))
    if r.returncode != 0:
        bad += 1

    # 6 跨册真重复
    sec("⑥ 跨册重复长句（规则行）")
    r = subprocess.run([PY, os.path.join(HERE, "lib_health.py")], capture_output=True, text=True, encoding="utf-8", env=CHILD_ENV)
    m = re.search(r"规则行（真重复，该修）：(\d+) 条", r.stdout or "")
    n = int(m.group(1)) if m else -1
    if n > 0:
        bad += 1
        out.append("  [FAIL] %d 条真重复（跑 lib_health 看明细）" % n)
    else:
        out.append("  [OK]   0 条（导航/出处行属设计）")

    # 7 路由表是否漏了刚加的册
    sec("⑦ 路由表自检（新增册有没有补路由）")
    out.append("  [OK]   见第 ① 项（无工位册＝0 即通过）")

    # 8 环境体检（**外部工具契约** · 2026-10-01 新增）
    #   为什么单列：ffmpeg / ffprobe 是 9 册的硬依赖（容器级·切片级·像素级三项核验 + concat 拼接），
    #   但全库从未声明过它、也没有任何地方预检 —— 代价是「跑到站 6.6 交付核验才发现跑不了」。
    #   **不计入 bad**：ffmpeg 只在站 6.6 必需，对「只跑剧本/分镜门禁」的人判 FAIL 属误报
    #   （governance-law.md L7·③：误报比漏报更隐蔽）。故只报状态 + 改法。
    sec("⑧ 环境体检（外部工具契约 · 不计入问题数）")
    def _find(tool):
        """**不只查 PATH**（2026-10-02 补）—— `imageio_ffmpeg` 只带**静态二进制**，**不进 PATH**。
        只查 PATH 会把「已经能拿到 ffmpeg」这个事实报成「未找到」——
        本轮它就是这个情况：pip 装好了，工具在，门禁却在叫「没装」。"""
        exe = shutil.which(tool)
        if exe:
            return exe, "PATH"
        if tool == "ffmpeg":
            try:
                import imageio_ffmpeg
                p = imageio_ffmpeg.get_ffmpeg_exe()
                if p and os.path.isfile(p):
                    return p, "imageio_ffmpeg（pip 包，未进 PATH）"
            except Exception:
                pass
        return None, None

    for tool, why in (("ffmpeg", "站 6.6 切片级/像素级核验 + concat 拼接"),
                      ("ffprobe", "站 6.6 容器级核验（时长/分辨率/fps/音轨）")):
        exe, src_ = _find(tool)
        if exe:
            out.append("  [OK]   %-7s %s（来源：%s）" % (tool, exe, src_))
        elif tool == "ffprobe" and _find("ffmpeg")[0]:
            out.append("  [OK]   %-7s 未找到，但**不阻塞**：`ffmpeg -i` 已能解析容器参数（"
                       "脚本自带回退，只在需要精确音轨列表时才必须补 ffprobe）" % tool)
        else:
            out.append("  [WARN] %-7s 未找到 —— %s" % (tool, why))
            out.append("         → 改法：`pip install imageio-ffmpeg`（得到 ffmpeg）或装全套 ffmpeg；"
                       "未装则站 6.6 的帧级判据无法执行")

    # 9 索引断言
    sec("⑨ 结论")
    out.append("  %s" % ("**全过**" if bad == 0 else "**%d 处要改**（按上面 → 改法）" % bad))
    return bad, out


def deliver(paths):
    """对交付件跑门禁 + 跨块矛盾。"""
    out, bad = [], 0
    for p in paths:
        if not os.path.exists(p):
            out.append("[SKIP] 不存在：%s" % p); continue
        t = _read(p)
        body = t.split("```text")[1].split("```")[0] if "```text" in t else t
        g = subprocess.run([PY, os.path.join(HERE, "audit_prompt.py"), "blocks", p],
                           capture_output=True, env=CHILD_ENV).returncode
        # ★ rc=3 ＝ **没扫到**（不是通过，也不是要改）→ 报 SKIP，**不计入不合格**。
        #   实测：`--deliver 多形态12轮/*.md` 把 12 份**声音表**全报成"要改 门禁 rc=3"——
        #   它们本来就不是镜头稿。把"没验到"混进"要改"，就是让 WARN 贬值
        #   （`SKILL.md` 退出码口径自己写着「3 与 0 的区别是这套把关的关键」，这里却没照着做）。
        if g == 3:
            out.append("[SKIP] %-34s 没扫到提示词块（**没验到，≠通过，也≠要改**）——"
                       "确认文件是否贴对、或它本来就不是镜头稿" % os.path.basename(p)[:34])
            continue
        probs = [name for name, fn in CROSS_CHECKS if fn(body)]
        st = "OK" if (g == 0 and not probs) else "要改"
        if g != 0:
            probs.append("门禁 rc=%d" % g)
        out.append("[%s] %-34s %s" % (st, os.path.basename(p)[:34], "、".join(probs) or "无"))
        if st != "OK":
            bad += 1
    return bad, out


def route(key):
    """按站号或关键词，把该读哪几册打出来。"""
    t = ""
    for f in ROUTE_FILES:
        p = os.path.join(REF, f)
        if os.path.exists(p):
            raw = _read(p)
            start = raw.find("<!-- knowledge-routes:v1 -->")
            end = raw.find("<!-- /knowledge-routes -->")
            if start >= 0 and end >= start:
                raw = raw[:start] + raw[end + len("<!-- /knowledge-routes -->"):]
            t += raw
    out = []
    if key.isdigit():
        key = "站 " + key
    for line in t.split("\n"):
        if key in line or ("站 " + key) in line:
            out.append(line)
    # 命中标题就把它下面整节打出来
    sec = None
    res = []
    for line in t.split("\n"):
        if line.startswith("### "):
            sec = line
        if sec and key in sec:
            res.append(line)
    res = res or out
    if not res:
        return 3, ["（没匹配到 %s；试试「站 6」「人物」「颜色」「审片」）" % key]
    return 0, res


def grade(paths):
    """按「及格线」（`acceptance-check.md` §五·补 · 5.1）对交付件逐条判**及格/不及格**。"""
    out, bad = [], 0
    LINE = [("结构门禁 FAIL=0", None), ("观感不含 AI 味 FAIL=0", None),
            ("跨块矛盾 0 处", None), ("（交付件未附声音表则不查）", None)]
    for p in paths:
        if not os.path.exists(p):
            out.append("[SKIP] 不存在：%s" % p); continue
        t = _read(p)
        body = t.split("```text")[1].split("```")[0] if "```text" in t else t
        g1 = subprocess.run([PY, os.path.join(HERE, "audit_prompt.py"), "blocks", p], capture_output=True, env=CHILD_ENV).returncode
        g2 = subprocess.run([PY, os.path.join(HERE, "ai_smell_check.py"), p], capture_output=True, env=CHILD_ENV).returncode
        probs = [name for name, fn in CROSS_CHECKS if fn(body)]
        # 及格线：结构与观感必须 0 告警；跨块矛盾必须 0
        item = []
        if g1 != 0:
            item.append("结构门禁 FAIL(rc=%d)" % g1)
        if g2 not in (0, 3):          # 3＝没扫到提示词块（≠ 通过，但也不算 FAIL）
            item.append("有 AI 味 FAIL/WARN(rc=%d)" % g2)
        item += probs
        st = "及格" if not item else "不及格"
        if st == "不及格":
            bad += 1
        out.append("[%s] %-34s %s" % (st, os.path.basename(p)[:34], "、".join(item) or "四项全过"))
    out.append("")
    out.append("★ 已判：5.1 的四项（结构 / 观感 / 跨块矛盾 / 声音表）")
    out.append("★ 不能判（只能看片）：「表演是否可信 / 道具是否可达 / 画面是否好看」——不许声称已验")
    out.append("★ 以及 5.2/5.3 的拼接点、响度、交付包、抽卡次数（需成片与台账才能判）")
    return bad, out


def rhythm(path):
    """按 `editing-rhythm.md` 算一条排镜表的节奏：ASL · 节奏密度 · 四种"平/跳"症状。"""
    if not os.path.exists(path):
        print("[SKIP] 不存在：%s" % path); return 2
    t = _read(path)
    # 抓形如 `3s` / `3秒` / `3 秒` / `| 3 |` 的时长（优先带单位的）
    durs = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:s|秒)(?![a-zA-Z])", t)]
    if len(durs) < 3:
        # 退一步：表格里纯数字的时长列（取每行最后一个 0.5–120 的数）
        cand = []
        for line in t.split("\n"):
            if line.strip().startswith("|"):
                nums = re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.%])", line)
                if nums:
                    v = float(nums[-1])
                    if 0.3 <= v <= 120:
                        cand.append(v)
        durs = cand
    if len(durs) < 3:
        print("没扫到 ≥3 个时长（排镜表里要能看出每镜几秒）"); return 3
    n = len(durs)
    total = sum(durs)
    asl = total / n
    dens = [round(10.0 / max(a, 0.01), 1) for a in durs]     # 每 10 秒切点数（按单镜时长折算）
    out = []
    out.append("文件：%s" % os.path.basename(path))
    out.append("镜头数 %d ｜ 总时长 %.1fs ｜ **ASL %.2fs**" % (n, total, asl))
    out.append("单镜时长：%s" % "、".join("%.1f" % d for d in durs))
    probs = []
    if max(durs) - min(durs) < 0.4:
        probs.append("**全程几乎同长（ASL 是一条直线）→ 会读作\"平\"**；用 §2 挑一套公式重排时长")
    m3 = any(abs(durs[i] - durs[i + 1]) < 0.3 and abs(durs[i + 1] - durs[i + 2]) < 0.3 for i in range(n - 2))
    if m3:
        probs.append("**连续 3 个镜头时长几乎相同 → 这段会读作\"机械\"**；对调其中两个的时长")
    if min(durs) < 0.5:
        probs.append("有镜头 **< 0.5s**（%.1fs）——通常读不出来，除有意做「闪」否则删" % min(durs))
    if max(durs) > 6:
        probs.append("有镜头 **> 6s**（%.1fs）——确认它是\"有意留白\"还是\"没素材补\"" % max(durs))
    out.append("")
    for x in probs:
        out.append("[要改] %s" % x)
    if not probs:
        out.append("[OK]   节奏四项均无问题（有长短起伏 · 无机械重复 · 无读不出的短镜 · 无超长镜）")
    out.append("")
    out.append("★ 机器能判的四项（起伏 / 机械重复 / 过短 / 过长）；**\"这段到底好不好看\"只能看片**。")
    print("\n".join(out))
    return 1 if probs else 0


SHOT_SIZES = ["大远景", "远景", "全景", "中景", "中近景", "近景", "特写", "大特写", "插入"]


def linkage(path):
    """按 `shot-linkage.md` 查**分镜表的衔接质量**：景别序列 · 切点写全 · 情绪曲线。
    表里要能看出：景别列（九级之一）/ 切点列（含"切在…"）/ 情绪列（1–5 的数字）。只对能读出的项判。"""
    if not os.path.exists(path):
        print("[SKIP] 不存在：%s" % path); return 2
    # ★ 必须**按表头定位列**，且**只取那一张表**——按单元格扫会把"镜号 1"当成情绪值、
    #   把"构图=特写"也算成景别；全篇取 `|` 行还会把文档里别的表一起算进来（两处都实测踩过）
    hdr, rows = _table(path, lambda c: any("景别" in x for x in c))
    if hdr is None:
        print("没找到表头（需要含「景别」列的表头行）"); return 3

    def col(*names):
        for i, c in enumerate(hdr):
            if any(n in c for n in names):
                return i
        return None
    i_sz, i_cut, i_emo = col("景别"), col("切点", "过渡"), col("情绪", "强度")
    sizes, cuts, emos, size_rows = [], [], [], []
    for cells in rows:
        if len(cells) <= max([x for x in (i_sz, i_cut, i_emo) if x is not None], default=0):
            continue
        if i_sz is not None:
            for i, s in enumerate(SHOT_SIZES):
                if s in cells[i_sz]:
                    sizes.append(i)
                    size_rows.append(cells)   # ★ 与 sizes 同序——大跳那条要按"这两镜"取原文
                    break
        if i_cut is not None and cells[i_cut] and cells[i_cut] != "—":
            cuts.append(cells[i_cut][:14])
        if i_emo is not None:
            m = re.fullmatch(r"[1-5]", cells[i_emo])
            if m:
                emos.append(int(cells[i_emo]))
    if not sizes and not cuts and not emos:
        print("没扫到可判的列（需要：景别列 / 含「切在…」的切点列 / 1–5 的情绪列）"); return 3
    out, probs, infos = [], [], []
    out.append("文件：%s" % os.path.basename(path))
    out.append("读到：景别 %d ｜ 切点 %d ｜ 情绪 %d" % (len(sizes), len(cuts), len(emos)))
    if sizes:
        out.append("景别序列：%s" % "、".join(SHOT_SIZES[i] for i in sizes))
    if sizes:
        if len(set(sizes)) == 1:
            probs.append("**整条只有一个景别（%s）**——`segmented-shot.md` 口径：**整条一个景别＝不合格**；至少跨 2 级" % SHOT_SIZES[sizes[0]])
        same = [i + 1 for i in range(len(sizes) - 1) if sizes[i] == sizes[i + 1]]
        if same:
            probs.append("**相邻同景别**（第 %s 处）——需**换角度 ≥30°**（`editing-rhythm.md` §7.2 的 30 度原则），否则必跳" % "、".join(map(str, same)))
        jump = [i + 1 for i in range(len(sizes) - 1) if abs(sizes[i] - sizes[i + 1]) >= 3]
        # ★ 已声明的例外 → 降为提示（2026-09-19 立）：
        #   大跳本身不是错，库里的要求是"两镜里要有同一个物件/同一块颜色当锚"。
        #   锚要是**已经写在表里**，这条就不该继续报"要改"——**一直报一个已答的问题，
        #   只会让人开始无视 WARN**（`governance-law.md` E23 同族）。
        ANCHOR_DECL = ("同一个", "同一块", "同一位置", "同一物件", "仍在", "还在", "同机位", "同构图", "不变的是")
        for i in jump:
            pair = (size_rows[i - 1] if i - 1 < len(size_rows) else []) + \
                   (size_rows[i] if i < len(size_rows) else [])
            joined = "".join(pair)
            if any(k in joined for k in ANCHOR_DECL):
                infos.append("[提示] 大跳（第 %d 处跨 ≥3 级）——**已声明锚点**，确认它真的落在两镜的画面里" % i)
            else:
                probs.append("**有大跳**（第 %d 处跨 ≥3 级）——确认两镜里有**同一个物件或同一块颜色当「锚」**"
                             "（`shot-linkage.md` §2 第 2 条）" % i)
    if cuts:
        n_expect = max(len(sizes), len(cuts))
        if len(cuts) < n_expect - 1:
            probs.append("**切点没写全**（读到 %d 条，镜头间应有 %d 条）——每两个相邻镜都要写明「切在哪一帧」" % (len(cuts), n_expect - 1))
    if emos:
        if max(emos) - min(emos) <= 1:
            probs.append("**情绪曲线几乎是直线**（%d–%d）——没有戏；至少一次\"升到 5 再落\"" % (min(emos), max(emos)))
        peak = sum(1 for e in emos if e == 5)
        if peak and peak > len(emos) * 0.15 + 0.5:
            probs.append("**5 分镜占 %d/%d（>15%%）**——处处 5 分＝没有峰值" % (peak, len(emos)))
        if peak == 0:
            probs.append("**没有 5 分镜**——全片没有峰值")
    for x in probs:
        out.append("[要改] %s" % x)
    for x in infos:
        out.append(x)
    if not probs:
        out.append("[OK]   景别有多样性且无同级相邻 · 切点写全 · 情绪曲线有形状")
    out.append("")
    out.append("★ 机器能判：景别序列 · 切点是否写全 · 情绪曲线的形状与峰值占比")
    out.append("★ 不能判：**「这一段到底流不流畅」只能看片**；视觉呼应的「埋得好不好」也只能看片")
    print("\n".join(out))
    return 1 if probs else 0


# 设计装置词表（`shot-design.md` §2 的十个）——★ 只在【构图】列里判，别全行泛搜
DESIGN_DEVICES = (
    ("三角调度", ("三角",)),
    ("Z 轴调度", ("纵深", "Z轴", "由远而近", "由近而远", "沿纵深", "穿过画面")),
    ("负空间调度", ("负空间", "一侧为空", "一侧留空", "空出一", "空出", "大片空", "大面积空", "为空", "留空")),
    ("不对称配对", ("不对称", "一坐一站", "一前一后", "半身入画", "只入画", "半个身子")),
    ("框中框", ("门框", "窗框", "框中框", "镜中", "廊柱", "拱门", "取景框")),
    ("方向性装置", ("长桌", "楼梯", "走廊", "队列", "对角线", "延伸线", "一字排开")),
    ("象征性放置", ("放在", "搁在", "摆在", "推回", "扣在")),
    ("三区构图", ("前景", "中景", "后景")),          # 需命中 ≥2 个不同层词，见下
    ("焦点当调度", ("焦点转移", "焦平面", "变焦", "虚实转换", "移焦")),
    ("尺度对比", ("占比", "巨大", "参照物", "尺度", "九成")),
)
# 默认款（＝不是设计，是底子）
DEFAULT_COMP = ("三分", "中心", "中央", "居中")
# 落点制造器（`shot-design.md` §1 表）——强弱有别，但至少要写"用什么造的"
#   ★ 关键词别写太长：册里写的是「全画面唯一的高饱和色」，而词表里只有「唯一高饱和」——
#     中间插一个「的」就永远匹配不上（实测：自家的实例被自家门禁判"没写落点"）。
FOCAL_MAKERS = ("最亮", "高光", "高饱和", "唯一", "焦平面", "唯一清晰", "人脸", "逆光轮廓", "最暗")
# 母题的「复用写法」：**写成"与镜 N 同机位"时，逐字比对抓不到**（实测）——它是指针不是复述
REUSE_PAT = r"(与镜|同机位|同构图|与.{1,6}相同|复现|重复|同款)"


def _devices_in(text):
    """返回这条构图描述命中的装置名集合。★ 三区要命中 ≥2 个不同层词才算（只写"前景"一处不构成层）。"""
    hit = set()
    for name, kws in DESIGN_DEVICES:
        if name == "三区构图":
            if sum(1 for k in kws if k in text) >= 2:
                hit.add(name)
        elif any(k in text for k in kws):
            hit.add(name)
    return hit


def design(path):
    """按 `shot-design.md` 查**分镜表有没有"设计感"**：每镜是否点了一个可命名的设计装置 · 是否整场只有默认款 · 是否写了落点制造器。
    表里要能看出【构图】列（表头含「构图」/「画面」/「设计」）。只对这一列判——**全行泛搜会把景别词、运镜词当成装置**。"""
    if not os.path.exists(path):
        print("[SKIP] 不存在：%s" % path); return 2
    # ★ 只取**含「构图」列的那一张表**，且列名必须以「构图」为准——
    #   原先用 `col("构图","画面","设计")` 取"第一个命中的列"，遇到列名叫「段·画面」的表头时
    #   会把编号列当成构图列（实测）。故先认「构图」，认不到再放宽。
    hdr, rows = _table(path, lambda c: any(("构图" in x or "画面" in x or "设计" in x) for x in c))
    if hdr is None:
        print("没找到表头（需要含「构图」列的表头行）"); return 3

    def col(*names):
        for i, c in enumerate(hdr):
            if any(n in c for n in names):
                return i
        return None
    i_cp = col("构图")
    if i_cp is None:
        i_cp = col("画面", "设计")
    if i_cp is None:
        print("没找到「构图」列"); return 3
    comps = []
    for cells in rows:
        if len(cells) <= i_cp:
            continue
        if cells[i_cp]:
            comps.append(cells[i_cp])
    if not comps:
        print("没扫到可判的【构图】内容"); return 3

    out, probs, infos = [], [], []
    out.append("文件：%s" % os.path.basename(path))
    out.append("读到：构图 %d 条" % len(comps))

    per = [_devices_in(c) for c in comps]
    bare = [i + 1 for i, h in enumerate(per) if not h]
    used = set()
    for h in per:
        used |= h
    out.append("装置使用：%s" % ("、".join(sorted(used)) if used else "（无）"))

    # ① 整场没有装置 → 最重的判据
    if not used:
        probs.append("**整场没有点任何设计装置**——全是「%s」这一档的默认款；"
                     "从 `shot-design.md` §2 的十个里给这一场点 2–3 个" % "、".join(DEFAULT_COMP[:2]))
    elif len(used) < 2 and len(comps) >= 4:
        probs.append("**整场只用了 1 个装置（%s）**——一场 2–3 个，否则这一个也不被看见（`shot-design.md` §2 纪律 1）" % "、".join(sorted(used)))

    # ② 连续 ≥3 镜是默认款 → 单调
    if bare:
        run, runs, start = 1, [], bare[0]
        for a, b in zip(bare, bare[1:]):
            if b == a + 1:
                run += 1
            else:
                if run >= 3:
                    runs.append((start, run))
                run, start = 1, b
        if run >= 3:
            runs.append((start, run))
        if runs:
            probs.append("**连续默认款**（第 %s 处起各连续 ≥3 镜）——中间要换装置，否则整段没有落点"
                         % "、".join(str(s) for s, _ in runs))
        elif len(bare) > len(comps) * 0.5:
            probs.append("**默认款占 %d/%d（>50%%）**——`shot-design.md` §1：位置是最弱的落点制造器，全场靠它＝等于没有落点"
                         % (len(bare), len(comps)))

    # ③ 落点制造器：全表一条都没写 → 判据
    if not any(any(k in c for k in FOCAL_MAKERS) for c in comps):
        probs.append("**没有一条写了落点用什么造的**（亮度 / 清晰度 / 运动 / 色彩 / 人脸）——"
                     "只写「在哪」不写「怎么让它被看见」（`shot-design.md` §1 表）")

    # ④ 全场构图描述逐字同款 → 最直白
    if len(comps) >= 3 and len(set(comps)) == 1:
        probs.append("**%d 条构图逐字相同**——这是最直白的一种；至少按 §3 四条改法改掉一半" % len(comps))

    # ⑤ 母题复现（正面信号，只报不判）
    #   ★ 必须先排除"全场逐字同款"那一档——它不是母题，它就是直白本身（实测误报过一次：
    #     最差的反例被夸成"母题的好苗子"，正说明判据写成了"有没有重复"而不是"有没有变奏"）。
    seen = {}
    for i, c in enumerate(comps):
        seen.setdefault(c, []).append(i + 1)
    rep = [v for v in seen.values() if len(v) >= 2]
    reuse = [i + 1 for i, c in enumerate(comps) if re.search(REUSE_PAT, c)]
    if len(set(comps)) < 2:
        infos.append("[提示] 构图没有变奏（全表 ≤1 种）——**这不叫母题**；母题要「起 / 变 / 揭」三拍，"
                     "先按 §3 把大部分镜改成不同的装置（`shot-design.md` §4.3）")
    elif rep or reuse:
        bits = []
        if rep:
            bits.append("逐字相同：%s" % "；".join("镜 %s" % "、".join(map(str, v)) for v in rep))
        if reuse:
            bits.append("写明复用：镜 %s" % "、".join(map(str, reuse)))
        infos.append("[提示] 复现/复用的构图（%s）——**这是母题的好苗子**，确认它有没有「起 / 变 / 揭」三拍"
                     "（`shot-design.md` §4.3）" % " · ".join(bits))
    else:
        infos.append("[提示] 没有复现的构图——**全片可能没有母题**；埋 1–2 类（`shot-design.md` §4.2）")

    for x in probs:
        out.append("[要改] %s" % x)
    for x in infos:
        out.append(x)
    if not probs:
        out.append("[OK]   每镜都点了装置 · 有落点制造器 · 没有连续默认款")
    out.append("")
    out.append("★ 机器能判：装置的有无与种类数 · 连续默认款 · 落点制造器是否写 · 母题有没有复现")
    out.append("★ 不能判：**「这一镜有没有设计感」与「这套视觉语法配不配这个故事」只能人看**（`shot-design.md` §7）")
    print("\n".join(out))
    return 1 if probs else 0


def self_test():
    ok = 0
    # ① 库体检能跑完（不抛异常）
    try:
        doctor(); ok += 1; print("  [OK]   库体检能跑完")
    except Exception as e:
        print("  [NG]   库体检抛异常：%s" % e)
    # ② 交付件模式：合格样本不报错
    try:
        deliver([os.path.join(SKILL, "SKILL.md")]); ok += 1
        print("  [OK]   交付件模式能跑完（非提示词文件按 0 判）")
    except Exception as e:
        print("  [NG]   交付件模式抛异常：%s" % e)
    # ③ 跨块矛盾：反例必须被抓到 ≥3 类
    bad_sample = ("画幅21:9。" + chr(10)
                  + "变形宽银幕镜头（40 / 50 / 75mm）· 数字底 · 画幅 2.39:1。" + chr(10)
                  + "【镜头规格】球面镜头，约 47°（35mm），光圈 f2.0。")
    hit = [n for n, fn in CROSS_CHECKS if fn(bad_sample)]
    if len(hit) >= 3:
        ok += 1
        print("  [OK]   跨块矛盾：反例抓到 %d 类（%s）" % (len(hit), "、".join(hit)))
    else:
        print("  [NG]   跨块矛盾只抓到 %d 类：%s" % (len(hit), hit))
    # ④ 跨块矛盾：正例零误报
    good_sample = ("画幅2.39:1（21:9 落地）。" + chr(10)
                   + "变形宽银幕镜头（40 / 50 / 75mm）· 数字底 · 画幅 2.39:1。" + chr(10)
                   + "【镜头规格】变形宽银幕镜头，约 47°（50mm），光圈 f2.0。")
    hit2 = [n for n, fn in CROSS_CHECKS if fn(good_sample)]
    if not hit2:
        ok += 1
        print("  [OK]   跨块矛盾：正例零误报")
    else:
        print("  [NG]   正例被误报：%s" % hit2)
    # ⑤ 及格线：跑得通且判据方向对
    #   ★ 不要用"合成样本"当正例——`grade` 里跑的是**真门禁**（要 12 块齐），
    #     合成样本必然 FAIL，会把"判据方向"和"样本不合法"混为一谈（实测踩过）。
    #     这里只断言两件能自洽的事：**不合格的东西判不及格** · **文件不存在算 SKIP 不计入不合格**。
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    io.open(p, "w", encoding="utf-8").write("这不是一份提示词，什么都没有。")
    n_bad, _ = grade([p])
    os.unlink(p)
    n_missing, _ = grade([os.path.join(HERE, "___不存在___.md")])
    if n_bad == 1 and n_missing == 0:
        ok += 1
        print("  [OK]   及格线：无名文件判不及格 · 不存在的文件算 SKIP")
    else:
        print("  [NG]   及格线判据异常（不合格=%d 不存在=%d）" % (n_bad, n_missing))
    # ⑥ 节奏：全同的排镜表必须被判「有起伏问题」，有长短的必须过
    import tempfile
    def _tab(durs):
        fd, q = tempfile.mkstemp(suffix=".md"); os.close(fd)
        rows = "".join("| %d | %ss |" % (i + 1, d) + chr(10) for i, d in enumerate(durs))
        io.open(q, "w", encoding="utf-8").write("| 镜 | 时长 |" + chr(10) + "|---|---|" + chr(10) + rows)
        return q
    f1 = _tab([3, 3, 3, 3]); f2 = _tab([1.5, 3, 1, 2.5])
    r1 = rhythm(f1); r2 = rhythm(f2)
    os.unlink(f1); os.unlink(f2)
    if r1 == 1 and r2 == 0:
        ok += 1
        print("  [OK]   节奏：全同判\"平\" · 有长短则过")
    else:
        print("  [NG]   节奏判反了（全同=%d 有起伏=%d）" % (r1, r2))
    # ⑦ 衔接：同级相邻 + 大跳 + 切点不全 必须被抓到；有方向+切点齐 则过
    def _link(sizes, emos, cuts):
        fd, q = tempfile.mkstemp(suffix=".md"); os.close(fd)
        rows = "".join("| %d | 三分 | %s | 固定 | 2秒 | %d | %s |" % (i + 1, SHOT_SIZES[z], e, c) + chr(10)
                       for i, (z, e, c) in enumerate(zip(sizes, emos, cuts)))
        io.open(q, "w", encoding="utf-8").write(
            "| 镜 | 构图 | 景别 | 运镜 | 时长 | 情绪 | 切点 |" + chr(10)
            + "|---|---|---|---|---|---|---|" + chr(10) + rows)
        return q
    k1 = _link([0, 6, 6, 0], [1, 2, 2, 2], ["首镜", "切在动作", "切在视线", "切在形状"])
    k2 = _link([1, 2, 3, 5], [1, 2, 5, 2], ["首镜", "切在动作", "切在视线", "切在形状"])
    c1 = linkage(k1); c2 = linkage(k2)
    os.unlink(k1); os.unlink(k2)
    if c1 == 1 and c2 == 0:
        ok += 1
        print("  [OK]   衔接：同级相邻/大跳/峰值超 被抓到 · 有方向且切点齐 则过")
    else:
        print("  [NG]   衔接判据异常（反例=%d 正例=%d）" % (c1, c2))
    # ⑧ 设计感：全默认款 + 无落点 必须被抓到；有装置 + 有落点 则过
    def _dsg(comps):
        fd, q = tempfile.mkstemp(suffix=".md"); os.close(fd)
        rows = "".join("| %d | %s |" % (i + 1, c) + chr(10) for i, c in enumerate(comps))
        io.open(q, "w", encoding="utf-8").write("| 镜 | 构图 |" + chr(10) + "|---|---|" + chr(10) + rows)
        return q
    d1 = _dsg(["三分法，主体在左三分之一"] * 4)
    d2 = _dsg(["三人成三角，A 在顶点、B/C 在底边两侧",
               "他位于画面最右侧，左侧三分之二为空，唯一高光落在她脸上",
               "隔着半开的门框看他，门框占画面两侧，他在中景深处",
               "他坐着她站着，只入画他半个身子；焦点由前景杯子移焦到她的脸"])
    c1d = design(d1); c2d = design(d2)
    os.unlink(d1); os.unlink(d2)
    if c1d == 1 and c2d == 0:
        ok += 1
        print("  [OK]   设计感：全默认款+无落点 被抓到 · 装置多样+有落点 则过")
    else:
        print("  [NG]   设计感判据异常（反例=%d 正例=%d）" % (c1d, c2d))
    # ⑨ 多表文档：**只许读含「构图」列的那一张表**（反例：全篇扫 `|` 行会把别的表算成构图）
    #   实测来源：一份交付文档里有 4 张表，`--design` 读到"11 条构图"（实际 6 条）并据此报假警。
    def _doc(first_col, comps):
        fd, q = tempfile.mkstemp(suffix=".md"); os.close(fd)
        other = "| 要求 | 实拍 | AI |" + chr(10) + "|---|---|---|" + chr(10) \
                + "".join("| %s | 一镜多动 | 一画面一动 |" % k + chr(10) for k in first_col)
        rows = "".join("| %d | %s |" % (i + 1, c) + chr(10) for i, c in enumerate(comps))
        io.open(q, "w", encoding="utf-8").write(
            other + chr(10) + "| 编号 | 构图 |" + chr(10) + "|---|---|" + chr(10) + rows)
        return q
    good = ["三人成三角，A 在顶点、B 与 C 在底边两侧",
            "他位于画面最右侧，左侧三分之二为空，唯一高光落在她脸上",
            "隔着半开的门框看他，门框占画面两侧，他在中景深处",
            "她坐着他站着，只入画他半个身子；焦点由前景杯子移焦到她的脸",
            "长桌沿画面对角线延伸，她坐在最远端",
            "他的指尖是画面里唯一清晰的东西"]
    d3 = _doc(["运镜", "调度", "微表情", "景别"], good)
    c3 = design(d3)
    os.unlink(d3)
    if c3 == 0:
        ok += 1
        print("  [OK]   多表文档：只读含「构图」列的那一张表（不把别的表算成构图）")
    else:
        print("  [NG]   多表文档里读错了表（把旁表算成了构图）→ 码 %d" % c3)
    # ⑩ 大跳的"已声明例外"：**写了锚点就不该继续报"要改"**（一直报一个已答的问题＝训练用户无视 WARN）。
    #   配对：同一串景别，一版写锚点（→ 0）· 一版不写（→ 1）。
    #   ★ 两版**只差"有没有写锚"这一个变量**——第一版我用了 `_link([0,6,6,0])`，
    #     那串景别里还夹着一处"相邻同景别"，于是"写了锚"的那版照样 rc=1，
    #     **用例把两件事混在了一起**（自检先把这个错抓出来了）。改成 `0,6,0,6` 隔离变量。
    def _jump_tbl(anchor):
        fd, q = tempfile.mkstemp(suffix=".md"); os.close(fd)
        c2 = "那串钥匙仍在画面右下的桌面上" if anchor else "桌面中段"
        c3 = "同一个物件：钥匙" if anchor else "桌面中段偏近"
        io.open(q, "w", encoding="utf-8").write(
            "| 镜 | 构图 | 景别 | 运镜 | 时长 | 情绪 | 切点 |" + chr(10)
            + "|---|---|---|---|---|---|---|" + chr(10)
            + "| 1 | 空景 | 大远景 | 固定 | 3秒 | 1 | 首镜 |" + chr(10)
            + "| 2 | %s | 特写 | 推 | 2秒 | 2 | 切在动作 |" % c2 + chr(10)
            + "| 3 | %s | 大远景 | 固定 | 3秒 | 5 | 切在视线 |" % c3 + chr(10)
            + "| 4 | 空景 | 特写 | 推 | 2秒 | 2 | 切在形状 |" + chr(10))
        return q
    k3, k4 = _jump_tbl(False), _jump_tbl(True)
    c3j = linkage(k3); c4j = linkage(k4)
    os.unlink(k3); os.unlink(k4)
    if c3j == 1 and c4j == 0:
        ok += 1
        print("  [OK]   大跳：未写锚 判\"要改\" · 已写锚 降为提示（不改变退出码）")
    else:
        print("  [NG]   大跳例外判据异常（无锚=%d 有锚=%d）" % (c3j, c4j))
    # ⑪ 交付件模式：**没扫到（rc=3）要报 SKIP、不计入不合格**
    #   实测：把 12 份声音表一起丢给 `--deliver`，旧实现全报"要改 rc=3"——它们本来就不是镜头稿。
    import tempfile as _tf
    fd, q = _tf.mkstemp(suffix=".md"); os.close(fd)
    io.open(q, "w", encoding="utf-8").write("这不是提示词：只是一张声音表的字段清单。")
    n_skip, _o = deliver([q])
    os.unlink(q)
    if n_skip == 0:
        ok += 1
        print("  [OK]   交付件模式：非镜头稿（没扫到 rc=3）报 SKIP、不算不合格")
    else:
        print("  [NG]   没扫到的文件被算成了不合格（bad=%d）" % n_skip)
    print("\n自检：%d 通过 / %d 失败" % (ok, 11 - ok))
    return 0 if ok == 11 else 1


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return self_test()
    if len(argv) == 1:
        bad, out = doctor()
        print("\n".join(out))
        return 1 if bad else 0
    if argv[1] == "--design" and len(argv) > 2:
        return design(argv[2])
    if argv[1] == "--linkage" and len(argv) > 2:
        return linkage(argv[2])
    if argv[1] == "--rhythm" and len(argv) > 2:
        return rhythm(argv[2])
    if argv[1] == "--grade":
        bad, out = grade(argv[2:])
        print(chr(10).join(out))
        return 1 if bad else 0
    if argv[1] == "--deliver":
        bad, out = deliver(argv[2:])
        print("\n".join(out))
        return 1 if bad else 0
    if argv[1] == "--route" and len(argv) > 2:
        bad, out = route(argv[2])
        print("\n".join(out))
        return bad
    if argv[1] == "--route-json" and len(argv) > 2:
        try:
            from knowledge_routes import resolve_route
        except Exception:
            from scripts.knowledge_routes import resolve_route
        result = resolve_route(SKILL, argv[2])
        print(json.dumps(result, ensure_ascii=False))
        return int(result.get("exit_code", 2))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
