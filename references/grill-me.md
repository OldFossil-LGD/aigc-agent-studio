# 开拍前审问（GrillMe · 创作意图澄清引擎）

> **何时读**：**任何任务的第一步**（默认，不是可选项）。用户给一句话也走——原话已答的题直接落账，只问真空白。
> **读完回哪**：回 `run-sheet.md` 站 0 → 站 1；会话与契约见 §七。
> **没它会怎样**：正式 Final 编不出来——`compile_intent_delivery.py` / `compile_production.py` 的 `--grill` 没有台账或契约就回 `GRILL_REQUIRED`，契约带阻断冲突回 `GRILL_CONFLICT`，台账与 intent 矛盾回 `GRILL_MISMATCH`。
> **单一权威**：「何时该问、问的形态」以 `run-sheet.md` §二·补 为准，本册不复述；本册定义**会话机制、题库、契约与门禁**。
> **来源**：从本项目旧交付包恢复会话引擎、题库和台账，再适配当前编译链。上游来源与许可核查见[来源说明](../THIRD_PARTY_NOTICES.md)。

---

## 一 · 它解决什么

一句模糊需求（「制作一部出租车司机深夜遇到神秘乘客的悬疑短剧」）到可执行的生产计划之间，有几十个岔路。GrillMe 不是问得越多越好，而是：

1. **先解析**：原话里已经明确的内容写成带来源的字段，**不再问第二遍**。
2. **只问高价值的**：一次一个主问题；答案不改变成片方向就不问。
3. **区分来源**：用户原话 / 问答确认 / 项目预设 / AI 提议 / 未知 / 冲突，六者不许混。
4. **能默认就默认**：剩余未知项用**可追溯的库内预设**补，而不是把「未知」当「没有」。
5. **落成契约**：`Creative Intent Contract`（`creative-intent-contract/v1`）交给剧作、资产、分镜与 12 块提示词编译器。

**它不是开发前的架构审查**：摄影机参数、模型内部设置、GPU 任务、画布连线都不在这里问（→ 站 3 / 6.5）。

---

## 二 · 八个意图维度（外加生产闸）

| 维度 | 要理解什么 | 代表问题 | 落进契约 |
|---|---|---|---|
| **创作目标** | 作品形态与交付物 | 短剧 / 短片 / 广告 / 预告 / 概念片？ | `creative_intent.content_type` · `deliverable` |
| **故事意图** | 主题、核心矛盾、观众感受 | 你希望观众看完后最强的感受是什么？ | `emotional_target` · `theme` · `core_conflict` |
| **叙事结构** | 反转、节奏、结尾 | 最后反转，还是持续揭露线索？ | `narrative_preference` · `ending_tone` |
| **视觉风格** | 量级系与美学方向 | 风格编号 / 一句可核对的工艺描述 | `visual_style` · `visual_register` |
| **人物与关系** | 不可变特征、关系张力 | 主角最不能改变的身份特征是什么？ | `character_invariants` · `cast_relations` |
| **交付规格** | 时长、画幅、语言、声音、平台 | 竖屏信息流还是横屏？ | `production_constraints.*` |
| **创作约束** | 必有 / 禁有 / 授权 | 边界：必须出现什么、绝对不能出现什么？ | `creative_constraints.*` |
| **AI 自主权** | 未指定细节由谁拍板 | AI 全权、关键节点确认，还是每步确认？ | `creative_authority.*` |
| **生产闸**（非创作意图） | 资产、一致性、预算、点火 | 库内工程问题，按需才问 | `production_constraints.*` · `creative_authority.*` |

题库是**数据**：`scripts/grill_bank.py`（33 题 / 9 个维度，每题带依赖、适用范围、优先级权重与契约落点）。要加题改题库并跑 `tests/test_grill_session.py`——**不要在对话里另拟一套问卷**。

---

## 三 · 一次一个主问题，L0/L1/L2

**选问题的顺序**（`scripts/grill_session.py` 的 `select`）：

1. 先算 **frontier**：前置条件已定、当前终点适用、依赖已满足的题。
2. 在当前终点**必答**（`blocking_for`）的题里取分最高的一题——必答题永远优先。
3. 没有必答题时，取剩余题里分最高的一题；**分数 ≥ 阈值且未超预算**才问。
4. 达不到阈值 → **停止**（`READY_TO_FINISH`），剩余未知项写进 `unresolved`，**不许编**。

分数是**相对权重**，不是校准过的置信度：

```text
priority(q) = decision_impact + downstream_rework_risk + uncertainty
            + user_relevance − interaction_friction − ability_to_default_safely
            (+ 作品类型的维度偏置：广告抬约束、概念片抬视觉、短剧抬结构与人物)
```

| 模式 | 何时 | 可选问题预算 | 阈值 |
|---|---|---|---|
| **L0 直接执行** | brief 已经完整（必答题全定） | 0 | — |
| **L1 快速澄清**（默认） | 常见模糊创意 | 3 | 18 |
| **L2 深度访谈** | 用户主动要求，或分叉明显 | 8 | 10 |

默认 `mode=auto`：**必答题全定 → 自动按 L0 结束（0 问）**；否则按 L1。

**停止条件**（同时满足，spec §4.4）：创作目标可理解 · 无未解决的阻断性矛盾 · 剩余未知项可用可追溯预设 · 剩余问题收益低于交互成本。

**动态追问**（不是固定问卷）：情感目标选「情感反转」→ 下一问是关系轴；选「烧脑推理」→ 下一问是线索公平性；选「恐怖惊悚」→ 下一问是恐怖来源。答案是分支条件（`when`），不是标签。

---

## 四 · 每轮 UX 与「你定」

每轮只给：

1. **一个**主问题；
2. 宿主允许数量内的互斥选项＋**自由输入**；选项过多时分页；
3. 题库允许委托时提供**「由 AI 决定」**——记 `project_preset` / `agent_proposed`，不锁；预算和点火题只收用户明示；
4. 一句**为什么问**（会影响生产哪一段）；
5. 非阻断时的**「直接开始」**——`default-rest` 批量填库内预设，然后编契约。

下面是题目内容的示意。实际交互必须调用宿主的询问工具，推荐方向与提问原因一并放进卡片。

```text
第 2 问 · I02 情感目标（故事意图 · 评分 31）
  你希望观众看完后，最强烈的感受是什么？
    A 心理悬疑（压迫感来自未知）
    B 恐怖惊悚（威胁直接可见）
    C 情感反转（结尾改写前面的关系）
    D 烧脑推理（线索可复核）
    E 其他（请写一句）
  ➡️ 推荐：C —— 原话里"神秘乘客 + 司机"更像关系揭示，不是破案。
  📌 为什么问：它决定下一问往关系还是往线索走，也决定结尾怎么写。
  ⤷ 也可以：回复「你定」由 AI 决定（记 defaulted/proposed，不锁）；或「直接开始」。
```

**禁止**：一轮里问「时长、画幅、风格、角色、节奏、预算、配音」；把「你想要什么风格？」这种空问抛回去。

---

## 五 · 来源、锁定与修订

| 字段 | 取值 | 纪律 |
|---|---|---|
| `source_type` | `user_original` / `grillme_answer` / `project_preset` / `agent_proposed` / `inherited_project` | 预设与 AI 提议**不许**标成用户原话 |
| `decision_status` | `confirmed` / `proposed` / `defaulted` / `unresolved` / `conflicted` | 默认与提议各归各的档 |
| `locked` | 布尔 | 只有用户原话/确认/继承项可锁；预设与提议不锁 |
| `confidence` | 数值或 null | 只是解释可信度，**不能代替用户授权** |
| `source_ref` | 原话片段 / `turn_003` / `preset:I17@bank-v2` / 上游契约 | 每项都能追回出处 |

**修订**：用户改变主意 → `revise` 生成**新 revision**，旧值进 `revision_history`，**不静默改写**。契约发布后按 revision 不可变。

---

## 六 · 契约、冲突与门禁

- **结构**：`schemas/creative_intent_contract.schema.json`（正式 JSON Schema，draft 2020-12）。
- **样例**：`samples/grill_ledger_papercut_prompt.json`；会话到契约的离线演示见 `examples/grillme_walkthrough.py`。
- **状态**：`needs_question` / `ready_for_planning` / `blocked_conflict`（`ready_for_planning` ≠ 所有生产参数就绪）。
- **阻断冲突**（`blocking_conflicts`，编契约时机判）：
  - `CONFLICT_REQUIRED_AND_FORBIDDEN`：同一项同时在必有与禁有里；
  - `CONFLICT_SILENT_REQUIRES_SOUND`：声音政策无声，却有必有的声音；
  - `CONFLICT_DIALOGUE_FORBIDDEN`：允许对白，禁有却禁人声；
  - `CONFLICT_MUSIC_FORBIDDEN`：配乐政策要音乐，禁有却禁配乐（「只有水声 + 默认加配乐」的典型）；
  - `CONFLICT_PEOPLE_AND_INVARIANTS`：禁有要求不出现人物，却给了人物不可变特征；
  - `CONFLICT_DEFAULT_FORBIDDEN`：用户选了每步确认，仍有默认／提议项。
- **编译器怎么用**：`--grill` 接受**契约**或**台账**，按下表处理。

| 情况 | 回执 | 结果 |
|---|---|---|
| 正常 CLI 没有 `--grill` | `GRILL_REQUIRED` | 意图编译只出草稿，生产编译拒绝开编 |
| 契约 `blocked_conflict` | `GRILL_CONFLICT` | 拒绝 |
| 当前终点还有必答题 | `GRILL_BLOCKED` | 拒绝 |
| 契约与 intent 的停点/时长/画幅/声音矛盾 | `GRILL_MISMATCH` | 拒绝 |
| 通过 | `GRILL_PASS` / `GRILL_PASS_WITH_WARNINGS` | 继续（审阅证据仍另判） |

契约自带 `authorization.generation_authorized: false`——**GrillMe 不授权点火**；`GRILL_PASS` 只证明该问的都答了，不证明原文已读、创作对或媒体合格。

`--draft` 保留给离线工程诊断，可以不传 GrillMe。显式传入的 `--grill` 即使在草稿模式也要校验。Python API 保留既有调用兼容性，需强制门禁的调用方传 `require_grill=True`。Skill 的正常创作流程始终先走站 0。

---

## 七 · 工作流（一条命令一步）

```bash
# 1 建会话（mode=auto 默认）
python scripts/grill_session.py start --out grill.session.json \
    --request "制作一部出租车司机深夜遇到神秘乘客的悬疑短剧"

# 2 把原话已经说清的字段落账（不问第二遍）
python scripts/grill_session.py record --session grill.session.json \
    --set G01=full_film --set G03=60 --set 'G04="2.39:1"'

# 3 生成本轮原生工具载荷，Agent 随后调用返回的 tool_call
python scripts/grill_ui.py prepare --session grill.session.json --tools tools.json

# 4 收到真实用户回答后记录响应；改口使用 revise
python scripts/grill_ui.py record --session grill.session.json --response response.json
python scripts/grill_session.py revise --session grill.session.json --id G03 --value 90

# 5 其余按库内预设，编契约 + 台账
python scripts/grill_session.py default-rest --session grill.session.json
python scripts/grill_session.py finish --session grill.session.json \
    --contract out/cic.json --ledger out/grill.json

# 6 用户可复核与纠错（show 列已定项与来源；metrics 给人看运营指标）
python scripts/grill_session.py show    --session grill.session.json
python scripts/grill_session.py status  --session grill.session.json --json
python scripts/grill_session.py metrics --session grill.session.json

# 7 交给编译器
python scripts/compile_intent_delivery.py intent.json --out out/ --grill out/cic.json --draft
```

退出码：`0` 就绪 ｜ `1` 阻断/不可信 ｜ `2` 用法错 ｜ `4` 仍需回答（`finish` 回 `NEEDS_QUESTION`）。

### 宿主交互适配

`tools.json` 由 Agent 根据本轮真实工具清单写入，每项含 `name`、`available: true` 和原始 `input_schema`。当前适配两种问题结构，`questions[].title/options` 字符串选项，以及 `questions[].id/header/question/options` 对象选项。只有实际可用且结构匹配的工具才使用，Plan 专用工具在普通模式不能列为可用。

`prepare` 返回 `WAITING_FOR_USER`、`pending_id`、`revision` 和 `tool_call`。Agent 必须执行该调用并等用户提交。异步工具的 `accepted: true` 只是调用回执，预选、空答和取消均保持等待。完整 brief 的 auto/L0 直接返回 `READY_TO_FINISH`。

`response.json` 包装原始响应，例如 `{"pending_id":"GUI_…","revision":1,"result":原始响应}`。同步响应读取当前问题 ID 下的 `answers`。异步响应使用用户消息里的原始答复数组，核对问题全文、工具名与题目序号。Agent 负责把实际调用的回复绑定到当前 pending，不能拿其他调用的回复代填。

复杂回答返回 `NEEDS_INTERPRETATION`，Agent 基于已收到的原话，用 `record --interpreted-value '<类型化 JSON>'` 映射题库字段。选「由 AI 决定」返回 `DELEGATED` 后，Agent 用 `--proposal` 提交未锁定提议。用户无需填写 JSON。

没有匹配工具时返回 `TEXT_CONSENT_REQUIRED`，先说明原因并等用户同意。取得同意后用 `prepare --text-consent '<用户同意原话>'` 出文字选项。文字答复由 Agent 包装为 `result.answers[当前 question_id].answers` 的单元素数组，仍走同一记录接口。复制 Skill 可获得适配脚本，原生卡片能力由宿主提供。

`grill_session.py next`、`answer`、`skip` 是内部诊断与会话维护接口。正常交互使用上述 prepare → 宿主提问 → 真实回复 → record 链路。

**会话恢复**：会话是磁盘上的 JSON（`grill-session/v1`），断线后 `--session` 继续；`--key` 幂等键防重复写入，重复提交回 `DUPLICATE` 而不是记两笔。

---

## 八 · 与既有册分工

| 册 | 管什么 | 本册怎么用它 |
|---|---|---|
| `run-sheet.md` §二·补 | **何时该问**、问的形态 | 唯一权威；本册把它变成会话与契约 |
| `steelman-protocol.md` | 稿子写完后的自打 | 审问在写之前，钢人在写之后 |
| `stage1-delivery-entry.md` | 提示词交付入口 | 读契约后编译；`--grill` 是站 0 凭证 |
| `production-compiler.md` | 整片主编译链 | 同上，缺契约拒编 |
| `delivery-review.md` | 正式交付的任务—来源—证据绑定 | `GRILL_PASS` 不升级为它 |
| `reverse-fidelity-contract.md` | 反推 mode / deliverable / source_access | `job.kind=reverse` 时 G17 是入口三问 |

---

## 九 · 坑

1. **一轮多问**：违反 spec §5 与 `run-sheet` §二·补；`next` 一次只出一题，别手工补问。
2. **问已知**：原话已答的必须 `record`，不是再问一遍。
3. **把未知写成默认**：没有安全预设就 `unresolved`（`I02` / `I03` / `I11` 没有默认值）。
4. **默认冒充用户**：`skip` 的项永远是 `project_preset` / `agent_proposed`，不锁。
5. **跳过阻断冲突**：配乐 / 无声 / 必有禁有冲突必须停；不能用「用户想跳过」当理由。
6. **把 L2 当目标**：轮数是体验预算，不是 KPI；分数不到阈值就停。
7. **改口不记账**：一律 `revise`，不许直接改 entry。
8. **把契约当 intent**：契约是意图层，12 块提示词是镜头层，别混。

---

## 十 · 验收（与规范 §14 对齐）

- [ ] 一句话需求能起会话，原话已有的字段不重复问
- [ ] 完整需求在 auto/L0 下 **0 问**直接 `ready_for_planning`
- [ ] 模糊需求每轮**只有一个**主问题，且随上一题改变分支
- [ ] 支持自由输入、由 AI 决定（`defaulted` / `proposed`）、非阻断时直接开始
- [ ] 每个决策可查 `source_type` / `source_ref` / `locked` / `decision_status` / revision
- [ ] 契约通过 `schemas/creative_intent_contract.schema.json`
- [ ] 真实冲突不被静默覆盖（`blocking_conflicts` 非空即阻断）
- [ ] 契约能过 `--grill` 进入提示词编译或整片编译
- [ ] 点火授权不因审问而放宽（G15 / G16 只收用户明示）
- [ ] 修改生成新 revision，旧值留在 `revision_history`
- [ ] 会话可恢复；重复提交幂等；空/非法答案有明确错误码
