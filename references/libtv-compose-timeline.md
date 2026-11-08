# LibTV 合成节点（`video-clip`）与时间线字段细则

> **来源**：官方 CLI 文档 `libtv-cli/node-types/video-clip.md` 与 `node-types/image.md`（**一手 · 2026-10-15 读**）。
> **为什么单列**：`libtv-canvas-nodes.md` 已 279 行贴顶；而合成层字段（`clipTimelineData` 必填项、静音/音量语义、两条合成路径）此前在本库**几乎没有记载**（`sourceOffset` / `sourceDuration` / `audioTrackMuted` / `gridType` 全库 **0 命中**）。
> **读完回哪**：`libtv-canvas-nodes.md`（节点全书）· `run-sheet.md` 站 6.6（剪辑与合成）。

---

## 一、`video-clip` 是"属性节点"，不是"模型节点"

- **核心编辑对象在 `data` 顶层**：`cropRange` · **`clipTimelineData`** · `saveToNodeOnComplete` · `url` · `poster`。
- **不走 `model` + `tool_spec` 的 schema 校验**；CLI 对 `params` 做 **JSON patch 式浅合并**；`--run` 走**视频合成任务链路**（与 text/image「选 modelKey 拉 schema」的流程不同）。
- **不在 `libtv model search --type` 的枚举内**（该枚举只有 `text` / `image` / `video` / `audio` / `script` / `storyboard`）。

## 二、`clipTimelineData` 字段（时间线持久化）

| 字段 | 类型 | 说明 |
|---|---|---|
| `clips[]` | 数组 | **时间线片段**；空数组＝空时间线 |
| `videoAudioMuted` | bool | **视频轨原声整体静音**（文档称优先级高于 volume） |
| `videoAudioVolume` | number | 视频轨原声音量 **0–1（会被 clamp）**，缺省 1 |
| `audioTrackMuted` | bool | 音频轨整体静音 |
| `audioTrackVolume` | number | 音频轨音量 0–1，缺省 1 |
| `cropRange` | `{start,end}` | 时间线整体裁剪区间（秒）——**与 `data.cropRange` 的数组形式不同，别混** |

**★ `videoSourceNodeIds` / `audioSourceNodeIds` 由 CLI 自动维护**：`--left*` 连线/断线时按当前入边**重算写回**，**手写也会被覆盖**（与 `imageList` 由连线重算是同一条平台规则）。

## 三、`clips[*]` 的四个必填项（最容易漏）

| 字段 | 必填 | 含义 |
|---|---|---|
| `startTime` | **是** | 片段在**时间线**上的起点（秒） |
| `duration` | **是** | 片段在时间线上**占用**多久（秒） |
| `sourceOffset` | **是** | 从**来源素材**的第几秒开始取（入点） |
| `sourceDuration` | **是** | 从来源素材**取用**多久（秒） |
| `sourceNodeId` | 否 | 来源素材节点 id（**须已连到本节点左侧**的 video/audio 素材节点） |
| `type` | 否 | 应用侧 `ClipType` 的序列化值（视频/音频） |
| `id` | 否 | 同源多段（分割）时用于对齐 |
| **`decibel`** | 否 | **音频推子分贝，约 -60~+20，缺省 0dB** |

## 四、两条合成路径（别把简单的做复杂）

1. **简单首尾拼接**：**只连线、不写 `clipTimelineData`**，直接 `--run` → 按入边顺序首尾相接。
2. **精细剪辑**：用 `-u clipTimelineData={...}` 写 `clips[]`（**来源 id 仍由连线维护**）。

## 五、★ 文档意图 vs 实测的一处冲突（两边都要记）

- **文档意图**（本册第二节）：`videoAudioMuted:true` **"按 0 合成，优先级高于 volume"**。
- **官方另一份产线文档的实测**（`music-driven-product-ad/references/libtv-production.md`）：**在某条路径上 `videoAudioMuted:true` 与 `videoAudioVolume:0` 被持久化了，但渲染出的原声并没有被静音**。
- **→ 结论**：**不要相信"设了静音就真静音"**——**用渲染证据核**；必要时**直接设 clip 的 `decibel`**（如 -60）。**"有限增益是衰减，不是数学上的静音。"**

## 六、附带：图片节点的两条 CLI 映射（同批读到）

- **图片工具九宫格 / 生成器 `/` 面板 → `libtv image shortcut`**：先 `libtv image shortcut list` 抄 `scene` / `label`，再 `libtv image shortcut <scene|label> -n <源图节点>`；**`gridType ∈ {4,9,16,25}` 走"原地改图"，其它走"右侧新建节点（入边＝源节点）"**。
- **图片节点的 `-u` 属性键**：`rotateAngle` · `alt` · `showGenerator` · `url` / `originalUrl` · **`scriptRowHiddenUuid`（与脚本/分镜行的关联 UUID）**。**生成参数一律走 `-s`；改展示名一律走 `--name`。**
- **图片模型抽样（`nebula-ultra`）**：`quality` ∈ `1K/2K/4K`（默认 2K，落 `settings`）· `ratio` 默认 16:9（落 `settings`）· `searchable` switch 默认 1（落 `advancedSettings`）。**`fineTuneType` / `fineTuneModels` / `magicList` / `focusRegion` / `originImage` / `scene` / `cameraControl` 是否进 settings 桶，以 `libtv model <modelKey>` 为准；未进桶的写 `params` 顶层。**

## 七、`data.cropRange` 的示例级校验（官方示例 · 2026-10-15）

`examples/node-types/video-clip.md` 给出的顶层数组形态是
`-u cropRange='[0.2,8.5]'`，并明确要求
**`起 < 止 ≤ totalDuration`**（单位秒）。

**→ 写入前门**：先回读 `clipTimelineData.totalDuration` 与当前
`data.cropRange`，校验两个不等式后再提交；否则只保留字段形状，
不把“数组长度为 2”当成足够条件。

---

## 八、★ CLI 侧的三条硬事实（**REA 静态 · 2026-10-15**）

- **★ `video-clip` 不在 CLI 的后端类型映射表里**：`convertFrontendNodeTypeToBackend` 只有
  `text:1 · image:2 · video:3 · audio:4 · group:5 · script:20`，**未命中一律回落 `1`（TEXT）**；
  而 `video-clip` **确实在 `FlowNodeType` 枚举与 CLI help 行里**（同批缺映射的还有
  `custom` / `video_group` / `video-story`）。
- **既有节点安全、创建路径待验**：更新与合成走
  `buildApiCanvasNodeUpdate({..., backendType: rawApi?.type})`——**后端类型取自服务端记录**；
  而**创建路径**走映射表且无显式 backendType ⟹ **新建 `-t video-clip` 可能被提交成 `type:1`**。
  **本轮未实测，列为"待验证缺口"，不得当结论用**（`--run` 走 `runNode7` 是支持的，那是另一条链）。
- **合成输出节点落位**：`NODE_WIDTH = 350` ＋ `NODE_GAP = 100` ⟹ 新输出视频节点放在
  **剪辑节点右侧 450**（`x+450, y` 不变），并新建一条 `剪辑节点 → 输出节点` 连接
  （`connectionId = randomUUID()`）。
- **`label` 不是持久字段**：`normalizeNodeDataTitle` 会在缺 `name` 时用 `label` 补，
  **然后无条件删除 `label`** ⟹ 改展示名一律走 `--name`，写 `label` 只会被搬走。

**详见** `outputs/libtv_rea_20261014/34_CLI节点类型映射与标题归一.md`（证据 C166–C170）。

---

## 九、★★ 智能剪辑的"模式目录"与素材槽（【REA静态】· 2026-10-16）

> 出处：`outputs/libtv_rea_20261014/65_智能剪辑模式目录与素材槽.md`。
> **本册前面八节讲的是"字段怎么填"；这一节讲的是"这个节点还有一层模式，模式决定它收什么、收几个"。**

`video-clip` 的 `data` 里有一个 **`agentComposerData.modeKey`**；目录形态是
**`{defaultMode, modes[], params}`**，每个模式带一组 **`materialSlots`**
（字段逐字：**`slotKey` · `nodeTypes` · `required` · `min` · `max`**）。

| `modeKey` | 名称 | 槽位（`slotKey` · 认哪些类型 · 必填 · 上下限） |
|---|---|---|
| `default` | **默认模式** | `video` · `["video"]` · 必填 · **1–30** |
| `explainerVideo` | **讲解视频** | `audio` · `["audio"]` · 必填 · **1–1** ； `text` · `["text"]` · 选填 · **0–10** |
| `batchAd` | **批量广告** | `productImage` · `["image"]` · 必填 · **1–10** ； `refVideo` · `["video"]` · 必填 · **1–1** |
| `smartMixCut` | **素材混剪** | `generatedVideo` · `["video"]` · 必填 · **5–30** |

**★ 三条硬事实**：

1. **连线闸只看 `max`**——目标是 `video-clip` 时，客户端**不查连线矩阵**，改按
   **`modeKey` → 模式 → 槽位**：**对每个类型，把"`nodeTypes` 含它的槽的 `max`"求和，
   `已有数 < 求和` 就放行**（四类任一有余额即放行）。**`min` / `required` 不在这个分支里**
   ⟹ **它们不是"连不上"的原因**；**执行点 = unknown**。
2. **同一类型被多个槽覆盖时是"加总"**，不是取最大。
3. **这层是远端配置**：**`videoComposeAgent` ＝ 配置 id `280`**；**内嵌目录只是回退值**——
   **引用上表时必须说明它是"内嵌回退值"**，线上以 id `280` 为准（与 `supportModels` 同族：**内嵌 ≠ 线上**）。

**★ `params`（内嵌回退值）**：`aspectRatios` **6 档**（`21:9` / `16:9` / `9:16` / `1:1` / `4:3` / `3:4`）·
`durationRange` **`{min:0, max:300, default:30}`** · `resolutions` **`["480P","720P","1080P"]`** ·
`defaults` **`{aspectRatio:"16:9", duration:30, resolution:"720P"}`**。

**★ 模式 → skill**：`explainerVideo` / `batchAd` / `smartMixCut` 各挂一个 `skill`
（`skillKey` 形态 **`<slug>-<uuid>`**，`resultType: 3`）。
**⚠ 模式名 ≠ skill 名**：`smartMixCut` 的模式名是「素材混剪」，
它的 `skill.name` 是「**卡点视频制作工作流**」——**两个名字不能互查**。

---

## 十、★★ 写入契约与模式集缺口（【REA静态】· 2026-10-16）

> 出处：`outputs/libtv_rea_20261014/66_智能剪辑槽位消费面与模式集缺口.md`。

**★ `agentComposerData` 的写入契约（就三个字段）**：

| 字段 | 内容 |
|---|---|
| `modeKey` | 当前模式键 |
| `prompt` | 提示词 |
| `params` | 比例 / 时长 / 清晰度（**由目录解析，不是三个独立手填字段**） |

**★ 切模式的行为（别写反）**：

1. **切模式不会覆盖已有 `prompt`**——旧值非空就保留；
2. **只有 `withPreset` 才写入预设提示词**（由 `preset.urlValue` + `preset.prompt` 拼接）；
3. **`withPreset` 还会按 `preset.materials` 建素材节点，并自动打组，组名＝模式名**。

**★ 模式集缺口**：图标组件的**回退表认识 6 个 `modeKey`**（`default` · **`talkingVideo`** ·
**`productUrlAd`** · `explainerVideo` · `batchAd` · `smartMixCut`），**内嵌目录只有 4 个**——
多出的 `talkingVideo` / `productUrlAd` 全语料**各只出现 1 次且只在那张表里**
⟹ **线上目录很可能还有这两个模式**（**`inferred`，不是实测**）。
**→ 判据**：**要报"有哪几个模式"就得先拉远端配置 `280`**；
**不拉就只能报"内嵌回退目录里是这四个"**。

**★ 槽位字段的消费面**：`materialSlots` 全客户端**只有一处被读**，**只读 `nodeTypes` 与 `max`**；
`slotKey` 的用途是**拼节点显示名**（`canvas:videoComposeSlot_<slotKey>`，**6 键 ↔ 6 槽**）；
**`required` / `min` / `promptRequired` / `urlInput` 四条文案在客户端里，但调用点 0 命中**
（**同族 6 个键都有调用点，且本地语料不等于 canvas 全集**）⟹ **执行点 = unknown**。
