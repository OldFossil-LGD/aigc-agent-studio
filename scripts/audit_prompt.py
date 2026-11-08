#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_prompt.py — 结构断言（只查结构，不判质量）

用法：
  python3 scripts/audit_prompt.py timeline <file.md>      查分镜总表的时间轴
  python3 scripts/audit_prompt.py blocks   <file.md>      查提示词块的结构
  python3 scripts/audit_prompt.py blocks --asset <file.md>  同上，但按静帧类规则（资产提示词）
  python3 scripts/audit_prompt.py blocks --storyboard <file.md>  同上（黑白故事板，同为静帧类）
  python3 scripts/audit_prompt.py index    <skill_dir>     查索引与实际文件是否对应
  python3 scripts/audit_prompt.py index --headroom <skill_dir>  同上，并把 300 行余量升级为 WARN
  python3 scripts/audit_prompt.py claims   <skill_dir>     查 SKILL.md 的数字断言与实测是否相符
  python3 scripts/audit_prompt.py --self-test             跑内建回归用例（改脚本后必跑）

退出码分级（CI 靠这个判绿）：
  0 全过，且**实际扫到了东西**
  1 有 FAIL（结构问题：围栏不成对 / 块内元说明 / 时间轴断裂 / 索引幻影或孤立 / 数字断言对不上）
  2 用法错误（参数不对、路径不存在、未知子命令）
  3 **扫描对象为空**（没有提示词块 / 没有镜头行）—— 不是通过，是"没验到"
  4 只有 WARN（需人工定性，无结构 FAIL）

⚠️ 关键区别：0 与 3 完全不是一回事。历史上出过"贴错文件、脚本照样报 PASS"的假绿，
   所以"什么都没扫到"必须单独用 3 表示，绝不能混进 0。

注意：分数只表示结构完整，不预测生成效果。
"""

import io
import math
import os
import re
import subprocess
import sys
import tempfile

# ---------- 退出码 ----------
try:
    from .knowledge_routes import CatalogError, library_index_text
except ImportError:
    from knowledge_routes import CatalogError, library_index_text

RC_OK = 0      # 全过且扫到了东西
RC_FAIL = 1    # 有结构 FAIL
RC_USAGE = 2   # 用法错误
RC_EMPTY = 3   # 扫描对象为空（没验到，≠ 通过）
RC_WARN = 4    # 只有 WARN

# ---------- 通用 ----------

def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def die(msg, code=RC_USAGE):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


# ---------- timeline ----------
# 用途：校验**排镜表**的「时长」列（规划层）。
# 注意：**提示词那一层不写秒数**（按「段落 / 组合」写，时间由模型自己分配）——
#       本命令因此只对**带时长列的排镜表**有意义；对提示词文件返回 RC_EMPTY 属正常。
# 支持：0.0–2.4 / 0-5 / 0到5秒 / 0.0–2.4s / 00:00-00:04
NUM = r"[+-]?\d+(?:\.\d+)?"
TIME_TOKEN = r"(?:\d{1,2}:\d{2}|" + NUM + r")"
RANGE_PATTERNS = [
    re.compile(r"(?<![\d:.+-])(" + TIME_TOKEN + r")\s*(?:[–—~-]|到|至)\s*("
               + TIME_TOKEN + r")(?![\d:.])"),
]
# ★ 载体兼容（与 `shotlist_lint.py` 第 21–25 行**同一套写法**）：
#   本库编号载体已由「镜几」扩到「段落 / 组合」（`镜N` 自带"剪辑点"预设，会把段内的
#   景别变化误读成硬切）。这里漏掉「段落 / 组合」，段落式排镜表会被判成"没扫到"（RC_EMPTY=3），
#   **且不报错**——只是行行不符合一遍，绿着假。写法兼容 `段落A` / `段落 A` / `组合1` / `组合 甲`。
#   **改任一个载体词都必须补一条对应的自检用例**——否则这条检查会"静默失效"。
SEG_ID = r"(?:段落|组合)\s*[0-9A-Za-z甲乙丙丁一二三四五六七八九十]+"
SHOT_TABLE_ROW = re.compile(
    r"^\s*\|.*?(?:\bSH\s*\d+|镜\s*\d+|镜头\s*\d+|\bMOTION-|" + SEG_ID + r")", re.I)
# 也支持标题式：## SH01 · 0–5 秒 · 拖拽入场（同样兼容 ## 段落A · 0–5 秒）
SHOT_HEADING = re.compile(
    r"^#{2,3}\s+.*?(?:\bSH\s*\d+|镜\s*\d+|镜头\s*\d+|\bMOTION-|" + SEG_ID + r")", re.I)


def _to_seconds(tok):
    m = re.match(r"^(\d{1,2}):(\d{2})$", tok)
    if m:
        if int(m.group(2)) >= 60:
            raise ValueError("seconds must be below 60")
        return int(m.group(1)) * 60 + int(m.group(2))
    return float(tok)


def _first_range(line):
    for pat in RANGE_PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        raw = m.group(0)
        try:
            return _to_seconds(m.group(1)), _to_seconds(m.group(2)), raw
        except ValueError:
            continue
    return None


def cmd_timeline(path):
    lines = read(path).split("\n")
    rows, unparsed = [], []
    for i, line in enumerate(lines, 1):
        if not (SHOT_TABLE_ROW.match(line) or SHOT_HEADING.match(line)):
            continue
        r = _first_range(line)
        if r:
            rows.append((i, r[0], r[1], r[2]))
        else:
            unparsed.append((i, line.strip()[:80]))

    print("文件：%s" % path)
    print("识别到镜头行：%d 条；未识别出时间区的镜头行：%d 条\n" % (len(rows), len(unparsed)))

    if not rows:
        print("[EMPTY] 没有识别到任何镜头行的连续时间区间。")
        print("       本命令校验的是**排镜表**的时长列（规划层）。")
        print("       提示词那一层不写秒数（按「段落 / 组合」写）——若你给的是提示词，这是正常的。")
        if unparsed:
            print("\n疑似镜头行（无法解析时间区，请人工确认）：")
            for i, txt in unparsed:
                print("  L%-5d %s" % (i, txt))
        return RC_EMPTY

    fails = ["L%-5d 无法解析镜头时间区：%s" % (i, text) for i, text in unparsed]
    rows_sorted = sorted(rows, key=lambda r: r[1])
    prev_end = None
    for i, s, e, raw in rows_sorted:
        if not (math.isfinite(s) and math.isfinite(e)) or s < 0 or e <= s:
            fails.append("L%-5d %s 时间区必须为有限非负起点，且终点晚于起点" % (i, raw))
            continue
        if prev_end is None:
            if abs(s) > 0.05:
                fails.append("L%-5d 首镜从 %s 开始，不是 0" % (i, raw))
        else:
            if s < prev_end - 0.05:
                fails.append("L%-5d %s 与前一段重叠（前段结束 %.1f）" % (i, raw, prev_end))
            elif s > prev_end + 0.05:
                fails.append("L%-5d %s 与前一段之间有 %.1f 秒空档（前段结束 %.1f）"
                             % (i, raw, s - prev_end, prev_end))
        prev_end = e

    total = prev_end if prev_end is not None else 0.0
    print("覆盖区间：0.0 → %.1f 秒" % total)
    if fails:
        print("\n[FAIL] 时间轴问题：")
        for f in fails:
            print("  " + f)
        print("\n提示：秒段加总正确，不代表台词说得完——台词另按 3.5–5 字/秒单独核。")
        return RC_FAIL

    print("\n[PASS] 镜头总表时间轴连续：无空档、无重叠、首镜从 0 起。")
    print("       （仍须人工核：每镜台词的时长是否能说完。）")
    return RC_OK


# ---------- blocks ----------

# ===== 12 块契约（依据 block-spec.md §二「每块规格（12 小节 · 9 个字段）」）=====
# ★ 为什么要有这一组（2026-09-17 用户铁律后立）：
#   "写镜头提示词必须逐模块完整处理、不得跳过" —— 此前**库里从来没有"块齐备"的检查**，
#   实测后果：交付件漏人物真实性下限仍能 PASS（v1 就是这么溜过去的）。
#   判据：① **块齐备** 缺哪个点哪个名（FAIL）；② **每块的必需元素** 缺什么点什么（WARN）。
#   ★ 顺序不查——`block-spec.md` §三 自己登记了"两版块序有三种互斥说法"（待确认项），
#     库都未统一，脚本无权替它裁定。
BLOCKS_COMMON = ("后期特效", "统一提质层", "风险移除")
BLOCKS_SHOT = ("本镜目的", "镜头规格", "构图", "人物与环境", "光位与影调",
               "时间线", "运镜", "声音", "过渡压力")
BLOCKS_SEG = ("本段目的", "镜头规格", "光位与影调", "声音", "人物与环境",
              "时间线", "运镜", "过渡压力", "全局约束")
# 块 → (候选关键词, 缺什么)
BLOCK_NEEDS = {
    "本镜目的": (("情绪", "推进", "压力"), "三选一（改变情绪 / 推进动作 / 施加压力）"),
    "本段目的": (("情绪", "推进", "压力"), "三选一（改变情绪 / 推进动作 / 施加压力）"),
    "镜头规格": (("毫米", "mm", "焦段"), "焦段"),
    "构图": (("三分之一", "中央", "中心", "留白", "画框"), "主体位置或留白"),
    # ★ 2026-10-31 补（IR 规范 §4.1.5 / §4.1.8）：无角色镜头写「人物：不适用」是合法形态，
    #   不算缺必需元素；否则每个空镜都会被判缺身份锚点。
    "人物与环境": (("岁", "男性", "女性", "身份锚点", "不适用", "空镜", "无人物入画"), "身份锚点句（或明确 N/A）"),
    "光位与影调": (("光源", "灯", "窗", "光从", "光池", "影子"), "光源出处"),
    "运镜": (("起始观察点",), "起始观察点"),
    # ★ "无配乐" 接受两种写法（2026-09-17 加 · 一手源 `cinema-director-v3` §SLOT 15）：
    #   精确术语 `NO BGM` 或中文等价「无配乐」——**两者都算写了"无配乐"这件必需元素**。
    #   实测教训：改基线写成 `NO BGM` 之后，契约里写死的「无配乐」就再也匹配不上，
    #   于是**所有合格样本全被误判**——**加新术语时必须同时扩契约词表**。
    # ★ 必需元素＝**"声明音乐立场"**，不是"必须无配乐"（2026-09-18 修）。
    #   原有的写法把「无配乐」当死条件 → **有配乐的镜头反而被判"缺元素"**（实测：新加的音乐让路正例就是这么挂的）。
    #   ★ 与"改术语要同步扩词表"是同一条教训：**改"允许范围"必须同步改契约，否则新合法形态会被判错。**
    "声音": (("无配乐", "NO BGM", "no bgm", "配乐", "音乐", "BGM", "bgm"),
             "音乐的立场（「无配乐」/ `NO BGM`，或明写有配乐并交代它与对白的关系）"),
    "过渡压力": (("切", "匹配", "声音桥", "景别落差", "接"), "接法（怎么接下一镜/下一段）"),
    "统一提质层": (("器材", "痕迹", "胶片", "颗粒", "质感"), "器材行或痕迹行"),
    "风险移除": (("禁止出现", "禁止"), "禁止出现清单"),
}
TL_PHASES = ("起始", "主动作", "反应与呼吸", "定格")
# ★ 真实感下限与"默认写实"（2026-09-17 用户规则："未声明风格时，所有东西都应往真实走"）
#   背景：资产模式下此前**只跳过声音/留白，内容一概不查** —— 于是
#   "有些旧了"这种写法（出来是全新塑料）**从来没人拦**，用户反馈"道具、场景都比较假"。
#   ★ 默认值口径：**无显式风格声明 → 系一·写实系**（style-library.md §二）。
DIRT_KEYS = ("逐处写脏", "磨损", "掉漆", "划痕", "积灰", "锈", "油亮", "指印", "指纹",
             "起皮", "褪色", "磕碰", "踢痕", "水渍", "踩亮", "蒙灰", "磨白", "磨出",
             "缺口", "卷边", "泛黄")
MAT_KEYS = ("哑光", "吸光", "不反光", "反光弱", "漫反射", "粗糙无镜面", "开片",
            "接触阴影", "釉面", "纤维")
STYLE_WORDS = ("描边", "平涂", "赛璐璐", "网点", "像素", "水墨", "厚涂", "纯色底",
               "平光", "风格化", "二次元", "动画风", "插画")
STYLE_DECL = ("风格：", "美术风格", "量级系", "非写实", "写实系", "描边系", "第三系",
              "风格化处理：", "风格:")
# ★ 九级景别（`sequence-craft.md` §8.1）——判据"景别由画框装了什么决定"（§8.1b）。
#   2026-09-17 立此表：库里有九级景别与"段落版每段至少跨 ≥2 级"的硬要求，
#   但**门禁不查景别** → 实测两份已过门禁的稿子**都没有声明起始景别**（用户当场指出"景别是不是又没了"）。
#   ★ 长度优先匹配：先长后短，避免"中近景"被算成"近景"、"大特写"被算成"特写"。
SHOT_SIZES = ("大远景", "大特写", "中近景", "中全景", "远景", "全景", "中景",
              "近景", "特写", "插入", "细节")
# ★ 人物"不能锁死"的三条（2026-09-17 立 · 用户看片后指出"开头几秒一直不动、动作后才呼吸、目光也不对"）：
#   依据 `character-realism.md` §4.3「**机位可以锁死，人不能锁死**」（原文给了反例：
#   ❌ 他站在门口等她，一动不动）· `character-depth.md` 表情下限（**每镜必写「眼的落点」**：
#   看哪里、什么时候移开；**呼吸**：在哪一拍屏住、在哪一拍松开）· `performance-craft.md`
#   （出戏成因① "**人物知道自己在被看（摆姿势）**" → 处方："写『没在看镜头』的具体形式"）。
#   ① 人物静止语：主语是"人/他的某部位"却写"不动" → WARN（**"画面/镜头不动"是合法的，豁免**）
#   ② 起始与定格两相必须各含微动或生理活性证据 → WARN（防"起始死机、动作后才活"）
#   ③ 【时间线】里必须有"眼落点"（看哪里、什么时候移开）→ WARN（不写＝模型默认看镜头）
STATIC_SUBJECT = ("他", "她", "人物", "胸口", "上身", "肩膀", "手指", "脸")
STATIC_WORDS = ("几乎不动", "一动不动", "静止不动", "纹丝不动", "完全不动", "像雕塑")
LIVE_EVIDENCE = ("呼吸", "起伏", "重心", "手指", "肩", "眨", "瞳孔", "视线",
                 "目光", "眼神", "移开", "换到")
# ★ 起始相**必须是"动作已在途中"**，不是"待机保持"（2026-09-17 立 · 用户指出
#   "人物在前几秒呆着不动、**似乎在等指令**"）。
#   依据 `motion-principles.md`（B 档实践）：**"复杂动作要从生成的第一帧就直接处于中段"**，
#   甚至明写"砍掉预备、直接从中段起"；`performance-craft.md` 破"虚假"三工具：
#   **反应延迟 · 半途修正 · 未完成与余势**（出戏成因③"动作太对、每个动作都完成得干干净净"）。
#   判据：① 起始相必须有"进行中"证据（已经在/正要/到一半…）；② 起始相不许出现**摆拍位**词。
IN_PROGRESS = ("已经在", "正在", "半途", "到一半", "抬到一半", "举到一半", "转到一半",
               "尚未", "还没", "刚要", "正要", "刚动", "延续")
POSED_HOLD = ("站好", "端正地站", "站得端正", "站定", "两手都放在", "预备好",
              "等待", "等他", "静立", "伫立", "笔直地站")
# ★ 块内**不许出现装饰符号**（2026-09-17 立 · 用户："请你不要随便加这种符号"）。
#   实测：我自己的稿子在提示词块内塞了大量 markdown 强调 **（最严重的一稿 142 处）——
#   **那些星号会被模型当作提示词正文读进去**，既是噪声、也违反"块内只有提示词本身"的口径。
#   禁：markdown 强调 `**` · 装饰星 `★` · emoji 勾 `✅`/警示 `⚠️` · 圈号 ①②③…
#   不禁：`·` 与 `——`（库里方案包原文与中文标点就用它们）。
DECO_SYMBOLS = ("**", "★", "✅", "⚠️", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩")
# ★ 现实逻辑与"填表式写作"四条（2026-09-17 立 · 用户："模块内容明明有但不思考直接写／缺失重要元素／
#   生成的东西缺乏现实逻辑／动作人物不自然"，并要求"自主推进、不要仅限于举例"）。
#   这四条都是**机器可判**的，来源是**对我自己 9 份交付件的体检**：
#   ① 本镜目的填表式（9 稿同一句式、45–54 字，都没有"变化"与"代价"）
#   ② 手部动作过密（一双手装三件事）
#   ③ 接触事件过密（6 秒内 5 处以上）
#   ④ 影子方向与光源位置**反向矛盾**（光从下往上、影子却写"向下投射"）
PURPOSE_CHANGE = ("变成", "变为", "从", "改为", "被打断", "没能", "结果", "转向", "升级", "失去")
HAND_ACTS = ("抬手", "一把", "猛地把", "按住", "抓住", "拽", "抹", "伸向", "拉", "推", "扶")
CONTACT_WORDS = ("按在", "握", "攥", "抵", "贴在", "搭在", "扶着", "抓住", "捏")
CAM_FROM_BELOW = ("下方偏左", "从下方", "由下往上", "自下而上", "桌面显示器")
SHADOW_DOWN = ("向下投射", "朝下投", "影子向下", "向下落")
# ★ 现实逻辑的另三条（2026-09-17 立 · 用户"现实逻辑自查／建立规则"；规则册见 `real-world-logic.md`）
#   轴四 因果链：二级动作必须有因（"被带翻的东西是被什么带翻的"）
SECONDARY = ("被带翻", "被带起", "震出", "弹起", "蹭出", "打了转", "晃了一下")
#   ⚠️ 判据坑：**不能把"被"当成因**——"椅子被带翻"本身就含"被"，会让这条检查永不触发（实测发现）
CAUSE_WORDS = ("因为", "因", "借着", "带着", "随着", "惯性", "动量", "被起身", "被这道")
#   轴一 光源数量：动机光源一到两个；写到四个以上等于没布光
LIGHT_WORDS = ("顶灯", "台灯", "桌灯", "落地灯", "壁灯", "吊灯", "荧光灯", "灯管", "灯泡",
               "霓虹", "招牌", "显示器", "屏幕", "应急灯", "逃生灯", "街灯", "路灯",
               "月光", "阳光", "火光", "炉火", "烛")
#   轴五 时间与动作量：一步约零点七五米，镜内位移超过约两米就该拆镜
STEP_MAX_IN_SHOT = 4
EYE_KEYS = ("视线", "目光", "眼神", "看向", "望向", "移开", "盯")
# ★ 皱纹的"静息—牵拉两态"（2026-09-17 立 · 用户看片后指出）：
#   "嘴边那两条斜的皱纹虽然真实人物也有，但真实人物只有在一些情绪下才会特别明显" ——
#   对应库里 `skin-realism.md` §1.3 皱纹四分类：**动力性**成分由**表情肌牵拉**产生；
#   §三 S5 判据："找到脸上每一道纹，问它垂直于哪块肌肉？那肌肉在动吗？"——
#   **有纹但表情是平的 ＝ 不合格**（AI 味的典型来源：把"最深那一帧"当成常态）。
#   **动力性纹名**（下方表）：**★ 2026-09-17 口径修正（用户二次反馈"嘴边皱纹还是有"）**——
#   **上一轮方向反了**：写"静息时只是很浅的影"**仍然提了名字**，而模型一读到"鼻唇沟"
#   就调用它训练里那个统计印象（图库里带法令纹的照片都是明显的）。
#   **正解＝① 不提纹名；② 换光位**——皱纹是微立体结构，**正面平光下沟影不成立**
#   （`skin-realism.md` §1.4："所有皮肤细节都在正面平光下隐形 · 换光位比改形容词有效得多"）。
#   年龄改用**结构**承载：鬓角白发 / 发际线后退 / 颌线 / 眼下凹陷 / 颈部。
DYN_WRINKLE = ("鼻唇沟", "法令纹", "眉间", "纵纹", "额纹", "额头横", "鱼尾",
               "下睑褶", "皱折", "皱褶")
#   （下表仅保留给"作者自己核对"用；判据已改为"出现纹名即 WARN"，不再要求静息态）
WRINKLE_CALM = ("静息", "只在", "退回", "松开", "平复", "很浅", "浅", "平常",
                "不笑的时候", "面无表情时", "垂着", "舒展开")
# ★ 器材型号与"译成效果"（2026-09-17 立 · 用户追问"提质层真的是电影感的真实吗"）。
#   库里判据（`shot-craft.md`「器材要译成效果」）：**把型号全部划掉，剩下的那句还能不能说清"这部片看着像什么"？**
#   这里做它的机器版：**型号 + 该行剔除型号后是否还剩"观感描述"**。
GEAR_MODELS = ("ARRI", "Alexa", "ALEXA", "RED ", "Kodak", "柯达", "VISION3", "500T", "250D",
               "2383", "Cooke", "Panavision", "Hawk", "MiniDV", "Blackmagic", "Venice",
               "5219", "5213", "iPhone", "手机主摄")
#   ★ 只收**观感词**，不收**工序名**（实测教训：把"印片""底片"当观感词 →
#     "ARRI Alexa · Cooke · 柯达 2383 印片"这种**只丢型号**的写法会漏判，假阴性）。
GEAR_EFFECT = ("滚降", "颗粒", "晕", "青蓝", "暖色", "偏冷", "呼吸", "晃动", "景深",
               "畸变", "眩光", "色散", "噪点", "对比", "饱和", "柔", "厚实", "宽容度",
               "偏灰", "发糊", "硬裁", "拉弯", "拖尾", "色温", "粗", "细")
# ★ 焦段要译成结果（2026-09-17 立 · 自查发现「器材要译成效果」只管器材、漏了焦段）。
#   判据（`shot-craft.md`「焦段也要译成结果」）：**把毫米数划掉，剩下的字还能不能说出"这一镜空间是什么样"？**
#   ★★ 关键区分（实测）：`中等偏浅景深` 是**光圈**的后果，**不算焦段的后果**。
#      我们的稿子**全都写了景深**、却几乎都把焦段当标签——所以这里**只收焦段专属词**；
#      一旦把"景深"收进来，这条检查会被自己的稿子全部假通过（假阴，比假报更隐蔽）。
LENS_MM = re.compile(r"\d{2,3}\s*(?:mm|MM|毫米)")
LENS_EFFECT = ("透视", "视差", "压缩", "边缘拉", "拉伸", "夸大", "前后景", "前中后景",
               "剖面感", "畸变", "桶形", "枕形", "关系保留", "关系不变", "从背景",
               "拔出来", "宽银幕感")
# ★ 三条同源补丁（2026-09-17 立 · 一手源 `cinema-director-v3`，原件见 outputs/higgsfield_skills_原件/）
#   ① 度打头：**模型把视场角当 snap 值、毫米读起来只是建议** → 焦段要写成 `84°（22mm）`
LENS_DEG = re.compile(r"\d{2,3}\s*(?:°|度)")
#   ② NO BGM：**裸的 "no music" 会被读成"弱的风格偏好"，被"生成的视频就该有配乐"的先验覆盖**；
#      `NO BGM` 是生产术语，读起来是硬规格。
NO_BGM_OK = ("NO BGM", "no bgm", "No BGM")
BGM_WEAK = ("无配乐", "不要音乐", "无音乐", "no music", "No music")
#   ③ 方向必须标注参照系：**未标注的方向约一半概率会反转**（`she turns to her OWN right` ≠ `screen-left`）。
DIR_WORD = re.compile(r"[左右]")
DIR_ANCHOR = ("画面", "屏幕", "入画", "他自己的左", "他自己的右", "自己的左", "自己的右")
#   ④ 声线母档（2026-09-17 立 · 一手源 `acting-skill` §8）：**有台词就要有声线描述**——
#      本库把"脸"和"物"都锁成了逐字复用的固定文本，**唯独声线没锁**，于是同角色每场嗓音都在飘。
#      ★ 判据只认"台词出现"，不认"人物存在"——没台词的镜头不该报（否则每镜恒 WARN，成了噪声）。
QUOTE_PAT = re.compile(r"[\u201c\"\u300c][^\u201d\"\u300d]{2,}[\u201d\"\u300d]")
VOICE_KEYS = ("音色", "音域", "声线", "嗓音", "语速", "口音", "沙哑", "音质", "音高")
#   ⑤ 音乐必须让路（2026-09-18 立 · 多源收敛：`mix-loudness.md` §3）：
#      音乐要比对白低 12–18 dB。**判据只认"提到了音乐"**——没提音乐的镜头不该报。
MUSIC_WORD = ("配乐", "音乐", "BGM", "bgm", "score", "cue")
MUSIC_YIELD = ("比对白低", "低于对白", "让路", "退到", "垫底", "低位", "低音量", "压在",
               "对白之下", "之下", "让位", "侧链", "闪避", "under the dialogue", "low in the mix")
#   ★ 否定排除：**"没有音乐"不是"有音乐"**（「无配乐」里含"配乐"两字，不排除就会假阳）。
MUSIC_NEG = ("无配乐", "不要音乐", "没有音乐", "不出现音乐", "NO BGM", "no bgm", "No BGM",
             "无音乐", "no music", "No music", "只留现场音", "只保留现场音")
#   ⑥ 环境层必须存在（2026-09-18 立 · 官方口径 + 三源印证 `sound-prompt-craft.md` §1/§3）：
#      **"没有环境层，场景在声学上是死的——画面在动，声场是空的。"**
#      判据只针对"**有离散事件声、却没有环境/空间词**"这一种情形（不是所有镜头都强制有环境词）。
SFX_HARD = ("脚步", "关门", "开门", "响", "撞", "落地", "敲", "碎裂", "摩擦", "turnstile",
            "footstep", "slam", "clack")
AMBIENT_WORD = ("环境", "底噪", "底床", "空间", "混响", "房间", "走廊", "巷", "街", "室外", "室内",
                "远处", "远车", "空调", "灯管", "灯泡", "顶灯", "电流", "嗡", "雨", "风", "空气",
                "厅", "室", "机房", "车流", "虫", "鸟", "水", "ambient", "room tone")
# ★ 引用优先律的机器口径（`governance-law.md` L5）：**风格编号必须真实存在**。
#   编号从库内各 `style-*.md` **动态抽取**（库改了自动跟上，不手写白名单）。
_LIB_STYLE_IDS = None


def _library_style_ids():
    global _LIB_STYLE_IDS
    if _LIB_STYLE_IDS is not None:
        return _LIB_STYLE_IDS
    ids = set()
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")
    try:
        for fn in os.listdir(d):
            if fn.startswith("style-") and fn.endswith(".md"):
                try:
                    with open(os.path.join(d, fn), encoding="utf-8") as f:
                        ids |= set(re.findall(r"\b([A-G]\d{2})\b", f.read()))
                except OSError:
                    pass
    except OSError:
        pass
    _LIB_STYLE_IDS = ids
    return ids
# ★ 面部肌肉级词表（2026-09-17 第三次复发后立）：生理活性与静息微动**都不含面部**，
#   故单列。依据 character-depth.md「表情动作的下限」：面部不许写情绪词，
#   要写"哪块肌肉、往哪个方向"。
FACIAL_KEYS = ("眉", "颏", "嘴角", "口角", "鼻翼", "眼轮", "下睑", "眼皮", "下唇",
               "咬肌", "蹙", "纵纹", "眼尾")
# ★ 必须是"部位 + 动作"同现才算表情证据（2026-09-17 实测防假阴性）：
#   只查部位词会被**身份锚点**骗过——"左眉中段一道旧疤""右眉略高"里也有"眉"，
#   于是"整条没写表情"反而 PASS（实测 v2 就是这样漏过的）。故用部位紧邻动作的正则。
FACIAL_PARTS = (
    ("眉", "压|抬|挑|皱|紧|动|收|松"),
    ("颏", "绷|紧|收|动"),
    ("嘴角", "下|上|收|松|动|斜"),
    ("口角", "下|上|收|动"),
    ("鼻翼", "张|动|收"),
    ("下睑", "动|收|跳|积"),
    ("眼皮", "动|颤|抬|收"),
    ("下唇", "咬|收|内|动|抿"),
    ("咬肌", "紧|动"),
    ("眼尾", "动|收|挤|皱"),
    ("喉结", "滚|动|紧"),
)
# 由词表生成，不手写长正则——手写那版括号失衡过一次（实测）：
FACIAL_ACT = re.compile("|".join("%s[^。；]{0,10}(?:%s)" % (p, v) for p, v in FACIAL_PARTS))
CAM_HARD = (
    (("起始观察点", "起始位置"), "起始观察点"),
    (("主运动", "运镜", "推", "移", "升", "环绕", "跟"), "主运动"),
    (("锁死", "保持不变", "不变的是"), "锁死项（全程不动的是什么）"),
    (("结尾落点", "落点"), "结尾落点"),
)

# ★ 参考图"角色分工"必须带排除（2026-09-17 立 · 外部学习后补）。
#   依据 `asset-prompt-spec.md` §11：**八种角色，每种都要写"不许它供什么"**
#   （身份 → 不许供姿态与背景 · 风格 → 不许供主体与构图 · 服装 → 不许供模特的脸…）；
#   §11·补：参考图供"艺术方向"，**绝不供"具体身份"**。
#   只在**真的在做角色分工**时才判——判据是 `图N … 供/借 …` 这个搭配；
#   单写"图1 只供脸"**不算**（那只说了正面，我们表里要求的是**明文排除**，两句都要有）。
REF_ROLE = re.compile(r"图\s*[0-9一二三四五六七八九][^。；\n]{0,14}?(?:供|借)")
REF_DENY = ("不许", "不要", "不供", "不继承", "别抄", "不要抄", "不准", "不得",
            "禁止", "排除", "不许它")


def _sub_block(body, key):
    """取出 `【key…】` 这一段（到下一个【为止）——用于**模块归属**与分块检查。

    ★ 必须取**行首**出现的那个（2026-09-17 实测修）：正文里有交叉引用，
      如「（什么时候开、什么时候收 → 见【时间线】）」——若按 `find` 取第一次出现，
      会**取到引用处**，于是检查一直在看错的区段（实测：眼落点检查因此恒报 WARN）。
    ★★ 2026-09-19 **第三次修 · 两处一起改**（都是实测复现的）：
      ① **块名改成"包含匹配"**。段落版的块名是 `【本段共用 · 人物与环境】`、
         `【时间线 · 段内变化】`，而调用方传的是 `【人物与环境】` / `【时间线】`——
         逐字匹配一律取空 → **段落版形态下全部逐块检查静默失效**（假阴：
         皮肤句归属 / 动作过程归属 / 起始·定格微动 / 眼落点 / 二级动作因果 /
         光源数量 / 镜内位移，七项一起死）。实测：`_sub_block(段落版body,"【时间线】")→""`。
      ② **删掉 `body.find` 兜底**。兜底会在"没有行首出现"时取到**交叉引用处**——
         实测 `_sub_block("…（变焦只按【时间线】写明的那一次）。","【时间线】")`
         返回 `'【时间线】写明的那一次）。'`，于是眼落点检查对着这句垃圾报假警。
    """
    inner = key.strip("【】")
    out, on = [], False
    for l in body.split("\n"):
        s = l.strip()
        if s.startswith("【"):
            title = s[1:s.find("】")] if "】" in s else s[1:]
            if on:
                break
            if inner in title:
                on = True
        if on:
            out.append(l)
    return "\n".join(out)


# ★ 2026-10-31 补（对齐 Production IR 规范 §4 的块名表）：第 10 块在规格里叫【摄影机】，
#   B3 样例与门禁旧词表叫【运镜】。二者视为同一块——否则按规格写的稿子会被判"缺块"。
BLOCK_ALIAS = {"运镜": ("运镜", "摄影机"), "摄影机": ("摄影机", "运镜")}


def _check_blocks_contract(body):
    """逐块完整性：返回 (fails, warns)。只对**模板版**（用【】块名）生效。"""
    fails, warns = [], []
    marks = re.findall(r"【[^】\n]{1,24}】", body)
    if len(marks) < 3:
        # ★ 非模板版（未用【】块名）→ **静默跳过本契约**，不报 WARN。
        #   为什么不像别处那样报 WARN：本库自检里有多份**旧式最小样本**（冒号式），
        #   给它们挂 WARN 会一次炸掉 11 条用例（实测）——**误报比漏报更隐蔽（E23）**。
        #   迁移口径：新交付一律用【】模板版（`shot-craft.md`），旧稿逐步迁移；此处只留 INFO。
        return fails, warns
    seg = ("本段共用" in body) or ("★ 时间线 · 段内变化" in body)
    need = list(BLOCKS_COMMON) + list(BLOCKS_SEG if seg else BLOCKS_SHOT)
    # 段落版的"本段共用 · X"与外层块名等价
    def _has_block(nm):
        names = BLOCK_ALIAS.get(nm, (nm,))
        return any(re.search(r"【[^】\n]*%s[^】\n]*】" % re.escape(x), body) is not None for x in names)
    for name in need:
        if not _has_block(name):
            fails.append("**缺块：%s**（%s版必须逐块写全，不得跳过——%s）"
                         % (name, "段落" if seg else "分镜", "`block-spec.md` §二"))
    for name, (keys, what) in BLOCK_NEEDS.items():
        if name not in body:
            continue
        if not any(k in body for k in keys):
            warns.append("块【%s】缺必需元素：**%s**" % (name, what))
    if "时间线" in body:
        # ★ 2026-09-19 修：四相是**单镜**的契约，段落版没有它。
        #   `segmented-shot.md` §三 明写：段内"从不动到动"时
        #   ⛔ 不许用 `起始 / 触发 / 主动作 / 反应`（那是**段间**词汇，模型会读成"这是三个镜头"），
        #   ✅ 改用「他先在…；随后…；最后…」。所以**拿四相去查段落版是拿错尺子**——
        #   实测：一份逐字合规的段落版稿被这条恒报 WARN（假阳；WARN 一多，真问题就没人看了）。
        if seg:
            if not any(k in body for k in ("先：", "随后：", "最后：")):
                warns.append("段落版【时间线】没有「先 / 随后 / 最后」三个相位——"
                             "段内推进要用这三个词组织（`segmented-shot.md` §三）")
        else:
            miss = [x for x in TL_PHASES if x not in body]
            if miss:
                warns.append("块【时间线】四相不全，缺：%s（起始 / 主动作 / 反应与呼吸 / 定格）" % " / ".join(miss))
    if "运镜" in body or "摄影机" in body:
        for keys, what in CAM_HARD:
            if not any(k in body for k in keys):
                warns.append("块【运镜】缺必需元素：**%s**" % what)
    return fails, warns


BANNED_META = [
    ("（改成", "元说明：括号里写着『改成…』——这是给用户看的，不是给模型看的"),
    ("(改成", "元说明：括号里写着『改成…』"),
    ("*可选*", "元说明：*可选*"),
    ("这里填", "元说明：这里填…"),
    ("TODO", "元说明：TODO 未清"),
]
# 思考残留：这些词一出现在块首，几乎必然是写作者把"给自己的备注"漏进了提示词
META_NOTE_PAT = re.compile(
    r"^\s*(?:另注|注[:：]|备注|说明[:：]|附注|注意[:：]|提示[:：]|小注|PS[:：]|P\.S\.)|"
    r"^\s*[（(]\s*(?:说明|注|备注)\s*[:：)]|"
    r"^\s*#{1,6}\s*(?:说明|注|备注)\b"
)
# 空话词（含变体）——只禁原词会被变体绕过（2026-09-11 实测：电影感被禁后「电影质感」照样漏进风格标签行）
EMPTY_HYPE = [
    "电影感", "电影质感", "大片感", "院线感", "震撼", "史诗感", "史诗级",
    "视觉盛宴", "极具冲击力", "冲击力十足", "美轮美奂", "叹为观止",
    "唯美", "氛围感", "氛围拉满", "高级感", "质感十足", "栩栩如生", "身临其境",
    "超高清", "8K", "HDR",
]
# 白名单：这些是真术语，不算空话（词后跟了可测对象）
# 【待确认项】 **预留未接线**：本表目前**一个都不可能命中**——EMPTY_HYPE 里根本没有「细腻」，
#   四个白名单词（细腻颗粒 / 中间调细腻 / 颗粒细腻 / 细节插窗）因此永远匹配不到任何东西。
#   **先不要删**（可能是为未来的宽容名单预留的）：若日后把「细腻」类词加进 EMPTY_HYPE，
#   这张表会自动生效。接线前请勿据本表的存在推断"细腻已被放行"。
#   （对照：`ai_smell_check.py` 的同名 WHITELIST 是真在用的——那边 HYPE 里有「细腻」。）
HYPE_WHITELIST = ["细腻颗粒", "中间调细腻", "颗粒细腻", "细节插窗"]

PLACEHOLDER = re.compile(r"\[[^\]\n]*[\u4e00-\u9fff][^\]\n]*\]")

# ---- 否定式检测（这里最容易误伤，务必分清"否定动作"与"否定状态的描述"）----
#
# skill 要求：写**肯定状态句**（"手平放在桌面"），不写"不要六根手指"。
# 但下面这些**必须放行**，它们是正确写法，不是要改的否定句：
#   · "没有停" / "没有举手" / "没有动"  → 描述**持续状态**（否定一个未发生的动作）= 肯定状态句
#   · "无配乐" / "没人" / "无声"        → 声音层与环境层的标准写法
#   · "不许…不准…"                      → 意图明确的指令式否定（仍是坏写法，要留）
#   · "禁止出现：A / B / C"             → 现象清单（候选里明确说"不算否定式动作句"）
#
# 因此判据改成：**否定词后必须紧跟一个"祈使/排除型"的动作词**才算命中；
# 后跟"完成态或状态词"（停/动/举手/说话…）的，是状态描述 → 放行。
NEG_VERB = (r"(?:出现|添加|加入|生成|让|把|做|使用|采用|包含|带有|露出|打|开|"
            r"加|放|改|变|拉|推|摇|移|环绕|变焦|切|叠化|淡入|淡出|反射|发光|过曝|"
            r"看出|看到|感觉|显得|呈现|模仿|复制|拼接)")
# 状态词：这些跟在否定词后面时，是在**描述一个未发生的动作/持续状态**（=肯定状态句），
# 不是要改的否定式。注意"出现"不在此列——"不要出现X"永远是要改的写法。
NEG_STATE = (r"(?:停|动|举手|说话|张口|换|走|跑|转身|移动|反应|表情|"
             r"声音|光|影|配乐|对白|水印|字幕|人)")
NEG_PAT = re.compile(
    r"(?:不要|别|禁止|严禁|不得|不准|不许)\s*"
    r"(?!" + NEG_STATE + r")"
    r"[\u4e00-\u9fff]{0,6}?" + NEG_VERB
)


def _neg_hits(line):
    """在一个句子里找否定式动作句，返回匹配片段列表。

    必须按**分句**扫，不能整行扫：否则「景别与焦距全程不变」里的「别」
    会被当成否定词（"别"也是"景别/区别/分别"的字），产出假阳性。
    判据：命中片段的左边不能是汉字（否则"别"是词内字，不是否定词）。
    """
    out = []
    for seg in re.split(r"[，,；;。、|]", line):
        for m in NEG_PAT.finditer(seg):
            if m.start() > 0 and re.match(r"[\u4e00-\u9fff]", seg[m.start() - 1]):
                continue   # "景别" / "区别" / "分别" → 不是否定词
            out.append(m.group(0))
    return out
# 现象清单行（"禁止出现：A、B、C" / "【禁止出现】A、B、C"）——候选句已说清这不算否定式动作句，整行豁免
# 2026-09-12 修：此前只认冒号，导致「【禁止出现】换脸、疤痕消失」这种分节标签写法
# 被误报成"否定式动作句"（实报于交付物 表演示范_打烊_单镜分镜.md）。
# 判据仍是"关键字组 + 出现/包含/使用/加入 + 收尾（冒号或右书名号）"——
# 光秃秃的「禁止出现可读文字」（无冒号无括号）仍会被报，那正是要改的写法。
NEG_LIST_PAT = re.compile(
    r"(?:【\s*)?(?:禁止|不要|不得|避免)\s*(?:出现|包含|使用|加入)\s*(?:】|[:：])"
)

AUDIO_KEYS = ["声音", "无配乐", "环境音", "现场音", "[SFX", "音效"]
# 结尾留白：**行首锚定**（`结尾留白：` / `结尾落点：` / `留白：` / 【结尾留白】）
# 为什么不能用子串匹配：`柯达 2383 印片收尾` 里的"收尾"是器材术语，而本库**每条写实系提示词**
# 都带这四个字 —— 用 `"收尾" in body` 测，这条检查会被永久满足，等于**从来没生效过**（实测漏报）。
END_PAT = re.compile(r"(?:^|\n)\s*(?:【[^】\n]{0,12})?(?:结尾|留白)")


def _split_blocks(text):
    """返回 [(起始行号, 块内容)]。"""
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


def _is_spec_doc(path, text):
    """判定这是不是**技能库的规格文档**（而非交付物提示词文件）。

    需要与 `storyboard_lint.py` 第 342–356 行同一条「用途守卫」：
    规格文档的代码围栏里装的是**模板与示例**（`[本镜的景别与机位一句话]` 这类填空槽、
    五段骨架样板），拿交付提示词的规则去查会稳定产出假 WARN
    （实测 `blocks references/storyboard-frame.md` 吐 9 条）。本库纪律：**误报也算 bug**。

    判定条件（任一条成立即判为规格文档）：
      ① 路径落在 `references/` 或 `evals/` 目录下——相对调用（`references/x.md`）与
         绝对路径都判（用 abspath 归一），Windows 反斜杠先换成 `/`；
      ② 开头 6 行里出现「何时读 / 读完回」的规格导语（不在目录里但确实是规格文档的兜底）。
    """
    raw = path.replace("\\", "/")
    ap = os.path.abspath(path).replace("\\", "/")
    for cand in (raw, ap):
        for seg in ("references", "evals"):
            if cand.startswith(seg + "/") or ("/" + seg + "/") in cand:
                return True
    head = "\n".join(text.split("\n")[:6])
    return "何时读" in head or "读完回" in head


def cmd_blocks(path, asset=False, storyboard=False):
    """结构断言。asset / storyboard=True 时按**静帧类**规则：跳过"声音行 / 结尾留白"两项。

    为什么要有这两个开关：**静帧类提示词没有时间轴**——资产图与黑白故事板都是"一张图"，
    没有"这 5 秒发生了什么"，也就不该有声音层与结尾留白（见 `block-playbook-asset.md`
    与 `storyboard-frame.md`）。用镜头规则去查，每块会恒定吐 2 条无意义 WARN；
    **WARN 里混进固定噪声，人就会开始忽略 WARN**，真问题随之漏掉（E23：误报与漏报都算 bug）。
    """
    still = asset or storyboard
    text = read(path)
    blocks, unbalanced = _split_blocks(text)
    fails, warns, notes = [], [], []

    if unbalanced:
        fails.append("代码块围栏不成对（有未闭合的 ```）")

    # ★ 规格文档用途守卫（判据见 _is_spec_doc）：references/ 与 evals/ 下的 .md 装的是
    #   模板与示例，不是要交付给模型的提示词 —— 查它只会产出假 WARN（实测 9 条）。
    #   放在围栏 FAIL 之后：**顺序纪律**仍是"先判 FAIL，再判 EMPTY"——
    #   围栏没闭合是明确的"写坏了"（1），不该被降级成"没扫到东西"（3）。
    if not fails and _is_spec_doc(path, text):
        print("文件：%s" % path)
        print("[SKIP] 这看起来是**规格文档**（references/ 或 evals/ 下的模板与示例），不是交付物提示词。")
        print("       规格文档的围栏里装的是填空槽与样板句，套提示词规则查会稳定产出假 WARN")
        print("       （实测 9 条；本库纪律：误报也算 bug）。")
        print("       要查交付物，请指向实际交付的提示词 .md。")
        return RC_EMPTY

    # ★ 空扫描守卫：没有任何提示词块时**不能报 PASS**——否则"文件写错了/没贴内容"
    #   会被误判为"结构合格"（实测过这个假 PASS）。这是本脚本最重要的一条防伪。
    #   顺序纪律：**先判 FAIL，再判 EMPTY**——围栏未闭合是明确的"写坏了"（1），
    #   不该被降级成"没扫到东西"（3）。
    if not blocks and not fails:
        print("文件：%s" % path)
        print("提示词块：0 个\n")
        print("[EMPTY] 没有找到任何提示词代码块——无法判定结构。")
        print("        可能原因：① 文件里确实没有提示词；② 提示词没放进 ``` 围栏；")
        print("                  ③ 贴错了文件（比如把剧本当成分镜）。")
        print("        ⚠️ 这不是 PASS，是'没验到'——退出码 3。")
        return RC_EMPTY

    print("文件：%s" % path)
    print("提示词块：%d 个\n" % len(blocks))

    for start, body in blocks:
        label = "L%d" % start
        # 元说明
        for pat, desc in BANNED_META:
            if pat in body:
                fails.append("%s 块内出现%s" % (label, desc))
        # ★ 人物块的两条真实性下限（2026-09-17 立 · 实测教训）
        #   `shot-craft.md` 明写"第 7、9 块各带一条真实性下限（不许省）"，
        #   但**门禁里没有这条检查** → 交付件真的漏了，用户当场指出"人物 AI 感严重"。
        #   判据：**只对含人物块的镜头提示词生效**（资产/故事板无时间轴，不查）。
        #   ★ 只认**方括号块名**（12 块模板的正式写法）——旧样本用"人物与环境："冒号式，
        #   若按子串匹配会把既有样本一并误伤（实测：自检立刻多出 2 条假 WARN）。
        # ★ 2026-10-31 补（对齐 Production IR 规范 §4.1.5）：无角色镜头的合法写法是
        #   块 7 明确「人物：不适用 / 空镜 / 无人物入画」。此前没有这条豁免，
        #   每个空镜都会被判 3 条假 WARN（生理活性/静息微动/面部证据）。
        person_na = bool(re.search(r"(人物\s*[：:]\s*不适用|无人物入画|空镜|人物\s*[：:]\s*无)", body))
        if not still and not person_na and ("【人物与环境】" in body or "【人物】" in body):
            bio = sum(1 for w in ("瞳孔", "眨", "呼吸", "泪", "湿线", "喉结") if w in body)
            if bio < 2:
                warns.append("%s 含人物块但**生理活性不足**（瞳孔/眨眼/呼吸/泪膜 命中 %d 种，要求 ≥2 且不是恒定节律）"
                             "——`shot-craft.md` 第 9 块明写『不许省』（→ `character-realism.md` §三）" % (label, bio))
            if not any(w in body for w in ("重心", "起伏", "手指", "肩")):
                warns.append("%s 含人物块但**缺静息微动的体态句**（重心/起伏/手指/肩 至少一处）"
                             "——`shot-craft.md` 第 7 块明写『不许省』（→ `character-realism.md` §四）" % label)

        # ★ 12 块逐块完整性（2026-09-17 用户铁律：不得跳过任何模块）——见 _check_blocks_contract
        if not still:
            bf, bw = _check_blocks_contract(body)
            fails += ["%s %s" % (label, x) for x in bf]
            warns += ["%s %s" % (label, x) for x in bw]

        # ★ 微表情：面部肌肉级 + **必须有变化**（2026-09-17 用户第三次反馈后立）
        #   教训：生理活性（瞳孔/眨眼/呼吸）与静息微动（重心/手指）**都不包含面部肌肉**，
        #   所以"写了瞳孔+呼吸但没写眉/颏/口角"的提示词照样 PASS → 用户第 3 次说
        #   "人物微表情又没了 / 表情几乎没有变化"。故单列这条，且必须查**变化性**：
        #   **只出现一次＝静态表情**，那正是"表情没有变化"的直接成因。
        if not still and not person_na and ("【人物与环境】" in body or "【人物】" in body):
            acts = FACIAL_ACT.findall(body)
            if not acts:
                warns.append("%s 含人物块但**没有任何面部「部位 + 动作」证据**（眉压 / 颏绷 / 嘴角斜下 / 下唇咬…）"
                             "——面部不许写情绪词，要写「哪块肌肉、往哪个方向」（`character-depth.md` 表情下限）；"
                             "注意：**身份锚点里的「眉/眼」不算**" % label)
            elif len(acts) < 2:
                warns.append("%s 面部只有 1 处动作＝**静态表情，没有变化**——微表情必须有起止与拍数"
                             "（`expression-rhythm.md` §1–§3）" % label)

        # ★ 真实感下限 + 「默认写实」规则（2026-09-17 用户规则后立）
        #   ① 道具/场景：「逐处写脏」≥2 处（这是 block-playbook-asset.md 板块 5 的硬要求，
        #      此前**没有任何检查**）；② 材质受光响应；③ 出现风格化词却没有显式风格声明。
        if not storyboard:
            dirt = sum(1 for k in DIRT_KEYS if k in body)
            mats = sum(1 for k in MAT_KEYS if k in body)
            style_w = [k for k in STYLE_WORDS if k in body]
            decl = any(k in body for k in STYLE_DECL)
            if any(k in body for k in ("道具", "陈设", "场景", "物件", "逐处写脏",
                                       "资产设定图", "场景设定图")):
                if dirt < 2:
                    warns.append("%s 道具/场景的**真实感下限不足**（只检出 %d 处「脏」，要求 ≥2 处，"
                                 "每处写「位置 + 形态 + 尺寸」）——只写「有些旧了」＝出来是全新塑料"
                                 "（`block-playbook-asset.md` 板块 5）" % (label, dirt))
            is_scene = ("场景设定图" in body) or ("空间结构" in body)
            is_prop = ("道具资产设定图" in body) or any(k in body for k in ("道具", "器物", "制品"))
            if is_prop and not is_scene and mats == 0:
                warns.append("%s 道具类缺**材质受光响应**（哑光 / 吸光 / 不反光 / 接触阴影）——"
                             "不写受光响应，材质会被抹成同一种塑料面" % label)
            if style_w and not decl:
                # ★ 豁免**否定语境**：禁止/禁用清单里的"平光""描边"是"要避免的东西"，
                #   不是风格声明（实测：v2.1 的"大平光"在禁用行里被误报过一次）。
                NEG = ("禁止", "禁用", "不要", "不得", "避免", "排除", "杜绝", "不允许", "规避")
                live = []
                for ln in body.split("\n"):
                    s = ln.strip()
                    if not s or any(m in s for m in NEG):
                        continue
                    live += [w for w in style_w if w in s]
                if live:
                    warns.append("%s 出现风格化词（%s）却**没有显式风格声明**——本库默认：**未声明即走写实系**"
                                 "（`style-library.md` §二）；要么补一句风格声明，要么删掉这些词"
                                 % (label, " / ".join(sorted(set(live))[:3])))

        # ★ 模块归属（2026-09-17 用户要求"有些内容出现在两个模块里了，确定哪些内容只在哪些模块里"）
        #   依据 `block-spec.md` §三·补 内容归属与去重表。只查两条最确定、最常犯的：
        #   ① 皮肤句只准出现在【光位与影调】（实测：我自己的稿子把它同时写进了【人物与环境】）
        #   ② 动作链只准出现在【时间线】（实测：人物块把整条"入画→按住→回头"复述了一遍）
        if not still:
            pe = _sub_block(body, "【人物与环境】")
            if pe:
                if ("皮肤" in pe) and ("哑光" in pe or "毛孔" in pe):
                    warns.append("%s 【人物与环境】里写了**皮肤句**（哑光/毛孔）——皮肤归【光位与影调】"
                                 "（`block-spec.md` §三·补 归属表第 3 条）" % label)
                if any(k in pe for k in ("入画", "走过来", "走出去", "冲进", "冲出", "扑到",
                                        "两步", "三步", "迈步", "起身")):
                    warns.append("%s 【人物与环境】里出现**动作过程**——动作链归【时间线】，"
                                 "人物块只写姿态与状态（`block-spec.md` §三·补 归属表第 8 条）" % label)

        # ★ 景别（2026-09-17 立 · 用户指出"景别是不是又没了"）：库里 `sequence-craft.md` §8.1 有九级景别、
        #   §8.2 有占比硬线、段落版还要求"每段至少跨 ≥2 级"，但**门禁一条都不查** →
        #   实测两份已过门禁的稿子【镜头规格】里**没有景别**。故补两条：
        #   ① 单镜：【镜头规格】必须声明**起始景别**；② 段落版：全段**至少 2 级且跨级**（库里硬要求）。
        if not still:
            spec = _sub_block(body, "【镜头规格】")
            sizes = [k for k in SHOT_SIZES if k in body]
            if spec and not any(k in spec for k in SHOT_SIZES):
                warns.append("%s 【镜头规格】**没有声明景别**——九级景别里选一级写死"
                             "（大远景/远景/全景/中景/中近景/近景/特写/大特写/插入）"
                             "（`sequence-craft.md` §8.1）" % label)
            if ("本段共用" in body) or ("★ 时间线 · 段内变化" in body):
                if len(set(sizes)) < 2:
                    warns.append("%s 段落版只有 %d 级景别——**每段内部至少跨 ≥2 级**，"
                                 "整条只有一个景别＝不合格（`sequence-craft.md` §8.2）"
                                 % (label, len(set(sizes))))

        # ★ 皱纹：**不写纹名 + 换光位**（2026-09-17 二次修正 · 用户反馈"嘴边皱纹还是有"）
        #   **上一轮方向反了**：写"静息时只是很浅的影"**仍然提了名字**，模型一读到"鼻唇沟"
        #   就调用训练里那个统计印象（图库里带法令纹的照片都是明显的）→ **越提越深**。
        #   **正解两条**：① **不提纹名**（年龄改用结构承载：鬓发/发际线/颌线/眼下/颈部）；
        #   ② **把光位改成正面平光**——皱纹是微立体结构，沟影在平光下不成立
        #   （`skin-realism.md` §1.4："所有皮肤细节都在正面平光下隐形 · 换光位比改形容词有效得多"）。
        if not still:
            NEGW = ("禁止", "禁用", "不要", "不得", "避免", "排除", "杜绝", "不允许", "规避")
            live_body = "\n".join(ln for ln in body.split("\n")
                                  if ln.strip() and not any(m in ln for m in NEGW))
            dyn = [k for k in DYN_WRINKLE if k in live_body]
            if dyn:
                warns.append("%s 写了皱纹名「%s」——**不要把纹名写进提示词**：一提名字，模型就调用"
                             "「深沟」的统计印象（图库里带法令纹的照片都是明显的）；**改用两条**："
                             "①**年龄靠结构承载**（鬓角白发 / 发际线后退 / 颌线 / 眼下凹陷 / 颈部）；"
                             "②**光位改成正面平光**（皱纹是微立体结构，沟影在平光下不成立）"
                             "（`skin-realism.md` §1.4：「换光位比改形容词有效得多」）" % (label, " / ".join(dyn[:2])))

        # ★ 器材要译成效果（2026-09-17 立 · 用户追问"提质层真的是电影感的真实吗"）
        #   库里判据：**把型号全部划掉，剩下的那句还能不能说清"这部片看着像什么"？**
        #   机器版：**型号存在，但把型号剔掉后那一段没有剩下任何"观感描述"** → WARN（＝只丢了型号）。
        if not still:
            gear = _sub_block(body, "【全片通用 · 统一提质层】") or _sub_block(body, "【统一提质层】")
            if gear and any(m in gear for m in GEAR_MODELS):
                stripped = gear
                for m in GEAR_MODELS:
                    stripped = stripped.replace(m, "")
                if not any(k in stripped for k in GEAR_EFFECT):
                    warns.append("%s 【统一提质层】里有器材型号，但**剔掉型号后没有任何观感描述**——"
                                 "型号只是锚点，模型不懂它拍出来什么样；补一句「这台机器拍出来是…」"
                                 "（`shot-craft.md`「器材要译成效果」：划掉型号还能说清观感才算写了）" % label)

        # ★ 焦段要译成结果（2026-09-17 立 · 与上一条同源：同一条规则在焦段上的补齐）
        #   判据：**把毫米数划掉，剩下的字还能不能说出「这一镜空间是什么样」？**
        #   ⚠️ 只收**焦段专属**结果词：「景深」是光圈的事，收进来会让"只写焦段"的稿子全部假通过。
        if not still:
            spec = (_sub_block(body, "【镜头规格】") or _sub_block(body, "【本段共用 · 镜头规格】"))
            if spec and LENS_MM.search(spec) and not any(k in spec for k in LENS_EFFECT):
                warns.append("%s 【镜头规格】写了毫米数，却**没写焦段带来的空间结果**——"
                             "把毫米数划掉，剩下的字说不出「这一镜空间是什么样」，就等于只写了标签。"
                             "补一句：广角端写边缘拉伸与前后景比例夸大、长焦端写压缩感与人物从背景里被拔出来；"
                             "⚠️ **别拿「景深」顶替**（那是光圈的事，两个都要有）"
                             "（`shot-craft.md`「焦段也要译成结果」）" % label)

            # ★ ③ 度打头（2026-09-17 立 · 一手源 `cinema-director-v3` §SLOT 8）
            #   "The model latches onto degrees as a snap value; millimetres read as suggestion."
            if spec and LENS_MM.search(spec) and not LENS_DEG.search(spec):
                warns.append("%s 【镜头规格】只写了毫米数，**没写视场角（度）**——"
                             "模型把「度」当 snap 值、把毫米读成「建议」，所以要写成 `84°（22mm）`，"
                             "**度在前、毫米放括号**（十档对照表见 `shot-craft.md`「度打头」）" % label)

        # 〔已撤回〕`NO BGM` 精确术语检查 —— 2026-09-17 地毯式全量搜索后撤回。
        #   理由见 `block-spec.md`【声音】块的「已撤回」条目：该术语**只出现在 `cinema-director-v3`**，
        #   而**同一技能的后继版本 CINEDANCE V4 明确改用 `No music unless requested`** ——
        #   即当初我用来说服自己保留它的机制理由（"裸 no music 会被读成弱偏好"）
        #   **被来源自己的后继版本推翻**。
        #   ★ 可复用教训：**单源规则要盯它的后续版本**——后继弃用 = 作者自己把它证伪了。

        # ★ ④ 方向必须标注参照系（2026-09-17 立 · 一手源 `cinema-director-v3` §SLOT 6）
        #   原文：unlabelled direction inverts about half the time。本库默认走屏幕相对（画面左/右）。
        if not still:
            comp = _sub_block(body, "【构图】")
            if comp and DIR_WORD.search(comp) and not any(k in comp for k in DIR_ANCHOR):
                warns.append("%s 【构图】写了「左/右」，却**没标注它是谁的左右**——"
                             "未标注的方向约一半会反转；本库默认走**屏幕相对**（`画面左` / `画面右`），"
                             "写「角色自己的左右」时必须带「他自己的」"
                             "（`staging-craft.md` §6.1 · `cinema-director-v3` §SLOT 6）" % label)

        # ★ ④ 声线母档（2026-09-17 立 · 一手源 `acting-skill` §8）
        #   判据：**【声音】块里有台词，却没有声线描述** → WARN（只认台词，不认人物——没台词的镜头不该报）。
        if not still:
            snd2 = _sub_block(body, "【声音】")
            if snd2 and QUOTE_PAT.search(snd2) and not any(k in snd2 for k in VOICE_KEYS):
                warns.append("%s 【声音】块里有台词，却**没写声线**——本库把脸与物都锁成了逐字复用的固定文本，"
                             "**唯独声线没锁**，于是同一个角色每场戏的嗓音都在飘。"
                             "补一份声线母档（音色 · 音域 · 语速与说话方式 · 受压时在哪里破），"
                             "**紧跟他的那句台词、逐字复用**（`sound-craft.md` §一·补 · `acting-skill` §8）" % label)

        # ★ ⑤ 音乐必须让路（2026-09-18 立 · 多源收敛）
        #   判据：**【声音】块提到了音乐/配乐，却没写它与对白的关系** → WARN。
        #   依据：`mix-loudness.md` §3「音乐比对白低 12–18 dB」+ 一句判据"闭上眼，第一个听清的是人话吗？"
        if not still:
            snd3 = _sub_block(body, "【声音】")
            # ★ 必须先排除"没有音乐"的写法——否则「无配乐」里的"配乐"两字会把它判成"有音乐"（假阳）。
            #   这正是本库的纪律：**写判据时要先拿自己的稿子试一遍**（实测：本库绝大多数镜头就是无配乐）。
            _has_music = any(k in snd3 for k in MUSIC_WORD)
            _negated = any(k in snd3 for k in MUSIC_NEG)
            if snd3 and _has_music and not _negated and not any(k in snd3 for k in MUSIC_YIELD):
                warns.append("%s 【声音】写了音乐/配乐，却**没写它与对白的关系**——"
                             "音乐必须**让路**（比对白低 12–18 dB；对白密集或长镜头退到 −28 ~ −24 dBFS）。"
                             "补一句它的位置（如「音乐比对白低一档」「音乐在对白下让路/垫底」）"
                             "（`mix-loudness.md` §3 · 判据：「闭上眼，我第一个听清的是人话吗？」）" % label)

        # ★ ⑥ 环境层必须存在（2026-09-18 立 · 官方口径 + 三源印证）
        #   判据：**【声音】块写了离散事件声（脚步/关门/响/撞…），却没有任何环境或空间词** → WARN。
        #   "没有环境层，场景在声学上是死的——画面在动，声场是空的。"
        #   ★ 只针对这一种情形，**不强制每镜都写环境词**（否则会变成噪声）。
        if not still:
            snd4 = _sub_block(body, "【声音】")
            if snd4 and any(k in snd4 for k in SFX_HARD) and not any(k in snd4 for k in AMBIENT_WORD):
                warns.append("%s 【声音】写了离散事件声（脚步/关门/响…），却**没有任何环境或空间信息**——"
                             "**没有环境层，场景在声学上是死的：画面在动，声场是空的。**"
                             "补一句环境签名（这是哪、这个空间'什么都没发生'时有什么声），"
                             "并且**先写环境、后写事件**（`sound-prompt-craft.md` §1/§3）" % label)

        # ★ ⑦ 首行画幅必须与包的画幅同值（2026-09-18 立 · 用户"仔细一行行检查"后补的防再犯门禁）
        #   实测：4 份首行写「画幅21:9」，而【统一提质层】的包写「画幅 2.39:1」——**21:9＝2.33:1，不是 2.39:1**。
        #   这是"跨块自相矛盾"里最容易犯的一种：**首行是感观标签、包是硬规格，两者会各自漂移。**
        #   规范写法：`画幅2.39:1（21:9 落地）`——**把近似值标注在括号里**，不要并列成两个值。
        if not still:
            head = next((l for l in body.split("\n") if l.startswith("分镜头脚本")), "")
            kit = next((l for l in body.split("\n") if l.strip().startswith("摄影与印片")), "")
            if head and kit:
                hdr219 = ("21:9" in head)
                kit239 = ("2.39:1" in kit)
                if hdr219 and kit239 and "2.39" not in head:
                    warns.append("首行画幅写「21:9」，而包的画幅是「2.39:1」——**21:9 是 2.33:1，两者不是同一个值**；"
                                 "改成 `画幅2.39:1（21:9 落地）`：把近似值放括号里，不要并列成两个值"
                                 "（`quality-layer.md` 的统一提质层规格）")

        # ★ ⑧ 形态专属检查（2026-09-19 立 · 多形态 12 轮压测后补）
        #   只对**带该形态标记**的提示词生效，不影响单镜稿（避免对既有交付件产生假报）。
        #   为什么只做这三条：它们是本轮 13 类缺陷里最硬、最不易假阳的三条；
        #   其余形态判据（长镜五相 / 逐段跨级 / 卡的引用）**措辞变体多**，硬判会假报，先留在人工检查表。
        if not still:
            is_seg = ("段落 A" in body) or ("段落A" in body)
            is_multi = ("A（主动）" in body) or ("A(主动)" in body) or ("两人同框" in head)
            if is_seg:
                # 分段镜：恰好 N 段 N-1 切换点必须写死（不写死，模型自己决定切几次）
                if not (("个段落" in body) and ("个切换点" in body)):
                    warns.append("分段镜**没写死「恰好 N 个段落、N-1 个切换点」**——"
                                 "不写死，模型会自己决定切几次（`segmented-shot.md` 的全局约束）")
                # 分段镜：段内不许出现「第 N 秒」
                if re.search(r"第\s*\d+\s*秒", body):
                    warns.append("分段镜的段内出现了**「第 N 秒」**——段落语法用相位（先…随后…最后…）组织，"
                                 "**不用秒**；秒只活在首行总时长（`segmented-shot.md` / 用户 2026-09-14 定案）")
                # 分段镜：每段必须跨 ≥2 级景别
                #   ★ 必须数**不同的段落字母**（A/B/C），不能数「段落」出现次数——
                #     标题与【时间线】里会重复出现，数次数会得到 6 而声明只有 3 → **假阳**
                #     （实测：本条刚加时把 3 份合格的分段镜全判成 WARN。**新判据先拿自己的稿子试一遍**。）
                nseg = len(set(re.findall(r"段落\s*([A-Z])", body)))
                if nseg and body.count("跨 ≥2 级") + body.count("跨≥2级") < nseg:
                    warns.append("分段镜**每段内部至少要 1 次景别级变化（跨 ≥2 级）**，"
                                 "现在写了 %d 段、只声明了 %d 处跨级——整条一个景别＝不合格"
                                 "（`segmented-shot.md`）" % (nseg, body.count("跨 ≥2 级") + body.count("跨≥2级")))
            if is_multi and not any(k in body for k in ("只有 A 动", "只有一个人动", "一次只有一个人动",
                                                        "绝不主动起动作", "此刻 A 停住")):
                warns.append("多人物**没声明「一次只有一个人动」**——两人同时动＝观众不知道看谁、模型必崩；"
                             "写明主动方是谁、从动方只做呼吸或一次吞咽（`staging-craft.md` §五第 5 条）")

        # ★ ⑨ 方案包与光圈矛盾（2026-09-19 立 · 用户"检查是否有提示词被写死默认"）
        #   实测：`R6` 用的是 **P01 手机主摄（器材行明写「固定光圈」）**，却在【镜头规格】写「光圈 f2.0 中浅景深」
        #   —— **写死的 f2.0 与包本身的物理矛盾**。这是 block-spec §三·补「不许写死的七个变量」里
        #   **唯一能被机检的一条**（其余六条只能人核）。
        if not still:
            _kit = next((l for l in body.split("\n") if l.strip().startswith("摄影与印片")), "")
            _lens = next((l for l in body.split("\n") if l.startswith("【镜头规格】")), "")
            if _kit and _lens and ("固定光圈" in _kit) and re.search(r"光圈\s*f\s*[\d.]+", _lens):
                warns.append("【镜头规格】写了具体光圈值，但方案包的器材行明写「**固定光圈**」——"
                             "**这是写死的默认值与包本身矛盾**（手机主摄没有可调光圈，也不该写浅景深）；"
                             "改成与包一致的写法（固定光圈 / 深景深），或换包"
                             "（`block-spec.md` §三·补 七个不许写死的变量 · 第 3 条）")

        # ★ 引用优先律（`governance-law.md` L5）：**风格编号必须是库里真实存在的**。
        #   自编编号（库里查不到）= 引用优先律被破；这也是"自编型号"的同类问题在别的模块的形态。
        if not storyboard:
            ids = _library_style_ids()
            if ids:
                used = set(re.findall(r"\b([A-G]\d{2})\b", body))
                bad = sorted(x for x in used if x not in ids)
                if bad:
                    warns.append("%s 出现**风格编号 %s**，但库里没有这个编号——引用优先律（`governance-law.md` L5）："
                                 "**库里有的必须从册里取、不许自编**；要么换成库内真实编号，要么先把它补进库"
                                 % (label, " / ".join(bad[:3])))

        # ★ 人物"不能锁死"三条（2026-09-17 立 · 用户看片后指出三症状）
        #   依据 `character-realism.md` §4.3（机位可以锁死，人不能锁死）· `character-depth.md`
        #   表情下限（每镜必写眼落点与呼吸节拍）· `performance-craft.md`（出戏成因① 摆姿势）。
        if not still:
            # ① 人物静止语（"画面/镜头不动"是合法的，豁免）
            stat = [w for w in STATIC_WORDS if w in body]
            if stat:
                # ★ 必须遍历**每一处**出现（实测教训：用 body.find 只查第一处，
                #   第一处"画面几乎不动"被豁免后，第二处"胸口几乎不动"根本没被检查 → 漏判）。
                for m in re.finditer("|".join(STATIC_WORDS), body):
                    pre6 = body[max(0, m.start() - 6):m.start()]
                    if any(cam in pre6 for cam in ("画面", "镜头", "机位", "摄影机")):
                        continue
                    if any(s in pre6 for s in STATIC_SUBJECT):
                        warns.append("%s 写了人物**静止语**「%s」——`character-realism.md` §4.3："
                                     "**机位可以锁死，人不能锁死**；改写成持续的静息微动"
                                     "（呼吸起伏很浅但不停 / 重心换过一次 / 手指松了一下又收回）"
                                     % (label, m.group(0)))
                        break
            # ② 起始与定格两相必须各含微动或生理活性证据
            tl = _sub_block(body, "【时间线】") or _sub_block(body, "【★ 时间线 · 段内变化】")
            if tl:
                for ph in ("起始", "定格"):
                    i = tl.find(ph)
                    if i < 0:
                        continue
                    seg = tl[i:i + 160]
                    if not any(k in seg for k in LIVE_EVIDENCE):
                        warns.append("%s 【时间线】的「%s」相**没有微动或生理活性**——"
                                     "人不能锁死：呼吸/重心/手指/视线至少要有一样在动"
                                     "（`character-realism.md` §4.3 / `character-depth.md`）" % (label, ph))
            # ③ 眼落点（每镜必写：看哪里、什么时候移开）
            if tl and not any(k in tl for k in EYE_KEYS):
                warns.append("%s 【时间线】里**没有「眼落点」**——表情下限要求每镜写清"
                             "「看哪里、什么时候移开」；不写，模型默认让人物**直视镜头**"
                             "（＝摆姿势、出戏；`performance-craft.md` 出戏成因①）" % label)

            # ③·补 参考图角色分工必须带"不许它供什么"（2026-09-17 立 · 外部学习）
            #   不排除 → 模型把那张图**整体抄走**（脸 / 构图 / 材质一起搬）——这是参考图最常见的失败。
            #   ★ 判据按**引用声明处的窗口**判，不按全篇：`禁止` / `不要` 这些词在【风险移除】里必然出现，
            #     全篇搜会**恒不报**（假阴）。窗口取声明点前 60 / 后 140 字——我们的写法是
            #     「图1 只供脸，图2 只供配色——不要抄图2、图3 的物体与文字」，排除句就在同句附近。
            if not still:
                for m in REF_ROLE.finditer(body):
                    win = body[max(0, m.start() - 60): m.end() + 140]
                    if any(k in win for k in REF_DENY):
                        continue
                    warns.append("%s 在给参考图分角色（%s）却**没写「不许它供什么」**——"
                                 "一张参考图只供一样东西，其余要**明文排除**"
                                 "（身份 → 不许供姿态与背景 · 风格 → 不许供主体与构图 · 服装 → 不许供模特的脸）；"
                                 "只写「只供 X」不够，模型会把它整体抄走"
                                 "（`asset-prompt-spec.md` §11 八类角色表 · §11·补）"
                                 % (label, m.group(0).strip()))
                    break

            # ④ 起始相必须"已在途中"（2026-09-17 立 · 用户："呆着不动、似乎在等指令"）
            #    依据 `motion-principles.md`（**第一帧就处于动作中段**）与 `performance-craft.md` 破"虚假"三工具。
            if tl:
                i = tl.find("起始")
                if i >= 0:
                    seg = tl[i:i + 200]
                    # ★ 子句级**否定语境豁免**（实测误报：稿内的批注写"不是『站好等他开始』"
                    #   被当成了摆拍位）——与空话词检查同一机制。
                    seg_clean = "；".join(
                        ln for ln in seg.split("；")
                        if not any(n in ln for n in ("不是", "而非", "不要", "不写",
                                                     "禁止", "避免", "别")))
                    posed = [k for k in POSED_HOLD if k in seg_clean]
                    if posed:
                        warns.append("%s 【时间线】的「起始」相出现**摆拍位**词「%s」——那等于给模型一个"
                                     "**待机位**（他会一直站到动作被触发，看起来像**在等指令**）。改写成"
                                     "**已经在途中**：重心已偏向一侧 / 手已抬到一半 / 头已转向目标方向"
                                     "（`performance-craft.md`：僵硬是「没信息」，虚假是「信息太整齐」）"
                                     % (label, posed[0]))
                    elif not any(k in seg for k in IN_PROGRESS):
                        warns.append("%s 【时间线】的「起始」相没有**「已在途中」**的证据——"
                                     "起点读起来是「保持态」，模型就会先**待机**再启动（＝等指令）。"
                                     "写成「手已经抬到一半 / 重心已经偏向一侧 / 他刚从上一拍延续过来」"
                                     "（`motion-principles.md`：**复杂动作要从第一帧就处于中段**）" % label)

        # ★ 块内不许装饰符号（2026-09-17 立 · 用户："请你不要随便加这种符号"）
        #   实测：我的稿在提示词块内塞了大量 `**`（最严重 142 处）——**会被模型当正文读进去**。
        hits = [x for x in DECO_SYMBOLS if x in body]
        if hits:
            fails.append("%s 块内出现**装饰符号** %s（共 %d 处）——块内一切都会被当提示词执行："
                         "`**` / `★` / `✅` / 圈号都是噪声，**提示词正文里不许有**；"
                         "要强调就直接写完整句子，要编号就用 `1.`（见 `governance-law.md`）"
                         % (label, " ".join(hits[:4]), sum(body.count(x) for x in hits)))

        # ★ 现实逻辑与"填表式写作"四条（2026-09-17 立 · 用户要求"自主推进"）
        #   来源：对我自己 9 份交付件的体检（见 `sources-and-credits.md` 同日条目）。
        if not still:
            # ① 本镜目的不许填表式（要写清"从什么变成什么"或"代价"）
            pur = _sub_block(body, "【本镜目的】")
            if pur and not any(k in pur for k in PURPOSE_CHANGE):
                warns.append("%s 【本镜目的】**没有写出变化**（从什么变成什么 / 代价是什么）——"
                             "「改变情绪 / 推进动作 / 施加压力」三选一之后必须落到**本镜具体的变化**上，"
                             "否则这一块只是填表（`shot-craft.md` 第 4 块：答不出来的镜头应当删掉）" % label)
            # ② 一双手装几件事（阈值 4：三件是"两只手各一件 + 一件顺带"，四件才是不自然）
            tl2 = _sub_block(body, "【时间线】") or _sub_block(body, "【★ 时间线 · 段内变化】")
            h = sum(1 for k in HAND_ACTS if k in tl2)
            if tl2 and h >= 4:
                warns.append("%s 【时间线】里手部动作 %d 处——**一双手在 6 秒里做不了四件事**；"
                             "现实逻辑上要「减动作」或「拆镜」（人只有两只手，每只手一次只能占一件事）" % (label, h))
            # ③ 接触事件过密（★ 只查【时间线】：实测教训——按全篇计数会把**禁止项**
            #    （"不做抓握特写"）与**身份锚点**（"常年握笔留下的压痕"）误算成动作，造成假阳性）
            c = sum(tl2.count(k) for k in CONTACT_WORDS)
            if tl2 and c >= 4:
                warns.append("%s 【时间线】里接触事件 %d 处（按在/握/抵/贴在/搭在/抓住）——**6 秒内接触过密**："
                             "手与物的接触是本库高失败项，也是「不自然」的高发处；减到 2 处以内，"
                             "其余改成「已经握住」这类持续状态，而不是反复发生的动作" % (label, c))
            # ④ 影子方向与光源位置反向矛盾
            if any(k in body for k in CAM_FROM_BELOW) and any(k in body for k in SHADOW_DOWN):
                warns.append("%s **影子方向与光源位置矛盾**：光源在人物下方（显示器/低角度灯），"
                             "影子就不会「向下投射」——现实逻辑是「光在下、影在上」（或投到身后的墙与天花板上）；"
                             "改掉这句，否则整张脸的明暗关系会自相矛盾" % label)

            # ⑤ 轴四 因果链：二级动作必须有因（现实逻辑自查 · `real-world-logic.md` §1 轴四）
            #   ★ 判据范围＝**【时间线】段**（实测第三次修正）：全篇搜索会被别处的"被"骗过
            #     （如【本镜目的】里的"他被逼到那一步"），让这条检查静默失效；
            #     且必须**先把二级动作短语本身剔掉**再找"因"，否则"被带翻"自身就含"被"。
            _tl_c = _sub_block(body, "【时间线】") or _sub_block(body, "【★ 时间线 · 段内变化】")
            sec = [k for k in SECONDARY if k in _tl_c]
            resid = _tl_c
            for _k in SECONDARY:
                resid = resid.replace(_k, "")
            resid = resid.replace("已经被", "").replace("已经", "")   # "已经被…"是完成式，不是因
            if sec and not any(k in resid for k in ("被", "因", "借着", "带着", "随着", "惯性", "动量")):
                warns.append("%s 出现**二级动作**（%s）却没有写出**因**——每个动了的东西都要答"
                             "「它是被什么弄动的」（`physical-feedback.md` §四：二级动作必须有因；"
                             "`real-world-logic.md` 轴四）" % (label, " / ".join(sec[:2])))
            # ⑥ 轴一 光源数量：动机光源一到两个，写到四个以上等于没布光
            lo = _sub_block(body, "【光位与影调】")
            lights = [k for k in LIGHT_WORDS if k in lo]
            if len(lights) >= 4:
                warns.append("%s 【光位与影调】里出现 %d 种光源（%s）——**动机光源一到两个**；"
                             "光源一多，模型会把它们均质化成大平光，明暗关系反而全失"
                             "（`real-world-logic.md` 轴一）" % (label, len(lights), " / ".join(lights[:4])))
            # ⑦ 轴五 时间与动作量：镜内位移超过约两米就该考虑拆镜（一步约零点七五米）
            tl3 = _sub_block(body, "【时间线】") or _sub_block(body, "【★ 时间线 · 段内变化】")
            if tl3:
                m = re.search(r'([二三四五六七八九十两\d]+)\s*步', tl3)
                if m:
                    z = m.group(1)
                    num = {'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(z, None)
                    if num is None:
                        try: num = int(z)
                        except ValueError: num = 0
                    if num >= STEP_MAX_IN_SHOT:
                        # ★ 已声明的例外：本库有两条写明的路径可以超出镜内位移上限——
                        #   ① 「参考视频/首尾帧驱动」路径（周期动作与长位移**禁止用纯文字提示词求解**，
                        #      官方口径：文字教走路会出成姿态说明图）② 机位代走（写明了摄影机跟着走）。
                        #   这两种情况下原稿**已声明**，再报 WARN 就是误报（误报比漏报更隐蔽，E23）。
                        declared = ("参考视频" in body) or ("首尾帧" in body)
                        if declared:
                            notes.append("%s 【时间线】%d 步（约 %0.1f 米）超镜内位移上限，"
                                         "**但本块已声明参考视频／首尾帧驱动路径**——属既定例外，不判 WARN。"
                                         "仍请确认：参考素材够 2–3 步、纯色背景、无遮挡"
                                         "（`actor-movement.md` 位移四种写法 · 路径②）" % (label, num, num*0.75))
                        else:
                            warns.append("%s 【时间线】写了 %d 步——一步约零点七五米，**镜内位移已约 %0.1f 米**，"
                                         "超过「镜内位移超过约两米就考虑拆」的上限：要么改成**跨镜位移**"
                                         "（切过去他已经在那边），要么把机位代走。三步以内才是安全的镜内位移"
                                         "（`actor-movement.md` §5 · `real-world-logic.md` 轴五）" % (label, num, num*0.75))

        # 思考残留（另注 / 注： / 备注：…）
        meta_lines = [(n, ln.strip()[:60]) for n, ln in enumerate(body.split("\n"), start)
                      if META_NOTE_PAT.search(ln)]
        if meta_lines:
            fails.append("%s 块内混入思考残留（元说明）：L%d「%s」——块内一切都会被当提示词执行，"
                         "把这条挪到块外" % (label, meta_lines[0][0], meta_lines[0][1]))
        # 空话词与变体（白名单：跟了可测对象的术语不算空话）
        # 负面语境豁免：出现在「禁止/禁用/不要…」清单里的词，是"要避免的东西"，不算空话正用
        NEG_CTX = ("禁止", "禁用", "不要", "不得", "避免", "排除", "杜绝", "不允许", "规避")
        hypes, ctx_neg = [], False
        for ln in body.split("\n"):
            s = ln.strip()
            if not s:
                ctx_neg = False
                continue
            if any(m in s for m in NEG_CTX):
                ctx_neg = True
            if ctx_neg:
                continue
            if "❌" in s or "反例" in s or "无效写法" in s or "不要写" in s:
                continue
            s_wl = s
            for wl in HYPE_WHITELIST:
                s_wl = s_wl.replace(wl, "")
            for w in EMPTY_HYPE:
                if w in s_wl and w not in hypes:
                    hypes.append(w)
        if hypes:
            warns.append("%s 块内出现空话词（含变体）：%s —— 换成具体器材 / 行为 / 材质" % (label, "、".join(hypes[:6])))
        # 未替换占位符（区分「解析性占位」与「真未替换」）
        ph = PLACEHOLDER.findall(body)
        if ph:
            # 整块几乎全是占位符 = 骨架模板，是故意的；混在实文里 = 真没替换
            placeholder_ratio = sum(len(x) for x in ph) / max(len(body), 1)
            if placeholder_ratio > 0.6:
                notes.append("%s 整块是占位符骨架（%.0f%%）——按设计如此，跳过未替换检查"
                             % (label, placeholder_ratio * 100))
            else:
                warns.append("%s 块内疑似未替换的占位符：%s" % (label, "、".join(ph[:3])))
        # 否定式（判据见 NEG_PAT / _neg_hits 注释：按分句扫、排除"景别"这类词内字）
        hits = []
        for n, ln in enumerate(body.split("\n"), start):
            if NEG_LIST_PAT.search(ln):
                continue
            got = _neg_hits(ln)
            if got:
                hits.append((n, ln.strip()[:60], got[0]))
        if hits:
            warns.append("%s 块内出现 %d 处疑似否定式动作句（需人工确认已改成肯定状态句）："
                         "首处 L%d「%s」命中「%s」"
                         % (label, len(hits), hits[0][0], hits[0][1], hits[0][2]))
        # 声音（**静帧类豁免**：资产图与黑白故事板都没有时间轴，本就不该有这一行）
        if still:
            what = "资产模式（--asset）" if asset else "故事板模式（--storyboard）"
            notes.append("%s %s：跳过「声音行 / 结尾留白」两项检查——"
                         "静帧类提示词没有时间轴（见 block-playbook-asset.md / storyboard-frame.md）"
                         % (label, what))
        else:
            if not any(k in body for k in AUDIO_KEYS):
                warns.append("%s 块内没看到声音相关行（无配乐 + 显式列出关键环境音）" % label)

    # 结尾留白：**按整篇查，不按块查**——分段镜只有最后一段带结尾落点，中间段写的是接口状态。
    # 且必须**行首锚定**：`柯达 2383 印片收尾` 里的"收尾"是器材术语，不是结尾留白——
    # 本库每条写实系提示词都带这四个字，用子串匹配会让这条检查**从来没生效过**（实测漏报）。
    if not still and not END_PAT.search(text):
        warns.append("全文没看到结尾/留白相关句（最后一个镜头该用空位收，不堆对白/爆炸/强光）")

    if notes:
        for n in notes:
            print("[INFO] " + n)
    if warns:
        print("[WARN] 需人工确认：")
        for w in warns:
            print("  " + w)
    if fails:
        print("\n[FAIL] 结构问题：")
        for f in fails:
            print("  " + f)
        print("\n注意：脚本只查结构。否定式那几条由你判——'禁止出现：X' 是现象清单，"
              "不算否定式动作句；'不要六根手指' 才是要改的。")
        return RC_FAIL

    if warns:
        print("\n[PASS*] 代码块成对、无元说明、无未替换占位符——但有 %d 条 WARN 待人工定性。" % len(warns))
        print("        （退出码 4：结构没坏，不等于内容能交付。）")
        return RC_WARN

    print("\n[PASS] 代码块成对、无元说明、无未替换占位符。")
    print("       （WARN 项仍需人工过一遍；脚本不判质量。）")
    return RC_OK


# ---------- index ----------

REF_PAT = re.compile(r"references/[A-Za-z0-9_\-./]+\.md")
REF_DIR_PAT = re.compile(r"references/([A-Za-z0-9_\-]+)/")

# 文件长度上限：references 保持 ≤300 行（拆分阈值，超了就拆）
#
# ★ 适用范围（2026-09-15 明确 · 此前只写在注释里、没写清边界）：
#   · **适用**：`SKILL.md` 与 `references/**/*.md`。理由：**它们是"写提示词时会被读的手册"**，
#     长了会让关键指令落在中段被丢（`prompt-ops.md` 的注意力稀释）。
#   · **不适用**：`references/examples/**`（交付样例）与 `evals/**`（评测题库）——
#     它们是**案例与题库，不是手册**，正常使用时不进上下文；`evals/scenarios.md` 现 917 行属正常。
#     **但"不适用"必须写下来**——否则 917 行那份看起来像漏网，下一个人会去拆它。
#   · `scripts/*.py` 不适用（代码，按可读性组织，不受此限）。
# 为什么设这条：文件一长，同一概念容易在两处各写一遍（历史上出过），
# 而"没超 300 行"此前**没有任何自动检查**——真出过 shot-craft.md 涨到 357 行没人发现。
MAX_REF_LINES = 300
MAX_SKILL_LINES = 300

# 余量预警阈值（2026-09-15 补）：≥290 行即"下一步就可能顶穿"。
# **默认只报 INFO，--headroom 才升 WARN** —— 理由见 cmd_index 里的注释（避免 14 条噪声）。
HEADROOM_LINES = 290


def _count_lines(path):
    """行数。**本库以 `len(read().splitlines())` 为准**，与 `wc -l` **不一致**：

    `wc -l` 数的是**换行符个数**；文件最后一个没有尾随换行时，那一行不计
    → 恰好比本函数少 1（实测：`references/segmented-shot.md` Python 计 300、`wc -l` 计 299，
      正好卡在 MAX_REF_LINES=300 的边界上，两种口径会给出相反的"要不要拆"结论）。
    **代码行为不变**：现在的口径（含无尾随换行的末行）是对的，改掉的只是这句注释。
    """
    with io.open(path, encoding="utf-8", errors="replace") as f:
        n = 0
        for _ in f:
            n += 1
        return n


def cmd_index(skill_dir, headroom=False):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        die("找不到 %s" % skill_md)

    try:
        text = library_index_text(skill_dir)
    except (CatalogError, OSError, UnicodeError) as exc:
        print("[FAIL] declared library index: %s" % exc)
        return RC_FAIL
    ref_dir = os.path.join(skill_dir, "references")

    mentioned = sorted(set(REF_PAT.findall(text)))
    mentioned_dirs = sorted(set(REF_DIR_PAT.findall(text)))

    on_disk = []
    for root, _dirs, files in os.walk(ref_dir):
        for fn in files:
            if fn.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, fn), skill_dir).replace("\\", "/")
                on_disk.append(rel)
    on_disk.sort()

    print("skill 目录：%s\n" % skill_dir)
    print("SKILL.md 提到：%d 个文件 + %d 个目录" % (len(mentioned), len(mentioned_dirs)))
    print("references/ 实际：%d 个 .md\n" % len(on_disk))

    fails, warns = [], []
    # 幻影
    for m in mentioned:
        p = os.path.join(skill_dir, m.replace("/", os.sep))
        if not os.path.isfile(p):
            fails.append("幻影引用：SKILL.md 提到 %s，文件不存在" % m)
    # 孤立
    for d in on_disk:
        base = os.path.basename(d)
        if d in mentioned or base in text:
            continue
        parent = os.path.basename(os.path.dirname(d))
        if parent != "references" and parent in mentioned_dirs:
            continue
        fails.append("孤立文件：%s 没有被 SKILL.md 提到过（补进索引，或删掉）" % d)
    # 长度上限（超限 = 该拆了，不是 FAIL 但要立刻处理）
    skill_lines = _count_lines(skill_md)
    if skill_lines > MAX_SKILL_LINES:
        warns.append("SKILL.md %d 行，超过 %d 行上限——规则手册只留索引与判据，细节外移"
                     % (skill_lines, MAX_SKILL_LINES))
    for d in on_disk:
        p = os.path.join(skill_dir, d.replace("/", os.sep))
        n = _count_lines(p)
        if n > MAX_REF_LINES:
            warns.append("%s %d 行，超过 %d 行上限——拆出一个新文件，并在 SKILL.md 索引里挂上"
                         % (d, n, MAX_REF_LINES))

    # ---------- 300 行「余量」预警（2026-09-15 补 · O2） ----------
    # 为什么默认只报 INFO：本库当前有 14 份 ≥290 行，若一律判 WARN，**每次跑都吐 14 条**
    # → 噪声淹没真问题（E23：误报也是 bug）。所以：**默认 INFO 常驻可见，--headroom 才升 WARN**。
    # 判据一句话：**超 300 是 FAIL 级事故（要立刻拆）；≥290 是"下一次改动会顶穿"的预警（要排期）。**
    near = []
    if skill_lines >= HEADROOM_LINES:
        near.append(("SKILL.md", skill_lines))
    for d in on_disk:
        p = os.path.join(skill_dir, d.replace("/", os.sep))
        n = _count_lines(p)
        if n >= HEADROOM_LINES:
            near.append((d, n))
    near.sort(key=lambda kv: -kv[1])
    if near and headroom:
        warns.append("余量预警：%d 份文件 ≥%d 行（余量 ≤%d）——下一次改动很可能顶穿，先排拆卷"
                     % (len(near), HEADROOM_LINES, MAX_REF_LINES - HEADROOM_LINES))
    elif near:
        print("[INFO] 余量预警：%d 份文件 ≥%d 行（余量 ≤%d）——**这是预警不是错误**；"
              "要它进退出码就加 --headroom" % (len(near), HEADROOM_LINES, MAX_REF_LINES - HEADROOM_LINES))
        for d, n in near[:6]:
            print("         %3d 行  余 %d   %s" % (n, MAX_REF_LINES - n, d))
        if len(near) > 6:
            print("         ……另 %d 份" % (len(near) - 6))
        print()

    if warns:
        print("[WARN] 需要处理：")
        for w in warns:
            print("  " + w)
        print()

    if fails:
        print("[FAIL] 索引一致性问题：")
        for f in fails:
            print("  " + f)
        return RC_FAIL

    print("[PASS] 无幻影、无孤立：SKILL.md 的索引与 references/ 一一对应。")
    if warns:
        print("       （但有 %d 条长度 WARN，见上）" % len(warns))
        return RC_WARN
    return RC_OK


# ---------- claims：数字断言 vs 实测（2026-09-15 补 · O1） ----------

_CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def _cn2int(s):
    if s == '十':
        return 10
    if s.startswith('十'):
        return 10 + _CN.get(s[1:], 0)
    if '十' in s:
        a, b = s.split('十')
        return _CN.get(a, 0) * 10 + (_CN.get(b, 0) if b else 0)
    return _CN.get(s, 0)


# ── `claims --refs`（2026-10-01 新增 · `governance-law.md` L4·补 早就建议、一直没做的那条）──
#
# **为什么它默认只报 INFO、且必须显式 --refs-strict 才进退出码**：
#   本库 `references/` 里的「N 行」断言**绝大多数不是缺陷，是记录**。2026-10-01 全量普查实测：
#   带册名锚点的「N 行」断言共 **81 处**，其中**语义上是「历史/迁移态」的至少 70 处**——
#     · 历史态：`key-decisions.md` 里「新建 `music-craft.md`（159 行）」＝**成册当时**的行数，现 161；
#     · 迁移态：「`libtv-canvas-nodes.md` **304 → 299**」＝拆卷前后两个数，朴素解析只会取第一个。
#   **若把它们一律判 FAIL，就是 70 条假警报** —— 而 E23 写死了「**误报比漏报更隐蔽**」「不许为了
#   看起来有门禁而编一条会产生误报的检查」。**这正是 `claims` 当年只扫 `SKILL.md` 的原因：
#   不是偷懒，是当时没有能避开误报的判据。**
#
# **本函数的立场**：把普查结果**如实摆出来**（有多少处、多少处一致、多少处判不了、
# 多少处疑似当前态漂移），让人能分诊；**不替人决定哪条该改**。
REFS_SKIP_MARKERS = (
    "\u2192", "\u2190", "\u62c6", "\u79fb\u5165", "\u79fb\u51fa", "\u539f\u518c", "\u9876\u683c",
    "\u65b0\u5efa", "\u843d\u5e93", "\u7eed\u518c", "\u4e0a\u9650", "\u672c\u518c\u5230", "\u539f ",
)

# ★ 第三条结构性规则（2026-10-01 加）：**`key-decisions.md` 是决策日志，它记的是「当时」**。
#   按 L6，已定条目的内容是**历史事实**，「新建 X（N 行）」里的 N 就是**成册当时**的行数，
#   册后来长到 N+2 不是漂移。**故整册按性质跳过**——这不是关键词猜测，是文件职责决定的。
#   （前两条是文本规则、这条是结构规则；实测加上它，待分诊项从 26 降到个位数。）
REFS_HISTORY_LOGS = ("key-decisions.md",)


def cmd_claims_refs(skill_dir, strict=False):
    """`claims --refs`：普查 `references/` 里的数字断言（**默认只报 INFO**）。

    口径一律按 `governance-law.md` L4·补：`N 行` = `len(read().splitlines())`。
    **只处理「N 行」且同一行能解析出册名锚点**的断言——这是唯一能可靠复算的一类；
    `N 条`/`N 册` 的口径已分别由 `claims`（取图册条目数）与 `index`（册数）覆盖，不在此重复实现。
    """
    ref = os.path.join(skill_dir, "references")
    if not os.path.isdir(ref):
        die("没有 references/ 目录：%s" % ref, RC_USAGE)
    names = set(f for f in os.listdir(ref) if f.endswith(".md"))
    cache = {}

    def real_lines(fn):
        if fn not in cache:
            try:
                cache[fn] = len(read(os.path.join(ref, fn)).splitlines())
            except Exception:
                cache[fn] = -1
        return cache[fn]

    total = agree = skipped = drift = 0
    drifts = []
    for fn in sorted(names):
        for ln, line in enumerate(read(os.path.join(ref, fn)).splitlines(), 1):
            for m in re.finditer(r"(\d+)\s*\u884c", line):
                seg = line[max(0, m.start() - 70):m.end() + 12]
                anchor = None
                for nm in names:
                    if nm in seg:
                        anchor = nm
                        break
                if anchor is None:
                    continue
                total += 1
                got = int(m.group(1))
                real = real_lines(anchor)
                if real < 0:
                    continue
                if fn in REFS_HISTORY_LOGS:
                    skipped += 1          # 决策日志＝历史记录（L6 已定条目记的是当时值）
                elif got == real:
                    agree += 1
                elif any(k in seg for k in REFS_SKIP_MARKERS):
                    skipped += 1          # \u5386\u53f2/\u8fc1\u79fb\u6001\uff1a**\u4e0d\u62a5\u9519**\uff0c\u53ea\u8bb0\u8d26
                else:
                    drift += 1
                    drifts.append((fn, ln, got, real, anchor))

    print("\u2500\u2500 claims --refs\uff1areferences/ \u6570\u5b57\u65ad\u8a00\u666e\u67e5\uff08\u53e3\u5f84\uff1aN \u884c = splitlines\uff09\u2500\u2500")
    print("  \u5e26\u518c\u540d\u951a\u70b9\u7684\u300cN \u884c\u300d\u65ad\u8a00\uff1a**%d \u5904**" % total)
    print("    \u4e00\u81f4 %d \u2502 \u8df3\u8fc7\uff08\u5386\u53f2/\u8fc1\u79fb\u6001\uff0c\u4e0d\u62a5\u9519\uff09%d \u2502 \u7591\u4f3c\u5f53\u524d\u6001\u6f02\u79fb %d" % (agree, skipped, drift))
    if drifts:
        print("")
        print("  \u7591\u4f3c\u5f53\u524d\u6001\u6f02\u79fb\uff08**\u672a\u81ea\u52a8\u5224\u9519** \u2014\u2014 \u9700\u4eba\u5206\u8bca\uff0c\u53ef\u80fd\u662f\u8bb0\u5f55\u53e3\u5f84\u4e0d\u540c\uff09\uff1a")
        for fn, ln, got, real, anchor in drifts[:15]:
            print("    %s:%d  \u5199 %d \u2192 \u5b9e\u6d4b %d\uff08\u951a\u70b9 %s\uff09" % (fn, ln, got, real, anchor))
        if len(drifts) > 15:
            print("    \u2026\u5176\u4f59 %d \u5904" % (len(drifts) - 15))
    print("")
    if strict and drift:
        print("  [FAIL] --refs-strict\uff1a%d \u5904\u7591\u4f3c\u6f02\u79fb\u8fdb\u5165\u9000\u51fa\u7801" % drift)
        return RC_FAIL
    print("  \u9ed8\u8ba4**\u53ea\u62a5 INFO\u3001\u4e0d\u52a8\u9000\u51fa\u7801**\uff08E23\uff1a\u8bef\u62a5\u6bd4\u6f0f\u62a5\u66f4\u9690\u853d\uff09\u2014\u2014\u8981\u62a5\u9519\u52a0 `--refs-strict`\u3002")
    return RC_OK


def cmd_claims(skill_dir):
    """查 SKILL.md 里的**数字断言**与实测是否相符。

    设计纪律（**刻意只对"能可靠复算"的断言下判断**）：
      · 能复算 → 对不上判 **FAIL**（数字错了会引导错误决策，与"索引幻影"同级）
      · 不能可靠复算（"N 行"这类口径依赖上下文）→ **只报"无法自动核"**，绝不猜
    最后一条很重要：**审计工具最怕的不是漏报，是把解析误差当成真错报出来。**
    """
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        die("找不到 %s" % skill_md)
    try:
        text = library_index_text(skill_dir)
    except (CatalogError, OSError, UnicodeError) as exc:
        print("[FAIL] declared library index: %s" % exc)
        return RC_FAIL
    ref = os.path.join(skill_dir, "references")

    def _md_files(prefix):
        out = []
        for root, _d, files in os.walk(ref):
            for fn in files:
                if fn.endswith(".md") and fn.startswith(prefix):
                    out.append(os.path.join(root, fn))
        return sorted(out)

    # ---- 实测值 ----
    # 防御性读取：**这个命令要能在"只有 SKILL.md 的残缺目录"里跑完**（自检就是这么用的）。
    # 缺文件 → 计 0，而不是抛 FileNotFoundError。判据：**审计工具不该因为被审对象残缺而崩，
    # 它该说"实测 0，与断言的 17 不符"。**
    def _r(path):
        return read(path) if os.path.isfile(path) else ""

    style_docs = [p for p in _md_files("style-library")
                  if os.path.basename(p) not in ("style-library.md", "style-library-index.md")]
    ids = set()
    for p in style_docs:
        ids |= set(re.findall(r'^### ([A-G]\d{2}) · ', read(p), re.M))
    vol_n = len(style_docs)
    src_n = len(_md_files("style-sources-"))
    # ★ 2026-10-01（P2-1 修）：取图册**条目数**此前**无门禁**——src_n 数的是**文件数**(8)，
    #   而 SKILL.md 断言的「247 条」从来没人核过 → 数字漂了也没人知道（下一个 187 的空门禁）。
    #   口径见 governance-law.md L4·补：`**[★]? A01 ·`（★ 可选——c1/c2 两册无 ★，两种格式并存）。
    _src_item_pat = re.compile(r'^\*\*[\u2605]?\s*([A-G]\d{2})\s*\u00b7')
    src_items = []
    # ★ 故意**不吞异常**：第一版这里写了 `except Exception: pass`，结果函数名打错（`_read`→`read`）
    #   被静默吞掉、src_item_n 变成 0，门禁于是理直气壮地报「实测 0」——
    #   **一个会静默归零的检查比没有检查更坏**（它给的是假证据）。此处宁可崩。
    for _p in _md_files("style-sources-"):
        for _ln in read(_p).splitlines():
            _m = _src_item_pat.match(_ln)
            if _m:
                src_items.append(_m.group(1))
    src_item_n = len(src_items)
    src_dups = sorted(set(x for x in src_items if src_items.count(x) > 1))
    card_n = len([p for p in _md_files("style-cards-") if not p.endswith("style-cards-scale.md")])
    pkg_n = len(re.findall(r'^#### P\d+', _r(os.path.join(ref, "camera-package-library.md")), re.M))
    ext_n = len(re.findall(r'^#### P\d+', _r(os.path.join(ref, "package-extended.md")), re.M))
    pit_n = len(re.findall(r'^### PF\d+', _r(os.path.join(ref, "pitfalls.md")), re.M))
    exp_n = len(re.findall(r'^\| *\d+ *\|', _r(os.path.join(ref, "expression-library.md")), re.M))

    # 七脚本自检数：**只有真跑一次才知道**（数用例源码是脆的）。
    #
    # ★ 递归防线（2026-09-15 实测踩到）：`claims` 要跑 `audit_prompt --self-test`，
    #   而那个自检里又调用 `claims` → **无限套娃**。症状很隐蔽：自检仍能打印"X 通过"，
    #   但 `audit_prompt` 自己那一项**永远拿不到**（被子进程 timeout 掐掉，静默缺项）。
    #   修法：**子进程带 NESTED 环境变量；子进程里的 claims 看到它就跳过 spawn**（深度只有 1 层）。
    NESTED = "AUDIT_PROMPT_NESTED"
    selftest = {}
    if not os.environ.get(NESTED):
        child_env = dict(os.environ)
        child_env[NESTED] = "1"
        # ★ 2026-10-01 补 libtv_orchestrate（站6.5/6.6/6.7 编排器）与 workrally_bridge（站6.5 投喂桥）。
        #   后者此前是真空缺：SKILL.md:214 断言了「workrally_bridge.py 14 条」，但它不在本元组内
        #   → claims 永远不核它，那条数字可静默漂移。这就是「下一个 187」的最短路径：断言在、门禁不在。
        for name in ("audit_prompt", "ai_smell_check", "storyboard_lint", "shotlist_lint", "script_lint",
                     "sound_lint", "lib_doctor", "libtv_orchestrate", "workrally_bridge"):
            sp = os.path.join(skill_dir, "scripts", name + ".py")
            if not os.path.isfile(sp):
                continue
            try:
                r = subprocess.run([sys.executable, sp, "--self-test"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=90, env=child_env)
                out = r.stdout.decode("utf-8", "replace")
                # ★ 必须取「通过 + 失败」＝**用例总数**。
                #   只读"通过数"是错的：有 1 条失败时通过数＝总数−1，会被误判成"断言过期"。
                #   （2026-09-15 实测踩到：自检 29/1 时被读成 29，而 SKILL.md 写的 26 是总数。）
                m = re.search(r'自检：\s*(\d+)\s*通过\s*/\s*(\d+)\s*失败', out)
                if m:
                    selftest[name] = int(m.group(1)) + int(m.group(2))
                else:
                    m = re.search(r'自检：\s*(\d+)\s*通过', out)
                    if m:
                        selftest[name] = int(m.group(1))
            except Exception:
                pass

    # ---- 逐条断言： (正则, 说明, 期望值) ----
    rules = [
        (r'全库\s*\**(\d+)\**\s*条', "全库风格条目数", len(ids)),
        (r'(\d+)\s*条\s*·\s*十三卷', "风格条目数（索引行）", len(ids)),
        (r'([一二三四五六七八九十]+)\s*卷', "风格库分卷数", vol_n),
        (r'\((\d+)\s*包\)', "方案包数（主包）", pkg_n),
        (r'补充\s*(\d+)\s*包', "补充包数", ext_n),
        (r'犯过的\s*(\d+)\s*类', "pitfalls 类数", pit_n),
        (r'`expression-library\.md`\s*(\d+)\s*条', "expression-library 条数", exp_n),
    ]
    fails, ok, unver = [], [], []
    for pat, desc, expect in rules:
        hits = re.findall(pat, text)
        if not hits:
            continue
        for h in hits:
            raw = h if isinstance(h, str) else next((x for x in h if x), "")
            got = _cn2int(raw) if not raw.isdigit() else int(raw)
            if got == expect:
                ok.append("%s = %d ✓" % (desc, expect))
            else:
                fails.append("%s：SKILL.md 写 %s，实测 %d" % (desc, raw, expect))

    # 「N 册」的归类：**在同一条行内找最近的文件名**，用文件名定归属。
    #
    # 为什么不能用固定字符窗、也不能只看"向前"（2026-09-15 连踩三次）：
    #   ① **漏检**：`★ 全库 247 条已全部覆盖（9 册）` 前后 34 字里没有关键词 → 被跳过，
    #      **而这正是唯一的真错数**。
    #   ② **误判**（窗口）：同一行里 `style-cards-*.md`（7 册）前 34 字内有"参照/生成"（校准卡的用语）
    #      → 校准卡的 7 册被归成取图册。
    #   ③ **误判**（只向前）：索引表里"文件名在数字**之后**"的行，向前找会抓到**上一行**的锚
    #      → 行276 的「9 册」被归成校准卡。
    # **教训：判据要有确定的锚，且锚的作用域要写清楚——这里的作用域是「同一条行」。**
    anchor_re = re.compile(r'style-(?:sources|cards)-[a-z0-9\-]*')
    for m in re.finditer(r'(\d+)\s*册', text):
        ls = text.rfind('\n', 0, m.start()) + 1
        le = text.find('\n', m.end())
        line = text[ls:le if le != -1 else len(text)]
        rel = m.start() - ls
        cands = list(anchor_re.finditer(line))
        if not cands:                      # 行内没有文件名锚 → 不猜，跳过（**宁可漏，不可误报**）
            continue
        anchor = min(cands, key=lambda c: abs((c.start() + c.end()) / 2 - rel)).group(0)
        desc, expect = ("校准卡册数", card_n) if anchor.startswith("style-cards") else ("取图册册数", src_n)
        got = int(m.group(1))
        if got == expect:
            ok.append("%s = %d ✓" % (desc, expect))
        else:
            fails.append("%s：SKILL.md 写 %d，实测 %d（锚：%s）" % (desc, got, expect, anchor))
    # ---- ★ 取图册**条目数**（P2-1 · 2026-10-01 新增门禁）----
    # 只在**同一行内**有 `style-sources-` 锚点时才判：风格库今天也是 247 条但口径不同，
    # 不锚作用域就会把两者混为一谈 —— 而这正是「锚的作用域要写清楚」那条纪律的由来。
    for _m in re.finditer(r"(\d+)\s*条", text):
        _ls = text.rfind("\n", 0, _m.start()) + 1
        _le = text.find("\n", _m.end())
        _line = text[_ls:_le if _le != -1 else len(text)]
        if "style-sources-" not in _line:
            continue
        _got = int(_m.group(1))
        if _got == src_item_n:
            ok.append("取图册条目数 = %d ✓" % src_item_n)
        else:
            fails.append("取图册条目数：SKILL.md 写 %d，实测 %d（锚：style-sources-）" % (_got, src_item_n))
    if src_dups:
        fails.append("取图册编号重复：%s" % "、".join(src_dups))
    else:
        ok.append("取图册编号零重复 = %d ✓" % src_item_n)

    # 自检数断言（形如「`audit_prompt.py` **26 条**」）
    for name, real in selftest.items():
        m = re.search(re.escape(name) + r'\.py`\s*\**(\d+)\s*条', text)
        if m:
            if int(m.group(1)) == real:
                ok.append("%s 自检 = %d ✓" % (name, real))
            else:
                fails.append("%s 自检：SKILL.md 写 %s，实测 %d" % (name, m.group(1), real))

    # 「N 行」这类：口径依赖上下文 → 只登记，不判
    for m in re.finditer(r'(\d+)\s*行', text):
        unver.append("…%s…" % text[max(0, m.start() - 30):m.end() + 4].replace("\n", " ")[-48:])

    # ---- 库级状态断言：**这类数字不在 SKILL.md 里，而在 references/*.md 里** ----
    # 2026-09-15 实测教训：`pitfalls.md` 写着「本库有 12 份 ≥290 行、其中 5 份顶格 300 行」，
    # 而当时实为 **14 份 / 6 份**——**只扫 SKILL.md 的检查器看不见它**。
    # 判据：**"关于库自身状态的数字"是摘要位的一种，散在任何文件里都要核。**
    def _all_md():
        out = []
        for root, _dd, files in os.walk(ref):
            for fn in files:
                if fn.endswith(".md") and os.sep + "examples" + os.sep not in os.path.join(root, fn):
                    out.append(os.path.join(root, fn))
        return sorted(out)

    _scope = [skill_md] + _all_md()
    near_n = len([1 for p in _scope if _count_lines(p) >= HEADROOM_LINES])
    top_n = len([1 for p in _scope if _count_lines(p) == MAX_REF_LINES])
    for p in _scope:
        base = os.path.basename(p)
        t = _r(p)
        for mm in re.finditer(r'(\d+)\s*份\s*≥?\s*290', t):
            got = int(mm.group(1))
            (ok if got == near_n else fails).append(
                "%s「%d 份 ≥290 行」%s" % (base, got, "✓" if got == near_n else "——实测 %d" % near_n))
        for mm in re.finditer(r'(\d+)\s*份\s*\**顶格', t):
            got = int(mm.group(1))
            (ok if got == top_n else fails).append(
                "%s「%d 份顶格 300」%s" % (base, got, "✓" if got == top_n else "——实测 %d" % top_n))

    print("skill 目录：%s\n" % skill_dir)
    print("实测：风格条目 %d ｜ 分卷 %d ｜ 取图册 %d ｜ 校准卡 %d ｜ 主包 %d ｜ 补充包 %d ｜ pitfalls %d ｜ 表情 %d"
          % (len(ids), vol_n, src_n, card_n, pkg_n, ext_n, pit_n, exp_n))
    print("      七脚本自检：%s\n" % (" ｜ ".join("%s=%d" % kv for kv in sorted(selftest.items())) or "（没跑到）"))

    if ok:
        print("[OK] 对得上的断言（%d）：" % len(ok))
        for s in ok:
            print("  " + s)
        print()
    if unver:
        print("[INFO] 无法自动核的「N 行」类断言 %d 处（口径见 governance-law.md L4·补）：" % len(unver))
        for s in unver[:4]:
            print("  " + s)
        print()
    if fails:
        print("[FAIL] 数字断言与实测不符：")
        for s in fails:
            print("  " + s)
        print("\n  处置：改**写了这个数字的那个文件**（不一定是 SKILL.md——库级状态断言散在正文里），")
        print("        口径见 governance-law.md L4·补。**别改实测值去迁就文字。**")
        return RC_FAIL
    print("[PASS] SKILL.md 的数字断言与实测一致。")
    return RC_OK


# ---------- self-test ----------

def _run(cmd_fn, text, suffix=".md"):
    """把 text 写进临时文件、跑 cmd_fn，返回 (退出码, 输出)。"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(text)
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_fn(path)
        return rc, buf.getvalue()
    finally:
        os.unlink(path)


def cmd_self_test(_unused=None):
    """内建回归：每条断言"这个输入必须得到这个退出码"。

    为什么要有它：这两个脚本是**唯一会自动运行的把关**，但它们自己被改坏时没人知道
    （真出过：块内思考残留漏检、空扫描假 PASS）。改脚本后必跑这一条。
    """
    # ★ 2026-09-17 升级为**模板版 12 块**：基线样本必须代表现行契约
    #   （旧样本是"写实 | 单人 | 固定机位 | 3 秒"的冒号式极简写法，
    #    新检查会判"不是模板版块名"，与新契约冲突 → 一并改写）。
    OK_INNER = ("分镜头脚本，单人单镜，时长5秒，画幅16:9。\n"
                "【全片通用 · 后期特效】\n大气透视：越远越灰；颗粒：暗部颗粒簇。\n"
                "【全片通用 · 统一提质层】\n摄影与印片：35mm 胶片质感；痕迹：暗部颗粒簇与高光滚降。\n"
                "【全片通用 · 风险移除 + 禁止出现】\n禁止出现：第二个人，字幕，水印。\n"
                "【本镜目的】施加戏剧压力：他从坐着变成站起来，这一下就是他被逼到的那一步。\n"
                "【镜头规格】起始景别中景（框到腰部以上）；63°（35mm，中等广角：人物与房间的关系保留，"
                "背景仍可辨认，他前倾时前后景有自然视差），光圈 f2.0。\n"
                "【构图】主体位于画面左侧三分之一，右侧留白。\n"
                "【人物与环境】老陈，52岁男性，短发；他坐着，手平放在桌面；"
                "眉内端先压下去、随后下唇往里咬住；呼吸起伏一次，眨眼一次，重心在两脚之间换过一次。\n"
                "【光位与影调】光源是窗光，从左上进入，影子落在桌面右侧；皮肤哑光，\n"
                "面部平滑、只有很浅的皮沟；鬓角有少量白发、发际线在额角略后退。\n"
                "【时间线】起始：他已经在往前倾了——一只手已经压到桌沿、重心已经偏到右脚，呼吸起伏很浅但不停；"
                "主动作：他抬起头，视线从桌面移到门口；"
                "反应与呼吸：呼吸加深一次；定格：他保持坐姿，呼吸仍在、视线停在门口。\n"
                "【运镜】起始观察点：肩后；主运动：极缓推近约0.3米；"
                "全程锁死：构图关系；结尾落点：停在桌面。\n"
                "【声音】NO BGM（no background music），只留现场音：挂钟秒针、远处车流。\n"
                "【进入下一镜的过渡压力】下一镜切到他抬头的视线落点。\n"
                "【结尾留白】他不动，目光停在门口。")
    OK_BLOCK = "# 镜\n\n```\n" + OK_INNER + "\n```\n"
    # 配对反例①：抽掉【构图】整块 → 缺块即 FAIL
    BLOCK_MISSING = ("# 镜\n\n```\n"
                     + "\n".join(ln for ln in OK_INNER.split("\n")
                                 if not ln.startswith("【构图】"))
                     + "\n```\n")
    # 配对反例②：块齐但元素缺（时间线只剩起始 / 运镜缺锁死项与结尾落点）→ WARN
    BLOCK_THIN = "# 镜\n\n```\n" + OK_INNER.replace(
        "【时间线】起始：他已经在往前倾了——一只手已经压到桌沿、重心已经偏到右脚，呼吸起伏很浅但不停；"
        "主动作：他抬起头，视线从桌面移到门口；"
        "反应与呼吸：呼吸加深一次；定格：他保持坐姿，呼吸仍在、视线停在门口。",
        "【时间线】起始：他坐着。").replace(
        "【运镜】起始观察点：肩后；主运动：极缓推近约0.3米；"
        "全程锁死：构图关系；结尾落点：停在桌面。", "【运镜】起始观察点：肩后。") + "\n```\n"
    META_BLOCK = ("# 镜\n\n```\n另注：这里风格可以调整\n"
                  "声音：无配乐\n结尾留白：他不动\n```\n")
    TIMELINE_OK = ("| 镜号 | 时间 |\n|---|---|\n| SH01 | 0–5 |\n| SH02 | 5–12 |\n| SH03 | 12–18 |\n")
    TIMELINE_GAP = ("| 镜号 | 时间 |\n|---|---|\n| SH01 | 0–5 |\n| SH02 | 7–12 |\n")
    TIMELINE_OVERLAP = ("| 镜号 | 时间 |\n|---|---|\n| SH01 | 0–6 |\n| SH02 | 5–12 |\n")
    TIMELINE_START_LATE = ("| 镜号 | 时间 |\n|---|---|\n| SH01 | 2–5 |\n| SH02 | 5–12 |\n")
    # ★ 段落式排镜表（载体已由「镜几」扩到「段落 / 组合」）——认不出就是静默失效（RC_EMPTY=3）
    TIMELINE_PARA_OK = ("| 段落 | 时间 |\n|---|---|\n| 段落A | 0–5 |\n| 段落B | 5–12 |\n"
                        "| 段落C | 12–18 |\n")
    # 反例：认「段落」不等于放行——有「段落」列但**没有时间区**，仍是"没验到"（3），不许混进 0
    TIMELINE_PARA_NORANGE = ("| 段落 | 景别 | 时长 |\n|---|---|---|\n| 段落A | 中景 | 5 |\n"
                             "| 段落B | 特写 | 3 |\n")

    def _blk(inner):
        return "# 镜\n\n```\n" + inner + "\n```\n"

    OK_INNER = "声音：无配乐，只留现场音\n结尾留白：他不动"
    # 资产块：**没有时间轴**，本就不该有声音行与结尾留白（→ block-playbook-asset.md）
    ASSET_BLOCK = ("# 角色设定板\n\n```\n一张完整的角色设定板，超宽横版排布十个编号分区，"
                   "分区之间用细白线分隔，浅灰白色背景。\n"
                   "分区4 色板：六列两行网格色块，即全片调色基准。\n"
                   "逐处写脏：底座边缘一圈掉漆，露出黄铜色。\n```\n")
    # 镜头块故意缺声音行与结尾留白 —— 用来证明 --asset 没有把镜头侧的检查一并卸掉
    SHOT_NO_AUDIO = ("# 镜\n\n```\n写实 | 单人 | 固定机位 | 3 秒\n"
                     "人物与环境：老陈坐在桌边，手平放在桌面。\n"
                     "光位与影调：窗光从左上进入，光池边缘发脏。\n```\n")
    # 故事板块：**静帧**，同样没有时间轴（→ storyboard-frame.md）
    STORYBOARD_BLOCK = ("# 故事板 2/4\n\n```\n单镜黑白故事板，铅笔速写，纯黑白灰，无任何颜色。\n"
                        "超宽横幅构图，21:9。景别：中近景，人物偏画面右侧三分之一。\n"
                        "明暗结构：硬光从左上来，背景接近全白，人物是深灰剪影。\n```\n")
    # ★ 人物块真实性下限的两条配对用例（2026-09-17 补）：最小镜头提示词，
    #   只保留触发判据所需结构（有【人物与环境】+ 有声音行，避免其他项干扰）。
    MINI_SHOT_INNER = ("分镜头脚本，单人单镜，时长5秒，画幅21:9。\n"
                       "【全片通用 · 后期特效】\n颗粒：暗部颗粒簇。\n"
                       "【全片通用 · 统一提质层】\n摄影与印片：35mm 胶片质感；痕迹：暗部颗粒簇。\n"
                       "【全片通用 · 风险移除 + 禁止出现】\n禁止出现：第二个人，字幕。\n"
                       "【本镜目的】施加戏剧压力：他从坐着变成站起来，这一下就是他被逼到的那一步。\n"
                       "【镜头规格】起始景别中景（框到腰部以上）；63°（35mm，中等广角：人物与房间的关系保留，"
                       "背景仍可辨认，他前倾时前后景有自然视差），光圈 f2.0。\n"
                       "【构图】主体位于画面左侧三分之一，右侧留白。\n"
                       "【人物与环境】他52岁男性，站着，手放在桌沿上；"
                       "眉内端先压下去、随后下唇往里咬住。\n"
                       "【光位与影调】光源是窗光，从左上进入；皮肤哑光，面部平滑、只有很浅的皮沟。\n"
                       "【时间线】起始：他已经在往前倾了——重心已经偏到右脚，呼吸起伏很浅但不停；"
                       "主动作：他抬起头，视线移向门口；"
                       "反应与呼吸：呼吸加深一次；定格：他保持站姿，呼吸仍在、视线停在门口。\n"
                       "【运镜】起始观察点：肩后；主运动：极缓推近约0.3米；"
                       "全程锁死：构图关系；结尾落点：停在桌面。\n"
                       "【声音】NO BGM（no background music），只保留现场音：房间里的空调声。\n"
                       "【进入下一镜的过渡压力】下一镜切到他抬头的视线落点。\n"
                       "【结尾留白】他不动，目光停在门口。")
    MINI_SHOT = "# 镜\n\n```\n" + MINI_SHOT_INNER + "\n```\n"
    MINI_SHOT_BIO = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "他52岁男性，站着，手放在桌沿上；",
        "他52岁男性，站着，呼吸起伏一次、眨了一次眼；重心在两脚之间换过一次；手放在桌沿上；") + "\n```\n"
    # 配对反例③：抽掉面部肌肉级证据（只留生理活性与静息微动）→ 必须报 WARN
    #   —— 这正是 2026-09-17 用户第三次反馈"微表情又没了"的那个缺口
    FACIAL_MISSING = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "眉内端先压下去、随后下唇往里咬住。", "") + "\n```\n"
    # 配对反例④：道具只写"有些旧了"（真实感下限不足、且无材质受光响应）→ WARN
    #   —— 2026-09-17 用户反馈"道具、场景都比较假"的那个缺口（资产模式此前内容一概不查）
    PROP_FAKE = ("# 道具资产\n\n```\n【道具资产设定图】一张完整的道具资产设定图，"
                 "超宽横版排布五个编号分区。\n"
                 "分区1 搪瓷杯：白色搪瓷杯，有些旧了。\n"
                 "分区3 摆位：四件物并排。\n"
                 "统一摄影棚暗调布光，背景深灰褐渐变。\n```\n")
    # 配对反例⑤：出现风格化词却没有显式风格声明 → WARN（默认应走写实）
    STYLE_NODECL = ("# 镜\n\n```\n分镜头脚本，单人单镜，时长5秒，画幅21:9。\n"
                    "粗黑描边、平涂色块、纯色底，人物站在窗前。\n"
                    "【人物与环境】他站着。\n"
                    "【声音】NO BGM（no background music），只留现场音：空调声。\n```\n")
    # 配对反例⑧：把"表情性皱纹"写成常态（"鼻唇沟很深"）→ WARN
    #   （2026-09-17 用户看片后指出："真实人物只有在一些情绪下才会特别明显"）
    WRINKLE_FLAT = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "面部平滑、只有很浅的皮沟。", "鼻唇沟很深，两条刻在嘴边。") + "\n```\n"
    # 配对反例⑨：只丢型号、没写"拍出来什么样" → WARN（2026-09-17 用户追问"提质层真的是电影感的真实吗"）
    GEAR_NO_EFFECT = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "摄影与印片：35mm 胶片质感；痕迹：暗部颗粒簇。",
        "摄影与印片：ARRI Alexa Mini · Cooke S4/i · 柯达 2383 印片。") + "\n```\n"
    # 配对反例⑩：自编风格编号（库里没有 B99）→ WARN（引用优先律 L5）
    STYLE_ID_FAKE = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。",
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。风格：B99。") + "\n```\n"
    # 配对反例⑪：人物被写死（起始"几乎不动"、无眼落点）→ WARN
    #   （2026-09-17 用户看片后指出：开头几秒一直不动、动作后才呼吸、目光也不对）
    PERSON_LOCKED = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "【时间线】起始：他已经在往前倾了——重心已经偏到右脚，呼吸起伏很浅但不停；"
        "主动作：他抬起头，视线移向门口；"
        "反应与呼吸：呼吸加深一次；定格：他保持站姿，呼吸仍在、视线停在门口。",
        "【时间线】起始：他站着几乎不动；主动作：他抬起头；"
        "反应与呼吸：呼吸加深一次；定格：他不动。") + "\n```\n"
    # 回归用例⑫：正文里出现"见【时间线】"这类**交叉引用**时，块提取必须仍取到**行首的块**
    #   （2026-09-17 实测：早期用 find 取第一次出现 → 取到引用处 → 眼落点检查恒报 WARN）
    XREF_OK = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "他52岁男性，站着，手放在桌沿上；",
        "他52岁男性，站着，呼吸起伏一次、眨了一次眼；重心在两脚之间换过一次；手放在桌沿上；").replace(
        "眉内端先压下去、随后下唇往里咬住。",
        "眉内端先压下去、随后下唇往里咬住（收放时点 → 见【时间线】）。") + "\n```\n"
    # 配对反例⑫：起始相写成"待机位"（站得端正 / 等他开始）→ WARN
    #   （2026-09-17 用户："人物在前几秒呆着不动、**似乎在等指令**"）
    #   注：直接复用 MINI_SHOT_BIO（它自带围栏），不要再套一层 fence。
    WAITING_START = MINI_SHOT_BIO.replace(
        "起始：他已经在往前倾了——重心已经偏到右脚，呼吸起伏很浅但不停；",
        "起始：他站得端正，等他开始；")
    # 配对反例⑬：块内出现装饰符号（markdown 强调 / 星号 / 圈号）→ FAIL
    #   （2026-09-17 用户："请你不要随便加这种符号"；实测我自己的稿子塞了 142 处 `**`）
    DECO_IN_BLOCK = MINI_SHOT_BIO.replace(
        "【本镜目的】施加戏剧压力：他从坐着变成站起来，这一下就是他被逼到的那一步。",
        "【本镜目的】**施加戏剧压力**：他从坐着变成站起来。")
    # 配对反例⑭：填表式【本镜目的】（只写"施加戏剧压力"、没有变化与代价）→ WARN
    #   （2026-09-17 用户："模块内容明明有但不思考直接写"；实测我 9 份稿的本镜目的同为一句式、45–54 字）
    PURPOSE_FILLER = MINI_SHOT_BIO.replace(
        "【本镜目的】施加戏剧压力：他从坐着变成站起来，这一下就是他被逼到的那一步。",
        "【本镜目的】施加戏剧压力。")
    # 配对反例⑮：影子方向与光源位置反向矛盾（光在下、影却朝下）→ WARN
    SHADOW_WRONG = MINI_SHOT_BIO.replace(
        "光源是窗光，从左上进入；", "光源是桌面显示器从下方偏左打上来；影子方向向下投射到地面；")
    # 配对反例⑯：二级动作缺因（"椅子被带翻"没写被什么带翻）→ WARN（现实逻辑 轴四）
    NO_CAUSE = MINI_SHOT_BIO.replace(
        "反应与呼吸：呼吸加深一次；", "反应与呼吸：呼吸加深一次；椅子被带翻在地；")
    # 配对反例⑰：光源过多（四种光源＝等于没布光）→ WARN（现实逻辑 轴一）
    MANY_LIGHTS = MINI_SHOT_BIO.replace(
        "光源是窗光，从左上进入；", "光源是顶灯、台灯、显示器与走廊路灯；")
    # 配对反例⑱：镜内位移超限（六步约四点五米 > 约两米的上限）→ WARN（现实逻辑 轴五）
    TOO_MANY_STEPS = MINI_SHOT_BIO.replace(
        "起始：他已经在往前倾了——重心已经偏到右脚，呼吸起伏很浅但不停；",
        "起始：他已经走了六步，重心已经偏到右脚，呼吸起伏很浅但不停；")
    # 配对正例⑲：位移超限但**稿内已声明「参考视频驱动」** → 不算 WARN（本库明文的例外路径）
    #   （2026-09-17 实测 `复杂运镜_6秒单镜.md` B 版：4 步约 3.0 米、首行已写"以参考视频驱动主体步态"，
    #    门禁却报 WARN ＝ 误报。误报比漏报更隐蔽（E23）——用户会因此不信门禁、开始无视 WARN。
    #    本库两条写明的例外：① 参考视频/首尾帧驱动（周期动作与长位移禁止纯文字求解）
    #    ② 机位代走。声明在这两种路径下，位移检查降级为 INFO。）
    STEPS_REFVIDEO = MINI_SHOT_BIO.replace(
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。",
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。以参考视频驱动主体步态，保持镜头结构不变。").replace(
        "起始：他已经在往前倾了——重心已经偏到右脚，呼吸起伏很浅但不停；",
        "起始：他正在走第六步、重心已经偏到右脚，呼吸起伏很浅但不停；")
    #   ★ 第二处替换不是为了位移，是**保住「已在途中」证据**——直接复用 TOO_MANY_STEPS 会顺带
    #   丢掉"已经在往前倾"（换成了"已经走了六步"，`IN_PROGRESS` 要的是"已经在/正在"），
    #   于是样本会因**另一条**检查报 WARN，正例就跑不成。配对用例必须只改一个变量。
    # 配对反例⑳ / 正例㉑：参考图角色分工有没有写"不许它供什么"（2026-09-17 立 · 外部学习）
    #   依据 `asset-prompt-spec.md` §11（八类角色，每种都要写"不许它供什么"）。
    #   ★ 这一对**必须同时存在**：只写反例会把"只在声明点附近找排除句"退化成"全篇搜"，
    #     而全篇必然搜到【风险移除】里的「禁止出现」→ 恒不报（假阴）。正例证明窗口判据没退化。
    REF_NO_DENY = MINI_SHOT_BIO.replace(
        "【人物与环境】", "【人物与环境】\n参考图：图1 只供脸，图2 只供配色。")
    REF_WITH_DENY = MINI_SHOT_BIO.replace(
        "【人物与环境】",
        "【人物与环境】\n参考图：图1 只供脸、不许供姿态与背景；图2 只供配色、不许供主体与构图。")
    # 配对反例㉒ / 正例㉓：焦段有没有译成「空间结果」（2026-09-17 立 · 与「器材要译成效果」同源）
    #   ★ 两个都必须有：反例证明"只写毫米数"会被抓到；正例**故意换一套措辞**（压缩感／拔出来），
    #     证明判据不是只认基线那一句，而是真的在查"有没有焦段专属结果词"。
    #   ⚠️ 反例**不能**靠删掉景深来构造——景深是光圈的事、本就不算焦段结果（`LENS_EFFECT` 已排除它）。
    LENS_NO_EFFECT = MINI_SHOT_BIO.replace(
        "63°（35mm，中等广角：人物与房间的关系保留，背景仍可辨认，他前倾时前后景有自然视差）",
        "35毫米")
    LENS_OK_ALT = MINI_SHOT_BIO.replace(
        "63°（35mm，中等广角：人物与房间的关系保留，背景仍可辨认，他前倾时前后景有自然视差）",
        "63°（35mm，背景有轻微压缩感，人物像从背景里被拔出来）")
    # 配对反例㉔ / 正例㉕：焦段有没有写成「度打头」（2026-09-17 立 · 一手源 `cinema-director-v3` §SLOT 8）
    #   "The model latches onto degrees as a snap value; millimetres read as suggestion."
    NO_DEGREE = MINI_SHOT_BIO.replace("63°（35mm，中等广角", "35毫米（中等广角")
    # 配对反例㉖ / 正例㉗：无配乐有没有写成精确术语 `NO BGM`（同源 §SLOT 15）
    #   裸的 "no music" 会被读成弱偏好，被"生成的视频就该有配乐"的先验覆盖。
    WEAK_NO_BGM = MINI_SHOT_BIO.replace(
        "【声音】NO BGM（no background music），只保留现场音", "【声音】无配乐，只保留现场音")
    # 配对反例㉘ / 正例㉙：方向有没有标注参照系（同源 §SLOT 6 · unlabelled direction inverts about half the time）
    NO_DIR_ANCHOR = MINI_SHOT_BIO.replace("【构图】主体位于画面左侧三分之一", "【构图】主体位于左侧三分之一")
    # 配对反例㉚ / 正例㉛：有台词有没有配声线（2026-09-17 立 · 一手源 `acting-skill` §8）
    #   ★ 判据只认"台词出现"——没台词的镜头不该报（否则每镜恒 WARN，久了没人看 WARN）。
    _SND = "【声音】NO BGM（no background music），只保留现场音：房间里的空调声。"
    VOICE_NO_LINE = MINI_SHOT_BIO.replace(_SND, _SND + "他说：“把门关上。”")
    VOICE_OK_ALT = MINI_SHOT_BIO.replace(
        _SND, _SND + "他说：“把门关上。” —— 他的声线：低、干、语速慢，受压时尾音往上飘。")
    # 配对反例㉜ / 正例㉝：有音乐有没有让它"让路"（2026-09-18 立 · 多源收敛 `mix-loudness.md` §3）
    #   ★ 两个样本都必须**整块替换**——基线那块含「NO BGM / 只保留现场音」，属否定写法，会把样本变成"无音乐"而测不到。
    MUSIC_NO_YIELD = MINI_SHOT_BIO.replace(
        _SND, "【声音】配乐：一段低频弦乐持续铺展，随他起身稍推。现场音：空调声、脚步。")
    MUSIC_OK_YIELD = MINI_SHOT_BIO.replace(
        _SND, "【声音】配乐是一段低频弦乐，比对白低一档、始终不进前景。现场音：空调声、脚步。")
    # 配对反例㉞ / 正例㉟：环境层是否缺失（2026-09-18 立 · `sound-prompt-craft.md` §1/§3）
    NO_AMBIENT = MINI_SHOT_BIO.replace(
        _SND, "【声音】无配乐。事件声：脚步声、关门声、铁椅翻倒在地的一声闷响。")
    HAS_AMBIENT = MINI_SHOT_BIO.replace(
        _SND, "【声音】无配乐。Ambient: 走廊里顶灯的极细电流嗡鸣、远处车流；"
              "事件声：脚步声、关门声、铁椅翻倒的一声闷响。")
    # 配对反例㊱ / 正例㊲：首行画幅与包的画幅是否同值（2026-09-18 立）
    AR_BAD = MINI_SHOT_BIO.replace(
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。",
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。" + "\n"
        + "摄影与印片：ARRI Alexa Mini LF · 变形宽银幕镜头（40 / 50 / 75mm）· 数字底 · 画幅 2.39:1。")
    AR_OK = MINI_SHOT_BIO.replace(
        "分镜头脚本，单人单镜，时长5秒，画幅21:9。",
        "分镜头脚本，单人单镜，时长5秒，画幅2.39:1（21:9 落地）。" + "\n"
        + "摄影与印片：ARRI Alexa Mini LF · 变形宽银幕镜头（40 / 50 / 75mm）· 数字底 · 画幅 2.39:1。")
    # 配对反例㊳/㊴ 与正例㊵/㊶：形态专属检查（2026-09-19 立 · 多形态 12 轮压测后补）
    SEG_NO_COUNT = MINI_SHOT_BIO.replace(
        "【构图】", "段落 A：起始景别全景，段内改为中景（跨 ≥2 级）。\n【构图】")
    SEG_WITH_SEC = MINI_SHOT_BIO.replace(
        "【构图】", "全局约束：恰好 3 个段落、2 个切换点。\n段落 A：第 3 秒切到中景。\n"
                    "段落 B：跨 ≥2 级；段落 C：跨 ≥2 级。\n【构图】")
    MULTI_NO_SINGLE = MINI_SHOT_BIO.replace(
        "【构图】", "A（主动）—— 他先动；B（从动）—— 她也在动。\n【构图】")
    MULTI_OK_ONE = MINI_SHOT_BIO.replace(
        "【构图】", "A（主动）—— 他先动，B 只做一次吞咽。\n"
                    "主动作：只有 A 动——他伸手把杯子推回一寸。\n【构图】")
    # 配对反例㊷：包是固定光圈却写了 f 值（2026-09-19 立 · 用户"检查是否有提示词被写死默认"）
    P01_FIXED_APERTURE = MINI_SHOT_BIO.replace(
        "摄影与印片：35mm 胶片质感；痕迹：暗部颗粒簇。",
        "摄影与印片：现代手机主摄（等效 26mm，固定光圈）· 机内直出，不套胶片模拟 · 画幅 4:3。痕迹：暗部颗粒簇。")
    # 配对反例⑦：镜头规格没声明景别 → WARN（2026-09-17 用户指出"景别是不是又没了"）
    SHOT_NO_SIZE = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "起始景别中景（框到腰部以上）；", "") + "\n```\n"
    # 配对反例⑥：模块归属错——【人物与环境】里写了动作过程与皮肤句 → WARN
    OWNER_BAD = "# 镜\n\n```\n" + MINI_SHOT_INNER.replace(
        "他52岁男性，站着，手放在桌沿上；眉内端先压下去、随后下唇往里咬住。",
        "他52岁男性，从门外走过来两步、扑到桌边；皮肤哑光，毛孔可见；眉内端先压下去。") + "\n```\n"
    # ★ 原先这里有一句 `_io.open("tmpXREF_debug.md","w").write(XREF_OK)`——**纯遗留调试，没有任何用例读它**
    #   （用例直接用 `XREF_OK` 字符串），却**每跑一次 --self-test 就往 CWD 扔一个文件、从不清理**：
    #   实测在技能根目录与 outputs/ 各留过一份。**自检是"随时会跑"的动作，不许有副作用**（2026-09-17 删）。
    # ★ 配对用例㊸㊹：**块提取器本身**（2026-09-19 立 · 一次段落版交付暴露出两处）
    #   ① 段落版的块名是 `【本段共用 · 人物与环境】`/`【时间线 · 段内变化】`，
    #      而调用方传 `【人物与环境】`/`【时间线】` —— 旧实现逐字匹配 → 一律取空 →
    #      **段落版形态下七项逐块检查静默失效**（假阴）。
    #   ② 正文里的交叉引用（"变焦只按【时间线】写明的那一次"）—— 旧实现在"没有行首出现"时
    #      用 `body.find` 兜底 → 取到**引用处那一段** → 眼落点检查对着垃圾报假警（假阳）。
    #   **两处都是"检查器不报错、只是看错了地方"，所以必须直接测提取器，不能只测最终 rc。**
    SEG_BLOCKNAMES = ("【本段共用 · 时间线】她先在桌边站着；随后把手收回。\n"
                      "【本段共用 · 人物与环境】她从门外走过来两步。\n"
                      "【本段共用 · 声音】无配乐。\n")
    XREF_ONLY = ("【风险移除】禁止出现：无来由的变焦（变焦只按【时间线】写明的那一次）。\n"
                 "【本段目的】施加压力。\n")

    def _probe_seg_names(path):
        b = io.open(path, encoding="utf-8").read()
        tl, pe = _sub_block(b, "【时间线】"), _sub_block(b, "【人物与环境】")
        return RC_OK if ("她先在" in tl and "走过来" in pe) else RC_FAIL

    def _probe_xref(path):
        b = io.open(path, encoding="utf-8").read()
        return RC_OK if _sub_block(b, "【时间线】") == "" else RC_FAIL

    cases = [
        # (名称, 函数, 输入, 期望 rc)
        ("blocks·段落版块名（本段共用 · X）能被取到 → 0", _probe_seg_names, SEG_BLOCKNAMES, RC_OK),
        ("blocks·交叉引用（变焦只按【时间线】…）不许当块起点 → 0", _probe_xref, XREF_ONLY, RC_OK),
        ("blocks·合格块（模板版 12 块齐 + 元素齐）→ 0", cmd_blocks, OK_BLOCK, RC_OK),
        ("blocks·抽掉【构图】整块 → 1（缺块即 FAIL）", cmd_blocks, BLOCK_MISSING, RC_FAIL),
        ("blocks·块齐但元素缺（时间线四相不全 / 运镜缺锁死与落点）→ WARN", cmd_blocks, BLOCK_THIN, RC_WARN),
        ("blocks·含人物块但**无面部肌肉级证据**（微表情缺）→ WARN", cmd_blocks, FACIAL_MISSING, RC_WARN),
        ("blocks·道具只写「有些旧了」（真实感下限不足）→ WARN", lambda p: cmd_blocks(p, asset=True), PROP_FAKE, RC_WARN),
        ("blocks·出现风格化词却无风格声明（默认应走写实）→ WARN", cmd_blocks, STYLE_NODECL, RC_WARN),
        ("blocks·【人物与环境】写了动作过程与皮肤句（模块归属错）→ WARN", cmd_blocks, OWNER_BAD, RC_WARN),
        ("blocks·【镜头规格】没声明景别 → WARN", cmd_blocks, SHOT_NO_SIZE, RC_WARN),
        ("blocks·把表情性皱纹写成常态（鼻唇沟很深，无静息态）→ WARN", cmd_blocks, WRINKLE_FLAT, RC_WARN),
        ("blocks·只丢型号、没译成效果 → WARN", cmd_blocks, GEAR_NO_EFFECT, RC_WARN),
        ("blocks·自编风格编号（库里没有 B99）→ WARN", cmd_blocks, STYLE_ID_FAKE, RC_WARN),
        ("blocks·人物被写死（起始几乎不动 / 缺眼落点）→ WARN", cmd_blocks, PERSON_LOCKED, RC_WARN),
        ("blocks·正文含交叉引用「见【时间线】」时块提取仍正确 → 0", cmd_blocks, XREF_OK, RC_OK),
        ("blocks·起始相写成「待机位」（站得端正 / 等他开始）→ WARN", cmd_blocks, WAITING_START, RC_WARN),
        ("blocks·块内出现装饰符号（** 强调）→ 1", cmd_blocks, DECO_IN_BLOCK, RC_FAIL),
        ("blocks·填表式【本镜目的】（无变化与代价）→ WARN", cmd_blocks, PURPOSE_FILLER, RC_WARN),
        ("blocks·影子方向与光源位置矛盾（光在下、影朝下）→ WARN", cmd_blocks, SHADOW_WRONG, RC_WARN),
        ("blocks·二级动作缺因（椅子被带翻但没说被什么带翻）→ WARN", cmd_blocks, NO_CAUSE, RC_WARN),
        ("blocks·光源过多（四种光源）→ WARN", cmd_blocks, MANY_LIGHTS, RC_WARN),
        ("blocks·镜内位移超限（六步约 4.5 米）→ WARN", cmd_blocks, TOO_MANY_STEPS, RC_WARN),
        ("blocks·位移超限但已声明「参考视频驱动」→ 0（既定例外，防误报）", cmd_blocks, STEPS_REFVIDEO, RC_OK),
        ("blocks·参考图给了角色却没说「不许它供什么」→ WARN", cmd_blocks, REF_NO_DENY, RC_WARN),
        ("blocks·参考图角色带明文排除 → 0（证明不是全篇搜「禁止」）", cmd_blocks, REF_WITH_DENY, RC_OK),
        ("blocks·只写毫米数、没译成空间结果 → WARN", cmd_blocks, LENS_NO_EFFECT, RC_WARN),
        ("blocks·焦段配了空间结果（换了措辞）→ 0（证明不是只认基线那一句）", cmd_blocks, LENS_OK_ALT, RC_OK),
        ("blocks·焦段只写毫米、没写视场角（度）→ WARN", cmd_blocks, NO_DEGREE, RC_WARN),
        ("blocks·焦段写成「63°（35mm）」度打头 → 0", cmd_blocks, MINI_SHOT_BIO, RC_OK),
    # 〔已撤回〕"blocks·无配乐没写成精确术语 NO BGM → WARN" —— 见上方〔已撤回〕注释（CINEDANCE V4 已改用 no music）。
        ("blocks·方向没标注参照系（只写「左侧」）→ WARN", cmd_blocks, NO_DIR_ANCHOR, RC_WARN),
        ("blocks·有台词却没写声线 → WARN", cmd_blocks, VOICE_NO_LINE, RC_WARN),
        ("blocks·有台词且配了声线母档 → 0", cmd_blocks, VOICE_OK_ALT, RC_OK),
        ("blocks·有配乐却没写它与对白的关系 → WARN", cmd_blocks, MUSIC_NO_YIELD, RC_WARN),
        ("blocks·写了配乐且明确让它路（比对白低）→ 0", cmd_blocks, MUSIC_OK_YIELD, RC_OK),
        ("blocks·有事件声却无环境层（声场是死的）→ WARN", cmd_blocks, NO_AMBIENT, RC_WARN),
        ("blocks·环境层在前、事件声在后 → 0", cmd_blocks, HAS_AMBIENT, RC_OK),
        ("blocks·首行画幅 21:9 与包内 2.39:1 不同值 → WARN", cmd_blocks, AR_BAD, RC_WARN),
        ("blocks·首行画幅写 2.39:1（21:9 落地）→ 0", cmd_blocks, AR_OK, RC_OK),
        ("blocks·分段镜没写死「恰好 N 段 N-1 切换点」→ WARN", cmd_blocks, SEG_NO_COUNT, RC_WARN),
        ("blocks·分段镜段内写了「第 N 秒」→ WARN", cmd_blocks, SEG_WITH_SEC, RC_WARN),
        ("blocks·多人物没声明「一次一人动」→ WARN", cmd_blocks, MULTI_NO_SINGLE, RC_WARN),
        ("blocks·多人物写明「只有 A 动」→ 0", cmd_blocks, MULTI_OK_ONE, RC_OK),
        ("blocks·包是固定光圈却写了 f 值 → WARN", cmd_blocks, P01_FIXED_APERTURE, RC_WARN),
        ("blocks·块内思考残留 → 1", cmd_blocks, META_BLOCK, RC_FAIL),
        ("blocks·没有围栏（贴错文件）→ 3", cmd_blocks, "# 只是正文，没有代码块\n", RC_EMPTY),
        ("blocks·空文件 → 3", cmd_blocks, "", RC_EMPTY),
        ("blocks·围栏未闭合 → 1", cmd_blocks, "# x\n\n```\n有开头没结尾\n", RC_FAIL),
        ("timeline·连续时间轴 → 0", cmd_timeline, TIMELINE_OK, RC_OK),
        ("timeline·有空档 → 1", cmd_timeline, TIMELINE_GAP, RC_FAIL),
        ("timeline·有重叠 → 1", cmd_timeline, TIMELINE_OVERLAP, RC_FAIL),
        ("timeline·首镜不从 0 起 → 1", cmd_timeline, TIMELINE_START_LATE, RC_FAIL),
        ("timeline·没有镜头行 → 3", cmd_timeline, "# 无表格\n", RC_EMPTY),
        # ★ 载体「段落 / 组合」：认得出（→0）／但没时间区仍得判"没验到"（→3，不许混进 0）
        ("timeline·段落式表（段落A/B/C）→ 0", cmd_timeline, TIMELINE_PARA_OK, RC_OK),
        ("timeline·段落式表但无时间区 → 3（认载体 ≠ 放行）", cmd_timeline,
         TIMELINE_PARA_NORANGE, RC_EMPTY),

        # --- 否定式：真正该报的（否定词 + 祈使/排除型动作）---
        ("否定式·该报[不要出现六根手指] → WARN", cmd_blocks,
         _blk("风险移除：不要出现六根手指\n" + OK_INNER), RC_WARN),
        ("否定式·该报[禁止使用塑料皮肤] → WARN", cmd_blocks,
         _blk("禁止使用塑料皮肤\n" + OK_INNER), RC_WARN),

        # --- 否定式：**正确写法，必须放行**（实测误伤过，这几条是真正的防回退）---
        ("否正例·持续状态[没有停] 放行 → 0", cmd_blocks,
         _blk("倒影里的他不举手，双手仍在敲键盘；没有停\n" + OK_INNER), RC_OK),
        ("否正例·状态描述[没有任何人] 放行 → 0", cmd_blocks,
         _blk("人物与环境：画面里只有他一个人，身后办公室里没有任何人\n" + OK_INNER), RC_OK),
        ("否正例·现象清单[禁止出现：A、B] 放行 → 0", cmd_blocks,
         _blk("禁止出现：换脸、疤痕消失、左右翻转\n" + OK_INNER), RC_OK),
        ("否正例·现象清单[【禁止出现】A、B] 放行 → 0", cmd_blocks,
         _blk("【禁止出现】换脸、疤痕消失、左右翻转\n" + OK_INNER), RC_OK),
        ("否正例·环境层[无配乐/无声] 放行 → 0", cmd_blocks,
         _blk("无配乐，无声源进入画面\n" + OK_INNER), RC_OK),
        ("否正例·词内字[景别与焦距不变] 放行 → 0", cmd_blocks,
         _blk("景别与焦距全程不变\n" + OK_INNER), RC_OK),
        ("否正例·词内字[区别/分别] 放行 → 0", cmd_blocks,
         _blk("前后景要有区别，分别处理明暗\n" + OK_INNER), RC_OK),

        # --- 资产模式（--asset）/ 故事板模式（--storyboard）：静帧类没有时间轴，不查声音行与结尾留白 ---
        ("blocks·含人物块但生理活性与静息微动都缺 → WARN", cmd_blocks, MINI_SHOT, RC_WARN),
        ("blocks·含人物块且生理活性≥2种+静息微动齐 → 0", cmd_blocks, MINI_SHOT_BIO, RC_OK),
        ("blocks·资产块（无声音行 / 无结尾留白）→ 0", lambda p: cmd_blocks(p, asset=True),
         ASSET_BLOCK, RC_OK),
        ("blocks·故事板块（无声音行 / 无结尾留白）→ 0", lambda p: cmd_blocks(p, storyboard=True),
         STORYBOARD_BLOCK, RC_OK),
        ("blocks·镜头块缺声音行与结尾留白 → WARN（--asset / --storyboard 不许卸掉镜头侧检查）",
         lambda p: cmd_blocks(p, asset=False), SHOT_NO_AUDIO, RC_WARN),
        # 漏报守卫：`印片收尾` 是器材术语，不能当成"结尾留白"（旧版用子串匹配 → 这条检查永久失效）
        ("blocks·'印片收尾'不算结尾留白 → WARN", cmd_blocks,
         _blk("柯达 2383 印片收尾，对比扎实\n声音：无配乐，只留现场音"), RC_WARN),
    ]

    ok = bad = 0
    for name, fn, text, expect in cases:
        got, _out = _run(fn, text)
        if got == expect:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s —— 期望 rc=%d，实得 rc=%d" % (name, expect, got))
            # ★ 失败时把被检出的那几行也打出来（2026-09-17 加）——**自检失败必须说清"为什么"**，
            #   否则只能靠人肉复现样本才知道是哪条判据在报（实测：我为此白跑了三轮）。
            _lines = [l for l in (_out or "").split("\n")
                      if l[:2] == "  " or l.startswith(("[WARN]", "[FAIL]", "[INFO]"))]
            for l in _lines[:6]:
                print("         | %s" % l.strip()[:150])

    # 真实库仍查索引结构；长度 WARN 如实保留，不把 WARN 误报成检查器失效。
    here = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(here)
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_index(skill_dir)
    index_rc = rc
    if rc == RC_OK:
        ok += 1
        print("  [OK]   index·本 skill 自身 → 0（无幻影 / 无孤立 / 无超长）")
    elif rc == RC_WARN:
        ok += 1
        print("  [WARN] index·本 skill 自身 → 4（无结构 FAIL，长度 WARN 仍待处理；不是全库 PASS）")
        print(buf.getvalue())
    else:
        bad += 1
        print("  [NG]   index·本 skill 自身 —— 期望 0 或纯 WARN 4，实得 %d\n%s" % (rc, buf.getvalue()))

    # 余量语义用隔离的 291 行参考册验证，避免真实库的超长 WARN 污染断言。
    with tempfile.TemporaryDirectory() as index_fixture:
        ref_dir = os.path.join(index_fixture, "references")
        os.makedirs(ref_dir)
        with io.open(os.path.join(index_fixture, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Index fixture\n\n`references/near.md`\n")
        with io.open(os.path.join(ref_dir, "near.md"), "w", encoding="utf-8") as f:
            f.write("# Near limit\n" + "fixture\n" * 290)
        for headroom, expect, label in (
            (False, RC_OK, "291 行隔离册·默认余量 INFO → 0"),
            (True, RC_WARN, "291 行隔离册·--headroom → 4"),
        ):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_index(index_fixture, headroom=headroom)
            if rc == expect:
                ok += 1
                print("  [OK]   %s" % label)
            else:
                bad += 1
                print("  [NG]   %s —— 期望 %d，实得 %d\n%s" % (label, expect, rc, buf.getvalue()))

        # 同一真实 fixture 加孤立文件：结构 FAIL 必须压过默认 INFO 与 headroom WARN。
        with io.open(os.path.join(ref_dir, "orphan.md"), "w", encoding="utf-8") as f:
            f.write("# Orphan\n")
        for headroom in (False, True):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cmd_index(index_fixture, headroom=headroom)
            if rc == RC_FAIL:
                ok += 1
                print("  [OK]   index·孤立文件（headroom=%s）→ 1（结构门禁仍生效）" % headroom)
            else:
                bad += 1
                print("  [NG]   index·孤立文件（headroom=%s）—— 期望 1，实得 %d\n%s"
                      % (headroom, rc, buf.getvalue()))

    # ---- claims（O1）：**先验"能抓出错数字"，再验"自己不误报"** ----
    # 只验不误报是不够的——一个永远返回 PASS 的检查器同样能通过那条。
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_claims(skill_dir)
    if rc == RC_OK:
        ok += 1
        print("  [OK]   claims·本 skill 自身 → 0（数字断言与实测一致）")
    else:
        bad += 1
        print("  [NG]   claims·本 skill 自身 —— 期望 0，实得 %d\n%s" % (rc, buf.getvalue()))

    # 造一个"全库 999 条"的假 SKILL.md，必须判 FAIL（否则说明检查器根本没在查）
    import shutil
    tmpd = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmpd, "references"))
        with io.open(os.path.join(tmpd, "references", "pitfalls.md"), "w", encoding="utf-8") as f:
            f.write("### PF1 · x\n")
        with io.open(os.path.join(tmpd, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("**全库 999 条分属三个量级系**\n\n`references/pitfalls.md`\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_claims(tmpd)
        if rc == RC_FAIL:
            ok += 1
            print("  [OK]   claims·假的「全库 999 条」→ 1（**证明它真的在查**）")
        else:
            bad += 1
            print("  [NG]   claims·假数字没被抓到 —— 期望 1，实得 %d" % rc)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

    # ── `claims --refs`（2026-10-01 新增）两条用例：一条锁默认不误报，一条证明它真能抓 ──
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc_refs = cmd_claims_refs(skill_dir, strict=False)
    if rc_refs == RC_OK:
        ok += 1
        print("  [OK]   claims --refs·默认 → 0（**只报 INFO、不误报** —— E23：误报比漏报更隐蔽）")
    else:
        bad += 1
        print("  [NG]   claims --refs 默认应恒为 0（普查模式不得进退出码），实得 %d" % rc_refs)

    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc_strict = cmd_claims_refs(skill_dir, strict=True)
    if rc_strict in (RC_OK, RC_FAIL):
        ok += 1
        print("  [OK]   claims --refs-strict → %d（**能进退出码**，证明它不是空壳）" % rc_strict)
    else:
        bad += 1
        print("  [NG]   claims --refs-strict 返回了意外码 %d" % rc_strict)

    print("\n自检：%d 通过 / %d 失败" % (ok, bad))
    if index_rc == RC_WARN:
        print("本库 index：WARN（rc=4）；自检通过不等于全库 PASS。")
    return RC_OK if bad == 0 else RC_FAIL


# ---------- main ----------

USAGE = """用法：
  python3 scripts/audit_prompt.py timeline <file.md>
  python3 scripts/audit_prompt.py blocks   <file.md>
  python3 scripts/audit_prompt.py blocks --asset <file.md>       （资产提示词：静帧类，跳过声音行与结尾留白）
  python3 scripts/audit_prompt.py blocks --storyboard <file.md>  （黑白故事板：静帧类，同上）
  python3 scripts/audit_prompt.py index    <skill_dir>
  python3 scripts/audit_prompt.py index --headroom <skill_dir>   （把 300 行余量从 INFO 升为 WARN）
  python3 scripts/audit_prompt.py claims   <skill_dir>
  python3 scripts/audit_prompt.py --self-test

退出码：0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN

--asset / --storyboard 何时用：查的是**静帧类**提示词（资产图 / 黑白故事板）时。
  静帧没有时间轴，不该有声音行与结尾留白——用镜头规则查会恒定吐无意义 WARN，
  久了就没人看 WARN 了。

--headroom 何时用：**准备往这个库里加内容之前**。默认的余量信息只是 INFO——
  本库有 14 份文件 ≥290 行，若每次都判 WARN，真 WARN 会被噪声淹掉（E23）。
  要拿它卡 CI 或做拆卷排期时，显式加 --headroom。

claims 查什么：SKILL.md 里的**数字断言**与实测是否相符（口径见 governance-law.md L4·补）。
  只对**能可靠复算**的断言下判断；「N 行」这类口径依赖上下文的，只登记不判——
  审计工具最怕的不是漏报，是把解析误差当成真错报出来。
"""


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return cmd_self_test()
    args = argv[1:]
    asset = "--asset" in args
    storyboard = "--storyboard" in args
    headroom = "--headroom" in args
    refs = "--refs" in args or "--refs-strict" in args
    refs_strict = "--refs-strict" in args
    args = [a for a in args if a not in ("--asset", "--storyboard", "--headroom", "--refs", "--refs-strict")]
    if len(args) != 2:
        die(USAGE, RC_USAGE)
    cmd, target = args
    if not os.path.exists(target):
        die("路径不存在：%s" % target, RC_USAGE)
    if cmd == "timeline":
        return cmd_timeline(target)
    if cmd == "blocks":
        return cmd_blocks(target, asset=asset, storyboard=storyboard)
    if cmd == "index":
        if asset or storyboard:
            die("--asset / --storyboard 只对 blocks 有效（index 没有提示词块）", RC_USAGE)
        return cmd_index(target, headroom=headroom)
    if cmd == "claims":
        if asset or storyboard or headroom:
            die("--asset / --storyboard / --headroom 对 claims 无效（它只读 SKILL.md 的数字）；--refs / --refs-strict 才是 claims 的有效扩展", RC_USAGE)
        if refs:
            return cmd_claims_refs(target, strict=refs_strict)
        return cmd_claims(target)
    die("未知子命令：%s\n\n%s" % (cmd, USAGE), RC_USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
