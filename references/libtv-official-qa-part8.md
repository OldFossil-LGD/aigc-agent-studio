# LibTV 平台侧官方答疑 · 续册八（UV3 其余接口 10 问）

> **来源**：同 `libtv-official-qa-part7.md`（UV3 节）。
> **读完回哪**：回 `libtv-official-qa-part7.md` UV1/UV2，或 `libtv-official-qa.md`。
>
## UV3 · 其余接口答疑（10 问）

> **★ 它的可信度标注（照抄）**：
> - **已验证（当前工具契约可直接支撑）**：第 1 条的 `prompt_template` 映射、第 5 条的 `analyze_video/analyze_audio`、第 6 条 director `add_group`、第 8 条 `reference_nodes` 与占位符插桩及 `search_asset`、第 9/10 条的模型与模板枚举。
> - **推断（接口未在本工具面暴露，按平台惯例解释，需以真实 API 文档/实测为准）**：`upload_ticket/upload_complete`、`inspect_media`、`manage_group`、`delete_node`、`search_models/get_model`、`create_resource_node/left` 的确切字段名与返回结构。

### UV3.1 `cameraControl` / `enableSlash` / `count` 三个 schema 属性

**这三个是"模型能力声明（capability flags）"，告诉前端该模型支持什么，不等于 `params` 里要原样传这三个键。**

| flag | 含义 | 对应 `params` |
|---|---|---|
| **`cameraControl: true`** | 该图片模型支持"**镜头/机位控制**"（视角、景别、机位方向等） | **没有独立的 `cameraControl` 布尔字段要传**；镜头意图写进 **prompt 自然语言**（如"俯拍/仰视/过肩镜头/特写"）。`true` 只表示"写了会被理解" |
| **`enableSlash: true`** | 该模型支持"**斜杠玩法 / `prompt_template`（预设模板）**" | 工具里就是 **`prompt_template` 字段**。启用时传一个**合法枚举值**；不用就不传（**不存在"普通模板"这个值，想去掉模板只能新建普通节点，不能在原节点上把模板清空**） |
| **`count: [1,2,4]`** | 该模型一次请求**允许出图的张数候选集合**，只能取 1/2/4 | **当前 `create_image_node` / `update_image_node` 工具没有暴露独立 `count` 入参，默认按 1 张处理**；若底层 schema 需要多选，应在创建节点的模型设置里以张数选项表达，**而不是在 prompt 里写**。取值必须落在枚举内，**传 3 之类会被拒** |

**要点**：**flags 描述"能不能"，params 描述"这次怎么做"。** 三者里**只有 `enableSlash` 明确映射到 `prompt_template`**；`cameraControl` 落到 prompt 文案；`count` 在当前工具面未直接暴露。

### UV3.2 `nodeType: "text"` 文本节点怎么用

- 文本节点是承载"**文字内容**"的节点（草稿、说明、文案、参考文本）。读取节点统一用 `get_node_details`，返回里对 text/script 节点给出 **`text`（正文）**。
- **是否叫 `prompt`**：文本节点的正文**一般不是"生成 prompt"，而是内容本体**。不同接入层字段名可能是 `content` / `text`，而不是 `prompt`。**以 `get_node_details` 实际返回的 `text` 字段为准。**
- **能否被引用/被读**：**能被读**；**能否作为生成参考，取决于引用关系是否被支持**。当前图片/视频生成的 `reference_nodes` **主要面向媒体节点**，把文本节点作为引用**并非主路径**——更可靠的做法是**把需要约束的文字直接写进生成节点的 prompt**。
- **当前工具面没有暴露"创建 text 节点"的函数**，无法直接新建；可在前端手动新建，或用 `write_file_v2` 写工作文件、或把文字放进 image/video 节点的 prompt 来承载。

### UV3.3 `script` 节点 与 Script V2 分镜表 的区别

- **`script`（脚本节点）**：**画布上的一个节点**，承载"剧本文本"（对白、旁白、场次等创作内容）。它是**内容载体**，属于画布节点体系，可用 `get_node_details` 读取。
- **Script V2 分镜表**：是 **task-v2 工作流里的"账本/ledger 文件"**（通过 `read_file_v2` / `write_file_v2` 读写，路径如 `storyboards/xxx.md`）。它是**制作流程的结构化表格**：逐镜记录镜头、引用的锚点 node_key、续镜关系、时长、状态等，用于驱动批量生成与回填。**它不是画布节点。**
- **区别核心**：**一个是画布上的"内容节点"，一个是工作流文件体系里的"制作台账"。**
- **能否互转**：**没有一键互转换接口**。可以人工/流程化映射——从 `script` 节点读出正文，拆解后写进分镜表；反向也能把分镜表的台词汇总成剧本文本，但这是**内容层面的搬运，需要保持 node_key 引用一致，不是节点类型转换**。

### UV3.4 `upload_ticket` + `upload_complete` 两段式上传（**推断**）

**标准流程**：
1. **`upload_ticket`**：先请求一个"上传凭证/票据"。入参通常带**文件名、MIME 类型、大小**（可能还有目标用途/目录）。返回：**上传地址/端点、对象存储 key/object_id**、可能还有签名 header、以及一个**待确认的句柄**（ticket/ref 标识）。
2. **实际传字节**：拿 ticket 给的地址，把文件字节 **PUT/POST** 上去（直传对象存储）。
3. **`upload_complete`**：上传成功后回调"完成确认"，带上 ticket/object 标识做服务端登记。返回：一个**稳定的 `file_ref`**（文件引用句柄），可能还有 url、尺寸、时长、哈希等元数据。
4. **`file_ref` 怎么用**：它代表"**已入库的素材**"。在生成里应通过"**资源/引用**"字段传入（本环境等价物是 `reference_nodes`，或先把该资源包成画布节点再引用其 node_key），**而不是把临时 URL 直接塞进 prompt**。

**能否传 `.png` / `.md`**：
- **`.png`** 属于图片，**通常允许**（`image/*`），上传后可作为参考图/首帧图。
- **`.md`** 属于文本文档，**是否允许取决于平台接受的 MIME 白名单**；很多媒体上传通道只接受图片/音频/视频，**纯文本 `.md` 可能被拒或走"文档/附件"通道。不能假定 `.md` 一定可上传。**

### UV3.5 `inspect_media` 分析什么（**推断**，已暴露等价物如下）

- **`analyze_video`**：返回源视频**整体结构 + 分段级视觉分析**（镜头/场景/动作等结构化描述），可限定 `start/end`。
- **`analyze_audio`**：**仅做语音 ASR 转写**，输出 `[start,end]文本` 的**句子级时间轴**；**不检测节拍/BPM/小节/切点，器乐基本为空**。
- **`get_node_details` / `get_media_profile`**：读取**分辨率、是否已有产物、（视频）词级转写与未转写有声段**等。
- **能拿到的结构化信息**：画面分段与内容描述、尺寸/时长、语音文本与时间轴、词级边界等。
- **能否"当参考图使用分析结果"**：**不能直接当**。分析结果是"**描述数据（文本）**"，不是图像本身。要做参考图，**必须引用原始图片/视频节点（`reference_nodes`）**，分析文本只能辅助写 prompt。
- **★ 特别提醒**：**节拍/卡点要用节拍分析工具，不能用 `analyze_audio` 的语句时间戳当切点**；**ASR 句边界含口癖/卡顿，也不宜直接当剪辑入出点**。

### UV3.6 `manage_group` 怎么用 / 与 `director_apply` 的 `add_group` 的区别

- **`manage_group`（若存在 · 推断）**：一般是对"**画布节点分组/文件夹**"做管理——建组、把节点加入组、从组移除、删组。**它操作的是画布组织关系。**
- **`director_apply` 的 `add_group`**：是"**导演控制台 3D 场景内**"的实体分组命令，把 **≥2 个场景内角色/道具/空对象**编成一个组，目的是**让相机能对整组取景**（如 `look_at` 组时自动拉远 fit 全员）。**它作用于 3D 舞台实体，不是画布文件夹。**
- **结论**：**不是一回事。** 一个管**画布节点的收纳**，一个管 **3D 场景里的拍摄编组**；**命名空间和作用对象都不同，不能互替。**

### UV3.7 `delete_node`：硬删还是标废弃（**推断**）

- 从命名看 `delete_node` **倾向"硬删"**（真正移除节点）。
- **但在制作规范里，默认不做物理删除，而是三态管理**：**已创建 / 已生效 / 已废弃**——失败或弃用时"**标废弃（deprecated）**"，并在**账本保留旧 node_key 与原因**，**新建 v2/v3 节点替代**。
- **硬删后引用方会怎样**：存在引用边指向它的节点会变成"**悬空引用（dangling）**"。**通常不会优雅回落为空，而是在运行时校验引用失败、报错或拒绝生成**；具体是报错还是回落空取决于后端，**但绝不应假定安全**。因此推荐"**标废弃 + 新建替换 + 同步更新所有引用方的 `reference_nodes` / 续镜引用**"，而不是直接硬删。
- **被引用节点变化（改参/重跑/被替换）会沿引用链波及派生节点**，需把受影响节点结果作废并重新生成。

### UV3.8 "把一张图/一段文本变成可被引用资源"的接口

- **外部图片**：先用 **`search_asset`** 在素材库里找；若已有，用其返回结果，再由"**资源节点包装**"把现有 url 包成画布节点（工具描述中名为 **`create_resource_node`**：传 `node_type` / `url` / `title` 包出一个节点），随后该节点 **node_key 即可进 `reference_nodes` 被引用**。若平台支持两段式上传（见 UV3.4），则先 upload 拿到 `file_ref`，再包成资源节点。
- **不要把外部 URL 直接塞进 `reference_nodes`**（那是 node_key 专用），**也不要在 prompt 里仅口头提名**（不算引用）。
- **文本**：要让文本"可约束生成"，**最稳的是直接写进生成节点 prompt**；要作为可复用资产，可存成素材库资产或工作文件（`write_file_v2`），再在需要时读取。**当前没有"纯文本资源节点 + 建边"的一等函数暴露。**
- **关于 "left 建边"**：当前工具集**没有暴露名为 `left` 的建边函数**；节点间依赖的正规表达就是 **`reference_nodes` / `start_frame` / `end_frame` / 续镜（`continue_from`、`video_action_type=extend`）** 这些引用字段，并在 prompt 里用**双花括号包住 node_key**的形式插桩。**每个被引用 key 必须同时出现在引用字段和 prompt 占位符中。**
- **一句话**：**外部图 = 入库（上传或素材库）→ 包成资源节点 → 拿 node_key 进 `reference_nodes` 并在 prompt 用占位符引用。**

### UV3.9 查"当前账号可用模型/配额"的接口

- **`search_models` / `get_model` 在当前 Agent 工具面同样未直接暴露**；它侧能看到的模型清单**来自各创建函数的枚举**：
  - **图片**：Lib Image、Lib Image 2.5 Pro、Lib Image 2.5 Fast、General image Pro、General image V2、Midjourney V8.2/V8.1/V7、Midjourney Niji7、Seedream 5.0 Pro。
  - **视频**：Seedance 2.0 / 2.0 Fast / 2.5、Kling O3 / 3.0、Minimax H3、Wan 3.0 / Wan 3.0 Prime。
  - **音频**：Seed Audio（tts/音效）、Mureka V8（音乐）。
- **"账号配额/余额/可用区"这类账户级查询，当前工具集没有暴露函数**；**模型枚举只说明"平台支持"，不等于"你账号有权限/有额度"**。配额需在平台账户/控制台侧查询，或由后端在运行报错时体现。

### UV3.10 提示词模板库（`prompt_template` 全部枚举 · **13 项**）

1. `portrait_texture_adjustment` —— 写实人像质感校正
2. `multi_camera_grid_9` —— 多机位九宫格
3. `story_beat_grid_4` —— 四格故事节拍
4. `character_face_turnaround_3view` —— 角色脸部三视图
5. `character_turnaround_3view` —— 角色全身三视图
6. `product_turnaround_3view` —— 产品三视图
7. `scene_turnaround_3view` —— 场景三视图
8. `continuous_storyboard_grid_25` —— 25 格连续分镜
9. `cinematic_lighting_correction` —— 电影感光效校正
10. `style_display_board` —— 风格展示板
11. `storyboard_panel` —— 单格分镜板
12. `frame_prediction_plus_3s` —— 预测 3 秒后帧
13. `frame_prediction_minus_5s` —— 反推 5 秒前帧

**在哪看全量**：最权威是对应图片模型 schema 里 `enableSlash` 关联的模板枚举（前端"斜杠/玩法"菜单会按模型动态列出该模型实际支持的子集）。**注意不是每个模型都支持全部 13 项**；某模板是否可用**以该模型能力声明为准**。**切换模板会重置该模板专属参数；想从模板节点退回普通出图，需新建普通节点。**
