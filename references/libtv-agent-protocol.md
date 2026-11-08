# 跨 Agent 通信协议（让它把答案写进“我能读的容器”）

> **从 `libtv-canvas-nodes.md` 分卷而来**（2026-10-02，原册触顶 300 行）。
> **为什么分开**：画布与节点是「平台能做什么」，
> 本册是「**我方怎么拿到它的答案**」——各自变迁频率完全不同，混住会让「读回协议」被当成「画布能力」。
> **核心判据**：**通信失败时，先盘点「我这一侧到底能读哪几类东西」，然后让对方往那几类里写。**
> **不要反复要求对方用它做不到的方式交付。**（原文一字未删）
> **读完回**：`libtv-canvas-nodes.md`（画布与节点）· `libtv-official-qa*.md`（平台口径）。

---

## 十、★ 跨 Agent 通信协议：**让它把答案写进"我能读的容器"**

**教训（2026-09-20）**：我一直在说"读不到它的回答"，**却没让它换一个"我能读的容器"**——这是我的问题，不是能力问题。
**判据**：**通信失败时，先盘点"我这一侧到底能读哪几类东西"，然后让对方往那几类里写。** 而不是反复要求对方用"它做不到的方式"（建文本节点）交付。

**外部侧（我）** 验证过**能读**的三类：

| 通道 | 它要做什么（**都不要生成媒体**） | 我怎么读 | 容量/风险 |
|---|---|---|---|
| **A · Script V2 表当"文件"** ★首选 | 把全文建成 **Script V2 表**（表名 `Agent答疑_<主题>`）；每行放一段（`durationSeconds: 1` 占位、正文写进 `plotDescription` 等文本字段），**行序＝段序** | `read_script_v2(node="Agent答疑_<主题>")` | **单表 1 MiB**、结构化、**我免费读** —— **容量最大** |
| **B · 节点名 + `prompt` 字段** | **建一个节点但不 run**（不生成），`name` 用 `Agent答疑_<主题>`，**全文写进该节点的 `prompt`** | `read_node("Agent答疑_<主题>")` → 读 `params.prompt` | 受**单模型 `prompt` 长度上限**约束（**无 3000 硬上限，但仍有 schema 限制**）；节点名短 |
| **C · 上传成素材 + 给 URL** | 把 `.md` **上传成项目素材**，然后**把素材 URL 贴出来** | 我**本地能联网** → `curl` 直接下载（本轮已用 curl 成功拉过 mp4 / 图片） | 最稳；**只受"它给不给 URL"限制** |

**→ 给它的指令模板（可直接复制转发）**：
> 请把你的答案写进下面任一个"我的外部侧能读的容器"里（**都不要生成任何媒体**）：
> **A** 建成 **Script V2 表**，表名 `Agent答疑_<主题>`，逐行分段（`durationSeconds: 1` 占位，正文写 `plotDescription`）；
> **B** 建一个节点（**不 run**），节点名 `Agent答疑_<主题>`，全文写进它的 `prompt`；
> **C** 把文件**上传成项目素材**并**贴出素材 URL**。
> 若三条都不可行，**请告诉我"哪一条的哪个工具名不可用"**，我再换方案——**不要重复用我已经告诉你我读不到的方式交付**。

### 十·补 · 我这侧**读不到**它工作区的文件（2026-09-20 查证三条实据）

| 查什么 | 结果 |
|---|---|
| 我的工具集搜 `read_file_v2` / `write_file_v2` | **无此工具** |
| `ListMcpResources(server=LibTV)` | 返回 13 个资源：`analysis-v1` · `media-v1~v4` · `download-v1｜v2` · `upload-v1｜v2` · `followup-form-v1｜v2` · `agent-progress-v1｜v2`；**mimeType 全为 `text/html;profile=mcp-app`（＝UI 卡片），没有那个 md** |
| `ReadMcpResource(uri="answers/Agent答疑_工作流.md")` | ❌ **`MCP error -32602: Invalid request parameters`** |

**★ 结论（现实约束）**：**它能写**（`write_file_v2` 写进自己工作区）；**我能读本地文件**；**中间缺一座桥**。且 **MCP 资源 ≠ 它的工作区文件**——`ReadMcpResource` 只够得到服务器声明的那 13 张 UI 卡，**够不到它沙箱里的 `answers/…`**。

**★ 三条可用桥（用户侧操作即可，按快到慢）**：
1. **把它下载到工作区**（如 `<HOME>\WorkBuddy\<工作区>\`）→ 我 `Read` 直接读全文（**最快**）；
2. 复制内容贴给我；
3. 给一个可访问 URL → 我本地 `curl` 下载。

**★ 那 13 张 UI 卡＝它的界面能力清单**（MCP 侧不可编程调用，只能给人在界面里用）：**分析 · 素材 · 下载 · 上传 · 追问表单 · Agent 进度**。

**★★★ 已验证的"读回协议"（2026-09-21 · 实测成功 · 推翻本册此前的悲观结论）**

**此前我判定"读回不可能"是错的。真正可行的协议如下（一次成功）：**

| 步 | 我做什么 | 实测结果 |
|---|---|---|
| **1** | `run_agent(message, autoGenerate=false)`，消息里**只要求一件事**：**"建一个 image 节点但不要 run，节点名 `Agent交付_<主题>`，把答案全文写进该节点的 `prompt` 字段"** | run 起得来（`streaming`） |
| **2** | **耐心轮询** `read_project(view="summary")` 看有没有新节点 | **★ 关键：它几分钟后才建**——我上次只等 2 分钟就收手，误判为"不通"；**实际第二次查（约 10 分钟后）节点已在那里** |
| **3** | `read_node("Agent交付_<主题>")` → **读 `data.params.prompt`** | **✅ 拿到全文** |

**实测证据**：节点 `i-79q4dnhfwf72`（`type: image` · `name: "Agent交付_R11答案"`），`data.params.prompt` 里是完整答案；`data.action: "image_generate"`、**`taskInfo.taskId: ""` + `status: 0` → 它没有 run、没有生成、零成本** ✓

**★ 三条纪律**：
1. **要"指定落点"**——明确说"建节点但不要 run、写进 `prompt` 字段、节点名用 `Agent交付_<主题>`"；
2. **要"耐心"**——**轮询间隔按分钟计，不要按秒**；宁多查几次，不要早收手（**早收手是上次误判的直接原因**）；
3. **它还会顺手写一份项目文件**（`Agent交付_<主题>.md`，在**"task-v2 存储根目录"**）——**这条通道我读不到，但说明它有文件根目录**。

**⚠️ 一处仍要自己验**：它回答里说"`reference_nodes` / `start_frame_image_node` / `end_frame_image_node` 就是 MCP 侧字段名"——**但我在 MCP 侧实测到的是**：Wan 3.0 用 **`modeType: frames2video / mixed2video / videoExtend2video`** 表达"首尾帧 / 多参考 / 续写"。**→ 两边字段体系不同：它是"编排层一级字段"，我是"模型层模式+输入列表"。以 `get_model` 的 schema 为准。**
**⚠️【旧结论留档 · 已被上面的"读回协议"推翻，保留以示教训】**
2026-09-20 我曾判定"读回不可能"，据此写下"改用用户搬运作为唯一通道"。**错因**：① 我向它**索要"办法"**而非**指定落点**；② **只轮询 2 分钟就收手**。**教训**：**别问对方"怎么让我读到"，要直接指定一个我能读的落点；且给足它落地的时间。**

---

## ★★★ 平台侧「Agent 会话」的完整接口族（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

> 本册此前讲的是"**怎么让它把答案写进我能读的容器**"（方法论）。本节补的是**平台自己的会话管道长什么样**——`project session` 家族的 CRUD、**审批模式开关**、消息拉取与字段归一。

### 一、会话（session）＝ 一个项目下的一次 Agent 对话

| 操作 | 方法与请求体 |
|---|---|
| **建会话** | `POST`：**`{ projectId, name, … }`**，并按需带上这些**可选字段**：`agentName`（**只在带它时才可能带 `canvasId`**）· `nodeKey` · `workKey` · **`skill` → 被映射成 `{ skillKey, skillVersion }`** · **`libtvMeta`（仅当非空对象才带）** |
| 建会话（原样透传版） | 直接把入参 POST 出去（另一条调用路径） |
| **列会话** | `GET`，params **`{ projectId, type? }`**——**`type` 是 `types.join(",")` 逗号串** |
| 改标题 | `POST`：`{ sessionId, title }` |
| 改元数据 | `POST`：`{ sessionId, libtvMeta }` |
| **停止会话** | `POST`：`{ sessionId }` |
| 删会话 | `POST`：`{ sessionId }` |

**★ 三条读法**：
1. **`skill` 在传输层是 `{ skillKey, skillVersion }`** ⟹ 与我方"挂模板"那条纪律对得上：**挂 skill 是"键 + 版本"两个字段**，不是名字字符串；
2. **`canvasId` 依附于 `agentName`**（不带 agentName 时不会带 canvasId）——**说明"指定画布"是 Agent 上下文的从属字段**；
3. **`libtvMeta` 是任意结构化元数据的官方通道**，且**空对象不发**。

### 二、★★ 审批模式：平台自己的"阶段闸"（`approvalMode`）

```
POST  { sessionId, approvalMode }
```

**★★ 意义**：**平台把"这个会话要不要人工审批"做成了显式的会话级字段**——与我方 `autoGenerate:false` 阶段闸、以及本库实测的"平台 Agent 点火前强制提问（`AGENT_QUESTION_PENDING`）"是**同一族机制的三个侧面**。
**→ 用法**：**要"先审后跑"就在会话层把审批模式设住**，而不是只在单次调用上火阶段闸；两者**并存**，不是替代关系。

### 三、消息拉取（我方"读回"的正式通道）

```
GET  params: { projectId, sessionId?, afterSeq? }
```

- **`afterSeq` 是增量游标** ⟹ **支持"只取上次之后的新消息"**（比整段重拉省得多）；
- 返回 `data.messages[]`，**客户端会把每条消息的 `messageId` 归一成 `id`**（**两个字段名都要预期**）；
- 另有 **`projectSessionCreate` 的标题生成入口**：`GET` 传 **`message`**，由平台生成画布标题。

**→ 与本册总纲的关系**：**这就是"我能读的容器"在平台侧的正规形态**——**优先用"会话 + afterSeq 增量拉取"，而不是让对方把答案塞进提示词或画布节点**。

### 四、帖子分享（同族配套）

`POST projectShare`（建/写）· `GET projectShare { params:{ shareId } }`（读）。

### 五、★ 入口来源追踪（"用户从哪进来的"）

前端会读 5 个路由 query 参数——**`entrySource` · `entryItemKey` · `entryItemName` · `entryItemIsViralContent` · `entryTargetUrl`**——并转成 snake_case 上报：
**`entry_source` · `entry_item_key` · `entry_item_name` · `entry_item_is_viral_content` · `is_new_project`**；
**★ 读完之后这 5 个参数会从 URL 里被删掉**。
**→ 含义**：**"用户从哪个入口/哪条内容进来的"是平台显式追踪的**；**分享链接里的来源参数是一次性消费的**，转发后会丢——**留证时要在首次落地时记，别指望 URL 里还在**。

### 六、★ 一处"客户端校验比别处严"的样板：`agentTaskModes`

```
GET  params: { agentName }
```

响应 `{ code, data:{ modes[] } }`；**客户端对每个 mode 做逐字段校验并直接抛错**——要求 **`key`（非空字符串）**、**`name`（字符串）**必填，可选 **`aliasName`**、**`isVip`（布尔）**、**`version`（字符串且长度 ≤ 100）**；之后再做归一（trim、缺 name 时回落 key 等）。
**→ 与 §四 那批"静默吞错"的助手形成鲜明对照**：**同一份客户端里，"能影响生成路径的读"会严格抛错，"装饰性/辅助性的读"会静默返回空**。**排查时可按这个二分法判断"这条数据缺失是否会有报错"**。

---

## ★★★ 平台自己的 Agent 与 Skill 引用格式（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

> 本节把"挂一个平台 Agent / 引用一个 Skill"的**字面形态**钉死——本库此前只记过"`skillList` 是数组""用户生成命名空间"这类间接表述。

### 一、片头（智能片头）实际用的 Agent 与 Skill（逐字）

| 项 | 值 |
|---|---|
| 任务类型 | **`agent_task`** |
| 片名设计 Agent | **`libtv_creative_title_design_agent`** |
| 片名动效 Agent | **`libtv_creative_title_motion_agent`** |
| **片名设计 Skill 引用** | **`libtv-user-generated/creative-title-designer-ad7396f8e0a5497ab352f403f290c82f`** |
| **片名动效 Skill 引用** | **`libtv-user-generated/creative-title-motion-ad7396f8e0a5497ab352f403f290c82f`** |

**★★ 由此确定的 Skill 引用格式（本库此前零记录）**：

```text
libtv-user-generated/<短横线小写 slug>-<32 位十六进制>
```

- **命名空间 `libtv-user-generated/` 之后是"slug + 破折号 + 32 位 hex"**（两个片头 skill 的 hex 部分**相同**，只有 slug 不同 ⟹ **hex 很可能是"作者/库"维度而不是"单个 skill"维度**，但**本轮不能判定**，只记字面）；
- **`agent_task` + 具体 agent 名 + Skill 引用三者同时出现** ⟹ 与第 31 轮记的"`agent_task` + `agent_name`"和"会话层的 `{skillKey, skillVersion}`"合成**三层对照**：
 **① 任务层**：`taskType = agent_task` ＋ `params.agent_name`（或函数级 agent 名）**② 会话层**：`skill = { skillKey, skillVersion }` **③ 内容层**：Skill 引用串（`libtv-user-generated/…`）。

### 二、★ 一条与旧记录的互证

本轮顺带看到**移动窗口下限的校验常量是 `>= 5.5`**，与第 4 轮从同一批 bundle 里挖到的 **`OPENING_BLEND_WINDOW_MOVABLE_MIN_SEC = 5.5`** **逐值一致**——**两条独立路径（常量扫描 vs 调用点校验）验到同一个数**。

### 三、片头预设的身份约定

- **预设 uuid 用字符串 `"default"` 表示内置默认**（判定即 `uuid === "default"`）；
- **每个预设带 `official` 布尔与 `coverList`**：**非官方且无封面时回退到内置封面常量**（片名设计与动效各有一套 default/custom 封面 URL）。
**★ 读法**：**"是否官方"是一个显式布尔** ⟹ 与我方"不得把用户生成内容当官方资产"的纪律同向——**平台自己就把这两类分开了**。

### 七、★ Skill key 的构造规则（客户端函数级证据指针）

登录态编辑器 bundle 里还有一个专职构造函数，逐字规则为：命名空间默认
`libtv-user-generated`；先 `trim` 并去掉首尾 `/`；若 `skillKey ?? id` 已经含
`/`，原样返回；否则拼成 `<namespace>/<key>`。调用方可以覆盖命名空间。

**→ 三条执行口径**：

1. `libtv-user-generated/<slug>-<32hex>` 里的整段 **是 `skillKey` 自身**，
   hex 不是客户端临时添加的；
2. 解析旧数据时要同时接受 **带命名空间的全串** 与 **裸 key**；
3. 另有一个 JSON 字符串解析器，只接受可选的 `skillId`、`prompt`，且
   `draft` 必须逐字为布尔 `true` 才生效。

**完整 API 族、枚举与案例结构 → `libtv-web-api-shapes.md` §八。**

---

## ★★ 平台自己的"干跑"与"额度闸"：`dryRun` 与 `agentPowerLimit`（**登录态网页 bundle · 一手 · 2026-10-15 读**）

> **来源**：`outputs/libtv_rea_20261014/28_发布模板可见性与用户配置服务族.md`（证据 C138–C140）。
> **一句话**：**LibTV 自己就有一套"用户级干跑开关 + Agent 积分上限"**——它和我方 `autoGenerate:false`
> 阶段闸**是两套并存机制，不是替代关系**。

### 一、真实回读（唯一有运行时证据的一条）

`POST /api/canvas/user-config/get` 返回 200：

```json
{"code":0,"data":{"config":{"agentPowerLimitEnabled":true,"agentPowerLimit":10,"updatedAtMs":1789918532764,"dryrun":true}},"msg":"","trace_id":"qHvkbiTv4cTBf8Qq"}
```

服务端键是小写 **`dryrun`**，客户端归一为 **`dryRun`**；
`agentPowerLimit=10` / `updatedAtMs=1789918532764` 是**该账号当时取值，不是平台默认值**。
请求头名称含 `token` / `webid` / `x-language` / `x-log-id`（**未记录值**）。

### 二、`dryRun` 的传播链（三步，逐字）

1. 用户级配置：`user-config/update {dryRun:boolean}`，网页 store **默认 `true`**，
   写入有并发保护、失败回滚；
2. 会话级落点：输入框提交时写 **`dryRunIntent`**，存进 session 的 `libtvMeta.extra`；
3. 请求级还原：构造 Agent 请求时映射回 **`dryRun`**（首页发送路径同样映射）。

**★ 三条执行口径**：

1. **`dryRun:true` 只能证明"客户端请求里带了干跑意图"，不能证明"服务端一定不扣费"**——
   服务端语义未验证，**不得把 dryRun 当成本地零成本证明**；
2. 要"先审后跑"，**会话层 `approvalMode` + 我方 `autoGenerate:false` + 本开关三者并存**，
   按需叠加，不要互相替代；
3. `dryRun` / `agentPowerLimit` / `user-config` 在 CLI 载荷与官方文档 **全 0 命中** ⟹
   **这是网页侧能力，别在 CLI 脚本里写**。

### 三、`agentPowerLimit`：Agent 积分上限（客户端口径）

- 读取：`agentPowerLimitEnabled`（布尔）+ `agentPowerLimit`（正整数）；`limit` 非数字或不大于 0 时按空处理；
- 首次开启且无已存阈值：客户端建议值 **`max(800, round(0.2 × 当前额度))`**，
  再提交 `{agentPowerLimitEnabled:true, agentPowerLimit:max(1,round(该值))}`；
- 只改阈值：提交 `{agentPowerLimit:round(值)}`，**小于 1 直接拒绝**；输入控件 `min=1` / `step=100`；
- **★ 单位、服务端是否强制、与计费如何结算都未验证**（`inferred`，不是实测）。

**→ 与我方纪律的关系**：这条正好把 `libtv-billing.md` 的"积分闸"从"我方自律"抬到"平台自带配置"——
但我方仍**不得**在没有显式批准时点火，**平台额度开关不构成用户批准**。

---

## ★ 声明 ≠ 接线：引用平台端点前先查接线状态（**登录态 bundle 机器扫描 · 一手 · 2026-10-15**）

**常量表里有定义，不等于客户端接线了。** 本轮机器扫描 146 个脚本：
97 条 canvas 字面量路径中 **83 条有引用、14 条只有声明**；46 个运行时捕获文件里**只有 9 条 URL 出现过**。

**14 条"声明未接线"**：项目版本 3 · 工作流版本 2 · studio-stack 1 · artifact-version 2 ·
`node/payload/batch/get` 1 · `template/view-creation-process` 1 · `media-asset/tags/delete` 1 · 回收站 3。
**9 条运行时可观察**：`heartbeat` · `nodes/batch` · `draft/update` · `extra-config get/update` ·
`media-asset/tags/list` · `project/detail-by-space` · `user-config/get` · `folder/vfs/scripts`。

**★ 三条执行口径**：

1. 要引用某个端点或"平台能力"前，先查 `outputs/libtv_rea_20261014/29_canvas端点接线图.md`；
   `declared-only` 一律按 **unknown** 处理，**不许写成"平台支持"**；
2. 运行时可观察的**出现次数 ≠ 请求次数**（多数来自同一份合并网络清单的重复出现），别当调用量统计；
3. **判消费方必须解析导入别名链**：常量 key 只出现在服务层文件**不等于**没有消费方——
   例：模块 `984954` 导出 `ai`，消费方写 `(0,k.ai)(t)`，不再出现常量 key。

**机器产物**：`05_网页bundle与sourcemaps/endpoint_wiring_20261015.json`（含逐端点状态、key 列表、引用文件与运行时命中）。

### 补 · 接线之后还有一层：**导出 ≠ 被调用**

按导入别名精确数过模块 `984954`：**65 个导出 → 54 个可映射端点 → 58 个有消费方 / 7 个零消费**，
252 个调用点分布在 25 个消费文件（23 个含 `e.i(984954)` 别名）。
该方法与上一轮**手工别名链**在 9 条上逐值一致（`ad=2 / Fr=1 / Gd=2 / qX=3 / O2=3`，发布四族各 1）。

- **调用点最多**：`canvasNodesBatch` **53** · `canvasFolderCreate` **43**（`I8`+`aj` 两个导出）· `canvasFolderEntries` 13
  —— **改这三条路径前先做影响面排查**；
- **零消费的端点导出**：`canvasProjectCopyToTeam` · `canvasProjectList` · `projectSpaceCopy` ·
  `canvasProjectShareDetail` · `canvasProjectCopyToTeamStatus`；
- **★ 口径警告**：这是**模块级**负搜索——`canvasProjectList` 在本模块无人调用，
  但 CLI `project list` 已验证可用。**模块内没调用 ≠ 平台没能力**，两种结论不能互换。
- 调用点数量是**静态代码位置数**，不是运行次数、不是业务频次。

**机器产物**：`05_网页bundle与sourcemaps/consumer_depth_20261015.json`；重跑用 `work/libtv_consumer_depth.mjs`。

### 补2 · CLI `-s` 的 schema 往返：`originalField` 与 modeType 剪枝

- **`getStoreKey(prop, field) = prop.originalField ?? field`** —— schema 字段名 → 存储键的**唯一映射**
  （如 `duration` → `music_length_ms`）；
- **`getFieldList(cfg, modeType)`**：缺 `modeType` 时**回落 `text2video` 的字段表**——不是"全允许"也不是"全禁止"；
- **写侧** `hoistSchemaGroupedParamsFromTopLevelPatch`：顶层 patch 里**非结构键**只要命中
  `settings`/`advancedSettings` 允许表（按字段名或存储键）就**提升进容器**；
  **27 个结构键**（`model`/`prompt`/`count`/`modeType`/各列表/`cameraControl`/`multi_prompt`…）**永不动**；
- **提交侧** `stripVideoFlatParamsDisallowedBySchema`：**没有硬编码黑名单**——
  删键 ＝ **`collectUnique(全 mode 并集) − getFieldList(modeType)`**；**schema 缺 `config` 时一个键都不删**；
- **往返**：顶层 patch → 提升进 `settings` → 提交时**摊平回顶层** → video 再按 schema × mode 剪枝；
- **实践判据**：某个 `-s` 键"写了没生效"，**先查该模型 schema 在当前 `modeType` 下的允许表**，别去找全局黑名单；
- **跨源**：网页 bundle 也用 `originalField ?? 默认` 并写 `settings` 容器（92 次 / 8 文件）→ **两端共享该约定**；
  CLI 的具名函数在网页端 0 命中，但**网页是压缩产物，按名比对不能证明行为差异**。

**详见** `outputs/libtv_rea_20261014/32_CLI字段schema参数层.md`（C157–C160）。

**其余两个服务模块的消费深度（同口径）**：`292830`（node payload）**3 导出 / 2 消费文件 / 6 调用点**（`j` get · `K` 读改写含 4 MiB 校验 · `u` JSON 解析，各 2）；`413784`（user-config）**3 导出 / 2 消费文件 / 4 调用点**（`A` get=1 · `P` update=2 · `j` 空间额度=1）——与报告 28 的人工读数**逐值吻合**（机器↔人工第二次互证）。**→ 影响面读法**：`984954` 是**总线**（65 导出 / 25 文件 / 252 调用点），另两个是**专用小模块**（使用方少而集中）。
**详见** `outputs/libtv_rea_20261014/37_多模块消费深度.md`（C182–C185）。
