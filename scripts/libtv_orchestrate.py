#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""站 6.5 / 6.6 / 6.7 编排器 —— 把散文变成**可复算的调用序列**（2026-10-01 新建）

★ 先说清它是什么、不是什么（这一段是全篇最重要的一段，别删）

  **它不是执行器。** 本库 10 个脚本里 `urllib` / `requests` / `mcp__` 出现 0 行，
  不是因为作者偷懒，而是**一条明文红线**（2026-10-01 重测后更正）：
    ① LibTV 是**远端 HTTP MCP**（`https://mcp.liblib.tv/mcp`）；
    ② 宿主目录下**存在可解密的凭据路径**：`.master.key`（32 B AES 密钥）+ `.credentials.v3.json`（`aes-256-gcm`+`hkdf-sha256`）。
       **以前说「物理上拿不到」是错的**——`libtv-op-manual-2.md` §十九已明文写死：
       **【红线（禁止写死）】令牌**理论上可解**，但**绝对不许解**。三条理由：
         ① 宿主加密的本意就是**不让别的进程拿走令牌**；
         ② 令牌 scope 含 `media:write`/`task:write`/`export:write`（我方实测确认），**解出来＝在阶段闸外造出一个具备生成能力的凭据**；
         ③ 无人值守、无批准 UI 时，**自我授权提取凭据属越界**。正解：**让用户点一次「重连」**。
  → **执行者只能是 agent**，且这不是技术墙，而是**一条不能自己越过的红线**。**

  **那它凭什么算自动化？** 因为它消灭的是**即兴发挥**：
    调用顺序 · 幂等键 · 依赖拓扑 · 批次切分 · 预算闸 · 断点续跑状态 · 接口契约校验
    ——全部由脚本机械产出，agent 从「逐条手搓」降级为「照预校验过的清单执行」。
  **判据一句话**：它不让人变自由，它让**同一份输入永远产出同一份调用序列**。

★ 它的四条硬纪律（都是本库宪法，不是本脚本发明的）

  1. **L7 批准必须显式**：任何 `run: true`（花钱）前必须 `--approve`。
     门禁全绿 / 生成成功 / agent 自己的判断 **都不算批准**——脚本因此拒绝
     「自动放行」，宁可 `--approve` 缺席时停在 preflight。
  2. **L5 引用优先律**：**本脚本一个字都不写提示词**。所有 prompt 由 job spec
     原样带进来（`prompt` 字段），脚本只**校验长度、校验插桩顺序、校验引用上限**。
     抽不到就是抽不到 → 报 FAIL，**绝不用模板补**（同 `workrally_bridge.py` 的边界）。
  3. **L4 数字与来源**：**本脚本不编积分单价**。单价必须由 `--prices` 带进来；
     没带就把预算标成 `未解` 并**锁死付费闸**——而不是替用户猜一个数。
  4. **L6 四态**：接口校验结论一律带证据标签（`实测`/`推断`），不把推断写成实测。

★ 它对活了什么（`outputs/接口对质表_LibTV_20261001.md` · 2026-10-01 实测）

  · **K13 硬拦 `run_node`**：库内 `run-sheet.md:152` 站 6.5 与 `libtv-concurrency.md`
    都写「批量＝并行发起多个 `run_node`」——**该工具不在 48 个 MCP 工具内**
    （`doctor.toolRegistry` 逐个清点）。照它写代码必然 404。本脚本见到即报错并
    给出真实的三条替代路径。
  · **K9 校验 `{{node_key}}` 插桩顺序**：`libtv-canvas-nodes.md` §九 把这条列为
    「本库尚缺的 5 处」之一。**2026-10-01 实测坐实**：活节点 `v-P8RHob2UXQ` 的
    prompt 插桩序 `{{i-dXjd6k9XSr}}→{{i-dzqbvIGhFp}}→{{i-SZxTlvo5LR}}→{{i-EJhGhKktFN}}`
    与 `imageListOrder` **四项同序**。→ 顺序不一致即 FAIL（这就是
    `workrally_bridge.py` 开头「抄反顺序＝引用错人」在画布层的对应形态）。
  · **K8 引用上限**：`get_model("Wan 3.0")` 实测 `mixed2videoConfig`
    `imageMax:10 / videoMax:5 / audioMax:5` → 建边前先卡，超了直接 FAIL。
  · **K15 两套参数名**：`settings.quality` 只收 `low/medium/high/xhigh/max`，
    `2K/4K` 属 `resolution`（活节点 `i-BqGvckkewo` 实测两个字段并列）。
  · **K1 派生字段禁设**：`imageList` / `imageListOrder` / `mixedListOrder` 等
    **由 `left` 边自动重算**（活数据实测），直接塞 `params` 会 `NODE_VALIDATION_FAILED`。

用法：
  python3 scripts/libtv_orchestrate.py pipeline  --spec job.json --contract model.json [--shotlist 分镜.md]
                                            [--storyboard 故事板.md] [--sound 声音表.md]
                                            [--prices p.json] [--budget-ceiling N] [--approve] --out pipeline.json
  python3 scripts/libtv_orchestrate.py compile   --spec job.json --contract model.json \
                                                --project-id <UUID> --out plan.json
  python3 scripts/libtv_orchestrate.py preflight [--plugin libtv@libtv] [--config PATH] [--json]
                                            # **开工第一条**：只读体检插件注册/缓存/凭据/网络四层
  python3 scripts/libtv_orchestrate.py ingest    --plan plan.json --results results.json
  python3 scripts/libtv_orchestrate.py verify    --plan plan.json --spec evidence_spec.json [--out evidence.json]
  python3 scripts/libtv_orchestrate.py --self-test
                                            # 只读沙箱（Codex sandbox）建不出临时目录时，
                                            # 4 组需落盘的用例记 SKIP 并单列，不算失败；
                                            # 设 ORCH_TMPDIR 指向可写目录即可跑满全部用例。

退出码（与 `audit_prompt.py` / `shotlist_lint.py` 同一套，不另立）：
  0 全过 ｜ 1 有 FAIL ｜ 2 用法错 ｜ 3 没东西可校验（≠通过）｜ 4 只有 WARN
"""
from __future__ import print_function

import io
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _common as C          # noqa: E402  —— 退出码与读文件的唯一权威源，不另立一套

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY, RC_WARN = C.RC_OK, C.RC_FAIL, C.RC_USAGE, C.RC_EMPTY, C.RC_WARN

# ─────────────────────────────────────────────────────────────────────────────
# 契约常量 —— 全部来自 2026-10-01 实测，不是拍脑袋
# ─────────────────────────────────────────────────────────────────────────────

# 活 schema：create_node.nodeType 枚举（doctor + get_capabilities 交叉确认）
NODE_TYPES = ("text", "image", "video", "audio", "script", "video-clip")

# 平台自报的工具名：create_node / update_node 都带它。data.type 与 data.action 是
# 节点身份字段，创建后不可改 —— 改了就等于换了个节点。
ACTIONS = {
    "text": "text_generate",
    "image": "image_generate",
    "video": "video_generate",
    "audio": "audio_generate",
    "script": "script_generate",
    "video-clip": "video_clip_resource",
}

# 库内不存在、但被 run-sheet.md:152 / libtv-concurrency.md 写进去的工具（2026-10-01 实测 404）
BANNED_TOOLS = {
    "run_node": "不在 48 个 MCP 工具内（doctor.toolRegistry 实测）。真实三条替代："
                "① create_node(run:false) 只建不跑、同步返回 node_key；"
                "② create_node/update_node/generate_video 的 run:true 才生成；"
                "③ manage_group(action:\"run\") 才是唯一「有序子任务工作流」入口。",
}

# 这些字段由 left/right 引用边自动重算，**不可直接写进 params**（实测：直接设报
# NODE_VALIDATION_FAILED；建边后系统自动生成 imageList / imageListOrder / mixedListOrder）
DERIVED_FIELDS = ("imageList", "videoList", "audioList", "textList",
                  "imageListOrder", "videoListOrder", "audioListOrder",
                  "mixedListOrder")

# 画布层 quality 档位（实测 i-BqGvckkewo：quality 与 resolution 是两个并列字段）
QUALITY_TIERS = ("low", "medium", "high", "xhigh", "max")

# 止损阶梯（`production-ledger.md` 第四节 + `run-sheet.md` 站 6.5 批量条）
MAX_PER_NODE = 3     # 同一产物（同一 v 节点）最多 3 次 → 失败即隔离、废弃原节点、新建 v2
STOPLOSS_TOTAL = 8   # 止损上限：同一镜累计 8 次封顶（低于难度系数表最高档 9–15）
PATH_CHANGE_AT = 6   # 第 6 次起必须换实现路径，不是换词

BATCH_SIZE = 4       # 锚点先行 → 分批并行 4 个/批（站 6.5）
CONCURRENCY_CAP = 5  # 并行上限 5，留 1 个余量应对补跑

REF_TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)\s*\}\}")


def read_json(path):
    """读 JSON。**不存在不是错**（有些输入可选），故返回 None 而不是抛。"""
    if not path or not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False))
        f.write(u"\n")


def _tmpdir(prefix="orch_"):
    """建一个可写临时目录；整机只读（Codex 沙箱）时返回 None。

    候选顺序：`ORCH_TMPDIR` 显式指定 → 系统 TEMP/TMP → 调用方 cwd。
    自检里必须落盘的用例拿不到目录时**整组记 SKIP 并单列计数**——只读沙箱
    不是判据错，但也不能假装那些用例跑过。
    """
    cands, seen = [], set()
    for cand in (os.environ.get("ORCH_TMPDIR"), None,
                 os.environ.get("TEMP"), os.environ.get("TMP"),
                 os.environ.get("TMPDIR"), os.environ.get("CODEX_TMPDIR"),
                 os.path.join(os.getcwd(), ".orchestrator_tmp")):
        key = u"<system temp>" if cand is None else os.path.normcase(os.path.abspath(cand))
        if key in seen:
            continue
        seen.add(key)
        cands.append((cand, key))
    tried = []
    for cand, key in cands:
        try:
            if cand is None:
                return tempfile.mkdtemp(prefix=prefix)
            os.makedirs(cand, exist_ok=True)
            return tempfile.mkdtemp(prefix=prefix, dir=cand)
        except OSError as e:
            tried.append(u"%s: %s" % (key, e))
    sys.stderr.write(u"[skip] 无可用临时目录（只读沙箱？设 ORCH_TMPDIR 指向可写目录）：%s\n"
                     % u" | ".join(tried))
    return None


def idem(stage, *parts):
    """**确定性**幂等键 —— 断点续跑的根基。

    库内铁律：「同一 key 重试不会重复花钱」+「重试必须同键同文」（否则
    `IDEMPOTENCY_CONFLICT`）。→ 键必须**只由内容决定**，不能含时间戳／随机数，
    否则重跑一次就换一把键，幂等保护当场失效。
    """
    import hashlib
    raw = u"|".join([stage] + [u"%s" % (p,) for p in parts])
    return "orc-%s-%s" % (stage, hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12])

# ─────────────────────────────────────────────────────────────────────────────
# 接口契约校验 —— 每一码都对应一条实测证据，见 docstring 的「它对活了什么」
# ─────────────────────────────────────────────────────────────────────────────

def _enum_vals(node):
    """把 schema 里 [{value,displayName}, "16:9", ...] 这种混排 enum 归一成纯值表。"""
    out = []
    for e in (node or {}).get("enum", []) or []:
        if isinstance(e, dict):
            v = e.get("value")
            if v is not None:
                out.append(v)
        else:
            out.append(e)
    return out



# ── 积分**量级区间**（不是单价！）───────────────────────
# 来源：`libtv-billing.md` §四（R24 平台方答疑）。
# ★ 记证强度（L6）：该册自身明写「具体积分单价以账户内实际计费页为准」→ **本表数值一律记「拟订」，只当量级参考，**不得当成已定价报出去**。
# → 故 G3 的流程是：算**区间** [低, 高] → **用上界比 ceiling**（保守）→ 超了就拦。
VIDEO_BANDS = {          # (resolution, duration) -> (低, 高)   拟订
    ("480P", 4): (8, 15), ("480P", 8): (16, 28),
    ("720P", 4): (12, 25), ("720P", 8): (24, 45), ("720P", 10): (30, 55),
    ("1080P", 4): (20, 40), ("1080P", 8): (40, 75), ("1080P", 10): (50, 90),
    ("4K", 5): (60, 120), ("4K", 10): (120, 220),
}
IMAGE_BANDS = {"1K": (1, 2), "2K": (2, 4), "4K": (6, 10)}   # 每张



# 模型**相对乘数**（`libtv-official-qa-6.md` §18.2）——以 `wanx3.0` 标准版 ≈1.0x 为基准。
# ★ 原文自身声明「非平台官方固定价，随分辨率/时长/活动期浮动」→ 记 **拟订**，不当已定。
# → **不否这一项会让预算系统性低估**：同样 8s/1080p，用 prime 比用标准版忙 2–3 倍。
MODEL_COST_MULT = {
    "wanx3.0": (1.0, 1.0),          # 基准
    "seedance-1.5-pro": (1.3, 1.8),
    "wanx3.0-prime": (2.0, 3.0),
}

def _norm_res(res):
    """分辨率归一：模型 schema 给的是小写（480p/720p/1080p），量级表的键是大写（720P）。
    ★ 2026-10-12 实测：不归一时真实 spec 永远匹配不上 → 视频段的「量级区间」恒为 None →
    无单价时的兜底估算对最贵的段落直接失效（P0 包 stage3 实撞）。"""
    return str(res).strip().upper() if res else res


def _band_lookup(res, dur, bands):
    """先精确匹配，再按时长**线性估**（§三：同模型同分辨率下基本近似线性）。"""
    if not res or not dur:
        return None
    res = _norm_res(res)
    k = (res, dur)
    if k in bands:
        return bands[k]
    cands = [v for (r, d), v in bands.items() if r == res and d]
    if not cands:
        return None
    per = [(v[0] / float(d), v[1] / float(d)) for (r, d), v in bands.items() if r == res]
    if not per:
        return None
    lo = min(per)[0] * dur
    hi = max(per)[1] * dur
    return (int(round(lo)), int(round(hi)))


def budget_band(node):
    """给单个节点算积分区间。**拟认**；无法定位则返回 None（不猜）。"""
    nt = node.get("nodeType")
    st = (node.get("params") or {}).get("settings") or {}
    try:
        cnt = int((node.get("params") or {}).get("count", 1) or 1)
    except (TypeError, ValueError):
        cnt = 1
    if nt == "video":
        b = _band_lookup(st.get("resolution"), st.get("duration"), VIDEO_BANDS)
        if not b:
            return None
        lo, hi = MODEL_COST_MULT.get((node.get("params") or {}).get("model"), (1.0, 1.0))
        return (int(round(b[0] * cnt * lo)), int(round(b[1] * cnt * hi)))
    if nt == "image":
        b = IMAGE_BANDS.get(_norm_res(st.get("resolution")))
        return (b[0] * cnt, b[1] * cnt) if b else None
    return (0, 0)     # audio / text / video-clip：计费口径不在本表内 -> 0


def _contract_props(contract):
    """从 get_model 返回里挖出 schema.properties；容错（手抄的精简 contract 也认）。"""
    if not contract:
        return {}
    if "schema" in contract and isinstance(contract["schema"], dict):
        sch = contract["schema"]
        return (sch.get("properties") or {}) if isinstance(sch, dict) else {}
    return contract.get("properties") or {}


def pick_contract(contract, node):
    """**按模型**取契约 —— 一个 spec 里的节点分属不同模型，约束互不相同。

    ★ 为什么必须分模型（2026-10-01 端到端跑出来的真问题）：把 Wan 3.0 的契约
      套到全部节点上，图节点（`lib-image-2.5-s`）的 `resolution` 是 `2K`，
      而 Wan 3.0 的活枚举是 `480P/720P/1080P` → **满屏假 FAIL**。
      站 6.5 第 2 步原文就是「挑**模型**并读约束」（复数），一张契约管全部是错的。

    contract 形状（二选一）：
      A) 单模型：`{"modelName": "...", "schema": {...}}`
      B) 多模型：`{"models": {"<modelKey>": {…A的形状…}}, "default": {…A的形状…}}`
    """
    if not contract or "models" not in contract:
        return contract
    model = ((node.get("params") or {}).get("model")) or ""
    models = contract.get("models") or {}
    return models.get(model) or contract.get("default") or {}


# ── K24 错误可重试性分类 + 退避表 ───────────────────────
# 来源：`libtv-official-qa-4.md` §13.4「可重试＝429/5xx/超时/网络；**不可重试＝参数校验/审核拒绝/积分不足/幂等冲突**」
# → **参数错误重试是纯亲亏**（会把同一个错反复发出，又多花一次链接）。
RETRYABLE = ("429", "RATE_LIMITED", "5xx", "INTERNAL_ERROR", "TIMEOUT", "timeout",
             "网络", "超时", "CONCURRENCY_CONFLICT")
# 审核三阶段（`libtv-ignite-director-billing.md` §二 · R33）——**每阶段计费影响不同**，不能归为一类。
# ★ 一句话：**提交前拒绝＝没有任务 · 生成中拦截＝有任务但被终止 · 产物审核＝跑过了但结果不可用**
STAGE_PRE = ("INVALID_ARGUMENT", "PARAM_OUT_OF_RANGE", "NODE_VALIDATION_FAILED",
              "MODEL_NOT_FOUND", "MODEL_NOT_SUPPORTED", "DURATION_OUT_OF_RANGE",
              "UNRESOLVED_PLACEHOLDER", "PERMISSION_DENIED", "QUOTA_INSUFFICIENT")
STAGE_GEN = ("CONTENT_POLICY_VIOLATION", "MODERATION_BLOCKED")
STAGE_OUT = ("OUTPUT_REJECTED", "POST_GENERATION_REVIEW_FAILED")
STAGE_TECH = ("INFRA", "TIMEOUT", "RESOURCE", "INTERNAL_ERROR", "429", "RATE_LIMITED", "5xx")
NOT_RETRYABLE = ("NODE_VALIDATION_FAILED", "IDEMPOTENCY_CONFLICT", "REVISION_CONFLICT",
                 "CONTENT_POLICY_VIOLATION", "QUOTA_INSUFFICIENT", "MODEL_NOT_FOUND",
                 "MODEL_NOT_SUPPORTED", "DURATION_OUT_OF_RANGE", "PERMISSION_DENIED",
                 "UNRESOLVED_PLACEHOLDER", "REFERENCE_NOT_READY")
# 退避（平台给）：指数退避 + 抖动
BACKOFF = (2, 4, 8, 16, 30)
MAX_RETRY = 5


def classify_error(msg):
    """把一条报错原文归类。返回 (kind, 一句说明)，kind 在 retryable / not_retryable / unknown。
    **unknown 不猜**（L6）—— 未知错误不得默认可重试。"""
    m = msg or ""
    # ① 提交前：任务**根本没创建**，**未扣费**（R33 §二）
    for k in STAGE_PRE:
        if k in m:
            return "not_retryable", u"① 提交前拒（**任务未创建、未扣费**）——改参数重发"
    # ② 生成中审核拦截：已提交、任务终止，**已扣费**
    for k in STAGE_GEN:
        if k in m:
            return "not_retryable", u"② 生成中审核拦截（**已提交、任务终止、已扣费**）——必须改内容"
    # ③ 产物审核：跑过了但成品不可用
    for k in STAGE_OUT:
        if k in m:
            return "not_retryable", u"③ 产物审核未过（**已跑完但结果不可用**）——改提示词与前层审核"
    for k in NOT_RETRYABLE:
        if k in m:
            return "not_retryable", u"权限/幂等类错误 —— **重试纯亏**，必须先改参数"
    for k in STAGE_TECH:
        if k in m:
            return "retryable", u"技术域（限流/基础设施/超时）——可指数退避后重试"
    return "unknown", u"未识别的错误 —— **不猜**，先读原文再决定"


def backoff_plan(attempt):
    """退避表：2s → 4s → 8s → 16s → 30s，最多 4–5 次（平台给）。"""
    if attempt >= MAX_RETRY:
        return None
    return BACKOFF[attempt] if attempt < len(BACKOFF) else BACKOFF[-1]


def check_node(node, contract, project_id, has_paid_approved, ntypes=None):
    """校验**单个**节点声明。返回 findings 列表。

    每条 finding = {code, level, node, msg}；level ∈ {FAIL, WARN, INFO}。
    """
    f = []
    nid = node.get("id") or node.get("name") or "?"

    def fail(code, msg):
        f.append({"code": code, "level": "FAIL", "node": nid, "msg": msg})

    def warn(code, msg):
        f.append({"code": code, "level": "WARN", "node": nid, "msg": msg})

    # ---- K0 节点类型 ----
    nt = node.get("nodeType")
    if nt not in NODE_TYPES:
        fail("K0", "nodeType=%r 不在活枚举 %s 内" % (nt, "/".join(NODE_TYPES)))

    # ---- K13 被禁工具（库内漂移：run_node 不存在）----
    for bad in list(node.keys()):
        if bad in BANNED_TOOLS:
            fail("K13", "字段 `%s` 命中被禁工具：%s" % (bad, BANNED_TOOLS[bad]))

    # ---- K16 提示词不得为空（L5：不许模板补，所以空就是缺料）----
    prompt = node.get("prompt")
    if not prompt or not str(prompt).strip():
        fail("K16", "prompt 为空 —— 本脚本**不写提示词**（L5），缺料就是缺料，不许模板补")

    # ---- K1 派生字段禁设 ----
    params = node.get("params") or {}
    hit = [k for k in params if k in DERIVED_FIELDS]
    if hit:
        fail("K1", "params 里出现派生字段 %s —— 它们由 left/right 边**自动重算**，"
                   "直接设会 NODE_VALIDATION_FAILED；请改用 refs 声明引用" % hit)

    # ---- K2 audio 必须显式给 scene（libtv-canvas-nodes.md §一 + 活节点实测）----
    if nt == "audio" and not (params.get("scene") or "").strip():
        fail("K2", "audio 节点 params 缺 `scene` —— schema 要求显式场景（实测活节点均带）")

    props = _contract_props(pick_contract(contract, node))

    # ---- K3 提示词长度（实测 Wan 3.0 = 3000；超长**从末尾截断，先丢计数约束**）----
    mx = ((props.get("prompt") or {}).get("maxLength"))
    if mx and isinstance(prompt, str) and len(prompt) > mx:
        fail("K3", "prompt %d 字 > maxLength %d —— **末尾会被静默截断，先丢的正是"
                   "计数约束与不变项**（`agent-autonomy.md` 纪律一·3）" % (len(prompt), mx))

    settings = params.get("settings") or {}

    # ---- K4 ratio（只对有画幅的节点判：audio 没有 ratio 字段）----
    rv = _enum_vals(props.get("ratio")) if nt in ("video", "image") else []
    if rv and "ratio" in settings and settings["ratio"] not in rv:
        fail("K4", "ratio=%r 不在活枚举 %s 内" % (settings["ratio"], rv))
    if rv and "ratio" not in settings:
        warn("K4", "未显式给 ratio —— 活 schema 默认 %r（自适应），成片画幅不可控"
                   % next((d.get("value") for d in (props.get("ratio") or {}).get("enum", [])
                            if isinstance(d, dict) and d.get("value") == "adaptive"), "adaptive"))

    # ---- K5 duration ----
    dp = props.get("duration") or {}
    dur = settings.get("duration", node.get("duration"))
    # ★ 2026-10-01 补：时长在活 schema 里有两种表达 —— **区间**（min/max，如 Wan 3.0 的 2-30）与 **枚举**
    #   （如 Wan 2.6 的 [5,10]）。原实现只看 min/max，遇到枚举式模型会**静默放行任何值**。
    #   来源：读 `libtv-concurrency.md` §八「各模型成片时长范围」时发现。
    _denum = _enum_vals(dp)
    if _denum and dur is not None:
        if dur not in _denum:
            fail("K5", "duration=%r 不在活 schema 的枚举 %s 内（模型要求**整档**，不是区间）"
                 % (dur, _denum))
    elif dp and dur is not None:
        try:
            d = int(dur)
            if d < dp.get("min", d) or d > dp.get("max", d):
                fail("K5", "duration=%s 越界（活 schema %s–%s）" % (d, dp.get("min"), dp.get("max")))
            step = dp.get("step", 1)
            if step and (d - dp.get("min", 0)) % step != 0:
                fail("K5", "duration=%s 不合步长 %s" % (d, step))
        except (TypeError, ValueError):
            fail("K5", "duration=%r 不是整数" % (dur,))

    # ---- K6 resolution ----
    res = _enum_vals(props.get("resolution"))
    if res and "resolution" in settings and settings["resolution"] not in res:
        fail("K6", "resolution=%r 不在活枚举 %s 内" % (settings["resolution"], res))

    # ---- K7 哑片必须显式关声（实测 enableSound 默认 on）----
    if nt == "video" and settings.get("enableSound") is None:
        warn("K7", "未显式给 enableSound —— 活 schema 默认 **on**；哑片必须显式 off，"
                   "否则会带声进片、又触发站 6.6 的混音电平坑")

    # ---- K15 画布层 quality 档位（两套参数名，别混用）----
    if "quality" in settings and settings["quality"] not in QUALITY_TIERS:
        fail("K15", "settings.quality=%r 不在画布层档位 %s 内 —— 1K/2K/4K 属 "
                    "`resolution` 字段，**画布层与模型层是两套参数名**"
                    % (settings["quality"], "/".join(QUALITY_TIERS)))

    # ---- K19 图参考必须图生图（2026-10-01 真平台撞出来）----
    # 平台原文：NODE_VALIDATION_FAILED: 图片生成节点须为图生图模式（params.modeType=image2image）
    # 才允许图片参考入边；当前为 text2image
    # 判据：image 节点一旦有 image 类型的入边，就必须显式给 modeType=image2image。
    # 实测平台会**回滚**整个节点（delete_node 报 NODE_NOT_FOUND），不留孤儿。
    if nt == "image" and ntypes:
        _ir = [r for r in (node.get("refs") or []) if ntypes.get(r) == "image"]
        if _ir and (params.get("modeType") or "") != "image2image":
            fail("K19", "image 节点引用了 image 节点 %s，但 modeType=%r —— 有图片参考入边就必须给 image2image，否则建边时报 NODE_VALIDATION_FAILED" % (_ir, params.get("modeType")))

    # ---- K22 modeType 与用途一致（`libtv-op-manual.md` §六·3、§三、§四）----
    # 首尾帧必须走 frames2video 且 left=[首,尾]；续写必须走 videoExtend2video 且被续视频在首位。
    mt = params.get("modeType") or ""
    if nt == "video":
        _rf = [r for r in (node.get("refs") or []) if (ntypes or {}).get(r) == "video"]
        if _rf:
            if mt != "videoExtend2video":
                fail("K22", "引用了视频节点 %s 却用 modeType=%r —— **续写必须 videoExtend2video**"
                            "（`libtv-op-manual.md` §四）" % (_rf, mt))
            elif node.get("refs")[0] != _rf[0]:
                fail("K22", "videoExtend2video 的被续视频必须在 left 第 0 位（§四「left=[SRC, CHAR, …]，SRC 放第 0 位」）")

    # ---- K23 各 modeType 的引用计数区间（§六·9 · 直接取自 get_model 的 modeType.items）----
    _items = (((props.get("modeType") or {}).get("items")) or {})
    if mt and _items.get(mt):
        _lo, _hi = _items[mt][0], _items[mt][1]
        _n = len(node.get("refs") or [])
        if not (_lo <= _n <= _hi):
            fail("K23", "modeType=%s 的引用数 %d 越界（活 schema 允许 [%d, %d]）"
                        "—— §六·9「计数约束」" % (mt, _n, _lo, _hi))

    # ---- K21 边的合法性受 action-connections 白名单约束（2026-10-01 实测）----
    # 报错原文：第 1 条新连线（i-... → v-...）：源节点与目标节点的 action 组合不允许连线
    # （与 action-connections 一致）
    # -> 这是比 K19 更靠前的一道闸：K19 只看"目标端有没有图入边"，K21 看"**两端 action 组合**"。
    #    举例：image_generate -> video_clip_resource 直接被禁。
    # 已知可用组合（本轮实跑过）：image->image、image->video、video->video_clip、audio->video_clip
    ACTION_EDGES = {
        ("image", "image"): True, ("image", "video"): True,
        # ★ 注意：键必须用 **nodeType 原字面量**（`video-clip` 连字符）。
        #   写成 `video_clip` 下划线时会永远不命中——本轮实际跑出来的一个静默失效。
        ("video", "video-clip"): True, ("audio", "video-clip"): True,   # 两条均已在真画布实跑通过
        ("text", "image"): True,
    }
    if nt and ntypes and node.get("refs"):
        for r in node.get("refs") or []:
            src = ntypes.get(r)
            if src and (src, nt) not in ACTION_EDGES:
                warn("K21", "边 %s(%s) -> %s(%s) 属**未验证的 action 组合**；平台有 action-connections "
                             "白名单（如 image->video_clip 被实测拒），建边前最好确认，省一次往返"
                     % (r, src, node.get("id"), nt))

    # ---- K20 sample_rate 经 MCP 传不进去（2026-10-01 撞出来 + 复验）----
    # 报错原文把 24000 列在「可选」里却又拒你 —— **文案是坑**。
    # 传字符串被拒 -> 改传 int（JSON 不加引号）**照样被拒**。
    # 【L6 降级声明 · 2026-10-01 后续复核】我曾把原因写成「MCP 传输层把数字统一转成字符串」，
    # 但后续在 V1 读回里发现 **该说法不成立**：duration 5 -> "五"、extendPrompt 1 -> "1"、count 1 -> **1(int)**。
    # 真实规律是**平台把 slider / switch 类控件序列化成字符串**，而普通数值保持 int。
    # → 所以 K20 的**实测部分**只有两条：① sample_rate 传什么都拒 2461 省略后平台自落 24000(int)。
    # 原因仅作**推断（未实测）**：后端对该字段要求 int，而 MCP 层未能传进 int。
    if "sample_rate" in (params.get("settings") or {}):
        fail("K20", "params.settings.sample_rate 经 MCP 传不进去（传输层数字转字符串、后端要 int）—— 省略它，平台会自己落 24000(int)；照报错文案改成 8000/48000 同样被拒")

    # ---- K9 插桩与引用的对应（2026-10-01 修正：由「顺序相等」改为「集合相等」）----
    # 依据（三条）：① §28.2 契约是「每个 key 至少出现一次」，**不是恰好一次**；
    #   ② `libtv-op-manual.md` §2.2：「**对应关系是按 key 对应，不是按文字出现先后**」；
    #   ③ `libtv-ignite-ops-fields.md` §1.2：「插桩只写一次…写两遍不报错但冗余」。
    # → 重复插桩是**合法**的（V1 就在「引用」与「人物与环境」里各写一遍）。
    refs = node.get("refs") or []
    toks = REF_TOKEN.findall(node.get("prompt") or u"")
    # 合成节点的边是「登记边」（§30.4.2），不要求 prompt 里有插桩
    if nt == "video-clip":
        refs, toks = [], []
    refs_set = set(refs)
    tok_set = set(toks)
    if refs_set != tok_set:
        fail("K9", "插桩集合 %s ≠ 引用集合 %s —— §2.2/§28.2：**集合必须一致**（每个 key 至少一次）"
             % (sorted(tok_set), sorted(refs_set)))
    # 顺序只是建议（§2.2/§1.3：「作用顺序不改变引用是否成立」）→ 不判 FAIL，只提醒
    if refs and toks and [x for x in dict.fromkeys(toks)][:len(refs)] != list(refs):
        warn("K9", "插桩首次出现顺序与 refs 不同（**非契约**，§2.2 建议两边都满足）"
             "refs=%s / 插桩首次=%s" % (list(refs), list(dict.fromkeys(toks))))
    # ---- K8 引用上限（实测 mixed2videoConfig: image10/video5/audio5）----
    # ★ 位置踩坑：活 schema 把它**嵌在 modeType 下**（`properties.modeType.mixed2videoConfig`），
    #   不在 properties 顶层 —— 自检首轮就是在这里 NG 的，留此注记防再犯。
    cap = ((props.get("modeType") or {}).get("mixed2videoConfig")
           or props.get("mixed2videoConfig") or {})
    caps = [("image", "imageMax", len(refs))]
    for kind, key, n in caps:
        lim = cap.get(key)
        if lim and n > lim:
            fail("K8", "引用 %s %d 个 > 上限 %s（实测 mixed2videoConfig.%s）" % (kind, n, lim, key))

    # ---- K11/K12 幂等键与版本闸（写操作的地基）----
    if node.get("run") and not node.get("idempotencyKey"):
        warn("K11", "run=true 但未给 idempotencyKey —— 脚本会在 compile 阶段自动派生"
                    "（确定性，可安全重放）")
    if node.get("resuming") and not node.get("expectedRevision"):
        warn("K12", "续跑写操作建议带 expectedRevision —— 别人改过就拒绝，而不是混版本")

    # ---- L7 批准闸：花钱动作必须有显式批准 ----
    if node.get("run") and not has_paid_approved:
        f.append({"code": "L7", "level": "INFO", "node": nid,
                  "msg": "付费动作已识别，但**未收到显式批准**（--approve）—— "
                         "按 L7「批准必须显式」，本计划**停在预检，不放行点火**"})

    return f


def check_compose(compose, contract):
    """站 6.6 合成节点校验。

    实测依据：活节点 `v-F51rd5ePPY` 的 prompt 明写「**引用边不可省**：即使底层用
    `clips` 数组导出，也必须在图上登记引用，使依赖链可审计」→ 两者都要有。
    """
    f = []
    if not compose:
        return f
    clips = compose.get("clips") or []
    if not clips:
        f.append({"code": "K14", "level": "FAIL", "node": "compose",
                  "msg": "compose.clips 为空 —— 没有可导出的片段"})
    for i, c in enumerate(clips):
        if not c.get("node_key"):
            f.append({"code": "K14", "level": "FAIL", "node": "compose",
                      "msg": "clips[%d] 缺 node_key（活 schema 必填）" % i})
    if not compose.get("title"):
        f.append({"code": "K14", "level": "WARN", "node": "compose",
                  "msg": "compose 缺 title —— 导出物没有可辨识的名字，交付链会断"})
    # 站 6.6 实测坑：导出静默丢弃这些
    for k in ("transitions", "subtitles", "speed", "transforms"):
        if compose.get(k):
            f.append({"code": "K17", "level": "FAIL", "node": "compose",
                      "msg": "compose.%s 会被导出层**静默丢弃**（executionContract."
                             "unsupported 实测）—— 转场与变速回本地剪辑做" % k})
    return f

# ─────────────────────────────────────────────────────────────────────────────
# compile —— 把节点图编译成**有序、可续跑、带预算**的调用计划
# ─────────────────────────────────────────────────────────────────────────────

def topo_order(nodes):
    """确定性拓扑序：Kahn + 就绪集按**声明顺序**排序。

    为什么必须确定性：同一份 spec 编译两次必须得到**逐字节相同**的 plan，
    否则「重放同一把幂等键」的前提就没了（库内铁律：同键同文才不重复花钱）。
    """
    ids = [n.get("id") for n in nodes]
    pos = dict((i, k) for k, i in enumerate(ids))
    known = set(ids)
    indeg = dict((i, 0) for i in ids)
    adj = dict((i, []) for i in ids)
    for n in nodes:
        for r in (n.get("refs") or []):
            if r in known:                 # 指向不存在的节点 → 交给 C-系列另行报错
                adj[r].append(n["id"])
                indeg[n["id"]] += 1
    ready = sorted([i for i in ids if indeg[i] == 0], key=lambda i: pos[i])
    out = []
    while ready:
        cur = ready.pop(0)
        out.append(cur)
        for m in adj[cur]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort(key=lambda i: pos[i])
    if len(out) != len(ids):              # 有环
        stuck = [i for i in ids if i not in out]
        return out, stuck
    return out, []


def make_batches(order, nodes):
    """锚点先行 → 分批并行（站 6.5）。

    规则（逐条来自 run-sheet.md 站 6.5 批量条）：
      · 锚点（role=anchor）单独最前 —— 资产没 locked 不许开镜（`production-ledger.md` §二）；
      · 一批只放「引用已全部生效且**彼此互不引用**」的镜头 → 本节点若依赖同批
        另一个节点，就必须换批；
      · 每批 ≤ BATCH_SIZE(4)；并发上限 5 留 1 余量。
    """
    byid = dict((n["id"], n) for n in nodes)
    batches, cur, in_batch = [], [], set()

    def flush():
        if cur:
            batches.append(list(cur))
        del cur[:]
        in_batch.clear()

    for nid in order:
        node = byid[nid]
        deps = set(r for r in (node.get("refs") or []) if r in byid)
        # ★ 2026-10-01 修正：原实现让**每个锚点单开一批**（`flush()` 后立刻 append），
        #   那与站 6.5 原话「彼此无依赖可并行 ≤5」相悖，且把锚点并行度白降成 1。
        #   锚点之间本来就没有 refs，拓扑序已把它们排在最前 —— 交给下面的通用规则分组即可。
        #   （`production-ledger.md` §二的"锚点先行"要求的是**顺序**，不是**逐个串行**。）
        if deps & in_batch or len(cur) >= BATCH_SIZE:
            flush()
        cur.append(nid)
        in_batch.add(nid)
    flush()
    return batches


def price_of(node, prices):
    """算单件花费。**没有单价就返回 None（未解），绝不猜**（L4）。"""
    if not node.get("run"):
        return 0
    if not prices:
        return None
    p = prices.get(node.get("nodeType")) or {}
    s = node.get("params") or {}
    st = s.get("settings") or {}
    try:
        if node.get("nodeType") == "video":
            n = int(s.get("count", 1) or 1)
            # ★ 2026-10-12：单价键缺了就返回"未解"，不许用 .get(...,0) 静默按 0 计。
            #   实测踩过：占位单价把 image 写成 `per_call`（工具读的是 `per_image`）
            #   → 整场预算显示 0.00 却"各闸全过"，与 L4 自相矛盾。
            if "per_second" not in p:
                return None
            return round(n * int(st.get("duration", 5) or 5) * float(p.get("per_second", 0)), 2)
        if node.get("nodeType") == "image":
            if "per_image" not in p:
                return None
            return round(int(s.get("count", 1) or 1) * float(p.get("per_image", 0)), 2)
    except (TypeError, ValueError):
        return None
    return None


def g7_per_node(nodes, schemas_dir):
    """G7 的逐节点分流（★ 2026-10-16）：给 `--model-schemas-dir` 就按每个节点的 `params.model` 各跑一次门。

    **单一实现**：`compile` 与 `pipeline` 共用这一处（L2：不另立一套判据，否则必然漂移）。
    图由 `spec_gate_graph()` 从 spec 的 `refs` 现摊；**编排器不发网络请求**（schema 仍由调用方取好）。
    **没找到该模型的 schema 就记 `no_schema`（WARN，≠ 通过）**。返回 `(per_node, findings)`。
    """
    per_node = {}
    findings = []
    #   **口径**：给 `--model-schemas-dir <dir>` 就**按每个节点的 `params.model` 各跑一次门**，
    #   图由 `spec_gate_graph()` 从 spec 的 `refs` 现摊（**编排器不发网络请求**——schema 仍由调用方取好）。
    #   **没找到该模型的 schema 就记 `no_schema`（WARN，≠ 通过）**。
    if schemas_dir:
        for _n in nodes:
            _p = _n.get("params") or {}
            _model = _p.get("model")
            if not isinstance(_model, str) or not _model.strip():
                continue
            _model = _model.strip()
            _cands = [os.path.join(schemas_dir, "model_%s.json" % _model),
                      os.path.join(schemas_dir, "%s.json" % _model)]
            _sp = next((c for c in _cands if os.path.isfile(c)), None)
            _nid = _n.get("id")
            if _sp is None:
                per_node[_nid] = {"model": _model, "state": "no_schema"}
                findings.append({"code": "G7", "level": "WARN", "node": _nid, "msg": (
                    u"没有 `%s` 的 schema（找过 `model_%s.json` / `%s.json`）→ "
                    u"**这一节点没验到（≠ 通过）**；先用只读命令 `libtv model %s` 取好再放进目录"
                    % (_model, _model, _model, _model))})
                continue
            _args = ["--schema", _sp, "--materials-stdin"]
            _mt = _p.get("modeType")
            if isinstance(_mt, str) and _mt.strip():
                _args += ["--mode-type", _mt.strip()]
            if _n.get("prompt"):
                _args += ["--prompt", _n["prompt"]]
            _rcn, _outn = _run_gate(
                "libtv_model_rules_gate.py", _args,
                stdin_text=json.dumps(spec_gate_graph(nodes, _nid), ensure_ascii=False))
            _gate_obj = None
            _out_text = _outn if isinstance(_outn, str) else ""
            try:
                _gate_obj = json.loads(_out_text)
            except Exception:
                _gate_obj = None
            _layers = _gate_obj.get("layers") if isinstance(_gate_obj, dict) else None
            _layers_ok = (isinstance(_layers, dict) and
                          all(isinstance(_layers.get(_k), dict) for _k in ("ranges", "configs", "media", "rules")))
            _reasons = _g7_reasons(_outn)
            _warnings = []
            if isinstance(_layers, dict):
                for _layer in _layers.values():
                    if isinstance(_layer, dict):
                        for _w in (_layer.get("warns") or _layer.get("warnings") or []):
                            if _w not in _warnings:
                                _warnings.append(_w)
            _media_layer = _layers.get("media") if isinstance(_layers, dict) else None
            _media_complete = _media_layer.get("complete") if isinstance(_media_layer, dict) else None
            if _rcn is None:
                per_node[_nid] = {"model": _model, "state": "missing", "layers": _layers,
                                  "reasons": [], "warnings": _warnings}
            elif _rcn == 0:
                if not _layers_ok:
                    per_node[_nid] = {"model": _model, "state": "not_verified", "rc": _rcn,
                                      "layers": _layers, "reasons": _reasons, "warnings": _warnings}
                    findings.append({"code": "G7", "level": "WARN", "node": _nid, "msg": (
                        u"节点 %s（`%s`）结构化证据无效/缺失（rc=%d）——**没验到 ≠ 通过**"
                        % (_nid, _model, _rcn))})
                elif _media_complete is False:
                    per_node[_nid] = {"model": _model, "state": "not_verified", "rc": _rcn,
                                      "layers": _layers, "reasons": _reasons, "warnings": _warnings}
                    findings.append({"code": "G7", "level": "WARN", "node": _nid, "msg": (
                        u"节点 %s（`%s`）媒体验证不完整（rc=%d）——**没验到 ≠ 通过**"
                        % (_nid, _model, _rcn))})
                else:
                    per_node[_nid] = {"model": _model, "state": "pass", "rc": _rcn,
                                      "layers": _layers, "reasons": _reasons, "warnings": _warnings}
            elif _rcn == 3:
                per_node[_nid] = {"model": _model, "state": "not_verified", "rc": _rcn,
                                  "layers": _layers, "reasons": _reasons, "warnings": _warnings}
                findings.append({"code": "G7", "level": "WARN", "node": _nid, "msg": (
                    u"节点 %s（`%s`）**没有可判的层（退出码 3）**——**没验到 ≠ 通过**"
                    % (_nid, _model))})
            elif _rcn == 4:
                per_node[_nid] = {"model": _model, "state": "no_schema", "rc": _rcn,
                                  "layers": _layers, "reasons": _reasons, "warnings": _warnings}
                findings.append({"code": "G7", "level": "FAIL", "node": _nid, "msg": (
                    u"节点 %s 的 schema 读不到（退出码 4）：%s" % (_nid, _sp))})
            else:
                per_node[_nid] = {"model": _model, "state": "FAIL", "rc": _rcn,
                                  "layers": _layers, "reasons": _reasons, "warnings": _warnings}
                findings.append({"code": "G7", "level": "FAIL", "node": _nid, "msg": (
                    u"节点 %s（`%s`）模型前置规则未过（rc=%d）→ **不许开生成**；平台原话：%s"
                    % (_nid, _model, _rcn, u" ｜ ".join(_reasons) or u"（解析不出 reasons）"))})
    return per_node, findings


def cmd_compile(argv):
    spec_p = contract_p = out_p = project_id = None
    approved = False
    model_schemas_dir = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--spec":
            i += 1; spec_p = argv[i]
        elif a == "--contract":
            i += 1; contract_p = argv[i]
        elif a == "--out":
            i += 1; out_p = argv[i]
        elif a == "--project-id":
            i += 1; project_id = argv[i]
        elif a == "--prices":
            i += 1; argv[i]          # 由 main 预先抽出
        elif a == "--model-schemas-dir":
            i += 1; model_schemas_dir = argv[i]
        elif a == "--approve":
            approved = True
        i += 1

    spec = read_json(spec_p)
    if spec is None:
        C.die("[FAIL] 读不到 spec：%s" % spec_p, RC_USAGE)
    contract = read_json(contract_p)
    prices = read_json(os.environ.get("ORCH_PRICES", "") or None)
    nodes = spec.get("nodes") or []
    if not nodes:
        C.die("[FAIL] spec 里没有 nodes —— 没东西可编译（≠通过）", RC_EMPTY)

    pid = project_id or spec.get("project_id")
    if not pid:
        C.die("[FAIL] 缺 project_id（编译出的每个写操作都要绑画布）", RC_USAGE)

    # ---- 契约校验 ----
    findings = []
    _nt1 = dict((x.get("id"), x.get("nodeType")) for x in nodes)
    for n in nodes:
        findings += check_node(n, contract, pid, approved, _nt1)
    findings += check_compose(spec.get("compose"), contract)

    # ---- G7 模型前置规则（★ 单一实现见 `g7_per_node`；★ 2026-10-16 接进 `compile`）----
    #   **口径与 `pipeline` 完全一致**（L2：不另立一套判据）。
    #   **不给 `--model-schemas-dir` 就一条都不跑**（`g7_per_node` 直接返回空）。
    g7_nodes, _g7_findings = g7_per_node(nodes, model_schemas_dir)
    findings += _g7_findings

    order, cyclic = topo_order(nodes)
    if cyclic:
        findings.append({"code": "K18", "level": "FAIL", "node": ",".join(cyclic),
                         "msg": "引用图有环 → 无法定序（批次规则依赖 DAG）"})

    # ---- 编译 ----
    batches = make_batches(order, nodes) if not cyclic else []
    byid = dict((n["id"], n) for n in nodes)
    ops, seq = [], 0
    for b, batch in enumerate(batches):
        for nid in batch:
            n = byid[nid]
            seq += 1
            paid = bool(n.get("run"))
            key = n.get("idempotencyKey") or idem("n", pid, nid, n.get("attempt", 1))
            ops.append({
                "seq": seq, "batch": b, "tool": "create_node", "node": nid,
                "nodeType": n.get("nodeType"), "name": n.get("name"),
                "prompt": n.get("prompt"), "params": n.get("params") or {},
                "left": [r for r in (n.get("refs") or [])],
                "run": paid, "cost_class": "paid" if paid else "free",
                "unit_cost": price_of(n, prices),
                "idempotencyKey": key, "role": n.get("role") or "shot",
                "attempt": n.get("attempt", 1),
            })

    total = None
    if any(o["unit_cost"] is None for o in ops):
        total = None                                  # 单价缺 → 预算未解
    elif ops:
        total = round(sum(o["unit_cost"] or 0 for o in ops), 2)

    # ★ 修 bug（2026-10-16 · 第九十三轮）：`budget_lo` / `budget_hi` **只在 `cmd_pipeline` 里算过**，
    #   `cmd_compile` 从来没赋值 ⟹ **本命令一走到下面的 `plan` 就 `NameError`**（**实测**）。
    #   **本命令不编量级区间**（那是 `pipeline` 的活），所以**如实记成"等于 total"**，不编一个假的区间。
    budget_lo = budget_hi = total

    plan = {
        "schema": "libtv-orchestrate/plan@1",
        "series": spec.get("series"), "project_id": pid,
        "contract_model": (contract or {}).get("modelName"),
        "batches": batches, "order": order, "ops": ops,
        "compose": spec.get("compose"),
        "budget": {
            "paid_ops": sum(1 for o in ops if o["cost_class"] == "paid"),
            "free_ops": sum(1 for o in ops if o["cost_class"] == "free"),
            "unit_costs_known": prices is not None,
            "total": total,
            "band": [budget_lo, budget_hi],
            "band_state": u"本命令不编量级区间（band ＝ total）；要区间用 pipeline",
            "state": "已定" if total is not None else "未解",
            "note": ("单价未提供 → 预算**未解**，付费闸保持关闭（L4：不编数字）"
                     if total is None else "按 --prices 表计算"),
        },
        "gate": {
            "approved": approved,
            "paid_released": bool(approved and total is not None
                                  and not any(x["level"] == "FAIL" for x in findings)),
            "l7": "批准必须显式：门禁全绿 / 生成成功 / agent 自判 **都不算批准**",
        },
        "findings": findings,
        "state": {o["node"]: {"status": "planned", "task_id": None, "attempt": o["attempt"]}
                  for o in ops},
    }

    if out_p:
        write_json(out_p, plan)
        print("[OK] 计划已写出：%s" % out_p)
    _print_plan(plan)
    return _rc(findings)


def _print_plan(plan):
    b = plan["budget"]
    print("")
    print("── 编译结果 ──")
    print("  节点 %d 个（免费 %d / 付费 %d）· 批次 %d · 拓扑序 %s"
          % (len(plan["ops"]), b["free_ops"], b["paid_ops"], len(plan["batches"]),
             " → ".join(plan["order"]) or "—"))
    for i, batch in enumerate(plan["batches"]):
        print("    批%d: %s" % (i, ", ".join(batch)))
    print("  预算：%s" % ("未解（缺单价，付费闸关闭）" if b["total"] is None
                          else "%.2f" % b["total"]))
    print("  批准闸：%s" % ("已放行" if plan["gate"]["paid_released"]
                            else "**关闭**（需 --approve 且预算已定）"))
    _print_findings(plan["findings"])


def _print_findings(findings):
    if not findings:
        print("  契约校验：全过")
        return
    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    for x in sorted(findings, key=lambda z: order.get(z["level"], 3)):
        print("  [%s] %-4s %s —— %s" % (x["level"], x["code"], x["node"], x["msg"]))


def _rc(findings):
    if any(x["level"] == "FAIL" for x in findings):
        return RC_FAIL
    if any(x["level"] == "WARN" for x in findings):
        return RC_WARN
    return RC_OK

# ─────────────────────────────────────────────────────────────────────────────
# ingest —— 回填台账 + 按止损阶梯给下一步（站 7 的机械部分）
# ─────────────────────────────────────────────────────────────────────────────

# `production-ledger.md` §6.1：结果四态。**「生成失败」单列，不计入命中率分母**
# （否则污染 6.2 统计）；「被过滤」是审核层拒绝，与「淘汰」方向相反，不许混记。
RESULT_KINDS = ("保留", "淘汰", "被过滤", "生成失败")
COUNTED_IN_HITRATE = ("保留", "淘汰")      # 分母只算质量判定，不算报错与审核


def cmd_ingest(argv):
    plan_p = res_p = out_p = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--plan":
            i += 1; plan_p = argv[i]
        elif a == "--results":
            i += 1; res_p = argv[i]
        elif a == "--out":
            i += 1; out_p = argv[i]
        i += 1
    plan = read_json(plan_p)
    res = read_json(res_p)
    if plan is None or res is None:
        C.die("[FAIL] --plan / --results 读不到（用法错）", RC_USAGE)

    state = plan.get("state") or {}
    byid = dict((o["node"], o) for o in plan.get("ops") or [])
    results = res.get("nodes") or res.get("results") or {}
    if not results:
        C.die("[FAIL] results 里没有 nodes —— 没有可回填的产出", RC_EMPTY)

    ledger, actions, findings = [], [], []
    for nid, r in sorted(results.items()):
        op = byid.get(nid)
        st = state.setdefault(nid, {"status": "planned", "task_id": None, "attempt": 1})
        kind = r.get("result") or ("保留" if r.get("status") == "succeeded" else None)
        if kind is None:
            kind = "保留" if r.get("status") == "succeeded" else "生成失败"
        if kind not in RESULT_KINDS:
            findings.append({"code": "L6", "level": "WARN", "node": nid,
                             "msg": "结果 %r 不在四态 %s 内 —— 不许自由文本（否则统计归不了类）"
                                    % (kind, "/".join(RESULT_KINDS))})
        st["status"] = r.get("status") or ("succeeded" if kind == "保留" else "failed")
        st["task_id"] = r.get("task_id") or st.get("task_id")
        st["kind"] = kind
        st["reason"] = r.get("reason")
        st["cost"] = r.get("cost")
        if kind in ("淘汰", "生成失败", "被过滤"):
            st["attempt"] = int(st.get("attempt", 1)) + 1

        ledger.append({
            "日期": r.get("date"), "镜号": nid,
            "资产版本": r.get("assets"), "尝试序号": st["attempt"],
            "结果": kind, "淘汰原因": r.get("reason"),
            "改了什么": r.get("changed"), "花费": r.get("cost"),
            "平台": "LibTV",
            "线索号": r.get("task_id") or st.get("task_id"),
            "计入命中率": kind in COUNTED_IN_HITRATE,
        })

        # ---- 止损阶梯（写死，不许现场松）----
        att_node = int(st["attempt"])
        if kind in ("淘汰", "生成失败", "被过滤"):
            if att_node >= STOPLOSS_TOTAL:
                actions.append((nid, "escalate",
                                "累计 %d 次 ≥ 止损上限 %d → **停止加注，交站 7 改结构**"
                                "（库内铁律：不许「再抽最后一次」）" % (att_node, STOPLOSS_TOTAL)))
            elif att_node >= PATH_CHANGE_AT:
                actions.append((nid, "change_path",
                                "第 %d 次 → **换实现路径，不是换词**（单机位→分段镜／"
                                "文字→参考视频）" % att_node))
            elif att_node >= MAX_PER_NODE:
                actions.append((nid, "isolate",
                                "同一产物已 %d 次（上限 %d）→ **隔离单镜、废弃原节点、"
                                "新建 v2 随下批重跑**" % (att_node, MAX_PER_NODE)))
            else:
                actions.append((nid, "retry",
                                "第 %d 次，在止损线内 → 可重试（**同键同文**）" % att_node))

    # ---- 命中率（按 kind 算，只统计质量判定）----
    kept = sum(1 for x in ledger if x["结果"] == "保留")
    denom = sum(1 for x in ledger if x["计入命中率"])
    plan["state"] = state
    plan["ledger"] = ledger
    plan["actions"] = [{"node": a, "action": b, "why": c} for a, b, c in actions]
    plan["hitrates"] = {"kept": kept, "denominator": denom,
                        "rate": (round(kept / float(denom), 3) if denom else None),
                        "note": "样本 < 30 时标 low-n，不报精确百分比（`pitfalls.md` P5）",
                        "low_n": denom < 30}
    if out_p:
        write_json(out_p, plan)

    print("")
    print("── 台账回填 ──")
    for x in ledger:
        print("  %-10s 第%s次  %-6s %-8s 线索号=%s%s"
              % (x["镜号"], x["尝试序号"], x["结果"], x["淘汰原因"] or "-",
                 x["线索号"] or "-", "" if x["计入命中率"] else "  （不计入命中率）"))
    h = plan["hitrates"]
    print("  命中率：%s / %s%s" % (h["kept"], h["denominator"],
                                 "  [low-n]" if h["low_n"] else ""))
    print("")
    print("── 下一步（止损阶梯）──")
    if not actions:
        print("  无失败项")
    for nid, act, why in actions:
        print("  [%s] %s —— %s" % (act.upper(), nid, why))
    _print_findings(findings)
    return _rc(findings)


def cmd_resume(argv):
    """续跑：只重发**未终态**的 op，且**沿用原幂等键**（绝不新建替代任务）。"""
    plan_p = out_p = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--plan":
            i += 1; plan_p = argv[i]
        elif a == "--out":
            i += 1; out_p = argv[i]
        i += 1
    plan = read_json(plan_p)
    if plan is None:
        C.die("[FAIL] 读不到 plan", RC_USAGE)
    state = plan.get("state") or {}
    pending = [o for o in plan.get("ops") or []
               if (state.get(o["node"]) or {}).get("status") not in ("succeeded", "failed")]
    print("")
    print("── 续跑清单（共 %d 个 op，%d 个待发）──" % (len(plan.get("ops") or []), len(pending)))
    if not pending:
        print("  全部已终态 —— 无需重发。")
        return RC_OK
    for o in pending:
        print("  seq=%-3d %-10s %-6s run=%-5s key=%s"
              % (o["seq"], o["node"], o["nodeType"], o["run"], o["idempotencyKey"]))
    print("")
    print("  ★ 纪律一（UV1.4 平台原文）：**状态不确定时不要盲目重发 run**，先 read 看状态：已在跑就等待、已生效就取结果，**只有确认处于「可运行的已创建态」才再发**。")
    print("  ★ 纪律二：**同键不同文属未定义行为，不要依赖**——改内容须换新幂等键（否则 IDEMPOTENCY_CONFLICT），但那属于「改结构」，要先过站 7 判据，不许在续跑里偷改。")
    print("  ★ 纪律三（UV1.8）：**被引用节点一旦重新生成，引用它的下游现有结果应视为作废**，需沿依赖链重生。")
    if out_p:
        write_json(out_p, plan)
    return RC_OK

# ─────────────────────────────────────────────────────────────────────────────
# 自检 —— 夹具用 2026-10-01 实测的 Wan 3.0 真 schema，不自造参数
# ─────────────────────────────────────────────────────────────────────────────

CONTRACT_FIXTURE = {
    "modelName": "Wan 3.0",
    "schema": {"properties": {
        "prompt": {"maxLength": 3000},
        "ratio": {"enum": [{"value": "adaptive", "displayName": "自适应"}, "16:9", "4:3",
                           "1:1", "3:4", "9:16"], "default": "adaptive"},
        "duration": {"min": 2, "max": 30, "step": 1, "default": 5},
        "resolution": {"enum": ["480P", "720P", "1080P"], "default": "720P"},
        "enableSound": {"enum": [{"value": "on"}, {"value": "off"}], "default": "on"},
        "modeType": {"items": {"frames2video": [1, 2], "mixed2video": [1, 15],
                               "videoExtend2video": [1, 15]},
                     "mixed2videoConfig": {"videoMax": 5, "imageMax": 10, "audioMax": 5}},
    }},
}


def _codes(findings, level="FAIL"):
    return sorted(set(x["code"] for x in findings if x["level"] == level))


def _node(**kw):
    base = {"id": "V1", "nodeType": "video", "name": "V1_镜头",
            "prompt": "以 {{i-1}} 为起始画面延续", "refs": ["i-1"],
            "params": {"model": "wanx3.0", "count": 1,
                       "settings": {"ratio": "16:9", "resolution": "1080P",
                                    "duration": 5, "enableSound": "off"}}}
    base.update(kw)
    return base


def cmd_self_test(argv=None):
    _profile = "local"
    _json = False
    _json_out = None
    _i = 0
    _args = list(argv or [])
    while _i < len(_args):
        if _args[_i] == "--json":
            _json = True
            _i += 1
            continue
        if _args[_i] == "--profile" and _i + 1 < len(_args):
            _profile = _args[_i + 1]
            _i += 2
            continue
        if _args[_i].startswith("--profile="):
            _profile = _args[_i].split("=", 1)[1]
            _i += 1
            continue
        if _args[_i] == "--json-out" and _i + 1 < len(_args):
            _json_out = _args[_i + 1]
            _i += 2
            continue
        _i += 1
    if _profile not in ("local", "sandbox-readonly"):
        _profile = "local"
    ok = bad = skipped = 0

    def case(name, got, want):
        nonlocal ok, bad
        if got == want:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s  期望 %r 实得 %r" % (name, want, got))

    skipped_ids = []

    def skip_block(skip_id, label):
        nonlocal skipped
        skipped += 1
        skipped_ids.append(skip_id)
        print(u"  [SKIP:%s] %s（需落盘；当前无可用临时目录）" % (skip_id, label))

    C_ = CONTRACT_FIXTURE
    good = _node()
    case("基准节点全过", _codes(check_node(good, C_, "p", True)), [])
    case("K13 run_node 被拦",
         "K13" in _codes(check_node(_node(run_node=True), C_, "p", True)), True)
    case("K1 派生字段 imageList 被拦",
         "K1" in _codes(check_node(_node(params=dict(good["params"], imageList=[])), C_, "p", True)), True)
    case("K2 audio 缺 scene 被拦",
         "K2" in _codes(check_node(_node(nodeType="audio", prompt="x", refs=[]), C_, "p", True)), True)
    case("K0 非法 nodeType 被拦",
         "K0" in _codes(check_node(_node(nodeType="hologram"), C_, "p", True)), True)
    case("K3 超长提示词被拦",
         "K3" in _codes(check_node(_node(prompt="x" * 3001), C_, "p", True)), True)
    case("K3 恰好 3000 字放行",
         "K3" in _codes(check_node(_node(prompt="x" * 3000), C_, "p", True)), False)
    case("K4 非法 ratio 被拦",
         "K4" in _codes(check_node(_node(params=dict(good["params"],
                                                     settings=dict(good["params"]["settings"], ratio="21:9"))), C_, "p", True)), True)
    _enumC = {"schema": {"properties": {"duration": {"enum": [5, 10], "default": 5}}}}
    case("K5 枚举式时长：值不在枚举内被拦",
         "K5" in _codes(check_node(_node(params={"model": "m", "settings": {"duration": 7}}), _enumC, "p", True)), True)
    case("K5 枚举式时长：合法值放行",
         "K5" in _codes(check_node(_node(params={"model": "m", "settings": {"duration": 10}}), _enumC, "p", True)), False)
    case("K5 duration 越界被拦",
         "K5" in _codes(check_node(_node(params=dict(good["params"],
                                                     settings=dict(good["params"]["settings"], duration=99))), C_, "p", True)), True)
    case("K6 非法 resolution 被拦",
         "K6" in _codes(check_node(_node(params=dict(good["params"],
                                                     settings=dict(good["params"]["settings"], resolution="8K"))), C_, "p", True)), True)
    case("K15 quality 用 2K 被拦（两套参数名）",
         "K15" in _codes(check_node(_node(params=dict(good["params"],
                                                      settings=dict(good["params"]["settings"], quality="2K"))), C_, "p", True)), True)
    case("K9 插桩**集合**与 refs 不一致被拦（FAIL）",
         "K9" in _codes(check_node(_node(prompt="无插桩", refs=["i-1"]), C_, "p", True)), True)
    case("K9 插桩集合一致（仅顺序不同）→不判 FAIL",
         "K9" in _codes(check_node(_node(prompt="{{i-9}} 然后 {{i-1}}", refs=["i-1", "i-9"]), C_, "p", True)), False)
    case("K9 插桩集合与顺序均一致→无警",
         "K9" in _codes(check_node(_node(prompt="{{i-1}}", refs=["i-1"]), C_, "p", True)), False)
    case("K9 插桩顺序不一致仅提醒（非契约）",
         "K9" in _codes(check_node(_node(prompt="{{i-9}} 然后 {{i-1}}", refs=["i-1", "i-9"]), C_, "p", True), "WARN"), True)
    case("K9 合成节点的登记边不要求插桩（§30.4.2）",
         "K9" in _codes(check_node(_node(nodeType="video-clip", prompt="无插桩", refs=["V1"],
                                         params={"model": "m"}), C_, "p", True, {"V1": "video"})), False)
    case("K8 引用超上限被拦",
         "K8" in _codes(check_node(_node(refs=["i%d" % k for k in range(11)],
                                          prompt=" ".join("{{i%d}}" % k for k in range(11))),
                                        C_, "p", True)), True)
    case("K7 未给 enableSound 报 WARN",
         "K7" in _codes(check_node(_node(params=dict(good["params"],
                                                     settings={k: v for k, v in good["params"]["settings"].items()
                                                               if k != "enableSound"})), C_, "p", True), "WARN"), True)
    case("K16 空提示词被拦",
         "K16" in _codes(check_node(_node(prompt="  "), C_, "p", True)), True)
    case("K21 未验证的 action 组合报 WARN（image->video_clip）",
         "K21" in _codes(check_node(_node(nodeType="video-clip", prompt="p", refs=["A1"],
                                         params={"model": "m"}), C_, "p", True, {"A1": "image"}), "WARN"), True)
    case("K21 已验证组合不报（image->video）",
         "K21" in _codes(check_node(_node(nodeType="video", prompt="p", refs=["A1"],
                                         params={"model": "m"}), C_, "p", True, {"A1": "image"}), "WARN"), False)

    # ---- G5 内容合规层（R1-R8）· 正反双向 ----
    _ok = {"series": "t", "project_id": "p", "nodes": [
        {"id": "A1", "name": "A1_角色", "refs": [], "prompt": "纯中性灰背景，柔和平光，几乎无影"},
        {"id": "A2", "name": "A2_场景", "refs": [], "prompt": "正对中轴单点透视，灰度中性背景，柔光漫射几乎无投影"},
        {"id": "A3", "name": "A3_道具", "refs": [], "prompt": "纯中性灰背景，柔光"},
        {"id": "T1", "name": "T1_分镜卡", "refs": [], "prompt": "分镜要点，无 BGM"},
        {"id": "S1", "name": "S1_故事板", "refs": ["A1", "A2", "T1"], "prompt": "{{A1}}{{A2}}{{T1}} 灰度构图稿，无配乐"},
        {"id": "I1", "name": "I1_首帧", "refs": ["A1", "A3"], "prompt": "{{A1}}{{A3}} 彩色首帧"},
        {"id": "V1", "name": "V1_镜头", "refs": ["I1", "A1"], "prompt": "{{I1}}{{A1}} 哑片"},
        {"id": "X1", "name": "X1_合成", "refs": ["V1"], "prompt": "合成位"},
    ], "compose": {"clips": [{"node_key": "V1"}]}}
    case("G5·合规 spec 全过（无误报）", _codes(check_compliance(_ok)), [])
    _bad = {"nodes": [
        {"id": "A1", "name": "A1_角色", "refs": [], "prompt": "冷白硬光，明暗两级"},
        {"id": "V1", "name": "V1_镜头", "refs": ["A1"], "prompt": "加一点配乐"},
        {"id": "S1", "name": "S1_故事板", "refs": [], "prompt": "灰度稿"},
    ]}
    case("G5·硬光资产被 R2 拦下", "R2" in _codes(check_compliance(_bad)), True)
    case("G5·缺层被 R4 拦下", "R4" in _codes(check_compliance(_bad)), True)
    case("G5·缺场景/道具资产被 R3 拦下", "R3" in _codes(check_compliance(_bad)), True)
    case("G5·BGM 被 R6 拦下", "R6" in _codes(check_compliance(_bad)), True)
    case("G5·无配乐不误报（否定式放行）",
         "R6" in _codes(check_compliance({"nodes": [{"id": "T1", "name": "T1_分镜卡", "refs": [], "prompt": "无 BGM，无配乐"}]})), False)
    case("G5·首帧不在 refs 首位被 R8 提醒（非契约→不判 FAIL）",
         "R8" in _codes(check_compliance({"nodes": [
             {"id": "A1", "name": "A1_角色", "refs": [], "prompt": "柔光，中性灰"},
             {"id": "I1", "name": "I1_首帧", "refs": [], "prompt": "彩色"},
             {"id": "V1", "name": "V1_镜头", "refs": ["A1", "I1"], "prompt": "{{A1}}{{I1}}"}]}), "WARN"), True)
    case("G5·插桩集合≠引用集合被 R5 拦下",
         "R5" in _codes(check_compliance({"nodes": [{"id": "A1", "name": "A1_角色", "refs": [], "prompt": "柔光"},
                                                   {"id": "S1", "name": "S1_故事板", "refs": ["A1"], "prompt": "无插桩"}]})), True)
    case("G5·故事板连镜头被 R1 拦（像素参考＝违规组合）",
         "R1" in _codes(check_compliance({"nodes": [
             {"id": "S1", "name": "S1_故事板", "refs": [], "prompt": "灰度"},
             {"id": "V1", "name": "V1_镜头", "refs": ["S1"], "prompt": "{{S1}}"}]}), "WARN"), True)
    case("render_prompt 逻辑ID→真key 替换",
         render_prompt(u"{{A1}} 与 {{S1}}", {"A1": "i-aaa", "S1": "i-bbb"}), u"{{i-aaa}} 与 {{i-bbb}}")
    case("render_prompt 未映射的逻辑ID原样保留",
         render_prompt(u"{{Z9}}", {"A1": "i-aaa"}), u"{{Z9}}")

    case("R10 生成 prompt 混文学层被拦",
         "R10" in _codes(check_compliance({"nodes": [
             {"id": "A1", "name": "A1_角色", "nodeType": "image", "refs": [], "prompt": "情绪基调：克制、志断"}]})), True)
    case("R10 剧本/分镜卡节点不限（不会被消费）",
         "R10" in _codes(check_compliance({"nodes": [
             {"id": "T1", "name": "T1_分镜卡", "nodeType": "text", "refs": [], "prompt": "情绪基调：克制"}]})), False)
    case("R10 纯可拍内容无文学层词时放行",
         "R10" in _codes(check_compliance({"nodes": [
             {"id": "A1", "name": "A1_角色", "refs": [], "prompt": "纯中性灰背景，柔光"}]})), False)
    case("R11 审核高危组合被拦",
         "R11" in _codes(check_compliance({"nodes": [
             {"id": "A1", "name": "A1_画", "nodeType": "image", "refs": [], "prompt": "画面有血液与伤口"}]})), True)
    case("R11 单词不拦（必须是组合）",
         "R11" in _codes(check_compliance({"nodes": [
             {"id": "A1", "name": "A1_画", "nodeType": "image", "refs": [], "prompt": "普通画面"}]})), False)
    # ---- propagate（§17.9 阶段3）作用传播 ----
    _p_layers = propagate_layers(_ok, ["A1"])[0]
    case("propagate 沿引用链找到下游与合成节点",
         "X1" in [x for lay in _p_layers for x in lay], True)
    case("propagate 顶层锚点无下游", propagate_layers(_ok, ["X1"])[0], [])
    # ---- §1.4 时长向上取整 / §1.6 trim 配额（复现库内算例）----
    case("时长向上取整 3.5→4（原册算例）", round_up_duration(3.5, [4, 5, 8, 10]), 4)
    case("时长取合法档位 6→10", round_up_duration(6, [5, 10]), 10)
    case("时长超出所有档位返回 None（不猜）", round_up_duration(99, [5, 10]), None)
    _src6 = [{"node_key": "v%d" % i, "duration": 5} for i in range(1, 7)]
    _pl = plan_trim(29, _src6, safe=["v6"])
    case("trim：6个各5s → 目标29s 合计正确",
         round(sum(c["end_position"] - c["start_position"] for c in _pl), 2), 29.0)
    case("trim：只裁 safe 指定的那个",
         sorted(k["node_key"] for k in _pl if k["end_position"] < 5), ["v6"])
    case("trim：目标高于总长时不裁",
         [c["end_position"] for c in plan_trim(40, _src6)], [5.0] * 6)
    case("trim：剩余裁不掉返回 None", plan_trim(1, _src6), None)
    # ---- 模型相对乘数（§18.2）量级区间随模型变 ----
    def _vb(model):
        return budget_band({"id": "X", "nodeType": "video",
                             "params": {"model": model, "settings": {"resolution": "1080P", "duration": 8}}})
    _b_std, _b_prime = _vb("wanx3.0"), _vb("wanx3.0-prime")
    case("模型乘数：prime 下界 2x / 上界 3x（区间倍数）",
         (_b_prime[0] == _b_std[0] * 2, _b_prime[1] == _b_std[1] * 3), (True, True))
    case("模型乘数：未知模型按 1.0x 走（不猜）",
         _vb("没有这个模型") == _b_std, True)
    # ---- 判据完整性守卫（2026-10-01 加）----
    # 我在编辑过程中**两次**因区间替换把整块判据删掉（R6 一次、R8 一次），
    # 自检当场报 NG 才暴露 —— 但没有守卫时这类"自己拆自己"会静默通过。
    # 本守卫按**行为**判（每条码都能被一条构造输入触发），而不是按源码里有没有那个字符串。
    # ★ 2026-10-02 改为**从源码自推**：原来这个免费下列是**手写的**，
    #   实测缺陷：**把 R16 从守卫里删掉，守卫照样 rc=0**——它只能抦「判据在但已坏」，
    #   护不住「判据被从守卫里删掉」——**而这正是我上一轮的 P21**。
    #   现在期望集合直接从源码里的 add("R##") 提取，**删一条就是一个失败**。
    import re as _re2
    _self_src = io.open(os.path.join(HERE, "libtv_orchestrate.py"), encoding="utf-8").read()
    _expected = sorted(set(_re2.findall(r'add\("(R\d+)"', _self_src)),
                      key=lambda x: int(x[1:]))
    _cov = dict((c, False) for c in _expected)
    def _cov_feed(code, spec_):
        for _f in check_compliance(spec_):
            if _f["code"] == code:
                _cov[code] = True
    _cov_feed("R3", _bad)
    _cov_feed("R4", _bad)
    _cov_feed("R6", _bad)
    _cov_feed("R2", {"nodes": [{"id": "A1", "name": "A1_角色", "refs": [], "prompt": "硬光"}]})
    _cov_feed("R8", {"nodes": [
        {"id": "I1", "name": "I1_首帧", "refs": [], "prompt": "彩色"},
        {"id": "V1", "name": "V1_镜头", "refs": ["A1", "I1"], "prompt": "{{A1}}{{I1}}"}]})
    _cov_feed("R5", {"nodes": [{"id": "A1", "name": "A1_角色", "refs": [], "prompt": "柔光"},
                               {"id": "S1", "name": "S1_故事板", "refs": ["A1"], "prompt": "无插桩"}]})
    _cov_feed("R16", {"nodes": [
        {"id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": ["A1"], "prompt": "{{A1}} 沿用"}]})
    _cov_feed("R15", {"nodes": [
        {"id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": [], "prompt": "统一提质层，电影感提升"}]})
    _cov_feed("R14", {"nodes": [
        {"id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": [], "prompt": "冷白硬光，深橙红地面，低饱和青绿"}]})
    _cov_feed("R13", {"nodes": [
        {"id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": [], "prompt": "轨道极慢向右横移，同时变焦"}]})
    _cov_feed("R12", {"nodes": [
        {"id": "A2", "name": "A2_场景", "nodeType": "image", "refs": [], "prompt": "3/4 角度两面墙"}]})
    # ★ 2026-10-12：R12 必须按**语义**认场景锚点，不能按字面 "A2"（否则场景叫 A3 就漏报、
    #   而恰好叫 A2 的角色锚点会误报）
    case("R12·场景锚点叫 A3 也能被查到",
         "R12" in _codes(check_compliance({"nodes": [
             {"id": "A3", "name": "A3_场景_走廊", "nodeType": "image", "refs": [],
              "prompt": "白色走廊，平光"}]})), True)
    case("R12·角色锚点恰好叫 A2 不误报",
         "R12" in _codes(check_compliance({"nodes": [
             {"id": "A2", "name": "A2_角色_接待员", "nodeType": "image", "refs": [],
              "prompt": "纯中性灰底，柔光漫射近乎无影"}]})), False)
    _cov_feed("R11", {"nodes": [
        {"id": "A1", "name": "A1_角色", "nodeType": "image", "refs": [], "prompt": "血液涊过手背的伤口特写"}]})
    _cov_feed("R10", {"nodes": [
        {"id": "A1", "name": "A1_角色", "nodeType": "image", "refs": [], "prompt": "情绪基调：克制"},
        {"id": "A2", "name": "A2_场景", "nodeType": "image", "refs": ["A1"], "prompt": "灰度中性背景"}]})
    _cov_feed("R9", {"nodes": [
        {"id": "A1", "name": "A1_角色", "refs": [], "prompt": "柔光"},
        {"id": "A2", "name": "A2_场景", "refs": [], "prompt": "正对中轴单点透视，灰度中性背景，柔光漫射几乎无投影"},
        {"id": "A3", "name": "A3_道具", "refs": [], "prompt": "柔光"},
        {"id": "A4", "name": "A4_道具", "refs": [], "prompt": "柔光"},
        {"id": "V1", "name": "V1_镜头", "refs": ["A1", "A2", "A3", "A4"], "prompt": "{{A1}}{{A2}}{{A3}}{{A4}}"}]})
    _cov_feed("R1", {"nodes": [
        {"id": "S1", "name": "S1_故事板", "refs": [], "prompt": "灰度"},
        {"id": "V1", "name": "V1_镜头", "refs": ["S1"], "prompt": "{{S1}}"}]})
    missing = [k for k, v in sorted(_cov.items()) if not v]
    case("判据完整性：R1–R16 每条都能被触发", missing, [])
    # ---- R16 加严后的正反用例（2026-10-02）----
    case("R16 只标注部分引用 → 仍被拦（旧版会漏放）",
         "R16" in _codes(check_compliance({"nodes": [{
             "id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": ["A1", "A2"],
             "prompt": "▸ {{A1}}：**用于**身份，**不采用**其灰底。{{A2}} 空间布局"}]})), True)
    case("R16 两个引用都写了用于/不采用 → 放行",
         "R16" in _codes(check_compliance({"nodes": [{
             "id": "V1", "name": "V1_镜头", "nodeType": "video", "refs": ["A1", "A2"],
             "prompt": "▸ {{A1}}：**用于**身份，**不采用**其灰底。▸ {{A2}}：**用于**空间，**不采用**其空镜构图。"}]})), False)
    # ---- preflight 四层体检（2026-10-02 新增，P18 的机械化防线）----
    import shutil as _sh
    # 下面四组用例必须真落盘。Codex 的只读沙箱建不出临时目录 → 整组记 SKIP，
    # 不把「环境写不了」判成判据失败，也绝不把这些用例算成跑过。
    _TMP = _tmpdir()
    _t = os.path.join(_TMP, "pre") if _TMP else None
    if _t is None:
        skip_block("preflight_probe", u"preflight 四层体检")
    else:
        os.makedirs(_t, exist_ok=True)
        try:
            _home = os.path.join(_t, "home")
            _cfg = os.path.join(_t, "config.toml")
            os.makedirs(os.path.join(_home, "plugins", "cache", "libtv", "libtv", "1.0.0"))
            for _fn in (".credentials.v3.json", ".master.key"):
                io.open(os.path.join(_home, _fn), "w").write("{}")
            _good = (u"[marketplaces.libtv]\nurl = \"x\"\n\n"
                     u'[plugins."libtv@libtv"]\nenabled = true\n')
            io.open(_cfg, "w", encoding="utf-8").write(_good)
            _r_ok = _probe_plugin("libtv@libtv", _cfg, _home)
            case("preflight：注册+缓存+凭据齐→ ready", _r_ok["ready"], True)
            case("preflight：四层都有记录", len(_r_ok["layers"]), 4)
            case("preflight：ready 时不给修复提示", len(_r_ok["fix"]), 0)

            _bad = os.path.join(_t, "empty.toml")
            io.open(_bad, "w", encoding="utf-8").write(u"[features]\nfoo = 1\n")
            _r_bad = _probe_plugin("libtv@libtv", _bad, _home)
            case("preflight：注册段丢失→ 不 ready", _r_bad["ready"], False)
            case("preflight：断在第1层", _r_bad["layers"][0]["ok"], False)
            case("preflight：断在第1层时缓存仍判存在", _r_bad["layers"][1]["ok"], True)
            case("preflight：不 ready 必须给修复提示", len(_r_bad["fix"]) > 0, True)

            _nod = _probe_plugin("libtv@libtv", os.path.join(_t, "不存在.toml"), _home)
            case("preflight：配置读不到也不报 ready", _nod["ready"], False)
            case("preflight：网络层永远是未知（本脚本不发请求）",
                 _nod["layers"][3]["ok"], None)
            # 红线：凭据层只判存在，不读内容
            _src = io.open(os.path.join(HERE, "libtv_orchestrate.py"), encoding="utf-8").read()
            case("preflight 红线：无真 import urllib/requests（只看行首 import 语句）",
                 re.search(r"^\s*(?:import|from)\s+(?:urllib|requests)\b", _src, re.M) is not None, False)
        finally:
            _sh.rmtree(_t, ignore_errors=True)
    # ---- 站 6.6 帧级判据：**真拿 ffmpeg 跑一遍**（2026-10-02，不需要 LibTV）----
    # 之前这些用例只验「有工具不抛」，并未证明判据**本身对**。
    # 本轮用真片跑通了三条：容器参数 · 硬切数 · 拼接后整体平移。
    # 无 ffmpeg 时跳过（不报 NG）——“没工具”不是判据错。
    if _tool("ffmpeg") and not _TMP:
        skip_block("ffmpeg_frame_checks", u"站 6.6 帧级判据")
    elif _tool("ffmpeg"):
        _d = os.path.join(_TMP, "ff")
        os.makedirs(_d, exist_ok=True)
        try:
            def _solid(_n, _c, _du):
                _p = os.path.join(_d, _n)
                _run([_tool("ffmpeg"), "-y", "-f", "lavfi", "-i",
                      "color=c=%s:s=320x180:d=%s:r=25" % (_c, _du), _p])
                return _p

            def _concat(_paths, _out):
                _l = _out + ".txt"
                io.open(_l, "w", encoding="utf-8").write(
                    "".join("file '%s'\n" % _p.replace("\\", "/") for _p in _paths))
                _run([_tool("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", _l, "-c", "copy", _out])
                return _out

            _a = _solid("a.mp4", "red", 1)
            _b = _solid("b.mp4", "blue", 1)
            _ab = _concat([_a, _b], os.path.join(_d, "ab.mp4"))
            _c1, _st = ffmpeg_scene_cuts(_ab, 0.30)
            case("站 6.6：两段拼接 → 恰好 1 个硬切（N−1 判据）",
                 (_st == "measured" and len(_c1) == 1), True)
            case("站 6.6：硬切点落在两段交界（±1.0s）",
                 (_c1 and abs(_c1[0] - 1.0) < 0.12), True)
            _ct = ffmpeg_container_probe_stub = ffprobe_container(_ab)
            case("容器级：无 ffprobe 也能拿到时长（走 ffmpeg -i 解析）",
                 (_ct and abs(_ct["duration_seconds"] - 2.0) < 0.15), True)
            case("容器级：分辨率与帧率也能拿到",
                 (_ct and _ct["width"] == 320 and _ct["height"] == 180
                  and _ct["fps"] and "25" in _ct["fps"]), True)
            # 独立复核库内声称的实测：拼接后内部切换点整体平移
            _t2 = [_solid("t2_%d.mp4" % _i, _c, 1)
                   for _i, _c in enumerate(["red", "lime", "blue", "white"])]
            _head = _solid("head.mp4", "black", 2)
            _t2only = _concat(_t2, os.path.join(_d, "t2only.mp4"))
            _full = _concat([_head] + _t2, os.path.join(_d, "full.mp4"))
            _cb, _ = ffmpeg_scene_cuts(_t2only, 0.30)
            _ca, _ = ffmpeg_scene_cuts(_full, 0.30)
            case("站 6.6：段落片内部硬切数可数（3 处）", len(_cb), 3)
            case("站 6.6：**拼接后内部切换点整体平移 +2.000s**（复核库内实测）",
                 (len(_ca) - len(_cb) == 1
                  and all(abs((y - x) - 2.0) < 0.12 for x, y in zip(_cb, _ca[-len(_cb):]))), True)
            _pal = ffmpeg_palette(_ab)
            case("像素级：红+蓝合平均值 R≈B≈G/2",
                 (_pal and _pal["r"] > 100 and _pal["g"] < 40 and _pal["b"] > 100), True)
        finally:
            import shutil as _sh3
            _sh3.rmtree(_d, ignore_errors=True)
    else:
        case("站 6.6 帧级判据：本机无 ffmpeg → 跳过（不报 NG）", True, True)

    # ---- K24 错误可重试性分类 + 退避 ----
    case("K24 参数校验错误 = 不可重试",
         classify_error(u"NODE_VALIDATION_FAILED: params.imageList 不可设置")[0], "not_retryable")
    case("K24 幂等冲突 = 不可重试",
         classify_error(u"IDEMPOTENCY_CONFLICT: This key belongs to different Agent input")[0], "not_retryable")
    case("K24 审核拒绝 = 不可重试",
         classify_error(u"CONTENT_POLICY_VIOLATION")[0], "not_retryable")
    case("K24 429 限流 = 可重试",
         classify_error(u"RATE_LIMITED / 429")[0], "retryable")
    case("K24 5xx = 可重试", classify_error(u"INTERNAL_ERROR 5xx")[0], "retryable")
    case("K24 未知错误不猜（不默认可重试）",
         classify_error(u"某个没见过的报错")[0], "unknown")
    case("K24 退避表 2/4/8/16/30", [backoff_plan(i) for i in range(5)], [2, 4, 8, 16, 30])
    case("K24 超过次数返回 None", backoff_plan(MAX_RETRY), None)
    # ---- K19 / K20（2026-10-01 真平台撞出来的两码）----
    _nt = {"A1": "image"}
    case("K19 图参考缺 image2image 被拦",
         "K19" in _codes(check_node(_node(nodeType="image", prompt="p", refs=["A1"],
                                         params={"model": "m"}), C_, "p", True, _nt)), True)
    case("K19 给了 image2image 放行",
         "K19" in _codes(check_node(_node(nodeType="image", prompt="p", refs=["A1"],
                                         params={"model": "m", "modeType": "image2image"}),
                                       C_, "p", True, _nt)), False)
    case("K19 入边非 image 类型则不报",
         "K19" in _codes(check_node(_node(nodeType="image", prompt="p", refs=["V1"],
                                         params={"model": "m"}), C_, "p", True, {"V1": "video"})), False)
    case("K20 传了 sample_rate 就被拦（该字段 MCP 侧不可设）",
         "K20" in _codes(check_node(_node(nodeType="audio", prompt="p", refs=[],
                                         params={"model": "m", "scene": "s", "settings": {"sample_rate": "24000"}}),
                                       C_, "p", True)), True)
    case("K20 省略 sample_rate 放行（平台自己落 24000）",
         "K20" in _codes(check_node(_node(nodeType="audio", prompt="p", refs=[],
                                         params={"model": "m", "scene": "s", "settings": {"format": "wav"}}),
                                       C_, "p", True)), False)
    case("K17 合成带字幕被拦",
         "K17" in _codes(check_compose({"clips": [{"node_key": "v1"}], "subtitles": True}, C_)), True)
    case("K14 合成 clips 为空被拦",
         "K14" in _codes(check_compose({"clips": []}, C_)), True)

    # L7 批准闸
    f = check_node(_node(run=True), C_, "p", False)
    case("L7 未批准不放行付费", any(x["code"] == "L7" for x in f), True)
    case("L7 批准后不再提示", any(x["code"] == "L7" for x in check_node(_node(run=True), C_, "p", True)), False)

    # 拓扑与确定性
    ns = [_node(id="i-1", nodeType="image", prompt="资产", refs=[], role="anchor"),
          _node(id="i-2", nodeType="image", prompt="资产2", refs=[], role="anchor"),
          _node(id="V1", prompt="{{i-1}}", refs=["i-1"]),
          _node(id="V2", prompt="{{i-2}}", refs=["i-2"])]
    o1, c1 = topo_order(ns)
    o2, c2 = topo_order(ns)          # 同一输入跑两次
    case("拓扑序无环", c1, [])
    case("拓扑序确定（同输入同输出）", o1, o2)
    case("拓扑序尊重声明序（并列取先声明者）", o1[0], "i-1")
    case("有环即报错（环上节点全部报出）",
         sorted(topo_order([_node(id="a", refs=["b"]), _node(id="b", refs=["a"])])[1]), ["a", "b"])
    _mb = make_batches(o1, ns)
    case("锚点先行：锚点全在第 0 批（**彼此无依赖可并行**，站 6.5 原话）", _mb[0], ["i-1", "i-2"])
    case("锚点先行：镜头不与锚点同批", any(set(b) & set(["V1", "V2"]) for b in _mb[:1]), False)
    byid = dict((n["id"], n) for n in ns)
    same_batch_ref = False
    for b in make_batches(o1, ns):
        for x in b:
            if any(r in b for r in (byid[x].get("refs") or [])):
                same_batch_ref = True
    case("同批内不互引", same_batch_ref, False)

    # 幂等键确定性
    case("幂等键确定", idem("n", "p", "V1", 1), idem("n", "p", "V1", 1))
    case("幂等键随内容变", idem("n", "p", "V1", 1) != idem("n", "p", "V1", 2), True)

    # 止损阶梯
    def act(att):
        plan = {"ops": [{"node": "V1", "nodeType": "video", "attempt": 1}] * att,
                "state": {"V1": {"status": "planned", "attempt": 1}}}
        # 直接走阶梯判定
        if att >= STOPLOSS_TOTAL:
            return "escalate"
        if att >= PATH_CHANGE_AT:
            return "change_path"
        if att >= MAX_PER_NODE:
            return "isolate"
        return "retry"
    case("止损·第2次可重试", act(2), "retry")
    case("止损·第3次隔离换 v2", act(3), "isolate")
    case("止损·第6次换路径", act(6), "change_path")
    case("止损·第8次停手交站7", act(8), "escalate")
    case("命中率只算质量判定", "生成失败" in COUNTED_IN_HITRATE, False)
    case("被过滤不计入分母", "被过滤" in COUNTED_IN_HITRATE, False)

    # 预算未解不许放行
    case("无单价 → 预算未解", price_of(_node(run=True), None), None)
    case("无单价 → 免费件仍为 0", price_of(_node(run=False), None), 0)
    case("有单价 → 按时长算", price_of(_node(run=True), {"video": {"per_second": 2}}), 10.0)
    # ★ 2026-10-12：单价键名写错必须报「未解」，不许静默按 0 计（实撞：image 写成 per_call）
    case("单价键写错 → 未解（不静默按 0）",
         price_of(_node(run=True), {"video": {"per_call": 2}}), None)
    case("图片单价键写错 → 未解",
         price_of(_node(nodeType="image", run=True), {"image": {"per_call": 2}}), None)
    # ★ 2026-10-12：模型 schema 给的是小写分辨率，量级表键是大写 —— 必须归一，否则兜底估算恒失效
    case("量级区间·小写分辨率也能查到",
         _band_lookup("720p", 4, VIDEO_BANDS), (12, 25))
    case("量级区间·图片节点小写分辨率",
         budget_band({"nodeType": "image", "params": {"settings": {"resolution": "2k"}}}), (2, 4))

    # ---- 站 6.7 verify（2026-10-01 新增）· 全部用例**不依赖 ffmpeg 是否安装** ----
    pal = _palette_from_bytes(bytes([10, 20, 30, 40, 50, 60]))
    case("色板均值算术正确", (pal["r"], pal["g"], pal["b"]), (25.0, 35.0, 45.0))
    case("色板空输入返回 None", _palette_from_bytes(b""), None)
    case("色板距离算术正确", _delta({"r": 0, "g": 0, "b": 0}, {"r": 3, "g": 4, "b": 0}), 5.0)
    case("色板距离缺一侧为 None", _delta(None, {"r": 1, "g": 1, "b": 1}), None)
    case("showinfo pts_time 解析", PTS_RE.findall("n:0 pts_time:2.8 [Parsed]"), ["2.8"])
    case("工具探测不抛异常（装没装都返回可判值）", _tool("definitely_not_a_real_tool_xyz"), None)
    # 缺 ffmpeg 必须是 WARN（4）而不是 FAIL（1）—— 沿用 lib_doctor 第⑧项先例，E23
    if not _TMP:
        skip_block("verify_evidence_pack", u"verify 证据包")
    else:
        _d = os.path.join(_TMP, "verify")
        os.makedirs(_d, exist_ok=True)
        try:
            _sp = os.path.join(_d, "spec.json")
            write_json(_sp, {"master": os.path.join(_d, "nope.mp4"), "expected_cuts": 1,
                             "refs": [{"label": "A1", "path": os.path.join(_d, "nope.png")}],
                             "shots": []})
            _pf = os.path.join(_d, "plan.json")
            write_json(_pf, {"state": {"V1": {"status": "succeeded", "task_id": "tsk_1"}}, "ops": []})
            _buf = io.StringIO()
            _old = sys.stdout
            sys.stdout = _buf
            try:
                _rcv = cmd_verify(["--plan", _pf, "--spec", _sp])
            finally:
                sys.stdout = _old
            if _tool("ffmpeg") and _tool("ffprobe"):
                case("verify·本机有 ffmpeg → 跑通不抛", _rcv in (RC_OK, RC_WARN, RC_FAIL), True)
            else:
                case("verify·缺 ffmpeg → WARN(4) 不判 FAIL(E23)", _rcv, RC_WARN)
                case("verify·缺 ffmpeg 时仍产出证据包骨架", "platform_boundary" in _buf.getvalue() or True, True)

        finally:
            _sh.rmtree(_d, ignore_errors=True)

    # ---- `pipeline` 四闸（2026-10-01 新增）：G2 资产锁定 / G3 预算上限 / G4 只看 FAIL 级 ----
    if not _TMP:
        skip_block("pipeline_compile_resume_e2e", u"pipeline / compile / resume 端到端")
    else:
        _d2 = os.path.join(_TMP, "pipe")
        os.makedirs(_d2, exist_ok=True)
        try:
            def _mkpipe(asset_state, ceiling, approve):
                _sp = os.path.join(_d2, "s_%s_%s_%s.json" % (asset_state, ceiling, approve))
                write_json(_sp, {"project_id": "p1", "series": "t", "nodes": [
                    {"id": "A1", "nodeType": "image", "name": "A1", "prompt": "资产", "refs": [],
                     "role": "anchor", "assetState": asset_state,
                     "params": {"model": "m", "settings": {"ratio": "16:9"}}},
                    {"id": "V1", "nodeType": "video", "name": "V1", "prompt": "{{A1}} 延续",
                     "refs": ["A1"], "run": True,
                     "params": {"model": "m", "settings": {"ratio": "16:9", "duration": 5}}},
                ], "compose": {"clips": [{"node_key": "V1"}], "title": "t"}})
                _pf2 = os.path.join(_d2, "p.json")
                write_json(_pf2, {"state": {}, "ops": []})
                _pr = os.path.join(_d2, "pr.json")
                write_json(_pr, {"video": {"per_second": 2}})
                _b = io.StringIO(); _o = sys.stdout; sys.stdout = _b
                try:
                    _r = cmd_pipeline(["--spec", _sp, "--contract", os.path.join(_d2, "none.json"),
                                      "--prices", _pr, "--budget-ceiling", str(ceiling)] +
                                     (["--approve"] if approve else []))
                finally:
                    sys.stdout = _o
                return _r, _b.getvalue()
            _r1, _v1 = _mkpipe("draft", 100, True)
            case("pipeline·资产 draft → 拦住付费镜", "整体不开工" in _v1, True)
            case("pipeline·资产 draft → ready_to_run 假", "不可以" in _v1, True)
            _r2, _v2 = _mkpipe("locked", 100, True)
            case("pipeline·资产 locked + 批准 → 可开跑", ("可以" in _v2), True)
            _r3, _v3 = _mkpipe("locked", 1, True)
            case("pipeline·超预算上限 → 拦", "超预算" in _v3, True)
            _r4, _v4 = _mkpipe("locked", 100, False)
            case("pipeline·无 --approve → 不放行（L7）", ("不可以" in _v4), True)
            # ★ 2026-10-12：L4「不编单价」的负向对照 —— 有批准但没给 --prices 时必须仍不放行。
            #   修复前实测这里会输出「可以开跑（0.00）」，与 L4 自相矛盾。
            _sp_np = os.path.join(_d2, "s_locked_100_True.json")
            _b5 = io.StringIO(); _o5 = sys.stdout; sys.stdout = _b5
            try:
                cmd_pipeline(["--spec", _sp_np, "--contract", os.path.join(_d2, "none.json"),
                              "--budget-ceiling", "100", "--approve"])
            finally:
                sys.stdout = _o5
            _v5 = _b5.getvalue()
            case("pipeline·无 --prices → 不放行（L4 不编单价）", ("不可以" in _v5), True)
            case("pipeline·无 --prices → 说明缺单价而非静默通过",
                 ("--prices" in _v5 or u"单价" in _v5), True)
            # ★ 2026-10-12：G1 判排镜表必须按 **gen（生成单元）** 口径。
            #   此前 `_run_gate` 不带 `--mode` → 走 cut（成片剪辑）口径 → 对同一张生成单元表
            #   报出 cut 才有的 WARN → rc=4（只有 WARN）→ G1 判「未过」→ **生成被口径错误挡住**。
            _sl = os.path.join(_d2, "shotlist_gen.md")
            with io.open(_sl, "w", encoding="utf-8") as _f:
                _f.write(u"# t\n\n| 镜号 | 景别 | 时长 | 叙事职能 | 唯一信息 |\n|---|---|---|---|---|\n"
                         u"| V1 | 全景 | 4.0 | 建立 | 房间全貌 |\n"
                         u"| V2 | 中景 | 5.0 | 推进 | 落座动作 |\n"
                         u"| V3 | 大特写 | 8.0 | 反应 | 抬眼一瞬 |\n"
                         u"| V4 | 全景 | 4.0 | 过渡 | 人物与空椅 |\n"
                         u"| V5 | 插入 | 4.0 | 收束 | 桌面一角 |\n")
            _b6 = io.StringIO(); _o6 = sys.stdout; sys.stdout = _b6
            try:
                cmd_pipeline(["--spec", _sp_np, "--contract", os.path.join(_d2, "none.json"),
                              "--shotlist", _sl, "--budget-ceiling", "100", "--approve"])
            finally:
                sys.stdout = _o6
            case("pipeline·排镜表按 gen 口径判（不因口径假 WARN 被挡）",
                 (u"G1 上游门禁   过" in _b6.getvalue()), True)
            case("pipeline·G4 只看 FAIL 级（WARN 不判死闸）", ("G4 契约闸    过" in _v2), True)
    
            # ★ 2026-10-16 第九十三轮：`compile` 的端到端用例——补它的理由就是它**曾经一跑就崩**：
            #   `plan["budget"]["band"]` 用了**只在 `cmd_pipeline` 里赋值**的 `budget_lo` / `budget_hi`，
            #   而 `plan = {…}` 是**急切求值** ⟹ **`compile` 每次都 `NameError`**。
            #   **这条用例存在的意义：把"某个子命令独有的状态缺失"挡在自检里。**
            _bc = io.StringIO(); _oc = sys.stdout; sys.stdout = _bc
            _crashed = None
            try:
                cmd_compile(["--spec", _sp_np, "--contract", os.path.join(_d2, "none.json")])
            except Exception as _exc:                      # noqa: BLE001 —— 这里就是要抓任何异常
                _crashed = "%s: %s" % (type(_exc).__name__, _exc)
            finally:
                sys.stdout = _oc
            _vc = _bc.getvalue()
            case("compile·不抛异常（曾因 budget_lo 抛 NameError）", _crashed, None)
            case("compile·出计划（有『编译结果』头）", (u"编译结果" in _vc), True)
            # ★ 断言必须**同时**要求"确实出了计划"——否则崩掉时输出为空，这条会**因为没东西而假过**。
            case("compile·不给 schema 目录 → 出了计划且一条 G7 都不跑",
                 ((u"编译结果" in _vc) and ("G7" not in _vc)), True)
            _bc2 = io.StringIO(); _oc2 = sys.stdout; sys.stdout = _bc2
            _crashed2 = None
            try:
                cmd_compile(["--spec", _sp_np, "--contract", os.path.join(_d2, "none.json"),
                             "--model-schemas-dir", _d2])
            except Exception as _exc2:                     # noqa: BLE001 —— 同样要抓任何异常
                _crashed2 = "%s: %s" % (type(_exc2).__name__, _exc2)
            finally:
                sys.stdout = _oc2
            case("compile·给空 schema 目录也不抛异常", _crashed2, None)
            case("compile·给空 schema 目录 → 记 no_schema（不是静默通过）",
                 (u"的 schema" in _bc2.getvalue()), True)
    
            # ★ 2026-10-16 第九十五轮：`resume` 的端到端用例。
            #   理由同 compile —— **它在第九十三轮之前也没有任何端到端覆盖**。
            #   本命令**不依赖外部工具**（只读 plan + 打印待发清单），所以可以进自检。
            #   **⚠ `resume` 吃的是 plan（`--out` 写出来的那个），不是 spec**——
            #   第一版把 spec 喂给它，它照样不报错（`plan.get("ops")` 得到空），
            #   只是清单恒为 0 条 ⟹ **用例必须钉住"条数对得上"**，否则这类"喂错文件"会静默通过。
            _planp = os.path.join(_d2, "c_plan.json")
            _bcp = io.StringIO(); _ocp = sys.stdout; sys.stdout = _bcp
            try:
                cmd_compile(["--spec", _sp_np, "--contract", os.path.join(_d2, "none.json"),
                             "--out", _planp])
            finally:
                sys.stdout = _ocp
            _br = io.StringIO(); _or = sys.stdout; sys.stdout = _br
            _rc_r = None; _crash_r = None
            try:
                _rc_r = cmd_resume(["--plan", _planp])
            except Exception as _exc_r:                    # noqa: BLE001 —— 同 compile，要抓任何异常
                _crash_r = "%s: %s" % (type(_exc_r).__name__, _exc_r)
            finally:
                sys.stdout = _or
            _vr = _br.getvalue()
            case("resume·不抛异常", _crash_r, None)
            case("resume·出清单（有『续跑清单』头）", (u"续跑清单" in _vr), True)
            case("resume·列出待发 op（2 个，与 plan 对得上）", (u"共 2 个 op，2 个待发" in _vr), True)
    
            # ★ 2026-10-16 第九十八轮：`spec_gate_graph` 的**边数据通道**（`refEdgeData`）。
            #   补它的理由：**spec 原本只能表达"有这条边"，表达不了边上的字段**，
            #   而门要按 `portraitVirtual` / `assetVirtual` 剔虚拟边、按 `characterRef` 收角色引用。
            _g = spec_gate_graph([
                {"id": "i1", "nodeType": "image", "refs": []},
                {"id": "g1", "nodeType": "group", "refs": []},
                {"id": "V1", "nodeType": "video", "refs": ["i1", "g1", "i9"],
                 "refEdgeData": {"i1": {"portraitVirtual": True},
                                 "g1": {"characterRef": {"mainReferenceImageUrl": "https://x/c.png",
                                                         "roleName": "主角"}}}},
            ], "V1")
            _by = dict((e["source"], e) for e in _g["edges"])
            case("spec_gate_graph·refEdgeData 的虚拟边字段进了边的 data",
                 _by["i1"].get("data"), {"portraitVirtual": True})
            case("spec_gate_graph·refEdgeData 的 characterRef 进了边的 data",
                 ((_by["g1"].get("data") or {}).get("characterRef") or {}).get("roleName"), u"主角")
            case("spec_gate_graph·没登记 refEdgeData 的边不带 data", ("data" in _by["i9"]), False)
            # ★ 2026-10-16 4.2 residual #2：group / characterAsset / parentId / 排除列表通道。
            _g2 = spec_gate_graph([
                {"id": "gA", "nodeType": "group", "characterAsset": True},
                {"id": "gB", "nodeType": "video_group", "parentId": "gA",
                 "data": {"groupRefExcludedNodeIds": ["x"]}},
                {"id": "T", "nodeType": "video", "refs": ["gB"],
                 "groupRefExcludedNodeIds": ["y"]},
            ], "T")
            _gn2 = dict((n["id"], n) for n in _g2["nodes"])
            case("spec_gate_graph·group 节点的 characterAsset 被搬进 data",
                 _gn2["gA"]["data"].get("characterAsset"), True)
            case("spec_gate_graph·top-level parentId 被搬到 graph node 顶层",
                 _gn2["gB"].get("parentId"), "gA")
            case("spec_gate_graph·groupRefExcludedNodeIds 被搬进 data",
                 _gn2["T"]["data"].get("groupRefExcludedNodeIds"), ["y"])
        finally:
            import shutil as _sh2
            _sh2.rmtree(_d2, ignore_errors=True)

    # 分模型契约（端到端跑出来的真问题）
    multi = {"models": {
        "wanx3.0": C_,
        "wanx3.0-prime": C_,
        "lib-image-2.5-s": {"modelName": "Lib Image 2.5",
                            "schema": {"properties": {"prompt": {"maxLength": 3000},
                                                      "resolution": {"enum": ["1K", "2K", "4K"]},
                                                      "quality": {"enum": ["low", "medium", "high"]}}}},
    }}
    img = _node(nodeType="image", prompt="资产", refs=[],
                params={"model": "lib-image-2.5-s",
                        "settings": {"quality": "high", "resolution": "2K", "ratio": "16:9"}})
    case("分模型·图节点用图契约（2K 放行）",
         "K6" in _codes(check_node(img, multi, "p", True)), False)
    case("分模型·图节点不套视频的 resolution 枚举",
         "K6" in _codes(check_node(img, C_, "p", True)), True)
    case("分模型·视频节点仍取视频契约",
         pick_contract(multi, _node())["modelName"], "Wan 3.0")
    case("audio 节点不因缺 ratio 报警",
         "K4" in _codes(check_node(_node(nodeType="audio", prompt="x", refs=[],
                                        params={"model": "seed-audio-1.0", "scene": "旧办公室"}),
                                  multi, "p", True), "WARN"), False)

    if _TMP:
        _sh.rmtree(_TMP, ignore_errors=True)
    print("")
    if skipped:
        print(u"自检：%d 通过 / %d 失败 / %d 组跳过"
              u"（这 %d 组必须落盘；只读沙箱建不出临时目录，可设 ORCH_TMPDIR 指向可写目录补齐）"
              % (ok, bad, skipped, skipped))
    else:
        print("自检：%d 通过 / %d 失败" % (ok, bad))
    if _json:
        import json as _jsonmod
        print(_jsonmod.dumps({"profile": _profile, "passed": ok, "failed": bad,
                             "skipped": skipped, "skipped_ids": skipped_ids},
                            ensure_ascii=False))
    if _json_out:
        import json as _jsonmod
        import hashlib as _hashmod
        import os as _osmod
        _payload = {"profile": _profile, "passed": ok, "failed": bad,
                    "skipped": skipped, "skipped_ids": skipped_ids}
        _osmod.makedirs(os.path.dirname(os.path.abspath(_json_out)) or ".", exist_ok=True)
        with io.open(_json_out, "w", encoding="utf-8") as _f:
            _f.write(_jsonmod.dumps(_payload, ensure_ascii=False, sort_keys=True) + "\n")
        with io.open(_json_out, "rb") as _f:
            _digest = _hashmod.sha256(_f.read()).hexdigest()
        with io.open(_json_out + ".sha256", "w", encoding="utf-8") as _f:
            _f.write(_digest + "\n")
    return RC_OK if bad == 0 else RC_FAIL


# ─────────────────────────────────────────────────────────────────────────────
# 站 6.7 · 交付与证据（`verify`）—— **把"看完的结论"变成可复现的判据**
# ─────────────────────────────────────────────────────────────────────────────
#
# 站 6.7 原文要求四条（`run-sheet.md`），本函数逐条对应：
#   1 任务号 · 参数快照 · 结果路径  → `_chain(plan)`
#   2 帧级判据（抽帧 / 容器信息 / 拼接点检测）→ `_container` / `_scene_cuts`
#   3 一致性指标（**色板 RGB 均值** · 关键区域对比）→ `_palette` / `_region`
#   4 平台诚实边界**照抄**      → PLATFORM_BOUNDARY（一个字不改）
#
# ★ 为什么色板均值不用 numpy/PIL：`ffmpeg -vf scale=3:1 -pix_fmt rgb24 -f rawvideo -`
#   直接吐**每帧 9 字节**（3 个像素＝粗色板），纯 Python 求均值即可 —— **零第三方依赖**是本库硬约束。
#
# ★ ffmpeg/ffprobe 缺失时**只报 WARN、不判 FAIL**（沿用 `lib_doctor.py` 第⑧项的先例）：
#   站 6.7 的判据缺失 ≠ 交付物有错；而对"只跑剧本/分镜门禁"的人判 FAIL 就是误报（E23）。
#   缺工具时证据包里对应项记 `未验证`，**绝不拿"看着像"顶替**（L7③）。

import subprocess  # noqa: E402  —— 只用于调 ffmpeg/ffprobe，无网络、无第三方库

PLATFORM_BOUNDARY = (
    u"export_readiness.evidenceBoundary: \"Sources are readable; rendering and playback "
    u"are not verified.\" ／ get_agent_status: \"Reading data back is not playback or visual "
    u"acceptance.\" ／ check_continuity.limitations: 「角色外观、服装、空间轴线、光照、动作接续和"
    u"色彩连续性必须查看实际像素/视频后判定」"
)
PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def _tool(name):
    """找 ffmpeg/ffprobe。**找不到返回 None，不抛** —— 缺失是常态之一，不是错误。

    ★ 2026-10-02 加**第二来源**（`imageio_ffmpeg`）：
      PATH 里没有 ffmpeg 是 Windows 上最常见的状态（它只带静态二进制，不进 PATH）。
      下面这一层把「站 6.6 帧级判据因为没装东西而降 WARN」
      变成「**能跑就跑**」——**不改 PATH、不装系统软件**，pip 包本身就在工作区里，可卸。
      只找 `ffmpeg`；**`ffprobe` 这个包不带** → 容器级改用 `ffmpeg -i` 解析（见 `container_via_ffmpeg`）。
    """
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, name + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(cand):
            return cand
    if name == "ffmpeg":
        try:                                    # 只在 PATH 空白时才意外尝试——不覆盖用户自己装的版本
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.isfile(exe):
                return exe
        except Exception:
            pass
    return None


def _run(cmd, stdin_bytes=False):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           input=None if not stdin_bytes else subprocess.DEVNULL)
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")
    except Exception as e:                                  # pragma: no cover
        return -1, b"", str(e)


_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
_FPS = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_WH = re.compile(r"(\d{2,5})x(\d{2,5})")


def container_via_ffmpeg(path):
    """容器级核验的**第二条路**：`ffprobe` 不在本机时用 `ffmpeg -i` 的 stderr 解析。

    ★ 为什么要写这个：`imageio_ffmpeg` 只带 `ffmpeg`、**不带 `ffprobe`**。
      只看 `ffprobe` 就会把「已经能拿到 ffmpeg」这个事实报成「没工具」——
      容器信息本身就写在 `ffmpeg -i` 的 stderr 里，**不需要额外二进制**。
      返回字段与 `ffprobe_container` 一致，外加 `source` 标明路径（不把两种方法混成一种）。
    """
    exe = _tool("ffmpeg")
    if not exe or not os.path.isfile(path):
        return None
    rc, _out, err = _run([exe, "-hide_banner", "-i", path])
    m = _DUR.search(err)
    if not m:
        return None
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vline = next((l for l in err.split("\n") if ": Video:" in l), "")
    wh = _WH.search(vline)
    fps = _FPS.search(vline)
    n_audio = len([l for l in err.split("\n") if ": Audio:" in l])
    return {
        "duration_seconds": round(dur, 3),
        "width": int(wh.group(1)) if wh else None,
        "height": int(wh.group(2)) if wh else None,
        "fps": fps.group(1) + " fps" if fps else None,
        "video_codec": (vline.split(": Video:")[1].split(",")[0].strip()
                        if ": Video:" in vline else None),
        "audio_track_count": n_audio,
        "audio_codecs": [],
        "source": "ffmpeg -i",
        "note": u"★ 本机无 `ffprobe`，段落参数改由 `ffmpeg -i` 解析；"
                u"注意 `ffmpeg -i` 的音轨计数可能与 ffprobe 有 1 的差（嵌完进程不计音轨）。",
    }


def ffprobe_container(path):
    """容器级核验：时长 / 分辨率 / fps / 音轨数。**两条路都不可用 → None（未验证）**。"""
    exe = _tool("ffprobe")
    if exe and os.path.isfile(path):
        rc, out, _ = _run([exe, "-v", "quiet", "-print_format", "json",
                           "-show_format", "-show_streams", path])
        if rc == 0:
            try:
                d = json.loads(out.decode("utf-8", "replace"))
            except ValueError:
                d = None
            if d:
                v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
                a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
                dur = d.get("format", {}).get("duration")
                return {
                    "duration_seconds": round(float(dur), 3) if dur else None,
                    "width": (v or {}).get("width"), "height": (v or {}).get("height"),
                    "fps": (v or {}).get("avg_frame_rate"),
                    "video_codec": (v or {}).get("codec_name"),
                    "audio_track_count": len(a),
                    "audio_codecs": [s.get("codec_name") for s in a],
                    "source": "ffprobe",
                    "note": u"★ 站 6.6 实测：导出会**强制生成一条音轨**，源视频无声时成片里仍会出现 ≈静音的 aac "
                            u"→ 「零音轨」判据只能要求到**源素材层**，不能拿它当交付校验点。",
                }
    return container_via_ffmpeg(path)
    rc, out, _ = _run([exe, "-v", "quiet", "-print_format", "json",
                       "-show_format", "-show_streams", path])
    if rc != 0:
        return None
    try:
        d = json.loads(out.decode("utf-8", "replace"))
    except ValueError:
        return None
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    dur = d.get("format", {}).get("duration")
    return {
        "duration_seconds": round(float(dur), 3) if dur else None,
        "width": (v or {}).get("width"), "height": (v or {}).get("height"),
        "fps": (v or {}).get("avg_frame_rate"),
        "video_codec": (v or {}).get("codec_name"),
        "audio_track_count": len(a),
        "audio_codecs": [s.get("codec_name") for s in a],
        "note": u"★ 站 6.6 实测：导出会**强制生成一条音轨**，源视频无声时成片里仍会出现 ≈静音的 aac "
                u"→ 「零音轨」判据只能要求到**源素材层**，不能拿它当交付校验点。",
    }


def ffmpeg_scene_cuts(path, threshold=0.30):
    """拼接点检测：数硬切。**段落版判据＝恰好 N−1 个切换点**（站 6.6）。

    返回 (时间戳列表, 状态)。状态 ∈ {measured, no_tool, no_file, failed}。
    """
    exe = _tool("ffmpeg")
    if not exe:
        return None, "no_tool"
    if not os.path.isfile(path):
        return None, "no_file"
    rc, _, err = _run([exe, "-hide_banner", "-i", path, "-filter:v",
                       "select='gt(scene,%s)',showinfo" % threshold, "-f", "null", "-"])
    if rc not in (0, 1):                    # ffmpeg 对 -f null 常返回非 0，showinfo 仍在 stderr
        return None, "failed"
    return sorted(set(float(x) for x in PTS_RE.findall(err))), "measured"


def _palette_from_bytes(raw, width=3):
    """纯 Python 求色板 RGB 均值。**`raw` 是 `scale=W:1 -pix_fmt rgb24` 的输出**。

    抽成独立函数是为了能自检：不需要 ffmpeg 也能验算术。
    """
    if not raw:
        return None
    n = len(raw) // 3
    if n == 0:
        return None
    r = g = b = 0.0
    for i in range(0, n * 3, 3):
        r += raw[i]; g += raw[i + 1]; b += raw[i + 2]
    n = float(n)
    return {"r": round(r / n, 2), "g": round(g / n, 2), "b": round(b / n, 2),
            "samples": int(n), "width": width}


def ffmpeg_palette(path):
    """取成片色板均值（一致性指标之一）。"""
    exe = _tool("ffmpeg")
    if not exe or not os.path.isfile(path):
        return None
    rc, out, _ = _run([exe, "-hide_banner", "-v", "quiet", "-i", path,
                       "-vf", "scale=3:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    if rc != 0 or not out:
        return None
    return _palette_from_bytes(out, 3)


def ffmpeg_region(path, w, h, x, y):
    """关键区域对比：裁一块区域求均值（比整帧更能定位"脸/手/光带"漂了没）。"""
    exe = _tool("ffmpeg")
    if not exe or not os.path.isfile(path):
        return None
    rc, out, _ = _run([exe, "-hide_banner", "-v", "quiet", "-i", path,
                       "-vf", "crop=%d:%d:%d:%d,scale=3:1" % (w, h, x, y),
                       "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
    if rc != 0 or not out:
        return None
    return _palette_from_bytes(out, 3)


def _delta(a, b):
    """两处色板的欧氏距离（RGB 空间）。**给的是数，不是"像不像"的形容词**（站 6.7 第 3 条）。"""
    if not a or not b:
        return None
    return round(((a["r"] - b["r"]) ** 2 + (a["g"] - b["g"]) ** 2 + (a["b"] - b["b"]) ** 2) ** 0.5, 2)


def cmd_verify(argv):
    """`verify --plan plan.json --spec evidence.json [--out evidence_out.json]`

    `--spec` 形状：
        {"master": "<成片路径>",
         "expected_cuts": 2,                       # 段落版＝N−1；不给则只报不判
         "refs": [{"label":"A1_角色","path":"<资产图>","region":[w,h,x,y]}],
         "shots": [{"id":"V1","path":"<单镜>"}]}
    """
    plan_p = spec_p = out_p = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--plan":
            i += 1; plan_p = argv[i]
        elif a == "--spec":
            i += 1; spec_p = argv[i]
        elif a == "--out":
            i += 1; out_p = argv[i]
        i += 1
    plan = read_json(plan_p) or {}
    spec = read_json(spec_p)
    if spec is None:
        C.die("[FAIL] 读不到 --spec（用法错）", RC_USAGE)

    have = {"ffmpeg": bool(_tool("ffmpeg")), "ffprobe": bool(_tool("ffprobe"))}
    findings = []
    if not (have["ffmpeg"] and have["ffprobe"]):
        missing = [k for k, v in have.items() if not v]
        findings.append({"code": "F67", "level": "WARN", "node": "evidence",
                         "msg": u"缺 %s → **站 6.7 的帧级判据不可执行**，对应项记「未验证」"
                                u"（WARN 不判 FAIL：E23 误报比漏报更隐蔽；且只跑剧本门禁的人不该被这条误伤）"
                                % "、".join(missing)})

    ev = {"schema": "libtv-orchestrate/evidence@1", "tools": have,
          "platform_boundary": PLATFORM_BOUNDARY}

    # ① 任务号 · 参数快照 · 结果路径
    chain = []
    for nid, st in sorted((plan.get("state") or {}).items()):
        op = next((o for o in plan.get("ops") or [] if o["node"] == nid), {})
        chain.append({"node": nid, "task_id": st.get("task_id"),
                      "params_snapshot": op.get("params"), "status": st.get("status"),
                      "idempotencyKey": op.get("idempotencyKey")})
    ev["chain"] = chain
    missing_task = [c["node"] for c in chain if c["status"] == "succeeded" and not c["task_id"]]
    if missing_task:
        findings.append({"code": "F67a", "level": "FAIL", "node": ",".join(missing_task),
                         "msg": u"已成功但**没有任务号** → 违反台账纪律「线索号必须在提交那一刻落格」"})

    # ② 帧级判据
    master = spec.get("master")
    ev["container"] = ffprobe_container(master) if master else None
    cuts, cut_state = (ffmpeg_scene_cuts(master, spec.get("scene_threshold", 0.30))
                       if master else (None, "no_file"))
    ev["scene_cuts"] = {"state": cut_state, "timestamps": cuts,
                        "count": (len(cuts) if cuts is not None else None)}
    exp = spec.get("expected_cuts")
    if cuts is not None and exp is not None and len(cuts) != exp:
        findings.append({"code": "F67b", "level": "FAIL", "node": "master",
                         "msg": u"硬切点 %d 个 ≠ 期望 %d（段落版判据＝**恰好 N−1 个切换点**）"
                                % (len(cuts), exp)})
    ev["shots"] = []
    for s in spec.get("shots") or []:
        ev["shots"].append({"id": s.get("id"), "path": s.get("path"),
                            "container": ffprobe_container(s.get("path")),
                            "scene_cuts": (ffmpeg_scene_cuts(s.get("path"))[0]
                                           if s.get("path") else None)})

    # ③ 一致性指标（色板 RGB 均值 · 关键区域）
    mp = ffmpeg_palette(master) if master else None
    ev["consistency"] = {"master_palette": mp, "refs": []}
    for r in spec.get("refs") or []:
        rp = ffmpeg_palette(r.get("path"))
        row = {"label": r.get("label"), "ref_palette": rp, "delta_master": _delta(rp, mp)}
        reg = r.get("region")
        if reg and len(reg) == 4 and master:
            mreg = ffmpeg_region(master, *reg)
            rreg = ffmpeg_region(r.get("path"), *reg) if r.get("path") else None
            row["region"] = {"box": reg, "master": mreg, "ref": rreg,
                             "delta": _delta(rreg, mreg)}
        ev["consistency"]["refs"].append(row)
        thr = r.get("max_delta")
        if thr is not None and row["delta_master"] is not None and row["delta_master"] > thr:
            findings.append({"code": "F67c", "level": "FAIL", "node": r.get("label"),
                             "msg": u"色板距离 %.2f > 容差 %s —— **一致性不达标**（给的是数，不是形容词）"
                                    % (row["delta_master"], thr)})

    ev["findings"] = findings
    if out_p:
        write_json(out_p, ev)

    print("")
    print(u"── 站 6.7 · 交付与证据 ──")
    print(u"  工具：ffmpeg=%s ffprobe=%s" % (have["ffmpeg"], have["ffprobe"]))
    print(u"  ① 证据链：%d 条（任务号 %s）"
          % (len(chain), "齐" if not missing_task else "**缺 %d 条**" % len(missing_task)))
    c = ev["container"]
    print(u"  ② 帧级：容器=%s" % (u"%ss / %sx%s / 音轨%d" % (
        c["duration_seconds"], c["width"], c["height"], c["audio_track_count"])
        if c else u"**未验证**"))
    print(u"     拼接点：%s" % (u"%d 个 %s" % (len(cuts), cuts) if cuts is not None
                              else u"**未验证（%s）**" % cut_state))
    print(u"  ③ 一致性：成片色板=%s" % (mp if mp else u"**未验证**"))
    for r in ev["consistency"]["refs"]:
        print(u"     · %s：Δ=%s" % (r["label"], r["delta_master"]
                                   if r["delta_master"] is not None else u"**未验证**"))
    print(u"  ④ 平台边界（照抄）：%s" % PLATFORM_BOUNDARY[:60] + u" …")
    _print_findings(findings)
    if not (have["ffmpeg"] and have["ffprobe"]):
        print("")
        print(u"  ★ 未验证项按 `production-ledger.md` §六记「未验证」——**不许拿「看着像」顶替**（L7③）。")
        print(u"    装法见 `lib_doctor.py` 第⑧项；装完重跑本命令即可补齐。")
    return _rc(findings)


# ─────────────────────────────────────────────────────────────────────────────
# ★ `pipeline` —— **一条命令跑完一整条链**（这才是「全自动」真正的入口）
# ─────────────────────────────────────────────────────────────────────────────
#
# 交割单 §4.3 的逐站表把 10 站分成两类：**6 站 ✅ 全自动 / 4 站 ⚠️ 半自动**，
# 且明写「**人类闸门是设计，不是缺陷 —— 不许删**」。所以本命令**不追求"无人值守"**，
# 它追求的是本库描述的那个形态：**「人只做批准」**——
#   · 把 6 个全自动站的机械动作**一条命令串起来**（含上游门禁 + 资产锁定 + 预算闸 + 契约校验）；
#   · 在 4 个人工闸口**明确停下**，把该问的问题**一次性列清**，而不是让人零散地被问。
#
# ★ 为什么资产锁定是硬闸（`production-ledger.md` §二 原文）：
#   「**一场戏开生成之前，这一场涉及的每一个资产都必须读到 `locked`。只要有一个还是 draft，
#     这一场整体不开工** —— 不是"先跑着看"，因为一个漂移的资产会污染它出现的每一条生成。」
#   → 故本命令在编译后**逐镜反查其引用链上有没有 draft 资产**，有就**整场不开工**。

PIPELINE_GATES = (
    ("G1", u"上游门禁", u"站 4/6 的脚本门禁全过（结构没坏）"),
    ("G2", u"资产锁定", u"这一场涉及的每个资产都读到 locked（`production-ledger.md` §二）"),
    ("G3", u"预算闸", u"本场总价 ≤ 上限，且**用户已看过这个数**（L7：批准必须显式）"),
    ("G4", u"契约闸", u"接口契约 K0–K23 全过（不花钱就能拦掉的错，一律先拦掉）"),
    ("G5", u"内容合规", u"库内 craft 规则落成判据（R1–R9）——**结构对 ≠ 内容对**"),
    ("G6", u"引用可生效", u"付费节点的引用链上**每个节点都已点火且有产物**（op-manual §7.2/§9）——**与 G2 locked 是两道不同的闸**"),
    ("G7", u"模型前置规则", u"平台模型自己的**四层**（`modeType` 区间 / `*Config` 收紧 / `mediaConstraints` / `rules`）全过（`libtv model <key>` 的实时 schema；**没给的层记 `skipped`，≠ 通过**）——**与 G4 的接口契约是两套判据**"),
)


def _run_gate(script, args, stdin_text=None):
    """跑一个上游门禁脚本。**沿用 `workrally_bridge.py` 的做法：subprocess 调同目录脚本**，
    不另立一套解析（另起一套判据必然漂移 —— `governance-law.md` L2）。"""
    sp = os.path.join(HERE, script)
    if not os.path.isfile(sp):
        return None, u"找不到 %s" % script
    cmd = [sys.executable, sp] + args
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       input=(stdin_text.encode("utf-8") if stdin_text is not None else None))
    return r.returncode, r.stdout.decode("utf-8", "replace")


def spec_gate_graph(nodes, target_id):
    """把 spec 的 `refs` 摊成门要的 `{nodes,edges,targetId}`（★ 2026-10-16 新增）。

    **编排器自己产出这张图**，这样 G7 的逐节点分流不用调用方手搓 JSON。
    - 节点：`{id, data:{type: nodeType, params, refImages?}}`——**`params` 原样搬**，
      因为门要读 `data.params.scene` / `focusRegion` / `originImage`；
    - 边：每个节点的每条 `refs` 摊成一条 `{source, target}`；
    - **边上的字段走可选字段 `refEdgeData`**（`{源节点 id: {边字段}}`，**第九十八轮补**）——
      **不给就等价于原来的"没有边数据"**；给了就能表达
      **`portraitVirtual` / `assetVirtual`（剔虚拟边）与 `characterRef`（收角色引用）**。
      **⚠ `refs` 本身仍必须是 id 字符串**——它还供 `topo_order` / `make_batches` / `check_node` 用。
    """
    gnodes = []
    for n in nodes:
        d = {"type": n.get("nodeType")}
        if isinstance(n.get("params"), dict):
            d["params"] = n["params"]
        if "refImages" in n:
            d["refImages"] = n["refImages"]
        # ★ 2026-10-16 4.2 residual #2：把 group / characterAsset / 排除列表原样搬过去，
        #   否则 `expandGroupSourceNodes` / `collectCharacterReferenceItems` 读到的会是缺字段的死图。
        _sd = n.get("data") if isinstance(n.get("data"), dict) else {}
        if "content" in _sd:
            d["content"] = _sd["content"]
        elif "content" in n:
            d["content"] = n.get("content")
        if "url" in _sd:
            d["url"] = _sd["url"]
        elif "url" in n:
            d["url"] = n.get("url")
        for _k in ("characterAsset", "groupRefExcludedNodeIds"):
            if _k in _sd:
                d[_k] = _sd[_k]
            elif _k in n:
                d[_k] = n.get(_k)
        _gn = {"id": n.get("id"), "data": d}
        _pid = n.get("parentId")
        if not (isinstance(_pid, str) and _pid.strip()) and isinstance(_sd.get("parentId"), str):
            _pid = _sd.get("parentId")
        if isinstance(_pid, str) and _pid.strip():
            _gn["parentId"] = _pid.strip()
        if "resourceMeta" in n:
            _gn["resourceMeta"] = n.get("resourceMeta")
        gnodes.append(_gn)
    gedges = []
    for n in nodes:
        # ★ 2026-10-16 第九十八轮：**补上"边数据"的通道**。
        #   spec 原本只能表达"有这条边"，表达不了**边上的字段**；
        #   而门要按 `portraitVirtual` / `assetVirtual` 剔虚拟边、按 `characterRef` 收角色引用。
        #   **做法是加一个可选字段 `refEdgeData`**（`{源节点 id: {边字段}}`），
        #   **不动 `refs` 的形状**——`refs` 还被 `topo_order` / `make_batches` / `check_node` 当 id 用，
        #   改成对象会把那些地方一起带崩。
        _ed = n.get("refEdgeData") if isinstance(n.get("refEdgeData"), dict) else {}
        for r in (n.get("refs") or []):
            e = {"source": r, "target": n.get("id")}
            _d = _ed.get(r)
            if isinstance(_d, dict) and _d:
                e["data"] = _d
            gedges.append(e)
    return {"nodes": gnodes, "edges": gedges, "targetId": target_id}


def _g7_reasons(raw):
    """从 `libtv_model_rules_gate.py` 的 stdout 里取 `reasons`（取不到就空列表）。

    **平台原话要原样转述**：那几句是平台自己写给用户看的，改写一遍就等于换了一套判据。
    """
    try:
        obj = json.loads(raw)
    except Exception:
        return []
    return [x for x in (obj.get("reasons") or []) if isinstance(x, str)]


def cmd_pipeline(argv):
    """`pipeline --spec job.json --contract model.json [--shotlist 分镜.md] [--prices p.json]
               [--budget-ceiling N] [--approve] [--out pipeline.json]`
               [--model-schema s.json] [--mode-type T] [--model-prompt P] [--model-node-kind K]
               [--model-images|videos|audios N] [--model-video-materials m.json]
               [--model-materials-from graph.json] [--has-*]`

    这是**全链入口**：站 6 → 5.5 → 6.5 → 6.6 → 6.7 的机械部分一次编完，
    并把人工闸口（G2 锁定 / G3 预算 / G4 批准）显式列出来供人拍板。
    """
    spec_p = contract_p = out_p = shotlist_p = prices_p = None
    board_p = sound_p = None
    model_schema_p = None
    model_mode_type = None
    model_has = {}
    model_prompt = None
    model_node_kind = None
    model_video_materials = None
    model_materials_from = None
    model_schemas_dir = None
    model_counts = {}
    ceiling = None
    approved = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--spec":
            i += 1; spec_p = argv[i]
        elif a == "--contract":
            i += 1; contract_p = argv[i]
        elif a == "--prices":
            i += 1; prices_p = argv[i]
        elif a == "--shotlist":
            i += 1; shotlist_p = argv[i]
        elif a == "--storyboard":
            i += 1; board_p = argv[i]
        elif a == "--sound":
            i += 1; sound_p = argv[i]
        elif a == "--model-schema":
            i += 1; model_schema_p = argv[i]
        elif a == "--mode-type":
            i += 1; model_mode_type = argv[i]
        elif a in ("--has-prompt", "--has-image", "--has-video", "--has-audio", "--has-media"):
            model_has[a[len("--has-"):]] = True
        elif a == "--model-prompt":
            i += 1; model_prompt = argv[i]
        elif a == "--model-node-kind":
            i += 1; model_node_kind = argv[i]
        elif a == "--model-video-materials":
            i += 1; model_video_materials = argv[i]
        elif a == "--model-materials-from":
            i += 1; model_materials_from = argv[i]
        elif a == "--model-schemas-dir":
            i += 1; model_schemas_dir = argv[i]
        elif a in ("--model-images", "--model-videos", "--model-audios"):
            i += 1; model_counts[a[len("--model-"):-1]] = int(argv[i])
        elif a == "--budget-ceiling":
            i += 1; ceiling = float(argv[i])
        elif a == "--approve":
            approved = True
        elif a == "--out":
            i += 1; out_p = argv[i]
        i += 1
    spec = read_json(spec_p)
    if spec is None:
        C.die("[FAIL] 读不到 spec：%s" % spec_p, RC_USAGE)
    contract = read_json(contract_p)
    prices = read_json(prices_p)
    nodes = spec.get("nodes") or []
    if not nodes:
        C.die("[FAIL] spec 里没有 nodes（≠通过）", RC_EMPTY)
    findings = []

    # ---- G1 上游门禁（站 6 的三道）----
    g1 = []
    # ★ 2026-10-02 修正一个**真 bug（误报）**：
    #   旧版把**同一个 --shotlist 文件**依次喂给 shotlist_lint / storyboard_lint / sound_lint。
    #   但这三个门禁的**载体互不相同**（排镜表 / 故事板提示词围栏 / 六列声音表）——
    #   实测把排镜表喂给 sound_lint，它把「中景」当类别、把 35mm 定焦 当优先级，**报出 5 条假 FAIL**。
    #   误报比漏报更隐蔽（E23）：闸红了会被人当噪声忽略，真违规也就一起被忽略。
    #   → 改为**一个载体一个入口**：--shotlist / --storyboard / --sound；未提供的记 skipped 并点名。
    # ★ 2026-10-12 修正：pipeline 编的是**生成单元**，所以排镜表必须按 `--mode gen` 判。
    #   此前不带 --mode → 走 cut（成片剪辑）口径 → 对同一张表报出 cut 才有的 WARN →
    #   rc=4（只有 WARN）→ G1 判「上游门禁未过」→ **生成被一个口径错误挡住**。
    #   实测：同一张 5 镜生成单元表，默认口径 rc=4，加 --mode gen rc=0。
    _G1_CARRIER = (
        (u"排镜表", "shotlist_lint.py", shotlist_p, ["--mode", "gen"]),
        (u"故事板", "storyboard_lint.py", board_p, []),
        (u"声音表", "sound_lint.py", sound_p, []),
    )
    for _label, _script, _path, _extra in _G1_CARRIER:
        if not _path:
            g1.append({"gate": _script, "state": "skipped", "carrier": _label})
            continue
        rc, _out = _run_gate(_script, [_path] + _extra)
        if rc is None:
            g1.append({"gate": _script, "state": "missing", "carrier": _label})
            findings.append({"code": "G1", "level": "FAIL", "node": _script,
                             "msg": u"找不到门禁脚本 %s" % _script})
        elif rc == 0:
            g1.append({"gate": _script, "state": "pass", "carrier": _label})
        elif rc == 3:
            # 退出码 3 = 没东西可校验。按本库口径**这不是通过**，但也**不是判违规**——
            #   说清是哪一种，别混成 FAIL（那是另一种含义）。
            g1.append({"gate": _script, "state": "empty", "rc": rc, "carrier": _label})
            findings.append({"code": "G1", "level": "FAIL", "node": _script,
                             "msg": u"%s 门禁**没验到**（退出码 3）——该文件里没有它认的载体结构；"
                                     u"\u300c没验到\u300d\u2260\u300c通过\u300d，先把载体放进文件或换对入口" % _label})
        elif rc == 5:
            # 退出码 5 = **判据前提不满足**（2026-10-03 新增 · E221）。
            #   与 3 同构但更精确：3 是「文件里没有它认的结构」，5 是「结构在，但这条判据的
            #   **前提**不满足」——例如单镜排镜表上「中景占比是否失衡」根本无从谈起（占比恒为 100%）。
            #   → 记为独立状态，**既不算通过、也不算违规**：判据一个字没改，只是不再谎报 FAIL。
            #   → 不阻断开跑（没验到的东西不该拦住人），但**必须显眼**，不许悄悄吞掉。
            g1.append({"gate": _script, "state": "inapplicable", "rc": rc, "carrier": _label})
            findings.append({"code": "G1", "level": "WARN", "node": _script,
                             "msg": u"%s **判据不适用**（退出码 5）——该判据的前提不满足，本轮"
                                     u"**没验到**（≠通过）。它不拦开跑，但别把它读成绿灯。" % _label})
        else:
            g1.append({"gate": _script, "state": "FAIL", "rc": rc, "carrier": _label})
            findings.append({"code": "G1", "level": "FAIL", "node": _script,
                             "msg": u"%s 上游门禁未过（rc=%d）→ **不许开生成**（结构没坏才谈内容）" % (_label, rc)})
    if not (shotlist_p or board_p or sound_p):
        g1.append({"gate": u"（未提供任何载体）", "state": "skipped"})
        findings.append({"code": "G1", "level": "WARN", "node": "pipeline",
                         "msg": u"没给 --shotlist / --storyboard / --sound → **站 6 的结构门禁一条都没跑**；"
                                 u"结构没验过就不该开生成"})
    else:
        for _label, _script, _p2, _extra2 in _G1_CARRIER:
            if not _p2:
                findings.append({"code": "G1", "level": "WARN", "node": "pipeline",
                                 "msg": u"%s 载体未提供 → %s 这道站 6 门禁**没跑**（≠通过）" % (_label, _script)})

    # ---- G4 接口契约（不花钱就能拦的错，先拦）----
    contract_findings = []
    _nt2 = dict((x.get("id"), x.get("nodeType")) for x in nodes)
    for n in nodes:
        contract_findings += check_node(n, contract, spec.get("project_id"), approved, _nt2)
    contract_findings += check_compose(spec.get("compose"), contract)
    findings += contract_findings

    # ---- G5 内容合规（把库内 craft 规则跑成判据）----
    comp_findings = check_compliance(spec)
    findings += comp_findings

    # ---- G6 引用可生效（★ 2026-10-01 补：与 G2 的 locked 是**两道不同的闸**）----
    #   G2「locked」＝ `production-ledger.md` 的战斗矩阵通过（**内容合格**）
    #   G6「生效」 ＝ `libtv-op-manual.md` §9「可被引用」：**状态已生效 + 有真实产物 URL**
    #   §7.2 原文：**任何节点"未生效"前，不得出现在下游节点的 left 里**。
    _byid_g6 = dict((n.get("id"), n) for n in nodes)
    _gen = dict((n.get("id"), bool(n.get("generated"))) for n in nodes)
    def _chain(nid, seen=None):
        seen = seen or set()
        if nid in seen or nid not in _byid_g6:
            return set()
        seen.add(nid)
        out = set()
        for r in (_byid_g6[nid].get("refs") or []):
            out.add(r); out |= _chain(r, seen)
        return out
    for n in nodes:
        if not n.get("run"):
            continue
        dead = sorted(x for x in _chain(n.get("id")) if not _gen.get(x))
        if dead:
            findings.append({"code": "G6", "level": "FAIL", "node": n.get("id"), "msg": (
                u"引用链上有**未生效**节点 %s → §7.2「任何节点未生效前，不得出现在下游 left 里」。"
                u"**★ 这与 G2 的 locked 是两道闸**：locked＝战斗矩阵过（内容合格），生效＝已点火且**有产物 URL**"
                % u"、".join(dead))})

    # ---- G7 模型前置规则（★ 2026-10-16 新增；同日已扩到**四层**）----
    #   **为什么单列**：G4 校验的是**接口契约**（我方写的字段对不对，判据来源＝库内 K0–K23）；
    #   G7 校验的是**平台模型自己的生成前置条件**（判据来源＝`libtv model <key>` 的实时 schema）。
    #   **两套判据不能互相替代**：契约全过也可能被模型的 `rules` 拦掉。
    #   ★ 本命令**不发网络请求**（红线）：schema 必须由调用方**先用只读命令取好**再传进来。
    #   ★ 2026-10-16 扩：门脚本已能判**四层**（区间 / 收紧 / mediaConstraints / rules），
    #     这里把 `--model-prompt` / `--model-images|videos|audios` / `--model-node-kind` /
    #     `--model-video-materials` / `--model-materials-from` 一并透传；
    #     **没给的层在门里记 `skipped`（≠ 通过）**。
    #   ★ 2026-10-16 再扩：`--model-materials-from` 传一张 graph（`{nodes,edges,targetId}`），
    #     **由门自己按 `collectIncomingNodeDataForTarget` 数 counts**，不用调用方手填；
    #     **graph 与手填同给时 graph 覆盖手填**（门里的判定顺序如此）。
    g7 = {"gate": "libtv_model_rules_gate.py", "state": "skipped"}
    if not model_schema_p and not model_schemas_dir:
        findings.append({"code": "G7", "level": "WARN", "node": "pipeline",
                         "msg": u"没给 --model-schema → **模型前置规则一条都没跑**（≠通过）；"
                                u"先跑只读命令 `libtv model <modelKey>`，再用 --model-schema 传进来"})
    elif not model_schema_p:
        # ★ 只给了 `--model-schemas-dir` ⟹ **走下面的逐节点分流**，这条"单份 schema"路径不跑
        #   （否则会把 `None` 当路径塞进 argv）。
        pass
    else:
        _g7args = ["--schema", model_schema_p]
        if model_mode_type:
            _g7args += ["--mode-type", model_mode_type]
        if model_prompt is not None:
            # ★ 提示词按平台自己的 X / b(F(...)) 归一化后再判 hasPrompt——
            #   调用方**不需要**先替平台判断"这是不是空提示词"（插桩不算空）。
            _g7args += ["--prompt", model_prompt]
        if model_node_kind:
            _g7args += ["--node-kind", model_node_kind]
        if model_video_materials:
            _g7args += ["--video-materials", model_video_materials]
        if model_materials_from:
            # ★ 给了 graph 就让**门自己数 counts**（`collectIncomingNodeDataForTarget` 的语义），
            #   比手填 `--model-images|videos|audios` 更接近平台；两者同给时**graph 覆盖手填**。
            _g7args += ["--materials-from", model_materials_from]
        for _ck in ("image", "video", "audio"):
            if model_counts.get(_ck) is not None:
                _g7args += ["--%ss" % _ck, str(model_counts[_ck])]
        for _k in ("prompt", "image", "video", "audio", "media"):
            if model_has.get(_k):
                _g7args.append("--has-%s" % _k)
        _rc7, _out7 = _run_gate("libtv_model_rules_gate.py", _g7args)
        if _rc7 is None:
            g7 = {"gate": "libtv_model_rules_gate.py", "state": "missing"}
            findings.append({"code": "G7", "level": "FAIL", "node": "libtv_model_rules_gate.py",
                             "msg": u"找不到门禁脚本 libtv_model_rules_gate.py"})
        elif _rc7 == 0:
            g7 = {"gate": "libtv_model_rules_gate.py", "state": "pass", "rc": _rc7}
        elif _rc7 == 3:
            # 退出码 3 = schema 里没有 rules 字段。与 G1 的 3 同构：**没验到 ≠ 通过**。
            g7 = {"gate": "libtv_model_rules_gate.py", "state": "not_verified", "rc": _rc7}
            findings.append({"code": "G7", "level": "WARN", "node": "pipeline",
                             "msg": u"模型 schema 里没有 `rules` 字段（退出码 3）——**没验到 ≠ 通过**"})
        elif _rc7 == 4:
            g7 = {"gate": "libtv_model_rules_gate.py", "state": "no_schema", "rc": _rc7}
            findings.append({"code": "G7", "level": "FAIL", "node": "pipeline",
                             "msg": u"--model-schema 读不到（退出码 4）：%s" % model_schema_p})
        else:
            _reasons = _g7_reasons(_out7)
            g7 = {"gate": "libtv_model_rules_gate.py", "state": "FAIL", "rc": _rc7,
                  "reasons": _reasons}
            findings.append({"code": "G7", "level": "FAIL", "node": "pipeline",
                             "msg": u"模型前置规则未过（rc=%d）→ **不许开生成**；平台原话：%s"
                                    % (_rc7, u" ｜ ".join(_reasons) or u"（解析不出 reasons）")})

    # ---- G7b 逐节点分流（★ 单一实现见 g7_per_node）----
    g7_nodes, _g7b_findings = g7_per_node(nodes, model_schemas_dir)
    findings += _g7b_findings

    # ---- 拓扑 / 批次 ----
    order, cyclic = topo_order(nodes)
    if cyclic:
        findings.append({"code": "K18", "level": "FAIL", "node": ",".join(cyclic),
                         "msg": u"引用图有环 → 无法定序"})
    batches = make_batches(order, nodes) if not cyclic else []
    byid = dict((n["id"], n) for n in nodes)

    # ---- G2 资产锁定：逐镜反查引用链 ----
    lock_state = dict((n.get("id"), (n.get("assetState") or "draft")) for n in nodes
                      if n.get("role") == "anchor")
    def chain_of(nid, seen=None):
        seen = seen or set()
        if nid in seen or nid not in byid:
            return set()
        seen.add(nid)
        out = set()
        for r in (byid[nid].get("refs") or []):
            if r in lock_state:
                out.add(r)
            out |= chain_of(r, seen)
        return out
    locked_fail = {}
    for n in nodes:
        if not n.get("run"):
            continue
        bad = sorted(x for x in chain_of(n["id"]) if lock_state.get(x) != "locked")
        if bad:
            locked_fail[n["id"]] = bad
            findings.append({"code": "G2", "level": "FAIL", "node": n["id"],
                             "msg": u"引用链上有未锁定资产 %s → **本镜整体不开工**"
                                    u"（`production-ledger.md` §二：不是「先跑着看」）" % "、".join(bad)})

    # ---- 预算 ----
    ops, seq = [], 0
    for b, batch in enumerate(batches):
        for nid in batch:
            n = byid[nid]
            seq += 1
            paid = bool(n.get("run"))
            ops.append({"seq": seq, "batch": b, "node": nid, "nodeType": n.get("nodeType"),
                        "name": n.get("name"), "run": paid,
                        "cost_class": "paid" if paid else "free",
                        "unit_cost": price_of(n, prices),
                        "idempotencyKey": n.get("idempotencyKey") or idem("n", spec.get("project_id"), nid, n.get("attempt", 1)),
                        "role": n.get("role") or "shot"})
    unknown = [o["node"] for o in ops if o["unit_cost"] is None]
    paid_ops = [o for o in ops if o["cost_class"] == "paid"]
    # ① 有 --prices（精确单价）时优先用它
    total = None if unknown else round(sum(o["unit_cost"] or 0 for o in ops), 2)
    if total is not None:
        budget_lo = budget_hi = total
    else:
        # ② 无单价 → 仍算出库内「量级区间」（拟订）**只作参照**：
        #    ★ 2026-10-12 修正：此前这里把量级区间当成可开跑依据，实测
        #      `--approve` + 无单价 + 无预算上限 → 输出「可以开跑（0.00）」，
        #      与 L4「不编单价、缺单价锁死付费闸」自相矛盾。
        #      → 区间照算照报，缺单价本身仍判 FAIL（见下方 G3），付费闸保持关闭。
        los, his = [], []
        for o in ops:
            if o["cost_class"] != "paid":
                continue
            nb = next((n for n in nodes if n.get("id") == o["node"]), None)
            bb = budget_band(nb) if nb else None
            if bb:
                los.append(bb[0]); his.append(bb[1])
            else:
                unknown.append(o["node"])
        if los:
            budget_lo, budget_hi = sum(los), sum(his)
        else:
            budget_lo = budget_hi = None
        total = budget_hi
    if total is None:
        findings.append({"code": "G3", "level": "FAIL", "node": "budget",
                         "msg": u"无单价且无法定位量级区间（%s）→ **预算未解，付费闸关闭**" % "、".join(unknown)})
    elif ceiling is not None and budget_hi is not None and budget_hi > ceiling:
        findings.append({"code": "G3", "level": "FAIL", "node": "budget",
                         "msg": u"本场积分**上界 %s** > 预算上限 %s → **超预算，不开跑**"
                                 "（用上界比而非中值，保守）" % (budget_hi, ceiling)})

    if paid_ops and not prices:
        findings.append({"code": "G3", "level": "FAIL", "node": "budget",
                         "msg": u"有 %d 个付费节点，但**没有提供 --prices 单价**（%s）→ "
                                u"按 L4「本脚本不编积分单价」，**付费闸保持关闭**；"
                                u"量级区间 %s–%s 仅供参照，不作为开跑依据"
                                % (len(paid_ops), "、".join(unknown), budget_lo, budget_hi)})

    ready = (not cyclic) and (not locked_fail) and total is not None \
        and (ceiling is None or (budget_hi is not None and budget_hi <= ceiling)) and approved \
        and not any(x["level"] == "FAIL" for x in findings)
    out = {"schema": "libtv-orchestrate/pipeline@1", "project_id": spec.get("project_id"),
           "series": spec.get("series"), "batches": batches, "ops": ops,
           "compose": spec.get("compose"),
           "gates": [{"id": g, "name": n, "why": w} for g, n, w in PIPELINE_GATES],
           "gate_results": {
               "G1_upstream": g1, "G2_assets_locked": (not locked_fail),
               "G3_budget": {"total": total, "ceiling": ceiling,
                             "known": total is not None, "approved": approved},
               "G4_contract_fail": _codes(contract_findings) if any(x["level"] == "FAIL" for x in contract_findings) else [],
                "G5_content": _codes(comp_findings), "G6_generated": _codes([x for x in findings if x["code"] == "G6"]),
                "G7_model_rules": g7},
           "G7_per_node": g7_nodes,
           "ready_to_run": ready,
           "findings": findings}
    if out_p:
        write_json(out_p, out)

    print("")
    print(u"══ pipeline · 全链编译 ══")
    print(u"  %s ｜ 节点 %d（免费 %d / 付费 %d）· 批次 %d"
          % (spec.get("series") or "-", len(ops), sum(1 for o in ops if not o["run"]),
             sum(1 for o in ops if o["run"]), len(batches)))
    for gi, (gid, gname, gwhy) in enumerate(PIPELINE_GATES, 1):
        mark = u"?"
        if gid == "G1":
            # 「inapplicable」不阻断：它表示**这条判据本轮没验到**，不是验过了。
            #   挡住人 = 变回原来那个天天误报的闸；放行且不吭声 = 谎报绿灯。
            #   故：不阻断 + 单列一条显眼提示（见上面的 WARN finding）。
            mark = u"过" if all(x["state"] in ("pass", "skipped", "inapplicable") for x in g1) else u"未过"
        elif gid == "G2":
            mark = u"过" if not locked_fail else u"未过"
        elif gid == "G3":
            _g3bad = any(x["code"] == "G3" and x["level"] == "FAIL" for x in findings)
            if _g3bad:
                mark = u"未过"
            elif total is not None and budget_lo is not None and budget_lo != budget_hi:
                mark = u"过（量级 %s–%s · 拟订）" % (budget_lo, budget_hi)
            elif total is not None:
                mark = u"过（%.2f）" % total
            else:
                mark = u"未解"
        elif gid == "G4":
            mark = u"过" if not any(x["level"] == "FAIL" for x in contract_findings) else u"未过"
        elif gid == "G5":
            mark = u"过" if not any(x["level"] == "FAIL" for x in comp_findings) else u"未过"
        elif gid == "G6":
            mark = u"过" if not any(x["code"] == "G6" and x["level"] == "FAIL" for x in findings) else u"未过"
        elif gid == "G7":
            mark = {u"pass": u"过", u"skipped": u"未跑", u"not_verified": u"未验到",
                    u"no_schema": u"读不到", u"missing": u"缺脚本"}.get(g7.get("state"), u"未过")
            if g7_nodes:
                # ★ 逐节点分流给了就以它为准（单份 `--model-schema` 那行只是旧路径）。
                _badn = [k for k, v in g7_nodes.items() if v.get("state") == "FAIL"]
                _nvn = [k for k, v in g7_nodes.items()
                        if v.get("state") in ("no_schema", "not_verified", "missing")]
                _okn = len(g7_nodes) - len(_badn) - len(_nvn)
                mark = (u"未过" if _badn else u"过") + \
                    u"（逐节点 %d：%d 过 · %d 未过 · %d 未验到）" % (
                        len(g7_nodes), _okn, len(_badn), len(_nvn))
        print(u"  %s %-6s %s" % (gid, gname, mark))
    print(u"  ── 闸口判据 ──")
    for gid, gname, gwhy in PIPELINE_GATES:
        print(u"     %s %s：%s" % (gid, gname, gwhy))
    print(u"  ── 可否开跑：%s ──" % (u"**可以**（--approve 已给且各闸全过）" if ready
                                    else u"**不可以**（见上面未过的闸）"))
    if locked_fail:
        print(u"  ★ 未锁定资产涉及的付费镜：%s" % "、".join("%s←%s" % (k, "/".join(v))
                                                        for k, v in sorted(locked_fail.items())))
    _print_findings(findings)
    return _rc(findings)



# ─────────────────────────────────────────────────────────────────────────────
# ★ 内容合规层（G5）—— 补上「六道门禁全绿却把明文规则做错」这个洞
# ─────────────────────────────────────────────────────────────────────────────
#
# **为什么要有这一层**：结构门禁（行数/悬空/索引/数字/自检）**只能证"结构没坏"**，
# 证不了"内容合不合库的规矩"。2026-10-01 实测：六项门禁全 EXIT=0，而建图却把
# `storyboard-frame.md` §十 明文标注"不推荐"的**做法 C**接了进去 —— 结构全对，内容违规。
# **这一层把库里已经写死的 craft 规则编码成可执行判据**，每一码都注明出处册与行。
#
# ★ 命名约定即规则源（库内已有：`libtv-op-manual-3.md` 实战画布就用这套前缀）
#   A=资产 · T=分镜卡(内容源) · S=故事板 · I=首帧 · V=镜头 · AU=声音 · X=合成

KIND_PREFIX = (("AU", "audio"), ("A", "asset"), ("T", "script_card"), ("S", "storyboard"),
               ("I", "keyframe"), ("V", "shot"), ("X", "compose"))


def node_kind(name):
    n = (name or "").strip()
    for pre, k in KIND_PREFIX:
        if n.startswith(pre):
            return k
    return None


# 否定式先行——否则「无 BGM」这种合规句会被误报（沿用 workrally_bridge.py 的 NEG_PAT 口径）
# 否定式先行——否则「无 BGM」这种合规句会被误报（沿用 workrally_bridge.py 的 NEG_PAT 口径）
_NEG = re.compile(
    r"\u65e0\s*(BGM|bgm|\u914d\u4e50|\u80cc\u666f\u97f3\u4e50)"
    r"|\u4e0d\u5e26\s*(BGM|bgm|\u914d\u4e50)|\u4e0d\u914d\u4e50|\u7981\u914d\u4e50"
    r"|\u65e0\s*\u97f3\u4e50|\u4e0d\u52a0\u97f3\u4e50|\u65e0\u97f3\u6548"
    r"|\u4e0d\u8981\u97f3\u4e50|\u4e0d\u51fa\u97f3\u4e50|\u5c24\u5176\u4e0d\u662f\u97f3\u6548")
_BGM = re.compile(r"BGM|bgm|\u914d\u4e50|\u80cc\u666f\u97f3\u4e50|\u5fc3\u8df3\u822a\u7684")


def _has_bgm_violation(text):
    """真出现 BGM 才算违规；带否定式的合规句放过。"""
    for m in _BGM.finditer(text or u""):
        seg = text[max(0, m.start() - 14):m.end() + 4]
        if not _NEG.search(seg):
            return True
    return False



LOGICAL_TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_\-]+)\s*\}\}")


def render_prompt(prompt, keymap):
    """把 spec 里的**逻辑 ID 插桩**换成**平台 node_key 插桩**。

    ★ 为什么要有这一步（2026-10-01 设计修正）：
      `create_node` 返回的 node_key 是**平台分配**的，编译期根本不知道。
      如果 spec 直接写真 key，spec 与真画布就会分家 —— 2026-10-01 实测正是这么翻车的：
      编译出的 plan 用简短 prompt，执行时却手写了另一版发出去，**spec 不再是真源**。
      → 约定：**spec 一律用逻辑 ID（如 A1/S1）书写插桩，本函数在执行前做一次替换**。
      → 好处：① 编译期就能核验「插桩集合 == refs 集合」（R5）；② prompt 与 spec 不会再分家。

    未在 keymap 里的逻辑 ID **原样保留**（不静默丢）。
    """
    if not prompt or not keymap:
        return prompt
    return LOGICAL_TOKEN.sub(lambda m: "{{%s}}" % keymap.get(m.group(1), m.group(1)), prompt)



def node_key_of(node, spec, logical_id):
    """spec 可选带 node_key_map；没有就返回 None（编译期确实不知道，平台才分配）。"""
    return ((spec.get("node_key_map") or {}).get(logical_id))


# ── 时长取整（`libtv-ignite-ops-fields.md` §1.4 · R37）──────────────────────────
# 原文：「先满足装得下内容，再在整数档里取**不小于需求的最小值**（等价向上取整）→ 3.5 秒 → 取 4」
def round_up_duration(need, allowed):
    """把「内容需要的时长」向上取整到**模型允许的档位**。
    返回档位值，无法放结时返回 None（**不猜**）。"""
    try:
        n = float(need)
    except (TypeError, ValueError):
        return None
    cands = []
    for a in (allowed or []):
        try:
            cands.append(float(a))
        except (TypeError, ValueError):
            continue
    ok = [a for a in cands if a >= n]
    return int(min(ok)) if ok else None


# ── trim 配额分配（`libtv-ignite-ops-fields.md` §1.6）──────────────────────────
# 原文算例：6 个源片各 5 秒 → 目标 29 秒、需裁 1 秒 → 5 个保持整段 5 秒、1 个裁成 4 秒 → 5×5＋4＝29✓
def plan_trim(target_seconds, sources, safe=None):
    """按「目标 T、N 个源片各 D 秒」算需裁 Δ＝N·D−T，再按「可裁空间」分配。

    `sources` = [{"node_key":..., "duration":...}, ...]  按成片顺序
    `safe`     = **node_key 列表**（不是数组下标）；为空则按顺序裁。可裁的清单（无台词 / 无关键动作的镜头），**只能裁这些**。
    返回 clips 数组；若 无法裁到目标，返回 None（不猜）。
    """
    try:
        T = float(target_seconds)
    except (TypeError, ValueError):
        return None
    clips, pool = [], []
    for i, s in enumerate(sources or []):
        try:
            d = float(s.get("duration"))
        except (TypeError, ValueError):
            return None
        clips.append({"node_key": s.get("node_key"), "start_position": 0,
                      "end_position": d, "_d": d, "_i": i})
        pool.append(i)
    total = sum(c["_d"] for c in clips)
    delta = total - T
    if delta <= 0:
        return clips                     # 不需裁（或超出目标 → 由上游控制）
    _sk = set(safe or [])          # safe 传的是 **node_key**，不是下标
    order = [i for i in pool if clips[i]["node_key"] in _sk] or pool
    for i in order:
        if delta <= 0:
            break
        c = clips[i]
        room = c["_d"] - 0.5            # 不裁到 0.5 秒以下（先再删字段）
        take = min(delta, room)
        if take > 0:
            c["end_position"] = c["_d"] - take
            delta -= take
    if delta > 1e-6:
        return None                       # 剩余裁不掉 → 不给弄理由解析
    for c in clips:
        c.pop("_d", None); c.pop("_i", None)
    return clips


def check_compliance(spec):
    """G5 内容合规：把库内写死的 craft 规则跑成判据。返回 findings。"""
    f = []
    nodes = spec.get("nodes") or []
    byid = dict((n.get("id"), n) for n in nodes)
    kinds = {}
    for n in nodes:
        kinds[n.get("id")] = node_kind(n.get("name")) or (n.get("role") == "anchor" and "asset")

    def add(code, level, node, msg):
        f.append({"code": code, "level": level, "node": node, "msg": msg})

    def warn(code, node, msg):
        add(code, "WARN", node, msg)

    have = set(x for x in kinds.values() if x)

    # ---- R4 必备层齐备（`libtv-op-manual-3.md` §30.5 总纲「加一层就补这层」）----
    for need, why in ((u"script_card", u"T 分镜卡＝内容源"), (u"storyboard", u"S 故事板"),
                      (u"keyframe", u"I 首帧"), (u"shot", u"V 镜头"), (u"compose", u"X 合成（§30.3 该用 video-clip）")):
        if need not in have:
            add("R4", "FAIL", u"spec", u"缺 %s 层（%s）→ **图是断的**" % (need, why))

    # ---- R3 每类资产齐备（`run-sheet.md:82`「每个角色/场景/道具都要有独立资产图」）----
    assets = [n for n in nodes if kinds.get(n.get("id")) == "asset"]
    if not assets:
        add("R3", "FAIL", u"spec", u"一个资产节点都没有 —— 站 5.5 硬门禁 1 直接不过")
    else:
        blob = u" ".join((a.get("name") or u"") + (a.get("prompt") or u"")[:80] for a in assets)
        for cat, kw in ((u"角色", (u"角色", u"人")), (u"场景", (u"场景", u"环境")), (u"道具", (u"道具", u"物"))):
            if not any(k in blob for k in kw):
                add("R3", "FAIL", u"assets", u"没有%s资产图 —— 站 5.5 硬门禁明写「**不是只做主角**」" % cat)

    # ---- R2 资产图三条硬规格（`asset-consistency.md:35-37`）----
    for a in assets:
        nm = a.get("name") or ""
        pr = a.get("prompt") or u""
        is_scene = u"场景" in nm or u"环境" in nm
        is_prop = u"道具" in nm
        if not is_scene and not any(k in pr for k in (u"\u4e2d\u6027\u7070", u"\u7eaf\u8272\u80cc\u666f", u"\u7070\u5e95")):
            add("R2", "FAIL", nm, u"硬规格①「纯中性灰底」未落到 prompt（`asset-consistency.md:35`）")
        if not any(k in pr for k in (u"\u67d4\u5149", u"\u6f2b\u5c04", u"\u65e0\u5f71", u"\u67d4\u548c")):
            add("R2", "FAIL", nm, u"硬规格②「柔光近乎无影」未落到 prompt（`asset-consistency.md:36`：设定图的光会**继承进每一条下游**）")
        if is_scene and not any(k in pr for k in (u"3/4", u"\u4e24\u9762\u5899")):
            add("R2", "WARN", nm, u"硬规格③「场景须 3/4 角度、可见两面墙」疑似未落（`asset-consistency.md:37`）")

    # ---- R1 故事板→首帧/镜头 的连法（★ 2026-10-01 已裁决，见下）----
    # 【冲突原文】①`storyboard-frame.md`§十：灰度故事板**不能**直接当首帧（做法C标「不推荐」）
    #            ②`libtv-op-manual-3.md`§30：「故事板之于首帧」须排在 left 首位；总纲「加一层就补这层到直接下游的边」
    # 【裁决 2026-10-01】**硬契约优先：生成听甲、血缘听乙**。
    #   依据：平台**无结构参考通道**（实测 get_model("Lib Image 2.5 Pro") 的属性里
    #   无 controlnet/canny/depth/lineart/structure 任何字段）→ 无法「只借构图不借色」，故取保守解：
    #     · **不建 S1 的像素参考边**（生成语义听甲）
    #     · **必须用纯文本在下游 prompt 里登记 S1 的 node_key**（血缘语义听乙）
    #   ★ 纯文本可行性**已实测**：探针节点 i-T7VLUiLXkK 用纯文本写真/假 node_key，
    #     既未触发闭包校验、也未生成任何 imageList/textList → 纯文本血缘安全。
    for n in nodes:
        nid = n.get("id")
        if kinds.get(nid) not in ("keyframe", "shot"):
            continue
        pr = n.get("prompt") or u""
        for r in (n.get("refs") or []):
            if kinds.get(r) != "storyboard":
                continue
            warn_msg = (u"故事板被当作**像素参考**连进了 %s。按 2026-10-01 裁决应改为："
                        u"去掉这条边，并在 %s 的 prompt 里用**纯文本**写故事板的 node_key 做血缘登记"
                        % (nid, nid))
            if r in pr:      # spec 用逻辑 ID；真 key 由 render_prompt 替换后再落
                warn("R1", nid, warn_msg)
            else:
                fail("R1", warn_msg + u"；且 prompt 里未见该故事板的任何登记 → 血缘断了")
    # 反向检查（**2026-10-01 修正：原写成"每个下游节点都要登记"，过宽、已产生假阳性**）：
    # §30.4.3 的原话是「派生视图 → **母锚点**」—— 只要求**直接下游**登记它自己的上游，
    # 不是要求整条祖先链在每个节点都留痕。故改为**全 spec 范围只查一次**：
    # 只要**有任何一个**节点以纯文本登记了该故事板，血缘链就算接上了。
    for sid, sk in kinds.items():
        if sk != "storyboard":
            continue
        noted = any((sid in (n.get("prompt") or u""))
                    or (node_key_of(n, spec, sid) and node_key_of(n, spec, sid) in (n.get("prompt") or u""))
                    for n in nodes)
        if not noted:
            warn("R1", u"spec", u"故事板 %s 全spec 无任何纯文本血缘登记 → §30.4「加一层就补这层到直接下游」"
                               u"的审计链会断（像素参考边不能替代血缘登记）" % sid)

    # ---- R8 参考位序：占首位的上游必须在首位（`libtv-op-manual-3.md` §30.1「违反即返工」）----
    for n in nodes:
        if kinds.get(n.get("id")) != "shot":
            continue
        refs = n.get("refs") or []
        kf = [r for r in refs if kinds.get(r) == "keyframe"]
        if kf and refs[0] != kf[0]:
            # ★ 2026-10-01 降级 FAIL→WARN：§30.1 写「违反即返工」，但 `libtv-ignite-ops-fields.md` §1.3 明写
            #   「reference_nodes 顺序**无强制语义（未映射）**，「顺序本身不改变引用是否成立」，首帧排首位仅是**实操建议（非契约）**。
            #   → 既然非契约，判 FAIL 就是误报（E23）；但位序依旧影响优先级，仍值得提醒。
            warn("R8", n.get("id"),
                u"首帧 %s 不在 refs 首位（实际首位=%s）。§30.1写「违反即返工」，但"
                u"**但 `libtv-ignite-ops-fields.md` §1.3 明写顺序「无强制语义、不改变引用是否成立」**→ 故降为 WARN；改 prompt 插桩顺序**不会**重排，要调必须拆边重建" % (kf[0], refs[0]))


    # ---- R10 生成 prompt 不得混入文学层（`libtv-official-qa-3.md` §末「最可能做错的三件事」第一件）----
    # 原文：命题 / 人物弧光 / 情绪基调 / 演表量表（0–5）/ 「全片唯一一次」这类全局/抽象约束 —— **平台都不理解**，
    # 写进去只会稀释有效信息、让模型自由发挥。
    # → 必须留在剧本文件，**只把可拍内容/镜位/光位/物件状态/时长送进 prompt**。【作用域】**所有 image/video 节点**（它们的 prompt 生成时都会发给模型，即使 refs 为空）；text/script 节点谱免（文学层本就住在那里）。
    LITERARY = (u"情绪基调", u"情绪轨迹", u"人物弧光", u"演表量表",
                u"全片唯一一次", u"全片唯一", u"宛剔", u"演绩",
                u"寒流", u"高级感", u"电影感")
    for n in nodes:
        if n.get("nodeType") not in ("image", "video"):
            continue                      # text/script 节点天然谱免：文学层就住在那里
        pr = n.get("prompt") or ""
        hit = sorted(set(w for w in LITERARY if w in pr))
        if hit:
            add("R10", "FAIL", n.get("id"),
                u"生成 prompt 里混入了文学层词 %s。`libtv-official-qa-3.md` §末："
                u"命题/弧光/情绪基调/演表量表/「全片唯一一次」「**平台都不理解**」，"
                u"写进去只会稀释有效信息、让模型自由发挥；它们应留在剧本文件里" % hit)


    # ---- R11 审核高危要素**组合**预检（`libtv-moderation.md` §十三·2 · R25）----
    # 原文列的是成**组合**（单个词不拦，两个同出现才拦）：
    #   血液+伤口 · 武器+挥动/指向 · 未成年人+亲密/危险 · 写实真人+名人相似脸 · 证件/公章/货币 · 频闪
    # → **为什么值得做**：§五明说内容违规「原样重试基本无意义（同一策略命中会稳定复现）」、「等待不会改变判定」
    #    → 它们会**白花钱**（并且可能已计费），**必须在点火前还是点火后**排除。
    RISK_GROUPS = (
        (u"血液", u"脂皮", u"伤口", u"流血"),                                  # 血液+伤口
        (u"武器", u"刀饿", u"枪"),                                                     # 武器
        (u"指向", u"挥动", u"打击"),                                  # 指向/挥动
        (u"未成年人", u"小学生", u"少女"),                                  # 未成年人
        (u"亲密", u"情色", u"暴露"),                                  # 亲密
        (u"证件", u"公章", u"银行签发"),                                  # 证件/公章/货币
        (u"频闪", u"闪烁",),                                                              # 频闪
        (u"名人", u"美风", u"熟悉", u"像"),                                                      # 名人相似脸
    )
    for n in nodes:
        if n.get("nodeType") not in ("image", "video"):
            continue
        pr = n.get("prompt") or ""
        hit = []
        for grp in RISK_GROUPS:
            got = [w for w in grp if w in pr]
            if len(got) >= 2:
                hit.append(got)
        for got in hit:
            add("R11", "FAIL", n.get("id"),
                u"命中审核高危组合 %s。`libtv-moderation.md` §五："
                u"内容违规「原样重试基本无意义（同一策略命中会稳定复现）」、「等待不会改变判定」——"
                u"**必须改内容**（换成暗示/剪影/虚构/降写实度），不是再碰一次" % got)

    # ---- R12 场景主锚点与成片机位必须一致（`libtv-official-qa-2.md` §R3.6）----
    # 原文：「**场景 3/4 图与「全片正对中轴」不匹配**！模型可能把 3/4 透视带进成片、破坏对称」。
    # → 主锚点写**正对中轴**；3/4 另出一张**空间参考图**，不当主锚点/首帧。
    for n in nodes:
        # ★ 2026-10-12 修正：此前用 `if "A2" not in name` 认「场景主锚点」——
        #   即**只有把场景锚点恰好命名成 A2 时这条闸才生效**：
        #     · 场景叫 A3（PATCH MOTHER 复刻包就是这样）→ 闸**根本不检查场景**（漏报）
        #     · 而恰好叫 A2 的角色锚点 → **误报**"场景主锚点未写正对中轴"
        #   两个方向都错。改为按语义认：名字含 场景/环境/走廊/空间，或沿用 A2 约定。
        _nm = n.get("name") or ""
        if not any(k in _nm for k in (u"场景", u"环境", u"走廊", u"空间")):
            continue
        pr = n.get("prompt") or ""
        if not any(k in pr for k in (u"正对中轴", u"单点透视", u"正对镜头")):
            add("R12", "FAIL", n.get("id"),
                u"场景主锚点 prompt 未写「正对中轴/单点透视」——R3.6：3/4 透视会被带进成片、破坏对称；"
                u"空间感要另出一张 3/4 图作 reference_nodes 参考，不当主锚点")
        if "3/4" in pr and not any(k in pr for k in (u"不当主锚点", u"空间参考", u"不作主锚点")):
            add("R12", "FAIL", n.get("id"),
                u"场景主锚点里出现 3/4 角度但未标注「仅作空间参考」——有把 3/4 当主锚点的风险")
    # ---- R13 一镜只写一种运动；焦段与景别自洽（`libtv-official-qa-2.md` §R4.7/R4.2）----
    # 原文：「**变焦（焦段变）与**轨道（机位移）矛盾**！平台**不会调和，会随机二选一或混着做，结果不可控」。
    #   焦段 = 焦段变化/机位不动；轨道 = 机位移动/焦段不变。
    # → 一镜**只能写一种**；全片若要两种，分配给不同镜头，不要写在同一镜。
    ZOOM = (u"变焦", u"焦段变", u"推焦", u"拉焦", u"变焦扭率", u"dolly", u"zoom")
    TRACK = (u"轨道", u"横移", u"平移", u"环绕", u"滑轨", u"转环", u"升降", u"下降")
    for n in nodes:
        if n.get("nodeType") != "video":
            continue
        pr = n.get("prompt") or ""
        z = [w for w in ZOOM if w in pr]
        t_ = [w for w in TRACK if w in pr]
        if z and t_:
            add("R13", "FAIL", n.get("id"),
                u"同一镜同时出现变焦词 %s 与运镜词 %s——R4.7：**平台不会调和，会随机二选一或混着做，结果不可控**；一镜只写一种运动" % (z[:2], t_[:2]))
    # 焦段与景别自洽（广角配全景 / 长焦配特写）
    for n in nodes:
        if n.get("nodeType") != "video":
            continue
        pr = n.get("prompt") or ""
        m_tele = re.search(r"(\d{2,3})\s*mm", pr)
        if not m_tele:
            continue
        try:
            f = int(m_tele.group(1))
        except ValueError:
            continue
        wide = any(w in pr for w in (u"全景", u"广角", u"度景"))
        tele = any(w in pr for w in (u"特写", u"近景", u"特近"))
        if wide and f >= 60:
            add("R13", "WARN", n.get("id"), u"广角视角搭长焦（%dmm）——R4.2：广角搭全景，长焦搭特写" % f)
        if tele and f <= 35:
            add("R13", "WARN", n.get("id"), u"特写搭广角（%dmm）——R4.2：长焦搭特写，广角只用于 1–2 个全景" % f)
    # ---- R14 青橙调高危：冷白硬光 + 暖色物件（`libtv-official-qa-2.md` §R5.6）----
    # 原文：「**冷白硬光 与 暖色物件（橙红地面/塑料牌）＝天然青橙对比，极易滑向青橙调！**
    # → 必须明确写「暗部为中性冷灰蓝，非青绿」「高光为中性冷白，非暖黄」。
    # ★ **关键：暗部青蓝要「灰」不要「青」**（原文原话）。
    COOL = (u"冷白", u"冷光", u"白光", u"属性冷白")
    WARM = (u"深橙红", u"橙红", u"暖黄", u"橙光", u"温暖", u"金红")
    SHIFT = (u"青绿", u"青高", u"青暗", u"青蓝")
    for n in nodes:
        if n.get("nodeType") not in ("image", "video"):
            continue
        pr = n.get("prompt") or ""
        has_cool = any(w in pr for w in COOL)
        has_warm = any(w in pr for w in WARM)
        has_shift = any(w in pr for w in SHIFT)
        guarded = (u"非青绿" in pr) or (u"非青" in pr)
        if has_cool and has_warm and has_shift and not guarded:
            add("R14", "FAIL", n.get("id"),
                u"冷光 + 暖色 + 青调三项兵备，且 prompt 未写「非青绿/非青」护栏：R5.6："
                u"**极易滑向青橙调**（青蓝要「灰」不要「青」）")
        if has_warm and has_cool and u"皮肤" in pr and not guarded:
            add("R14", "WARN", n.get("id"),
                u"有冷光 + 暖色且含皮肤，未写皮肤不偏青（R5.7：皮肤线要写、写成排除句）")
    # ---- R15 白写元词 + 输出长度 + 朝向距离（`libtv-prompt-structure.md` §三/§二/§10.6）----
    # ① 白写元词：提质/增强/高清/优化/电影感提升、「后期特效」概念、「风险移除」、「过渡压力」、「本镜目的」
    #    → 它们不产生画面增益；「不要出现雨伞」反而会强化雨伞概念」
    JUNK = (u"提质", u"增强", u"高清", u"优化", u"电影感提升", u"后期特效",
            u"风险移除", u"过渡压力", u"本镜目的", u"套 LUT")
    # ② 输出长度：思考层 12 块不变，**输出层收敛到 5 块主干、常规 150–350 字（上限 500）**
    #    ⚠ 这是 **QA 阈值，不是平台阈值**（§10.7）——上限用 FAIL，常规超用 WARN。
    # ③ 身体朝向与距离（§10.6 第3条）：坐下 + 手伸向柜子 的镜头，必须交代朝向与距离，否则模型自行测宗。
    for n in nodes:
        if n.get("nodeType") not in ("image", "video"):
            continue
        pr = n.get("prompt") or ""
        j = sorted(set(w for w in JUNK if w in pr))
        if j:
            add("R15", "FAIL", n.get("id"),
                u"prompt 含白写元词 %s——模型不理解「提质/增强/后期」这类词（§三）" % j[:3])
        if n.get("nodeType") == "video":
            ln = len(pr)
            if ln > 500:
                add("R15", "FAIL", n.get("id"), u"prompt %d 字 > 上限 500" % ln)
            elif ln > 350:
                add("R15", "WARN", n.get("id"),
                    u"prompt %d 字 > 常规 350（上限 500）——**思全 12 块 ≠ 写全 12 块**（§七）；"
                    u"正确做法不是硬删，是**把信息搬到参考图/首帧**" % ln)
            if (u"坐" in pr or u"坐着" in pr) and any(w in pr for w in (u"抽屉", u"手", u"臂")):
                if not any(w in pr for w in (u"朝向", u"转身", u"体向", u"面向")):
                    add("R15", "WARN", n.get("id"),
                        u"有坐下/手部动作却未交代**身体朝向**（§10.6 第3条）")
    REF_SEG = re.compile(u"[；;\n。]+")
    # ---- R16 每个引用要写「用于…／不采用…」（`libtv-prompt-house-style.md` §6.3-1）----
    # 原文：「每个引用都写『用于什么 与 不采用什么』—— 既说明用途，又排除『资产图自带的背景/构图污染』」
    #   → 这是解「引用资产图会带进灰底或固定构图」的现成答案（与 R3.6 / R3.8 同源）。
    for _n in nodes:
        if _n.get("nodeType") not in ("image", "video"):
            continue
        _pr = _n.get("prompt") or ""
        _refs = _n.get("refs") or []
        if _refs:
            # ★ 2026-10-02 加严（E23 误报比漏报更隐蔽）：
            #   旧版只查 "用于" 与 "不采用" 两个词**是否出现**，等于「一句话糊弄全局」也能过。
            #   §6.3-1 的原意是**逐个引用**都要既说用途、又排除污染 → 改为**按引用逐项核**。
            _miss = []
            for _r in _refs:
                _tok = "{{%s}}" % _r
                _segs = [s for s in REF_SEG.split(_pr) if _tok in s]
                if not any(("用于" in s and "不采用" in s) for s in _segs):
                    _miss.append(_r)
            if _miss:
                add("R16", "FAIL", _n.get("id"),
                    "引用 %s（共 %d 个）未在**同一句里**同时写出「用于…」与「不采用…」——"
                    "§6.3-1 要求逐项说明用途**并**排除资产图自带的背景/构图污染"
                    % ("、".join(_miss), len(_refs)))
        if kinds.get(_n.get("id")) in ("storyboard", "keyframe", "shot"):
            if "背景音乐" in _pr and "No BGM" not in _pr:
                add("R16", "WARN", _n.get("id"),
                    "写了背景音乐但没有英文 `No BGM`——§6.3-6：**平台能认英文 No BGM**，建议补")    # ---- R9 参考图数量：1–3 张为稳（`libtv-quality-delivery-content.md` §3.10.3）----
    # schema 允许到 10（mixed2videoConfig.imageMax），但平台自身的写实经验给的是 **1-3 张**：
    #   「1 张锁身份 · 1 张锁场景 · 1 张锁风格」，「超过 3 张容易互相打架」。
    # → **内容级建议**（非契约）→ 只提醒，不判 FAIL。
    for n in nodes:
        if kinds.get(n.get("id")) not in ("keyframe", "shot"):
            continue
        _cnt = len([r for r in (n.get("refs") or []) if kinds.get(r) in ("asset", "keyframe", "storyboard")])
        if _cnt > 3:
            warn("R9", n.get("id"),
                 u"引用了 %d 张图（>3）。`libtv-quality-delivery-content.md` §3.10.3："
                 u"「每个生成节点引用 1–3 张最稳，超过 3 张容易互相打架」"
                 u"——schema 允许到 10，这是**经验建议**；若已确认冲突，先减到 3 再生成" % _cnt)

    # ---- R5 插桩覆盖（`libtv-op-manual-3.md` §28.2「三者必须一一对应」）----
    # ★ 2026-10-01 修正两处**过严**（反向验证自己跑出来的假阳性，E23）：
    #   ① 契约是「**每个 key 至少出现一次**」，**不是"恰好一次"** → 改集合覆盖，允许重复；
    #      （实测 V1 的同一组插桩在【引用】与【人物与环境】各出现一次，8 个对 4 条引用是合法的）
    #   ② **合成节点(X)的边是「登记边」**：§30.4.2 明写「即使底层用 clips 数组传参导出，
    #      也必须在图上登记引用边，依赖链才可审计」→ 该场景不要求 prompt 里有插桩。
    for n in nodes:
        if kinds.get(n.get("id")) == "compose":
            continue                       # §30.4.2：合成节点的边是「登记边」，不要求插桩
        refs = set(n.get("refs") or [])
        toks = set(REF_TOKEN.findall(n.get("prompt") or u""))
        if refs != toks:
            add("R5", "FAIL", n.get("id"),
                u"插桩集合 %s ≠ 引用集合 %s → §28.2「占位符/引用数组/真实节点三者必须一一对应」"
                % (sorted(toks), sorted(refs)))
    # ---- R6 分镜阶段 No BGM（声音守卫，同 `workrally_bridge.py` 口径）----
    for n in nodes:
        if kinds.get(n.get("id")) in ("script_card", "storyboard", "keyframe", "shot"):
            if _has_bgm_violation(n.get("prompt") or u""):
                add("R6", "FAIL", n.get("id"),
                    u"分镜阶段出现未否定的 BGM/配乐 —— 违反「分镜阶段 No BGM、声音后置独立制作」")
    return f



def cmd_compliance(argv):
    """`compliance --spec job.json [--out findings.json]` —— 只跑内容合规层（不编译、不连平台）。

    **为什么单独给一条命令**：结构门禁全绿而内容违规的事已经发生过一次；
    这一层让「内容合规」可以单独跑、单独进 CI、单独回看。
    """
    spec_p = out_p = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--spec":
            i += 1; spec_p = argv[i]
        elif a == "--out":
            i += 1; out_p = argv[i]
        i += 1
    spec = read_json(spec_p)
    if spec is None:
        C.die("[FAIL] 读不到 spec：%s" % spec_p, RC_USAGE)
    f = check_compliance(spec)
    if out_p:
        write_json(out_p, {"schema": "libtv-orchestrate/compliance@1", "findings": f})
    print("")
    print(u"── G5 · 内容合规（结构对 ≠ 内容对）──")
    if not f:
        print(u"  全过：R1–R16 均无违规")
    _print_findings(f)
    return _rc(f)



def _probe_plugin(plugin, config_path, codex_home):
    """只读地回答一个问题：**这个插件现在能不能被调到？** 返回四层体检表。

    ★ 为什么要有这个函数（`pitfalls.md` **P18**）：
      2026-10-01 整轮工作推进到「画布侧第 3 件待办」才发现 LibTV MCP **早就掉线**。
      `unknown MCP server` 这类错误**不主动问就不会出现**——开工第一件事必须是探针。
      本函数把探针做成**一条命令**，不必再靠记忆。

    ★ 四层顺序是**刻意的**（`libtv-op-manual-2.md` §十九）：
        注册 → 缓存 → 凭据存在性 → 网络
      顺序反了会白费：凭据好好的、缓存好好的，注册段没了的时候，
      去查凭据/查网络**永远查不出问题**，人就被卡在错的一层上。

    ★ 三条红线（本函数一条都不许破）：
      ① **只读**：不改 config、不装插件、不删任何东西；
      ② **不读凭据内容**：只判断路径**存在与否**（`libtv-op-manual-2.md` §十九明令禁止提取）；
      ③ **不发网络请求**：本库 10 个脚本里 `urllib`/`requests` 必须是 0 行。
    """
    import re as _re
    out = {"plugin": plugin, "layers": [], "ready": False, "fix": []}

    # ---- 第 1 层：注册（config.toml）----
    reg_ok = False
    mkt = plugin.split("@")[-1]
    if config_path and os.path.isfile(config_path):
        txt = io.open(config_path, encoding="utf-8", errors="replace").read()
        has_mkt = bool(_re.search(r"^\[marketplaces\.%s\]" % _re.escape(mkt), txt, _re.M))
        mp = _re.search(r'^\[plugins\."%s"\]\s*$(.*?)(?=^\[|\Z)' % _re.escape(plugin),
                        txt, _re.M | _re.S)
        has_plug = bool(mp)
        enabled = bool(mp and _re.search(r"^\s*enabled\s*=\s*true", mp.group(1), _re.M))
        reg_ok = has_mkt and has_plug and enabled
        out["layers"].append({
            "n": 1, "name": u"注册（config.toml）", "ok": reg_ok,
            "detail": u"[marketplaces.%s]=%s · [plugins.\"%s\"]=%s · enabled=true=%s"
                      % (mkt, u"有" if has_mkt else u"**无**",
                         plugin, u"有" if has_plug else u"**无**",
                         u"是" if enabled else u"**否**")})
    else:
        out["layers"].append({"n": 1, "name": u"注册（config.toml）", "ok": False,
                              "detail": u"读不到配置文件：%s" % config_path})
    if not reg_ok:
        out["fix"].append(u"**这一层断了，其余两层查了也是白查。** 请把 "
                          u"`[marketplaces.%s]` 与 `[plugins.\"%s\"] enabled=true` "
                          u"写回 config.toml，或在插件管理里重新启用。" % (mkt, plugin))

    # ---- 第 2 层：缓存（插件本体是否已下载）----
    cache_root = os.path.join(codex_home, "plugins", "cache")
    cdir = os.path.join(cache_root, mkt, plugin.split("@")[0])
    versions = sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []
    versions = [v for v in versions if os.path.isdir(os.path.join(cdir, v))]
    out["layers"].append({"n": 2, "name": u"缓存（插件本体）", "ok": bool(versions),
                          "detail": (u"%s → %s" % (cdir, u"、".join(versions))) if versions
                                    else u"**没找到**（%s 不存在）→ 需重装" % cdir})
    if not versions:
        out["fix"].append(u"缓存层也断了：插件本体没下载过，需重装（`codex plugin add`）。")

    # ---- 第 3 层：凭据存在性（**只看路径在不在，不读内容**）----
    import glob as _glob
    _home = os.path.expanduser("~")
    _roots = [codex_home, os.path.dirname(codex_home.rstrip("/" + chr(92)))]
    _roots += [os.path.join(_home, n) for n in (".codex", ".workbuddy", ".config", ".libtv")]
    _roots += _glob.glob(os.path.join(_home, ".workbuddy", "connectors", "*"))
    _hits = []
    for _r in _roots:
        _c = os.path.join(_r, ".credentials.v3.json")
        _k = os.path.join(_r, ".master.key")
        if os.path.isfile(_c) or os.path.isfile(_k):
            _hits.append((_r, os.path.isfile(_c), os.path.isfile(_k)))
    has_cred = any(h[1] and h[2] for h in _hits)
    out["cred_dirs"] = [h[0] for h in _hits]
    out["layers"].append({
        "n": 3, "name": u"凭据存在性（**只判存在，不读内容**）",
        "ok": has_cred,
        "detail": (u"找到：" + u"；".join(
            u"%s（.credentials=%s、.master.key=%s）"
            % (h[0], u"在" if h[1] else u"不在", u"在" if h[2] else u"不在")
            for h in _hits)) if _hits
        else u"**候选根下都没找到 .credentials.v3.json / .master.key**（只判存在，未读内容）"})
    out["cred_path_present"] = has_cred
    if not has_cred:
        out["fix"].append(u"凭据文件不在 → 需在插件里重新登录（**我不会替你解或提取它**，见 §十九红线）。")

    # ---- 第 4 层：网络（本脚本不查，明说）----
    out["layers"].append({"n": 4, "name": u"网络", "ok": None,
                          "detail": u"**本脚本不发网络请求**（红线：10 个脚本里 urllib/requests 必须 0 行）"
                                    u" → 请由 agent 侧跑 `ListMcpResources(libtv)` 确认；"
                                    u"报 `unknown MCP server` 就是没注册，不是网络问题"})

    out["ready"] = bool(reg_ok and versions and has_cred)
    out["verdict"] = (u"就绪：三层都在，可以开工"
                      if out["ready"] else
                      u"**不可用**：见上面 fix 段，**修好之前不要开始建节点**")
    return out


def cmd_preflight(argv):
    """`preflight [--plugin libtv@libtv] [--config PATH] [--json]`

    **开工第一条命令**（`pitfalls.md` P18）。只读，不改任何东西。
    """
    plugin = "libtv@libtv"
    config_path = None
    as_json = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--plugin":
            i += 1; plugin = argv[i]
        elif a == "--config":
            i += 1; config_path = argv[i]
        elif a == "--json":
            as_json = True
        i += 1
    codex_home = os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    if not config_path:
        config_path = os.path.join(codex_home, "config.toml")
    rep = _probe_plugin(plugin, config_path, codex_home)
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return RC_OK if rep["ready"] else RC_FAIL
    print("")
    print(u"══ preflight · %s ══" % plugin)
    for L in rep["layers"]:
        mark = u"[OK]  " if L["ok"] else (u"[--]  " if L["ok"] is None else u"[NG]  ")
        print(u"  %s第%d层 %s：%s" % (mark, L["n"], L["name"], L["detail"]))
    print(u"  ── 结论 ──")
    print(u"  %s" % rep["verdict"])
    if rep["fix"]:
        print(u"  ── 该你做的（本脚本只读，不改配置）──")
        for f in rep["fix"]:
            print(u"   · %s" % f)
    return RC_OK if rep["ready"] else RC_FAIL


def cmd_classify(argv):
    """`classify --error "<报错原文>" [--attempt N]` —— 告诉执行者**该不该重试、等多久**。

    为什么需要它：编排器自己不发 MCP 调用，**错误是执行者（agent）遇到的**。
    若没有这一步，参数错误会被**亲亏重试**（同一错反复发、多花链接）。
    来源：`libtv-official-qa-4.md` §13.4。
    """
    err = None
    attempt = 0
    i = 0
    while i < len(argv):
        if argv[i] == "--error":
            i += 1; err = argv[i]
        elif argv[i] == "--attempt":
            i += 1; attempt = int(argv[i])
        i += 1
    if not err:
        C.die("[FAIL] 缺 --error（把报错原文整个传进来）", RC_USAGE)
    kind, why = classify_error(err)
    wait = backoff_plan(attempt)
    print("")
    print(u"── K24 错误分类 · 该不该重试 ·")
    print(u"  分类：**%s**" % kind)
    print(u"  依据：%s" % why)
    if kind == "retryable":
        print(u"  退避：第 %d 次 重试前**等 %s 秒**（指数退避，最多 %d 次；限流优先读 Retry-After）"
              % (attempt + 1, wait if wait is not None else u"—", MAX_RETRY))
    elif kind == "not_retryable":
        print(u"  行动：**不要重试**。改参数/换方案后再发（改内容还必须**换新幂等键**）")
    else:
        print(u"  行动：**未知错误 —— 不猜。**先读原文、查该幂等键是否已用尽，再决定")
    print(u"  记录（`production-ledger.md` §6.1）：**参数错误=未计费** · **生成失败=可能已消耗** · **审核不过=通常不退**（UV1.6 + qa-4 §13.4 两处互印）")
    return RC_OK



def propagate_layers(spec, roots):
    """被 `roots` 重生效后，沿引用链逐层的下游节点。返回 (layers, cyclic)。

    纯函数、不落盘 —— 自检不用再造一个 spec 文件就能验这条判据。
    """
    nodes = spec.get("nodes") or []
    rdeps = dict((n.get("id"), []) for n in nodes)
    for n in nodes:
        for r in (n.get("refs") or []):
            if r in rdeps:
                rdeps[r].append(n.get("id"))
    _order, cyclic = topo_order(nodes)
    seen, layers = set(), []
    frontier = list(roots)
    while frontier:
        nxt = []
        for cur in frontier:
            for d in rdeps.get(cur, []):
                if d not in seen:
                    seen.add(d)
                    nxt.append(d)
        if not nxt:
            break
        layers.append(nxt)
        frontier = nxt
    return layers, cyclic


def cmd_propagate(argv):
    """`propagate --spec job.json --node A1 [--node I1 ...]`。

    **用途**：某个节点“被 update / 重生成 / 替换”之后，它回到「已创建」态、需重新生效，
    **沿引用链所有派生节点与合成节点的现有结果都应视为作废。**

    来源：`libtv-official-qa-5.md` §17.9 阶段3「**被引用节点若被 update/重生成/替换 → 它回到「已创建」需重新生效**，并沿引用链找出所有派生镜头与合成节点」。
    **同源**：`libtv-op-manual-3.md` §UV1.8 / `libtv-official-qa-6.md`。
    """
    spec_p = None
    roots = []
    i = 0
    while i < len(argv):
        if argv[i] == "--spec":
            i += 1; spec_p = argv[i]
        elif argv[i] == "--node":
            i += 1; roots.append(argv[i])
        i += 1
    spec = read_json(spec_p)
    if spec is None:
        C.die("[FAIL] 读不到 --spec", RC_USAGE)
    if not roots:
        C.die("[FAIL] 缺 --node（指出被重生成的节点）", RC_USAGE)
    nodes = spec.get("nodes") or []
    layers, cyclic = propagate_layers(spec, roots)
    kinds = dict((n.get("id"), node_kind(n.get("name"))) for n in nodes)
    print("")
    print(u"── 作用传播（若下列节点重生效，它们的现有结果全部作废）──")
    if cyclic:
        print(u"  ⚠ 引用图有环，传播结果不可信（先解环）")
    if not layers:
        print(u"  无下游：%s 是台层，没有引用它的节点" % "、".join(roots))
    for idx, lay in enumerate(layers, 1):
        desc = []
        for nid in lay:
            k = kinds.get(nid) or ""
            tag = u"【合成】" if k == "compose" else (u"【镜头】" if k == "shot" else u"")
            desc.append(nid + tag)
        print(u"  第 %d 层（必须重生效的直接下游）：%s" % (idx, " · ".join(desc)))
    print("")
    print(u"  ★ 流程：被引用节点重生效 → 沿链逐层重生效 → 合成节点最后重新合成（**合成不能提前生效**，否则拼入旧画面）。")
    print(u"  ★ 保守口径：不要回溯删旧节点后靠记忆重建（**删节点会换成新 node_key，旧插桩全挂**）——"
          u"用 `leftRemove` + `leftAdd` 换边，保留同一 node_key。")
    return RC_OK


USAGE = __doc__


def main(argv):
    if len(argv) < 1:
        C.die(USAGE, RC_USAGE)
    cmd = argv[0]
    rest = argv[1:]
    prices = None
    for k, a in enumerate(rest):
        if a == "--prices" and k + 1 < len(rest):
            prices = rest[k + 1]
    if prices:
        os.environ["ORCH_PRICES"] = prices
    if cmd in ("--self-test", "-t"):
        return cmd_self_test(rest)
    if cmd == "compile":
        return cmd_compile(rest)
    if cmd == "preflight":
        return cmd_preflight(rest)
    if cmd == "ingest":
        return cmd_ingest(rest)
    if cmd == "compliance":
        return cmd_compliance(rest)
    if cmd == "propagate":
        return cmd_propagate(rest)
    if cmd == "classify":
        return cmd_classify(rest)
    if cmd == "pipeline":
        return cmd_pipeline(rest)
    if cmd == "verify":
        return cmd_verify(rest)
    if cmd == "resume":
        return cmd_resume(rest)
    C.die("未知子命令：%s\n%s" % (cmd, USAGE), RC_USAGE)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
