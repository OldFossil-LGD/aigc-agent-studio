# LibTV 节点类型全表（枚举 19 · 显示名 21）（【REA静态】）

**这一册只做一件事：把"画布上到底有哪些节点类型"一次列清，并说清"六种"该在什么范围里说。**
出处：`outputs/libtv_rea_20261014/63_节点类型全表与六种的关系.md`。
> ⚠ 与 `libtv-canvas-nodes.md` §一 的关系：那册写的是 **"节点类型只有六种（`create_node` 的 enum）"**——
> **那句话只在 `create_node` 这一层成立**；**客户端实际认识 19 个值**。两处不要混着引用。

## 一、★★ 客户端枚举：**19 个值**

```text
text · image · video · audio · custom · group · script · script-v2 · video-story ·
video_group · video-clip · space-scene-720 · material-style · material-lens ·
reference · director-console-3d · director-studio · shot-breakdown · screenplay
```

## 二、★★ 显示名对照（21 键 · 逐字）

| 值 | 中文显示名 |
|---|---|
| `text` | 文本 |
| `image` | 图片 |
| `video` | 视频 |
| `audio` | 音频 |
| `custom` | 自定义 |
| `group` | 分组 |
| `script` | 脚本 |
| `script-v2` | **脚本 V2** |
| `video-story` | 视频故事 |
| `video_group` | 视频组 |
| **`video-clip`** | **智能剪辑**（**界面名；本库别处叫它"合成节点/时间线片段"**） |
| `space-scene-720` | 720°全景 |
| `material-style` | 风格 |
| `material-lens` | 特效 |
| `reference` | 参考节点 |
| `director-console-3d` | 导演台 |
| `director-studio` | Director Studio |
| `shot-breakdown` | 逐帧拉片 |
| `screenplay` | 剧本 |
| `storyboard`（**不在枚举**） | **脚本**（**与 `script` 同文案**） |
| `temp`（**不在枚举**） | 临时 |

**★ 两条**：
1. **`storyboard` 与 `script` 共用"脚本"**——与"`script` / `storyboard` 共用 `data.type=script` 结构"一致；
2. **映射表比枚举多 `storyboard` 与 `temp`** ⟹ **"映射键数" ≠ "枚举取值数"**。

## 三、★ "六种"该怎么说

**"六种"＝ `create_node` 层能创建的类型**：`text` / `image` / `video` / `audio` / `script` / `video-clip`。

**不在六种里的**：`group` · `video_group` · `video-story` · `script-v2` · `reference` · `custom` ·
`director-console-3d` · `director-studio` · `space-scene-720` · `material-style` · `material-lens` ·
`shot-breakdown` · `screenplay` ——**它们要么由客户端自己建，要么由特定功能（导演台 / 拉片 / 全景 / 风格特效）建**。

**→ 判据**：**说"只有六种"必须带限定语"在 `create_node` 层"**；说"平台只有六种节点"是错的。

## 四、★★ 连线合法性：按 `action` 判，不按"类型"判

> 出处：`outputs/libtv_rea_20261014/64_连线合法性客户端实现.md`（**【REA静态】**，2026-10-16）。
> **客户端不是按"类型×类型"判连线**——先做 **`type → action`** 降维，再查一张 **19×19** 的布尔表
> （表在客户端模块里，**自带中文说明"节点 action 之间的连线关系映射表"**）。

### 4.1 `type → action` 候选表（【REA静态】）

| 节点 type | 候选 action |
|---|---|
| `text` | `text_generate` · `text_resource` |
| `image` | `image_generate` · `image_edit` · `image_resource` |
| `video` | `video_generate` · `video_edit` · `video_resource` |
| `audio` | `audio_generate` · `audio_resource` |
| `script` / `script-v2` | `script_generate` · `script_resource` |
| `video-story` | `video_story_resource` |
| `video-clip` | `video_clip_resource` |
| `space-scene-720` | `director_console_panorama_input` |
| `material-style` | `material_style_resource` |
| `material-lens` | `material_lens_resource` |
| `reference` | `reference_node` |
| `director-console-3d` | `director_console_panorama_input` |
| `shot-breakdown` | `shot_breakdown_resource` |
| `group` · `video_group` · `director-studio` · `screenplay` · `custom` | **空集 → 永远不能当连线来源** |

### 4.2 三条要点（【REA静态】）

1. **"生成"与"资源"在连线上不区分**：`text_generate`＝`text_resource` · `image_generate`＝`image_edit`＝`image_resource` · `video_generate`＝`video_edit`＝`video_resource` · `audio_generate`＝`audio_resource`（**逐位相同**）⟹ **别拿"生成/资源"解释连线差异**。
2. **五行全 0（只能被连、不能连出去）**：`script_generate` · `script_resource` · `video_story_resource` · `director_console_panorama_input` · `shot_breakdown_resource`。**⚠ 这是 action 层的"不能连出去"，不等于"脚本节点不能连线"**。
3. **两条特例在查表前短路**：目标是 `reference` ⟹ **仅 `reference → reference` 合法**；来源是 `reference` ⟹ **一律合法**。

### 4.3 ⚠ 两处未解冲突（**不许写成定论**）

| 冲突 | 一边 | 另一边 | 本轮口径 |
|---|---|---|---|
| **`video_generate → video_generate`** | 客户端矩阵 ＝ **`true`** | 本库 `libtv-canvas-anatomy.md` §2.2（2026-10-03 修正）说 **"`video_generate` 之间不可直接引用"** | **冲突未解**；**写的时候带限定语**，别写"平台拓扑禁止" |
| **`video_clip_resource` 这一列** | 客户端矩阵把 `text_generate` / `image_generate` → `video_clip_resource` 标 **`true`** | 本库 `key-decisions.md` **C54** 的**服务端报错原文**把这两格记为**被拒** | **"客户端允许" ≠ "平台允许"**；该列按**存疑**处理 |

**判据**：**静态读表是客户端行为；C54 那种服务端报错原文权重更高。** 两者冲突时**不许二选一写死**，
**要定案得做一次受控连线并看服务端回执（写操作，需显式批准）**。

## 五、边界

1. 全部为客户端**只读静态**证据；**未建任何节点**；
2. **"六种"这一侧只有本库既有记录**（`create_node` 的 enum），**本轮未复核 MCP schema**；
3. **连线合法性已静态读出（见 §四）**，但**只是客户端表**；**能否被引用 / 计费如何，仍未逐个验证**；
4. **显示名是 i18n 文案，会随版本变**；**稳定标识是取值**。
