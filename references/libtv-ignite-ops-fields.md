# 点火与合成的实操字段 + 剧本/资产/台账接口（**学自 R37 `i-5p6s56btw933` / R39 `i-5p9p5c2jrzq5v`** · 2026-09-23）

> **本册补的是"我方卡住的具体字段"**——都是可照抄的操作级答案。
> **★ 口径**：它侧未暴露的字段（如 `modeType`/`create_text_node`）以"未映射"标注；**我方 MCP 侧若实测存在，以我方为准**（另标）。

---

## 一、★★★ 点火与合成的实操字段（R37）

### 1.1 ★ "取帧成图" ＝ 用 `edit_video_v4`
- **工具 `edit_video_v4`**；**必填 `source_node_keys = [该视频节点 key]` ＋ `brief`（自然语言）**；
- **brief 里明确写"提取该视频的最后一帧，导出为一张 IMAGE 节点"**；
- **它能力清单明确含 `first/last frame extraction to image nodes`** → **产出可被 `start_frame_image_node` 引用的 IMAGE 节点**；
- **前提：源视频必须已渲染完成（finished），否则被拒**；
- **★ `director_apply` 的 `capture` 不能对"已 record 出来的视频"抽末帧**（它只对当前 3D 场景出静帧）——**别混用**。

### 1.2 ★★ 首帧"三处一致"的确切写法
**同一 `node_key` 必须同时出现在三处，缺一不可**：
1. **`start_frame_image_node` ＝ 首帧 key**；
2. **`reference_nodes` 数组里再次包含同一个 key**；
3. **prompt 正文里有双花括号插桩**。
**★ 插桩只写一次**——"一个节点插桩一次即可，不要因它同时占两个字段就写两遍；写两遍不报错但冗余"。
**prompt 要写明用途**，如"（首帧 key）作为本镜首帧，画面从该帧状态开始延续"。

### 1.3 `reference_nodes` 顺序
**无强制语义（未映射）**；**实操建议（非契约）：首帧排第一位**，其后 **角色锚点 → 场景锚点 → 道具锚点**；**顺序本身不改变引用是否成立**。

### 1.4 ★ `duration` 取整规则
- **估法 ＝ 台词自然时长 ＋ 无台词屏幕节拍预估**；**台词时长是硬下限**；
- **★ 先满足"装得下内容"，再在整数档里取不小于需求的最小值（等价向上取整）** → **3.5 秒 → 取 4**；
- **"官方推荐方向"这一说法本身未映射**，上法是由估算契约推得的安全做法。

### 1.5 ★ `reuse_clip_node_key`（`composite_video` 入参）
- **含义**：**复用一个已存在的"视频剪辑 / 智能剪辑（Video Compose）"节点（`data.type=video-clip`）作为本次合成的上游**，而不是新建剪辑节点（**否则画布不断堆积"智能剪辑 2/3/4…"**）；
- **只能传已存在的 `video-clip` 类型节点 key**；传其他类型**直接报错**（不静默新建）；
- **使用场景**：通常由用户在界面点击该节点时由运行时注入；**在"对同一次合成做重算 / 追加镜头"时回填该 key 以保持单一剪辑节点**。

### 1.6 ★★ trim 语义与对齐算例
- **单位秒，作用于 SOURCE 源片**；`start_position` 入点（**≥0 从片头、负数从片尾**；省略＝从片头）· `end_position` 出点（同约定；省略＝播到片尾）；**每镜贡献时长 ＝ end − start**；
- **★ 算例（6 个源片各 5 秒 → 目标 29 秒，需裁 1 秒）**：**5 个保持整段 5 秒，1 个裁成 4 秒**（镜 6 写 `start:0 end:4`，**选无台词 / 无关键动作的一端**）→ **5×5 ＋ 4 ＝ 29** ✓
  **要保留片尾则写 `start_position = −4` 并省略 `end_position`**；
- **推广**：**目标 T、N 个源片各 D 秒 → 需裁 Δ ＝ N·D − T** → **按各镜"可裁空间"分配，保证不切断台词与关键动作**。

### 1.7 ★ 单镜超模型上限（>15s）两条路
- **(a) 延长（首选做"同一镜头续长"）**：设 **`video_action_type = "extend"`**，**`reference_nodes` 放被延长的视频节点**（可再加角色/风格参考图，**都要插桩**）；**extend 保持源视频画幅 → `aspect_ratio` 被忽略**；**不是每个模型都能 extend**；
- **(b) 拆段拍再拼**：切成每段在模型上限内的多个分镜 → 逐段生成 → `composite_video` 按 `video_list` 顺序拼接；**段间可用首帧机制衔接**（上一段末帧经 `edit_video_v4` 取帧 → 下一段 `start_frame_image_node`）；
- **★ 选择**：**要"一个连续镜头不断"优先 extend；要分镜 / 可切机位则拆段 ＋ composite**。

### 1.8 ★★★ 环境声不连续的正解（**关键混音坑**）
- **各镜 `sound = "off"`**（★ 契约限定"只有明确要静音 / 无声时才用 `off`"；**为后期统一铺环境声属"中间素材后期统一混音"的合理用法，但要清楚 `off` 永久丢弃该镜音轨**）；
- **统一环境声**：**单独建一条音频节点**（持续 ambience，用 `create_audio_node` 的 `sound_effect` 描述，或 `music` 类）→ **`composite_video` 时经 `audio_list` 叠加**（`node_key` 填它、**`start_time = 0`**；铺满全片就省略 `end_time`）；
- **★★ 关键混音坑**：**`composite_video` 不会自动平衡电平——所有视频原声与 `audio_list` 线性相加，再由峰值限幅器整体拉低；若保留各镜原声，铺的环境声几乎会被压到听不见** →
  **→ 统一环境声时必须设 `video_volume = 0`**（彻底静音各镜原声），**让 `audio_list` 的统一环境声成为唯一环境底**；旁白 / BGM 作额外 `audio_list` 条目，用 `audio_volume` 控电平；
- **→ 这样无论画面怎么切，环境声都是同一条连续轨，不会断。**

### 1.8b ★★★ **点火后想确认「这次到底吃了什么」，看 `taskParams`，不要看 `params`**（2026-10-03 实测 · E216）

- **`read_node` 会同时给出两份**：`params`（节点当前存着的参数）与 `taskInfo.taskParams`（**这一次生成真正提交进去的东西**）。
- **实测反例**：改完提示词再点火，回读得 `params.prompt` = 新版、`taskParams.prompt` = **旧版**，`taskParams.duration` 也是旧值 —— **那次生成完全没吃到修改，等于白花一笔积分**。
- **配套**：改 `params` 有「套一层 `settings:` 被静默忽略」的坑 → `key-decisions-part2.md` **E214**。
- **纪律**：**改参数 → 点火 → 回读 `taskParams`**；三者缺一，就等于没验证。只读 `params` 是**最常见的假验证**。

### 1.9 ★ 点火前没确认就一定翻车的一条
> **引用一致性**：**每个被引用节点的 key 必须同时进引用字段（`reference_nodes`，首帧还要进 `start_frame_image_node`）且在 prompt 中有对应双花括号插桩。**
> **只在 prompt 文字里提到节点名、或只把 key 放进 `reference_nodes` 却不在 prompt 插桩，都不算有效引用**——**漏一处就会丢身份 / 丢首帧 / 丢道具，直接翻车。**

---

## 二、★★★ 剧本 / 资产 / 台账接口（R39）

### 2.1 ★ 剧本与分镜表的落点
- **`text` / `script` 节点在平台侧真实存在、可读**（`get_node_details` 能读它们的 `text`）；**但"创建 / 写入"它们的工具在它侧未暴露（未映射）**；
- **★ 已验证的稳定文本落点 ＝ `write_file_v2` / `read_file_v2` / `list_dir_v2`（task-v2 文件，如 `anchors/story.md`、`storyboards/ledger.md`）**；
- **实务建议**：**剧本正文与分镜表用 `write_file_v2` 落文件；节点 `prompt` 里只放本镜生成所需内容**。

### 2.2 ★★ 分镜表的读写（`edit_script_v2` 未映射时的替代）
**用 `write_file_v2` 读写整份文件**（`append=true` 追加 / `append=false` 整体替换）——**改一行即"读回—改—整体写回"**；节点侧用 `update_video_node` / `update_image_node` / `update_audio_node` 改参数。

### 2.3 ★★ 资产库链（**`asset_type` 枚举是重点**）
- **`save_asset`**：**必填 `node_key`**；**可选 `folder_name`（默认文件夹）· `name`（默认取节点名）· ★ `asset_type`（整数分类：`0` 其他 / `1` 角色 / `2` 场景 / `3` 道具 / `4` 风格 / `5` 音效；默认 `0`）**；
- **`search_asset`**：入参 **`query`（按名称模糊搜索）**；**返回每条含 `asset_uuid` / `name` / `url` / `node_type`**；
- **`create_resource_node`**（它侧未映射，平台语义旁证）：**传 `node_type`/`url`/`title`，包装其现有 url；不要用生成工具重建**；**产物能否直接进 `reference_nodes` 需实测**；
- **★ `search_asset` 的循环上限：同一目标最多连续问 3 轮，仍不明确就停下让用户直接指定。**

### 2.4 ★★ `search_canvas_nodes` 的匹配规则
- **匹配对象 ＝ 节点名**（`name` 为"**节点名子串、大小写不敏感**"）；**没有证据表明它匹配 prompt**；
- **类型过滤 `node_type`（逗号分隔，如 `"image,video,reference"`）**；其他过滤：`tag`（**精确匹配**）· `node_keys`（精确列表，OR）· `parent_keys` · `child_keys`；
- **中文分词：未映射** → **建议用连续子串**（不要假设能跨词切分）；
- **分页：`page`（从 1 开始）· `page_size`（默认 50）**；返回含 `total` 与 `canvasId`/`nodeKey`/`type`/`name`/`tag`/`desc`/`parentNodeKey` 的紧凑列表。

### 2.5 ★★★ "批"的定义（终于问清）
- **粒度：是"每批（per batch / per tool-call block）"**——**不是每项目总量、也不是按时间窗**；
- **数量：无依赖调用可并行，一次最多 5 个；有依赖必须串行**；
- **什么算一批：同一轮里发出的一个并行调用块（block）中、彼此无依赖的节点（≤5）**；
- **★ 强制串行 / 单独调用的工具：`ask_human` · `Skill` · `skill_assistant` · `composite_video` · `director_agent_list`**；
- **制作语义上的"批"**：**每批开始前读账本，取"当前全部可做（可创建或可运行）且互不引用"的节点；超 5 个分多轮创建、合并审批；被引用节点未生效的节点不进同一运行批。**

### 2.6 ★★ 重建 3 次仍失败 → **官方动作是【问人】**
**没有"自动换模型 / 自动拆镜"的硬性规定**；**第 4 步不是自行硬试，而是用 `ask_human` 说明原因、影响与可选处理，取得决定后继续**；**提问中要给出可选项**（典型：**换模型 · 拆镜或缩短时长 · 降规格（分辨率）· 去掉被判为失败原因的引用**）。

### 2.7 ★ 无对白片字幕：**常规不应强加**
**字幕服务于对白 / 旁白信息，硬加会损害写实片观感**；**若有片头标题 / 章节卡 / 地点时间标注，那是"包装字卡"不是对白字幕**，应单独评估。
**若确实要走 `edit_video_v4`**：前置＝**所有源节点必须已渲染完成**；它可做静态 / 动态 captions、章节卡、关键词 chip、大标题，**能在没有现成 VO/BGM 时生成 voiceover/BGM**；**额外调用：1 次 `edit_video_v4`（可能先返回 `needs_confirmation`，再二次确认 ＝ 至少 1–2 次）＋ 产出新成片 / 智能剪辑节点**；
**★ 值不值：纯无对白片仅为字幕走这条链不值**（`composite_video` 已能拼接 / 混音）；**只有同时需要转场、字卡、调色、PiP、章节包装等剪辑增值时才划算**。

### 2.8 ★★★ 故事板路径 ＋ `prompt_template` 完整枚举
**★ 推荐：6 镜写实片走"一镜一请求"**（逐镜生成独立视频节点，靠 `reference_nodes` 引用锚点保证一致性），**不要用一张大网格组图去驱动写实视频**——理由：**写实片对单镜构图 / 光影 / 连续性要求高，逐镜可控、可单镜重建、可插桩首尾帧；大网格在写实风格下易互相串味、单格失败要整板重来**。

**★ `prompt_template` 完整枚举（`create_image_node` 已暴露的真实取值）**：
| 取值 | 含义 |
|---|---|
| **`continuous_storyboard_grid_25`** | 25 格连续故事板 |
| **`story_beat_grid_4`** | 4 格故事节拍 |
| **`multi_camera_grid_9`** | 9 机位网格 |
| **`storyboard_panel`** | **单格故事板面板** |
| **`character_face_turnaround_3view`** / **`character_turnaround_3view`** | 角色（面部）三视图 |
| **`product_turnaround_3view`** / **`scene_turnaround_3view`** | 道具 / 场景三视图 |
| **`style_display_board`** | 风格展示板 |
| **`cinematic_lighting_correction`** | 电影感光位修正 |
| **`frame_prediction_plus_3s`** / **`frame_prediction_minus_5s`** | 帧预测（向前 / 向后） |
| **`portrait_texture_adjustment`** | 人像质感调整 |

**★ 6 镜写实若要先出板：用 `story_beat_grid_4` ＋ `storyboard_panel` 补格，但最终视频仍走一镜一请求。**

### 2.9 ★★ 生产台账：平台有现成一家人（`task_*_v2`）
- **`task_create_v2`**（`subject` 必填 · `id` 可选 · `status`(planned) · `task_content` 轻量备注）→ 返回 `id`/`status`/`subject`/`created`；
- **`task_list_v2`**（列全部）· **`task_read_v2`**（读单个完整状态与 `task_content`）· **`task_update_v2`**（更新 status：**planned→in_progress→completed** / subject / task_content）；
- **定位：task 只记"一个最终交付物"的轻量元数据**（需求、决策、工作文件路径、最终输出 `node_key`、当前进度），**不替代正文**；**`completed` 仅在最终视频合成并归档后置位**；
- **★ 一个制作目标 ＝ 一个 task**；
- **★ 推荐台账四张表**（落 task-v2 文件）：
  1. **总表（项目级）**：制作目标 · 比例 · 默认模型 · 分辨率 · 范围 / 镜数 · 用户关键决策 · 当前阶段 · **最终成片 `node_key`**；
  2. **锚点集**：锚点 id · 类型(character/scene/prop) · 标题 · prompt 摘要 · 上游标识 · 节点标识 · 状态 · 失败原因 / 废弃标识；
  3. **分镜表**：镜号 · 标题 · 画面 prompt · 台词/旁白(逐字) · 引用锚点 · 续镜锚点 · 时长 · 比例 · 模型 · 分辨率 · sound · 节点标识 · 状态 · 失败原因 · **重建版本(v2/v3)**；
  4. **变更日志**：变化来源 · 受影响节点 · 用户决定 · 替换关系。

### 2.10 ★ 最容易被跳过但代价最大的一步
> **引用插桩**——**省掉插桩，角色脸 / 场景 / 连续性在后续镜直接漂移，且失败往往到成片才暴露，导致整批分镜返工**。

---

## 三、★★ 声音节点的创建与接线（2026-09-24 实建成功）

### 3.1 `create_node(nodeType="audio")` 的必填项
- **必须带显式 `scene`**（工具描述原文：*nodeType 'audio' additionally requires an explicit scene in params*）→ 实测 `params: {model, scene: "<场景名>", prompt}` **可一次建成**，返回 `a-` 前缀 node_key。
- **模型**：环境声 / 音效 / 人声一体化用 **`seed-audio-1.0`（Seed Audio 1.0）**；TTS 用 `speech-2.8-hd`｜`speech-2.8-turbo`｜`vocal-v3`；音乐用 `vocal-music`｜`mureka-9`｜`mureka-8`；音色设计用 `minimax-voice-design`（全表见 `libtv-model-params.md` §三·补 2）。

### 3.2 ★★ 按"层"分条，不按"事件个数"分条
| 层 | 建几条 | 内容 | 判据 |
|---|---|---|---|
| **连续层** | 1 条 | 环境底噪（贯穿全片、无事件点、电平平稳） | 描述成**一整条时长素材**（15s 片＝15s ambience） |
| **点状事件层** | 1 条 | 该片全部动作音效（椅滑 / 抽屉 / 金属碰 / 脚步），**按镜内时间点**分布 | **同类点状动作合并成一条音效床**，不必每个动作一个节点 |
> **15 秒体量 ＝ 2 条性价比最高**；30s 以上或事件跨多镜再拆 3–4 条。
> **为什么分两条**：连续底噪与点状事件的**电平/处理不同**，分开才能在合成时分别调电平。

### 3.3 ★★ 接线：**声音只接合成节点，不接镜头**
- **音频节点不接 `Vn`**——各镜是 `enableSound=off` 的**哑片**，声音在合成阶段统一混入（与 `libtv-official-qa-part7.md` UV2.9 的解耦口径一致）。
- **直接作为 `X1`（`video-clip` / composite）的音频入边**：`X1.left` 增加 AU 节点；合成入参分两面（★ 2026-09-28 落库注）：**它侧 `composite_video` 用 `audio_list`，我方 MCP 侧用 `audio_tracks`**——每条给 `start_time`（铺满全片省略 `end_time`）。
- **★ 点火顺序约束**：**AU 节点必须先 run 生效，`X1` 才能合成**；`audio_list` 里引用的音频**必须是画布上真实存在且已生效的节点**，不能只写名字或 URL。
- **电平**：视频轨 `video_volume=0`（哑片）→ 否则叠加轨被峰值限幅压至听不见；**三轨原则：人声最高 · 环境音垫底 · BGM 最低**（点状音效略高于环境床）。

---

## ★★ 客户端提交参数原型与任务状态字段（**REA 静态 · 2026-10-15 · 编辑器 bundle**）

> 这是**画布前端真正组装并提交**的形状（`toTaskParams()` 与 `buildRequestData()` 都是前端函数名），**比任何转述都硬**。

**① 参数对象（`toTaskParams()` 的返回）**——图像编辑实测形态：
```text
{ model, prompt, count, modeType:"image2image", quality:"2K", ratio:"auto",
  textList: [], imageList: [ {nodeId, url}, ... ] }
```
**字段名确认**：`model` · `prompt` · `count` · `modeType` · `quality` · `ratio` · **`textList` / `imageList`（元素是 `{nodeId, url}` 而不是裸 URL 字符串）**。

**② 包装函数（`buildRequestData` 的签名）**：
```text
buildRequestData(taskParams, nodeType /* "image"|"video" */,
                 sourceNodeId, projectId, getModel, taskType, teamId)
```
**调用链（前端实测）**：`toTaskParams()` → `buildRequestData(...)` → **`power/calculator` 算积分** → 提交。**算积分与提交用的是同一个 `requestData`** ⟶ 想预知"这次生成要多少分"，复刻 `buildRequestData` 的输出即可。

**③ 客户端任务状态对象（提交后写进 store 的字段全集）**——逐字：
```text
status · progressPercent · result · failedReason · delayInfo · acceleratePower ·
benefitTag · tracking · sessionId · taskParams · taskResult · nodeKeys ·
yieldStage · yieldResumeAt · agentProcessing · scriptV2TaskMode ·
recognizeAssetsOnly · scriptV2TaskContext · scriptV2RecomputedShotIds
```
**可用的新判据**：`delayInfo`（排队/延迟）· **`acceleratePower`（加速档位）** · `benefitTag`（权益标签）· `yieldStage` / `yieldResumeAt`（让出与恢复）· `agentProcessing`（Agent 处理中）· `scriptV2Task*`（脚本 V2 专有）。

**④ Agent 通道的参数形状（智能片头实证）**：`{ agent_name, skillList:[<skill>], prompt, imageList, videoList?, assetId?, refUrlMap }` ⟶ **画布确实会带 `agent_name` + `skillList` 调平台 Agent**，与我方 `run_agent(skills=[…])` 同一形态（`skillList` 是数组）。

### ★★★ 提交体顶层结构（`buildRequestData` 函数体已读 · 2026-10-15）

```text
{ params, metadata:{node_id, project_id}, provider, model, taskType, requestId,
  clientContext?:{userCharacterUuids:[…]}, teamId? }
```
**签名**：`buildRequestData(taskParams, nodeType, sourceNodeId, projectId, getModel, taskType, teamId, modelSchema)`。

**`params` 内部的关键装配规则**（逐条实测）：
- **列表语义三档**：`imageList`/`videoList`/`audioList` 是**URL 字符串数组**；`imageListV2`/`videoListV2`/`audioListV2` 是**对象数组**（带 `width`/`height`/`durationSec`、必要时带 `assetId`，非空才出现）；`mixedList` 元素是 `{url, type, …}`——**用 mixed 时其余三槽被清空**。
- **`cameraPresets` 以"提示词字符串数组"提交**（`cameraPresets.map(p=>p.prompt)`），且只在非 mixed 模式带。
- **`elementList = subjectList.map(s=>s.klingId)`**（主体库走 `klingId`）；微调 `lora` → `loraList:[{modelId,modelType,imageUrl,weight,name}]`；微调 `template` → `effectTemplateUuids`；通用 `effects` 原样带。
- **`advancedSettings` 受模型白名单裁剪**：schema 的 `config.advancedSettings` 存在时**只转发白名单内的键**。
- **`asset://` 协议**：带 `assetId` 的媒体项，`url` 与 `nodeId` **同时**被改写成 `asset://<assetId>`；`_` 前缀内部字段提交前剥掉。
- **角色卡随请求上报**：从四个列表里收集 `characterRef.characterUuid` 去重 → `clientContext.userCharacterUuids`。
- **时长回填**：模型 `properties.derivesDurationFromVideo===true` 时，客户端按**参考视频最大 `durationSec`**取整回填 `duration`。

**★ 三条"最后一步"改写（最容易踩坑）**：
1. **`cameraControl.enabled===false` 时直接删掉 `cameraControl`** ⟶ 该字段**默认存在**。
2. **长视频任务给 params 注入 `agent_name`** ⟶ 走 Agent 通道（不是普通生成）。
3. **视频任务且 `model === "star-video2.5-draft"`（UI 的「Seedance 2.5 样片模式」）时注入 `params.draft=true`** ⟶ **"样片模式"的服务端开关就是它**；另：**`segmentRemakeLock` 把 `modeType` 设成 `videoEdit2video`**（分段重做复用"视频编辑"模式）。

**★ 模式预剪枝（客户端先清槽再提交）**：`text2video` 清 image+video · `singleImage2video`/`frames2video`/`image2video` 清 video · `video2video` 清 image · mixed 模式清其余三槽 · 模型 `digitalHuman===true` **强制 `modeType="singleImage2video"` 并清 videoList** · `segmentRemakeLock` 时 `ratio="adaptive"`。

**★ 任务类型枚举（`getGeneratorTypeFromNode`，新增 4 个）**：`enhanceImage` / `enhanceVideo`（=`IMAGE_EDIT`/`VIDEO_EDIT`）· `subtitleErase` · **`audioEdit`**（形状 `{input_url, format:"mp3", description, audioEditOperation:"lyrics"?, source_audio_node_key?}`，**"歌词"是它的一个 operation**）· `text`（`SCRIPT_GENERATE` 也映射到 `text`）。

### ★★★ 报价接口的请求体规则（**`calculatePower` 函数体已读**）

```text
body = { ...buildRequestData的输出(剥掉 clientContext), params: await c(params) }
if (taskType === "image" || "enhanceImage") l(params)
POST /api/task/generation/power/calculator
```
**→ "算分与提交同体"从推断升级为逐字确认**（唯一差异：剥 `clientContext` + `params` 过 `c()`）。

- **`c(params)`＝参考视频时长补全**：把 `videoList` 与 `mixedList` 里 `type/mediaType==="video"` 的项与 `videoListV2` 对齐，**缺 `duration` 的用 `_httpUrl`（或 `https:`/`blob:`）探测并写回**，**探测不到直接抛错**。→ 这正是 `pricingRule`「按秒计价，参考视频时长计入总时长」的落地：**没有秒数连报价都发不出去。**
- **`l(params)`＝本地图拦截**：检查 `imageList`/`imageListV2`/`image`/`images`/`originImage`/`refImages`/`referenceImages`/`Reference_Image_Intent`/`mark`，出现 `blob:` 或 `data:` 即抛 `LocalImageInputError`。→ **本地图必须先上传成 CDN URL 才能报价/提交**。
- **同族接口**：`calculatePower4Agent` **原样透传、不做预处理**；`calculatePowerBatch` 收 `{list, infiniteSwitch}`（`list` 元素带 `taskId`）；`stopTaskBatch` 收 `{taskIds}`；`skipQueue` / `setAgentTaskBudget` / `releaseAgentTaskYield` / `createLightingTask` / `createVideoOptTask` 同族导出。

### ★★★ `agent_task` 的三条用途（常量已钉死）

| 场景 | taskType | `params.agent_name` | 其他特征 |
|---|---|---|---|
| **长视频** | `agent_task` | **`libtv_agent_generator`** | 由 `isLongVideoAgentTask` 触发 |
| **歌词生成（audioEdit 的 lyrics）** | `agent_task` | **`libtv_audio_edit_agent`** | **prompt 是 JSON 字符串**：`{"operation":"segment","source_audio_node_key":"…"}` |
| **智能片头** | Agent 链路 | `agent_name` + **`skillList:[…]`** | 带 `function_context` / `is_agent:true` |

**非歌词的 audioEdit**：`taskType="audio_edit"`，`params={input_url, format:"mp3", description}`，**`provider` 与 `model` 都是空字符串**。
**★ 结构洞察**：**LibTV 用「`agent_task` + `agent_name`」承载"需要 Agent 编排"的生成**；**歌词路径用"prompt 里塞 JSON"传结构化参数**——平台自己就这么干，值得照抄。

### ★★ Seedance 合规校验：`asset://` 的真正来源（**官方 CLI 文档 · 一手**）

`--run` 触发视频生成时，**若当前模型 schema 满足 `properties.portrait === true` 且 `properties.autoCompliance.enable === true`**，CLI 会在提交 `generation/create` **之前**、按网页端同一规则校验上游图片：

| 情况 | 处理 |
|---|---|
| 图片**已带 `assetId`** | 视为已合规，跳过 |
| 图片**已标记 `portraitCompliantExempt`** | 视为豁免，跳过 |
| 未带 `assetId` / 未豁免，**检测到真人** → 后端签发 `assetId` | **本次请求把该图转成 `asset://<assetId>`** |
| 未带 `assetId` / 未豁免，**未检测到真人** 且后端不签发 | 写入 **`portraitCompliantExempt`**，**继续用真实 URL** |
| **任一图片未通过** | **本次生成中止** |

**→ 三条收益**：
1. 这解释了客户端 `buildRequestData` 里"带 `assetId` 的项把 `url` 与 `nodeId` **同时**改写成 `asset://<assetId>`"——**那是真人合规资产化，不是普通 URL 重写**。
2. **`asset://` 的项不进 `refMap`**（客户端 refMap 生成器显式跳过）——两条独立证据互相印证。
3. **新登两个此前库里零记录的字段**：模型级 `properties.autoCompliance.enable`、素材级 **`portraitCompliantExempt`**。排产时可直接用它判断"这个模型会不会卡真人图"。

---

## ★★ 官方合成与静音字段的实测结论（**LibTV 官方 `music-driven-product-ad/references/libtv-production.md` · 一手 · 2026-10-15**）

**① ★ 静音字段可能"存了但不生效"（本库此前零记录）**：官方实测——在**某条 LibTV 路径**上，**`videoAudioMuted: true` 与 `videoAudioVolume: 0` 被持久化了，但渲染出的原声并没有被静音**。**处理办法**：若**渲染证据**确认该现象在当前路径存在，就**直接设该 clip 的增益**（例如 `decibel: -60`）。**★ 且要记住："有限增益是衰减，不是数学上的静音。"** 若原声无法与不想要的生成音乐分离，**要如实声明"已移除"，不要声称"保留"**。

**② 参数写进字段，不写进提示词**：时长 / 画幅 / 分辨率 / 输出条数**配置在 live 参数字段里**，**不要写进散文式 prompt**（提示词只写画面与动作）。

**③ 别用会诱发剪辑的词**：一镜到底的提示词里**不要把它切成「镜头 / 待剪场景 / 蒙太奇段 / 转场」**——官方原话是**不要用这些词去称呼它的时间段**。

**④ 提交前先"虚拟校验一份生成计划"（本库此前零记录）**：用**确切的模型、参数、提示词、分组与参考**先跑一次**虚拟生成计划校验**，再真正提交。

**⑤ 合成收尾 checklist**：保留干净的环境声床 → 生成后再叠音乐 → **音乐事件与画面事件对齐**（首个强拍＝产品离开主角且机位起动；乐句边界＝穿过硬缝；终止式＝接住/停机/收拾/向右出画）→ 环境声压在音乐之下 → **移除意外生成的音乐/人声/旁白** → 检查起始偏移/增益/淡化/结尾/**最后 1–2 秒空帧停留** → **最终渲染或导出前保存图/合成状态**。

> **★ 另见**：网页端**各任务接口"发什么字段、走哪个 host、失败怎么处理"**的成体系记载（含 `riskControl.deviceToken` 风控注入、**"生成带指纹而报价不带"**、以及一批**静默吞错**的只读助手）→ `libtv-web-api-shapes.md`。

---

## ★★ CLI `--run` 的提交与轮询契约（**REA 静态 · 2026-10-15 · `libtv-pkg-runtime.js`**）

> 上文那套 `buildRequestData` 是**网页端**实现；本段是 **CLI 自己**的实现，两者独立。

- **CLI 网络面只有 31 条 `/api/` 路径**；生成相关 3 条：`task/generation/{create,progress,video/opt}`。
- **create 体（逐字）**：`{params, metadata:{node_id,project_id}, provider, model, taskType, requestId:crypto.randomUUID()}` ＋ 条件 `teamId`（仅当 `projectMeta.teamId` 是有限正数）；**★ `requestId` 每次现场生成** ⟹ **CLI 不复用幂等键**，服务端是否去重 unknown——**别把"稳定幂等键"想当然套到 CLI**。
- **★ `settings`/`advancedSettings` 被摊平到 params 顶层**——这正是 §1.8b"套一层 `settings:` 被静默忽略"的机制解释：**节点存储形状 ≠ 线上请求形状**。
- **CONFIG 六类**：audio/image/video 同名；**script 与 storyboard 都是 `scriptText` + `generatorTaskType:"text"` + `resultKind:"script"`**；**storyboard 节点 `data.type` 必须是 `script`**。
- **group 不支持 CLI run-node**；**video-clip 走 `task/generation/video/opt`**，`taskType:"compose"`，`provider`/`model` 都是 `"media-platform"`。
- **轮询默认 `2000 ms × 600`（≈20 分钟）**，`{taskIds:[taskId]}`；`loading = status 0|1`，**终态 2 成功 / 3 失败**，超时 `poll_timeout`。
- **写回三次**（`nodes/batch`）：提交后 `taskInfo.status=1` → 每轮 → 终态 `resultMerge`（video/audio 另做 MediaInfo 补全）。

**详见** `outputs/libtv_rea_20261014/31_CLI生成提交与轮询契约.md`（C151–C156）。
