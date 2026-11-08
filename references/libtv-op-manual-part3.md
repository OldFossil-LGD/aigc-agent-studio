# LibTV 点火与合成手册 · 续册（**点火审批链** · 2026-09-23）

> **承** `libtv-op-manual.md`（第一–二十五节）。**本册＝第二十六节 点火审批链**（依 `R34`）。
> **★ 与正册冲突处以本册为准。**
> **本轮新增结论（E160–E167）** → `key-decisions-part2.md`：R16 改为「逐引用核」· `pipeline` 的「排镜表 / 故事板 / 声音表」改成三个分开入口（旧版用一个排镜表喂三个门禁，**5 条假 FAIL**）· 退出码 3「没扫到」单独成态· 单镜演练的景别分布判据属**不适用**（未放宽判据）。

---


## 第二十六节 · ★★★ 点火审批链（R34 `i-n8wzcj4pnyjm`）——**决定"能否不要人"的硬边界**

### 26.1 ★ `ask_human(approve_run_node_once)` 的完整入参
**顶层只有一个入参：`questions`（Array\<QuestionCard\>，必填）**。

**`QuestionCard` 字段表**：
| 字段 | 必填 | 取值 / 约束 |
|---|---|---|
| **`mode`** | **必填** | 固定 `"approve_run_node_once"` |
| **`node_keys`** | **必填** | **`Array<String>`（JSON 数组，不是逗号串）**，元素形如 `"i-xxxx"`/`"v-xxxx"`/`"a-xxxx"`；**规则要求"列出关于要运行的每一个节点"** |
| **`question`** | **必填** | 审批卡文案；**约束：不得含裸 ASCII 双引号、反斜杠、控制字符**；**引用标题/用户原话用「...」或《...》** |
| **`options`** | **必填** | **本模式下"恰好两个 `text` 选项"——第一个＝批准（approve），第二个＝拒绝（reject），顺序固定** |
| `node_key`（单数） | 可选 | **本模式用 `node_keys` 复数，不用它** |
**`Option` 字段**：`type`（`"text"`｜`"input"`；**审批卡的两选项必须是 `text`**）· `content`（显示文案）。
**未映射**：一次调用的卡片上限 · **审批卡的返回体 schema**。

### 26.2 ★★ 授权的边界（**原文语义**）
> **"The runtime holds run_node back until the user approves on such a card; each approval covers one run of each listed node."**
- **边界 ＝"每个被列出节点的一次运行"**——**按"节点 × 次数"核销，不是按请求 ID、也不是按时间段**；
- **仅对该批列出的 `node_keys` 生效**；不在列表里的节点不被覆盖；
- **★ 改完参数重新 run 需重新审批**（第二次 run 不在那次授权的字面覆盖范围内）；
- **★ 无 TTL**（契约无时间维度表述）——**按"一次运行"核销，而非按时间核销**；
- **数量上限：未映射**。

### 26.3 ★★★ 外部编排侧**无法触发审批、也无法预授权**
- **`ask_human` 是"会话内工具调用"**——**工具契约没有暴露任何外部 HTTP 入口 / URL / 鉴权头 / webhook / 宿主侧 SDK 方法**；
- **会话内可确证的链路只有**：Agent 调 `ask_human(mode=approve_run_node_once)` → **runtime 暂停 `run_node`** → **用户在审批卡上批准/拒绝** → **runtime 放行**；
- **→ 宿主侧要复用同一机制，必须由平台提供对应的外部 API；该 API 在可见契约中不存在（未映射）。**
- **★ 预授权 / "本画布未来 24h 免审"：不存在**——`ask_human` 入参里**没有任何 TTL / 时间窗 / scope / pre-authorize / grant 字段**；`mode` 的三个取值里也没有"预授权"类型；
- **★ 按"同模型、同分辨率、总量 ≤N 张"放宽审批：不存在这种字段**——**批量的唯一含义是"一张审批卡列多个节点、一次批准覆盖每个列出节点各一次运行"**（＝**"批量逐节点授权"，不是"按总量自动免审"**）。

### 26.4 无审批直接点火会怎样
**在配置为需要审批的流程下，runtime 会 hold 住 `run_node`**（未获批不放行）；**具体报错码/文案：未映射**；**审批开关由运行配置决定**（**设置入口未映射**）。

### 26.5 ★ `ask_human` 的 `mode` 三个取值
**`"single"`（单选）· `"multiple"`（多选）· `"approve_run_node_once"`（运行审批卡）**。

### 26.6 审批被拒
**返回体：未映射**；**规则层面可确证**：被拒节点本次不运行；**改参数属节点变更**（用 `update_*_node`，改后回到"已创建"态）→ **需重新发起审批卡、重新获批才能 run**；**不存在"拒绝后在同一次授权内直接重提"的通道**。

### 26.7 ★★ 其他未映射项
**审批与幂等键的关系**（`ask_human` 与 `run_node` 均无 `idempotency-key` 字段）· **导演台 `capture`/`record` 是否花分、是否走同一审批**（未显式声明；`approve_run_node_once` 的 `node_keys` 语义对应 `run_node` 可启动的 image/video/audio 节点，**未明确把 capture/record 纳入**）。

### 26.8 ★★★ 本节的工程结论（**最重**）
> **外部编排者（我方）无法通过 MCP 工具面绕过审批闸门，也拿不到"预授权"或"外部触发审批"的入口。**
> **→ 在我方自动化里，"点火"这一步当前只有两条路**：
> 1. **由人在客户端审批卡上点一次批准**（`each approval covers one run of each listed node`）；
> 2. **依赖平台另行开放外部 API**（**当前未映射，需向平台确认**）。
**→ 这与本库的阶段门一致：`创建 / 读回 / 校验` 可全自动；`点火` 这一步必须有人在场。**

---

## 第二十七节 · ★★★ 导出 / 合成 / 时间线（R43 `i-g4ef8ngyrwwf`）

### 27.1 ★★ `composite_video` 完整入参（**平台 Agent 侧 · 合成/导出唯一真实工具**）
| 字段 | 必填 | 取值 / 说明 |
|---|---|---|
| **`video_list[]`** | — | **源视频数组，按"数组下标顺序"拼接**（**顺序＝数组位置，无独立 order/index 字段**）；每条 `{node_key(必填), start_position?, end_position?}`；**禁止传媒体 URL**；★ 2026-09-28 落库注：**源节点必须已生效（渲染完成）**，仍在生成中/未生效的不能用于合成 |
| `audio_list[]` | 可选 | **叠加音频轨**（不是拼接，是在输出时间线上叠加混音）；每条 `{node_key(必填), start_time(必填), end_time?}`；**★ 无淡变字段**；★ 2026-09-28 落库注：**源节点必须已生效（渲染完成）**，未生效不能引用 |
| `aspect_ratio` | 可选 | `1:1`/`4:3`/`3:4`/`9:16`/`16:9`/`3:2`/`2:3`/`4:5`/`5:4`/`21:9`；省略＝跟随源 |
| `resolution` | 可选 | **`480p`/`720p`/`1080p`/`1440p`/`2160p`（★ 指短边）**；省略＝跟随源 |
| `output_format` | 可选 | **`mp4`（默认）/`mov`/`mp3`/`wav`** |
| `video_volume` | 可选 | 视频原声线性 0–1，默认 1；**0＝静音** |
| `audio_volume` | 可选 | `audio_list` 轨道线性 0–1，默认 1（**对全部叠加轨统一生效**） |
| `reuse_clip_node_key` | 可选 | 复用已有"智能剪辑/Video Compose"节点 |
**返回：新建 VIDEO 节点的 `node_key`**（纯音频时是音频产物节点）。
**★ 失败语义**：**契约未显式声明事务边界**；**建议按"整体成败"对待，不要依赖部分生效**。

### 27.2 ★★ `edit_video_v4` 完整入参（**多轨剪辑，能力最强**）
**`brief`（自然语言编辑意图）· `source_node_keys[]`（★ 必须已渲染完成，仍在生成中的会被拒绝）· `clip_node_key`（可选）· `style_skill`（可选）**；
**支持**：剪辑 · **转场** · **每轨音量与淡变** · BGM · SFX · **旁白生成** · **字幕** · 图文包装 · **首尾帧导出** · **colour grading（调色）**。
**★★ `clip_node_key`：续作同一部片用它；换新素材即使来源相同也应省略它，否则会覆盖旧片（破坏性）。**

### 27.3 ★★ `edit_audio` 的 4 个操作
| op | 参数 | 说明 |
|---|---|---|
| **`clip`** | `start_sec` / `end_sec` | 单段裁剪，**不受 15s 限制** |
| **`segment`** | — | **自动切成 ≤15s**（按歌词行/节拍对齐） |
| **`transition`** | `transition_duration`（默认 2s） | **首尾淡入淡出** |
| **`volume`** | `decibel` ∈ **[−60, 20]**，0＝不变 | 恒定增益（非淡变） |
**返回：新 AUDIO 节点 `node_key`。**

### 27.4 ★★ 导出必然重编码（**画质损失无法完全避免**）
- **`composite_video` 是"拼接＋混音＋可选缩放/画幅/分辨率"的合成输出，必然重新编码封装**；**当显式设置与源不同的 `resolution`/`aspect_ratio` 时还会缩放，损失更明显**；
- **★ 码率不可控（无 `bitrate`/`crf` 字段）→ 无法保证"流复制（−c copy）"**；**帧率也不暴露（无 `fps`）**；
- **降低损失的做法（规避手段，非无损承诺）**：**`resolution` 留空跟随源 · `aspect_ratio` 留空 · 所有源片段尽量同分辨率/帧率/编码 · ★ 不要把已合成的成片再当源反复多级合成（避免级联重编码）→ 迭代同片用 `edit_video_v4` 的 `clip_node_key` 续改，而不是重走 `composite_video`** · 纯音频用 **wav（无损）**。

### 27.5 ★ 调色与字幕在哪做
**`composite_video` 不能调色**（无色彩/grade/LUT/对比度/饱和度字段）；**调色在 `edit_video_v4`**（能力含 `colour grading`，**用 brief 描述，无独立 grade 参数对象**）；**字幕同样只在 `edit_video_v4`**（见第二十五节 25.7）。

### 27.6 ★ 状态观测（**无 `export_status`**）
**它侧无 `export_status`/`read_timeline`/`apply_timeline_edit`/`export_readiness`/`export_video`/`check_continuity`** （⚠️ **我方 MCP 侧有这些，以我方为准**）；
**可观测状态来自节点四态**：**已创建 · 生成中（重复 run 会失败）· 已生效 · 已废弃**；
**轮询：用 `get_node_details` 看"是否已有输出"，指数退避、设上限**；**超时无独立产物桶——产物始终挂对应画布节点**。

### 27.7 ★ `audio_list[]` 单条**不能**带淡入淡出
**正确做法：先用 `edit_audio` 的 `transition` 预生成带淡变的音频节点，再放进 `audio_list`**；
**★ 若需中间点的复杂包络 → 当前工具未映射，需借 `edit_video_v4` 在时间线上做"按时间的音量淡变"。**

### 27.8 ★★★ 导出阶段最易忽略、代价最大的一条 = **混音电平陷阱**
> **`composite_video` 不对各路电平自动平衡——视频原声与 `audio_list` 线性相加，再由峰值限幅器把"整个混音"整体拉低以防削波。**
> **因此只要保留视频原声（`video_volume` 未设 0），叠加的配乐/旁白就会被压到几乎听不清；而且这是"能成功导出、但成片不可用"的问题，不会被任何 readiness 拦截，往往到最后看成片才发现，需返工重导。**

---

## 第二十八节 · ★★★ 插桩定案 与 批/审口径（R45 `i-qe4m8t55gm6f`）

### 28.1 ★★★ **插桩定案：只有一种写法——双花括号包真实 `node_key`**
> **定案**：**写 `{{i-xxxx}}`（双花括号包真实节点 key）**。
> **依据（工具原文）**：`create_video_node`「write its key as a **double-brace placeholder 双花括号node_key** inline」；`create_image_node`「**every node_key in reference_nodes must appear in prompt as 双花括号node_key**」；系统级约束"**只在文字里提到不算引用**"。
> **★ 关于 `{{Image 1}}`/`{{Image 2}}`**：**"这不是本套工具契约定义的插桩语法……可能是某个前端/产品层在保存或展示时把'第 N 张参考图'渲染成的位次标签（Image 1/2/3），属界面侧别名，而不是调用 `create_*_node` 时应写的内容"**；**不能据此外推"两种等价"**；**`{{Image N}}` 不是受支持的占位符**。
> **★ 取舍制**：**以"工具引用字段能否解析回具体节点"为准——只有能被 `reference_nodes` 解析、且与真实 key 一一对应的写法才作数**；**位次标签即便在 UI 上显示，也不应作为跨系统对接的规范**。
> **⚠️ 本库此前写的"两法并列／优先 `{{Image N}}`"是错的，以本节为准。**

### 28.2 ★ 写错插桩会怎样
**不会静默忽略**——**契约明确"prompt 中出现的每个占位 key 必须确实存在于 `reference_nodes`/`start_frame`/`end_frame` 中"，且"Never use URLs or invented node_keys"** → **强校验关系**（**具体抛出时点未映射**）→ **按强一致处理：占位符、引用数组、真实节点三者必须一一对应。**

### 28.3 ★★ `start_frame_image_node` 与 `reference_nodes` 的关系（**与 R37 口径冲突，标注**）
- **R45**：**`start_frame_image_node` 是独立的专用参数**，**它不会因为"排在 `reference_nodes` 第几位"才成为首帧，而是凭字段身份成为首帧**；**→ 首帧不需要、也不应该在 `reference_nodes` 里再占一个位次去"充当首帧"**；**该 key 同样必须在 prompt 中以 `{{node_key}}` 出现**；
- **R37**：**"三处一致"＝同一 key 同时进 `start_frame_image_node`、`reference_nodes`、prompt 插桩**；
- **⚠️ 两处口径打架** → **稳妥做法：按 R37 的"三处一致"实施**（**多放一次不报错，只是冗余**），**但按 R45 理解其语义**（**首帧的"首位"由专用字段承载，不靠 `reference_nodes` 位次**）。

### 28.4 ★ `modeType`（它侧未映射）→ **它给的"契约语言"等价能力区分**
- **普通图生视频**：用 `reference_nodes` 传参考图（人物/场景/道具）；
- **指定首/尾帧**：用 `start_frame_image_node` / `end_frame_image_node`；
- **多图参考**：放进 `reference_nodes`（**多图之间不要求是"帧序列"**，作为身份/风格/内容参考）；
- **视频续写/延长**：`video_action_type = "extend"`，`reference_nodes` 放被延长的视频（至少一个视频，可再带参考图），**继承源帧尺寸 → `aspect_ratio` 被忽略**。

### 28.5 ★★★ "批"的定案（**外部一次执行 ≠ 天然一批**）
- **批 ＝ 同一轮里的一个并行调用块（无依赖调用一次最多 5 个；有依赖的串行）**；
- **"一轮" ＝ 一次模型返回（assistant turn）内发起的工具调用组织单元**；
- **★ 外部循环"一次执行里发很多次调用"算一批还是多批，取决于它们是否落在"同一次模型返回的同一个并行块"里**：
  - 落在**同一次返回的同一个并行块**（≤5、互不依赖）→ **一批**；
  - 分属多次返回 / 同一次返回里因依赖被拆成先后多块 / 超过 5 个被拆多块 → **多批**；
- **★ 切分标准不是"你外层的 for 循环"，而是"运行时里一次 assistant turn 内的并行块边界 + 5 上限 + 依赖导致的串行拆分"。**

### 28.6 ★ 审批卡**可混类型节点**
**`image` / `video` / `audio` 节点可列在同一张卡的 `node_keys` 里一并审批**（**卡没有按类型分卡的限制**）；**约束在别处：按批发起、授权只对卡上列出的具体 `node_key` 生效，不对整个方案或尚未创建的节点预授权。**

### 28.7 ★ 几处名称澄清（**它侧查无此项**）
- **`director_agent_list`：未映射**——**它工具名单里没有**；**单独调用名单里能确认的是 `director_apply`**（以及 `ask_human`/`Skill`/`skill_assistant`/`composite_video`）；
- **`search_skill_templates`：未映射**——**能以 `create_image_node.prompt_template` 的实际枚举为唯一准绳**（13 项，见第二十五节 25.8）；
- **`generate_video`：未映射**——**它实际拥有 `create_video_node`/`create_image_node`/`create_audio_node` + `run_node`**；**★ "一步到位生成"在它侧是 `create_and_run_video_node`（创建并立即运行）**；**产物形态：无论"先建后跑"还是"即建即跑"，成功后都是同一种产物（挂在该节点上，`node_key` 不变），区别只在"是否当场触发生成"。**

---

## 第二十九节 · ★★★ 我方 MCP 独有接口的**实测 schema**（2026-09-23 · 空参数探得，**零成本**）

> **为什么这一节重要**：`read_timeline`/`apply_timeline_edit`/`export_readiness`/`export_video`/`export_status`/`check_continuity` **在平台 Agent 侧根本不存在**（R43 明确）→ **问它永远问不出来** → **只能自己"空参数调用 → 从校验报错里读 schema"**（**在校验阶段即被拒，不会执行、不会扣费**）。

### 29.1 ★★★ `export_video` 完整 schema
```
export_video(
  project_id: string            # 必填
  idempotency_key: string       # 必填
  clips: ExportClip[]           # 必填
  audio_tracks?: ExportAudioTrack[] | null
  title?: string                # 默认 "Final export"
  video_volume?: number         # 0–1，默认 1
  audio_volume?: number         # 0–1，默认 1
  reuse_clip_node_key?: string | null
)
```
**★ `ExportClip`** ＝ `{ node_key(必填) · start_position?（**源入点，秒，≥0，省略＝源起点**）· end_position?（**源出点，秒，>0，必须晚于 start**）}`
**★ `ExportAudioTrack`** ＝ `{ node_key(必填) · start_time?（**在"输出时间线"上的叠加起点，秒，≥0**）· end_time?（**输出时间线上的叠加终点，不是源裁剪**）}`
**★★ 关键认知（修正）**：**`export_video` 是"直接导出"接口——传 `clips` 即可**，**不必先建"智能剪辑/Video Compose"节点**；**`clips` 的数组顺序即拼接顺序**；**`start_position`/`end_position` 就是在导出时做 trim**（与 `composite_video` 的 `video_list` 同语义）。
**★ 注意**：**它没有 `resolution`/`aspect_ratio`/`output_format`/转场参数** → **导出规格很可能沿用源/项目设置或后端决定（待实测）**。

### 29.2 ★★★ `export_readiness` 完整 schema（**与 `export_video` 同构**）
```
export_readiness(
  project_id: string            # 必填
  clips: ExportClip[]           # 必填
  audio_tracks?: ExportAudioTrack[] | null
)
```
**★★ 与 `export_video` 共用同一套 `ExportClip`/`ExportAudioTrack` 定义** → **标准流程 ＝ 同一份 `clips` 先 `export_readiness` 预检、再 `export_video` 导出** ✓✓✓
**（★ 2026-10-01 实测回填 · 返回结构已全部拿到）**：`export_readiness` 的返回顶层 ＝ `projectId` · `ready`(bool) · **`missingNodes` / `unavailableMediaNodes` / `invalidMediaTypeNodes` / `invalidNodeKeys`（★ 这四个数组就是"不能导出"的全部原因分类，schema 里看不到）** · `checkedNodes` · `graphRevision` · `executionContract` · `evidenceBoundary`。**→ 排障判据**：`ready:false` 时**先看这四个数组哪个非空**——`missingNodes`＝节点不存在 · `unavailableMediaNodes`＝**节点在但媒体没落盘**（"全建不点火"必中此条，实测）· `invalidMediaTypeNodes`＝类型不对 · `invalidNodeKeys`＝key 非法。**`executionContract` 实测原文**：`videoOrder:concatenate_in_list_order` · `videoRange:source_seconds` · **`audioRange:output_timeline_seconds`** · **`mixing:overlay_with_global_video_and_audio_volumes`** · `unsupported:[speed,transitions,transforms,subtitles,per_clip_volume,per_track_volume,audio_source_trim]`。**★ 两条此前未记**：`audioRange` 与 `mixing` 决定了**音频轨是按输出时间线对齐、且混音是"叠加＋全局音量"**——这解释了为什么 `export_video` 的 `video_volume` / `audio_volume` 是**全局**而非逐轨（逐轨音量本就在 `unsupported` 里）。

### 29.3 ★★ `check_continuity` 完整 schema
```
check_continuity(
  node: string                  # 必填 —— 注意：是"单个节点"，不是一组 clips
  projectId?: string | null
  projectContext?: string | null
)
```
**★★ 关键**：**它入参是"一个 `node`"** → **说明它是"查这个节点与其上游的连续性"**（**不是"跨镜成组比对"**）。**（★ 2026-10-01 实测回填 · 返回结构已拿到）** 顶层 ＝ `ok` · `revision` · **`shotCount`** · **`deterministicIssues[]`** · **`adjacentComparisons[]`** · **`visualReviewItems[]`** · **`unverifiableRules[]`** · `summary{errors,warnings,adjacentPairsNeedingReview,visualReviewItems}` · `limitations[]`。**四个数组的形状**：`deterministicIssues[]`＝`{issueId,code,severity,scope,message,nodeId,shotId,evidence{},suggestedAction,requiresVisualReview}`（实测码：`STALE_SHOT_PROMPT` · `SHOT_MEDIA_MISSING`）· `adjacentComparisons[]`＝`{previousShotId,shotId,changedFields[],facts{…},reviewStatus,conclusion}` · `visualReviewItems[]`＝`{ruleId,severity,fromShotId,toShotId,stateEvidence{previous,current},mediaEvidence{…},status,suggestedReview,suggestedFix}` · `unverifiableRules[]`＝`{ruleId,status,reason}`。**★ 与本库旧记载对质（3 镜实测，全部吻合）**：`facts` 实测 **9 类**（characters · scenes · props · shotSize · emotion · cameraMovement · lighting · dialogue · audio）＝本册原写"9 类事实" **✓**；`unverifiableRules` 实测**恰好 3 条**（`CONTINUITY_SCREEN_DIRECTION_AND_AXIS` · `CONTINUITY_VISUAL_IDENTITY` · `CONTINUITY_MOTION_AND_AV_SYNC`）＝原写"3 条没证据不能判" **✓**；原写"9 条看片项"指 **`visualReviewItems` 的 ruleId 种类数**（实测触发 4 种：`CONTINUITY_SHOT_SIZE` · `CONTINUITY_CHARACTER_STATE` · `CONTINUITY_LIGHTING` · `CONTINUITY_AUDIO_BED`）——**是种类不是条数**，写得不够准，此处已校正。**★ 关键纪律**：全部 `visualReviewItems` 的 `status` 恒为 `visual-review-required`、`requiresVisualReview:true` → **它只把"该看片的地方"指出来，绝不替你判连续性**（`limitations` 原文照抄执行）。

### 29.4 ★ 仍待探的 MCP 独有接口（记下）
`read_timeline` · `apply_timeline_edit` · `export_status` · `inspect_media` · `task_status` · `resource_info` —— **同样方法：空参数调用读 schema（零成本）。**

---

## 三十、★★★ 画布写入三律（2026-09-23 实战实测 · 新增）

> **来源**：15 秒 / 3 镜实战画布（`实战_15秒3镜_20260923`）改造中撞出的硬约束，每条都带原始报错。

### 30.1 ★★★ 第一律：参考位顺序＝**建节点时 `left` 数组顺序**，事后不可改
**四条证据链**：

1. **`params.imageListOrder` 不可直写** → 报 `NODE_VALIDATION_FAILED: params.imageListOrder 不可通过 --set 直接设置：媒体列表/排序/混合列表由画布连线重算与 CLI 内部现算得出，请用连线（如 --left/--left-add）调整`
   → **`imageList` / `imageListOrder` / `mixedList` / `mixedListOrder` 四个字段全部是连线派生，字段本身只读。**
2. **`leftRemove` + `leftAdd` 放同一次调用不能重排** → 写成功但 `operationStateUnchanged: true`，回读顺序完全未变（平台当成同一集合，判 no-op）。
3. **分两步"全删 → 全加"也不能重排** → 旧边被"恢复"到原位置，不按新数组顺序落位。
4. **★ 决定性探针**：新建空节点、`left = [S1, A1]`（**S1 创建时间晚于 A1**）→ 回读 `imageListOrder = [S1, A1]`
   → **顺序＝建节点时给的 `left` 数组顺序，与源节点创建先后无关。**

**★★ 落地规则（写进流程，违反即返工）**：
- **需要"排第一参考位"的上游（首帧之于镜头 · 故事板之于首帧 · 主锚点之于派生视图）必须在 `create_node` 时就放进 `left` 数组首位。**
- **补救只能重建节点**（delete + create），且**会级联**：改 F1 定序 → 要重建 V1（F1 在 V1 的 `left` 里位置也漂）→ 再传到 X1。
- **所以"建节点顺序"本身是设计的一部分**：先定好每层参考位序，再建节点；**先建节点、后补边的写法会把先补的边全排到末位。**
- **回退口径**：既已建错且不想重建时，**用 prompt 插桩 + 文字表述承担优先级**（示例：`构图第一依据：{{S1_故事板}}`），并在卡内标明"本节点平台参考位序为后补边、优先级由文字承担"。

### 30.2 ★★★ 第二律：同一画布**写操作必须串行**
`PROJECT_WRITE_BUSY: The original write is still running; retry shortly`
—— 并发发 3 个 `create_node` → **只有 1 个成功，另 2 个被拒**。
**★ 与 `libtv-concurrency.md` 的"节点级互斥"是两个层级的锁**：节点级＝同一节点不可并发生成；**画布级＝同画布任何写操作都要排队**（本节新证）。
**落地**：批量建节点**逐条串行发**，不要放在同一并行调用块；**读操作不受影响**（可与写并发）。

### 30.3 ★★ 第三律：节点类型决定"能接几路"与"能不能当合成位"
| 节点类型 | 实测约束 | 撞到的报错 |
|---|---|---|
| **text**（`aurora-3-prime`） | **最多接受 1 路视频入边** | `当前文本模型最多接受 1 路视频入边，已达上限`（`leftAdd` 传 3 个视频节点，第 2/3 条逐条被拒） |
| **image**（`lib-image-2.5-s`） | **接图片参考入边前必须先 `modeType=image2image`** | `图片生成节点须为图生图模式（params.modeType=image2image）才允许图片参考入边；当前为 text2image` |
| **video-clip** | **★ 合成/时间线该用它，不是 text 节点** | 建 `video-clip` 节点 + `left=[V1,V2,V3]` 一次成功；`counts.timelines` 由 0 变 1（**会在时间线区注册**） |

**★ 推论**：**"合成导出"步的正确节点类型是 `video-clip`**。用文本节点承载合成，既接不满 3 路镜头、也不进时间线区——**本库此前把合成位建成文本节点是错的，已改**。

### 30.4 ★ 三处"引用边不可省"的补课
1. **`Dn → Sn`（分镜卡→故事板）** —— **新增"分镜层"后最易漏的一条边**；缺了它，分镜卡的动作/构图意图传不到故事板，故事板重新变孤岛。
2. **`X1 ← V1/V2/V3`（合成节点引镜头）** —— 即使底层用 `clips` 数组传参导出，**也必须在图上登记引用边**，依赖链才可审计。
3. **派生视图 → 母锚点** —— 凡"派生"必挂一条到其母锚点的边（近距版→主锚点 · 三视图→定妆图 · 机位视图→平面图）。

### 30.5 一句话总纲
> **先定参考位序再建节点 → 逐条串行写 → 合成用 `video-clip` → 派生必有边 → 加一层就补这层到直接下游的边。**

### 30.6 ★★ 本节 §30.1 与 `storyboard-frame.md` §十 的**正面冲突及裁决**（2026-10-01 实测 + 平台 Agent 问询）

**冲突**：§30.1 明写「**故事板之于首帧**」须排在 `left` 首位、总纲又要求「加一层就补这层到直接下游的边」→ 读着像 **S1 必须连 I1**；但 `storyboard-frame.md` §十（标注「实测翻车 · 一字不改保留」）明写**灰度故事板不能直接当图生视频的首帧**，做法 C 标「**不推荐**」。

**裁决（硬契约优先：生成听甲、血缘听乙）**：
- **不建 S1 → I1 的像素参考边**（生成语义听 §十）。依据：平台**无结构参考通道**——
  实测 `get_model("Lib Image 2.5 Pro")` 的属性只有 `enableSlash/magic/cameraControl/mention/count/prompt/template/quality/resolution/ratio/background/modeType`，
  **无 controlnet / canny / depth / lineart / structure 任何字段** → 无法「只借构图不借色」，故取保守解。
- **但必须用「纯文本」在下游 prompt 里登记故事板的 `node_key`**（血缘语义听本节 §30.4）——**纯文本 ≠ 插桩**，不构成引用。
  **★ 此法可行性已实测**：探针节点 `i-T7VLUiLXkK` 在 prompt 里纯文本写了**真 key 与不存在的假 key**，
  结果**既未触发闭包校验、也未生成任何 imageList/videoList/textList** → 纯文本血缘安全。
  随后在真实节点 `i-V4qZiwDlE5`（I1）上应用：回读 `imageListOrder` 仍为 `[A1, A3]`、`textList` 为 `[]` → 血缘登记**零副作用**。

**★ 顺带更正一处口径**：§26.8 已实测「外部编排者**无法绕过审批闸**，也拿不到预授权或外部触发审批的入口」，且 §26.3 明写「**预授权 / 未来 24h 免审：不存在**」——批量**只是**「一张审批卡列多个节点、每个节点各一次」，**不是**「按总量自动免审」。
**这与本库「创建/读回/校验可全自动、点火必须有人在场」的阶段门完全一致**。

**★ 已机检化**：上述裁决落成 `scripts/libtv_orchestrate.py` 的 **R1**（`compliance --spec`），故事板若被当作像素参考连进首帧/镜头即 **FAIL**；若全 spec 无任何纯文本血缘登记则 **WARN**。
