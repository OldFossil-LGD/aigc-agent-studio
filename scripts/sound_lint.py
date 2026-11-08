#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音表门禁（把「spotting sheet」从"人看的字段规范"变成"机器能判的契约"）。

为什么要有它：`sound-post-pipeline.md` §4 定义了声音表的六字段，但**只有人看**——
实操中一定会漂（字段缺、时间码乱、优先级全是 A、"脚步声"三个字了事）。
本脚本把那几条变成机器可判的门禁，与 `script_lint.py` / `shotlist_lint.py` 同族。

检查三组（每组都必须能被机器判定，不许猜）：
  A 字段组：六字段表头齐备 · 每行无空单元格 · 优先级只允许 A/B/C
  B 内容组：类别在允许集合内 · 不许"空话词"（脚步声/音效/有声音…）· 至少一条环境层 ·
            A 级不得超过总行数的 60%（全 A ＝ 没有优先级）
  C 口径组：时间码格式合法 · 起 < 止 · 时间码非递减 · 不超过声明的总时长

用法：
  python3 scripts/sound_lint.py <声音表.md>
  python3 scripts/sound_lint.py --self-test

退出码（与其余门禁一致）：
  0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN
"""
import re
import sys

FIELDS = ("时间码", "类别", "具体声音", "挂在哪", "强度", "优先级")
# ★ "界面" 是合法类别（`sound-design-craft.md` §1 频率分工表里的 UI 层，住 1–12 kHz）——
#   实测：第一份声音表实例里我把它写成了"界面"，工具原表没有 → 会对一个**正确的类别**报 FAIL。
CATEGORIES = ("对白", "环境", "环境声", "硬效", "音效", "拟音", "设计声", "音乐", "静音", "界面")
PRIORITY_OK = ("A", "B", "C")
# ★ 空话词：只有类别名、没有"动作 + 表面/材质"的写法。
#   依据 `sound-post-pipeline.md` §4：「不许写"脚步声"三个字」。
GENERIC = re.compile(r"^(?:有)?(?:脚步|走路|关门|开门|开门声|关门声|脚步声明|音效|声音|环境音|背景音|"
                     r"一些声音|各种声音|氛围|音乐声|打斗声|撞击声)(?:声)?$")
MATERIAL = ("木", "水泥", "混凝土", "金属", "铁", "瓷", "玻", "砖", "石", "沙", "碎", "泥", "雪", "草",
            "布", "皮", "纸", "塑", "胶", "玻璃", "绒", "丝", "干", "湿", "哑", "亮", "闷", "脆")
TC = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[–\-~—]\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*$")


def _secs(h, m, s):
    h = int(h) if h else 0
    return h * 3600 + int(m) * 60 + int(s)


def parse(text):
    """抽出所有表格行（含表头），返回 (header_cells, rows)。"""
    lines = [l for l in text.split("\n") if l.strip().startswith("|")]
    header, rows = None, []
    for l in lines:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if set(cells) >= {"---", ":---:"} or all(set(c) <= set("-: ") for c in cells if c):
            continue                                  # 分隔行
        if header is None:
            header = cells
            continue
        if len(cells) >= 5:
            rows.append(cells)
    return header, rows


def lint(path):
    out, fails, warns = [], [], []
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as e:
        print("读不到文件：%s" % e)
        return 2, ""

    # 声明的总时长（可选）
    total = None
    m = re.search(r"总时长\s*[:：]?\s*(\d{1,4})\s*秒", text)
    if m:
        total = int(m.group(1))

    header, rows = parse(text)
    if not rows:
        print("没扫到声音表（没有可解析的表格行）")
        return 3, ""

    out.append("文件：%s" % path)
    out.append("行数：%d ｜ 声明总时长：%s" % (len(rows), ("%d 秒" % total) if total else "未声明"))
    out.append("-" * 70)

    # ---------- A 组：字段 ----------
    if header is None or not all(any(f in c for c in header) for f in FIELDS):
        fails.append("表头缺字段：需要六列（时间码 / 类别 / 具体声音 / 挂在哪 / 强度·情绪 / 优先级）"
                     "（`sound-post-pipeline.md` §4）")

    prio_count = {"A": 0, "B": 0, "C": 0}
    seen_env = False
    for i, r in enumerate(rows, 1):
        cells = (r + [""] * 8)[:8]
        empty = [j for j, c in enumerate(cells[:6]) if not c]
        if empty:
            fails.append("第 %d 行有空单元格（列 %s）——六字段每一格都要填"
                         % (i, "、".join(str(j + 1) for j in empty)))

        # ---------- C 组：时间码 ----------
        mt = TC.match(cells[0])
        if not mt:
            warns.append("第 %d 行时间码格式可疑：`%s`（要写成 `MM:SS–MM:SS`）" % (i, cells[0][:20]))
        else:
            a = _secs(mt.group(1), mt.group(2), mt.group(3))
            b = _secs(mt.group(4), mt.group(5), mt.group(6))
            if b <= a:
                fails.append("第 %d 行时间码起点不早于终点：`%s`" % (i, cells[0][:24]))
            if total and b > total:
                fails.append("第 %d 行时间码超出声明总时长 %d 秒：`%s`" % (i, total, cells[0][:24]))

        # ---------- B 组：类别 / 空话词 / 优先级 ----------
        cat = cells[1]
        if cat and not any(c in cat for c in CATEGORIES):
            fails.append("第 %d 行类别不在允许集合内：`%s`（对白/环境/硬效/拟音/设计声/音乐）" % (i, cat[:16]))
        if "环境" in cat:
            seen_env = True

        snd = cells[2]
        if snd and GENERIC.match(snd):
            warns.append("第 %d 行『具体声音』太笼统：`%s`——要写**动作＋表面/材质**（例：皮鞋跟落在木地板）"
                         % (i, snd[:20]))
        elif snd and len(snd) <= 4 and not any(k in snd for k in MATERIAL):
            warns.append("第 %d 行『具体声音』信息偏少：`%s`（缺表面/材质，模型只能猜）" % (i, snd[:20]))

        p = cells[5].strip().upper()
        if p and p not in PRIORITY_OK:
            fails.append("第 %d 行优先级非法：`%s`（只允许 A / B / C）" % (i, cells[5][:8]))
        elif p in prio_count:
            prio_count[p] += 1

    # 时间码非递减
    seq = []
    for i, r in enumerate(rows, 1):
        mt = TC.match((r + [""] * 8)[0])
        if mt:
            seq.append((i, _secs(mt.group(1), mt.group(2), mt.group(3))))
    for k in range(1, len(seq)):
        if seq[k][1] < seq[k - 1][1]:
            warns.append("第 %d 行的时间码比上一行更早（表按时间码排更易读）" % seq[k][0])
            break

    if not seen_env:
        warns.append("整张表没有一条『环境』类——**没有环境层，场景在声学上是死的**"
                     "（`sound-post-pipeline.md` §4 / `sound-prompt-craft.md` §1）")

    nA = prio_count["A"]
    # ★ 只在"够长的表"上判 A 级占比——**短表（<8 行）天然粗糙**：
    #   3 行里 2 个 A 就是 67%，那是"表还小"，不是"没有优先级"（实测：本脚本合格样表 3 行就是这么被误报的）。
    #   ★ 教训：**比率型判据必须配样本量下限**，否则小样本会把判据变成噪声。
    if len(rows) >= 8 and nA > len(rows) * 0.6:
        warns.append("A 级 %d 条 / 共 %d 行（>60%%）——**全 A 等于没有优先级**；"
                     "A 级只该留给非做不可的（`sound-post-pipeline.md` §4）" % (nA, len(rows)))

    out.append("统计：A=%d ｜ B=%d ｜ C=%d" % (prio_count["A"], prio_count["B"], prio_count["C"]))

    for f in fails:
        out.append("[FAIL] %s" % f)
    for w in warns:
        out.append("[WARN] %s" % w)
    if not fails and not warns:
        out.append("全过：字段齐备、时间码合法、优先级有效、无空话词、有环境层。")
    print("\n".join(out))

    if fails:
        return 1, "\n".join(out)
    if warns:
        return 4, "\n".join(out)
    return 0, "\n".join(out)


# ------------------------------------------------------------------ 自检
HEAD = ("| 时间码 | 类别 | 具体声音 | 挂在哪 | 强度/情绪 | 优先级 |\n"
        "|---|---|---|---|---|---|\n")
TC1 = "| 00:00–00:02 | 环境 | 走廊里顶灯的极细电流嗡鸣、远处车流 | 整个走廊 | 冷、空 | A |\n"
OK = ("# 声音表 · 示例\n\n总时长：6 秒\n\n" + HEAD + TC1 +
      "| 00:02–00:04 | 拟音 | 皮鞋跟落在水泥地上，两步 | 他，左脚先 | 急、压着 | A |\n"
      "| 00:04–00:06 | 硬效 | 铁椅翻倒在水泥地上的一声闷响 | 铁椅 | 干、重 | B |\n")

_MANY = [("环境", "走廊里顶灯的极细电流嗡鸣、远处车流", "整个走廊", "冷、空", "A"),
         ("拟音", "皮鞋跟落在水泥地上", "他", "急", "A"),
         ("硬效", "铁门关在水泥门框上的闷响", "铁门", "干、重", "A"),
         ("拟音", "棉布外套与椅背摩擦", "他", "轻", "A"),
         ("硬效", "钥匙串落在木桌上", "钥匙", "脆", "A"),
         ("拟音", "手掌按在瓷砖台面上", "他", "黏", "A"),
         ("设计声", "低频心跳垫在底下", "他（主观）", "闷", "A"),
         ("环境", "室外远处车流渗进来", "窗外", "滤过", "B"),
         ("硬效", "纸张翻页", "文件", "干", "B"),
         ("拟音", "袖口擦过桌面", "他", "轻", "C")]
MANY_A = ("# 声音表 · 多 A 例\n\n总时长：20 秒\n\n" + HEAD +
          "".join("| 00:%02d–00:%02d | %s | %s | %s | %s | %s |\n" % (i, i + 1, *r)
                  for i, r in enumerate(_MANY, 1)))

CASES = [
    ("合格表 → 0", OK, 0),
    ("缺表头字段（少了「挂在哪」）→ FAIL",
     ("| 时间码 | 类别 | 具体声音 | 强度 | 优先级 |\n|---|---|---|---|---|\n" + TC1), 1),
    ("优先级写了 D → FAIL",
     OK.replace("| 干、重 | B |", "| 干、重 | D |"), 1),
    ("时间码起晚于止 → FAIL",
     OK.replace("| 00:04–00:06 |", "| 00:06–00:04 |"), 1),
    ("超出声明总时长（6 秒）→ FAIL",
     OK.replace("| 00:04–00:06 |", "| 00:04–00:09 |"), 1),
    ("类别不在集合内 → FAIL",
     OK.replace("| 硬效 |", "| 随便 |"), 1),
    ("『具体声音』只写「脚步声」→ WARN",
     OK.replace("皮鞋跟落在水泥地上，两步", "脚步声"), 4),
    ("整张表没有环境层 → WARN",
     (HEAD + "| 00:02–00:04 | 拟音 | 皮鞋跟落在水泥地上 | 他 | 急 | A |\n"), 4),
    ("A 级占比 >60%（10 行 7 个 A）→ WARN", MANY_A, 4),
    ("空文件 → 3（没扫到东西 ≠ 通过）", "（空）\n", 3),
]


def self_test():
    import tempfile, os, io, contextlib
    ok = bad = 0
    for name, text, want in CASES:
        fd, p = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        open(p, "w", encoding="utf-8").write(text)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):        # ★ 自检时收掉 lint 的输出噪音
            got, _ = lint(p)
        os.unlink(p)
        if got == want:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s —— 期望 rc=%d，实得 rc=%d" % (name, want, got))
            # ★ 失败时把**被检出的那几行**打出来（同 `audit_prompt.py --self-test` 的改进）：
            #   **自检失败必须说清"为什么"**，否则只能靠人肉复现样本。
            for l in buf.getvalue().split("\n"):
                if l.startswith(("[FAIL]", "[WARN]")):
                    print("         | %s" % l[:150])
    print("\n自检：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 1


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return self_test()
    if len(argv) != 2:
        print(__doc__)
        return 2
    rc, _ = lint(argv[1])
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
