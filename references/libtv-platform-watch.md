# LibTV 平台更新监测与新接口（**R27 专册**）

> **为什么单列一册**：**平台没有 changelog 接口**（实测：无 release-notes / revision-history / "上次更新时间"字段；`changelog` / `变更日志` 在本库全库 0 命中）。
> → **"平台更新了什么"只能靠「快照 diff」被动发现**。本册 = **那套方法** + **本次（2026-09-22）差集结果** + **四个库内此前零记录的接口**。
> **读完回哪**：`libtv-canvas-nodes.md`（接口全景）· `libtv-concurrency.md`（锁与并发）· `libtv-model-params.md`（模型目录）· `libtv-official-qa-part7.md` UV2.9（合成与混音权威源）。
> **元数据**：节点 `i-r42yg5pxxkmj` · 画布 A `128b26b763444eafa5565aaab3d4ade4` · 读回 **2026-09-22 10:32**。
> **证据等级（L6）**：§一 / §二 = **实测**（我直接调接口读到的）· §三 / §四 = **实测 schema**（工具自述 + 实际入参）· §五 / §六 / §七 = **平台方声明 + 推断**（不确定项已逐条标）· §十 = **拟订**（1.5 官方公告对照，行为未实测）· **§十·补 = 实测**（零积分探测，2026-09-22 11:05）。

---

## 一、怎么发现平台更新（**唯一可靠机制：三源快照 diff**）

**三源**（每源都要存**完整快照 + 指纹**，与上一版做**字段级 diff**）：

| 源 | 怎么取 | 指纹字段 | 能发现什么 |
|---|---|---|---|
| **① 工具注册表** | `doctor` | `toolRegistry.revision`（`sha256:…`）+ `toolRegistry.count` + `names[]` | **接口新增 / 消失 / 改名** |
| **② 能力契约** | `get_capabilities`（`detail="full"`） | `capabilityContractVersion` + `serviceVersion` | **模块边界 / 删减 / 契约升版** |
| **③ 模型目录** | `search_models(action="search", nodeType=image\|video\|audio)` **全量** | 逐条 `modelKey` + `labels` + `requiresWhitelistPermission` + `vip` | **模型上新 / 权限变更 / 标签变化** |

**★ 为什么必须自己存**：平台侧 Agent 自己确认——**它读不到服务端 changelog，只能按 revision 存快照本地 diff**（它给的原话：**"目前唯一可靠的变更检测"**）。
**★ 辅助探测**：响应头 `ETag` / `Last-Modified` / `Deprecation` / `Sunset`（**是否提供：不确定**）；旧接口探 `410` 确认下线。
**★ 告警口径**：新增 / 消失 / 改默认 / 改权限——**四类都要报**，尤其**改默认**（如 `enableSound` 默认若从 `off` 变 `on`，我方"假设静音"的流程会静默出错）。

---

## 二、本次差集（**2026-09-22 01:35 实测**）

- 工具注册表 **48 个**，`revision = sha256:26880a931d50c18a71f334825b4c61f6e3468b44eda39851a7eeacb4499e5f65`
- `serviceVersion: 0.1.0` · `capabilityContractVersion: 3` · `transport: streamable-http` · `environment: prod`
- **库内零记录的四个接口**（全库 grep 0 命中）：**`list_projects` · `project_info` · `update_project` · `show_generation_result`**
- **`get_capabilities` 说明里写明「the former technical catalog has been removed」** → **技术目录被删**（见 §六）
- **模型目录全量**：图片 **25** · 视频 **43** · 音频 **8**
- **带标签的条目**：`qwen-image-3` = `["上新"]`；`mj-v8.2` = `["风格上新"]` **且 `requiresWhitelistPermission: true`**；`mj-v8.1` / `mj-v7` / `mj-niji7` = `["风格上新"]`
- **★★ 标签不可检索**：`search_models(query="上新")` → **返回空**（`matchKind: "none"`）。**只能全量拉下来自己过滤** —— **这是一条会误导人的坑：以为能按标签搜，实际搜不到。**

---

## 三、四个新接口逐个（**实测 schema**）

### 3.1 `list_projects` —— 与 `project_list` **并存**，且**分页字段命名不一致**

| | `project_list` | `list_projects` |
|---|---|---|
| 分页字段 | **`page_size`（snake_case）** | **`pageSize`（camelCase）** |
| 其它入参 | `page` / `name` | `page` / `name` / **`teamId`** |
| 默认 | `page_size` 默认 20、上限 100 | `pageSize` 默认 20、上限 100 |

**★ 这是踩过的坑**：两个工具**同义但命名不同**，混用会直接参数校验失败。
**返回**：`data.projectMetaList[]`（`id` / `uuid` / `name` / `description` / `visibility` / `ownerId` / `createdAtMs` / `updatedAtMs` / `folderId` / `projectSpaceId` / `projectType` / `bizScene` / `source`）+ **`total`**。
**★★ 同名项目不自动合并**（工具自述："same-name projects are not automatically merged"）—— 本账号实测 **5 个都叫「画布 1」**（`26ce801a…` 主片场 / `230b91f5…` / `a7f94f50…` / `78f637cd…` / `df2a013c…`；原稿"4 个"与实列 5 个 uuid 不符，2026-09-30 勘正）、2 个叫「学习循环_2/_3」→ **必须用 uuid 选，永远不要用名字选**。

### 3.2 `project_info` —— ★★★ **我方第一次能直接读「边」**

- 入参：`project_id`（**必填**，就是画布 uuid）
- 返回三块：**`projectMeta`**（含 `accessConfig` 与 **`effective.canRead / canEdit / canManage / canPublish / canShare / canCopy`**）· **`projectDraft`**（`viewportX / viewportY / viewportZoom` / `lastEditedAtMs`）· **`nodeList`** + **`connectionList`**
- **★★★ `connectionList` = 真实的边清单**，每条：
  `{ connectionId, source, target, sourceHandle, targetHandle, type, deletable, selectable, createdAtMs, updatedAtMs }`
  - **→ 这把 `libtv-op-manual.md`（WF1）里"确认三条边都在"从「靠 `imageListOrder` 间接推断」升级为「直读边表」** —— **引用一致性的验收终于有直接证据了。**
- `nodeList[]` 每条含：`nodeKey` / `toolKey` / `type` / `name` / `status` / **`tag`** / `parentKey` / `position` / `measured` / `workflowUuid` / **`data`（完整 JSON，含 `params.prompt`）** / **`desc`（`prompt` 的纯文本副本）**
  - **→ `desc` 是"答案全文"的第二条读取通道**（`data.params.prompt` 与 `desc` 内容一致，`desc` 更省事）
- **⚠️ 代价**：输出**极大**（画布 A 的 8 个节点 ≈ **9 万字符**）。**只在"要读边"或"要 `data` 全文"时用**；日常清单用 `read_project(view="summary")`。
- **★ 最便宜的哨兵**：`read_project(view="summary")` 返回 **`counts`** —— `nodes` / **`edges`** / `groups` / `scripts` / `assets` / `scenes` / `shots` / `media` / `timelines` / `relations` / `issues` / `errors` / `warnings`。
  **`counts.edges` 一读就知道"边数变了没有"**，比拉 `project_info` 省两个数量级。

### 3.3 `update_project` —— **唯一带乐观锁的写接口**

- 必填 **`idempotencyKey`**（`^[A-Za-z0-9._:-]{8,255}$`）；可写 `name` / `description` / `coverUrl` / `folderId`；`projectId` 与 `projectContext` 二选一
- **`expectedRevision`**：格式 **`^sha256-[a-f0-9]{64}$`**，**可不传**（不传＝不加锁，实测直接成功）
- **★★★ 实测纠正（2026-09-22 11:05 · 推翻早先按工具自述写下的口径）**：
  - ❌ **旧口径"`expectedRevision` 就是 `read_project` 返回的 `revision.token`" —— 实测必冲突**：在**两张画布**上（空画布 `canvasDataSource: none`；有 6 节点画布 `revision.source: api`）各读一次再原样提交，**两次都返回 `REVISION_CONFLICT`**。
  - ✅ **正确值 ＝ `update_project` 自己返回的 `projectRevision`**（用它再写一次即成功，且每次写入后该值推进）。
  - → **纪律：写前要么不传 `expectedRevision`（裸写），要么用「上一次 `update_project` 返回的 `projectRevision`」；不要拿 `read_project` 的 token 去写。**
- **★ 正确顺序**：**取 `projectRevision`（上一次写操作回执）→ 带 `expectedRevision` 提交 → 冲突则重读状态 + 字段级合并 + 用最新 `projectRevision` 重提**
- **★ 禁止同 payload 盲重试**：成功那次已把 revision 推进，**同值重试必然冲突**
- **★ 幂等重放（实测）**：同 `idempotencyKey` 重发 → **`replayed: true` + 同一个 `task_id` + 回执与当前状态分开返回 + revision 不推进**
- **★ 冲突错误码（实测确证）**：**`REVISION_CONFLICT`**，文案 `Project changed; read the current state before updating`
- **★ 回执结构**：`task_id`（`cop_…`）· `status: completed` · `replayed` · **`operationProject`（当次操作结果）与 `project`（当前状态）分开** · **`projectRevision`** · **`projectContext`（不透明句柄，可直接当其它接口的 `projectContext` 入参）** · `currentStateVerification: verified`

### 3.4 `show_generation_result` —— **结果卡片，不是验收证据**

- 入参 `node`（必填）+ `projectId` / `projectContext` → **打开一张结果卡片**（MCP Apps 侧渲染）
- **★★ 硬边界（工具自述，逐字）**：**"A card does not certify generation completion or visual/audio quality."**
- **已完成的视频节点本就有卡片**；**要验收请用 `inspect_media` 或 `read_node`**，**除非用户明确要求再看一次**
- **→ 我方纪律：卡片 ≠ 证据。验收链仍是 `read_node`（状态 + `url`）+ `inspect_media`。**

---

## 四、两侧工具面**再映射**（R26 映射表的补充）

| 平台侧（它那层） | 我方（MCP 侧） | 关系 |
|---|---|---|
| `get_node_details` | `read_node` | 同义（R26 已记） |
| `search_canvas_nodes` | `read_project` | 同义（R26 已记） |
| —— | **`project_info`** | **我方独有：能读 `connectionList`（边表）** |
| —— | **`list_projects`** | 我方独有：带 `teamId` 过滤 |
| —— | **`update_project`** | 我方独有：**项目级乐观锁写** |
| —— | **`show_generation_result`** | 我方独有：结果卡片（**非证据**） |

**★ 平台侧 Agent 明确自陈**：`list_projects` / `project_info` / `update_project` / `show_generation_result` / `get_capabilities` / `project_list` / `read_project_context` / `read_project` **都不在它的可调用注册表里** → **这八个是我方专属面**，**别拿它的"我没这个接口"当"我方没有"**（R26 已立此纪律，本册再证）。

**★★★ 活例（R23 · 2026-09-22 · 本册立新纪律）**：它把 `create_node` / `read_node` / `validate_generation_plan` / `get_model` / `left` / `imageList(Order)` / `frames2video` / `mixed2video` / `read_timeline` / `apply_timeline_edit` / `export_video` / `enableSound` / `step:1` **一律判为"不存在 / 你跑不通"** —— 而这些**在我方 48 工具表与 `get_model` 的 schema 里全部真实存在**。**它把"我侧没有"直接写成了"你跑不通"。**
→ **★ 新纪律**：**平台侧 Agent 说"某接口不存在"时，一律先在我方 48 工具表里 grep 一遍再采信。**

---

## 五、`labels` 与白名单

- `labels` 是**运营标记**，不是权限：**`["上新"]`** = 新近上线 / 新可用；**`["风格上新"]`** = 既有模型线新增风格能力
- **`requiresWhitelistPermission: true`** = **默认不可用，需白名单**（本次全目录仅见 `mj-v8.2`）
- **★ 白名单自查三步**（不靠猜）：
  1. **用最小请求实调一次** → 权限不足通常返回 **403 / `permission_denied` / `whitelist_required`**
  2. 查账户 / 模型详情里的 `accessible` / `enabled`（字段名：**不确定**）
  3. **不要仅凭 `labels` 判断** —— **以 `requiresWhitelistPermission` + 实际鉴权为准**
- **申请入口**：平台侧**无可调用接口** → 走控制台模型详情 / 工单（**确切流程：不确定**）
- **★ 枚举"还有哪些带标签"的正确姿势**：**全量拉目录 + 客户端按 `labels` 非空过滤**（因为 §二 已证**标签不可检索**）

---

## 六、`get_capabilities` 技术目录被删：哪些旧用法会断

- **工具自述**：**"Only the declared business module IDs are accepted; the former technical catalog has been removed."**
- 契约仍是 **9 个业务模块**：`project-canvas` · `image-creation` · `video-creation` · `audio-creation` · `script-storyboard` · `editing-composition` · `media-delivery` · `media-understanding` · `agent-delegation`
- 每模块带 **`pluginSupport`**（`full` / `partial` / `discovery-only` / `none`）与 **`parityVerified`** —— **本次 9 个模块全部 `partial` + `parityVerified: false`**
- **会断的用法**（推断，需逐项核）：
  1. 把它当**接口 schema 权威源**（自动生成客户端 / 参数校验）→ **改走各接口自身 schema**
  2. 读**内部技术标识 / 原始端点 / 计费配额字段**做硬编码 → **会拿到 `undefined`**
  3. 把它当**模型能力细节（格式 / 限制 / 价格）唯一源** → **改走 `search_models` / `get_model`**
- **不受影响**：只用「模块名 + 是否可用 + 边界说明」
- **被删字段的确切集合：不确定** → 要拿旧快照与 v3 做字段级 diff

---

## 七、破坏性变更与处置

| 项 | 状态 | 我方处置 |
|---|---|---|
| `get_capabilities` 技术目录移除 | **可确认** | 见 §六，三处换源 |
| 四新接口与旧接口重叠（`list_projects`↔`project_list`；`project_info`↔`read_project`/`read_project_context`） | **不确定**（**无 `Sunset` / `Deprecation` 证据**） | **两套都保留、都可用**，不押注单一接口 |
| 字段改名（分页 / revision / id 类型） | **不确定** | 每次调用前看 schema；**`page_size` vs `pageSize` 已是活例** |
| 默认值变更（**尤其 `enableSound`**） | **不确定** | **我方逐镜显式写 `enableSound`，永不依赖默认** |
| 限制收紧（并发 / 时长 / 批量 / 白名单扩大） | **不确定** | 跑前用 `get_model` 复核取值域 |

**★ 版本号含义（均标「不确定」）**：`serviceVersion: 0.1.0` = 服务实现版本（`0.x` 表示稳定性承诺仍在演进）；`capabilityContractVersion: 3` = 能力契约结构版本，**与 serviceVersion 解耦**，仅在契约结构变化时递增。

---

## 八、R27 给出的三条"必须改"（**已并入我方流程**）

1. **写操作全走乐观锁**：`update_project` **取上一次 `update_project` 回执的 `projectRevision`**（§三.3 实测：`revision.token` 必 REVISION_CONFLICT——本条 2026-09-30 按 §三.3 勘正）→ 改 → 带 `expectedRevision` 提交；**冲突禁盲重试**，重读 + 字段级合并 + 新 revision 重提
2. **声音解耦**：分镜阶段统一 `enableSound = false` → 声音**后置独立制作** → 合成时 `video_volume = 0` 叠三轨
   - **机制与字段在权威源**：`libtv-official-qa-part7.md` **UV2.9**（`composite_video.audio_list` 的 `start_time/end_time`、`audio_volume`、`video_volume`）
   - **收益**：**改台词只重音频、不重视频**（这是关声最大的隐性价值）
3. **建快照 diff 变更检测**：见 §一

**★ 附带一条我方流程改进（来自 R27 第 8 问，供选型时参考）**：
**A2** —— 需多视角一致性时，可用**三视图 / 转正预设**先固定角色再扇出（`character_face_turnaround_3view` / `character_turnaround_3view`）；**效果是否更稳：未验证，需 A/B**。
**C1** —— **合成前先确认全部上游已是终态**（用 `read_node` 看 `url` 非空），避免引用未就绪素材。

---

## 九、待验（下一轮）

1. ~~**`update_project` 的冲突错误码与 `expectedRevision` 实际行为**~~ → **✅ 已实测解决（2026-09-22 11:05，见 §三.3）**：错误码 ＝ **`REVISION_CONFLICT`**；**`read_project` 的 token 不可用**，正确值 ＝ 上一次 `update_project` 返回的 `projectRevision`；`expectedRevision` 可不传
2. **`list_projects` 的 `teamId` 语义**（本账号 `activeTeamId: null`、`teamRole: null`、账号类型「标准版VIP 连续包月」`accountLevel: 3`）—— **部分**：不传时**回显 `teamId: 0`**（＝"无团队"用 0 表示）；**传非 0 值的过滤行为仍未验**
3. ~~**`project_info.connectionList` 是否包含跨类型边**~~ → **✅ 已实测结案（2026-10-01）**：包含。画布 `616f30b234fd4f7cb121cb4e0c9865c1`（11 节点/12 边）的 `connectionList` 里同时出现三类跨类型边：`T1`(text)→`S1`(image)、`AU2`(audio)→`X1`(video-clip)、`V1`(video)→`X1`(video-clip)。**→ 只看边时无需拉 `nodeList`。**
4. ~~**`show_generation_result` 在本环境是否真能渲染卡片**~~ → **✅ 已实测解决（见 §十·补）**：能出卡片（`1 of 1 items`），但**"Visual playback remains unverified"**
5. **`get_capabilities` 旧快照 vs v3 的字段级 diff**（需先有旧快照；本册 §一 的三源快照从此开始存）
6. **`labels` 全量名单**（全量拉 + 过滤，确认除已知 5 条外还有没有）
7. ~~**1.5 公告五功能在 MCP 的暴露面**~~ → **✅ 已实测解决（见 §十·补）**：**导演分身与 Script V2 可用；角色造型/3D-BOX 走客户端或平台侧内部命令；字幕渲染平台自陈未完整映射**
8. **`projectContext` 句柄的复用边界**（能否完全替代 `projectId` 选项目 / 有效期多长）—— §十·补 新出
9. **模板目录的分页总量与检索质量**（"导演"仅第 1 页就 20 条、`nextPage: 2`）—— 全量规模未测
10. **★ `run_agent` / 与平台 Agent 对话本身是否计费** —— **平台无明文**（`get_capabilities`、各工具自述、R24 计费答疑**均未提**）；**已定部分**＝`autoGenerate: false` 不产生生成任务故不触发计费点（有节点 `taskInfo` 为证）；**`account_user` 不暴露余额 → 我方无法自证** → 只能看客户端计费页或问平台（已问，等回）
11. **`create_script_v2` 的 `assets` 表与既有资产节点的绑定关系**（`characterAssetId` 必须引用本表资产 → 能否跨表引用主片场已有锚点？）

---

## 十、官方 1.5 公告五大功能 vs 三源差集对照（**拟订 · 2026-09-22**）

**公告源**：公众号「LibTV」**2026-09-21 10:00**《LibTV 1.5 版本更新，五大独家功能升级创作全流程！》（`mp.weixin.qq.com/s/s4UiAlcaieiK6qEYVb1iqg`）。
**取文方法（可复用）**：正文是**纯图片排版**（6 图 + 5 段演示视频，HTML 里非 ASCII 文字仅 8 个字符）→ **直接抽 `js_content` 的文字会拿到空**，必须**抓 `data-src` 图片逐张读图**。**★ 以后读公众号公告先查"正文区非 ASCII 字符数"，≈0 就是图片文。**
**时间关系**：公告（09-21）**早于**我方快照（09-22 01:35）→ **快照已包含 1.5 上线后的状态**，但 48 工具表里**没有以这五项功能命名的接口**。

| # | 功能（公告名） | 公告要点 | 我方 MCP 面 | 对照结论 → 动作 |
|---|---|---|---|---|
| 1 | **角色造型 CHARACTER CRAFT** | 从人设/参考图/已有角色出发，可视化调五官·发型·服装，细化痣·雀斑·疤痕；**关联音色、保存角色卡，后续项目继续调用** | 48 工具表**无专属接口** | 判断＝客户端 UI 功能；我方角色一致性仍走 `reference_nodes` + 身份锚点。**★ 角色卡若可被 MCP 读到，就是"跨项目角色资产"的正解** → 待验 ⑦ |
| 2 | **原创编剧 WRITER'S ROOM** | 按题材/人设/背景共创原创剧本；台词·冲突局部改写 + 对比确认；**关联修改提示对大纲/钩子/伏笔的影响** | `script-storyboard` 模块已有 `create_script_v2`/`edit_script_v2`/`read_script_v2` | "局部改写 + 关联提示"可能已部分映射到 Script V2；行为细节待验 ⑦ |
| 3 | **导演分身 DIRECTOR TWIN** | 选预设导演，或**导入自己的创作方法与提示词模板生成导演分身**；辅助拆镜·创建节点·批量优化提示词；**手动模式先审核计划、确认后再生成** | 无专属工具；`agent-delegation`（`run_agent`）疑为其执行通道 | ★★★ **与我方最相关**：库内 SOP（《钥匙》/分镜 SOP）正是"自己的创作方法与提示词模板" → 下一步试**把 SOP 喂成导演分身**；"先审核计划再生成"与我方 `autoGenerate=false` 阶段闸**同构互证**，纪律不改 |
| 4 | **LibTV 3D-BOX 3D 虚拟影棚** | 文字描述或参考图 → Agent 搭场景、排角色动作与机位、**多分镜预演**；**手绘轨迹即可预演运镜**；对话或手动调场景镜头 | 48 工具表**无专属接口** | 客户端功能；我方"故事板→预演"环节可在客户端用它做 previz，产物再进 MCP 流程 → 待验 ⑦ |
| 5 | **成片精修 SMART FINISH** | 选帧设计片名 + 文字动效；**字幕识别与样式调整**；口播视频自动粗剪·画中画·B-Roll 匹配·音效配乐 | `editing-composition` + `composite_video`/`apply_timeline_edit`，**无字幕/片头工具** | 字幕·片头·粗剪是 MCP 盲区 → 需要时在客户端做；**我方验收链（`read_node`+`inspect_media`）不依赖它** |

**三条硬结论**：
1. **五功能在 48 工具表均无专属接口** → 判断为**客户端 UI 功能为主**（推断；依据＝时间覆盖关系 + 全表 grep 0 命中）。**MCP 是否另有隐藏暴露：待验 ⑦。**
2. **证据等级（L6）**：本节全部＝**拟订**（证据＝平台方公告，功能行为未实测）；唯一**已证**项＝公告文本本身存在。
3. **导演分身的"先审核计划再生成"与我方阶段闸同构** → 不是要改我方纪律，而是平台侧对我方做法的印证。

**本轮落库动作**：提问循环新增优先出题方向（五功能 MCP 暴露面）；读回循环三源快照 diff 新增哨兵词 **`character` / `director` / `3d` / `caption` / `subtitle` / `writer`**（新工具注册名一旦命中即报）。

---

## 十·补、五功能在我方接口面**到底能不能用**（**实测 · 2026-09-22 11:05–11:15 · 零积分 · 未点火**）

**探测手法（可复用，全程不点火）**：`doctor`（工具注册表）· `get_capabilities(detail="full")`（模块与约束）· `search_skill_templates`（模板目录）· `list_projects` / `read_project` / `update_project` / `show_generation_result`（四个新接口）。

**★ 第一层结论：工具注册表没变** —— `count` 仍 **48**、`revision` 仍 `sha256:26880a93…`（与 §二 基线**逐字符相同**）→ **1.5 五大功能没有以 MCP 接口形式注册。**

| # | 功能 | 能不能用（我方接口面） | 实测证据 |
|---|---|---|---|
| ① | **角色造型** | **半可用**：无专属接口，但**模板目录里角色资产模板很多** | `search_skill_templates("角色")` 命中 10+ 条：**「Cast Builder 角色资产创建」v1.0.16**（"三路线定脸、服装定妆、造型细节卡与无头三格角色资产工作流"）· 「角色三视图设定｜锁定脸部」v1.0.18 · 「原创AI角色捏脸」· 「女频角色设计-高辨识度」——**经 `run_agent` 加载执行，不是直调接口**；**"角色卡跨项目调用"仍是客户端能力** |
| ② | **原创编剧** | **可用，但"生成"不在 MCP** | `create_script_v2` / `read_script_v2` / `edit_script_v2` 均在 48 表；模板目录另有「AI导演-剧本诊断改稿」「电影级 AI 视觉资产导演」等。**★ 但 `create_script_v2` 工具自述明写 "No content or media generation" → 它是"建表接口"，不是编剧生成器**；要它"写剧本"只能经 **`run_agent`** 让平台侧 Agent 产出（实测：11:20 发起 → 11:22 落画布 2，节点 `i-yg3u7th8pcnb`） |
| ③ | **导演分身** | **★★★ 可用（本轮最大发现）** | `search_skill_templates("导演")` **一次返回 20 条**，全部 `libtv-user-generated/*`（**用户生成命名空间＝"导入自己的创作方法"的落地形态**）：电影级 AI 超级导演 / 分镜导演 / 古典武侠全流程导演 / 动作导演 / 连续长镜头导演 / PV 导演 / 口播导演台 …；**接线 ＝ `run_agent.skills`**；契约 `libtv-skill-template-search-v2`、`bindingPolicy: agent-latest-by-skill-ref`、**`versionPinned: false`（版本不锁执行）** |
| ④ | **3D-BOX 虚拟影棚** | **半可用**：客户端 UI 无接口，但**导演台场景编辑有平台侧内部命令** | `director_apply`（R17 已记录：`commands` / `base_revision` / `target_node`）**不在我方 48 表** → 属"**Agent 内部工具不是公共 MCP 接口**"（`agent-delegation` 约束原文）；**"手绘轨迹预演运镜"＝客户端专属 UI**（`libtv-canvas-nodes.md` 陷阱 6 早记） |
| ⑤ | **成片精修** | **部分可用，且字幕有硬伤** | 模板目录仅 **1 条**字幕模板「AI 智能字幕搭配」v1.0.13；**★ `editing-composition` 约束原文："高级变速、转场、变换、字幕等编辑数据尚未完整映射到最终渲染，不能静默忽略"** → **字幕样式能生成、但不保证落到成片**；片头动效 / 口播粗剪 / B-roll 匹配**无接口** |

**★ 三条新硬约束（实测 / 工具自述）**：
1. **`run_agent.skills` 上限 `maxItems: 1`** → **一次只能挂一个模板（一个导演分身）**，**不能"风格模板 + 流程模板"叠加**。
2. **`run_agent` 另有入参 `ackUser`**（`weak` / `normal` / `strong`）—— 与 `autoGenerate`（阶段闸）并列；**我方维持 `autoGenerate: false` 不变**。
3. **`projectContext` 是跨接口可复用句柄**：`update_project` 回执里返回的不透明串，可直接当其它接口的 `projectContext` 入参（**绕过"按 uuid 选项目"的一条捷径，待验**）。

**★ 四个新接口实测**：`list_projects` ✅（不传 `teamId` 时**回显 `teamId: 0`**，`total: 10`）· `project_info` ✅（R27 已读）· `update_project` ✅（**见 §三.3 实测纠正**）· `show_generation_result` ✅（对已有节点返回 `LibTV media: 1 of 1 items. Visual playback remains unverified.` → **卡片能出，"画面未验证"与工具自述一致**）。

**★ 一句话结论**：**1.5 的五大功能是"客户端 UI + 模板生态"两条腿，不是 MCP 新接口**——**能被直接调用的只有「导演分身（模板目录 + `run_agent`）」与「Script V2」**；**角色造型、3D-BOX 走客户端或平台侧 Agent 内部命令；成片精修的字幕渲染平台自陈未完整映射。**

**★ 原创编剧实战对拍一次（2026-09-22 11:20–11:22 · 题材取主片场《钥匙》）**
同一 brief（写实 · 室内单场景 · 无对白 · 30–34s · 10 镜 · 落空结尾）下：
- **它强的地方**：结构完整 · **逐镜带运镜与机位** · **钩子/伏笔逐个写"埋设 → 回收"** —— 这三项**比我们自己的分镜模板更规整**，可直接当"运镜列 + 伏笔列"的来源。
- **★ 抓到 3 处硬伤**：**① 自述"总时长 32 秒"而逐镜加总 ＝ 35 秒**（超 brief 上限 34s，自述与实数不符）**② 给女性角色写了"喉结"** **③ 混入"心跳般的低频鼓起"＝ BGM 元素**（与我方"分镜阶段 No BGM、声音后置"纪律冲突）。
- **★★ 结构性发现：它的产出与我们既有《钥匙》几乎同构**（同一骨架 **"犹豫 → 差点拿 → 松手 → 空镜留钥匙"**）→ **给定"物件 ＋ 无对白 ＋ 落空"的 brief，它会强烈收敛到同一解法（题材惯性）**：brief 只给"物件+情绪+结局"，它就必然把冲突外化成"有人来了"。
- **→ 用法（2026-09-22 用户定为常设流程）**：**我方定题材 ＋ 写大纲 ＋ 出初稿 → 平台 Agent 定稿 → 我方三项复核（时长 / 人物生理 / 声音）→ 入 Script V2**。**★ 完整交接流程、交付协议与复核表见 `script-agent-handoff.md`**（本册只留实测依据）。
- 交付物：工作区 `原创编剧对拍_钥匙题材_20260922.md`（题材锚点 + A 版原文 + 我方《并排》全文 + 对照表）。

---

## 十一、平台 Agent「全流程」实测（**2026-09-22 12:57–14:05 · 首次开 `autoGenerate: true` · 只出图未出视频**）

**背景**：用户授权「**视频先不生成，允许生成图片以及其他操作**」→ 阶段闸进入「实片预演」（见 `agent-autonomy.md` 纪律五）。三轮 run（画布 `4552ebba…` / `698b5f36…` / `7007c927…`）+ 我方接手点火（画布 `6c12c424…`）。

**★ 它的全流程（图片部分，完整暴露）＝ 两层 + 一点火**
| 层 | 节点 | modeType | 做法 |
|---|---|---|---|
| ① **内容锚点层** | 角色身份卡 / 场景空镜 / 道具特写 | `text2image` | 浅灰背景、平光、**只定基线不带剧情**；节点带 `tag: character/scene/prop` |
| ② **关键帧层** | S1/S2/S3 | `image2image` | **用 `left` 连线引用锚点** —— `imageList` 由平台按连线**自动重算**并填 URL（实测：直接写 `params.imageList` 报 `NODE_VALIDATION_FAILED`："媒体列表由画布连线重算与 CLI 内部现算得出，请用连线 --left"） |
| ③ **点火** | —— | —— | **默认不做，等审批** |

**★ 它的节点留痕格式（可借用）**：`【阶段：xxx】【能力/模板/模型：xxx】【关键参数：xxx】` ＋ 全局风格 ＋ 画面 ＋ `【产出：xxx；下一步：xxx】`。

**★★ 它的流程闸：点火前强制提问** —— 三次 run 全部停在"建完节点、点火前"（`steer_agent_run` 返回 `AGENT_QUESTION_PENDING`）。**message 里写"免审批声明"无效；"铁律禁提问"能跳过提问，但代价是它也不点火**（run 直接到终态）→ **它的"审批"是流程强制环节，绕不过只能答**。

**★★★ 环境障碍（本轮最重要的运维结论）**：`get_agent_status` / `show_agent_progress` **在 WorkBuddy 宿主里恒返回桩文案**（"Agent 状态来自远端回读…"，换 3 种参数组合相同）→ **拿不到 pending question 的 `toolCallId`** → `answer_agent_questions` 无法回答（传占位值返回 `AGENT_QUESTION_MISMATCH`）→ **平台 Agent 的"点火审批"我方走不通**。**出路**：① 用户在客户端界面答 ② 我方接手点火。

**★ 画布锁**：active run 占画布（`update_node` 报 `AGENT_RUN_ACTIVE: An Agent owns this canvas`）；`stop_agent_run` 发出后**锁不立即释放**（>2 分钟未释放）→ **复刻要换新画布**。

**★ 我方接手点火（复刻它的流程，画布 `6c12c424…`）**：`create_node(run=true)` ×3 建锚点点火 → 全部 `SUCCEEDED`（2048×1152）→ `create_node(left=[锚点keys])` 建 3 关键帧（**连线即引用**；点火后平台自动把锚点 URL 填进 `imageList`）→ `update_node(run=true)` ×3 点火。**出图质量**：角色 / 场景（百叶窗硬光切平行亮带完全按 prompt）/ 道具（磨旧铜钥匙＋饱和橙红塑料牌）三张全部高质量、逐项符合。

**★ 它的硬伤（第四次同类）**：**自述模型名与 `params.model` 不符**——prompt 写"Lib Image 2.5 Pro"，实际 `model: "lib-image-2.5-s"`。

**★ 新接口知识**：`create_node` 的 `left`/`right` ＝ **引用连线**；`create_node(run=true)` **不阻塞**（回 `generation.task_id` ＋ `tool_call_id: run.xxx`），`update_node(run=true)` 阻塞等终态；`task_status` 拿 artifact（`outcome: SUCCEEDED` / `readiness: TERMINAL_READY` / `resource_id`）；媒体 URL 在节点 `url` 字段（`https://libtv-res.liblib.art/...`），可直接 curl 下载验收。

**待验**：① 画布锁 stop 后多久释放 ② `toolCallId` 有无界面途径获取 ③ 关键帧 image2image 耗时为何显著长于锚点

## 十二、资产层实测 + **审批闸「不可自答」已穷举证明**（**2026-09-22 14:28–14:50 · 只出图**）

**★ 补跑资产层（画布 `6c12c424…` · 我方自建自点火 · 4/4 SUCCEEDED · 全 4K 3840×2160）**：`资产_角色三视图`（三格正/左/背，`image2image` 引角色锚点）· `资产_场景多角度板`（四机位：主视角3/4 · 反打 · 侧视 · 低角度）· `资产_场景平面图`（**正交俯视**，`text2image` 不引参考）· `资产_道具多角度板`（五格，含手掌尺度对照）。**四条板式全部达标**（三格同一人 · 四机位同空间同光向 · 正交无文字 · 五格同一道具）。
**★ 执行率实测（推翻"板式类约束执行率最高"的一半口径）**：**「分区之间用细白线分隔」4/4 全部未执行**（板子改用背景自然分栏）；而**「禁止文字」「正交俯视」「三格/四格/五格数」4/4 全部执行**。→ **分隔线属低执行率项，别再依赖**，改写成"背景自然分栏"或"浅灰卡片分栏"。
**★★ 新硬伤（第一条跨图级，最该防）**：**多角度板自行给场景加了锚点里没有的陈设**（壁挂地图 / 挂衣架 / 台灯 / 电话 / 盆栽 / 六把椅子），而**锚点空镜里没有** → **锚点与多角度板成了"两个办公室"**（正是 `asset-consistency.md` §三 实测反例的同类）。**纪律：出了多角度板就必须回写覆盖锚点**，否则下游分别引用两张＝两套空间。
**★★★ 审批闸「不可自答」已穷举证明（结论确定，勿再试）**：
- `get_agent_status`：**句柄无效时返回真错误**（`PROJECT_REQUIRED` / `LEGACY_RUN_ID_REQUIRED` / `AGENT_RUN_NOT_FOUND` / `AGENT_SESSION_INVALID`），**句柄有效时恒返回同一句"远端回读"文案、不给任何状态** → **合法 run 的状态被挡在门外**，`toolCallId` 无从取得。
- 已换 5 种组合（本轮精确 runId+projectId · projectContext+runId · agentSession · 无参 · 垃圾 runId）＋同批并发 → 结论不变。
- `steer_agent_run` → `AGENT_QUESTION_PENDING`（**可当"有无待答问题"的探针**）· `run_agent(runId=<活动run>)` → `AGENT_RUN_ACTIVE` · `answer_agent_questions` 只回 `AGENT_QUESTION_MISMATCH`（**不回声 id**）。
- **★ 已试模板通道**：`skills=[短剧·导演级全流程编排]`（描述"剧本→切点/分镜/资产/画布全链路"）→ **同样卡 `AGENT_QUESTION_PENDING`** → **审批闸与模板无关，属流程强制环节**。
- **★ 新错误码三条**：`IDEMPOTENCY_CONFLICT: This key belongs to different Agent input`（幂等键不可换内容复用）· `PROJECT_WRITE_BUSY: The original write is still running`（**画布是单写者 → 多个 `create_node` 必须串行发**）· `params.textList/videoList/audioList` **同样不可直写**（与 `imageList` 同一条平台规则）。
- **★ 新判据**：**active run 占着画布时 `read_project` 回 `canvasDataSource: "none"` + 0 节点**（空闲画布回 `"api"` + 真节点）→ **可当"画布是否被 run 占用"的粗判据**，替代被屏蔽的状态接口。
**★ 唯一出路**：**我方接手点火**（§十一已证 6/6）＋ 让 Agent 走"禁提问"路线只出方案；或**用户在 LibTV 界面答**。
**★ 模板目录用法（新接口知识）**：`search_skill_templates` **中文能搜到、英文搜不到**（`"短剧"` 命中 40 条/页；`"storyboard"` 与 `"全流程 分镜 资产 短片"` 均空）。**与本库工作流对得上的两条**：`短剧·导演级全流程编排`（refId `drama-script-orchestrator…`）· `短剧全角色视觉设定生成器`（refId `drama-character-visual-generator…`，描述明写"为每个角色生成专业级全身三视图"）。


> **★ 2026-10-01 实测补注（省量用法）**：`project_info` 的 `connectionList` 是**读边最低成本的通道**——相比 `read_project(view="nodes")`（库内实测：8 节点 ≈ 9 万字符），**只要边表时应用它**。另：`nodeList[]` 每条带 **`status`（数值型）**，实测未点火节点均为 `status:1`。**→ 这是「节点是否已生效」的机器可读依据**，对编排器 **G6 引用可生效闸**有用；**但其语义映射（1 = 已创建？）仍属未解**——待有点火节点后才能校对，按 L6 不猜。

## 十三、2026-10-14 REA 逆向差集（**已拆出**）

> **本节正文已移到 `libtv-platform-watch-rea-index.md`**（**本册顶格 300 行，拆册以便两边继续长**）。
> **本节只留指针**（L2：单一权威源 + 指针，正文一个字没删）。
