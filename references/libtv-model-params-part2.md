# LibTV 模型参数字典 · 续（工程后果 / 待验 / 派生字段 / 官方字段字典）

> **何时读**：`libtv-model-params.md` 前五节读完后。
> **读完回哪**：回 `libtv-model-params.md`。
>
## 六、★★ 两条最重的工程后果（R12 硬规则 · 完整 16 条见 `libtv-official-qa-part4.md`）

| # | 规则 | 后果 |
|---|---|---|
| **级联作废** | **某节点被 `update`/重跑/替换后，所有引用它的下游节点"现有结果全部作废"，需重生成** | **★★★ 改一个锚点 ＝ 重做全片** → **锚点必须在生成任何镜头之前定死**（这就是"资产先行"的成本级理由） |
| **重建上限 3 次** | **同一产物最多重建 3 次（v1→v2→v3）** | **★ 平台的硬止损比本库的"超 8 次改结构"更严** → **止损线要与它对齐：3 次不过就必须改结构/改锚点，不是继续抽** |

**★ 另两条关键**：① **`node_key` 前缀**：`i-`图 · `v-`视频 · `a-`音频 · `n-`（Director Console）· `r-`（revision，**不是 node_key**）· **`b-` 平台方"没见过、不背书"，但我这边确实有 `b-`＝`script-v2` 节点 → 属 MCP 侧特有前缀**；② **`tag` 只决定检索分类，不决定"能否被引用"**；但**把 `keyframe` 当实体参考时，模型可能强绑定它的构图与光影（特性，不是 bug）**。

---

## 七、待验（下一轮自动化做）

**★ 工具名确证回填（2026-09-27/28 实测）**：`validate_generation_plan` / `create_node` / `update_node` / `read_node` 在我方 MCP 侧**均真实存在**（`validate_generation_plan` 在 v3 能力契约内；`create_node` 入参确有 `left`/`right`，`update_node` 确有 `leftEnsure`/`leftAdd`/`leftRemove`/`rightEnsure`/`rightAdd`/`rightRemove` 六个）。**工具名存在 ≠ 下列三项的"结论"已验**——三项仍按"待验"读。

1. **`validate_generation_plan`**：把一份带 `modeType: mixed2video` + 参考节点 + `enableSound: off` 的计划丢进去，**看它怎么报错/补全** → 确认引用到底怎么写、`{{}}` 是否必需。
2. **`create_node(run=false)` + `read_node` 回读**：确认 `params` 是否完整持久化（＝确认"先建后跑"是否真等价）。
3. **`supportAttachment` 挂 `.md`**：试一次能否把文本作为附件传给模型（**这可能是"把内容投递给它 / 从它取内容"的一条正规通道**）。

---

## 八、★ 四个"只读派生字段"（2026-09-23 实测确认）

| 字段 | 归属 | 是否可写 | 权威来源 |
|---|---|---|---|
| `params.imageList` | 图片参考列表 | **只读** | 连线重算 |
| `params.imageListOrder` | 图片参考**位次** | **只读** | 连线重算 |
| `params.mixedList` | 混合素材列表 | **只读** | 连线重算 |
| `params.mixedListOrder` | 混合素材位次 | **只读** | 连线重算 |

- 直写 `params.imageListOrder` 报：`不可通过 --set 直接设置：媒体列表/排序/混合列表由画布连线重算与 CLI 内部现算得出，请用连线（如 --left/--left-add）调整`。
- **位次＝建节点时 `left` 数组顺序**，事后 `leftRemove`/`leftAdd` 均无法重排 → 详见 `libtv-op-manual-part3.md` **§三十·30.1**。
- **接图片参考入边前必须先 `modeType=image2image`**（`text2image` 会被拒）→ 详见 §三十·30.3。


---

## 

---

★ 两条真平台契约（2026-10-01 编排器真跑时撞出来的）
> 上面都是**读 schema** 得到的。下面两条是**真去建节点、被拒绝后**才知道的 —— schema 里没有，只有跑过才有。
| 码 | 规则 | 平台原文 |
|---|---|---|
| **C19** | **image 节点一旦有 image 类型的入边，就必须显式给 `params.modeType=image2image`**（无入边时可省略，平台会自动落 `text2image`） | `NODE_VALIDATION_FAILED: 图片生成节点须为图生图模式（params.modeType=image2image）才允许图片参考入边；当前为 text2image` |
| **C20** | **`params.settings.sample_rate` 经 MCP 传不进去 → 删掉它**（省略后平台自己落 `24000`(int)，与本库记录的活节点一致） | `params.settings.sample_rate="24000" 不在允许范围。可选: 8000, 16000, 24000, 48000` |
### ★ C20 那条报错文案是个坑（已复验）
它把 `24000` 列在「可选」里，**却又拒绝你** —— 先以为是值不对：改传字符串（被拒）→ **改传 int**（JSON 里不加引号）**照样被拒**，错误里仍是带引号的 `"24000"` 字符串
→ **真因是 MCP 传输层把数字统一转成了字符串**，而后端要 int。**这不是我能绕开的** —— 所以正解是**别传**，而不是照报错文案改数字。
**→ 记录这条的方法学（`governance-law.md` L4·补的另一个实例）**： **报错文案里列了合法值却仍拒绝 → 先怀疑自己的类型，不照字面改值**。
**别照字面读——它的字面意思可能就是错的。**
### ⚠ C19 一个好质量的实测细节
被拒绝后**平台会把整个节点回滚**（随后 `delete_node` 报 `NODE_NOT_FOUND`）—— **不留孤儿节点**。 平台保留了整体语义，这点很好：**失败不留脏数据**，重试时用同一幂等键即可（本轮实测：改内容后换新键重发即成功）。

---

## ★★★ 官方字段字典补全（**`libtv-cli/model-schema/schema.md` · 一手文档 · 2026-10-15**）

> 本册此前缺的几块，官方文档里写全了。**下面每条都是文档原文要点，不是推断。**

| 字段 / 机制 | 官方定义 | 为什么要紧 |
|---|---|---|
| **`properties.<key>.originalField`** | **写入 `params.settings` / `advancedSettings` 时使用的键名**；不写则与 `properties` 的 key 一致 | **属性名 ≠ 落库键名**——照 `properties` 的 key 写 `settings` 可能写错键 |
| **`config.settings`** | 可为 **`string[]`**（所有 modeType 共用）**或 `Record<modeType, string[]>`（按当前 `params.modeType` 切换列表）** | 视频模型常见后者 ⟹ **换模式会换一套可调字段** |
| **`config.advancedSettings`** | 同上格式，对应高级设置区 | 与本册「按白名单裁剪」的实测互相印证 |
| **`config.generateTypes`** | 创建生成任务时与 **`taskType` / `checkpointId`** 等的数值映射 | **不用于画布连线条数判断**——别拿它当入边规则 |
| **顶层 `schema.rules`** | **对象数组**，判断"当前是否允许发起生成"；求值把 `params` 与 `textList`/`imageList`/`videoList`/`audioList` 整理成布尔条件 | **本册此前零记录**；这才是"生成按钮能不能点"的正式依据 |
| **`count`** | 多为**数组**（如 `[1,2,4]`）＝可选张数/条数 | 别当标量解析 |
| **文本模态 modeType** | **`image2text`** / **`video2text`** | 本册此前只记视频/图片模态 |
| **音频模型** | **常常根本没有 `modeType.items`**——入边条数不由该结构表达，而依赖 `rules` 与画布连接规则 | 对音频节点不能用 `items` 判上限 |

### 顶层 `rules` 的求值规则（逐条）

| 规则字段 | 含义 |
|---|---|
| `require` | 需要的输入类型数组，元素 ∈ **`prompt` \| `image` \| `video` \| `audio` \| `media`**（`media` ＝图/视频/音频任一存在） |
| `mode` | **`all`**（默认，`require` 每项都要满足）\| **`any`**（至少一项满足） |
| `forModeTypes` | 非空时**仅当当前 `params.modeType` 在数组内**本条才参与；否则**本条直接视为通过** |
| `message` | 不满足时的自定义提示；省略则由客户端按 `require`+`mode` 生成 |

**三条关系与三态**：
1. **规则之间是 AND**——每条都要过；单条内部由 `mode` 决定 AND/OR。
2. **`rules` 字段不存在** → 客户端按生成器类型套**内置默认规则**（图片生成器常见默认＝「`prompt` 与 `media` 至少其一」）。
3. **`rules: []`** → **显式无约束**（不再套默认）；**非空** → **只用数组内合法项**，非法项被过滤忽略、不中断求值。

**★ 分工（照做）**：**`modeType.items[key]=[min,max]` 回答"连了几条、超没超"；顶层 `rules` 回答"这组 params+汇入数据能不能发起生成"**——两者同时存在，**先看 items 再看 rules**。
**★ 另一个坑**：`properties` 内部的 `rules`（如营销/划线价）**不是**顶层 `schema.rules`，**别混**。

**★★ 四条显式 `message` 各挂在哪个模型上（2026-10-16 · 77 份 schema 全扫）**：`全能参考不可仅输入音频，须至少包含 1 个参考视频或图片`→**`MiniMax-Hailuo-H3`** · `请同时添加参考图片和视频`→**`kling-v3-motion-control`** · `该模型需要参考图片才能生成视频`→**`midjourney-video`** · `请同时添加参考图片和音频`→**`omnihuman-1.5`**。
**77/77 都带 `rules`（共 102 条）；显式 `message` 只有这 4 条、每条只挂一个模型，其余靠模板句**（**如 `vidu-q4` 的"请输入提示词并添加参考图片"＝ `require:[prompt,image]` 的模板**）。
