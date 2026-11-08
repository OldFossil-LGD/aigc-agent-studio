# 20 · LibTV 图构建与分组规范（C 路 · 平台执行面）

日期：2026-10-07 ｜ 归属：C 路（平台图执行与验收）
上游契约：A 路 `02_图语法_节点边分组参数.md` + `graph_plan.schema.json`（**只读消费，不改**）
机器门禁：`scripts/graph_plan_lint.py`（离线、只读）

**本文只回答一件事**：A 的图语义落到 LibTV 画布上，**具体建什么、连什么、按什么顺序建**。
图是什么（语义）看 A 的 02；提示词怎么写看 B；本文不重复两者。

标签沿用全局约定：**【已验证】**（平台接口/回读实证）· **【库规】**（本库工程约束）·
**【例子】**（某次做法，不作规格）· **【已撤回】**· **【不可判定】**。

---

## 1 · A 的图语义 → 平台执行面：两张映射表（【已验证】）

### 1.1 节点类型

| A 的 `node_type` | 平台 `create_node.nodeType` | 说明 |
|---|---|---|
| `text` | `text` | 便签 / 剧本 / 备忘 |
| `image` | `image` | 资产图、关键帧、截帧 |
| `storyboard` | **`image`** | ⚠ 平台 6 档里**没有 storyboard**，落成 image 节点 |
| `video` | `video` | 镜头 |
| `audio` | `audio` | **必须显式给 `params.scene`**，否则建不出来 |
| `script` | `script` | Script V2 表（`b-` 前缀） |
| `video-clip` | `video-clip` | 时间线 / 合成位 |
| `group` | （分组） | 走 `groups[].node_ids`，**不是引用边** |

平台 `nodeType` 只有 **6 档**：`text / image / video / audio / script / video-clip`（doctor.toolRegistry 实测）。
**`storyboard` 是本库的统一语义层，不是平台概念** —— 它落地时就是一个 image 节点。

### 1.2 边类型（这是最容易被写错的一张表）

| A 的 `kind` | 平台机制 | 是否落平台边 |
|---|---|---|
| `reference` | `create_node`/`update_node` 的 **`left`**（增量 `leftAdd`/`leftEnsure`/`leftRemove`）+ prompt 里 `{{node_key}}` 插桩 | **是** |
| `assembly` | `video-clip` 节点的 `left` 顺序（或导出 `clips` 数组顺序） | **是** |
| `dependency` | 只表达"上游先生效"的排序约束 | **否**【已验证】 |
| `lineage` | 纯文本血缘登记（在 prompt 里以**纯文本**写 node_key） | **否**【已验证】 |

**【已验证】为什么后两类不落边**（2026-10-01 实测 + 平台 Agent 问询）：
带悬空 key 的**纯文本**不会触发闭包校验、也不生成任何 `*List`；
而 `{{key}}` 插桩会被当成真引用校验（key 不存在直接拒建）。
→ **血缘可以写名字，引用必须走边。**

**⛔ 绝对禁止**：用边表达 group 归属；用边代替 timeline；用边代替 prompt 插桩；
用展示名推导节点身份；把派生字段当人工输入（A §2 禁止项，**本文负责在平台侧执行它**）。

### 1.3 role → 习惯用法（非平台枚举，仅供建图时对齐）

`source`→text/script · `asset`/`storyboard`→image · `shot`→video ·
`audio`→audio · `composite`/`archive`→video-clip · `qa`→text · `group`→分组。

---

## 2 · 平台侧的三条硬事实（【已验证】，改设计前先读）

### 2.1 ⭐ 参考位次＝**建节点时 `left` 数组的顺序**，事后不可重排

四条证据链（2026-09-23 实战实测）：

1. 直接写 `params.imageListOrder` 被拒（`NODE_VALIDATION_FAILED`）——该字段由连线重算；
2. `leftRemove` + `leftAdd` 放**同一次调用**不能重排（返回 `operationStateUnchanged: true`）；
3. 分两步"全删 → 全加"也**不能**重排（旧边被恢复到原位）；
4. 决定性探针：新建空节点、`left=[S1, A1]`（S1 的创建时间晚于 A1）→ 回读 `imageListOrder = [S1, A1]`。

**→ 落地规则（违反即返工）**：

- 要"排第一参考位"的上游（首帧之于镜头 · 主锚点之于派生视图）**必须在 `create_node` 时就放进 `left` 首位**；
- **建节点顺序本身是设计的一部分**：先定好每层参考位序，再建节点；
- **补救只能重建节点**（`delete` + `create`），且会**级联**（改 F1 定序 → 要重建 V1 → 再传到 X1）；
- 既已建错又不想重建时的**唯一回退**：用 prompt 文字承担优先级（`构图第一依据：{{S1}}`），
  并在卡内标明"本节点平台参考位序为后补边，优先级由文字承担"。

### 2.2 ⭐ 同一画布的**写操作必须串行**

并发发多个 `create_node` → 只有 1 个成功，其余报 `PROJECT_WRITE_BUSY: The original write is still running`。
**与"节点级互斥"是两个层级的锁**：节点级＝同一节点不可并发生成；**画布级＝同画布任何写操作都要排队**。
读操作不受影响，可与写并发。

### 2.3 ⭐ 引用三件套缺一不可

一个被引用节点必须**同时**满足：

```text
① 出现在引用字段里（left / leftAdd；首帧还要进首帧槽位）
② 在 prompt 里以 {{node_key}} 插桩
③ 该节点已生效（有产物、url 非空）
```

**缺一即不得点火**。只在 prompt 文字里提到＝**无效引用**（等于没接）。
⚠ 讲机制的示例**不要写 `{{X}}`**：会当真实引用校验，key 不存在直接拒建 —— 改用「`『』`」或不带花括号。

---

## 3 · 节点与参数

### 3.1 两层字段，不要混

`action` 说节点类别（`image_generate` / `image_resource` / `video_generate` / `video_resource` …），
`modeType` 说生成方式（`text2image` / `image2image` / `mixed2video` / `frames2video` / `videoExtend2video` …）。
**`image2image` 不是一种 action**，它的 action 仍是 `image_generate`。

### 3.2 派生字段：只读

`imageList` · `imageListOrder` · `mixedList` · `mixedListOrder` · `videoList` · `audioList` ·
`textList` 及各自 `*Order` —— **由 `left` 建边后系统重算，不可直写**（直写报 `NODE_VALIDATION_FAILED`）。

### 3.3 ⭐ `params` 是**扁平补丁**：create 与 update 两套语义

| 操作 | `params` 语义 | 踩坑后果 |
|---|---|---|
| `create_node` | 建节点时按模型 schema 组织（`{model, modeType, settings:{…}}` 是合法的建节点形态） | —— |
| `update_node` | **扁平补丁**：要改 settings 里的字段，**必须平铺到 `params` 顶层** | 写成 `params:{settings:{duration:4}}` 会被**静默忽略**（不报错、`graphRevision` 照常推进） |

**【已验证】** 2026-10-03 实测：据此**白抽了一整笔视频积分**，运行的是旧提示词。
**→ 纪律：改完 `params` 必须回读确认字段值真的变了，不能只看 `ok:true`。**

### 3.4 参数取值域按模型逐个数

`params.settings.quality` 只接受 `low/medium/high/xhigh/max`（**不是** `1K/2K/4K`，那属 `resolution`）；
各模型的 `duration` 可能是**整数步进**（4.5 秒填不了）或**枚举**（如 `[5, 10]`）。
**任何取值域以现场 `get_model` 为准**，详见 21_ 规范 §2。

---

## 4 · 边与连接

### 4.1 连线合法性矩阵（【已验证】）

| 从 到 | image | video | audio | video-clip |
|---|---|---|---|---|
| **image** | 可连（0–14 参考） | 可连（1–15 张） | — | ✅ |
| **video（generate）** | ⛔ 不得进引用槽位 | ⛔ 不得进引用槽位 | ✅ | ✅ |
| **video（resource）** | 以 action 为准 | ✅ 可当参考素材 | ✅ | ✅ |
| **audio** | — | ✅ | ✅ | ✅ |
| **text** | — | ✅（血缘/说明） | — | ✅ |

### 4.1.1 ⭐⭐ `video→video`：约束在**引用槽位**，不在边

**【已验证】三作实测（2026-10-07）**：video→video 边**大量真实存在** ——
W1 **112** 条（源 `video_resource` 111 · `video_generate` 1）· W2 **101** 条 · W3 **33** 条。

**→ 精确规则**：

```text
① 边本身合法：video_resource 当参考素材、以及工作室自己的组织/顺序边，都允许存在。
② 被禁的是「把 video_generate 的产物放进下游的引用槽位」——即拿上一镜的成片直接接尾帧。
③ 判一条边是不是"引用"：回读目标的 imageList / mixedList / videoList 槽位，
   不在槽位里的边就不是引用边（W1 实测：115 个可判节点里，边表与槽位只有 34 个完全一致）。
④ 要"接上一镜"，正解是**先截成 image 节点**再进引用槽位（或走 frames2video 的第一槽位）。
```

**【已撤回】** 两版过严写法都作废：旧册"video 到 video 一律被禁"（2026-10-03 已修正），
以及"`video_generate` 之间绝对不可连"——**边可以连，槽位才是门禁**。

⚠ `graph_plan_lint` 因此只在 **`kind == "reference"`** 时才拿 `action` 判这条；
非引用边直接放行（`EDGE_V2V_NONREF`）。

### 4.2 不落平台边的两类，怎么留痕

- `dependency`：写进执行台账 / 波次表（谁必须先生效），平台侧**不需要**对应边；
- `lineage`：在 prompt 里**纯文本**登记来源 node_key，**不加花括号**。

### 4.3 重复边与悬空边

重复边会**放大权重或引发校验异常**；悬空边（端点不存在）会让下游拿不到参考。
两者都是点火前必须清掉的硬缺陷 → 由 `graph_plan_lint` 判 `FAIL`。

---

## 5 · 分组、命名与人审布局

### 5.1 分组是**组织单位**，不是运行语义

- 分组**只表归属**，不替代依赖边、不替代引用边、不参与生成顺序；
- 组内坐标与框只服务**人审阅读顺序**；
- **组变更不自动改节点版本**；节点内容变更才传播失效。

**分组判据**：**"同生共死"的才放一组**（要一起生、一起死的）；不是"看起来相关就放一起"。

### 5.2 组名是最廉价的情报

实测样本里的分组名是制作者自己写的语义标注（如 `主角资产` `怪兽` `第一段`），
**读画布时先看组名，比逐个读节点快一个数量级**。
→ **建图时给组写业务语义名**（`assets.<作品>.<角色>`、`shots.<场景号>`），别留 `Group 1` 这类默认名。

### 5.3 ⭐ 画布布局：三带分区（【例子】，来自获奖连载短片样本）

样本的 x 坐标把整张图分成三带：左＝全部资产（按语义分组）· 中＝分段 video ·
右＝合成类。**段内只有 video 节点，资产全在左边独立组**。

⚠ 这是**该样本的做法，不是平台要求**。可抄的是"**人审时先看哪里**"这个结构：
**读节点第一步是看标题行（叙事顺序），不是看它在画布上的位置（位置只表示分组归属）**。

### 5.4 三条命名纪律

1. **节点名承载语义，不承载状态** —— 名称不能用来推导运行状态、身份或版本（A §1）；
2. **节点名唯一性**：同名节点靠人区分不了，检索会串（三作实测有同名率）；
3. **画布/项目选择永远用 uuid，不用名字**（平台自陈"同名项目不自动合并"，本账号实测 5 个都叫「画布 1」）。

---

## 6 · 合成位：用 `video-clip`，不要用 text

**【已验证】** 建 `video-clip` 节点 + `left=[V1,V2,V3]` 一次成功，`counts.timelines` 由 0 变 1（会进时间线区）。

| 节点类型 | 实测约束 |
|---|---|
| `text` | 最多接受 **1 路**视频入边（多传直接报"已达上限"） |
| `image` | 接图片参考入边前**必须先 `modeType=image2image`**（text2image 会被拒） |
| `video-clip` | **合成 / 时间线该用它** |

**【已撤回】** 本库此前把合成位建成**文本节点**是错的（接不满多路、也不进时间线区），已改。

⚠ 即使底层用 `clips` 数组传参导出，**也必须在图上登记引用边**，依赖链才可审计。

---

## 7 · 写操作纪律（幂等 / revision / 锁）

| 纪律 | 内容 |
|---|---|
| **幂等键** | 所有写操作带 `idempotencyKey`：断了重试**不会生成第二个**；**同键必须同文**（换内容要换新键，否则 `IDEMPOTENCY_CONFLICT`） |
| **revision** | `update_project` 的乐观锁取**上一次 `update_project` 返回的 `projectRevision`**，**不是** `read_project.revision.token`（后者实测必冲突 `REVISION_CONFLICT`）；冲突时**拒绝盲重试**，重读 + 字段级合并 + 用新 revision 重提 |
| **画布锁** | 同画布写操作串行（§2.2）；平台 Agent 活跃 run 会占住画布，写操作报 `AGENT_RUN_ACTIVE` |
| **先建后跑** | `create_node(run=false)` 只建不跑、同步返回 `node_key`；`run=true` 才生成、才计费 |

> **【已验证】** 平台自己把审批写进了接口语义：`update_node.run` 原文含
"生成可能消耗积分，必须有用户明确授权"。**外部编排无法预授权**（详见 21_ §6）。

---

## 8 · 变更 → 下游失效（沿引用链推，不凭记忆）

节点被 `update` / 重跑 / 替换后，**引用它的下游"现有结果全部作废"**（平台硬规则）。
排查范围**只能沿 `left` 实际引用链走**：

1. **直接引用该节点的全部下游** → 作废重做；
2. **续写链上的间接下游** → 衔接基础已变，整条链重做；
3. **完全没引用、也不续写的** → 可保留；
4. **合成节点必须在所有受影响镜头重做生效之后重新合成**（否则拼入旧画面）；
5. ⚠ **导演台场景 `revision` 变化不会自动级联失效**（与节点级级联作废是两条口径，按差异记）。

**优先改回同 key**：在原节点 `update_node(leftAdd=…)` 换边，**保留同一 node_key**，
避免"删节点换新 key 导致旧插桩全挂"。

---

## 9 · 校验入口与点火前清单

### 9.1 机器门禁

```powershell
python3 scripts/graph_plan_lint.py validate --plan <graph_plan.json> [--overlay <overlay.json>]
python3 scripts/graph_plan_lint.py gate     --plan <graph_plan.json> [--overlay <overlay.json>] --out gate_results.json
```

判 **§1 映射 legality**、**§2.1 位次**、**§3.2 派生字段只读**、**§3.3 settings 陷阱**、
**§4 边合法性/重复/悬空/成环**、**§5 分组归属**，并产出
**structure / reference / media / cost 四类 gate result**（符合 A 的 `gate_result.schema.json`）。

### 9.2 点火前清单（逐项打勾，缺一不点火）

```text
节点层
☐ node_type 在 6 档内（storyboard 已落成 image）
☐ audio 节点带 params.scene
☐ 没有直写 imageList / *Order / status / taskInfo
☐ update 改参时字段平铺在 params 顶层，且已回读确认值变了

连线层
☐ 参考位次在建节点时就定好（不指望事后重排）
☐ 每个被引用节点：在 left 里 + 在 prompt 里 {{key}} 插桩 + 已生效（三件套）
☐ 血缘（lineage）用纯文本登记，没有多加花括号
☐ left 里无重复 key、无废弃/失败节点 key
☐ 合成位是 video-clip，不是 text

顺序层
☐ 写操作逐条串行发（不并行 create）
☐ 幂等键"同键同文"
☐ 波次划分满足"被引用节点全部已生效"

变更层
☐ 若改过锚点：沿 left 链列出全部下游并重做
☐ 合成节点在所有受影响镜头之后重新合成
```

---

## 10 · 与其它册的关系

- **图语义（role / 四类边 / 权威层 / 不变量）** → A 路 `02_图语法_节点边分组参数.md`（**本文的上游**）；
- **模型、成本、并发、恢复** → `21_模型成本并发与恢复规范.md`；
- **回读与媒体验收** → `22_结构回读与媒体验收规范.md`；
- **三作回归** → `23_三作与合成场景回归测试.md`；
- **平台接口明细与原文佐证** → skill `references/libtv-canvas-nodes.md`、`libtv-node-topology.md`、
  `libtv-canvas-anatomy*.md`、`libtv-op-manual*.md`、`libtv-concurrency.md`。
