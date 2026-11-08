# LibTV 画布与节点全书（Agent 自主版）

> **何时读**：要把片子落到 LibTV、或要用它的画布/节点/API 干活之前。
> **读完回哪**：`run-sheet.md` 的站 6.5（投喂与生成）与站 6.6（剪辑与合成）。
> **本文性质**：**全部依据实测与接口 schema 原文**（2026-09-20，本库亲自跑过一遍全流程）；标【未核】的条目一律不当结论用。
> **★ 平台会变**：所有数字与能力以"截至 2026-09"为准，**引用带月份**。**★ 三本配套专册（2026-09-22）：计费与积分（计费点 / 单价 / 退分 / 预冻结 / 成本公式）→ `libtv-billing.md`；审核边界（文本·图像·视频三侧红线，每类带「被拦句 → 安全改写」）→ `libtv-moderation.md`；并发与 run 锁（节点级互斥 · 契约未暴露项 · 死锁五出口 · 两侧工具面映射表）→ `libtv-concurrency.md`。**

---

## 一、六种节点——一张片子就是一张节点图

**节点类型只有六种**（`create_node` 的 enum）：**⚠ 这句只在 `create_node` 这一层成立——客户端实际认识 19 个值（含 `group`/`video_group`/`script-v2`/`reference`/导演台与全景等），全表见 `libtv-node-types.md`。**

| 节点 | 装什么 | 它的产出 | 备注 |
|---|---|---|---|
| **text** | 文案 / 创意 / 提示词草稿 | 文本 | 画布上的"便签" |
| **image** | 图像生成与编辑 | 图片 | |
| **video** | 视频生成 | 视频 | 六型里最贵的 |
| **audio** | 音频生成 | 音频 | **`params` 里必须显式给 `scene`** |
| **script** | 剧本 / 分镜表 | **Script V2 表**（见 §四） | 导演台的数据源 |
| **video-clip** | 时间线片段 | 时间线上的一段 | **导出/合成的素材单位** |

**★ 三条结构性事实**：
1. **节点即资产**；**但"边"只是可视化**——**★ 平台原话（2026-09-20 修正）**："**一致性靠『锚点节点 + 在 prompt 里用 `{{node_key}}` 插桩』实现，不是靠画布连线。边只是可视化，真正起作用的是字段引用。**"
   → **`reference_nodes` 放 key ＋ prompt 里同序 `{{key}}` 插桩，这才是引用**（**这是"平台编排层"的口径**）。
   **★★ 但 2026-09-21 实测发现：在 MCP/画布层，口径相反**——`params.imageList` **不可直接设**（报 `NODE_VALIDATION_FAILED`），**必须用 `left` / `leftAdd` 建引用边**；建边后系统**自动重算出 `imageList` 与 `imageListOrder`**。
   **→ 所以我这一层必须连线，只是工具名叫 `left` / `leftAdd`。**（**完整六步链条与报错原文见 `libtv-model-params.md` §一**）
   `create_node` / `update_node` 都带 `left` / `right`，**提交是原子的**（节点 + 边 + 分组布局一起落）；
2. **生成不是建节点**：`run: false`（默认）只建/改节点，**`run: true` 才生成**；
3. **平台的自我约束写在 schema 里**：`update_node.run` 的原文是"**生成可能消耗积分，必须有用户明确授权**"——**平台自己把"审批"写进了接口语义**。

---

## 二、画布操作全景（写操作全部带锁与幂等键）

| 动作 | 工具 | 关键参数 | 注意 |
|---|---|---|---|
| **选项目** | `target_project` | `projectId` → 返回 opaque `projectContext` | 返回的是**会话级**上下文（"selections never change other conversations"） |
| **校验项目** | `read_project_context` | `projectId` 或 `projectContext` | 重新校验并给权威详情 |
| **读画布** | `read_project` | `view: summary / nodes / groups`，`group?` 限定 | 三种视图 |
| **生产快照** | `get_project_snapshot` | `section: manifest / graph / scripts / assets / shots / media / timelines / relations / issues / all`，`expectedRevision` 分页 | **revision 绑定**："changed projects are rejected instead of mixing versions" |
| **建节点** | `create_node` | `nodeType` + `params` + 引用边 + `run?` | 幂等键必填 |
| **★ 只建不跑（先建后跑）** | `create_node(..., run=false)` | 实测成功：`taskKind: canvas_operation`、**不生成、不花钱、同步返回 `node_key`** —— **这就是"批量先建后跑"在 MCP 侧的实现**（平台 Agent 说的是 `generate_image_v3 mode:"create"`；**我这一侧用 `create_node(run=false)` 达到同样效果**，视频节点则靠"先不调用、排好参数"） |
| **★ `params.settings` 的档位** | `quality` / `ratio` | **实测踩坑**：`params.settings.quality` 只接受 **`low / medium / high / xhigh / max`**（**不是**模型侧的 `1K/2K/4K`）；写 `"1K"` 会报 `NODE_VALIDATION_FAILED`。**→ 画布层与模型层是两套参数名，别混用。** |
| **改节点** | `update_node` | `newName / prompt / params / data` + **`leftEnsure/leftAdd/leftRemove` · `rightEnsure/rightAdd/rightRemove`** + 按接口 schema 决定的 revision 字段 | **引用边可增量改**（ensure = 确保存在，add = 加，remove = 去） |
| **删节点** | `delete_node` | `node` + 幂等键 | **下游输入会自动重算**；**不支持删分组** |
| **分组** | `manage_group` | `action: list / read / create / bind / run` | **`run` 提交"有序子任务工作流"**——★ 批量生成的正规做法 |
| **传素材** | `upload_ticket` → `upload_complete` | 分片上传（≤5GB，默认 5MB/片），完成得 opaque `file_ref` | 两步式；`file_ref` 供后续生成或 `resource_info` 使用 |
| **读素材** | `browse_project_media` / `inspect_media` / `resource_info` | | `inspect_media` 是**有界的审查证据**，不做 ASR、不重生成 |

**★ 两条纪律（agent 必备）**：
- **所有写操作都要带 `idempotencyKey`**：断了重试**不会生成第二个**（Reusing the same key recovers the original run without resending）；
- **写前按接口读取并携带该接口要求的 revision**：`update_project` 的乐观锁取上一次 `update_project` 返回的 `projectRevision`，不是 `read_project.revision.token`；冲突时拒绝盲重试，其他写接口按各自 schema 是否必填处理——**这就是"中断恢复"的地基**。

---

## 三、★ Agent 排他：`run_agent` 跑着的时候，你不能写画布

`get_agent_status` 原文：**"an active run holds the single-writer lock. Poll this before writing the canvas."**

> **★ 并发与锁专册 → `libtv-concurrency.md`（R26 · 2026-09-22）**：**平台侧把"单写者锁"修正为「节点级互斥」**（`run_node` 对正在生成的节点失败；**不同节点可分别运行**）· 契约未暴露项清单 · 死锁五出口 · `ask_human` 独占一轮 · **两侧工具面映射表**。**本节"画布级排他"的口径以该册为准。**

**→ 一条硬纪律**：**在 `run_agent` 有活跃 run 时写画布会被拒**。所以 agent 的顺序必须是：
**先 `get_agent_status` 确认无活跃 run → 再写画布**；要让远端 Agent 干活，就**把画面交给它，自己停手**。
（这也解释了官方那句"用户侧不做创作、只做传话"——**不是礼貌，是单写者锁**。）

**Agent 委托族**：
| 工具 | 用途 | 成本 |
|---|---|---|
| `run_agent(message, autoGenerate, idempotencyKey, skills?, ackUser?)` | 起一个 durable run | **`autoGenerate: false`＝只做规划、不生成媒体** ← **省钱关键** |
| `get_agent_status` | 读 run 状态 / 待答问题 / 产物 / 近期消息 | 免费 |
| `steer_agent_run` | **在同一 run 内**纠偏（不新建 run、不重新授权生成） | 免费 |
| `answer_agent_questions` | 回答它 pending 的问题（配 `toolCallId`） | 免费 |
| `stop_agent_run` | 停止；**未确认的 stop 会把该 session 隔离**（quarantine） | 免费 |
| `search_skill_templates` | **公开模板目录**（只给元数据，不给可执行指令）· **★ ＝1.5「导演分身」的落地接口**（实测查"导演"一页 20 条，全为 `libtv-user-generated/*`）；**一次只能挂 1 个模板**（`run_agent.skills` `maxItems: 1`） | 免费 |
| `ask_followup_questions` | 表单卡（最多 3 问） | 免费 |

**★ 一条实测陷阱**：`get_agent_status` **不能空手问**——不带 `runId` / `agentSession` 时它回 **`LEGACY_RUN_ID_REQUIRED: use the existing runId or agentSession`**（**它知道有历史 run，但拒绝自动选**）。
而 **`read_project_context` 里没有 runId 字段**（实测 87KB 响应里没有）→ **runId 只能由 `run_agent` 自己返回**。
**所以"接上旧对话"的正规顺序是**：先用 `run_agent`（新 idempotencyKey）拿 runId → 此后一律带 runId；**不要在没 runId 的情况下反复试 `get_agent_status`**。

**★★★ 与它对话：实测四项事实（2026-09-20 · 用户确认"agent 不计费"）**

| # | 实测事实（含原始错误码） | 含义 |
|---|---|---|
| **1** | `run_agent(autoGenerate:false)` **起得来、也跑得完**（再 steer 时回 **`AGENT_REMOTE_TERMINAL: This run has ended`**）；**全程零媒体**（画布节点数不变）；**agent 不计费**（用户交底） | **"问平台内 Agent"是零成本动作** → 遇到不明确的事，**先问它，别硬猜** |
| **2** | **它的回答读不到**：`get_agent_status` / `show_agent_progress` **都只回一句包装信息**（"状态来自远端回读；控制须使用精确 runId"），**没有 messages 字段**；**它也不会自己往画布写** | **回复没有落点＝外部 agent 拿不到** |
| **3** | **它会反问，而且会把整条链卡住**：steer 时回 **`AGENT_QUESTION_PENDING: Answer the current toolCallId with answer_agent_questions before steering`** → 必须用 `answer_agent_questions(feedback, toolCallId)` 作答；**而 `toolCallId` 在 MCP 侧读不到**（只在网页端的进度卡里） | **人在环里是产品设计，不是缺陷**：待答问题+`toolCallId` 走 UI 卡片。**自动化路线必须绕开它** |
| **4** | **活跃 run 独占画布**：只要它活跃，新 run 直接回 **`AGENT_RUN_ACTIVE: An Agent owns this canvas; inspect or stop its exact run first`**，**所有画布写入也被挡**。**★ 而且 `stop_agent_run` 之后所有权不立即释放**（schema 原话："**a stop request does not release canvas ownership**"，要 `get_agent_status` 读到同一个 run 终态才算释放） | **一个活跃 run 会锁死整条外部流水线** → **① 要么人在 UI 里答它；② 要么 `stop_agent_run` 后轮询等释放（未确认的 stop 会隔离该 session）；③ 起 run 之前先确认无活跃 run** |
| **5** | **幂等键与内容绑定**：同一个 `idempotencyKey` 换一段文案再发 → 回 **`IDEMPOTENCY_CONFLICT: This key belongs to different Agent input`** | **重试必须"同键同文"**；要改内容就得**换新键**（否则会被判成"同一次输入的冲突"） |

**→ 因此"外部 agent 与它对话"的正确协议有三条**：
1. **第一句就指定输出落点**（把回答变成可回读的工件）：
   > 「不要生成任何图片或视频。请把你的完整回答**写成一个画布上的文本节点（text 节点）**，节点名就叫 `Agent答疑_<主题>`。」
   读回来：`read_node("Agent答疑_<主题>")`。
2. **第一句就禁止反问**（否则它会停下来等你，而你读不到它在等什么）：
   > 「**不要向我提问**，遇到不确定的自行合理假设。」
3. **先查有没有活跃 run**（`get_agent_status(runId)` 或直接看新 run 是否被 `AGENT_RUN_ACTIVE` 拒绝）——**单写者锁是全流程级的**。

**★ 判据一句话**：**只要回复停在"流式消息"里，外部 agent 就读不到；把它变成"画布上的文本节点"，才成为可回读的工件**——这与本库"一致性靠传实物、不靠传描述"是同一条道理：**工件 > 消息**。

**★★★ 为什么"让它写画布节点"这条路不通（2026-09-20 二次修正 · 以平台 Agent 原话为准）**
**我上一轮把原因归错了**：我推断是"`autoGenerate:false` 没给 task-write scope"。**平台 Agent 本人给出的原因是**——
> **"我的工具集中没有 `generate_text` 这类『创建文本节点』的能力，调用直接被拒（`generate_text: tool not available`）"**；
> 它试过的替代也全不通："`create_resource_node` 只能挂载已有 URL / Resource ID 的媒体，**不能承载文本**，且必须带 url"；"画布检索显示**当前画布上没有任何 text 节点可供改写**"。
**→ 正确结论**：**LibTV 的 Agent 侧没有"建文本节点"这条通路（工具缺失）**，所以**"把回答写成画布节点"这个可读协议在平台侧不成立**。
**→ 与之并存的另一条机制仍然成立**：`autoGenerate:false` = planning-only context（"true permits media generation and **requires task-write scope**"）。
**→ 外部 agent 想读它的答案，只剩两条路**：① **人在网页端读进度卡 / 它落盘的答案文件**（**推荐**）；② 我方若能调 `read_file_v2` / `write_file_v2` 之类（**本会话的 MCP 工具集里没有**，48 个工具里无此类）。

---

## 四、Script V2＝导演台的数据源

**建表**：`create_script_v2(name, rows[], assets?, idempotencyKey)`——**明写"不生成内容或媒体"＝零成本**。
**行字段**（每行＝一个镜头，`durationSeconds` 1–15 必填，镜号按行序自动编）：

| 字段 | 对应本库 |
|---|---|
| `shotSize` | 景别 |
| `plotDescription` | 画面内容 |
| `emotion` | 情绪 |
| `lightingAndAtmosphere` | 光位与影调 |
| `audioEffects` / `dialogue` | 声音 / 台词 |
| `characters[{characterAssetId, characterName}]` · `sceneAssetIds` · `propAssetIds` | **资产绑定** |
| **`imageGenerationPrompt` / `videoMotionPrompt`** | **★ 派生字段**（见下） |

**★★ 一条重要发现**：后两个字段是**派生**的——你留空，它报 `STALE_SHOT_PROMPT`（提示词已过期）。
**→ 平台的提示词是从"分镜行"自动推导出来的，不是手写的。** 这解释了它为何**欢迎结构化分镜、却不欢迎你替它写完整提示词**。

**读与查**：`read_script_v2`（行 / 资产 / issues）· `check_continuity`（**逐对相邻镜 9 类事实对比** + 9 条看片项 + 3 条"没证据不能判"）· `edit_script_v2`（`update_shot / insert_shot / delete_shot / move_shot / split_shot / merge_shots`；**明写"does not generate media or prompts"**→ 改行**不会**重算提示词）。

---

## 五、时间线与导出：**能编不等于能出**

**时间线**：`read_timeline`（读，不渲染）· `apply_timeline_edit`（`mode: plan` 免费；**"editing never starts a render"**）——支持 `insert_clip / trim_clip / split_clip / move_clip / ripple_delete / set_transition / align_audio / set_gain / set_speed / set_transform`。

**★★ 陷阱（实测）**：`export_readiness` 返回的 `executionContract.unsupported` 明写导出层**不支持**：

> `speed` · `transitions` · `transforms` · `subtitles` · `per_clip_volume` · `per_track_volume` · `audio_source_trim`

**→ 在时间线上设了转场 / 变速 / 变换 / 字幕，导出时会静默丢弃。**
**交付纪律：转场与变速回本地剪辑软件做；字幕不要在平台内加。**

**导出的真实行为（实测）**：`videoOrder: concatenate_in_list_order` · `videoRange: source_seconds` · 合成器 `model: media-platform`（**非生成模型**）。
实测把 2s + 8s 直拼成 **10.00s** 成片，**拼接点整体平移 +2.000s 一一对应** → **按列表顺序无损直拼**。
**★ 另一条**：**导出会强制生成一条音轨**——源视频都没有声音，成片里仍出现 `aac 48kHz stereo 2kb/s`（≈静音）→ **"零音轨"只能要求到源素材层**。

---

## 六、成本地图（决定"什么可以大胆做"）

| 动作 | 成本 |
|---|---|
| `read_project` / `read_node` / `get_project_snapshot` / `browse_project_media` / `inspect_media` | **0** |
| `create_script_v2` / `read_script_v2` / `edit_script_v2` / `check_continuity` | **0**（明写不生成媒体或提示词） |
| `read_timeline` / `apply_timeline_edit`（含 apply） | **0**（"editing never starts a render"） |
| `export_readiness` | **0**（只校验素材可读） |
| `validate_generation_plan` / `generate_video(run:false)` | **0**（预检） |
| `search_models` / `get_model` / `recommend_video_models` | **0** |
| `run_agent(autoGenerate:false)` | **0 媒体任务**（本次 `autoGenerate:false` 只写文本；不外推为“对话一定免费”） |
| **`generate_video(run:true)` / `generation_submit` / `create_node(run:true)`** | **★ 花积分**（生成图片 / 视频 / 音频） |
| **合成 / 剪辑 / 音频编辑** | **★ 也花积分**（**修正**：我原先猜"合成导出大概率不计费"——**平台 Agent 明确说"合成/剪辑"消耗积分**） |
| `export_video` | 走 `media-platform` 合成器，但**属"合成"→ 计费**（实测那条 10 秒成片很可能已扣费） |

**★ 平台侧给的成本量级（2026-09-20 · 来自 LibTV Agent 本人 · 以其口径为准）**：
- **量级**：**8 秒 480P ≈ 几十积分** · **1K 图 ≈ 个位数到十几积分**（随模型浮动，以平台结算为准）。
- **★ 返还口径两版有差**：2026-09-20 版＝**「只有生成失败的节点返还积分，其他情况不返还」**；**R24（2026-09-22）版＝生成失败 / 审核拒绝 / 超时全额原路退、手动取消看阶段** → **以 R24 为准**（更晚、更细），见 `libtv-billing.md` §五。

**结论**：**结构、读取与预检免费；媒体生成、合成、剪辑、音频编辑和导出按动作计费，具体以 R24/计费页为准。** → **抽卡克制，剪辑大胆。**

---

## 七、平台自己写明的边界（照抄，不许当耳旁风）

- `export_readiness.evidenceBoundary`：**"Sources are readable; rendering and playback are not verified."** → **预检通过 ≠ 渲染正确**；
- `get_agent_status`："**Reading data back is not playback or visual acceptance.**" → **读回数据 ≠ 验收**；
- `check_continuity.limitations`：**"角色外观、服装、空间轴线、光照、动作接续和色彩连续性必须查看实际像素/视频后判定"**；
- `search_skill_templates`：**"returns metadata, not executable Skill instructions"**。

**★ 这四条合起来是一句话**：**平台把"机器能判的"和"只能看片的"分得很清**——**这恰好是我们门禁该学的姿态**。

---

## 八、常见陷阱清单（踩过的）

| # | 陷阱 | 后果 | 正确做法 |
|---|---|---|---|
| 1 | **模型有 `prompt.maxLength`**（实测 Wan 3.0 = **3000 字**） | 超长被截断，**末尾的计数约束与不变项先丢** | 投喂前数字符；先压"形容词"，不压约束 |
| 2 | **`apply_timeline_edit` 支持 ≠ 导出支持** | 转场/变速静默丢失 | 见 §五 |
| 3 | **导出强制加音轨** | "零音轨"判据失效 | 判据只到源素材层 |
| 4 | **Agent run 独占画布写权限** | 你在它跑的时候写会被拒 | 先 `get_agent_status` |
| 5 | **改 Script V2 行不重算提示词** | 以为改了行提示词就更新了 | 派生字段要它自己重算，别指望 edit |
| 6 | **`get_capabilities` 的 `pluginSupport` 多为 `partial`、`parityVerified: false`** | 以为 MCP 与网页端能力完全对等 | **客户端专属功能（3D 导演台摆白模、宫格切分的 UI、扫码）在 MCP 里没有** |
| 7 | **白模／火柴人预演** | 以为有专门接口 | MCP **没有** previs 工具；正路是**上传白模视频当参考**（`video2video` / `frames2video` / `mixed2video`） |
| 8 | **prompt 里的 `{{...}}` 会被校验成真引用**（2026-10-01 平台 Agent 实测撞过） | 正文里举例写的 `{{X}}` 若 `X` **不存在**，创建直接拒（`node-key closure failed ... missing=...`） ——平台当真引用，不允许用空 reference_nodes 「清掉插桩」伪装通过 | 只写**真实存在的 node_key**；讲机制的示例改用 `『』` 记法（平台 Agent 就是这么规避的）。**空花括号 `{{}}` 实测不触发**，有内容的才会（我方 10 节点全量核过：无悬空插桩）|

---

## 九、★ 平台侧官方口径（**2026-09-20 · 来自 LibTV Agent 本人 · 本库最高优先级的一手源**）

> **来源**：LibTV 平台内 Agent 的完整回答（**全文已落成 `libtv-official-qa.md`** —— **那是本库关于 LibTV 的最高优先级一手源**，凡与本文冲突以它为准）。
> **获取方式**：它用 `write_file_v2` 落盘为 `answers/Agent答疑_工作流.md`；**我方 MCP 侧无 `read_file_v2`** → 由用户下载到本地后我方读取（见 §十·补）。
> **与本文关系**：本文只放**摘要**；**细节、原文、具体工具名一律看 `libtv-official-qa.md`**。

**★ 2026-10-01 校正（这份缺口清单写在 2026-09-20，已大面积过期）**：原列的 5 处里，实测只剩 **① 时序锚点（语速 / 镜头时长）** 一处真缺；② 派生锚点→`asset-consistency.md`§一·补 ③ 尾帧拉回→`asset-and-stage-checklist-part2.md`§8.7（每 N 镜拉回） ④ 代际退化防治→`pipeline-cross-source-consensus.md`§一·4/ §三·3 ⑤ 插桩写法→`libtv-op-manual.md`§2.2 与 `libtv-op-manual-part3.md`§28.1。**→ 下一个 agent 读到这里不要重做已补的四项**。
**★ 另一个要回抄的"为什么"**：它说资产图要 **中性、正面、无强透视、无复杂光影**，理由是"**这样它作为参考时不会把奇怪的构图带进每个镜头**"——**这正是本库"纯中性灰底 / 柔光近乎无影"的成因**，建议补进 `asset-consistency.md`。

### 9.1 它给的**标准工作顺序**（八步）
**剧本 → ① 拆锚点（主体 / 构图 / 时序，三样必配）→ ② 游标式拆分镜（≤10 镜/批）→ ③ 资产图定妆 → ④ 参考素材建边 → ⑤ 镜头生成 → ⑥ 合成 → ⑦ 归档**

### 9.2 ★★ 防漂移三条硬规则（**平台方原话**）
1. **每镜必带主体锚点**；
2. **同角色同 `node_key`**；
3. **新增特征走"派生锚点"**（不要改原锚点）。

### 9.3 一致性机制的组合用法（**修正了本库"二选一"的理解**）
- **资产图参考 = 身份一致性的主机制**；
- **尾帧续接 = 管动作连贯**；
- **★ 两者可同时用**：**尾帧做首帧 ＋ 资产图进 `reference_nodes`**；
- **`frames2video` 适合**：**精确起止画面**、**转场桥接**；**不适合**：**自由表演**与**长动作段**。

### 9.4 分组与 run 的用法
- **按"同生共死"判断是否分组**（要一起生一起死的才放一组）；
- **`group.run`** 用于**参数齐备的批量**；**单节点 `run`** 用于**调试 / 重跑 / 样板镜**；
- **推荐：先跑一个样板镜，再批量。**

### 9.5 Script V2 的分工（**关键：事实层 vs 表达层**）
- `imageGenerationPrompt` / `videoMotionPrompt` 是**系统自动推导的初稿**；
- **我方填"事实层"**：**景别 / 情节 / 情绪 / 光 / 声音 / 台词 / 资产绑定 / 时长**；
- **系统出"表达层"**；**只在有硬约束或特殊风格时才手写覆盖**。

### 9.6 ★ 它如何处理我们的提示词（**推翻了我"会被重写"的担心**）
- **硬约束照做、不重写**——**"恰好 N 段、N-1 个切换点""机位锁死只变焦"这类原样保留**；
- **只做"补"，不做"改"**；**台词一字不改**；**不擅自加配乐**；
- **无 3000 字硬上限**（**修正**：3000 是**单个模型 schema** 的限制，**平台级没有**）；
- 建议：**单镜 200–800 字 · 结构化分段 · 硬约束靠后编号**。

### 9.7 ★ 它眼里"最被低估的提效点"（12 项 · 我们大多没用上）
**主体库（资产库）· 镜头聚焦 `look_at` · 影视级灯光控制 · 尾帧续写 · 9/25 宫格 · 角色与场景三视图 · 首尾帧预测 · 导演台 · 风格展示板 · 派生锚点 · 灯光修正 · 批量"先建后跑"**。

---
## 十、→ **已分卷**

> 跨 Agent 通信协议（让它把答案写进「我能读的容器」· 读回协议·
> 「我这一侧到底能读哪几类东西」判据）已迁入 **`libtv-agent-protocol.md`**。
> **节号保留空位**（不改号）——按节号引用它的地方仍有一个可追的入口。

---

## 十一、网页端画布服务层（**REA 静态 · 2026-10-15 · 模块 `984954`**）

| 别名 | 端点 | 已观察合同 |
|---|---|---|
| `gg` | `POST /api/canvas/nodes/batch` | `{projectUuid,nodes:{create,update,delete},connections,requestId}`；节点 `data` JSON 会清掉 `blob:`/`data:` URL |
| `z6` | `GET /api/canvas/node/detail` | 重复 `nodeKeys` query，可带 `withConnection=true`；异常返回 `undefined` |
| `ia` / `Z4` | `extra-config/get` / `update` | `GET {canvasId}` 只在 `code===0` 返回 `data`；`POST {canvasId,extraConfig,...}` |
| `TO` | `POST /api/canvas/node/rating/set` | `{projectUuid,nodeKeys,rating,teamId?}`；本地先乐观更新，远端失败回滚；评分归一为 **1–5，否则 0** |

**分片/413（静态）**：node/edge 的 create/update/delete 总数 **>200** 才预分片，且每类数组各按 **200** 切；HTTP **413** 强制重分，仍失败则标记 `__blockedBy413`。项目深拷贝固定 **200 节点/批、500 连接/批**；同步 `buildPayload` 可带 `version`，但运行时 body 未保留，不能写成必填。

**真实用途**：`z6` 服务协作补偿、删除/重建权威查询与批量详情；`gg` 服务同步、深拷贝和 handoff；`ia/Z4` 读写 `storyboardMode`；`TO` 服务节点/产物评分。**`artifact-version/get|save` 在网页端只有 2 个定义 token、0 个非定义引用；恢复 CLI、官方 CLI 文档与插件对照也均 0 命中，契约保持 unknown。**

**CLI 差异（恢复载荷静态）**：CLI 同样清洗 `blob:/data:`，但 `nodesBatch` **不写 requestId、不分片、不处理 413**；`version/sessionId/timestamp` 均按调用路径可选，`code===0` 后可向配置的会话发 `canvas_patch` 回调。网页端的 200/413 规则不可直接套到 CLI。

---

## ★★★ 提示词引用记号的真实协议（**REA 静态 · 2026-10-15 · 编辑器 bundle 模块 677418**）

> **为什么单列**：本库此前只知道"要插桩、要有边、要在文字里声明"，**不知道平台认的确切记号**。现在拿到了正则与全部变换函数。

**客户端解析的是这五档记号（数字 1-based，含空格）**——**服务端另有一套 `{{Node "<名称>"}}` 解析**（按名称、且要求已连线），两者的分账见 `libtv-prompt-structure.md`「引用记号有两套体系」：

```text
{{Image N}}    {{Portrait N}}    {{Video N}}    {{Audio N}}    {{Mixed N}}
```

**对应关系**：`Image` 与 **`Portrait` 是同一槽**（都映射到 `imageList`）· `Video → videoList` · `Audio → audioList` · `Mixed → mixedList`。

**提交前会做的四种重写（逐字）**：

| 变换 | 行为 |
|---|---|
| `Portrait → Image` | **`{{Portrait N}}` 提交前一律改写成 `{{Image N}}`**（Portrait 只是输入别名） |
| 用 mixedList 时 | **`{{Image/Video/Audio N}}` 被改写成对应的 `{{Mixed M}}`**（M 是该素材在 mixedList 里的序号） |
| 非 mixed 时 | **`{{Mixed M}}` 被还原成该项 `mediaType` 对应的 `{{Image/Video/Audio N}}`** |
| **找不到对应素材项** | **该记号连同它前面的换行整段被删除（返回空串）——不报错、不保留** |

**★ 三条会咬人的后果**：
1. **写错序号＝静默掉内容**：提示词里写 `{{Image 3}}` 而实际只有 2 张图，**提交时这一段直接消失**（既不报错也不留痕）⟶ **必须回读"最终提交的 prompt"，不能只看自己写的那份。**
2. **`asset://` 引用不进 `refMap`**：`refMap` 只为真实 nodeId 生成；`asset://<assetId>` 的项被跳过。
3. **`refMap` 的键是"提示词原文里的那个记号"**（如 `"{{Image 1}}": "<nodeId>"`），不是序号本身 ⟶ 交付留证时可直接用它核"我声明的引用到底上报了没"。

**另有一个"URL→短 token"机制**（用于把长 URL 写进提示词的场景）：文件名取前 **8** 个字符（去扩展名/花括号/空格）生成 `{{名字}}`；**重名时追加 `~2`、`~3`**；同时产出 `refUrlMap`。

**prompt 归一化**：提交前统一做「连续空格压成一个、三连换行压成两连、首尾去空白」（**`{{Portrait N}}` → `{{Image N}}` 也会顺带过这一道**）。**★ 与真实画布用法的差异（`{{Node <uuid>}}` / `@ImageN` 不被解析）见 `libtv-prompt-structure.md` 的「引用记号有两套体系」一节——本册讲平台认什么，那册讲真实画布写什么。**

> **★ 拆册指引（2026-10-15）**：本册 279 行已贴顶，**合成层（`video-clip` / 时间线）的字段细则已拆到 `libtv-compose-timeline.md`；`audio`/`text`/`script`/`storyboard` 四类字段补遗在 `libtv-node-field-notes.md`**——`clipTimelineData` 的四个必填项、静音字段"文档意图 vs 实测"冲突、两条合成路径、图片九宫格 shortcut 映射都在那册。**往本册加内容前先拆册。**
