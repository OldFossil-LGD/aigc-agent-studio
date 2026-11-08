# LibTV 能力矩阵（**48 工具 × 实测状态** · 2026-09-23）

> **来源**：`get_capabilities`（**能力契约 v3 · 9 大类 · 48 工具**）逐项对照本会话实测。
> **用途**：**"把功能全部应用一遍"的正确姿势＝清单化 + 逐项标注状态**，而不是盲目全跑（全跑会烧掉大量积分）。
> **★ 状态口径**：✅**本会话亲手跑过** ｜ 🔶**只探到 schema（未实跑）** ｜ ⚠️**完全没碰** ｜ 📋**自动化代跑轮覆盖过（非本会话亲手）**
> **★ 数量构成注（2026-09-27 补）**：**48 ＝ 能力契约内 43**（`get_capabilities` v3 · 9 大类 · 去重）**＋ 表外 5**（`get_capabilities` 自身 / `doctor` / `account_user` / `project_info` / `project_list` 等画布·账号·诊断类入口）（**2026-09-29 实测复核：调用 `get_capabilities`（contractVersion 3 · 9 大类），把九类的 `mcpTools` 跨类去重后逐一清点，确为 43**；表外 5 个不在任何一类的 `mcpTools` 列表里——**43＋5＝48 已由实测坐实，此前"待核"标记撤销**；数字仍以 `get_capabilities` 实时为准）
>
> **★★ 2026-10-14 REA 补充**：本地 CLI `libtv.exe` 已确认是 `pkg` 打包的 Node 应用，CLI 帮助树可读，但**恢复出的 CLI 代码未发现与 MCP 同名的 `expectedRevision` / `idempotencyKey` 字段**；MCP 写入与生成 schema 明确暴露二者。**不得把 MCP 的幂等/乐观锁语义外推到 CLI，也不得用 CLI 重试证明 MCP 可安全重放。**完整证据见 `libtv-platform-watch-rea-index.md`（整册）。
> **★★ 2026-10-15 REA 补充（两个"角色"入口不是一件事）**：① **顶栏 `角色造型室`**＝`button[data-sidebar-btn="character-library"]`，**实测打开的是"角色库侧栏"**（tab `我的角色库` / `官方角色库`，`搜索角色名称或描述`、`多选`、`列表模式`/`宫格模式`、`创建新角色`），该步**实测发出 `POST /api/user/character/list`** → **「角色造型室 ⟶ `/api/user/character/*`」已由运行捕获坐实**（同族 `create`/`parse`/`update`/`mark-used` 仍只属字面）；② **生成器面板里的 `角色库`** 会**先弹《Seedance模型使用承诺书》**（`我已阅读并同意上述《Seedance模型使用承诺书》` / `不同意` / `同意并使用`），同意前看不到内容，并伴随 `POST /api/character-library/list` → 判为**公共角色库 + 合规闸**。**纪律：不得代用户点「同意并使用」；未同意时生成器角色库内容一律记 unknown。**

---

## 一、九大类 · 48 工具（契约原文）+ 实测状态

### 1 · project-canvas（项目与画布）· 12 个工具
| 工具 | 状态 |
|---|---|
| `list_projects` | ✅（拉过 16 张画布） |
| `create_project` | ✅（**建了 5 张**：交付通道测试 / 学习循环_2 / 学习循环_3 / 库审计_1 / 库审计_2 / 教学代跑） |
| `target_project` | ⚠️ |
| `update_project` | 📋 |
| `read_project_context` | ⚠️ |
| `read_project` | ✅（大量） |
| `read_node` | ✅（大量） |
| `get_project_snapshot` | ⚠️ |
| `create_node` | ✅（**schema 已探全**：`name`/`nodeType`(6 档含 `text`)/`idempotencyKey` 必填 + `prompt`/`params`/`data`/`left`/`right`/`group`/`x`/`y`/`run`/`expectedRevision`） |
| `update_node` | ✅（`run=false` 实跑；**`run` 字段已确认存在**；`leftAdd`/`leftRemove`/`leftEnsure` 已确认） |
| `delete_node` | ⚠️ |
| `manage_group` | ⚠️ |

### 2 · image-creation（图片创作）· 9 个工具
| 工具 | 状态 |
|---|---|
| `search_models` | ✅（**图像 27 个 / 视频 47 个全量目录已落库**）**★ 2026-10-01 修正：这两个数都不能当"全量"用——见下方「★ 空 query 不是全量目录」** |
| `get_model` | ✅（Wan 3.0 / Lib Image 2.5 Pro 的**完整 schema 已落库**） |
| `create_node` | ✅ |
| `update_node` | ✅ |
| `generation_submit` | 🔶**schema 已探全**（`project_id`/`idempotency_key`/`kind{image,audio,video}`/`request{model,params,source_node_keys,provider,task_title,tag,desc}`），**未实跑** |
| `task_status` | ⚠️ |
| `task_cancel` | ⚠️ |
| `show_generation_result` | 📋 |
| `inspect_media` | ⚠️ |

### 3 · video-creation（视频创作）· 12 个工具
| 工具 | 状态 |
|---|---|
| `search_models` / `get_model` | ✅ |
| `recommend_video_models` | ⚠️ |
| **`validate_generation_plan`** | 🔶**schema 已探全**（必填 `name`/`prompt`/`model`(**传完整 modelName，不传 modelKey**)/`mode`(**9 档，推荐 `auto`**)；**引用字段是 `referenceImageNodes`/`referenceVideoNodes`/`referenceAudioNodes`**；`params` 里**不要塞** model/modeType/prompt/媒体 list） |
| `generate_video` | ⚠️ |
| `create_node` / `update_node` / `generation_submit` | ✅ / ✅ / 🔶 |
| `task_status` / `task_cancel` / `show_generation_result` / `inspect_media` | ⚠️/⚠️/📋/⚠️ |

### 4 · audio-creation（音频创作）· 9 个工具
**全部 ⚠️ 未碰**（`search_models`/`get_model` 可查，但**音频模型目录已由自动化拉过**：8 个）。

### 5 · script-storyboard（剧本与分镜）· 9 个工具
| 工具 | 状态 |
|---|---|
| `create_node`（含 `text`/`script` 档） | 🔶**schema 已探**（`nodeType` 枚举含 `text`/`script`/`video-clip`），未实例化 |
| `create_script_v2` | 📋（**《钥匙》10 镜分镜表 `b-umfpvNTZFm` 是它建的**） |
| `read_script_v2` | ✅（读全 10 行） |
| `edit_script_v2` | ⚠️ |
| `get_project_snapshot` | ⚠️ |
| **`check_continuity`** | ⚠️（**SOP 里的"连续性机检"就等它**） |
| `task_status`/`task_cancel` | ⚠️ |

### 6 · editing-composition（剪辑与合成）· 9 个工具
| 工具 | 状态 |
|---|---|
| `read_timeline` | ⚠️ |
| `apply_timeline_edit` | ⚠️（**SOP 合成段的"按序放 10 镜"就靠它**） |
| `create_node`/`update_node` | ✅ |
| **`export_readiness`** | ⚠️（**官方"批量验收闸"**） |
| **`export_video`** | ⚠️ |
| `export_status` | ⚠️ |
| `task_status`/`task_cancel` | ⚠️ |

### 7 · media-delivery（素材与交付）· 6 个工具
| 工具 | 状态 |
|---|---|
| **`upload_ticket`** | ⚠️（**我方"上传本地资产图当参考"就靠它**） |
| **`upload_complete`** | ⚠️ |
| `resource_info` | ⚠️ |
| `inspect_media` | ⚠️ |
| `browse_project_media` | ✅（扫过素材） |
| `show_generation_result` | 📋 |

### 8 · media-understanding（媒体理解）· 3 个工具
`inspect_media`/`task_status`/`task_cancel` —— **全部 ⚠️**（`pluginSupport: discovery-only`）。

### 9 · agent-delegation（Agent 委托）· 8 个工具
| 工具 | 状态 |
|---|---|
| `search_skill_templates` | ⚠️ |
| `ask_followup_questions` | ⚠️ |
| **`run_agent`** | ✅（**本会话发了 20+ 轮**，含 `autoGenerate=false` 与 `true`） |
| `steer_agent_run` | ✅（**并实测出"探活技巧"**：从返回码读状态） |
| `get_agent_status` | ⚠️（**实测必须带 runId，空手问会回 `LEGACY_RUN_ID_REQUIRED`**） |
| `show_agent_progress` | ⚠️ |
| `answer_agent_questions` | 🔶（**存在**；平台方的 `ask_human(approve_run_node_once)` 疑似与它同源） |
| `stop_agent_run` | ✅（**并实测出"死锁 run 不可解"**：`steer`/`stop` 都回 `AGENT_ACCEPTANCE_UNKNOWN`） |

---

## 二、★ 状态汇总（诚实计数）

| 状态 | 数量 | 代表 |
|---|---|---|
| ✅ **亲手跑过** | **约 13** | `create_node` · `read_node` · `read_project` · `create_project` · `list_projects` · `search_models` · `get_model` · `update_node` · `run_agent` · `steer_agent_run` · `stop_agent_run` · `browse_project_media` · `read_script_v2` · `get_capabilities` |
| 🔶 **只探到 schema** | **4** | `validate_generation_plan` · `generation_submit` · `create_node` 的 `text/script` 档 · `answer_agent_questions` |
| 📋 **自动化代跑轮覆盖** | **4** | `create_script_v2` · `show_generation_result` · `update_project` · `project_info` 系 |
| ⚠️ **完全没碰** | **约 27** | **视频生成链** · **音频链** · **上传两段式** · **时间线/合成/导出链** · **`check_continuity`** · **`inspect_media`** · **`recommend_video_models`** · `target_project` · `get_project_snapshot` · `delete_node` · `manage_group` · `edit_script_v2` |

**★ 结论**：**"读取与建节点"这条链已经打通并熟练；"点火与出片"这条链（约 27 个工具）基本没碰。**

---

## 三、★ 按"工作流阶段"排的应用路线图（该按这个顺序补）

| 阶段 | 要补的工具 | 风险 |
|---|---|---|
| **① 资产与关键帧**（图） | `generation_submit`（或 `update_node(run=true)`） | **花积分**；需先过 `validate_generation_plan` |
| **② 镜头**（视频） | `validate_generation_plan` → `generate_video`/点火 → `task_status` → `show_generation_result` → `inspect_media` | **最贵**；模型选型 + 时长整数 |
| **③ 声音** | 音频链（`search_models`/`get_model`/`generation_submit`） | 本片声音本地做 → **可跳过** |
| **④ 合成导出** | `read_timeline` → `apply_timeline_edit` → `export_readiness` → `export_video` → `export_status` | 有"未映射"传闻，需实测 |
| **⑤ 验收** | `check_continuity` · `inspect_media` | 官方机检 |
| **⑥ 素材交付** | `upload_ticket`/`upload_complete`/`resource_info` | 本地资产图当参考的通道 |

**★ 纪律（沿用阶段门）**：**这一张表就是"申请花积分的清单"**——按阶段逐段申请、逐段验证，**不要一次全开**。

---

## ★ 空 `query` 不是全量目录（**2026-10-01 实测 · 踩过才知道**）

**现象**：`search_models(nodeType="video", query="")` 返回 **29** 个；而按族名定向查，**同一个目录里明显还有它没给的**。

| 定向 `query` | 该族实测数 | 空 query 里**缺**的 |
|---|---|---|
| `"Kling"` | **7** | `Kling 3.0`(`kling-video-o3`) · `Kling O1`(`kling-video-o1`) · `Kling 2.6`(`kling-v2-6`) |
| `"Wan"` | **6** | `Wan 2.7`(`wanx2.7-video`) · `Wan 2.6`(`wanxiang-v2-6`) |
| `"Vidu"` | 4 | 无（此族完整） |

**→ 已确认缺失 ≥ 5 个**，故真实目录规模 **> 34**，**空 query 的 29 与本册原记的 47 都不等于全量**（两个数都不能引用为现状）。

**★ 为什么会漏（机制，不只是"接口坏了"）**：定向查询的 `matchKind` 实测是 **`modelName`**（按**模型名子串**匹配），而目录里**中英文命名混存**——
- `可灵 3.0 Turbo`（中文名）**只在空 query 里出现**，`query:"Kling"` 反而**查不到它**；
- 反之 `Kling 2.6`（英文名）在空 query 里被漏掉。
→ **单靠空 query 或单靠英文 query，两边都会漏，必须并用。**

**★ 三条使用纪律（照做，别再引一个数当全量）**：
1. **要"目录有多大"→ 不要用模型计数回答**。改问 `recommend_video_models`（按任务给候选），或**按族逐个定向查并集**。
2. **要"某模型在不在池子里"→ 必须定向 `query` 核**（本轮就靠它证伪了"Wan 2.6 是孤证"：`wanxiang-v2-6` 确实在池内）。
3. **引用本册那两个数时必须带月份**（2026-09 快照），**且注明"非全量"**——否则就是下一个 187。

---

## 十三、★★ 平台硬上限常量（**REA 静态扫描 · 2026-10-15 · 原始 54 条，本节为人工筛过的业务项**）

> 来源：85 个网页 chunk 的常量扫描（产物 `05_网页bundle与sourcemaps/static_constants.json`）。原始表里混有 HTTP 状态码类常量（408/411/416/504），下表已剔除。**客户端常量 ≠ 服务端契约**——它只证明"客户端会这么拦"。

| 常量 | 值 | 用途 |
|---|---|---|
| `NODE_REFERENCE_LIST_MAX` | **50** | 节点引用列表上限（源码里硬编码 `if(n.length>=50)break`） |
| `MAX_VIDEO_COMPOSE_DURATION_SEC` | **1200** | 视频合成最长 **20 分钟** |
| `CAMERA_PRESETS_MAX_SELECT` | **6** | **单节点最多同时选 6 个运镜预设** |
| `CUSTOM_PRESET_MAX_COUNT` / `_NAME_MAX_LENGTH` / `_PROMPT_MAX_LENGTH` | 10 / 6 / 500 | 自定义运镜：条数 / 名字 / 提示词 |
| `MULTI_UPLOAD_MAX` | 15 | 批量上传单次上限 |
| `DEPTH_MAP_REF_MAX_DURATION_SEC` / `_720P_` 版 | 180 / 30 | 深度图参考时长上限（**分辨率越高窗口越窄**） |
| `SCRIPT_ADAPTATION_EPISODES_MIN/MAX/DEFAULT` | 2 / 100 / 100 | 剧本改编集数 |
| `MAGIC_SELECT_MAX_COUNT` / `SEGMENT_REMAKE_MAX_RANGES` / `CHAT_ASSET_MAX_PER_KIND` | 20 / 5 / 20 | 智能选择 / 片段重做 / Agent 单类素材 |
| `MAX_FOLDER_DEPTH` / `MAX_FOLDER_MD_FILES` / `MAX_FOLDER_TOTAL_BYTES` | 3 / 50 / 1 MiB | 素材文件夹 |
| `TAG_NAME_MAX_LENGTH` | 10 | 标签名 |
| `DEFAULT_PART_SIZE` / `MAX_CONCURRENCY` / `DEFAULT_CONCURRENCY` / `DEFAULT_MAX_RETRIES` | 5 MiB / 6 / 4 / 2 | 上传分片与重试 |
| `DEFAULT_UPLOAD_VIDEO_MAX_SIZE` | 500 | 视频上传上限（**单位未在客户端文本出现 → unknown**） |

**★ 口径提醒（三个数字不是一回事）**：CLI `libtv model search -t video` 与登录态 UI 下拉**都是 34 项、逐条一致**；**UI 标签 `2.0`/`2.5` ＝ 目录 `aliasName`**；**模型徽标 `30s/1min/2min/3min/8min` ＝ `estimatedTime`**。而本册 §九～§十二 记的是 **MCP `search_models` 侧更早截面（29/47）**——**三者来源不同，引用时必须写清来源与月份。**

### 13.1 导出 / 下载 / 水印（**静态字面 · 2026-10-15**）

| 事实 | 原文键与值 |
|---|---|
| 批量下载硬上限 | `batchDownloadLimitHint` = **单次下载数量上限 300 个**（另有 `historyDownloadMaxHint` 的 `{count}` 运行时版） |
| 导出＝服务端打包 | `packagingDownload` = 正在打包下载 {count} 个文件…；可中断（`stopBatchDownload` / `cancelDownloadConfirm`） |
| 音视频分离导出 | `avSeparateStarted` = 正在分离音视频（导出音轨与无声视频）；失败分支 `avSeparateAudioOnly` |
| 合成后自动下载 | `clipComposeSubmittedLocal` = 合成任务已提交，完成后将自动下载成片… |
| 导演台动画导出 | `directorAnimationExport*` 十余条：**录屏 → 上传 → 回建画布节点**，含"只读模式无法导出""视频已上传但画布节点创建失败"等分支 |
| 去 AI 水印 | `watermarkRemoveDescription` = 开启后，你创作、生成的 AI 内容将不再添加 AI 生成水印 |
| 去品牌水印＝会员权益 | `benefitWatermark` = 去除品牌水印 商用无忧 · `subscriptionBenefitRemoveWatermark` = 去除品牌水印 |
| 发布保护上限 | `publishProtectionSettingTooltip` = 复制后加水印或不可见，**最多可保护30个节点** |

**★ 交付纪律（新增一条）**：**"无水印交付"不是默认结果，而是会员权益/开关**——验收单里不得把它写成既有保证（`libtv-billing.md` 记成本口径）。

### 13.2 智能片头（Smart Opening）与时间线常量（**静态字面 · 2026-10-15 · 编辑器 bundle**）

**智能片头＝Agent 驱动的一条独立链路**：function key 为 `title_design`（片名设计）与 `motion_design`（片名动效）；提交参数带 `generator_type` · `is_agent: true` · `node_uuid` · `project_uuid` · `function_context: {preset_source, preset_uuid?}`，遥测事件为 `libtv.canvas.smart_opening.*`（含 submit/success/fail/timeout 与 `task_id` / `error_code` / `error_stage` / `duration_ms`）。

| 常量 | 值 | 含义 |
|---|---|---|
| `OPENING_BLEND_SEGMENT_SEC` | 5 | 片名动效与原片混合段长 |
| `OPENING_BLEND_WINDOW_MOVABLE_MIN_SEC` | 5.5 | 混合窗口可移动的下限 |
| `OPENING_FALLBACK_FPS` | 30 | 缺帧率时的兜底 |
| `OPENING_POWER_COST_DESIGN` / `_MOTION` / `_MOTION_BLEND` | 30 / 150 / 300 | 三档积分（**客户端常数**，见 `libtv-billing.md`） |
| `OPENING_GENERATION_MOCK` | `false` | 走真生成，不是 mock |

**预设结构**：`{uuid, type, name, coverList, content, referenceImages, official, createdAtMs, updatedAtMs}`。

**时间线 / 音频编辑常量（同批扫出）**：`AUDIO_FADER_DB_MIN/MAX = -60 / 20`（音量推子） · `AUDIO_PLAYBACK_LINEAR_MAX_RATIO = 5`（线性倍速上限 5×） · `CLIP_MIN_WIDTH = 20` · `MIN_TOTAL_DURATION = 60` · 时间线缩放 `MIN_SCALE = 2` / `DEFAULT_SCALE = 100` / `MAX_SCALE = 500`。

### 13.3 上传上限与生成器类型枚举（**2026-10-15 · 编辑器 bundle**）

| 规则 | 值 | 出处 |
|---|---|---|
| 视频上传体积 | `size > 0x60000000` 即拒 → **≈1.5 GiB**（1,610,612,736 B） | `89472` 模块 |
| 上传视频时长 | `maxDurationSec ?? 900` → **默认 900 秒 / 15 分钟** | 同上 |
| 输入视频容器 | 仅 **MP4 / MOV**（与 §十三 的 `videoFormatMp4Mov` 一致） | 同上 |

**生成器类型枚举（`getGeneratorTypeFromNode`，新登 4 个）**：`enhanceImage` · `enhanceVideo` · **`subtitleErase`** · **`audioEdit`**。映射关系：`IMAGE_EDIT → enhanceImage` · `VIDEO_EDIT → subtitleErase \| enhanceVideo` · `AUDIO_GENERATE → audioEdit \| audio` · `SCRIPT_GENERATE → text`。
**`subtitleErase` 缺省模型＝`volcano-subtitle-eraser`**，`mode ∈ {Text, Subtitle}`，`erase_ratio_location` 归一化为 `{top_left_x, top_left_y, bottom_right_x, bottom_right_y}`（全在 [0,1]）。

### 13.4 协议闸门只读原则（接口证据指针）

客户端里有 `agreementCheck → data.signed` 与 `agreementSign` 两段式接口，
至少覆盖 `star-video` 与 `doubao-visual` 两类，签署体带硬编码版本 `"v1.0"`。
**自动化只能读 `signed`；未签时必须停下报告，不得代用户同意法律条款。**

完整请求体、失败处置与 `third_asset` 合规轮询 →
`libtv-web-api-shapes.md` §九。

---

## 十四 · ★★★ **平台技能目录**（`skillPanelCommon` · **15 条** · 2026-10-16 只读取到）

> **为什么单列**：本册一至九节是 **MCP 的能力契约**（`get_capabilities` 那 48 个工具）；
> **这一节是"平台自己的一键成片技能清单"**——取自 **`/api/www/landing-activities/getById?id=262`**，
> **只读 GET、无需点火**。**它是一个裸 JSON 数组**（不是对象）。
> **★ 用法**：**`skillKey` + `templateUuid` 是"启动一个平台技能"所需的一对键**——
> **`templateUuid` 是技能要实例化的画布模板**；**要用就抄这一对，不是抄名字**。
> **★ 会过期**：2026-10-16 这一抓的快照；`version` 尤其会变。

| # | 技能名 | `skillKey` | `templateUuid` | 版本 |
|---|---|---|---|---|
| 1 | 皮克斯动画广告 | `pixar-animated-ad-creator-5de625e86d1143e6a4fd948ca25ec34b` | `00357d85c34c445eac9f0c8735017807` | 1.0.1 |
| 2 | 爆款拉片复刻 | `viral-video-replicator-3fdf06a4c10a4f96b98f779e197578c8` | `8a9e8bac7b0146f3a770749838f94495` | 1.0.5 |
| 3 | 新中式美学TVC | `neo-chinese-aesthetic-tvc-beda8103d1a8414aa15aa0eb1db95a07` | `caa124f3972044b8925b9308e96411c0` | 1.0.12 |
| 4 | 古典武侠电影全流程导演 | `hujinquanwuxia-a015ad0682e441c5a70fd7cac0fc563a` | `473f446619d643acac34272fa434b2ad` | 1.0.1 |
| 5 | 游戏实机PV | `gameplay-pv-builder-020b92eb952140af9a99e594358a115b` | `4a2899016c374656ab016803f6a20087` | 1.0.1 |
| 6 | 精品女频短剧一键成片 | `xingrannvpin-0bfcda928d704e8da3d20977029a31b8` | `9662f7b185a84ff7a86790b1cb640b6d` | 1.0.0 |
| 7 | 是枝裕和电影美学 | `koreeda-film-aesthetic-ad7396f8e0a5497ab352f403f290c82f-e8810017` | `50c4d60990ed4b39b5e5c40adfc942b8` | 1.0.11 |
| 8 | 韦斯安德森电影美学 | `wes-anderson-aesthetics-beda8103d1a8414aa15aa0eb1db95a07` | `74b462f926b149f2ac1693995191e4c2` | 1.0.0 |
| 9 | 剧情TVC广告片 | `narrative-tvc-creator-020b92eb952140af9a99e594358a115b` | `9df8a2399c7244358c419c0b833f1abd` | 1.0.1 |
| 10 | 伊斯特伍德西部片 | `eastwood-western-style-71a5fc5f6ae546d58b0b8d75abc87608` | `0e61a57cebde4bc7ac962cf743c1ef00` | 1.0.0 |
| 11 | 一键爽感轰炸流汽车TVC | `high-impact-car-tvc-9d8925c591a643bbad8ca8cfbb87922c` | `dd04bed176c74d198c13a81db200403a` | 1.0.1 |
| 12 | 旅拍大师 | `cinematic-travel-vlog-maker-ea101076a01c4630a1e90cb41e56b4d1` | `7ecc6d146dc5465e90deb2cdb6586128` | 1.0.4 |
| 13 | 一键海外狼人吸血鬼短剧 | `werewolf-vampire-short-drama-0bfcda928d704e8da3d20977029a31b8` | `fed2a4a8c9114769bf3cb9c242cd1ab7` | 1.0.1 |
| 14 | 宝岛浪潮电影美学 | `taiwan-new-wave-aesthetic-ad7396f8e0a5497ab352f403f290c82f-00e974d5` | `b6b90be9122b4ce98530e0adb707ec07` | 1.0.8 |
| 15 | 无厘头喜剧 | `absurdist-comedy-maker-8db3e80ed29a49109eb6c801f13bb76c` | `d474c84673f544adafd7d3060087b098` | 1.0.3 |

**★ 四条判据**：

1. **`resultType` 全为 3**——**15 条同一类型**（**这一抓里没有第二种 `resultType`**）；
2. **`skillKey` 的尾巴是随机 hex，前缀是人可读的英文名**——**匹配时用全串，别用前缀**；
3. **它比"本库自建的工作流"更靠平台侧**：**这些技能由平台维护、会随平台更新**；
   **本库自建流程的价值是"可控 + 可审计"，平台技能的价值是"开箱"**——**两者不是替代关系**；
4. **`280 videoComposeAgent` 的 4 条模式也各带一个 `skillKey`**（见 `libtv-compose-timeline.md`）——
   **"平台技能"不止这 15 条，"智能剪辑模式"那 4 条是另一组。**

> **来源**：**平台远端配置 `id=262`（`skillPanelCommon`）**，2026-10-16 只读 GET；**通道与取数链见 `libtv-cli-env-binding.md`**。
