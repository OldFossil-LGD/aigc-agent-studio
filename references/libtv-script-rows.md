# LibTV 脚本 / 故事板：13 列行模型与 CSV 导出

**这一册只回答一件事：`script`（＝`storyboard`）节点的「行」有哪些字段、平台回来的镜头对象怎么映射、CSV 怎么导出。**
来源标签：**【REA静态】**（客户端载荷 / 网页 bundle 静态读出，**不是服务端规则**）。
出处：`outputs/libtv_rea_20261014/49_故事板行模型与CSV导出.md`。
**写方向（行 → 服务端镜头对象、两个 scene 与各自上限）另见 `libtv-script-submit.md`。**
> ⚠ 与 `libtv-node-field-notes.md` 的分工：那册讲"**节点 data 里有什么**"，**本册讲"行的列模型与导出契约"**。

## 一、★ 13 列权威表（`SCRIPT_FIELD_META`）

| # | 行内键（camel） | 线上键（snake） | 默认表头 |
|---|---|---|---|
| 1 | `shotNumber` | `shot_number` | 镜号 |
| 2 | `durationSeconds` | `duration_seconds` | 时长 |
| 3 | `plotDescription` | `plot_description` | 画面描述 |
| 4 | `videoReference` | `video_reference` | 视频参考图 |
| 5 | `shotSize` | `shot_size` | 景别 |
| 6 | `characterAction` | `character_action` | 角色动作 |
| 7 | `emotion` | `emotion` | 表情 |
| 8 | `sceneTags` | `scene_tags` | 场景 |
| 9 | `lightingAndAtmosphere` | `lighting_and_atmosphere` | 光影氛围 |
| 10 | `audioEffects` | `audio_effects` | 音效 |
| 11 | `dialogue` | `dialogue` | 对白 |
| 12 | `imageGenerationPrompt` | `image_generation_prompt` | 分镜提示词 |
| 13 | `videoMotionPrompt` | `video_motion_prompt` | 视频提示词 |

**★ 表头可被平台覆盖**：平台若回 `columns[].field = <apiKey>`，就**用它给的 `label`**，否则用上表。
所以**要按表头认列，先看平台有没有回 `columns`**——别把上表当唯一真相。
（表里另有 `numeric: true/false` 标记，但**客户端从不读它**，不要依赖。）

## 二、服务端镜头对象 → 行（回落链）

| 行键 | 取值顺序 | 兜底 |
|---|---|---|
| 镜号 | `shot_number`（数字或数字串） | **不合法则「序号 + 1」** |
| 时长 | `duration_seconds` → `duration` | **`5`** |
| 画面描述 | `plot_description` → `visual_description` → `content` | `""` |
| 角色动作 | `character_action` → **`camera_movement`** | `""` |
| 光影氛围 | `lighting_and_atmosphere` → `lighting` | `""` |
| 音效 | `audio_effects` → `audio_music` | `""` |
| 对白 | `dialogue` → `audio_voice` | `""` |
| 视频参考 | `video_reference{}`，或扁平 `start_time` / `end_time` | 都没有 → **该键为 `undefined`** |
| 角色 | `characters[]` 的 `character_name` / `character_description` / `character_image_url` | 字符串 `"null"` / `"undefined"` **归一为空串** |

**★★ 一条会坑人的归并**：**`camera_movement` 会被写进「角色动作」列**，所以**"运镜"与"角色动作"在 CLI 侧分不开**；要分开只能走网页侧（见 §四）。

## 三、CSV 导出规则

- **列序**：`画面描述`及其之前的列 → **角色三连（`角色N` / `角色描述N` / `角色图N`）** → 其余列；
  **N 的最大值＝全表 `characters` 长度的最大值**；
- **引号规则**：值含 `,` / `"` / 换行 **才**加引号，并把 `"` 翻倍；
- **取值**：字符串原样 · 数字转字符串 · 其余空串；**视频参考取 `referenceFrameImage`**；
- **写出**：**带 BOM（`\uFEFF`）的 UTF-8**；文件名＝节点标签（无则 `脚本`）＋ `.csv`。

## 四、★★ CLI 是有损子集（网页侧富模型）

网页侧**同源解析器**在这些字段上比 CLI 多：`characterAssetId` · `cinematics{shotSize,cameraMovement,lighting}` ·
`plotDescriptionEntityRefs` / `finalVideoPromptEntityRefs` / `finalImagePromptEntityRefs` ·
`sceneAssetIds` / `propAssetIds` / `propTags` · `dialogueLines` / `voiceover` / `bgm` / `sfx` ·
`imageToVideoMotionPrompt`，并且还返回 `assets` 与 `styleDescription`。

**四条会改变做法的差异**：

1. **提示词**：网页优先 **`final_image_prompt` / `final_video_prompt`**，CLI 只读 `image_generation_prompt` / `video_motion_prompt`；
2. **时长**：网页 **`Math.round` 取整**，**CLI 保留原值**，两边导出可能差零点几秒；
3. **角色**：网页带 **`characterAssetId`**（并能按角色名回填资产 id），**CLI 没有**，CLI 的 CSV 回灌会丢资产绑定；
4. **运镜**：网页放进 `cinematics.cameraMovement`，**CLI 并进「角色动作」**。

**判据：把 CLI 导出的 CSV 当成"平台完整行模型"一定会丢字段**；**回灌平台是否接受未验证**。

## 五、★★ 行字段的词表（平台自己给的下拉表 · 【REA静态】）

**景别（`shotSize`）12 项**：`大远景` · `远景` · `全景` · `中远景` · `中景` · `中近景` · `近景` · `特写` · `大特写` · `头肩景` · `半身景` · `全身景`。
**默认 `中景`**。写词表以外的值**不会报错**，而是**按相似度就近吸附**（完全相同 1.0 / 输入含候选 0.9 / 候选含输入 0.85 / 否则＝字符集交集 ÷ 并集），
**最高分低于 0.6 就静默变成 `中景`** ⟹ **想清楚要哪个景别，就照这 12 个词逐字写**。

**运镜（`cameraMovement`）6 项**：`推镜` · `拉镜` · `摇镜` · `跟镜` · `俯拍` · `仰拍`。
**光影（`lighting`）7 项**：`冷色调` · `暖色调` · `逆光` · `硬光` · `柔光` · `霓虹光` · `自然光`。

⚠ 三组**声明在同一张表里**，但那处的消费点**只取了运镜那一组**——**别据此说"三组都被强制校验"**。
**CLI 载荷里这 12 个景别词 0 命中** ⟹ **词表只在网页侧**。

## 六、★ 资产实体与 EntityRefs（【REA静态】）

**资产实体**（角色 / 场景 / 道具共用一个解析器）除 §二 的行字段外，还有这些回落：
`linkedNodeId` ← `linkedNodeId` ?? `linked_node_id` ?? `node_id` · **`confidence` 收数字**，也收字符串档
**`high`→0.9 · `medium`→0.6 · `low`→0.3** · `isPrimary` ← `isPrimary` ?? `is_primary` ·
**`status` 恒为 `ready`** · `compliance.state` 白名单 **`pass` / `reject` / `pending` / `expired`**（其余 `unknown`）·
`sourceImageRef` ← `sourceImageRef` ?? `source_image_ref`（**非空才写**）。**名字为空的条目整条丢弃。**

**EntityRefs：按「资产 id」绑文本，与 `{{Image N}}` 按「序号」是两条路**：

| 线上键 | 行键 |
|---|---|
| `plot_description_entity_refs` | `plotDescriptionEntityRefs` |
| `final_video_prompt_entity_refs` | `finalVideoPromptEntityRefs` |
| `final_image_prompt_entity_refs` | `finalImagePromptEntityRefs` |

元素形如 **`{text, assetId}`**；**`text` 与 `asset_id` 都必须是非空字符串**，缺一即跳过。

⚠ **上一版此处写的是"编码方式 unknown"——已更正**（第五十五轮补采的 chunk 里读到了实现）：

```text
打包： p(refs) = N("prompt-bundle-v1", { text, entityRefs })
       entityRefs 先排序： assetId.localeCompare → 再 text.localeCompare
```

| kind | 文本字段 | refs 字段 | 状态字段 |
|---|---|---|---|
| `image` | `imageGenerationPrompt` | `finalImagePromptEntityRefs` | `imagePromptState` |
| `video` | `videoMotionPrompt` | `finalVideoPromptEntityRefs` | `videoPromptState` |

- **写回行**：`T(row, kind, {text, entityRefs})` → `{...row, [文本字段]: text, [refs 字段]: entityRefs?.length ? [...] : undefined}`
  ⟹ **refs 为空数组时该字段被写成 `undefined`**（不是空数组）；
- **同步版 `K`** 额外把 `[状态字段]` 置为 **`"synced"`**；**`B` 只写文本与 refs、不动状态**；
- **读出行**：`j(row, kind)` → `{ text: row[文本字段] ?? "", entityRefs: row[refs 字段] }`；
- **资产全量展开**：`A(row) ＝ [...characters, ...scenes, ...props]`；
- **refId 校验**：同文件里有一条 **UUID v4 形状**的正则（`^[0-9a-f]{8}-…-4…-[89ab]…$`，大小写不敏感）。

**→ 判据**：**refs 是"排序后打包"的**——同样的内容换个书写顺序会得到同一个 bundle，**所以不要用 refs 的先后表达优先级**（排序键是 `assetId`，不是书写顺序）。

## 七、★ 客户端对镜头文本的本地检查（【REA静态】 · 2026-10-16 补）

同一个 chunk 里有一组**按正则跑的本地启发式**——说明**平台自己也在"读"这些文本字段**：

| 检查组 | 词表（逐字） |
|---|---|
| 运镜（名词式） | `推镜`｜`拉镜`｜`摇镜`｜`移镜`｜`跟镜`｜`升镜`｜`降镜`｜`环绕` |
| 运镜（动词式） | `推进`｜`拉远`｜`推近`｜`拉开`｜`横移`｜`跟随`｜`上摇`｜`下摇`｜`缩放` |
| **动作** | `起手`｜`挥`｜`收势`｜`蓄势`｜`扑`｜`冲`｜`退`｜`跳`｜`踢`｜`抓`｜`抬`｜`放下`｜`转身`｜`起身`｜`坐下` |
| 运镜（英文） | `push`｜`pull`｜`pan`｜`tilt`｜`track`｜`dolly`｜`zoom` |
| **转场 / 衔接（中文）** | `继而`｜`随后`｜`与此同时`｜`同时`｜`紧接着`｜`紧接`｜`然后`｜`接下来`｜`紧随其后`｜`稍后`｜`片刻后` |
| **转场 / 衔接（英文）** | `cut to`｜`followed by`｜`then`｜`meanwhile`｜`simultaneously`｜`afterwards` |

- **计数函数**：`O(text, patterns)` ＝ 各正则命中数相加；
- **元素词表 57 项**（身体部位 / 光影 / 陈设 / 镜头参数 / 材质）：
  `脸 面 眼 眉 嘴 唇 鼻 手 指 臂 腿 脚 身体 肩 腰 背 光 影 色 色温 对比 高光 阴影 光斑 光线 色调
  桌 椅 杯 瓶 门 窗 墙 地面 天花板 灯 街道 房间 广场 篮球场 咖啡馆 走廊
  镜头 焦距 光圈 景深 构图 机位 视角 质感 纹理 材质 反光 玻璃 金属 木 石`；
- **重复检测**：`U(text, list)` 的正则要求**同一个词连着出现两次以上**（中间可夹空白或 `@` / `＠`）
  ⟹ 它找的是**"被重复强调的词"**，**不是"出现过就报"**；
- **停用词表**：`的 了 在 是 和 与 及 或 一 一个 一种 这 那 中` ＋ `a an the of in on at with and or is are to for`。

**→ 判据**：**运镜 / 动作 / 转场这三类词是"被点名检查的"**——**该写的没写，文本就进不了"有运镜、有动作、有衔接"那一档**。

**附：清单键与顺序字段（同 chunk · 逐字）**

```text
V2 族    = ["videoListV2","audioListV2","nodeKeyOrderedList","attachmentList"]
基础族   = ["textList","imageList","videoList","audioList","mixedList"]
顺序字段 = { image:"imageListOrder", video:"videoListOrder", audio:"audioListOrder" }
```

**→ 判据**：**音频也有自己的 `audioListOrder`**（不只图 / 视频）；
**`attachmentList` / `nodeKeyOrderedList` 属另一族**，与 `{{Image N}}` 那套**不是一张表**。

## 八、边界

1. 全部为客户端静态证据；**未导出 CSV、未跑故事板任务**；
2. 服务端**是否接受本表的 camel / snake 键回写**未验证；
3. 任务返回体外层是 `{ texts:[内层 JSON 字符串], columns }`（**内层要再解析一次**），
   该形态是**客户端预期**，真实响应**未捕获**。
4. §六 的词表是**客户端下拉表**证据：**服务端是否强制、写错会不会被纠正，未验证**；
5. **EntityRefs 的文本编解码 unknown**（实现模块未捕获）；
6. 本轮新增内容的出处：`outputs/libtv_rea_20261014/52_脚本行词表与资产实体模型.md`。
7. **节号变更（2026-10-16 · 第五十五轮）**：本册一度出现 **`§五` 缺号**（补写 §六/§七 时把原 §五 边界改成了 §八）。
   本轮**归位**为：**词表 → §五**、**资产实体与 EntityRefs → §六**、**客户端文本检查 → §七**、**边界 → §八**。
   **旧记录里写"§六–§八"的地方，指的是现在的 §五–§七。**
8. **EntityRefs 的编码已补上**（见 §六 的"已更正"段）：此前记的 "unknown" **不再成立**；
   **但"模块 `421201` 本身"仍未找到**——两件事不要混。
