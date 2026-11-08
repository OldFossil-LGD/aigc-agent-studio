# LibTV 模型参数字典（**MCP 侧实测确证**）

> **为什么单列一册**：平台 Agent 给的字段名与 MCP 侧**对不上**；它自己指了一条路——**"字段级真相以 MCP 的 tools/list inputSchema 与 `validate_generation_plan` 为准，优先于一切口头对照"**。
> **本册就是走那条路得到的结果**（2026-09-21 实测）。
> **★ 权威性**：本册是**接口 schema 实测**，**高于**`libtv-official-qa*.md` 里"平台 Agent 口头说的字段名"。**时效限定（2026-09-28 补）**：同一时间截面下，字段级真相以 `tools/list` inputSchema / `validate_generation_plan` 为准；**跨时间截面时，新 schema 覆盖旧实测**——本册结论按 **2026-09-21～09-23 截面**读，超期请按 §二 三步法重验。
> **读完回哪**：`libtv-canvas-nodes.md`（接口全景）· `run-sheet.md` 站 6.5（投喂与生成）。
>
> **★★ 2026-10-14 REA 补充（优先执行）**：`libtv.exe` 内嵌的 `supportModels` 只是**离线回退目录**，已与当前账号在线目录产生差异（本轮内嵌 56 项；在线只读查询为 video 34 / image 20 / script 10 / audio 6，且该计数仍不等于全量证明）。登录态 UI 实测视频模型列表同样为 **34 项（其中 4 项禁用）**；打开模型入口会触发 `POST /api/third_asset/list` 与 `POST /api/task/generation/power/calculator`。视频面板默认显示 `2.0 / 文生视频 / 16:9 · 720P · 5s · 1个`；实测选择 `Seedance 2.5` 后模型标签变为 `2.5`，默认模式与设置标签暂不变。**生成前一律先跑 `libtv model search --type <video|image|script|audio>`，再用 `libtv model <modelName>` 拉实时 schema；旧快照与 UI 列表都只作索引，最终参数以实时 schema 为准。**完整证据见 `libtv-platform-watch-rea-index.md`（整册）。
>
> **★★ 2026-10-15 REA 补充（客户端硬闸 · 静态字面 · 可直接当前置校验）**：`该模型不支持文生视频，请上传参考图片`（按模型禁 `text2video`）·`该模型需要参考图片才能生成视频` ·`全能参考包含视频时视频时长最长10s` ·`1080P 分辨率下不支持 10s 时长` ·`输入视频仅支持MP4和MOV格式` ·`动作控制仅支持单人角色，参考单人视频中的动作` ·`生成循环视频指以传入的图片作为视频的首尾帧`（＝首尾循环模式）·`视频分辨率超过 2K，暂不支持超分/去字幕`。
> **★ 生成器参数枚举（登录态实测 · 零点火）**：比例 `Auto / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 / 21:9` · 清晰度 `480P / 720P / 1080P / 4K` · 视频时长＝滑杆＋数字框 · 生成音频 `开启 / 关闭` · 生成数量 `1个 / 2个 / 4个`。**这是生成器通用枚举，不等于逐模型 schema。**
> **★ 模型专属提示词语法（逐字）**：`Hailuo 2.3 支持在提示词中使用运镜指令，如 [Zoom in]、[Pan left,Pedestal up] 等，点击按钮快速插入` → **方括号英文指令是 Hailuo 2.3 的提示词级运镜通道**（与我方"运镜写进提示词"同源）；**其他模型是否有同类语法＝unknown**。
> **★★ 2026-10-16 REA 补充（模型 schema 的读法 · 只读 CLI 实测 · **全量 34 个视频模型**）**：**"这个模型要连几张"的唯一答案是 `properties.modeType.items` 里的 `[min,max]`**（**`[0,0]` ＝ 占位但不可用**，与"键不存在"判定等价、schema 不同）；**区间通过之后还有第二道收紧 `properties.modeType.mixed2videoConfig`**（`videoMax` / `imageMax` / `imageMaxWithVideo` / `audioMax`），**第三道门是 `properties.mediaConstraints`**（按 `modeType`→素材→约束，**每条自带 `action`（只见到 `block`）与整句 `message`**）。**`text2video` 不出现在 `items` 里**（**34/34**）——**它是"隐含模式"，可用性只看 `config.excludeModeTypes` 有没有排除它**（**实测 3/34 有值，逐字都是 `["text2video"]`**）；**`longVideo2video` 34/34 都没有**（**`supportLongVideo: true` 只是必要条件**）⟹ **"客户端目录有 10 个 `modeType`" ≠ "某模型提供 10 个"**（**实测每模型 1–7 个**）。
> **★★★ 2026-10-16 更正（**上一轮 4 模型样本的结论被全量证伪**）**：**`videoEdit2video` 34 个里有 6 个**（两个 Seedance 2.5 ＋ **`kling-v3-omni`** ＋ **`kling-video-o1`** ＋ **`happy-horse-1.1`** ＋ **`happy-horse-1`**）——**它不是 Seedance 专属**；**`imageMaxWithVideo` 34 个里有 9 个**（**也不是 Seedance 专属**）；**`videoEdit2videoConfig` 在 `kling-v3-omni` / `happy-horse-1.1` 上都出现**。**`config.settings` 有两种形态**（按 `modeType` 分键的对象 / 全局数组）——**实测 10/34 是数组，只按对象读会在这些模型上静默读空**；**`videoEdit2video` 的 settings 用 `_auto` 变体**（比例与时长自动，别去填 `ratio`/`duration`）。**⚠ `firstFrame` 在 34 个视频模型 schema 里 0 次出现**——**它可能只是 `frames2video` 上限 < 2 时的显示名**，**待 image 类模型复核**。**全量 34 模型对照见 `outputs/libtv_rea_20261014/69_视频模型全量34个schema与三处更正.md`**（四模型版见同目录 `68_模型schema实测modeType区间与settings形态.md`）。
> **★★★ 2026-10-16 第三批 REA 补充（image / script / audio 三类已取 · `firstFrame` 结案 · **全 63 份 schema**）**：**`firstFrame` 在 63 份 schema 里 0 命中** ⟹ **它不是任何模型的 `modeType` 取值**——**它是 `frames2video` 上限 < 2 时的显示名**（**下一行那条"14 档"要按"客户端字面词表"读，不能按"逐模型可取的值"读**）。**image 类 20/20 只有一个 `modeType`＝`image2image`**（**区间各异：`[0,14]` / `[0,10]` / `[0,7]` / `[0,6]` / `[0,4]` / `[0,2]` / `[0,1]`，只有 `qwen-image-3` `[1,3]` 与 `qwen-edit` `[1,2]` 下限是 1**）⟹ **"0 张参考"就是文生图**；**image 类的 `config.settings` 18/20 是数组形态**（**只有 `nebula-2.1` / `nebula-2-flash` 是对象，且 `text2image` 只在这两个里、只在 `settings` 不在 `items`**）。**script 类 10 条里只有 3 条 `modality` 是 `text`**（`aurora-3-prime` / `aurora-3-lite` / `cvlm-5.5`，`properties` 只有 `prompt`＋`modeType`，取值是 **`image2text` / `video2text`**，**`cvlm-5.5` 的 `video2text` 是 `[0,0]`**）；**另 7 条实际是 `image` 模型** ⟹ **`search --type <T>` 的 `matches` ≠ "T 类模型"，要判类别得看 `libtv model <key>` 返回的 `modality`**。**audio 类只有 1/6 有 `modeType`**（`seed-audio-1.0`：`text2audio [0,0]` · `image2audio [1,1]` · `audio2audio [1,3]`；**其余 5 个根本没有这个字段**）。**去重后共 63 个 key**（`video` 34 / `image` 20 / `audio` 6 / `text` 3）。**三类全景见 `outputs/libtv_rea_20261014/70_三类模型schema与firstFrame结案.md`。**
> **★★★ 模式名与模式闸（2026-10-15 · 静态字面 · **2026-10-16 就地更正**）**：客户端 `modeType*` **i18n 标签键共 14 条**（逐字）——`text2video` 文生视频 · `text2image` 文生图 · `image2image` 图生图 · `singleImage2video` 图生视频 · `image2video` 图片参考 · `mixed2video` 全能参考 · `frames2video` 首尾帧 · `video2video` 视频参考 · `videoExtend2video` 视频续写 · `videoEdit2video` 视频编辑 · `longVideo2video` 超长视频 · `audio2video` 音频参考 · **`firstFrame` 首帧** · **`audio2videoDrive` 音频驱动**。**⚠ 两条更正（2026-10-16）**：**`firstFrame` 与 `audio2videoDrive` 都不是 `modeType` 取值**——前者是 **`frames2video` 上限 < 2 时的显示名**（**63 份 schema 0 命中**），后者**只是 i18n 键 `modeTypeAudio2videoDrive` 的中段**（**带引号的裸串全语料 0 命中**）⟹ **这张表是"i18n 标签键"口径，不能当"取值"口径用**。**★ 另**：**`audio2video` 在两个模块里显示名不同**（模块 `469850` →「**音频参考**」· 模块 `61637` →「**音频驱动**」）。**四套 `modeType` 口径与差集见 `outputs/libtv_rea_20261014/71_rules校验器与四套modeType口径.md`。**
> **★★ 2026-10-16 REA 补充（模型 schema 的三层前置门 · 模块 `61637` + `469850`）**：**63/63 个模型都带 `rules`**；单条形状是 **`{ require, mode = "all", forModeTypes, whenHas, message, messageI18nKey }`**——**`require` 取值 `prompt`/`image`/`video`/`audio`/`media`**，**`mode: "any"` 是"至少满足一个"，`"all"`（或省略）是"全满足"**；**`forModeTypes` 非空且当前 `modeType` 不在其中 → 该条不适用（直接通过）**，**`whenHas` 非空且不是每项都满足 → 同样直接通过**；**⚠ 只有"当前 `modeType` 已知"时才跳过**——**`modeType` 未知时不跳，照判**。**实测分布**：**`any` 48 条 · `all` 4 条 · 省略 35 条**；**`require` 计数 `prompt` 82 · `media` 47 · `image` 5 · `video` 2 · `audio` 1**；**22 条带 `forModeTypes`（几乎都是 `["text2video"]`）** · **1 条带 `whenHas`** · **4 条带显式 `message`**。**★ 4 条显式文案里有一条本库早就有**：**`midjourney-video` 的 `该模型需要参考图片才能生成视频`** ⟹ **那条"客户端硬闸"的出处就是模型 schema 的 `rules[].message`，不是全局规则**；另三条未记过（`请同时添加参考图片和视频` · `请同时添加参考图片和音频` · `全能参考不可仅输入音频，须至少包含 1 个参考视频或图片`）。**★★ 本库已有可直接跑的判据脚本 `scripts/libtv_model_rules_gate.py`**（**照抄模块 `61637` 与 `469850` 的判定**；`--self-test` **26/26**；用法 `--schema <libtv model 输出> --mode-type <…> [--images N --videos N --audios N] [--has-prompt|--has-image|--has-video|--has-audio|--has-media]`；**退出码 `0` 可生成 · `1` 被拦 · `3` 无一层可判（≠ 通过）**）。**★★★ 三层已落成机器判据**：**① `modeType.items` 区间（含 `config.excludeModeTypes`；`text2video` 无素材才算可用）· ② `mixed2videoConfig` / `videoEdit2videoConfig` 收紧（`videoMax` / `imageMax` / `imageMaxWithVideo` / `audioMax`）· ③ `rules`**——**①② 只在给了 `--images/--videos/--audios` 时跑**，**不给就记 `skipped`（≠ 通过）**；**④ `mediaConstraints` 已落**（**逐条素材判，不聚合**；**七个键**：`formats` / `duration` / `height` / `width` / `longSide` / `shortSide` / `size`；**`action` 有 `block` 与 `warn` 两种——`warn` 不拦但要走 `warnMessages` 显示**；**喂 `--video-materials <json>` 才跑**，**本脚本不探测媒体、不发请求**）。**★★★ 三条新事实（2026-10-16 补）**：**① `ctx` 的构造方找到了**（模块 `529639`）——**`hasPrompt` 有三条来路**（**归一化后提示词非空 · `textList` 里有一条 `content` 是非空数组 · `params.scene === "camera_focus"`**）· **`hasImage` 有两条来路**（**`imageList` 非空 · `camera_focus` 且 `params.originImage` 存在**）· **`hasVideo`/`hasAudio` 就是对应列表非空** · **`hasMedia = hasImage || hasVideo || hasAudio`（不含提示词）**⟹ **"连了几张图"不是"边数"，是 `data.imageList.length > 0`**；**② 节点没带 `rules` 时用的是模块 `821992` 的默认表**（**6 个键：`video`/`image`/`text`/`audio`/`enhanceVideo`/`enhanceImage`**，**其中 `video`/`image` 两条与 schema 里那两条逐字一致**）；**③ ⚠ 更正：带了 `rules` 之后过的是模块 `503357` 的"清洗"、不是"按模型过滤"**——**它收 `(rules, model)` 但 `model` 被内层循环变量遮蔽、一次都没读**；**清洗会改三样：`mode` 非 `"any"` 一律变 `"all"` · `require`/`whenHas` 里的非法 kind 被删（`require` 空了整条丢弃） · 非字符串 `message` 被丢掉**。**本脚本已按这三条改：先清洗再判，并支持 `--node-kind` 走默认表**。**★★★ 提示词归一化也读出来了（2026-10-16 · 模块 `838978`）**：**`hasPrompt` 用的是"归一化后非空"**，而**归一化按 `modeType` 分流**——**`frames2video` / `videoEdit2video` 走 `X`**（**删 `{{CameraPreset N}}` + `{{Panorama720}}` + `{{SlashPreset:…}}`，只 trim，不压空白**）；**其余模式走 `b(F(…))`**（**删 `{{SlashPreset:…}}` + `{{Panorama720}}`，把 `[ \t]+` 压成单空格**）。**★ 关键：插桩一律不删**——`{{Image N}}` / `{{Portrait N}}` / `{{Video N}}` / `{{Audio N}}` / `{{Mixed N}}` / `{{Element N}}` / `{{magic:…:N}}` **都保留** ⟹ **只写 `{{Image 1}}` 也算"有提示词"**；**⚠ 而 `{{CameraPreset N}}` 只在 `X` 那两个模式下被删**（**其余模式保留**）。**本脚本已加 `--prompt` / `--prompt-file` 按同一套归一化算 `hasPrompt`**。**★★★ 素材"怎么数"也读出来了（2026-10-16 · `collectIncomingNodeDataForTarget`）**：**只算 `edge.target === 目标` 的入边**；**排除 `edge.data.portraitVirtual` / `assetVirtual` 两类虚拟边**；**按 source 节点的 `data.type` 分桶**（`text`→textList · `image`→imageList · `video`→videoList · `audio`→audioList）；**`reference` 跳过（不进任何列表）· `director-studio` 不进素材列表**（**进单独的 `directorStudio` 字段，且只留 id 最大的那个**）；**普通 `group` 不在 switch 里**（**要先用 `expandGroupSourceNodes` 递归展开，深度上限 8**）；**`characterAsset` 的分组由 `collectCharacterReferenceItems` 单独收成 imageList 条目**；**目标自己的 `data.refImages`（★ 与 `params` 平级，不在 `params` 里）也补进 imageList**（id 形如 `<target>:ref-<i>`）。**⟹ 计数不是"数 `refs` 数组"**——**`refs` 里混着的 reference / group / director-studio 都不算素材**。**★★ 素材属性（`durationSec` / `width` / `height`）优先从 `node.resourceMeta.items[0]` 拿**（**缺了客户端才去探测**）。**本脚本已加 `--materials-from <json>` 自己数 counts**（**`--self-test` 63/63**）。**★★ 两条补全与一处更正（2026-10-16 第二轮）**：**① `expandGroupSourceNodes` 已实现**——**`group`/`video_group`/`video-story` 且**非 `characterAsset`**的入边会**递归展开**（**深度上限 8**），**遇到 `data.groupRefExcludedNodeIds` 里的节点在 `depth>0` 时"只标记不展开"**；**② `collectCharacterReferenceItems` 已实现，但 ⚠ 它读的是 `edge.data.characterRef`（逐边字段），不是分组节点**——`characterAsset` 是上游（`persistCharacterReference`）把它**写进边**的；**③ `textList[].content` 是"字符串数组"不是字符串**（`normalizeTextContentField` 把字符串包成 `[str]`、空串给 `[]`、数组只留字符串）。**输出里的 `notImplemented` 现在是空数组**（**两条都补上了**）。**★★★ 素材计数的尾段（2026-10-16 第三轮）**：**① ⚠ 更正 `refImages` 的路径**——**在 `node.data.refImages`（与 `params` 平级），不是 `data.params.refImages`**（旁证：孪生版逐字 · `1o5crmb53tqh1.js` 的 `refImages: e.data.refImages` · `05vjmhmsmxfo8.js` 6 处）；**② `focusRegion.nodeId` 是“排除项”**——`data.params.focusRegion.nodeId` 命中就把该 `nodeId` **从 `imageList` 里剔掉**（**只过滤 imageList**，**且在 refImages 之后**）；**③ `focusRegion` 的写入方＝`node.data.params.focusRegion`**（形如 `{nodeId, relX, relY, width, height, imag…}`，`detach` 即 `delete`）。**门脚本已按①②改，`--self-test` 60 → 63 → 70。****★★★ 素材计数的写入方与图类模式表（2026-10-16 第四轮）**：**① `node.data.refImages` 的写入方＝CLI 的“分镜批量生成”构造器**（`if (charImageUrls.length > 0) imageData.refImages = charImageUrls;`，**`imageData` 就是节点的 `data`** ⇙ **与 `params` 平级**；**没有角色图的节点根本没这个键**）；**② `camera_focus` / `originImage` / `focusRegion` 是“一次一起写”进 `node.data.params`**（网页聚焦处理器；**`originImage` ＝ 取景框渲图后按 `focus-region` 上传得到的 URL**）；**③ ⚠ 图类模式表更正**——门原来**没有 `image2image` 的 listKey** ⇙ **图类模型恒按 0 张判**（`qwen-image-3 [1,3]` 会被误拦）；**判据＝CLI 载荷的 `imageGeneratorReferenceCountViolationMessage` 读 `collectIncomingNodeDataCli(...).imageList.length`** ⇙ **`image2image → imageList`**；**`text2image` 客户端只推导、从不校验 ⇙ 门记 `not_verified`**；**④ camera_focus 的提交侧覆盖已接进 G7**（`imageList → [originImage]` ＋ `modeType → image2image`）；**⑤ 恢复载荷 `libtv-pkg-runtime.js` 是非压缩 esbuild bundle（保留函数名）——`buildEvalContextCli` / `isStructuralUserEdgeCli` 都能按名字读**；**⚠ 虚拟边过滤：网页用真值，CLI 用严格 `=== true`**。**★★★ 逐节点分流与 `ctx` 自推导（2026-10-16 第五轮）**：**① `pipeline` 新增 `--model-schemas-dir <dir>`**——**对每个有 `params.model` 的节点各跑一次门**（图由编排器的 `spec_gate_graph()` 从 spec 的 `refs` 现摊、带该节点自己的 `modeType` 与 prompt）；**找不到 schema 记 `no_schema` + WARN（≠ 通过）**；结果进 `G7_per_node`，汇总行印「逐节点 N：x 过 · y 未过 · z 未验到」；**⚠ spec 表达不了虚拟边与 `characterRef`** ⇙ **投影不是画布**；**② 给了图之后 `ctx` 也能自推**（照 `buildEvalContextCli`：`hasImage/Video/Audio` 来自列表非空 · `hasPrompt` 来自 `textList[].content` 或 `camera_focus` · **`hasMedia` 不含提示词**），**与 `--has-*` 取或** ⇙ **只给图也能判 `rules`**；**③ 门新增 `--materials-stdin`**（逐节点分流不落临时文件）。**门 `--self-test` 70 → 74。****★★★ 三条“未追来源”结案（2026-10-16 第六轮）**：**① `slashPreset.inputRequirement` ＝ 客户端 slash 目录里的字面量**（`2y_q_e93utebg.js`，**内嵌 16 条 scene**（**其中 8 条带 `inputRequirement`**）——**★ 线上远端目录 `188` 有 17 条**，**内嵌 16 条 ⊂ 线上 17 条、只缺 `portrait_texture_adjustment`**，**取值只有 `prompt` / `image` / `prompt_or_image`**）；**② `enhance*` ＝ “生成器类型”**——模块 `403216` 的校验表 **`p = {image, video, text, audio, audioEdit, enhanceVideo, enhanceImage}`**（**`enhanceVideo` 复用 video 的 schema、`enhanceImage` 复用 image 的**）⇙ **默认规则表里那两个 `enhance*` 键就是给这类节点用的**；**③ `characterReferences` 家族是模块 `25185` 的四个导出**（`persist` / `read` / `rebuild` / `remove`，**都先看 `nodeData.characterAsset`**）——**⚠ 方向更正：`persistCharacterReference` 读边的 `data.characterRef`、写“源节点自己的 `characterReferences[edgeId]`”**（**`rebuild…` 从空映射起把边折回去** ⇙ **边是源、节点映射是派生缓存**；**报告 79 §六 说反了**）；**④ 角色资产组建立时 `characterAsset` 与 `characterReferences:{}` 一起写在 `data` 上**（**与 `refImages` 同级**）。**★★★ 引用载荷与边的写入方（2026-10-16 第七轮）**：**① `edge.data.characterRef` 的写入方＝画布的 `onConnect`**——**建边时 `data: pC(源节点)`**，**`pC(e) = e.data.characterAsset ? 模块397289.J(e.data.characterAsset) : undefined`** ⇙ **只有源是角色资产组才写**；**② 引用载荷的两个构造器（模块 `397289`，`u` ＝ `structuredClone`）**：**`J(asset, stateId)` → `{characterRef: {roleId, characterUuid?, roleName, versionId, version, stateId, stateName, mainReferenceImageUrl, voice, capturedAtMs}}`**（**带包装**）；**`W(asset)` → 角色快照**（`{roleId, characterUuid?, sourceCharacterUuid?, roleName, versionId, version, defaultStateId, states, coverUrl, source, capturedAtMs, latestKnownVersionId}`，**不带包装**）；**③ 连接校验器把“角色资产组”归一成图片**（`GROUP && characterAsset ? IMAGE : type`）⇙ **`skippedTypes` ≠ “没贡献”**。**★★★ `enhance*` 的运行时取值（2026-10-16 第八轮）**：**① 取值集合只有两个**——`pS` 先看 **`generatorType === ENHANCE`**，再 **`type === VIDEO ? "enhanceVideo" : "enhanceImage"`**，**然后索引 `global.support[kind]`**；**② ⚠ 节点当前 `params.model` 不在支持表里时，客户端会把它自动改成表里第一个** ⇙ **“节点上写的模型” ≠ “实际提交的模型”**；**③ 落到实处的节点**：**高清图像**（`canvas:hdImageNodeName`）· **高清视频**（`canvas:videoHdNodeName`）· **图转高清**（`canvas:imageToHqNodeName`）。**★★★ `global.support` 的形状与键集（2026-10-16 第九轮）**：**① `support[kind]` ＝ 对象数组，条目至少带 `modelKey` 与 `modelName`**（`pS` 读 `[0].modelKey`；显示名解析读 `modelKey` 取 `modelName`）；**② 键集＝9 个模态**（`image/video/text/audio/enhanceVideo/enhanceImage/scriptImage/scriptText/storyboardVideo`），**与内嵌回退目录的模态集一致（C007）**；**③ 节点→键那条链**：`G`（节点类型→kind，**`SCRIPT`/`SCRIPT_V2`→`text`**）→ `H`（kind→kind，**`compose`/`subtitleErase` → `video`**）→ **剧本节点特判成 `scriptText`**；**查不到回落成调用方的 `modelKey` 并带 `listLoaded:false`**；**④ `resolveSupportModelDisplayName(support, modelKey, preferredKind)`**：偏好 kind 打头（只认 `image/video/audio/text`），其余按 9 键固定序补上，**逐键找 `modelKey` 相等则返回 `modelName`**。**★★★ support 条目的 `disable` 与模型解析器（2026-10-16 第十轮）**：**① `disable` 四种形态**——缺省/`false`/空值＝可用 · **`true`＝禁用无原因** · **非空串＝禁用、原因＝该串** · **对象＝按 locale 取原因、回落 `en`**；**归一化恒返回 `{disabled, reason}`** ⇙ **模型下拉的“禁用”来自这个字段，不是 `modeType` 那套门**；**② 模型解析器＝模块 `255534` 的 `O(list, preferredKey, locale, predicate)`**——**没 list → 返回 `preferredKey ?? ""`；空 list → `""`**；**过滤器＝`disable` 不挡 + predicate 通过**；**preferred 可用就用它，否则顺位到第一个可用的 `modelKey`**；同模块另导出 `Q`（某 key 是否禁用）/`A`（有没有 disable 值）/`E`（归一化）；**③ 画布全局表不止 `support`**：还有 **`defaultModel`（kind→默认模型，`enhance*` 先剥前缀）** 与 **`getModel(kind, key)`**；**④ 图像类 `modeType` 推导**：`有图 ? "image2image" : "text2image"`（**与 CLI 的 `computeImageModeTypeForCli` 逐字同构**）；**⑤ 两处补全**：计费返回**还有 `originalPrice`**（本地能算就不调服务端）· **`disableBenefitTags` 在未带权益标签时注入 `params`**。**★★★ `refImages` 的两个落点（2026-10-16 第十一轮）**：**① 节点上：`node.data.refImages`**——**网页端也有写入方**，就是**分镜批量生成**那一支（**`s` 就是节点的 `data`**：`r.length > 0 && (s.refImages = r.map(e => e.url))`，**与 CLI 的 `if (charImageUrls.length > 0) imageData.refImages = charImageUrls` 同守卫同字段**）；**② 请求上：`request.params.refImages`**——**普通生成与重试两处都拼过**（`Array.isArray(r.refImages) && (r.refImages = u)`，**“已经存在才改”**），**同处还写 `referenceImages` 与 `originImage`（取第一张解析出的图，`scene === "erase"` 时不写）**。**⇙ 写“`X` 在不在 `params` 里”之前，先说清“是哪个对象的 `params`”。****★★★ 已接进编排器**：`libtv_orchestrate.py pipeline` 新增 **第七道闸 `G7`（模型前置规则）**——**`--model-schema <path> [--mode-type <…>] [--has-*]`**；**不给 `--model-schema` 记 `未跑`（WARN，≠ 通过）**，**给了且被拦记 FAIL 并把平台原话逐字带进 findings**；**⚠ 编排器不发网络请求（红线）——schema 必须由 agent 先用只读命令 `libtv model <modelKey>` 取好再传进去**；**G7 现在能拿到 counts**（**`--model-materials-from <graph.json>` 透传给门当 `--materials-from`，门自己按 `collectIncomingNodeDataForTarget` 数**）。**★ 2026-10-16 第九十三轮：G7 收成单一实现 `g7_per_node()`，`compile` 也接上了**——**`compile --model-schemas-dir <dir>` 与 `pipeline` 共用同一个函数**（**一个定义、两个调用点**，L2）；**顺带修了 `compile` 一个真 bug**：`plan["budget"]["band"]` 用了**只在 `pipeline` 里赋值的 `budget_lo` / `budget_hi`**⇙ **`compile` 一跑到那行就 `NameError`**（**实测**）；现改成 `= total`，并把 `band_state` 说明改准。**★★★ 权益标签守卫的确切谓词（2026-10-16 第十二轮）**：**`w.u(request)` ≡ `request.taskType === "agent_task" && request.params.agent_name === "libtv_audio_edit_agent"`**（两个常量顺别名解出：模块 `508240` 的 `J` ＝ `"agent_task"` · 模块 `297998` 的 `u` ＝ `"libtv_audio_edit_agent"`）⇙ **`disableBenefitTags` 只对“歌词”那条流豁免**；**长视频那条虽然也是 `agent_task`，但 `agent_name` 是 `libtv_agent_generator`，仍然注入**——**“用了 `agent_task`” ≠ “跳过权益标签”**。**顺带**：**网页版歌词请求把 `audioEditOperation:"lyrics"` 换成 `agent_name` + `prompt=JSON.stringify({operation:"segment", source_audio_node_key})` + `taskType:"agent_task"`**（**与 `C058` 记的 CLI 形状不同**）。**★★★ `agent_task` 至少四条流 ＋ 一条可读孪生版（2026-10-16 第十三轮）**：**① 第四条流＝拉片**——`agent_name: "libtv_video_pack_agent"`，**提示词＝`拉片一下这个视频。拆解维度：<中文维度名>`**，**维度三键 `storyboard`/`cameraMoves`/`musicRef` ⇺ 叙事分镜/运镜动作/音乐参考**；**⇙ `C061` 那句“恰好三条”是样本内结论，应读作“至少三条”**；**② 模块 `297998` 有可读孪生版 `3aompfguczlp6.js`**——导出名是 `AUDIO_EDIT_TASK_TYPE` / `AUDIO_LYRICS_SPLIT_AGENT_NAME` / `buildAudioEditRequest`（具名解构参数），**第二份证据确认 `y.u` ＝ `AUDIO_LYRICS_SPLIT_AGENT_NAME` ＝ `"libtv_audio_edit_agent"`**；**③ 对豁免面无影响**：拉片这条 `agent_name` 不匹配 ⇙ **仍然注入 `disableBenefitTags`**。**★★★ `spec_gate_graph` 的边数据通道（`refEdgeData`，2026-10-16 第十四轮）**：**`pipeline` / `compile` 的逐节点分流共用 `spec_gate_graph()`**，而 **spec 的 `refs` 只能表达“有这条边”、表达不了边上的字段**，**门却要按 `portraitVirtual` / `assetVirtual` 剔虚拟边、按 `characterRef` 收角色引用**⇙ **加可选字段 `refEdgeData = {源节点 id: {边字段}}`**，**合并进 emit 的 `edge.data`**；**⚠ `refs` 本身仍是 id 字符串**（`topo_order` / `make_batches` / `check_node` 都读它）。**实跑对照**：V1 接 i1/i2 两张图，给 `refEdgeData:{i1:{portraitVirtual:true}}` → **G7 过**（虚拟边被剔，数出 1 张）；**去掉 → 未过**，平台原话 **`当前参考图片数量 2 个，需要 1 个`**。**自检 139 → 142**（新增 3 条 `spec_gate_graph·` 用例）。**⚠ 自查**：**第一版对照用字符串 replace 删字段，pattern 没匹配上、什么都没改，两组跑的是同一文件**——**退出码看不出来，只有把 graph 打出来才发现 `portraitVirtual` 还在** ⇙ **用“改文本造对照组”时，改完要验证“文本真的变了”**。**★★★ `edge.data.characterRef` 的第二条写入路径（2026-10-16 第十五轮）**：**`pC` 只在“建边”时盖章**（**`2yhb63stv1loj.js` 里 `pC(` 共 3 次 = 1 定义 + 2 调用，两个调用点形状相同**）——**另一条写路径是角色资产组控制面板**：**`R=(e,t)=>{x(e.id,{data:(0,c.J)(p,t)}),v(e.target)}`**，**`x` ＝ store 的 `updateEdge` · `c.J` ＝ 模块 `397289` 的同一个载荷构造器 · `v` ＝ `recalcIncomingForTarget`**；**面板列的是该组的“出边”**（`edges.filter(t=>t.source===组节点 id)`），**每行一个状态下拉（选项 ＝ `asset.states`，初值 ＝ `edge.data.characterRef.stateId ?? asset.defaultStateId`）＋ 一个“同步引用”刷新按钮**，**过期判据 `a.versionId !== p.versionId`** ⇙ **边上的 `characterRef` 是“连边那一刻的快照”，角色升版不会自动跟着变，这个面板就是修它的地方**。**★ 连带行为**：**`updateEdge` 是 `Object.assign(edge,{data:…})`——整块 `data` 被替换、不是字段合并**，**紧接着跑 `ic(nodes, 旧边, 新边)`**（＝ 模块 `25185` 的 `remove` ＋ `persist`）**把源节点的 `characterReferences[edgeId]` 缓存重建** ⇙ **写边与节点缓存同步，边仍是源**。**★ 有界计数**：**`updateEdge` 全语料 1 个消费者（就是这个面板，三个构建各一处）· `updateEdges` 0 · React Flow 的 `updateEdgeData` 0（只在两个库 bundle 里定义）· `setEdges` 0**。**★ 其余给边写 `data` 的地方与角色引用字段不相交**：**音频编辑边 `{audioEditResultIndex, audioEditResultTaskId}` · 剪辑输出边 `{clipOutputKind, clipSourceNodeId, clipOutputUrl}` · 复制/粘贴 `...e.data?{data:structuredClone(e.data)}:{}`（把已有的 `characterRef` 原样搬走，不是重建）**；**除两个 `pC` 点外，全语料没有 `addEdge` 盖章 `characterRef`**。**★ CLI 侧对照**：**恢复载荷里 `characterRef`/`characterAsset`/`characterReferences` 命中数全 0**，而 **`portraitVirtual` 6 · `assetVirtual` 7** ⇙ **CLI 认得虚拟边、完全表达不了角色引用**。**★★★ `support` 条目的 `disable` 归一化全表与语言回落（2026-10-16 第十六轮）**：**模块 `255534` 的 `resolveSupportModelDisable(disable, locale)` 逐字读出来了**——**`let t={disabled:!1},r={disabled:!0}`** · **`i(e)` ＝ 字符串就 `e.trim()||void 0`** · **`n(e)` ＝ `!!(!0===e||i(e))||!!(e&&"object"==typeof e&&!Array.isArray(e)&&Object.keys(e).length>0)`** · **`o(e,o)` ＝ 不 `n` 就 `t` · `!0===e` 就 `r` · 字符串非空就 `{disabled:!0,reason:trim串}` · 对象就 `let s=i(e[o])??i(e.en);return s?{disabled:!0,reason:s}:r`**。**★ 三条要点**：**① 语言没有白名单**——**`e[o]` 的 `o` 就是调用方传进来的 locale，模块里唯一写死的键只有回落用的 `en`**；**② locale 取不到不是“可用”，而是“禁用且不给原因”（`{disabled:true}` 没有 `reason` 字段，与 `true` 同形）**；**③ `{}` 空对象是“可用”**——**判禁用的条件是 `Object.keys(e).length>0`**。**★ 易错点**：**字符串先 `trim()`，`"   "` 算“可用”**。**★★★ 模块 `255534` 有可读孪生版（本库第三次）**：**`0qonvurf8nmvw.js` 导出 `isSelectedSupportModelUnavailable`/`isSupportModelDisabled`/`resolveSupportModelDisable`/`selectAvailableSupportModelKey`（保留 `"use strict"`）**，**`3y_7cwbb6i8tr.js` 导出 `Q`/`A`/`E`/`O`（无 `"use strict"`、两个内部小函数名互换）** ⇙ **`Q`=isSelected… · `A`=isSupportModelDisabled · `E`=resolveSupportModelDisable · `O`=selectAvailableSupportModelKey**；**两份函数体逐结构一致**。**★ 两个伴生判据**：**`isSelectedSupportModelUnavailable(list,key)` ＝ 模型不在 list 里就算不可用（`!r` 直接为真）**；**`selectAvailableSupportModelKey(list,preferred,locale,predicate)` ＝ 没 list 返回 `preferred??""` · 空 list 返回 `""` · 过滤器＝`disable` 不挡且 predicate 通过 · predicate 收到 `modelKey`、返回 `true` 表示排除**。**★ 样本那半仍开着**：**全语料搜字面量 `disable:{…}` 对象映射 0 命中** ⇙ **`support` 是服务端下发的运行时数据，客户端代码里没有一条真实 `disable` 值可读**。**★★★ 纯文生图支持性的判据定案（2026-10-16 第十七轮）**：**先推翻一条旧建议**——**“要判得看 `config.settings` 的键”是错的**：**`midjourney-video` 的 `settings` 键里有 `text2video`，而 `excludeModeTypes` 恰好排除 `text2video`**，**同一个 schema 两条客户端信号自相矛盾**；**而且这个信号本来就大面积缺席**（**`settings` 是“按 modeType 分键的对象”的只有 26/63，另 37 份是扁平字段名数组、根本不含 mode 信息**）⇙ **`settings` 说的是“这个模式暴露哪些可调项”，不是“这个模式存不存在”**。**★★★ 正确判据 ＝ `properties.modeType.items` 的下限**：**20 个 image 模态模型全部只有一个 item `image2image`**——**下限 `0`（允许 0 张参考）⇙ 纯文生图可行，18 个**；**下限 ≥1 ⇙ 必须带参考、纯文生图不可行，只有 `qwen-edit [1,2]` 与 `qwen-image-3 [1,3]` 两个**。**可行 18 个逐字区间**：`doubao-seedream-5-0-pro [0,10]` · `flux-3-image [0,10]` · `jimeng-4.6 [0,6]` · `lib-image-2.5-f`/`-s [0,14]` · `lib-image-2 [0,14]` · `mj-niji7 [0,4]` · `mj-v7`/`v8.1`/`v8.2 [0,6]` · `nebula-2-flash`/`2.1`/`ultra [0,7]` · `qwen [0,2]` · `seedream-4.5 [0,14]` · `seedream-4`/`5 [0,6]` · `z-image [0,1]`。**★ 两条信号的一致性（有界）**：**有 `excludeModeTypes` 的只有 3 份、全是 video**——**`vidu-q4` 一致（记录里也没有 `text2video`）· `midjourney-video` 矛盾 · `MiniMax-Hailuo-2.3-Fast` 不可比（settings 是扁平数组）** ⇙ **一致 1 / 矛盾 1 / 不可比 1，样本太小**；**image 侧两个有 `text2image` 键的（`nebula-2.1`/`nebula-2-flash`）下限都是 0，与“可行”一致**。**★ 与既有结论的关系**：**“客户端从不对 `text2image` 做 schema 门”仍成立**（**门是 `rules`，里面没有 `text2image`**）——**改的是“支不支持怎么判”，不是“门在哪”**；**门脚本对 image 类的 `not_verified` 应改成本判据**（**下限 0 ＝ 支持、下限 ≥1 ＝ 不支持**）。
> **模式的两件事必须分开：可见性由模型 schema 决定，可用性由"已连素材数量"决定**：`modeTypeNeedConnectMedia`＝「**需要连接{mediaLabel}节点（{rangeText}个）**」；配套还有 `modeTypeMediaCountMismatch`（数量不在 {rangeText}）· `modeTypeImageMaxExceeded` / `modeTypeImageMaxWithVideoExceeded`（**有视频时图片上限收紧**）· `modeTypeVideoMaxExceeded` · `modeTypeAudioMaxExceeded` · `modeTypeUnsupportedMediaCombo` · `modeTypeText2videoMediaConnected`（**连了媒体就不能退回纯文生**）· `modeTypeIgnoreConnectedMedia`（**切模式会忽略已连输入**）· `modelRequiresMediaInput` · `modelUnsupportedMediaTypes` · `modelSelectionDisabledDefault`（**模型可选项随已连参数变化**）· `modelSwitchUnavailable` · `modelLockedByStyle`（**用了风格就锁模型**）。
> **★★★ 模式判定算法（2026-10-15 · 已与实测对账 · 可实现）**：客户端只读三样——`schema.properties.modeType.items`（形如 `{modeType:[min,max]}`）· `schema.config.excludeModeTypes`（硬排除）· `schema.properties.supportLongVideo`（真值）。**可见性** ＝ 该模式在 `items` 里且 `max>0` 且不在排除表（`text2video` 例外：不在排除表就可见）；**可用性** ＝ 该模式 `listKey` 槽位的素材数落在 `[min,max]`，为 0 时理由文案就是 `modeTypeNeedConnectMedia`。**每个模式读哪个槽**：`text2video` 不读 · `singleImage2video`/`frames2video`/`image2video` → `imageList` · `video2video`/`videoEdit2video` → `videoList` · `audio2video` → `audioList` · `mixed2video`/`videoExtend2video`/`longVideo2video` → `mixedList`。
> **★ 三条反直觉行为（逐条已证）**：① **`supportLongVideo===true` 时客户端会凭空合成 `longVideo2video`**，区间 `[0, mixed2video 上限 ?? 32]`，**最小值 0 ⟹ 零素材即可选中**（实测 `超长视频 Beta` 在空节点上就是可用态），且时长被**强制覆盖为 30–300 秒**（`LONG_VIDEO_DURATION_RANGE`）；② **`audio2video` 永远被渲染列表剔除** ⟶ 视频生成器的模式下拉里**看不到「音频参考」**；③ **`frames2video` 素材 <2 张时显示名变成「首帧」**，≥2 张才是「首尾帧」。
> **★ 与实测对账**：`star-video2.5` 的 `items` 有 7 个 `max>0` 的模式 → 预测 `text2video + 7 − audio2video + longVideo(合成) = 8`，**实测正是 8 项**（文生视频/全能参考/图生视频/首尾帧/图片参考/视频编辑/视频续写/超长视频 Beta）。**★ 第二个对账点**：UI 标签 `2.0` ＝ `aliasName` 为 `2.0` 的 **`star-video2`**（Seedance 2.0 VIP），其 `items` 有 5 个 `max>0`（含 `audio2video [0,3]`）、`supportLongVideo` 未声明 → 预测 `text2video + 5 − audio2video = 5`，**实测正是 5 项**。**→ 算法在两个模型上各对上一次（5 与 8），可照抄实现。**
> **★ 模型目录三方对账（2026-10-15 · CLI 只读）**：`libtv model search -t video` 34 项 ⟺ 登录态 UI 下拉 34 项，**逐条 0 不匹配**；**UI 上的 `2.0`/`2.5` ＝ 目录里的 `aliasName`**；**模型项后面的 `30s / 1min / 2min / 3min / 8min` 徽标 ＝ `estimatedTime`**（此前的 unknown 已解决）；另可直接读到 `vip` / `studio` / `platform` / `prefix` / `labels` / **`pricingRule`**（例：Seedance 2.5 =「按秒计价，此模型上传的参考视频时长计入总时长」）。`libtv model <modelKey>` 与 2026-10-14 快照**逐字段一致，无漂移**。
> **→ 三条作业纪律**：① **模式置灰先查"素材没连"，不要先说"模型不支持"**（我曾误判过一次，已在本册更正）；② **切模式后必须回读连线**（该模式可能静默忽略已连输入）；③ **选型顺序＝先定模型、再定风格**（风格一上就锁模型）。**上限数值 `{max}`/`{rangeText}` 是运行时渲染的，本轮未读出 ⟶ 仍 unknown。**

---

## 一、★★★ 参考/一致性的落地机制（**2026-09-21 实测确证 · 回答"不会连线怎么保一致性"**）

**问题**：我不会在画布上拖线，那怎么把资产图作为"参考"喂给镜头？
**实测答案**：**我能连线——我的"连线"就是 `left` / `leftAdd` 参数（引用边）。** 而且**必须连**。

### 1.1 决定性证据（两条）
**① 直接设 `params.imageList` 会被拒**：
> `NODE_VALIDATION_FAILED: params.imageList 不可通过 --set 直接设置：**媒体列表/排序/混合列表由画布连线重算与 CLI 内部现算得出**，请用连线（如 `--left`/`--left-add`）调整`

**② 用 `left` 建边后，系统自动重算**：
- 建节点时传 **`left: ["i-79q4dnhfwf72"]`** → 返回里出现 **`plan.incomingRecalcNodeKeys: ["i-iDMJlk6mbM"]`**（＝**重算发生了**）
- `read_node` 回读该节点，`params` 里**自动出现**：
  ```
  "imageListOrder": ["i-79q4dnhfwf72"]
  "imageList": [ { "nodeId": "i-79q4dnhfwf72", "url": "" } ]
  "mixedListOrder": ["i-79q4dnhfwf72"]
  ```

**→ 三条推论**：
1. **参考素材＝"连线重算"的结果**，不能手填；**用 `left` 建边**（增量用 `leftAdd` / `leftEnsure` / `leftRemove`）；
2. **`imageListOrder` / `mixedListOrder` ＝ 参考顺序** —— **这正是平台说的"`{{}}` 顺序必须与 `reference_nodes` 一致"在 MCP 侧的落地物**；
3. **`url: ""`＝该资产节点尚未生成** → 印证平台规则"**可运行前提：引用节点必须已生效（有产物）**"。

### 1.2 ★ 完整的一致性链条（我 MCP 侧 · 六步）
| 步 | 动作 |
|---|---|
| **1** | 建资产节点（`create_node(nodeType="image")`）→ **生成它**（`run=true` / `generation_submit`）→ **让它"生效"（有产物）** |
| **2** | 建镜头节点时，**用 `left: [资产节点 key, …]` 建引用边**（多张就多个；顺序即 `imageListOrder`）；补充用 `update_node` 的 `leftAdd`/`leftEnsure`/`leftRemove` |
| **3** | **选对 `modeType`**（决定要几个输入）：<br>· 图像参考 → **`image2image`（0–14）**<br>· 视频多参考 → **`mixed2video`（1–15；图 ≤10 · 视频 ≤5 · 音频 ≤5）**<br>· 首尾帧 → **`frames2video`（1–2）**<br>· 续写 → **`videoExtend2video`（1–15）**<br>**★ 2026-09-28 限定注**：`modeType` 只存在于**模型 schema 层**，工具层 `mode` 枚举（9 档）没有它；`image2image` 的「0–14」来自 `lib-image-2.5-s` 旧快照，且实测 `text2image` 的入参区间才是 [0,14]、~~`image2image` 实为 [0,1]（`supportAttachment` 口径）~~。**（2026-10-02 平台实测 · E188）此限定注已**计数误**并废除**——`lib-image-2.5-s` 的 `get_model` schema 明写 `image2image:[0,14]`；零引用建节成功、14 引用成功、15 引用被拒（报错原文写「当前模型允许 0～14 张」）→ **下限是 0、不是 1**——**0–14 不是跨型号通用承诺**，用前按 §二 三步法现场复核 |
| **4** | **prompt 里 `{{node_key}}` 插桩**（模型属性 **`mention: true`**）——**顺序要与引用顺序一致** |
| **5** | **先 `run=false` 建好 → 审阅 → 再点火**（`run=true` / `generation_submit`）——**★ 2026-09-28 补**：`create_node(run=true)` 可**建即跑**直做（直做授权场景不必先建空节点再点火）；制作任务仍走"先建→审→跑" |
| **6** | **拉回**：每 N 镜把"上一镜尾帧"换成"资产节点引用"，重置累积漂移 |

### 1.3 ★★ 与平台口径的关系（**不是矛盾，是两层**）
| | 它那层（编排层） | **我这一层（MCP/画布层）** |
|---|---|---|
| 引用载体 | **`reference_nodes` 字段** + prompt `{{}}` 插桩 | **`left`/`leftAdd` 引用边** → **系统重算出 `imageList`** |
| 它怎么说 | "**边只是可视化，可连可不连**" | **★ 相反：媒体输入不可手填，必须靠连线** |

**→ 结论：两边都要 `{{}}` 插桩（`mention`）；但"引用"的载体不同——它用字段，我用边。**
**★ 所以我此前把"边只是可视化、可连可不连"当成通用结论写进库里，在 MCP 侧是错的，已按本节改正。**

---

## 一·补 · ★★★ 三层"引用字段"各不相同（**2026-09-21 空参探 schema 实测**）

**这是我此前反复困惑的根源：不同入口用不同的引用字段名。** 三张 schema 全部实测：

| 入口 | 引用字段名 | 其它要点 |
|---|---|---|
| **`validate_generation_plan`**（**预检计划**） | **`referenceImageNodes[]` · `referenceVideoNodes[]` · `referenceAudioNodes[]`** | 必填 `name` / `prompt` / `model` / `mode`；**`mode` 枚举 9 档**：`auto`（推荐）/ `text2video` / `singleImage2video` / `frames2video` / `image2video` / `video2video` / `videoEdit2video` / `audio2video` / `mixed2video`；**`model` 要传"完整 modelName、不要传 modelKey"**（**★ 2026-09-29 再审更正**：本行是 **2026-09-28 曾被降为"建议"、本次回复为硬约束**——降级依据取自 `get_model` 的入参宽松，属**跨工具外推错误**。`validate_generation_plan` 与 `get_model` 是**两个不同 schema**，二者不可互推：本行的硬约束只针对 `validate_generation_plan`，佐证见 `libtv-capability-matrix.md` §二 该工具的 schema 实测原文「model(**传完整 modelName，不传 modelKey**)」；而 `get_model` 的入参实测确有"完整展示名优先或 modelKey，须 trim 后全等命中"的宽松口径，见本册 §二——**那是另一个工具的事，不要把两条混为一谈**。）；`params` 里**不要自己塞** model/modeType/prompt/媒体 list（**由该工具管理**） |
| **`create_node`**（**建画布节点**） | **`left[]` / `right[]`**（建边 → 系统重算 `imageList`） | 必填 `name` / `nodeType` / `idempotencyKey`；**`nodeType` 枚举 6 档：`text` / `image` / `video` / `audio` / `script` / `video-clip`**（**★ 有 `text`——文本节点可建**）；还有 `prompt` / `params` / `data` / `group` / `x` / `y` / **`run`** / `expectedRevision` |
| **`update_node`** | **`leftAdd` / `leftRemove` / `leftEnsure`**（增量改边） | 配合 `params` / `run` 使用 |
| **`generation_submit`**（**直接提交生成**） | **`request.source_node_keys`** | 必填 `project_id` / `idempotency_key` / **`kind`: `image`\|`audio`\|`video`** / `request`；**image/audio 必须给 `request.model` + `request.params`**；**schema 里没有 node_key → 它是"提交一次新生成"，不是"点火已建节点"** |

**★ 由此确定的两条正确用法**：
1. **点火"已建好的空节点"** → **`update_node(node, run=true)`**（**不是 `generation_submit`**）；
2. **建节点必走 `left`；预检计划才用 `referenceImageNodes`**——**别把两者混用**。

---

## 二、★ 探测字段真相的三步法（**不依赖任何人**）

| 步 | 工具 | 得到什么 |
|---|---|---|
| **1** | `search_models(action="search", nodeType="video" \| "image" \| "audio")` | **真实模型清单**（`modelKey` / 展示名 / 描述 / `vip` / `pricingRule` / `estimatedTime`） |
| **2** | `get_model(model="完整展示名 或 modelKey")` | **★ 该模型的完整参数 schema**（字段名 / 取值域 / 默认值 / 输入数量约束 / prompt 上限 / rules） |
| **3** | `validate_generation_plan(...)` | **把计划丢进去校验**——报错与补全会直接指出正确字段名与取值 |

**→ 结论：以后凡"字段叫什么、能填什么"，一律走这三步；不要问、不要猜。**

---

## 二、★ Wan 3.0（`wanx3.0`）完整参数表（实测原文）

| 字段 | 取值 / 约束 | 备注 |
|---|---|---|
| `prompt.maxLength` | **3000** | **3000 是"模型层"上限**（不是平台层） |
| `ratio` | `adaptive`（默认）/ `16:9` / `4:3` / `1:1` / `3:4` / `9:16` | 资产图与镜头应统一，**别混用** |
| **`duration`** | **min 2 · max 30 · `step: 1` · 默认 5** | **★ 整数步进 → 4.5 秒填不了**（要么 4 要么 5） |
| `resolution` | **480P / 720P / 1080P**（默认 720P） | **★ 没有 4K**（与"平台 Agent 说 4k"不符） |
| **`enableSound`** | `on`（默认）/ `off` | **★ 这就是声音开关的真名**；**MCP/模型层没有 `need_bgm` 这个字段** |
| **`modeType`** | **`frames2video`：输入 1–2**（**＝首帧 + 尾帧**）<br>**`mixed2video`：输入 1–15**（**＝多参考**）<br>**`videoExtend2video`：输入 1–15**（**＝视频续写**） | **★★ 这三个模式对应平台 Agent 说的 `frames2video` / `reference_nodes` / `continue_from`** |
| **`mixed2videoConfig`** | **`videoMax: 5` · `imageMax: 10` · `audioMax: 5`** | **★★ 这就是"多参考"的硬上限：最多 10 图 + 5 视频 + 5 音频** |
| **★★★ 两个「多参考」模式的语义差（2026-10-03 平台实测 · E215）** | **`frames2video` ＝「这张图就是起始帧」（首帧驱动）**<br>**`mixed2video` ＝「这些图是混合参考」** | **上一行只写了「输入数量」（1–2 vs 1–15），没写「语义」——而语义才是选型依据。** 实测反例：把首帧图喂给 `mixed2video`，产物第一帧里主体跑到**画面另一侧**，**模型压根没把它当首帧**。判据：**语义是「从这帧开始」就用 `frames2video`；语义是「多张图一起参考」才用 `mixed2video`。选错必拍错，且换词修不好。** |
| `supportVideoContinuation` | `true` | 支持视频续写 |
| `magic` / `mention` | `true` | **`mention` 很可能就是 `{{node_key}}` 插桩的底层机制** |
| **`extendPrompt`** | 默认 **1（开）** · 提示："Wan 官方提示词扩写，**关闭后生成效果大概率会下降**" | **★★ 这就是"它会扩写我们的提示词"的机制**——要"照做不重写"就得处理这个开关 |
| `supportAttachment` | **可挂文档：docx/doc/xlsx/xls/pptx/ppt/pdf/txt/md/key/pages/numbers，单件 ≤100MB，最多 1 个** | **★ 这是"投递文本/文件"的一条正规路径**（可挂 txt/md！） |
| `template` | 特效，`maxCount: 1` | |
| `count` | `[1]` | |
| `rules` | ① `require: [prompt, media]`，`mode: any` ② **text2video 模式只要求 `prompt`** | **★ 文生视频只要 prompt**（不需要 media）；图生/首尾帧等需要 media |

**★ `config.settings` 按模式列出可调字段**：`text2video` / `frames2video` / `mixed2video` / `videoExtend2video` **四模式都暴露 `ratio / resolution / duration / enableSound`**；`advancedSettings: [extendPrompt]`。

---

## 三、视频模型清单要点（47 个 · 2026-09-21 快照　**★ 2026-10-01 标注：此数不是全量，见 `libtv-capability-matrix.md`「空 query 不是全量目录」**）

| 模型 | modelKey | 说明 | VIP |
|---|---|---|---|
| **Wan 3.0** | `wanx3.0` | 全模态参考；**2–30 秒** | **否** ✓ |
| Wan 3.0 Prime | `wanx3.0-prime` | 超快速、全模态参考、超写实高一致 | 否 ✓ |
| **Kling3.0 动作迁移** | `kling-v3-motion-control` | **需输入 1 张图片 + 1 条视频** | 是 |
| Kling O3 | `kling-v3-omni` | 视频编辑、参考一致性、音画同出、多镜头 | 是 |
| Kling 3.0 | `kling-video-o3` | 高质感、支持多镜头 | 是 |
| Seedance 2.5 / 2.0 / 2.0 Fast / 2.0 Mini | `star-video2.5` / `star-video2` / `star-video2-fast` / `star-video2-mini` | 音画同步（2.5 支持 30s、2.0 系列 15s） | 是 |
| **Seedance1.5 Pro** | `seedance-1.5-pro` | 音画同步、多机位、**最长 12 秒** | 否 |
| Shot V2 / V2 Pro | `scene-2` / `scene-2-ultra` | **直出 15s 有剧情多镜头** | 是 |
| Minimax H3 / H3 Max | `MiniMax-Hailuo-H3` / `-H3-Max` | 全模态输入；Max 支持文生/图生/**首尾帧控制** | 是 |
| Vidu Q2 / Q3 Pro | `viduq2` / `viduq3-pro` | **多图主体参考** | 是 |
| Veo3 (Libveo 3) | `motion-3-prime` | 电影级真实动态、音画同出 | 是 |
| Happy Horse 1.1 / 1.0 | `happy-horse-1.1` / `happy-horse-1` | 阿里视频模型 | 是 |

> **★ 更正注（2026-09-28 实测）**：上表 `Seedance1.5 Pro`「**最长 12 秒**」**有误**——`get_model` 实测其 `duration` 为**枚举 `[5, 10]`**，只能取 5／10 两档（3／4／12 秒均提交不了）；且 `modeType` 仅 `singleImage2video`（不支持首尾帧／续写）。

**★★ `multiClip`（多镜头开关）—— 2026-10-01 实测新增 · C49 的落点就在这里**

> **全库此前 0 次提到 `multiClip` 这个字段名**（2026-10-01 grep 实测），而它正是 C49「"一段多画面"能否让模型真的切」**在平台侧的现成杠杆**。

| 项 | `get_model("Wan 2.6")` 实测值 |
|---|---|
| 字段 | **`multiClip`**（`originalField:"multiClip"` · `component:"switch"`） |
| 显示名 | **多镜头** |
| 官方 tips | **「生成包含多个镜头角度和场景切换的视频，增强视觉叙事效果」** |
| **默认值** | **`1`（＝默认开）** |
| 位置 | `config.advancedSettings: ["multiClip"]` |
| modelKey | **`wanxiang-v2-6`**（**未出现在本册 §三 表里，也不在 E18 的多机位模型清单中**） |

**→ 判据**：想要「一条内多镜头」，**先看该模型的 `advancedSettings` 里有没有 `multiClip`，有就显式写死开/关**，不要指望提示词里的「镜1／镜2」措辞去驱动它——`key-decisions.md` **C49** 诊断的正是「靠措辞强制切换」这条路走不通。**★ 但这只是把变量摆上桌，不等于已验证**：C49 的 A/B/C 实测仍未跑（需付费），**在此之前按 L6 记「拟订」，不许当结论用**。

**★ 顺带实测到的 Wan 2.6 约束（选型时容易踩，与 Wan 3.0 差别很大）**：
- **`prompt.maxLength` ＝ `1500`**（**不是 Wan 3.0 的 3000**）→ 同一段提示词在两个模型上长度结论不同，**必须逐模型核**（这正是 `scripts/libtv_orchestrate.py` 采用**分模型契约**的原因）；
- **`duration` 是枚举 `[5, 10]`**（不是 Wan 3.0 的 2–30 滑杆）→ **3 秒／12 秒提交不了**；
- `resolution` 枚举 `[720P, 1080P]`，**默认 1080P**；`modeType.items` 仅 `frames2video` / `video2video`（**无 `text2video`**，`text2video` 仍由 `rules` 承认——**判能力要看 `rules`，别只看 `items`**）。

**★ 选型提示**：**非 VIP 可选**的有 `wanx3.0` · `wanx3.0-prime` · `seedance-1.5-pro` · `wanx2.7-video` · `wanxiang-*` 等；**VIP 模型（Seedance 2.x / Kling / Vidu / Veo3 / Shot V2）需开通**。

---

## 三·补 → **已分卷**

> 图片 / 音频模型目录（25 + 8）与「视频清单 47 vs 实测 43」核对，已迁入 **`libtv-model-catalog.md`**。
> **为什么迁：**目录会过期，参数契约不会——混住会让「旧目录数字」被当成「契约」引用。
> **节号保留空位**（不改号）——按节号引用它的地方仍然有一个可追的入口。

## 四、★★ 与"平台 Agent 口头说法"的差异表（**以本册为准**）

**★ 适用面声明（2026-09-28 补）**：本表**字段级**结论（modeType 与各上限 / enableSound / extendPrompt / 只读派生字段）在**我方 MCP 侧**有效；**工具动词不得跨面照抄**——`create_node` / `update_node` / `generation_submit` / `left`·`leftAdd` 是我方 MCP/画布侧动词，它侧（平台 Agent 编排层）的等价物是 `reference_nodes` 字段 + `{{}}` 插桩 + `create_*_node` / `run_node`（它侧工具面名单见 §5.1）。

| 项 | 平台 Agent 说 | **MCP 实测** | 结论 |
|---|---|---|---|
| 函数名 | `generate_image_v3` / `generate_video_v3` / `run_node` / `create_image_node`… | **这些名字在 MCP 侧都不存在**；MCP 侧是 `create_node` / `update_node` / `generation_submit` / `generate_video` | **两套入口不同**；它自己也说"我无法调用你列的那些 MCP 工具" |
| 声音开关 | **`need_bgm=false`** | **MCP/模型层无此字段**；只有 **`enableSound: on/off`**（**总开关**） | ★ **`need_bgm` 是它平台侧的字段，MCP 侧没有**；MCP 侧只有总开关 |
| 分辨率 | 480p/720p/1080p/**4k** | Wan 3.0 只有 **480P/720P/1080P** | 以模型 schema 为准 |
| 时长 | 秒（未说整数） | **`step: 1` → 整数** | **4.5 秒填不进去** |
| 参考机制 | `reference_nodes` | **`modeType: mixed2video`**（1–15 输入；图 ≤10 视频 ≤5 音频 ≤5） | 语义对应，**字段名不同** |
| 首帧/尾帧 | `start_frame_image_node` / `end_frame_image_node` | **`modeType: frames2video`**（输入 1–2） | 同上 |
| 续写 | `continue_from` | **`modeType: videoExtend2video`** / `supportVideoContinuation: true` | 同上 |
| 插桩 | prompt 里 `{{node_key}}` | **`mention: true`**（很可能是底层机制） | **待 `validate_generation_plan` 确证** |
| 提示词会被扩写吗 | "**只补不改**" | **`extendPrompt` 默认 1（开）**，且注明"关闭后效果大概率下降" | **★ 存在真实冲突：默认是"扩写"** |
| seed / 帧率 | 无 | schema 里确无 | ✓ 一致 |

---

## 五、★★ 它侧的真实工具清单与两条关键澄清（R11 · **经"读回协议"直接读到**）

### 5.1 它侧工具名（30 个 · 原文逐字；2026-09-28 复核实点为 30 个，原记 31）
`Skill` · `analyze_audio` · `analyze_video` · `ask_human` · `composite_video` · `create_audio_node` · `create_image_node` · `create_video_node` · `director_apply` · `edit_audio` · `edit_video_v4` · `get_node_details` · **`libtv_grounded_search`** · `list_dir_v2` · `read_file_v2` · **`recall_memory`** · `run_node` · `save_asset` · `search_asset` · `search_canvas_nodes` · **`skill_assistant`** · **`skill_file`** · `task_create_v2` · `task_list_v2` · `task_read_v2` · `task_update_v2` · `update_audio_node` · `update_image_node` · `update_video_node` · `write_file_v2`

**★ 三条新发现**：**`libtv_grounded_search`（联网接地检索）** · **`recall_memory`（它有记忆！）** · **`Skill` / `skill_assistant` / `skill_file`（它有技能体系）**。
**→ 对照**：**我 MCP 侧没有** `grounded_search` / `recall_memory` / `skill_*` / `save_asset` / `search_asset` / `director_apply` / `write_file_v2`；**我有而它没有**：`upload_ticket`/`upload_complete`（**★ 我会上传，它不会**）。

### 5.2 ★ 两条关键澄清（它原话）
- **`continue_from` 不是 `create_video_node` 的入参**——**它是 `director_apply` 的 `command` 对象内字段**（record 命令的 `continue_from`，值为上一 record 视频节点 key）。
  **普通视频续写**用 `create_video_node` 的 **`video_action_type=extend`** ＋ **把被续写视频放进 `reference_nodes`**。
- **`need_bgm=false` 是 `create_video_node`（或 `update_video_node`）的顶层字段**，与 `prompt` / `reference_nodes` / `aspect_ratio` / `duration_sec` **同级，不嵌在 prompt 或 settings 内**；**并再次强调"不要用 `sound=off` 表达无 BGM"**（那会连对白与环境音一起关）。
- **它还会顺手写一份项目文件** `Agent交付_<主题>.md`（在**"task-v2 存储根目录"**）——**该路径我读不到**，但说明它有文件根目录。
- **⚠️ 它的"字段名"说法仍需自己验**：它说 `reference_nodes`/`start_frame_image_node`/`end_frame_image_node` 就是 MCP 侧字段名；**但我 MCP 侧实测的是 `modeType: frames2video / mixed2video / videoExtend2video`** → **两边字段体系不同，以 `get_model` 的 schema 为准**。

---

