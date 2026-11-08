# LibTV 模型目录（全量实测快照）

> **从 `libtv-model-params.md` 分卷而来**（2026-10-02，原册触顶 300 行）。
> **职责分工**：原册管「**字段契约**（每个模型收哪些参数、枚举、上限）；
> **本册管「**有哪些模型**（展示名 ↔ modelKey · 选型口径 · 目录核对）。
> **为什么分开**：目录是**会过期的**（模型上下架、新模型上线），参数契约是**稳定的**；
> 混在一起会让「旧目录数字」被当成「字段契约」引用（已经真的发生过）。
> **读完回**：`libtv-model-params.md`（字段契约）· `libtv-capability-matrix.md`（能力矩阵）。
> **口径**：**模型目录以现场 `search_models` 全量取为准**；**本册的数字是当时快照，不是永久事实**。

---

## 三·补 · ★★ 图片与音频模型目录（**2026-09-22 全量实测**）+ 视频清单核对

> **为什么补这一节**：§三 只覆盖**视频**模型；**图片 26 个与音频 8 个在库内此前基本零记录**（全库 grep：图片 **15/25** 零命中、音频 **7/8** 零命中）。
> **取数方式**：`search_models(action="search", nodeType=…)` **全量**（**不带 `query`**），2026-09-22 01:35 实测。**★ 标签不可检索**：`query="上新"` 返回空（`matchKind: "none"`）→ **只能全量拉下来自己过滤**。

### 三·补 1 · 图片模型（26 个 · 2026-10-02 实测修正）
> **⚠️ 计数以实测为准**：2026-10-02 全量 `search_models` 实测 **图片 26 / 音频 8 / 视频 45**（库内原记 25 / 8 / 43）。本册目录条目仍是 2026-09-22 快照，**新增型号未逐个补录**；用前按 `libtv-platform-watch.md` 的「三源快照 diff」取实时清单，**不要把本册的 26 读成「已列全 26」**（E185）。
| 展示名 | modelKey | 一句话 | 标记 |
|---|---|---|---|
| **Lib Image 2.5 Pro** | `lib-image-2.5-s` | 精准生成与编辑，复杂指令稳定还原（**我方主力**，见 §一/§二） | |
| Lib Image 2.5 Fast | `lib-image-2.5-f` | 极速高质量生成 | |
| General image Pro | `nebula-ultra` | 最强图片模型，媲美 Nano pro | studio |
| Lib Image | `lib-image-2` | 最新最强，媲美 image2 | studio |
| General image V2 | `nebula-2-flash` | 支持联网搜索、文字准确、速度更快 | |
| Seedream 5.0 Pro | `doubao-seedream-5-0-pro` | 精准交互式编辑，原生多语言排版 | |
| **Qwen image 3.0** | `qwen-image-3` | 擅长复杂版面与精准文字 | **`["上新"]`** · **非 VIP** |
| Seedream 4.6 | `jimeng-4.6` | 提升人像一致性、平面设计 | |
| Seedream 5.0 Lite | `seedream-5` | 支持联网搜索、中式风格 | |
| Seedream 4.5 | `seedream-4.5` | 多角色一致性、中式风格 | |
| **Midjourney V8.2** | `mj-v8.2` | 细节更丰富、美学水准大幅提升 | **`["风格上新"]`** · **★ 需白名单** |
| Midjourney V8.1 | `mj-v8.1` | 生图更连贯、细节更丰富 | `["风格上新"]` · studio |
| Midjourney V7 | `mj-v7` | 最佳美学、电影质感 | `["风格上新"]` · studio |
| Midjourney Niji 7 | `mj-niji7` | 动漫高审美、风格多样 | `["风格上新"]` |
| Z Image Turbo | `z-image` | 极速生成，适合真实感 | |
| General image | `nebula-core` | 语义理解强 | |
| QwenImage | `qwen` | 文字排版能力强 | |
| QwenImage Edit | `qwen-edit` | Qwen 系编辑模型，精细可控 | |
| Shock Image 2 | `orbit-2-image` | 电影质感强、光影细腻 | |
| Seedream 4.0 | `seedream-4` | 支持中文文字与海报设计 | |
| 基础算法F.2 Pro | `flux-2-pro` | 新一代生成与编辑 | |
| 基础算法F.2 Flex | `flux-2-flex` | 新一代生成与编辑 | |
| 基础算法F.1 | `flux-1` | 经典生图，风格多样 | |
| 图片编辑模型 | `image-editor` | 局部精准改图 | |
| 图片编辑Pro | `image-editor-pro` | 局部精准改图 | |

**★ 两条与"写实片资产锚点"直接相关的实测**：
- **`lib-image-2.5-s`（我方主力）**：`resolution` **1K / 2K / 4K**（默认 2K）· `ratio` **13 档含 `21:9` 与 `9:21`** · `background` 可 **`transparent`**（**抠图 / 合成有用**）· `quality` **5 档**（low / medium / high / xhigh / max，默认 medium）· `count` 枚举 **1 / 2 / 4** · `modeType: image2image` 输入 **0–14** · 带 `magic` / `mention` / `cameraControl` / `enableSlash`。
- **`qwen-image-3`（带 `["上新"]`）**：`resolution` **只有 1K / 2K**（默认 2K）· `ratio` 8 档（默认 16:9）· `quality` 仅 **`std` / `pro`** · `modeType: image2image` 输入 **1–3**。
  **★ 判据：参考图上限只有 3，远低于 `lib-image-2.5-s` 的 14 → "上新"不等于"更强"，按任务选。**（我方锚点 + 多参考的工作流，**主力仍应是 `lib-image-2.5-s`**。）

### 三·补 2 · 音频模型（8 个）
| 展示名 | modelKey | 用途（工具自述） |
|---|---|---|
| Seed Audio 1.0 | `seed-audio-1.0` | 多模态音频生成：人声 / 音效 / 音乐一体化 |
| MiniMax voice design | `minimax-voice-design` | 用文字描述设计全新音色 |
| Minimax-speech-2.8-hd | `speech-2.8-hd` | TTS，多元情绪渲染 |
| Minimax-speech-2.8-turbo | `speech-2.8-turbo` | TTS，快速生成自然音频 |
| Eleven V3 | `vocal-v3` | TTS，高质量可定制 |
| ElevenMusic V3 | `vocal-music` | 智能音乐生成 |
| Mureka V9 | `mureka-9` | 智能音乐生成，多元风格与自然人声 |
| Mureka V8 | `mureka-8` | 智能音乐生成，多元风格与自然人声 |

**★★ 两侧目录有代差（必须记）**：平台侧 Agent 自陈 **"Mureka 我侧当前为 V8，未见 V9"**，而我方 `search_models` **同时返回 V8 与 V9**。
→ **口径：模型目录以我方 `search_models` 为准**（它那层是编排层视图，会滞后）。**这是 §四"两边字段体系不同"同一条纪律的延伸。**
**★ 音频与 `enableSound` 的关系**：`enableSound` 只管**随片声**（对白 / 环境 / 音效由视频模型一并产出），**不会去调这些 TTS / 音乐模型**；精修短片的标准做法是**解耦**——见 `libtv-official-qa-part7.md` **UV2.9** 与 `libtv-platform-watch.md` §八·2。

### 三·补 3 · 视频清单核对（§三 的 47 vs 实测 43）
- **§三 写"47 个 · 2026-09-21"，2026-09-22 全量实测为 43 个** → **差 4 个**。
- **可能原因**：长尾档位（`wanx2.7-video` / `wanxiang-*` / `vidaq*` 一类）在两次快照间有增减；**也可能上次数错**。
- **★ 处置**：**本册以 `modelKey` 为唯一身份**（展示名会重名、会改），**数量只作量级参考**；**要精确数量请现场 `search_models` 全量取**。
- **★ 核对结论**：§三 表里的**关键档位全部仍在架**（Wan 3.0 / 3.0 Prime · Seedance 2.5 / 2.0 / 2.0 Fast / 2.0 Mini · Kling O3 / 3.0 · Minimax H3 / H3 Max · Shot V2 / V2 Pro · Vidu Q2 / Q3 Pro · Veo3(Libveo 3) · Happy Horse 1.1 / 1.0）—— **无一条消失**，**差异只在长尾，不影响选型结论**。
- **（2026-09-28 补）**：当日实跑 `search_models`（video）实测为 **44 个**；§三 标题「47 个 · 09-21」为历史日期锚点、不作改写，数量仍以现场 `search_models` 全量取为准。

---

## 三·补 4 · ★★ **CLI 侧对照**（2026-10-16 · **登出态**实测 · 与本节快照的差）

> **为什么单列**：本册目录来自 **MCP 侧 `search_models`**；**CLI 侧 `libtv model search -t <type>` 返回的是另一套集合**（同 `libtv-capability-matrix.md`「空 query 不是全量目录」那条纪律）。
> **取数**：`libtv model search -t {image,audio,video}` **登出态**（`account list` 报 `未登录`），**退出码 0**，**实测 20 / 6 / 34**。

| 类型 | 本册快照 | **CLI 实测（10-16）** | **本册有、CLI 无** | **CLI 有、本册无** |
|---|---|---|---|---|
| 图片 | 25–26 | **20** | `flux-1` · `flux-2-flex` · `flux-2-pro` · `image-editor` · `image-editor-pro` · `nebula-core` · `orbit-2-image`（**7**） | `flux-3-image` · `nebula-2.1`（**2**） |
| 音频 | 8 | **6** | `minimax-voice-design` · `mureka-9`（**2**） | —— |
| 视频 | 44–47 | **34** | `motion-3-prime`（Veo3）· `scene-2` / `scene-2-ultra`（Shot V2）· `seedance-1.5-pro`（**4**，**均属三·补 3 记的"关键档位"**） | 19 条长尾 / 新档（含 `star-video2.5-draft` · `vidu-q4` · `kling-v2-6` · `wanxiang-plus` · `pixverse-v5` / `pixverse-v5.5` 等） |

**★ 口径（别读过头）**：**本表只说明"两套集合不同"，不等于"那 7 / 2 / 4 条已下架"**——
**登出态可能少给一部分模型**（**未验证**）；**要判"在不在架"，得登录后用 MCP `search_models` 全量取**（**需用户批准**）。
**★ 一处旁证**：**CLI 侧音频 6 条里没有 `mureka-9`**，**与平台侧 Agent 自陈的"我侧当前为 V8，未见 V9"一致**（见三·补 2）。
**★ 与本册旧结论的关系**：**三·补 3 记的"关键档位全部仍在架"是 09-28 的结论**；**10-16 的 CLI 侧已看不到其中 4 条**——
**这条差异本册只记录、不下结论。**

---

## 附 · 随册附带的**模型 schema 快照**（2026-10-16）

**`schemas/libtv-models/`** 里存着 **77 个模型的完整 schema**（**`<modelKey>.json` + `_manifest.json`**），
**由只读命令 `libtv model <modelKey>` 在登出态抓取**（**图片 20 · 视频 34 · 音频 6 · 脚本 10 · 故事板 10 · 文本 4**，
**外加 13 条"不在 `model search` 列表里但按 key 取得到"的**）。

**用途**：**`libtv_orchestrate.py --model-schemas-dir schemas/libtv-models` 直接可用**——
**逐节点 G7 不用再"由 agent 先取好 schema 再传"**（**实测：`star-video2.5` 的节点判出 `state: pass`、0 findings**）。
**★ 它会过期**：**模型上下架 / 字段改动都要重抓**；**重抓命令见 `schemas/libtv-models/_manifest.json` 的 `refresh` 字段**。
**★ 只读抓的，不含任何凭据**；**schema 里没有 `disable` 之类的服务端运行时值**（**那些仍要登录后才看得到**）。

---

## 附 2 · `mediaConstraints` 的**真实路径与分布**（2026-10-16 · 77 份 schema 全扫）

**★ 路径是 `schema.properties.mediaConstraints`**——**不是顶层 `schema.mediaConstraints`**。
**按顶层查会得到"0 份"，按 `properties` 查才是"2 份"**（**本轮实测踩到**）。

| 模型 | 模式 | 约束 |
|---|---|---|
| `kling-v3-motion-control` | `mixed2video` | `video.duration` **3–30s**（`block`） |
| `kling-v3-omni` | `videoEdit2video` | `video.duration` **3–10s**（`block`）· `video.formats` **mp4/mov**（`block`）· `video.height` **720–2160**（**`warn`，不拦**） |

**★ 判据**：**"这个字段在不在"要先说清"在哪个层级"**——**按错层级查，结论会从"2 份"变成"0 份"。**
**★ 门禁四层已按 77 份 schema 全扫**（**区间 441 · 收紧 98 · 素材 24 · 规则 77 = 640 个探针，0 处不符**，
见报告 `129`/`131`）——**且已固化成常驻脚本 `scripts/libtv_schema_sweep.py`**（**四层都扫**；**`--self-test` 6 条**；
**schema 集一刷新就重跑它**；**退出码 `0` 零不符 · `1` 有探针不符 · `3` 没扫到**）；
**它已挂进 `lib_doctor` ⑤ 的脚本自检清单（十三 → 十四）**。
**★ 规则层那条是"不变量"不是"边界"**：**ctx 全真（prompt/image/video/audio/media 都有）时，每条 `require` 都满足
⟹ 规则层必 `pass`**——**这一层在"什么都有"时不该拦任何模型。**

**★★ 2026-10-16 同日追加 · 上面那条"未验证"已用第二条只读通道解掉**：
**`libtv model <modelKey>`（直接按 key 取 schema）登出态同样 `exit=0`**——
**把"本册有、CLI 无"的 13 条逐个喂进去，13/13 全部返回完整 schema**：
`motion-3-prime` · `scene-2` · `scene-2-ultra` · `seedance-1.5-pro`（视频 4）·
`flux-1` · `flux-2-flex` · `flux-2-pro` · `image-editor` · `image-editor-pro` · `nebula-core` · `orbit-2-image`（图片 7）·
`minimax-voice-design` · `mureka-9`（音频 2）。
**⟹ 结论修正：那几条不是"下架"**——**`model search -t <type>` 的列表只是一个子集，`model <key>` 才是按 key 的直取**。
**要判某条"在不在"，`model <key>` 比 `model search` 可靠**（**"不在搜索列表里"不等于"取不到"**）。
**★ 顺带**：**本册与 `libtv-model-params.md` 里几处逐字段契约也在同一轮核过、全部对上**（见报告 `124`）。

---

## 三·补 5 · ★★★ **服务端自己的两张目录**（2026-10-16 · 只读远端配置取到）

> **为什么单列**：本册上面几节来自**我方 `search_models` / `model search`**；**这一节是"平台服务端自己下发的目录"**——
> 取自 **`/api/www/landing-activities/getById?id=182`（`supportModels`）与 `?id=188`（`slashImage`）**，
> **只读 GET、无需点火**（**通道与取数链见 `libtv-cli-env-binding.md`**）。
> **★ 口径**：**服务端目录 = 平台认为"这个模态有哪些模型"**；**它与 `model search` 的差**见三·补 4。
> **★ 会过期**：**2026-10-16 这一抓的快照**；**平台改配置即变**。

### 一、`supportModels`（id 182）：**9 个模态键 / 96 个模型**

| 模态键 | 条数 | `modelKey`（逐条） |
|---|---|---|
| `text` | **4** | `aurora-3-prime` · `cvlm-5.5` · `aurora-3-lite` · `qwen-3-vl-flash` |
| `image` | **20** | `lib-image-2.5-s` · `lib-image-2.5-f` · `lib-image-2` · `nebula-ultra` · `nebula-2.1` · `nebula-2-flash` · `doubao-seedream-5-0-pro` · `flux-3-image` · `qwen-image-3` · `mj-v8.2` · `mj-v8.1` · `mj-v7` · `mj-niji7` · `jimeng-4.6` · `seedream-5` · `seedream-4.5` · `z-image` · `qwen` · `qwen-edit` · `seedream-4` |
| `video` | **34** | `star-video2.5` · `star-video2.5-draft` · `star-video2` · `wanx3.0` · `wanx3.0-prime` · `vidu-q4` · `MiniMax-Hailuo-H3` · `MiniMax-Hailuo-H3-Max` · `star-video2-fast` · `star-video2-mini` · `happy-horse-1.1` · `happy-horse-1` · `kling-v3-omni` · `kling-v3-turbo` · `kling-video-o3` · `wanx2.7-video` · `kling-video-o1` · `wanxiang-v2-6` · `MiniMax-Hailuo-2.3-Fast` · `MiniMax-Hailuo-2.3` · `kling-v2-6` · `kling-v3-motion-control` · `midjourney-video` · `MiniMax-Hailuo-o2` · `viduq2` · `viduq2-pro` · `viduq2-turbo` · `viduq3-pro` · `omnihuman-1.5` · `kling-v2-5-turbo-pro` · `wanxiang-plus` · `wanxiang-preview` · `pixverse-v5.5` · `pixverse-v5` |
| `audio` | **6** | `seed-audio-1.0` · `speech-2.8-hd` · `speech-2.8-turbo` · `vocal-v3` · `vocal-music` · `mureka-8` |
| `storyboardVideo` | **19** | `star-video2` · `star-video2-fast` · `kling-video-o1` · `kling-video-o3` · `kling-v3-omni` · `wanxiang-v2-6` · `midjourney-video` · `MiniMax-Hailuo-2.3-Fast` · `MiniMax-Hailuo-2.3` · `MiniMax-Hailuo-o2` · `viduq2-pro` · `viduq2-turbo` · `viduq3-pro` · `kling-2.1` · `kling-v2-5-turbo-pro` · `wanxiang-plus` · `wanxiang-preview` · `pixverse-v5.5` · `pixverse-v5` |
| `scriptImage` | **7** | `nebula-ultra` · `lib-image-2` · `nebula-2-flash` · `seedream-5` · `seedream-4.5` · `seedream-4` · `z-image` |
| `scriptText` | **3** | `aurora-3-prime` · `cvlm-5.5` · `aurora-3-lite` |
| `enhanceVideo` | **2** | `topaz-video-upscaler` · `volcano-video-upscaler` |
| `enhanceImage` | **1** | `topaz-image-upscaler` |

**★ 三条判据**：

1. **`disable` 全表 0 条**（**96 个条目里没有一条带非空 `disable`**）——**"模型被禁"这件事，这一抓里不存在**；
   要拿一条真样本，**得等平台真的禁用某个模型**（**客户端代码里 0 命中，只能采服务端响应**）。
2. **`image 20` / `video 34` / `audio 6` / `text 4` 与 CLI `model search` 的计数逐个相等**——
   **⟹ "服务端 `supportModels` 与 CLI 目录同源"这条成立**。
3. **本表里有 `vidu-q4` 与 `midjourney-video`**（**video 键**）、**`vocal-v3` / `vocal-music`**（**audio 键**）——
   **这三条在早先的摘要里没列到**；**"条数对得上"不等于"名单落全了"。**

### 二、`slashImage`（id 188）：**17 条 scene 的"预设实际参数"与"支持模型"**

> **★ 这一张与 `libtv-model-params.md` 的 slash 表分工**：**那边管"每个 scene 要什么输入"**（`inputRequirement`）；
> **这张管"它实际用哪套参数、支持哪些模型"。**

| scene | 输入要求 | `match`（provider / model / quality / ratio） | `supportModels` |
|---|---|---|---|
| `storyboard_canvas_skill_new` | prompt | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` |
| `storyboard_canvas_skill` | prompt | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` |
| `portrait_texture_adjustment` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `multi_camera_grid_9` | image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `multi_camera_grid_9_4k` | image | nebula / `nebula-ultra` / **4K** / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `story_beat_grid_4` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `character_face_turnaround_3view` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `product_turnaround_3view` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `character_setting_sheet` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `scene_setting_sheet` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `product_setting_sheet` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `continuous_storyboard_grid_25` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `cinematic_lighting_correction` | image | nebula / `nebula-ultra` / 2K / **（无 ratio）** | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `character_turnaround_3view` | prompt_or_image | nebula / `nebula-ultra` / 2K / 16:9 | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `frame_prediction_plus_3s` | image | nebula / `nebula-ultra` / 2K / **（无 ratio）** | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `frame_prediction_minus_5s` | image | nebula / `nebula-ultra` / 2K / **（无 ratio）** | `lib-image-2` · `nebula-ultra` · `nebula-2-flash` |
| `720_panoramic` | prompt_or_image | nebula / `nebula-ultra` / **4K** / **21:9** | `lib-image-2` · `nebula-2-flash` |

**★ 四条判据**：

1. **`supportModels` 是"这个预设能选哪些模型"的白名单**——**绝大多数是 `lib-image-2` / `nebula-ultra` / `nebula-2-flash` 三件套**；
   **两条故事板 scene 只支持 `lib-image-2`**；**`720_panoramic` 只支持 `lib-image-2` / `nebula-2-flash`（不含 `nebula-ultra`）。**
2. **`match` 是"这个预设实际用的参数"**——**多数 `2K / 16:9`**；**`multi_camera_grid_9_4k` 与 `720_panoramic` 是 `4K`**；
   **三条没有 `ratio`**（`cinematic_lighting_correction` / `frame_prediction_plus_3s` / `frame_prediction_minus_5s`）。
3. **★★ `match` 与 `model` 可以不一致**：**`720_panoramic` 的 `match.ratio` 是 `21:9`，而它的 `model.ratio.enum` 只有 `2:1`**
   （**`modelOverrides["nebula-2-flash"].ratio` 才是 `21:9`**）——**"预设实际用 21:9" ≠ "这个模型的枚举里只有 2:1"。**
4. **`720_panoramic` 不在 CLI `image shortcut list` 的 16 条里**（**CLI 硬编码过滤掉它**）——**"CLI 能列的" ≠ "目录里有的"。**

---

## 三·补 6 · ★★ **素材面板自己的两组模型**（`materialPanelConfig` · 2026-10-16 只读远端配置）

> **来源**：`/api/www/landing-activities/getById?id=243`，**只读 GET、无需点火**；原始明细见 `outputs/libtv_rea_20261014/remote_configs_309_314_243_311_207_262_20261016.json`。
> **边界**：这是**素材面板 UI 的可用模型与上限**，不是“所有模型都能进素材面板”；**数量与上限会随平台配置变化**。

### 一、`styleModelList`：11 条风格模型

| modelKey | 展示名 | `baseType` | `styleType` | `maxCount` |
|---|---|---:|---|---:|
| `lib-image-2` | Lib Image | 27 | `template` | 1 |
| `mj-v7` | Style Image V7 | 42 | `template` | 1 |
| `mj-niji7` | Style Image Niji 7 | 43 | `template` | 1 |
| `mj-v8.1` | Style Image V8.1 | 79 | `template` | 1 |
| `nebula-ultra` | General image Pro | 40 | `template` | 1 |
| `nebula-2-flash` | General image V2 | 70 | `template` | 1 |
| `qwen` | Qwen Image | 37 | `lora` | 3 |
| `qwen-edit` | Qwen Image Edit | 39 | `lora` | 3 |
| `z-image` | Z Image | 53 | `lora` | 3 |
| `seedream-4.5` | Seedream 4.5 | 55 | `template` | 1 |
| `seedream-5` | Seedream 5.0 | 68 | `template` | 1 |

### 二、`lensModelList`：3 条镜头模型

| modelKey | 展示名 | `baseType` | `styleType` | `maxCount` |
|---|---|---:|---|---:|
| `star-video2` | Seedance 2.0 | 69 | `lens` | 6 |
| `kling-video-o3` | Kling 3.0 | 66 | `lens` | 6 |
| `kling-v3-omni` | Kling O3 | 67 | `lens` | 6 |

**★ 三条判据**：
1. **`styleType` 决定上限**：`template` 全是 **1**，`lora` 是 **3**，`lens` 是 **6**——**“能选几个”先看类型，不要只看模型名**。
2. **风格面板 11 条 ≠ 本册图片目录**：这里只列 UI 允许的风格模型，**缺项不等于模型下架**。
3. **素材面板是 UI 白名单**：进入生成前的参数与互斥关系仍以 `libtv-model-params.md` 和现场 schema 为准。
