#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分镜交付物 → WorkRally 场次投喂包（**投喂桥**）

为什么要有它：本库的分镜交付物（排镜表 + 每镜两板块）与 WorkRally 的 `shotlist`
是**两层**——设计层 vs 平台数据层。中间没有桥时，投喂靠人手抄，三类事故必发：
  ① **抄反顺序**——参考图顺序＝身份，抄反就是引用错人（`workrally-workflow.md` §三）；
  ② **抄漏**——某镜的 animation_prompt 忘了贴，平台照跑，成片少一镜才发现；
  ③ **抄进不该抄的**——把带配乐的声音行一起投出去，违反「分镜阶段 No BGM」。
本脚本把这段**机械搬运**变成一次可复算的转换，并在搬运前把**五类硬检查**跑掉：
  A 板块齐备（每镜两板块）· B 声音守卫（分镜阶段 No BGM）·
  C 静块齐备 +【运镜】块存在 · D 单镜时长下限 · E 决策树留痕（`motion-control.md` 走过没有）。

**两层之间的字段映射（本桥唯一的判断，且它是机械的）**
  `animation_prompt` ← **板块二整段原样**（视频提示词＝动效/运镜，就是它）
  `image_prompt`     ← **板块二里的「静块」**（【镜头规格】+【构图】+【人物与环境】+【光位与影调】）
                        ——**按块名过滤后拼接，块内逐字不动**；【时间线】【运镜】【声音】【过渡压力】
                        是「动」的，不进静帧。
  > 为什么不是「板块一 → image_prompt」：**板块一是黑白故事板**，喂进去会得到灰度关键帧，
  > 与 `storyboard-frame.md` 第十节同源（灰度输入会把整片锁死在单色）。踩过坑才立的规。

**它不做什么（边界，别指望它）**
  · **不写提示词**——所有 prompt **只从交付物原样抽取**；抽不到就报 FAIL/WARN，
    **绝不用模板补**（补出来的就是「填空模板」，本库明令禁止）。
  · **不定视频模式**——`--video-mode` 必须由人按 `motion-control.md` 决策树判定后传入；
    本桥只在末尾提醒「决策树路径 → mode 名」，不替它做决定。
  · **不判画面**——结构门禁过了 ≠ 能交付（`agent-autonomy.md` 纪律四）。
  · **不回写**——方向单向：设计层 → 平台层。平台侧改动不回写库内分镜表。

退出码（与 `audit_prompt.py` / `shotlist_lint.py` 同一套）：
  0 全过（且扫到了东西）｜1 有 FAIL｜2 用法错误｜3 没扫到东西（≠通过）｜4 只有 WARN

用法：
  python3 scripts/workrally_bridge.py <分镜交付物.md> [--mode gen|cut] [--video-mode SubjectToVideo]
          [--series-id SID] [--project-id PID] [--out-json 投喂包.json]
  python3 scripts/workrally_bridge.py --self-test

★ 解析一律复用 `shotlist_lint.py`（同目录），**不另起一套**——否则两套判据会漂移
  （分隔线与块名的容忍度都在那边定义）。本桥只是它的下游消费者。
"""
from __future__ import print_function

import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import shotlist_lint as sl          # noqa: E402  —— 解析口径的唯一权威源
except ImportError:                     # pragma: no cover
    sl = None

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = 0, 1, 2, 3, 4

# 静块名单（进 image_prompt 的只有这四块；块名按「含关键词」匹配，容忍模板微调）
STILL_BLOCKS = ("镜头规格", "构图", "人物与环境", "光位与影调")

# 配乐守卫：先摘掉否定式，再查违规词（否则合规句「无配乐，只留现场音」会被误报）
NEG_PAT = re.compile(r"无\s*配乐|不带配乐|不配乐|禁配乐|无\s*BGM|无\s*背景音乐|不要配乐|不加音乐")
BGM_PAT = re.compile(r"配乐|BGM|bgm|背景音乐|主题曲|音乐床|配乐床")

# 视频模式（取值域来自 `workrally shotlist set-model --video-mode`）
VIDEO_MODES = ("SubjectToVideo", "Text", "FirstLastFrame", "SmartEdit")
# 决策树路径 → 场次线 mode（**判定仍在 `motion-control.md`；本表只做"路 → 参数"的翻译**）
#   注：画布侧"参考视频驱动"是 VideoEdit；场次线没有 VideoEdit，落 SmartEdit。
#   extendVideo 不是独立 mode，是 SubjectToVideo 的子模式（需另带 --extra-mode/--extend-source-id）。
PATH2MODE = {
    "参考主体": "SubjectToVideo",
    "首尾帧单步": "FirstLastFrame",
    "构图规避": "Text",
    "参考视频驱动": "SmartEdit",
}
MODE_TREE = dict((v, k) for k, v in PATH2MODE.items())
# 决策树留痕的两种写法都认（正文一行 `决策树路径：参考主体` / 块名 【决策树】参考主体）
PATH_MARK = re.compile(r"决策树\s*路径\s*[:：]\s*([^\n，,。；；]{2,12})")
PATH_BLOCK = re.compile(r"【[^】\n]{0,8}决策树[^】\n]{0,8}】\s*[:：]?\s*([^\n，,。；；]{2,12})")


def _seg_meta(seg):
    """段内**围栏之外**的正文——决策树留痕只允许写在这里。

    为什么必须排除围栏：本库铁律是**块内一切都会被当提示词执行**，
    「决策树路径」是元数据不是提示词，写进围栏块＝混进 prompt（且它是 `audit_prompt.py` 的块内杂质类）。
    """
    return FENCE_RE.sub(" ", seg)


def _declared_path(seg):
    """取这一镜留下的决策树路径 → (路径, 是否误写进围栏块)。没留痕返回 (None, False)。"""
    meta = _seg_meta(seg)
    m = PATH_MARK.search(meta) or PATH_BLOCK.search(meta)
    if m:
        return m.group(1).strip(), False
    m2 = PATH_MARK.search(seg) or PATH_BLOCK.search(seg)
    if m2:
        return m2.group(1).strip(), True
    return None, False

BLOCK_RE = re.compile(r"【[^】\n]{1,20}】")
FENCE_RE = re.compile(r"```[^\n]*\n([\s\S]*?)```")
SEG_DECOR = re.compile(r"^\s*[─—=\-]{2,}.*[─—=\-]{2,}\s*$")
# 画幅：本库两种写法都出现过（`画幅 16:9` 与 `画幅16比9`），都要认 —— 认不出就报 WARN，不猜
RATIO_RE = re.compile(r"画幅\s*[:：]?\s*([0-9]{1,2}\s*[:：比]\s*[0-9]{1,2}|adaptive|2\.39\s*:\s*1)")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _segment_spans(text):
    """返回 [(段标签, 段正文)]。

    **段标签来自 `shotlist_lint._timeline_segments`**（分隔线与载体的容忍度在那边定义，
    本桥不重复实现）——靠「标签文本回定位到那行装饰线」来切片。
    拿不到标签（或只有兜底的「未标明段号」）时返回空列表 → 调用方报 FAIL。
    """
    if sl is None:
        return []
    labels = [lbl for lbl, _ in sl._timeline_segments(text)]
    if not labels or labels == ["未标明段号"]:
        return []
    lines = text.split("\n")
    marks = []
    for i, ln in enumerate(lines):
        if not SEG_DECOR.match(ln):
            continue
        decorated_label = ln.strip().strip("─—=-").strip()
        for lbl in labels:
            if lbl and lbl != "未标明段号" and lbl == decorated_label and (i, lbl) not in marks:
                marks.append((i, lbl))
                break
    marks.sort()
    out = []
    for k, (i, lbl) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        out.append((lbl, "\n".join(lines[i:end])))
    return out


def _fenced(seg):
    return [m.group(1).strip("\n") for m in FENCE_RE.finditer(seg)]


def _blocks(text):
    """按【块名】切围栏块内的 12 块 → (有序 dict, 块名顺序表)。"""
    out, order = {}, []
    hits = list(BLOCK_RE.finditer(text))
    for k, m in enumerate(hits):
        name = m.group(0).strip("【】")
        end = hits[k + 1].start() if k + 1 < len(hits) else len(text)
        body = text[m.end():end].strip()
        if name in out:
            out[name] += "\n" + body
        else:
            out[name] = body
            order.append(name)
    return out, order


def _still_text(blocks):
    """静块拼接 → image_prompt 原料（块内逐字不动，只做选择与拼接）。"""
    parts, used = [], []
    for name, body in blocks.items():
        for k in STILL_BLOCKS:
            if k in name:
                parts.append("【%s】%s" % (name, body))
                used.append(name)
                break
    return "\n".join(parts), used


def _bgm_hits(text):
    return BGM_PAT.findall(NEG_PAT.sub("", text))


def _match_row(seg_label, rows, c_shot):
    """把段标签对到排镜表某一行，匹配不得截断镜号或段号。"""
    if not c_shot:
        return None
    head = seg_label.split("·")[0].split("・")[0].strip()
    for r in rows:
        lab = (r.get(c_shot) or "").strip()
        if lab and lab in (head, seg_label):
            return r
    label_pattern = (r"(?<![0-9A-Za-z甲乙丙丁一二三四五六七八九十])"
                     r"%s(?![0-9A-Za-z甲乙丙丁一二三四五六七八九十])")
    for r in rows:
        lab = (r.get(c_shot) or "").strip()
        if lab and (re.search(label_pattern % re.escape(lab), seg_label)
                    or (head and re.search(label_pattern % re.escape(head), lab))):
            return r
    return None


def _gate(path, mode):
    """过桥前先跑 `shotlist_lint.py`（**同一把尺子**，不重写门禁）。"""
    sp = os.path.join(HERE, "shotlist_lint.py")
    if not os.path.isfile(sp):
        return None, ""
    r = subprocess.run([sys.executable, sp, path, "--mode", mode],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def bridge(path, mode="gen", video_mode="SubjectToVideo", series_id="<SERIES_ID>",
           project_id="<PROJECT_ID>", out_json=None):
    if sl is None:
        print("[FAIL] 找不到同目录的 shotlist_lint.py —— 本桥的解析口径依赖它，不能独立运行。")
        return RC_USAGE
    text = read(path)

    # ---- 门禁 0：排镜表尺子（「不改动 shotlist_lint」的落地方式）----
    gate_rc, gate_out = _gate(path, mode)
    if gate_rc is None:
        print("[WARN] 没找到 shotlist_lint.py，跳过排镜表门禁（结构断言未验）。")
    elif gate_rc == RC_USAGE:
        print("[FAIL] shotlist_lint.py 用法错，先修它再跑本桥。")
        return RC_USAGE
    elif gate_rc == RC_FAIL:
        print("[FAIL] 排镜表门禁未过 → **不许过桥**（先改排镜表，再投喂）。")
        print(gate_out.rstrip())
        return RC_FAIL
    elif gate_rc == RC_EMPTY:
        print("[FAIL] 排镜表门禁＝3（**没扫到内容，不等于通过**）。")
        print(gate_out.rstrip())
        return RC_EMPTY

    rows, headers = sl.parse_table(text)
    if not rows:
        print("[FAIL] 没找到排镜表 —— 本桥按「一镜一行」搬运，没有表就不许投喂。")
        print("       改法：先补排镜表（列：镜号/段落 | 景别 | 时长 | 叙事职能 | 唯一信息）。")
        return RC_EMPTY
    c_shot = sl._col(headers, sl.COL_SHOT)
    c_dur = sl._col(headers, sl.COL_DUR)
    c_info = sl._col(headers, sl.COL_INFO)

    segs = _segment_spans(text)
    if not segs:
        print("[FAIL] 拿不到镜/段分隔线（形如 ──── 镜2 ──── 或 ──── 段落B · 名字 ────）。")
        print("       改法：每镜/每段单独给一条装饰线 + 该镜两个板块——本桥靠它切镜。")
        return RC_FAIL

    fails, warns, notes = [], [], []
    if video_mode not in VIDEO_MODES:
        fails.append("--video-mode「%s」不在取值域 %s 内" % (video_mode, "/".join(VIDEO_MODES)))

    payload, per_shot, nomark = [], [], []
    for label, seg in segs:
        fenced = _fenced(seg)
        if len(fenced) < 2:
            fails.append("【%s】只有 %d 个围栏块——**每镜必须两个板块**（板块一故事板 / 板块二视频提示词）。"
                         % (label, len(fenced)))
            continue
        b1, b2 = fenced[0], fenced[-1]     # 板块一=故事板（不进 image_prompt）｜板块二=视频提示词
        blocks, order = _blocks(b2)

        # ---- 检查 A：板块二的块骨架 ----
        still, used = _still_text(blocks)
        if not used:
            fails.append("【%s】板块二里找不到静块（%s 之一）——**image_prompt 无料可用**。"
                         % (label, "/".join(STILL_BLOCKS)))
        else:
            missing = [k for k in STILL_BLOCKS if not any(k in u for u in used)]
            if missing:
                warns.append("【%s】静块缺 %s —— image_prompt 会缺这几层（关键帧多半会漂）。"
                             % (label, "/".join(missing)))
        if not any(("运镜" in o or "摄影机" in o) for o in order):
            fails.append("【%s】板块二缺【运镜】块（门禁按「运镜」匹配）——视频提示词没有运动声明。"
                         % label)
        if any("统一提质层" in o for o in order):
            notes.append("【%s】板块二含【统一提质层】——关键帧要不要带器材/痕迹句，由我方决定"
                         "（本桥不自动加：静帧的器材句与运动句必须分开）。" % label)

        # ---- 检查 B：声音守卫（分镜阶段 No BGM ＋ 平台默认开音效）----
        snd = [v for k, v in blocks.items() if "声音" in k]
        if not snd:
            fails.append("【%s】板块二缺【声音】块——本库要求每镜都有声音行（无配乐 ＋ 关键环境音）。"
                         % label)
        else:
            hits = _bgm_hits(snd[0])
            if hits:
                fails.append("【%s】【声音】块出现配乐词 %s —— **分镜阶段 No BGM**（声音后置）。"
                             "改法：删掉配乐描述，保留无配乐声明 ＋ 环境音清单。"
                             % (label, "、".join(sorted(set(hits)))))

        # ---- 抄录：时长 / 信息 / 命名 ----
        row = _match_row(label, rows, c_shot)
        dur = sl._to_float((row or {}).get(c_dur) or "") if row else None
        info = ((row or {}).get(c_info) or "").strip() if row else ""
        if row is None:
            warns.append("【%s】在排镜表里对不到行——时长/命名只能人工核（顺序别抄错）。" % label)
        if dur is not None and dur < 2.0:
            fails.append("【%s】时长 %.1fs < 2.0s（生成单元下限）——**投喂前先拆段**，不是投出去再发现。"
                         % (label, dur))

        # ---- 检查 D：决策树留痕（**判据在 `motion-control.md`，本桥只做「路 → 参数」的翻译**）----
        # 为什么要有这一条：路径是**语义判定**，桥不能替人判；但"判没判"是可以机检的——
        # 不留痕 → 无法证明这一镜走过决策树，等于没走（本库最贵的一类返工来源）。
        dpath, infence = _declared_path(seg)
        mode = video_mode
        if infence:
            fails.append("【%s】决策树路径写进了提示词代码块——**块内一切都会被当提示词执行**。"
                         "改法：挪到分隔线之后、代码块之前（它是一条元数据，不是提示词）。" % label)
        if dpath is None:
            nomark.append(label)
        else:
            key = next((k for k in PATH2MODE if k in dpath or dpath in k), None)
            if key is None:
                fails.append("【%s】决策树路径「%s」认不出（四选一：%s）——**不许凭感觉写**，"
                             "回 `motion-control.md` 重判后再填。" % (label, dpath, " / ".join(PATH2MODE)))
            else:
                mode = PATH2MODE[key]
                notes.append("【%s】决策树路径「%s」→ 平台 mode %s" % (label, key, mode))

        payload.append({"image_prompt": still, "animation_prompt": b2})
        per_shot.append({
            "label": label, "dur": dur, "info": info, "mode": mode, "path": dpath,
            "name": (info or label).replace("\n", " ")[:24],
            "storyboard_prompt": b1,       # 板块一：不进 json-list，单独留档（灰度，不作关键帧）
            "still_blocks": used,
        })

    # ---- 检查 D 的汇总（**汇总成一条，不逐镜报**——逐镜报会刷屏，刷屏的 WARN 没人看）----
    if nomark:
        warns.append("%d 镜未留决策树路径（%s%s）——沿用全局 --video-mode %s。"
                     "**不留痕等于没走**：在交付物里给每镜写一行「决策树路径：<参考主体 / 首尾帧单步 / "
                     "构图规避 / 参考视频驱动>」（判定回 `motion-control.md`）。"
                     % (len(nomark), "、".join(nomark[:4]), "" if len(nomark) <= 4 else " …",
                        video_mode))

    # ---- 检查 C：画幅（解析得到就填；解析不到就不写死，落平台默认）----
    m = RATIO_RE.search(text)
    ratio = re.sub(r"\s*[:：比]\s*", ":", m.group(1)) if m else None
    if ratio is None:
        warns.append("交付物未解析到画幅——set-model **不写** `--*-aspect-ratio`，落平台默认（16:9）。"
                     "这不是猜出来的值，是平台默认值，请核一遍。")

    # ---- 输出 ----
    print("WorkRally 投喂桥｜源：%s｜--mode %s（生成单元）｜识别到 %d 镜/段\n"
          % (os.path.basename(path), mode, len(payload)))
    if gate_rc == RC_OK:
        notes.append("排镜表门禁 0（硬线全过）")
    elif gate_rc == RC_WARN:
        notes.append("排镜表门禁 WARN（结构硬线过了，线条问题交人工定性）")

    print("── ① 场次 json-list（直接喂 `workrally shotlist create --json-list`）──")
    print(json.dumps(payload, ensure_ascii=False))
    print()
    print("── ② 配置（`workrally shotlist set-model`）──")
    # 按 mode 分组：决策树走出来**不止一条路**时，一条 set-model 覆盖不了全片
    # （`--video-mode` 是单次调用的一个值），必须按模式分组、各组带 `--story-ids`。
    groups = []
    for p in per_shot:
        if p["mode"] not in [g[0] for g in groups]:
            groups.append((p["mode"], [x["label"] for x in per_shot if x["mode"] == p["mode"]]))
    for m_, labels in groups:
        flags = ["--series-id %s" % series_id, "--image-model <IMAGE_MODEL_ID>"]
        if ratio:
            flags.append("--image-aspect-ratio %s" % ratio)
        flags += ["--video-mode %s" % m_, "--video-model <VIDEO_MODEL_ID>", "--duration <DURATION>"]
        if ratio:
            flags.append("--video-aspect-ratio %s" % ratio)
        flags.append("--no-enable-sound")
        if len(groups) > 1 or per_shot and per_shot[0]["mode"] != video_mode:
            flags.append("--story-ids <对应：%s>" % ",".join(labels))
        print("workrally shotlist set-model " + " ".join(flags))
    if len(groups) > 1:
        print("  ↑ 本片走了 %d 条决策树路径（%s）→ **必须分组下发**："
              "不同 --video-mode 的模型字段互不通用，一条 set-model 只能给一个 mode。"
              % (len(groups), " / ".join("%s→%s" % (MODE_TREE.get(m_, "?"), m_) for m_, _ in groups)))
    print("  ↑ 模型 id 现场取：`workrally shotlist models --category image,video,audio -o json`（**禁硬编码**）")
    print("  ↑ `--duration` 必须落在该模型 `durations` 里——几秒是模型给的，不是我们定的")
    print("  ↑ 画幅必须落在该模型 `aspect_ratios` 里（`2.39:1` 照写、落地取最接近值）")
    print("  ↑ `--no-enable-sound` 是本库硬守卫（分镜阶段 No BGM；平台默认开音效）")
    print()
    print("── ③ 生成链（**顺序不许倒**：先 recognize 绑参考，再生成）──")
    print("workrally shotlist recognize --series-id %s --project-id %s --match-rule symbol_text"
          % (series_id, project_id))
    print("workrally shotlist generate-image --project-id %s --story-ids <IDS>" % project_id)
    print("workrally shotlist generate-video --project-id %s --story-ids <IDS>" % project_id)
    print("# 音频**不在这一批**——声音后置（`sound-post-pipeline.md`）：")
    print("# workrally shotlist generate-audio --project-id %s --story-ids <IDS>" % project_id)
    print("workrally shotlist get-result --story-id <ID> --type image --watch")
    print("workrally shotlist get-result --story-id <ID> --type video --watch")
    print()
    print("── ④ 单镜抄录（投喂前逐条核：顺序别抄反）──")
    for p in per_shot:
        print("  %-16s 时长 %-6s %-18s --name \"%s\"  静块 %d 个"
              % (p["label"], ("%.1fs" % p["dur"]) if p["dur"] else "?", p["mode"],
                 p["name"], len(p["still_blocks"])))
    print()
    print("── ⑤ 本桥不做、但别跳过的下一步 ──")
    print("  · 过桥前先跑：`python3 scripts/audit_prompt.py blocks <交付物>`（块内杂质 / 声音行 / 时间戳）")
    print("  · **参考图顺序＝身份**：prompt 里「第一张图片」必须对应 `--input-images` 的第一个 URL")
    print("  · 参考图张数 ≤ 该模型 `kontext_config.max_input_images`（现场取，别写死）")
    print("  · 决策树留痕写在**分隔线之后、代码块之前**（`决策树路径：<四选一>`）——")
    print("    写进代码块会被当提示词执行，本桥直接判 FAIL")
    print("[INFO] 决策树路径「%s」→ 平台 mode %s（判定仍在 `motion-control.md`，本桥只提醒）"
          % (MODE_TREE.get(video_mode, "?"), video_mode))
    print()

    if out_json:
        with io.open(out_json, "w", encoding="utf-8") as f:
            f.write(json.dumps({"shotlist": payload, "per_shot": per_shot},
                               ensure_ascii=False, indent=2))
        notes.append("投喂包已落盘：%s" % out_json)

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
        print("[FAIL] 投喂桥未过（**不许投喂**）：")
        for f in fails:
            print("  " + f)
        print("\n提示：全部改在交付物这一层做——改这里是免费的，投出去再改要重抽。")
        return RC_FAIL

    print("[PASS] 投喂包可用（%d 镜；结构硬线 5 项）。" % len(payload))
    return RC_WARN if warns else RC_OK


# ---------------------------------------------------------------- 自检
def _run(path, **kw):
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = bridge(path, **kw)
    finally:
        sys.stdout = old
    return rc


def cmd_self_test():
    import tempfile

    def w(name, body):
        fd, p = tempfile.mkstemp(suffix=".md", prefix="wrb_")
        os.close(fd)
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    HEAD = """# 分镜交付物（自检用）
分镜头脚本，单人单镜，时长 8 秒，画幅 16:9，固定机位。

| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |
|---|---|---|---|---|
| 镜1 | 大远景 | 2.0 | 建立 | 空街两端，两个人影 |
| 镜2 | 近景 | 6.0 | 收束 | 手停在枪套上 |

"""

    def shot(label, sound="无配乐，只留现场音：远处狗叫、风穿过招牌。", still=True,
             cam="【运镜】固定不动；排除同族运镜。", tip=True, path="参考主体", in_fence=False):
        b = ""
        if still:
            b += "【镜头规格】35mm，f/2.0，机位齐腰高。\n"
            b += "【构图】主体落在右三分线上，左侧留负空间。\n"
            b += "【人物与环境】帽檐压低；画面里只有他一个人。\n"
            b += "【光位与影调】光从左上方下来，硬、灼白，光比 1:4。\n"
        if tip:
            b += "【统一提质层】机身与镜头型号逐字粘；痕迹两项。\n"
        b += "【时间线】起始：他不动；主动作：手停住；反应与呼吸：呼吸变浅；定格：冻结。\n"
        b += cam + "\n"
        b += "【声音】" + sound + "\n"
        b += "【过渡压力】视线落点指向下一镜。\n"
        mark = ("决策树路径：%s\n" % path) if path else ""
        if in_fence:                      # 反例：留痕误写进提示词块
            b, mark = mark + b, ""
        return ("──────── %s ────────\n%s```\n[板块一·故事板] 大远景，主体居中，明暗比 1:3；纯灰度。\n```\n"
                "```\n%s\n```\n\n" % (label, mark, b))

    HEAD3 = HEAD.replace(
        "| 镜2 | 近景 | 6.0 | 收束 | 手停在枪套上 |\n",
        "| 镜2 | 近景 | 6.0 | 揭示 | 手停在枪套上 |\n| 镜3 | 大远景 | 2.0 | 收束 | 街对面空了 |\n")

    good = HEAD + shot("镜1") + shot("镜2 · 停在枪套上的手")
    bgm = HEAD + shot("镜1") + shot("镜2", sound="配乐：低音提琴缓慢推进。")
    one_block = HEAD + shot("镜1") + "──────── 镜2 ────────\n```\n只有板块一\n```\n"
    no_still = HEAD + shot("镜1") + shot("镜2", still=False, tip=False)
    no_cam = HEAD + shot("镜1") + shot("镜2", cam="【后景】空街。")
    short = HEAD.replace("| 镜2 | 近景 | 6.0 |", "| 镜2 | 近景 | 1.0 |") + shot("镜1") + shot("镜2")
    no_table = "随便一段文字，没有排镜表。\n" + shot("镜1")
    no_sep = HEAD + "```\n[板块一]\n```\n```\n[板块二]\n【时间线】起始：不动。\n【运镜】固定。\n【声音】无配乐。\n```\n"
    # 检查 D（决策树留痕）三态：没留 → WARN；留了认不出 → FAIL；留痕写进围栏块 → FAIL
    nomark = HEAD + shot("镜1", path=None) + shot("镜2", path=None)
    badpath = HEAD + shot("镜1") + shot("镜2", path="凭感觉")
    infence = HEAD + shot("镜1") + shot("镜2", in_fence=True)
    multi = (HEAD3 + shot("镜1", path="参考主体") + shot("镜2", path="构图规避")
             + shot("镜3 · 街对面空了", path="首尾帧单步"))

    cases = [
        ("bridge·多路径（参考主体/构图规避/首尾帧）→ 按 mode 分组下发且仍为 0", w("mu", multi), RC_OK),
        ("bridge·未留决策树路径 → WARN（4）", w("nm", nomark), RC_WARN),
        ("bridge·决策树路径认不出 → FAIL（不许凭感觉写）", w("bp", badpath), RC_FAIL),
        ("bridge·留痕误写进提示词块 → FAIL（块内会被当提示词执行）", w("if", infence), RC_FAIL),
        ("bridge·正例（两板块齐、静块齐、无配乐）→ 0", w("g", good), RC_OK),
        ("bridge·配乐词 → FAIL（声音守卫）", w("b", bgm), RC_FAIL),
        ("bridge·只有板块一 → FAIL（每镜两板块）", w("ob", one_block), RC_FAIL),
        ("bridge·静块全缺 → FAIL（image_prompt 无料）", w("ns", no_still), RC_FAIL),
        ("bridge·缺【运镜】块 → FAIL", w("nc", no_cam), RC_FAIL),
        ("bridge·单镜 1.0s → FAIL（生成单元下限）", w("sh", short), RC_FAIL),
        ("bridge·没有排镜表 → 3（没扫到 ≠ 通过）", w("nt", no_table), RC_EMPTY),
        ("bridge·没有分隔线 → FAIL（无法切镜）", w("nsep", no_sep), RC_FAIL),
    ]

    ok = fail = 0
    for name, path, want in cases:
        got = _run(path, mode="gen", video_mode="SubjectToVideo")
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

    # 解析口径必须跟着 shotlist_lint 走：它改载体，本桥要能立刻跟上
    probe = "# x\n| 段落 | 景别 | 时长 |\n|---|---|---|\n| 段落A | 中景 | 2.0 |\n"
    p = w("probe", probe)
    rows, headers = sl.parse_table(probe)
    c = sl._col(headers, sl.COL_SHOT)
    if rows and c == "段落" and sl._carrier(c) == "seg":
        ok += 1
        print("  [OK]   bridge·解析口径复用 shotlist_lint（首列「段落」识别为段落版）")
    else:
        fail += 1
        print("  [NG]   bridge·解析口径与 shotlist_lint 不一致（c_shot=%r）" % c)
    os.remove(p)

    # 声音守卫必须能放过合规句（否则每条都 FAIL，等于门禁失效）
    if _bgm_hits("无配乐，只留现场音") == []:
        ok += 1
        print("  [OK]   bridge·声音守卫放过合规句「无配乐，只留现场音」")
    else:
        fail += 1
        print("  [NG]   bridge·声音守卫误报合规句 —— 门禁会失效")

    print("\n自检：%d 通过 / %d 失败" % (ok, fail))
    return RC_OK if fail == 0 else RC_FAIL


def die(msg, rc):
    print(msg)
    sys.exit(rc)


def main(argv):
    if len(argv) == 2 and argv[1] in ("--self-test", "-t"):
        return cmd_self_test()
    args = argv[1:]
    opt = {"mode": "gen", "video_mode": "SubjectToVideo",
           "series_id": "<SERIES_ID>", "project_id": "<PROJECT_ID>", "out_json": None}
    flags = {"--mode": "mode", "--video-mode": "video_mode", "--series-id": "series_id",
             "--project-id": "project_id", "--out-json": "out_json"}
    rest, i = [], 0
    while i < len(args):
        a = args[i]
        if a in flags:
            if i + 1 >= len(args):
                die("%s 缺值" % a, RC_USAGE)
            opt[flags[a]] = args[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    if opt["mode"] not in ("cut", "gen"):
        die("--mode 只能是 cut 或 gen", RC_USAGE)
    if len(rest) != 1:
        die(__doc__, RC_USAGE)
    if not os.path.exists(rest[0]):
        die("路径不存在：%s" % rest[0], RC_USAGE)
    return bridge(rest[0], **opt)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
