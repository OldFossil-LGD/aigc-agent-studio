# LibTV 实时通道与前端工具（FE Tool RPC）

> **来源**：登录态编辑器 bundle（REA 静态 · 2026-10-15）。
> **为什么单列**：`libtv-platform-watch.md` 已顶格 300 行；而"**平台怎么通过实时通道驱动浏览器侧工具**"
> 是本库此前**零记录**的一层——它解释了"Agent 面板为什么能操作画布"。
> **读完回哪**：`libtv-platform-watch.md`（平台监测与宿主表）· `libtv-web-api-shapes.md`（请求形状）· `libtv-op-manual.md`（点火前置）。

---

## 一、一个画布 store 一条连接

- 连接状态存在 **`WeakMap: store → { projectId, listeners:Set, connection?, opening? }`**；
- **`projectId` 变即关闭旧连接**；并发 `open` 用**同一个 `opening` Promise 去重**；
- await 回来后**二次校验** listeners 与状态，不匹配就 `close()`；
- 构造客户端时 **`inheritAgentQuery: false`** —— **不继承页面 URL 的 `agent_name` / `agent_version`**，改用显式 `agentName`；
- 事件默认**逐个 listener try/catch 广播**，**但 `fe_tool_*` 一族被专用处理器截胡**（见下），不进通用监听器。

## 二、★★★ FE Tool RPC：平台 → 浏览器工具

### 2.1 四个事件名（逐字常量）

```text
fe_tool_call / fe_tool_cancel / fe_tool_receipt / FE_TOOL_ERROR
```

另有三个**出站帧类型**：`fe_tool_ack` · `fe_tool_progress` · `fe_tool_result`。

### 2.2 入站分派（逐字）

```text
type === "fe_tool_receipt"        → onReceipt(e)
type.toUpperCase() === "CUSTOM" 且 name === "fe_tool_call"   → onCall(e.value, e.sessionUuid ?? "")
type.toUpperCase() === "CUSTOM" 且 name === "fe_tool_cancel" → onCancel(e.value)
```

### 2.3 `onCall`：**先 ack，再执行**（顺序是契约）

1. 校验 `value.requestId` 与 `value.toolName`，缺任一**直接忽略**；
2. `sessionId = sessionUuid || 当前会话 || ""`；
3. **同 `requestId` 已有已结算记录 → 直接重发上次的 `resultFrame`**（**幂等重放**）；
4. **立刻发 `fe_tool_ack {requestId, sessionUuid}`**；
5. 会话被抢占 → 走 `rejectByPreempt`；
6. 查工具注册表（模块 `320293` 的 `d(name)`）：**没注册 → 立刻回
   `fe_tool_result {status:"unsupported", error:{code:"FE_TOOL_UNSUPPORTED", message:"frontend tool \\"<name>\\" is not registered"}}`**；
7. 建记录 `{requestId, sessionId, controller: AbortController, timer, settled:false}`；
8. **超时**＝ `value.timeoutMs ?? tool.timeoutMs ?? 30000` → abort(`"timeout"`) 并删记录；
9. 交给 handler 的 `ctx` ＝
   `{toolCallId, sessionId, projectId, canvasId?, runId?, signal, reportProgress(p, msg)}`，
   `reportProgress` 发 `fe_tool_progress {requestId, progress, message}`；`args = value.args ?? {}`。

### 2.4 结果帧与状态映射（逐字）

```text
基帧：{ type:"fe_tool_result", requestId, sessionUuid }
成功：{ ...基帧, status:"ok",          result: data ?? {} }
失败：{ ...基帧, status:"error",       error:{ code, message } }
      其中 code === "rejected"    → status:"rejected"
           code === "unsupported" → status:"unsupported"
          code 为空                → "FE_TOOL_ERROR"
          message 默认 "frontend tool failed"
```

### 2.5 取消、回执与结算

- `onCancel(value)`：有 `requestId` 且记录未结算 → 清计时器 + `abort(value.reason || "cancel")` + 删记录；
- `onReceipt(e)`：**`e.accepted === false` → 删掉该 `requestId` 的记录**（服务端没收下）；
- `settleWithFrame`：**已结算的记录直接返回**（不重复结算）；**没有记录时会补建一条"已结算、只存 resultFrame"的记录**
  ——**这正是"重试能重放结果"的实现基础**。

## 三、★ 单活标签页模型（最容易咬人的一条）

```text
document.visibilityState === "hidden" → 先问 checkSessionActive()
  返回 "inactive" → rejectByPreempt
rejectByPreempt → 发 FE_TOOL_ERROR，原文要点：
  "This browser tab no longer holds the active canvas session
   (the canvas was opened in another window), so the call was not applied.
   Retry it so it can be routed to the active window."
```

**→ 判据**：**同一画布在另一个窗口打开时，本窗口的 FE 调用会被拒**，且报错**明确提示"重试以路由到活跃窗口"**。
排障时遇到这条错误，**不是 bug，是单活模型**。

## 四、工具注册表（同源）

- `registerAgentTool({name, handler})`：**`name` 必填、`handler` 必须是函数**，否则抛错；
  返回**注销函数**（内部用 `Symbol(name)` 做 owner 防误删）；
- `d(name)` 查表返回 `{tool}`；
- **未注册的工具不会静默失败**，而是回 `status:"unsupported"`（见 2.3 第 6 条）。

## 五、限制

1. 全部为静态实现证据；**未建立连接、未触发任何 FE 调用**；
2. `fe_tool_call` 的 `value` 里除 `requestId/toolName/args/timeoutMs/canvasId/runId` 外的字段未展开；
3. **工具清单（谁注册了哪些 `name`）未枚举**——只知道注册/查询/未注册三态；
4. 服务端侧的 `fe_tool_receipt` 语义（除 `accepted:false` 删记录外）unknown。

---

## 六、事件协议：**CopilotKit + AG-UI**（2026-10-15 补）

### 6.1 事件词表就是 AG-UI 标准集（逐名实测命中）

```text
RUN_STARTED · RUN_FINISHED · RUN_ERROR
TEXT_MESSAGE_START · TEXT_MESSAGE_CONTENT · TEXT_MESSAGE_END
TOOL_CALL_START · TOOL_CALL_ARGS · TOOL_CALL_END · TOOL_CALL_RESULT
STATE_SNAPSHOT · STATE_DELTA · MESSAGES_SNAPSHOT
ACTIVITY_SNAPSHOT · STEP_STARTED · STEP_FINISHED · CUSTOM
```

**run / text message / tool call / state / messages / activity / step 六族齐全 + `CUSTOM` 扩展位**
——**不是自造词表**；端点 `/api/copilotkit`（**只在登录态编辑器 bundle 出现**，公开 bundle 没有）。

**→ 结构判据**：**事件流走 CopilotKit/AG-UI（`/api/copilotkit`）；
工具执行走实时通道的 `fe_tool_*` 帧；工具注册由 React 组件完成。三者是三件事，排障时先分层。**

### 6.2 工具名比对前会**归一化**

```text
归一化 = trim → toLowerCase → 空白压成 "_"
被特殊对待的工具名之一 = "write_file"
TOOL_CALL_START / TOOL_CALL_RESULT 两支都认它；名字取 toolCallName ?? name
ACTIVITY_SNAPSHOT 的 activityType 走同一套归一化后比对
```

**★ 含义**：**"活动快照"与"工具调用"在这一层是并列通道**；
工具名大小写/空格差异**不会**导致漏匹配（客户端自己归一化了）。

### 6.3 FE 工具用 React hook 注册（**描述符六字段**）

```text
useFrontendTool(tool, deps = []) → useEffect 里注册 → 返回注销函数（卸挂自动注销）
描述符 = { name, description, parameters, timeoutMs, handler, available? }
handler 走 useRef 转发（重渲染不用旧闭包）；deps 控制重新注册
```

**★ 为什么静态数不出工具清单**：**`name` 来自组件 props（`ref.current.name`），不是字面量**——
本轮在整个 bundle 里**只找到这一个注册调用点（hook 自身）**，**没有任何组件级字面 `name`**。
**→ 要拿工具清单只能运行时观测注册调用。**

---

## 七、AG-UI 事件**逐事件字段**（模块 `361769` 的 zod schema · 2026-10-15 补）

> **★ 取代 §6.1 的 17 名词表**：那张由字符串计数得来，**枚举实际有 33 个成员**（＝联合 33 个 schema）；
> 漏的是 `*_CHUNK` · `THINKING_*` · `ACTIVITY_DELTA` · `RAW` · `REASONING_*` 各族。

**基类**：`{type, timestamp?, rawEvent?}` ＋ **`passthrough`**（**服务端多给字段不会导致客户端校验失败**）。

- **文本**：`TEXT_MESSAGE_START{messageId, role="assistant"}` · `CONTENT{messageId, delta≠空串}` · `END{messageId}` · `CHUNK{messageId?, role?, delta?}`
- **工具**：`TOOL_CALL_START{toolCallId, toolCallName, parentMessageId?}` · **`ARGS{toolCallId, delta}`（参数是流式增量！）** · `END{toolCallId}` · `RESULT{messageId, toolCallId, content, role="tool"?}` · `CHUNK{四字段皆可选}`
- **思考**：`THINKING_START{title?}` · `THINKING_END{}` · `THINKING_TEXT_MESSAGE_{START,END}{}` · `THINKING_TEXT_MESSAGE_CONTENT{delta}`
- **状态/消息**：`STATE_SNAPSHOT{snapshot:any}` · `STATE_DELTA{delta:any[]}` · `MESSAGES_SNAPSHOT{messages[]}`
- **活动**：**`ACTIVITY_SNAPSHOT{messageId, activityType, content:Record, replace=true}`** · `ACTIVITY_DELTA{messageId, activityType, patch:any[]}`
- **运行/步骤**：`RUN_STARTED{threadId, runId, parentRunId?, input?}` · `RUN_FINISHED{threadId, runId, result?}` · `RUN_ERROR{message, code?}` · `STEP_STARTED/FINISHED{stepName}`
- **推理**：`REASONING_START/END{messageId}` · `REASONING_MESSAGE_START{messageId, role="reasoning"}` · `REASONING_MESSAGE_CONTENT{messageId, delta≠空串}` · `REASONING_MESSAGE_END{messageId}` · `REASONING_MESSAGE_CHUNK{messageId?, delta?}` · **`REASONING_ENCRYPTED_VALUE{subtype:"tool-call"|"message", entityId, encryptedValue}`**
- **旁路**：`RAW{event, source?}` · **`CUSTOM{name, value}`**（**`fe_tool_*` 就走这支**）

**请求侧（上行）**：**`RunAgentInput{threadId, runId, parentRunId?, state, messages[], tools[], context[], forwardedProps}`**；
`Tool = {name, description, parameters}`——与 §6.3 的 hook 描述符前三个字段对齐。**判别键**：下行 33 个 schema 合成 **`discriminatedUnion("type")`**。

---

## 八、AG-UI 数据模型与传输入口（2026-10-15 补）

- **传输入口**：CopilotKit provider 逐字 `runtimeUrl="/api/copilotkit"` ＋ `agent`；
  **组件卸载 → `agent.disconnect()`**；**`onPreempted(reason)` → 落埋点（含 `projectId`）→ `disconnect()`**
  ⟹ **这正是报告 40"单活标签页模型"的上行侧证据**；
- **消息＝7 角色判别联合** `discriminatedUnion("role")`：
  `developer` / `system` / `assistant` / `user` / `tool` / `activity` / `reasoning`；
  **只有 `user` 的 `content` 可以是多模态块数组**，其余角色都是纯字符串；
  **`activity` 带 `activityType`**——与下行 `ACTIVITY_SNAPSHOT` 同名同义；
- **内容块**：`{type:"text", text}` 或 `{type:"binary", mimeType, id?, url?, data?, filename?}`；
  **二进制块必须给 `id`/`url`/`data` 至少一个**（逐字报错 `BinaryInputContent requires at least one of id, url, or data.`）；
- **`assistant.toolCalls`**：`{id, type:"function", function:{name, arguments}, encryptedValue?}`
  ——**`arguments` 是字符串**（与下行 `TOOL_CALL_ARGS` 的流式 `delta` 对得上）；
- **`Context = {description, value: string}`**（注意 value 是字符串）· **`Tool = {name, description, parameters}`**；
- **agent 客户端已知方法**：`disconnect()` · `getProjectId()`。

---

## 九、跨 bundle 复核（公开站 vs 登录态编辑器 · 2026-10-15/16）

两套产物**都在本地可比**：登录态编辑器 **146 脚本** · 公开首页 **87 文件**
（`05_网页bundle与sourcemaps/scripts/`）。本轮把前几节的结论在**公开包上重跑了一遍**：

- **★ `directorVcamSignalBase`（值 `wss://im.liblib.tv`）＝有界负结论**：
  **两包各只出现 1 次、都是配置定义本身**，**非定义引用 0/0**；
  `vcamSignal` / `virtualCamera` 两包均 **0** ⟹ **该信令通道协议 unknown**。
  三种可能解释（**均未验证**）：懒加载 chunk / 其它客户端（桌面端·3D-BOX 独立页）/ 废弃配置残留。
  **纪律：`配置里有` ≠ `客户端会用`**——与端点那份 `declared-only` 清单同一类判断。
- **★ `remoteConfig` 27 条 id 表跨包逐条一致**（`name=id` 序列相等，`identical=true`）
  ⟹ **构建期固化常量**，不是登录后下发；**"网络面板看到 `?id=186` ＝ cameraControl"这条判据对公开站同样成立**。
- **★ `/ws` 项目消息通道在公开首页也存在**（`097kwell1h_-9.js` 里同构的连接构造：
  `token` 取自 cookie、`project_id`、`canvas_id`）⟹ **它是"画布能力"，不是"编辑器专属能力"**；
  **是否真的被公开站调用，本轮未观测**（只读静态）。

---

## 十、活动（activity）词表、`write_file` 处理与 agent 交接（2026-10-15/16）

### 10.1 ★ 工具结果 → **UI 面板刷新映射**（不是轮询，是显式派发）

| 触发 | 刷新目标 | reason |
|---|---|---|
| `write_file` 相关事件（含 `ACTIVITY_SNAPSHOT.activityType=write_file`） | **`project-files`** | `write_file` |
| `TOOL_CALL_RESULT` 且工具名归一化后 `save_asset` | **`media-assets`** | `save_asset` |
| `TOOL_CALL_RESULT` 且工具名 `create_canvas` / `update_canvas` | **`canvas-list`** | `create_canvas` |

**→ "面板没刷新"先查这三个名字有没有对上**；工具名取 `toolCallName ?? name`。

### 10.2 工具卡元数据（每个工具四态文案）

`write_file` 在工具卡表里逐字为：`icon: TextFile` ＋
`chatToolMetaWriteFileProcessing` / `…WriteFileDone` / `…WriteFileFail` / `…WriteFileGrouped`（**带 count**）。
同表还有 `analyze_media` · `show_optimized_prompts` · `select_canvas` 等。

### 10.3 ★★ 活动词表与**双命名容错**

已读到的 `activityType`：**`write_file`** · **`skill_created` / `create_skill_biz`**（同一集合）·
**`skill_draft_saved`** · **`memory_recall_status`** · **`action_power_usage`**。

**★ 全部解析器都写成"先 snake_case 再 camelCase"**（`skill_uuid ?? skillUuid` ·
`skill_name ?? skillName` · `cover_url ?? coverUrl` · `toolCallId ?? tool_call_id`）
⟹ **我方解析活动载荷必须同样两写兼容**，否则字段一改命名就漏读。

### 10.4 ★★ 每种活动的关键字段

- **`action_power_usage`**：`{actionId, llmPower, toolPower, totalPower}`；
  `totalPower` 缺省＝`llmPower + toolPower`；**总数 ≤0 则不渲染** ⟹ **"没卡片"≠"没消耗"**。
  （**已同步进 `libtv-billing.md`**——这是"单动作消耗拆成 LLM/工具"的通道。）
- **Agent → Agent 交接**：`dst_agent_name` ＋ `prompt`（**两者齐备**才成卡），另带
  `dst_agent_session` · `source_agent_name` · `source_agent_session` · `tool_call_id` ·
  **`mode ∈ {"adapt","create"}`**（其它值被丢弃）。**平台自己有显式的跨 Agent 交接载荷。**
- **技能卡**：`skillUuid` · `skillName` · `namespace` · `skillKey` · `name` · `description` ·
  `coverUrl` · `version` · `bizType` · `resultType` · `createdAt`；
  **`skillName` 含 `/` 时按第一段拆 `namespace`**，否则退化为 `skillKey`。
- **草稿卡**：`draftUuid` · `skillName` · `namespace` · `skillKey` · `name` · `description`。

---

## 十一、★★ 工具调用参数：线上是字符串、流式拼接、两段解析（2026-10-15/16 补）

> 出处：编辑器模块 `1oc_ktipvjr7m.js`；**公开站 `13k5_nrh7be-1.js` 里是同一份实现**（只换了压缩别名）。

- **schema（逐字）**：`object({name:string, arguments:string})` ＋ 外层
  `{id, type:"function", function, encryptedValue?}` ⟹ **`arguments` 是字符串，不是对象**；
  同形的 Protobuf 编码：`name` ＝ **field 1** · `arguments` ＝ **field 2**（**空串不写**）。
- **怎么攒出来**：`TOOL_CALL_START` 建 `{function:{name, arguments:""}}` →
  `TOOL_CALL_ARGS` 做 **`c.function.arguments += delta`**（**纯字符串相加、无分隔符**）→ `TOOL_CALL_END` 解析。
  找不到调用时**只 `console.warn` 一句 `TOOL_CALL_ARGS: No tool call found with ID '<id>'` 并跳过**，**不抛错**。
- **★ 两段解析，失败都静默**：流中用**手写增量 JSON 状态机**（`topLevel` / `string` / `number` / `arrayNeedsValue` …，
  只保留最后一个"完整值"边界）产出 `partialToolCallArgs`；结束时用 **`JSON.parse`**。
  **两者都 `try {} catch {}` → `{}`** ⟹ **参数坏了不报错，只会变成空对象**。
- **⚠ 一处没有容错**：把消息转成 `AgentStateMessage.state` 时 `arguments: JSON.parse(...)` **不在 try/catch 里**
  （该路径带 `[LEGACY]` 标签）⟹ **一条历史消息的参数非法，就能让这次状态构造抛异常**。
- **可挂的钩子名**：`onToolCallArgsEvent` · `onToolCallEndEvent` · `onNewToolCall` · `onToolCallResultEvent`；
  参数里能拿到 **`toolCallBuffer`（原文）** 与 **`partialToolCallArgs`（部分解析结果）**。

**→ 判据**：`args` 出问题要分三层看——**流没拼完** / **拼完但不是合法 JSON** / **合法 JSON 但不符合工具 schema**。
**前两层在本层就静默成 `{}`**，只有第三层才轮得到工具自己的校验。排障时别把"空参数"直接当成"模型没给参数"。

---

## 十二、★★ 客户端"认识的工具名"清单（**不是注册集** · 2026-10-16 补）

> 出处：模块 `3y_7cwbb6i8tr.js`（工具名常量表）＋ `0978wbhid704x.js`（工具卡文案表）。
> **★ 先纠一条**：§四与 §6.3 写的是"工具清单静态数不出，只能运行时观测"。**这句只对一半**——
> **"注册集"确实数不出**（`name` 来自组件 props），但**"客户端认识的名单"能静态数出来**，见下。

**A. 四个集合 ＋ 一条配对**（常量表模块，逐字）

| 名 | 数 | 内容 |
|---|---|---|
| 人机回环对 | 2 | `request_feedback` · `ask_human` |
| 需子动作 | 1 | `edit_video` |
| `a` | 11 | `create_generation_task` · `nodes_connections_batch` · `ffmpeg_execute` · `analyze_media` · **`sandbox_run`** · `request_feedback` · `ask_human` · `propose_plan` · `write_file` · **`libtv_grounded_search`** · `show_optimized_prompts` |
| `s` | **37** | `director_apply` · `create_generation_task` · `generate_text` · `generate_image` · `generate_video` · `generate_audio` · **`edit_video.clip`** · **`edit_video.extract_frames`** · **`edit_video.add_subtitle`** · **`edit_video.transition`** · `composite_video` · `run_node` · `analyze_video` · `read_file` · `search_canvas_nodes` · `get_canvas_node_details` · **`Skill`（大写 S）** · `skill_creator` · `create_image_node` · `create_video_node` · `create_audio_node` · `nodes_connections_batch` · `create_canvas` · `list_canvas` · `get_canvas_nodes_view` · `ffmpeg_execute` · `request_feedback` · `ask_human` · `propose_plan` · `select_canvas` · `analyze_media` · `write_file` · `show_optimized_prompts` · `script_guide_workflow` · `transfer_to_agent` · `generate_story_events` · `get_project_detail` |
| `l` | 5 | **`task_create` · `task_update` · `task_list` · `task_read` · `script_agent`**（**被显式排除**） |

**B. 归一化与展开（逐字）**：归一化 ＝ `replace(/_v\d+$/i, "")`（`xxx_v2` → `xxx`）＋ `copilot_director_apply` → `director_apply`；展开 ＝ 名字 ∈ `{edit_video}` 时读 `args.operation`，拼成 `edit_video.<operation>`。

**C. 判定**：**`p(name) ＝ !l.has(名) && (a.has(名) || s.has(名))`** 才是"**客户端认不认识这个工具名**"的判据；
`v(name)` 只对 `request_feedback` / `ask_human` 为真（**人机回环**）。
**名字形态有两类**：裸名（`write_file`）与**父工具＋点子动作**（`edit_video.clip`）；**`Skill` ≠ `skill_creator`**。

**D. 工具卡文案表**：**32 个 snake_case 名**（i18n 键 90 个 / 30 个 CamelCase 词干），**未收录者走 fallback 文案**。
三张名单**互不包含**：`kill` **只在文案表**；`sandbox_run` / `libtv_grounded_search` **只在 `a`**；
`director_apply` · 四个 `edit_video.*` · `Skill` **只在 `s`** ⟹ **说"LibTV 有 N 个工具"之前先说清是哪张名单**。

**E. 入参 schema 拿不到**：全库**唯一内联的 `parameters` JSON schema** 是 **CopilotKit 自带的 `copilotkitSuggest`**，
**LibTV 工具一个内联 schema 都没有** ⟹ 想知道某工具吃什么参数，**只能运行时观测真实调用或读它自己的文档**。

**F. `@ImageN` 的负向计数**：编辑器 bundle 里 **`@Image` 0 命中**，而 **`{{Image` 10 处 / 4 文件**
⟹ **客户端解析的是 `{{Image N}}` 一族**，**`@ImageN` 只是书写约定**（与 `libtv-canvas-nodes.md` 一致）。
