# LibTV 节点字段补遗（`audio` / `text` / `script` / `storyboard`）

> **来源**：官方 CLI 文档 `libtv-cli/node-types/{audio,text,script,storyboard}.md`（**一手 · 2026-10-15 读**）。
> **为什么单列**：`libtv-canvas-nodes.md`（281 行）与 `libtv-compose-timeline.md` 已各自负责节点全景与合成层；**这四个类型的字段级细节此前多处零命中**（`music_length_ms` / `force_instrumental` / `scriptImage` / `shotColumns` / `viewMode` / `linkedImageGroupId` 全库 **0**）。
> **读完回哪**：`libtv-canvas-nodes.md` · `libtv-compose-timeline.md` · `sound-prompt-craft.md`。

---

## 一、`audio`：**时长是毫秒，不是秒**（最容易踩）

- **多数音频模型没有 `modeType.items`**——入边/媒体条数**由 `rules` 与画布连接规则决定**，别去 `items` 里找上限。
- **`scene`**：业务场景/子模式字符串；**模型默认带 `scene` 时，新建会按 schema 自动填初始值**，更新用 `--set scene=…` 覆盖。
- **`originalField` 映射（官方抽样，逐条）**：

| 逻辑字段 | 实际落库键 | 备注 |
|---|---|---|
| `voice` | **`params.advancedSettings.voice_id`** | `originalField: voice_id` |
| `stability` | `params.advancedSettings.stability` | `0 / 0.5 / 1`，默认 **0.5** |
| **`duration`** | **`music_length_ms`（毫秒）** | **未列入 `advancedSettings` 时写 `params` 顶层**；`vocal-music` 枚举如 `30000` / `60000` |
| `instrumental`（展示名「纯乐器」） | **`params.advancedSettings.force_instrumental`** | switch 默认 **1** |

**★ 铁律：音频时长用毫秒（`music_length_ms`），视频时长用秒（`duration`）——两侧单位不同，不可互相抄。**
- `audio` 节点的 `-u` 顶层字段极少（`url` 等，主要由上传/任务链路写入）；**日常改生成参数一律 `-s`**。

## 二、`text`：结果写 `data.content`，还能当"提示词来源"

- **生成结果写回 `data.content`（`string[]`）**；手工编辑也走这个键。
- 支持多模态槽位 `modeType ∈ {image2text, video2text}`（取值以 `properties.modeType.items` 为准）；**文本模型常没有 `config.settings`/`advancedSettings` 分桶**。
- **★ 一条组合用法**：**把 `text` 节点连到 `image` 节点左侧再 `--run`，text 的内容就成为图片模型的提示词来源**。

## 三、`script`：节点本体就是一张分镜表

- 节点本体是「**行 + 列 + 视图模式**」的分镜表；**`-s model=` 只接受 `scriptText` 维度 support 列表里的 `modelName`**；**配图侧用 `scriptImage` 维度的图片模型**（`model search --type script` 会同时列出这两组）。
- `scene` 新建默认常为 **`script-generate`**。
- **`-u` 是改分镜表的主入口**；其中：

| 键 | 读写 | 说明 |
|---|---|---|
| **`rows`** | **可写（主入口）** | 分镜表行数据 |
| `title` | **CLI 可写 + 运行时字段已证** | 脚本/分镜业务标题，**与 `name` 独立**；不是展示名改名通道 |
| `linkedImageGroupId` | **只读** | 关联的分镜图组节点 id（跑分镜图时画布自动写），**勿手设** |
| `viewMode` / `shotColumns` / `activeViewId` / `sourceType` / `scriptModel` / `imageGenConfig` | — | 与 `storyboard` 共用（见第四节） |

表头列标题由服务端 `shotColumns` 决定，缺省时画布用默认中文表头——**不必手设**。

### `rows[*]` 关键字段（`StoryboardRowCli`）

| 字段 | 说明 |
|---|---|
| `shotNumber` | 镜号，从 **1** 递增；**展示用，不建议手改**（画布按行序自动重排） |
| **`durationSeconds`** | 单镜时长（秒），**范围约 1.0–15.0** |
| `plotDescription` / `shotSize` / `characterAction` / `emotion` / `sceneTags` / `lightingAndAtmosphere` / `audioEffects` | 逐列内容 |
| `characters[]` | 角色数组；**画布按各行 `characters` 的最大数量动态加「角色」列** |
| **`videoReference`** | **该镜头的"参考帧图片"，不是参考视频片段**（名称极易误读） |
| `id` | 行唯一标识，用于与分镜图组 item 关联；新增行可省略由后端补 |

**整列改值时按行重写整个 `rows` 数组传入**；除 `shotNumber` 外其余字段均可编辑。

## 四、`storyboard` 与 `script` **共用同一套数据结构**

- **`data.type` 恒为 `script`**，由 React Flow 的 `type` 区分两者 ⟹ **CLI 改参、校验、`--run` 完全同一套路**；`model` 仍须落在 **`scriptText`** support 里。
- `libtv model search --type storyboard` **返回 `scriptText` + `scriptImage` 两组模型**（等价于 `script`）。
- 两节点的 `-u` 键集合一致：`rows` / `title` / `viewMode` / `shotColumns` / `activeViewId` / `sourceType` / `scriptModel` / `linkedImageGroupId` / `imageGenConfig`。
- **常见做法**：先用 `script` 生成剧情结构，再用 `storyboard` 做镜头层视图——**两者间的连线与数据同步行为不在 `libtv node` 的直接能力范围内**（以画布实现为准）。

## 五、`libtv script storyboard`：脚本行的批量分镜图（**官方 `commands/script.md` · 一手 · 2026-10-15**）

**这是 `libtv script` 目前唯一的子命令**，对齐画布上的「生成分镜」按钮；**创建/修改/连线脚本节点本身仍走 `libtv node -t script`，单节点文本生成走 `libtv node "<脚本>" --run`——都不经本命令**。

**① 前置硬条件（不满足直接报错）**：
- 目标必须是 **`script` 节点**（否则报「非脚本节点」）；
- **必须已有分镜行 `data.rows`**——没有就报 **「没有可分镜的行」**，需先 `libtv node "<脚本>" --run` 生成。

**② 它做什么（三阶段）**：
1. 读脚本节点已保存的 **`imageGenConfig`**（**可用 `-s` 覆盖**）；
2. 在脚本节点**右侧**创建 **storyboard image 类型的普通分组**（`data.type=group` / **`data.storyboardGroupType=image`**），并**按 `rows` 行数派生同等数量的 `image` 子节点**，**入边来自脚本节点**；
3. 对每个分镜图节点**按顺序**执行与 `libtv node --run` **同源**的生成与轮询。

**③ `-s` 的语义**：规则与 `libtv node create --set` **完全一致**（首个 `=` 拆键值；值可为 `true`/`false`/数字/JSON；**`settings` 与节点已有值做浅合并**）；**未传 `model` 时取 supportModels `scriptImage` 的默认首项**。

**④ 输出协议（可直接当机读判据）**：

| 流 | 内容 |
|---|---|
| stdout | `groupNodeKey` · `scriptNodeKey` · **`imageNodeKeys[]`** · `group`（分组节点详情）· **`imageGenerationRan`**（布尔）· **`imageRuns[]`**（每子图 `{nodeKey, ok, taskId?, status?}`） |
| stderr | **`[storyboard image-run] node=… task=… status=… progress=…%`**，**约每 3 分钟一条** |

**⑤ ★ 退出码与状态码**：**任一子图终态失败（`status=3`）或 run 失败时，命令退出码非 0**。
**→ 与本库既有实测互证**：`libtv-canvas-anatomy-part2/part3.md` 从真实画布读出的「**`status:2` 成功**」与此处官方给的 **`status=2` 成功 / `status=3` 失败** 完全一致——**这条状态码口径现在有一手文档佐证**。

**⑥ 一条典型双步流水线**：`node create -t script --prompt … --set model=…` → `node "<脚本>" --run` → `script storyboard "<脚本>"`。
**⑦ 不读 stdin**（与 `group`/`upload` 不同）。

## 七、`libtv image shortcut`：把画布九宫格/`/` 面板搬到 CLI（**官方 `commands/image.md` · 一手 · 2026-10-15 读**）

**两个子命令**：`list` 与 `<scene|label> -n <node>`。**范围**与 `libtv node` 一致（`-p` / `-g` / 目录绑定）。

### 1. `list`：先抄 `scene` / `label`

- **无选项**（**不接受 `-t/--type`**——本命令固定只针对 `image`）；
- stdout 含 **`nodeType`（固定 `"image"`）** 与 **`items[]`**，每项：

| 字段 | 说明 |
|---|---|
| **`scene`** | **稳定 key**，执行时的**首选**匹配 |
| `label` | 中文展示名（如「电影级光影校正」「多机位九宫格」） |
| `explain` | 说明文案（**可能为空**） |
| **`gridType`** | `4` / `9` / `16` / `25` / **缺省**；**命中 4/9/16/25 走"原地改图"，其余走"新建节点"** |

**★ runtime 差异（C117）**：当前登录态 `image shortcut list` 回读 16 项，实际键只有
`scene` / `label` / `explain`，`gridType` 出现次数为 0。**因此把 `gridType` 当可选字段**：
脚本不能把 `select(.gridType)` 当完整筛选，也不能因字段缺失判 Slash 不存在；执行分支在
字段缺失时按官方“其它（含未声明）→ 右侧新建节点”规则处理。

### 2. `<scene|label> -n <node>`：两条执行分支

**定位解析优先级（逐级退化）**：**① `scene` 全等 → ② `label` 全等（重名会报错并提示改用 `scene`）→ ③ `scene` 前缀唯一命中**；都不匹配时会建议先跑 `list`。

| `gridType` | 画布落点 |
|---|---|
| **4 / 9 / 16 / 25** | **原地改图**：对 `-n` 的**源节点**直接**改展示名为 `label`**、合并 Slash params（**`prompt` 强制为 `/`**），再对**同一节点 run 一次** |
| **其它（含未声明）** | **右侧新建节点**：在源节点右侧偏移处新建 `image`，**入边 = 源节点（replace 语义）**，合并 Slash params 后 **run 新节点** |

**★ 三条容易踩的约束**：
1. **`-n` 必须是 `image` 类型**，且**该源节点必须具备参考图**（**入边**，或**本节点自身已有 `http(s)` 图**）——否则报错（提示需「参考图」）；
2. **`--x/--y` 只在"新建节点"分支生效**（默认 X ＝ 源节点绝对 X **+420**，Y 与源节点齐平）；**"原地改图"分支直接忽略**；
3. **不读 stdin**——要连上游仍得用 `libtv node --left*`。

**输出**：stdout 与 `libtv node --run` 的**最终成功帧同构**（含 `nodeKey`、`data`），**接管道时为单行 NDJSON**，可被 `libtv node` / `libtv group` 当上游消费；**stderr 进度前缀 `[run-node]`**。

## 八、★★ 工作流（workflow）与 Studio：两条"可保存的容器"（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

### 一、工作流**绑定在分组节点上**（本册此前未记）

- **建工作流**：`POST` 请求体逐字为 **`{ sourceProjectUuid, sourceGroupKey, name, description, tags: <数组 join(",")>, snapshotData, coverUrl, teamId? }`**；
- **★★ 快照规则（可直接照抄）**：**`snapshotData` ＝ "该分组的节点（含其子节点）" ＋ "两端都落在这个节点集合内的边"**——**即"组内节点 + 组内边"，跨组边不进快照**；
- **响应三形态兜底**：`code===0` 后取 uuid 时依次尝试 **`data.workflow.uuid` → `data.uuid` → `data.workflowUuid`** ⟹ **服务端返回结构在不同版本间变过，读回时要容错**；
- **★ 回写**：建成功后会**把 `{ workflowUuid, workflowScope }` 写回那个分组节点的 `data`** ⟹ **"工作流"是挂在分组节点上的属性**；
- **改工作流**：`POST { workflowUuid, snapshotData, teamId? }`。
- **列工作流**：`POST { page, pageSize, name?, withPublic?, teamId?, userIds? }`；个人/团队库入口都按页取数。
- **读详情**：`GET { workflowUuid }`，消费方先取 `data.workflowDetail ?? data`，再解析 `snapshotData` 为 `{nodes, edges}`；缺快照报 `workflowNoSnapshot`。
- **删工作流**：`POST { workflowUuid }`；客户端先做权限判断，`code===0` 后才移出本地列表。
- **错误分档**：create/update/delete 可带条件 session 字段且 `code===10101` 抛会话冲突；list/detail 异常吞成 `undefined`，调用方必须自行区分“空结果”和“失败”。
- **版本端点负搜索**：`workflow/version/list`、`workflow/version/snapshot`、`workflow/studio-stack/list` 各只有 1 个 endpoint 定义 token、无 wrapper/调用点，契约保持 unknown。

**→ 与我方编排的关系**：**平台把"一组节点＋组内边"封装成可复用工作流的粒度，正是"分组"**。要复用一套子图，**先把节点收进一个分组，再存工作流**。

### 二、Studio ＝ **LibTV 3D-BOX**（"3D 动画预演"容器）

客户端文案给出的官方定位（逐字要点）：

| 文案键 | 原文要点 |
|---|---|
| 标题 | **「LibTV 3D-BOX · 你的专业影视空间」** |
| 副标题 | **「Agent 轻松搭景，精准调度站位，手绘轨迹实现大片级运镜」** |
| 输入框提示 | **「描述场景、人物动作和镜头怎么动，AI 帮你生成 3D 动画预演」** |
| 我的项目 | **「我的 3D-BOX」** · **「新建空白 3D-BOX」** · **「未命名 3D-BOX」** |
| 保存 | **「已保存到 3D-BOX」**（**云端保存**） |
| 分享 | **「个人项目链接，访问仍受项目权限限制」** |

**★ 三条可用的行为事实**：
1. **它是"云端项目"**——有列表/删除/"加载更多"，且**删除不可恢复**；
2. **生成中是"部分锁定"的**：文案明写**场景生成期间可继续浏览，但元素的平移/旋转/缩放暂不可用**；**取消等待后当前场景保留**；**生成结果保存失败时场景也保留**；
3. **打开失败的官方自查三项**：**是否已切到项目所在的个人空间或团队** · **项目链接是否完整正确** · **项目是否已被删除或停止分享**。

**→ 与本库既有记录的关系**：本库此前记过"3D-BOX 属客户端功能、48 工具表无专属接口"（**仍成立**）。本节的增量是**客户端侧的具体行为与失败自查**——**它验证了"手绘轨迹预演运镜"确实是该模块的官方卖点**。

---

## 九、官方 `examples/node-types/*` 补齐与跨文档冲突（**官方一手 · 2026-10-15 读**）

### 1. 最后 8 份示例已读齐

本轮读完 `libtv-cli/examples/README.md` 与
`libtv-cli/examples/node-types/{audio,image,script,storyboard,text,video-clip,video}.md`
共 8 份。它们与权威页共同确认：

- 通用前置仍是**登录 + 项目绑定（或 `-p`）**，普通分组再用 `-g` / `group use`；
- `text.content`、`script/storyboard.rows`、`video-clip.clipTimelineData`
  都是 **JSON 字符串经 CLI 解析后写入**；
- 展示名：**默认子命令用 `--name`，`node create` 的展示名由位置参数承载，
  `node create` 不接受 `--name`，`-u` 也不允许写 `name/label`**；
- `mixed2video` 示例至少连接 1 张参考图；实际数量仍以实时
  `modeType.items` 与 `mixed2videoConfig` 为准，示例的“至少 1”不是跨模型全局承诺。

### 2. ★ `title` 的文档冲突已由 CLI 源码与只读回读解开

| 来源 | 结论 |
|---|---|
| `libtv-cli/node-types/script.md` | **`title` 只读，勿手设**（语义层口径） |
| `libtv-cli/node-types/README.md`、`examples/node-types/{script,storyboard}.md` | 把 `title` 列入/示例为可 `-u` 写入 |

**→ CLI 层结论（已由恢复载荷证实）**：`UPDATE_REJECTED_KEYS` **不含 `title`**；
`-u title=…` 会进入 `dataFieldsPatch`，通过该键作为 extra allowed key 的校验，
经 script refine 后进入 `buildApiCanvasNodeUpdate` 的 `data` JSON。
因此 **CLI 接受并发送 `title`**。

**→ 运行时互证（只读回读）**：画布 `d90119b61e5044a0908ebd571298e1c9`
的节点「脚本 4」回读为 `data.title="春分的“误会”"`、
`data.name="脚本 4"`、节点 `name="脚本 4"` —— **`title` 确实是独立、
已被服务端保存的业务字段**。

**→ 仍未验证**：没有直接提交 `-u title` 再回读，因此 CLI 更新回路是否原样持久化、
是否与任务结果回写互相覆盖，**仍未实测**。展示名仍走 `--name`。

### 3. `rows` 的深层更新必须整块重写

- `-u rows='[...]'` 接受 JSON 字符串，CLI 内部解析；
- 示例明确说 `rows[0].plotDescription` 这类深层键**目前必须整块赋值**
  （先读回完整 `rows`，替换目标行，再写回完整数组）；
- 这条与 `libtv-node-field-notes.md` 的“整列改值按行重写整个 rows 数组”一致。

---

## 十、发布 / 模板 / 可见性 / user-config 的平台字段（**登录态网页 bundle · 一手 · 2026-10-15 读**）

> **来源**：`outputs/libtv_rea_20261014/28_发布模板可见性与用户配置服务族.md`（证据 C133–C143）。
> **边界**：这一族**只存在于网页端**——恢复的本地 CLI 载荷与官方 `libtv-cli`、插件文档对
> `project/publish`、`project/template/`、`visibility/set`、`user-config`、`artifact-version` 命中数均为 **0**，**别写 CLI 脚本去调**。
> **本节写请求全部是客户端源码证据（observed 静态），没有一条真实写请求被观测过**；只有 `user-config/get` 有真实 200 响应体。

### 1. 发布 / 重新发布：请求体与快照格式

**新建发布**（`canvasProjectPublish`）提交 `projectUuid, name, description, coverUrl, finalOutput, snapshotData`
加可选 `tagIds?, socialMediaUrl?, teamId?, protectedNodes?, sessionIds?`。
**重新发布**（`canvasProjectTemplateRepublish`）把 `projectUuid` 换成 `projectTemplateUuid`，其余键同构。
可选键是**条件携带**：`tagIds` 非空才带、`socialMediaUrl` 非空才带、团队场景才带 `teamId`、
选中 Agent 会话非空才带 `sessionIds`。

**★ 快照不是对象，是 JSON 字符串**：

- 公开发布模式下 `snapshotData = JSON.stringify({nodes, edges, savedAt: Date.now()})`；
- 非公开模式提交字面量 `"{}"`；
- `nodes` 是过滤过受保护节点的数组，`protectedNodes` 只在受保护集合非空时另带。

**客户端提交前硬门（按顺序）**：缺成片 `finalOutput` → 缺封面 `coverUrl` → 缺 `name` → 缺 `description` → 缺已签协议标记，任一命中即中止；
活动场景还要选赛道、填社交媒体地址，并按需先走报名；发布模式下画布节点为空也直接返回。

**成功判定**：新建发布看 `data.templateUuid` 是否存在，存在则把 uuid 写回画布；重新发布 **`data.templateUuid` 或 `code===0`** 都算成功；失败取 `msg`。
埋点会深拷贝请求体并**删掉 `snapshotData`** 再上报。

### 2. 模板详情：读回路径与标签推导

`GET {projectTemplateUuid}` 的消费方按 **`data.detail ?? detail`** 兜底，
读取 `name / description / coverUrl / finalOutput / snapshotData / socialMediaUrl / sessionIds / sessionSnapshots`。

**标签推导**：只取 `tagType===5`；先找 `parentTag===0` 的父标签当 `tagId`，再找它的子标签当 `trackId`；没有父标签时按 `parentTag` 反推。
**会话推导**：`sessionSnapshots[].sessionId` **优先于** `sessionIds`。

**模板管理另一套调用面**：客户端另有一个类 API，用硬编码路径 `template/list`、`template/like`、`template/check`、`template/setTop`、`template/republish`、`template/delete`；
其中 **`check` / `delete` / `like` / `setTop` 四条不在 endpoint 常量表里**
（常量表 226 条定义 / 224 条唯一路径，与之差集正好是这四条）。删除提交 `{projectTemplateUuid}`，`code===0` 才算成功。

### 3. 节点可见性：`hidden:false` 是"取消隐藏"

`POST canvasNodesVisibilitySet`，请求体 **`{projectUuid, nodeKeys, hidden}`**。
wrapper 在 `code` 存在且非 0 时抛错并返回 `data`。
唯一调用点的场景是**分析任务完成后的分组构建**：先把目标节点、其后代与子节点 key 汇总，`hidden:false` 取消隐藏，**然后**才构造分组。
**做分组前先取消隐藏**是这里的既有顺序。**★ 2026-10-16 第一百零四轮补全**：**“唯一调用点”已按全语料复核——逻辑 1 处、构建 2 份**（`3my9dn99359ls.js` `cc2d58e2…` 与 10-16 重取的孪生 `3sf_g68q_zllq.js` `939a9f4c…`，**全语料搜 `nodeKeys:[...p],hidden:!1` 命中数 ＝ 2**）；**`nodeKeys` 的构造逐字** ＝ `p.add(e.nodeKey)` ＋ `ei(e)`（后代） ＋ `d` 里 `parentKey===e.nodeKey` 的子节点，再 `[...p]` 展开。**★★ 客户端没有任何分批**：**全语料在 `nodeKeys` 附近没有 `slice`/`splice`/`chunk`/`batch` 任何一处**，请求体就是整份 Set 展开 ⟹ **批量上限（若有）在服务端，客户端侧不可见，仍为 unknown**（**另一个吃 `nodeKeys` 的 `canvas/node/detail` 也是逐个 `URLSearchParams.append`，同样不分片**）。**★★ `hidden` 一词在本 bundle 里有两个完全不同的载体，不许混**：**① 接口体字段 `hidden`**——**唯一调用点传的是 `!1`（取消隐藏），`!0` 从未到达这个接口**；**② React Flow 的节点渲染字段 `node.hidden`**——**在画布 store 里就地置位**（如 memo 的 `{...e,hidden:!0}`），**同一流程里还有 `updateNode(t,{hidden:!1},{bypassEditLock:!0})` 走本地 store** ⟹ **“取消隐藏”其实有两条通道：本地 store 更新 ＋ 服务端接口**，**只有后者被本接口承载**；**★ 看到 `hidden` 先问“是哪个对象的 `hidden`”。**

### 4. user-config：真实响应与两个开关

**唯一有运行时证据的响应体**（`user-config/get`，200，162 字节）：

```json
{"code":0,"data":{"config":{"agentPowerLimitEnabled":true,"agentPowerLimit":10,"updatedAtMs":1789918532764,"dryrun":true}},"msg":"","trace_id":"qHvkbiTv4cTBf8Qq"}
```

**字段口径**：服务端是小写 **`dryrun`**，客户端归一化成 **`dryRun`**；`updatedAtMs` 与 `agentPowerLimit=10` 是**该账号当时的取值，不是平台常量**。
请求头名称含 `token` / `webid` / `x-language` / `x-log-id`（**只记录名称，未记录值**）。

**两个写入口**（均为客户端源码，未实测写成功）：

| 入口 | 请求体 | 客户端判定 |
|---|---|---|
| `user-config/update` | `{dryRun:boolean}` 或 `{agentPowerLimitEnabled:boolean, agentPowerLimit?:number}` 或 `{agentPowerLimit:number}` | `code===0` |
| `user-config/space-power-limit/update` | `{projectSpaceId, enabled:boolean}` | 回读 `data.enabled === 请求.enabled` |

**空间额度**那条只有一个调用点：`continue_generation` 流程里传 `enabled:false`（关掉该空间额度限制）。
**全 bundle 没有 `spacePowerLimit*` 标识符**，所以字段就是布尔 `enabled`，不是数字额度。

**`dryRun` 与 `agentPowerLimit` 的 Agent 侧传播见 `libtv-agent-protocol.md` 的"干跑与额度闸"一节。**

### 5. 仍未解

`artifact-version/get` 与 `artifact-version/save` 在常量表各 1 条定义，**无 wrapper、无调用点、无运行时请求**；CLI 与官方文档 0 命中。
请求/响应与生命周期保持 **unknown**，**不许按"可能是版本历史"自行补写契约**。
