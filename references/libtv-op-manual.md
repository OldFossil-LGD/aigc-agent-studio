# LibTV 引用链与点火操作手册（**按 MCP 原语写 · 平台方给出 · 2026-09-21**）

> **来源**：平台内 Agent 按"我方操作原语"给出的极具体步骤（投递节点 `Agent交付_WF1引用链` / `i-vt27575sdd7w`）。
> **本册性质**：**可直接照敲的操作手册**——每一步＝调什么 / 传什么 / 回读看什么 / 验收判据。
> **读完回哪**：`libtv-model-params.md` §一（机制）· `run-sheet.md` 站 5.5/6.5（流程）。

---

## 〇、通用铁律（每一步都适用）

| # | 铁律 | 说明 |
|---|---|---|
| **0.1** | **绝不手填 `imageList` / `imageListOrder` / 任何 `*List` 引用字段** | 它们是 `left` 建边后的**"系统重算产物"，只读不写**；**要改引用只改 `left`**（create 时的 `left`，或 `update_node` 的 `leftAdd` / `leftRemove`） |
| **0.2** | **建边 ＝ 在 `left=[…]` 里放上游节点 key** | **`left` 的数组顺序就是参考顺序**，系统据此生成 `imageListOrder` |
| **0.3** | **prompt 里每个被引用节点都必须"双花括号包裹 key"插桩 ＋ 写明用途** | **`left` 里有、prompt 里没插桩；或 prompt 里插了、`left` 里没有 → 都属引用不一致，必须在点火前修正** |
| **0.4** | **★ 幂等顺序（我此前做错了）** | **`create(run=false)` → `read_node` 核对 → 需要改就 `update(run=false)` → 再 `read_node` → `validate_generation_plan` 通过 → `generation_submit`**。**任何一步读回不符就停在该步修正，不带病点火。** |

---

## 一、一图扇出多镜（角色资产 → S1 / S4 / S7）

**★ 核心原则**：**CHAR 是"一对多"扇出，建三条独立的边，不复制节点、不经过中转节点。**
**★ 不要**把 S1 当作 S4 的上游来"传递身份"——**那会变成"镜头内容串联"，毁掉镜头独立性。**（★ 2026-09-28 落库注：**本条只禁"传递身份"**；**衔接仍可以用上一镜的落幅**——**身份走锚点、衔接用上一镜落幅**，见 `key-decisions.md` E132 第 5 条。）

**步骤**：
1. **确认上游可用**：`read_node(CHAR)` → 期望：节点存在 · 类型正确 · **`url` 非空（已生效）**；**url 为空则停止，先解决资产**。
2. **建 S1**：`create_node(nodeType="video", params={model:"Wan 3.0", modeType:"mixed2video", settings:{…}}, prompt="…〔CHAR〕为本镜唯一角色身份，必须保持面部/发型/服装一致…", left=[CHAR], run=false)`
3. **`read_node(S1)` 核对**（期望全部成立）：
   - `video` · `modeType=mixed2video` · **未运行/无产物**；
   - **`left` 含 CHAR**；
   - **系统重算出 `imageList`，其中出现 CHAR 条目**；
   - **`imageListOrder` 长度=1，第 0 位=CHAR**；
   - prompt 中含 `{{CHAR}}` 且与 `left` 一一对应。
4. **同法建 S4、S7**（各 `left=[CHAR]`），逐个核对。
5. **`read_project` 看全貌**：确认三条边 `CHAR→S1` / `CHAR→S4` / `CHAR→S7` 都在，**S1/S4/S7 之间没有误连边**，三者 `imageListOrder` 长度都为 1。
6. **校验并点火**：对每镜 `validate_generation_plan`（确认引用数在 `mixed2video [1,15]` 内）→ 通过后 `generation_submit`（或 `run=true`）→ **完成后 `read_node` 确认 `url` 非空**。

---

## 二、多张参考（角色＋场景＋道具）

### 2.1 顺序
**顺序由 `left` 数组顺序唯一决定**：**建议 `left=[角色, 场景, 道具]`，并在各镜头保持一致**。
```
create_node(video, params={model:"Wan 3.0", modeType:"mixed2video", settings:{…}},
  prompt="…角色 {{CHAR}} 处于场景 {{SCENE}} 中，手持道具 {{PROP}}；{{CHAR}}决定人物身份/脸/服装，{{SCENE}}决定环境空间，{{PROP}}决定道具外观…",
  left=[CHAR, SCENE, PROP], run=false)
```

### 2.2 ★ `imageListOrder` 与 prompt 插桩的对应关系
- 系统按 `left` 顺序重算：`imageListOrder[0]=CHAR`、`[1]=SCENE`、`[2]=PROP`（长度 3）；
- **★ 对应关系是"按 key 对应"，不是按文字出现先后对应**；
- 因此三条要求：**① `left` 里每个 key 都要在 prompt 里有同名插桩 ② prompt 里每个插桩 key 都必须在 `left`/`imageListOrder` 中存在 ③ 建议 prompt 中插桩首次出现顺序也与 `left` 一致（角色→场景→道具），但权威位次由 `left`/`imageListOrder` 决定**。
- **上限**：`mixed2video` 总图 ≤10、总引用 ≤15（视频 ≤5、音频 ≤5）。

> **⚠️ 与平台方早前口径的细微差异（标注待核）**：R2 里平台 Agent 说"**`{{}}` 出现顺序必须与 `reference_nodes` 数组顺序完全相同**"；本册（同一平台的 Agent）说"**按 key 对应，权威位次由 `left`/`imageListOrder` 决定，出现顺序只是"建议一致"**"。
> **→ 稳妥做法：两边都满足**（既让 `left` 顺序正确，又让 prompt 插桩首次出现顺序一致）。

### 2.3 ★ 顺序错了从哪个回读字段看出来
- **首要信号：`read_node` 的 `imageListOrder`**——它直接列出系统认定的参考顺序；**若 `[0]` 不是 CHAR（例如变成 SCENE），即顺序错**；
- 交叉信号：`imageList` 重算条目的排列/归属与预期不符；
- 一致性信号：**`left`（请求的边）与 `imageListOrder`（重算结果）应一致**；不一致则用 `read_project` 复核后修正；
- **★ 注意：`imageListOrder` 的"长度"只反映条数；"顺序对不对"必须逐位看 key**。

### 2.4 修正顺序（仍不手填）
```
update_node(node, leftRemove=[SCENE,CHAR,PROP], run=false)
→ update_node(node, leftAdd=[CHAR,SCENE,PROP], run=false)
→ read_node 确认 imageListOrder=[CHAR,SCENE,PROP]
```
增删单个参考：`leftAdd=[NEWPROP]` / `leftRemove=[OLDPROP]`，**每次之后都要 `read_node` 看长度与位次**。

---

## 三、首尾帧 `frames2video`

1. **准备两张已生效图像** FIRST（首帧）/ LAST（尾帧），`read_node` 均 `url` 非空。
2. **`modeType="frames2video"`，引用区间 `[1,2]`**：
   - 只给首帧：`left=[FIRST]`（1 个，合法）；
   - **首帧＋尾帧：`left=[FIRST, LAST]`（2 个）**；
   - **★ 位置约定：`left` 第 0 位＝首帧，第 1 位＝尾帧；首在前、尾在后，不可颠倒。**
```
create_node(video, params={model:"Wan 3.0", modeType:"frames2video", settings:{…}},
  prompt="从首帧 {{FIRST}} 自然运动/演变，最终收敛到尾帧 {{LAST}}；{{FIRST}}为起始画面，{{LAST}}为结束画面，过程连贯…",
  left=[FIRST, LAST], run=false)
```
3. **不要把尾帧塞进手填字段**；**首/尾帧都只通过 `left` 表达，靠"位次"区分首尾**。
   （★ 2026-09-28 落库注：**"首帧/尾帧有实名入参"是它侧（平台 Agent 编排层）的字段体系**——`start_frame_image_node` / `end_frame_image_node` 属**编排层一级字段**（出处与两侧字段差异见 `libtv-canvas-nodes.md` 末尾「★ 一处仍要自己验」；名字清单见 `libtv-model-params.md` §5.1）；**我方 MCP 侧走模型层**——`get_model("Wan 3.0")` 实测 `settings` 中**无** `firstFrame`/`lastFrame` 槽位，故**仍不可手填 `imageList`**，**在已实测做法下统一用 `left` 第 0/第 1 位**。）
4. **验收**：`modeType=frames2video` · **`imageListOrder` 长度=2 且 `[0]=FIRST`、`[1]=LAST`** · prompt 同时含两 key 并标明起始/结束用途 · `validate_generation_plan` 通过（`[1,2]`）。**顺序颠倒同样从 `imageListOrder` 位次看出。**

---

## 四、续写 `videoExtend2video`

1. **前置**：被续视频 **SRC 已生效**（`read_node(SRC)` `url` 非空）。
2. **`modeType="videoExtend2video"`，引用区间 `[1,15]`**，**被续视频作为上游放入 `left`**：
```
create_node(video, params={model:"Wan 3.0", modeType:"videoExtend2video", settings:{…}},
  prompt="基于视频 {{SRC}} 的结尾画面与状态继续延展，保持人物身份、场景、光线、运动方向连贯，紧接 {{SRC}} 最后一帧向后发展…",
  left=[SRC], run=false)
```
- **被续视频位置：`left` 第 0 位作为主依据**；`mixed2video` 里视频类 ≤5，**`videoExtend2video` 总引用 `[1,15]`、至少 1 个（SRC）**；
- 若还要锚定角色/道具图 → **`left=[SRC, CHAR, …]`，SRC 放第 0 位**，其余为辅助参考。
3. **验收**：`modeType=videoExtend2video` · **`left` 含 SRC 且在第 0 位** · 顺序字段长度与 `left` 一致 · prompt 含 `{{SRC}}` 且明确"接续其最后一帧/结尾状态" · `validate_generation_plan` 通过。
4. `generation_submit` → 完成后 `url` 非空；**可对结果继续链式续写（新节点 `left=[上一段成片]`）**。

---

## 五、验收判据汇总（A–H）

| # | 判据 |
|---|---|
| **A** | **上游可用**：`read_node(上游)` 节点存在 · 类型正确 · **`url` 非空** |
| **B** | **边建成**：`read_node(下游).left` 含全部预期上游 key；`read_project` 见对应有向边、**无多余边** |
| **C** | **重算正确**：`imageList` 非空且条目**来自 `left`（无手填值）**；**`imageListOrder` 长度==`left` 长度；逐位 key 与预期顺序相等（不只看长度）** |
| **D** | **prompt 一致性**：`left` 每个 key 都有同名插桩；prompt 每个插桩 key 都在 `left` 中；用途写清 |
| **E** | **模型/模式**：`params.model` 与 `modeType` 正确；`get_model` 核对模式与计数上限 |
| **F** | **计划合法**：`validate_generation_plan` 通过，无 `NODE_VALIDATION_FAILED`，各类计数满足 |
| **G** | **点火结果**：`generation_submit` 后进入运行态；完成后 `url` 非空 |
| **H** | **结构**：一对多（CHAR→S1/S4/S7）为**三条独立边**；续写链**逐段 `left` 指向上一段成片** |

---

## 六、★★ "先建后跑"点火前必查 10 项（Checklist）

`read_node` 确认**以下全部成立**才可 `generation_submit`：

1. **运行状态**：**未运行、无产物**（确认 `run=false` 生效、未误点火）；
2. **`params.model`**：预期模型；
3. **`params.modeType`**：`image2image` / `mixed2video` / `frames2video` / `videoExtend2video`，**与用途一致**；
4. **`params.settings`**：时长 / 比例 / 分辨率等正确；
5. **`left`**：上游 key **集合与顺序**正确（角色/场景/道具；**首尾帧 第0=首、第1=尾**；**续写 第0=被续视频**）；
6. **`imageList`**：**系统重算产物，来源全部等于 `left`，无任何手填条目**；
7. **`imageListOrder`**：**长度==`left` 长度，逐位 key 与预期一致**（**顺序对错的权威回读字段**）；
8. **prompt**：**含且仅含 `left` 节点的插桩引用**，用途标注清楚；台词/画面为定稿原文；
9. **计数约束**：`image2image [0,14]`；`mixed2video [1,15]`（图≤10/视频≤5/音频≤5）；`frames2video [1,2]`；`videoExtend2video [1,15]`；
10. **`validate_generation_plan`**：通过、无校验错误。

**→ 10 项全满足 ＝"参数已存对、可以点火"，再 `generation_submit`（或 `run=true`）。**

---

## 附 · 最小操作序列模板（多参考镜头）

```
read_node(CHAR/SCENE/PROP) 确认 url 非空
→ create_node(video, params={model:"Wan 3.0", modeType:"mixed2video", settings:{…}},
              prompt="…{{CHAR}}…{{SCENE}}…{{PROP}}…", left=[CHAR,SCENE,PROP], run=false)
→ read_node：核对 left / imageList / imageListOrder(逐位) / prompt 插桩
→ （不符则 update_node 的 leftAdd/leftRemove 修正后再 read_node）
→ validate_generation_plan 通过
→ generation_submit
→ read_node 直到 url 非空
```

---

# 第二部分 · 十镜全程流程（**平台方给出** · 投递节点 `Agent交付_WF2十镜流程` / `i-h6a89hzbt6e6`）

## 七、五阶段总览

| 阶段 | 名称 | 核心产物 |
|---|---|---|
| **S0** | **规划与校验** | 可执行的镜号依赖图 · 锚点清单 · **每镜 `left` 预案** |
| **S1** | **锚点阶段** | 3 个**已生效**的图片节点（角色 / 场景 / 道具） |
| **S2** | **镜头阶段** | 10 个**已生效**的镜头视频节点 |
| **S3** | **合成阶段** | 1 个成片节点 |
| **S4** | **验收与交付** | 成片 + **全链回读记录** |

**★★ 三条贯穿全程的铁律**：
1. **顺序**：`create_node(run=false)` → `read_node` 核对参数与 `left` → `validate_generation_plan` + `get_model` 校验 → `generation_submit` 点火 → `read_node` 确认"生效/有产物" → **再做下游**；
2. **任何节点"未生效"前，不得出现在下游节点的 `left` 里**；
3. **★ `left` 是唯一的建边手段**——**不要只在文字 prompt 里写节点 key：文字提及不会生成 `imageList`/`imageListOrder`，等于没引用。** **且"创建 ≠ 生效"**，必须点火并等产物。

## 八、各阶段入口条件 / 出口验收（要点）

- **S0 出口验收（5 条）**：① 产出**镜号依赖图**（每镜引用哪些锚点、镜与镜之间有无续写/首尾帧关系）② 三个锚点描述定稿，**≥3 镜共用的视觉元素收敛成单一锚点，避免重复造** ③ **每镜 `left` 预案列好** ④ 用 `get_model` 确认模型可用、用 `validate_generation_plan` 做一次**结构预校验（此时可用占位符，重点查结构/时长/比例）** ⑤ **明确并行批次划分**。
- **S1 出口验收**：3 个锚点**全部"已生效（有产物）"**；`read_node` 显示 `left` 已正确重算出 `imageList`/`imageListOrder`；外观与定稿一致。
- **S2 出口验收**：10 个镜头**全部生效**；逐镜回读确认**引用版本正确 · 画面连续 · 时长与分镜表一致 · 无对白 · 写实风格统一**；**续写链的首尾衔接成立**。
- **S3 出口验收**：成片节点生效；**总时长≈40s**；顺序与分镜一致；转场/音量符合预期。
- **S4 出口验收**：成片完整可播放；**`read_project` 全链状态一致（无"废弃/失败/未生效"残留）**；交付物与剧本分镜逐项核对通过。

## 九、★ 锚点阶段：并行策略 + "可被引用"的判据

- **三个锚点彼此独立、互不引用 → 同一批并行**：一次 `create_node ×3`（`run=false`）→ 校验通过后**同批 `generation_submit`**；**不要把三个锚点串成 A→B→C**（无依赖却串行＝纯浪费时间）。
- **★ "可被引用"的 5 条回读判据**：① **状态＝已生效（成功），且有真实产物 URL**（**无产物＝未生效，禁止做下游 `left`**）② **`left` 与创建时传的上游 key 列表一致** ③ **`imageList`/`imageListOrder` 已按 `left` 重算、非空且顺序符合预期**（**这是"`left` 建边成功"的直接证据；为空或顺序错乱＝引用没真正建立**）④ 生成参数（prompt/模型/比例）与定稿一致 ⑤ 记录节点 key，回填到 S0 的 `left` 预案。
  **★ 口诀：状态生效 ＋ 有产物 ＋ `left` 正确 ＋ `imageList`/`imageListOrder` 已重算且非空 ＝ 可被引用。**

## 十、★ 镜头阶段：波次 + 每批五个标准动作

- **排序规则**：**先做"纯锚点引用、无续写依赖"的镜头**（`left` 只含已生效锚点、不引用其他镜头）→ 可并行（受并发上限约束，超限拆轮）；**续写/首尾帧链必须串行**（A 生效后 B 才能建/点火）；**不同的、互不引用的链之间可并行**。
- **按依赖图切成若干"波次"**：**每一波只放"所引用节点全部已生效、且波次内部互不引用"的镜头**；一波全部生效后再排下一波。
- **每批五个标准动作**：① **建**（`run=false`，`left` 只放已生效的锚点/上一镜 key）② **批前校验**（逐个 `read_node` 核对 prompt/`left`/模型/时长/比例；`validate_generation_plan` 校验本批；`get_model` 确认模型）③ **点火**（同批 `generation_submit`）④ **批后回读（必须做）**：逐个 `read_node` 确认状态生效、有产物 ⑤ **★ 进入下一批前必须重新核对 6 项**：**引用版本**（实际使用的锚点 key 是否仍是当前生效版本，防版本漂移）· **`left`/`imageList`/`imageListOrder`**（与预案一致、非空、顺序正确）· **时长**（每镜符合分镜表、累计朝 40s 收敛）· **连续性**（角色容貌/服装、场景、道具一致；风格统一；无对白）· **续写衔接**（首尾帧/动作是否接上）· **依赖图更新**（回填新生效 key，重算"下一波哪些可做"）。
- **写实无对白单场景提示**：**多数镜头可只靠 3 个锚点并行生成**；**仅在需要动作/情绪连续衔接时才用续写链**（**续写越多，返工成本越高，慎用**）。

## 十一、★★ "拉回"到底落在哪一步（**它给的明确答案**）

**"拉回"＝把一个已生效资产"重新接为该节点的上游"，用 `update_node` 的 `leftAdd` 完成——不是新建节点。**
- **动作**：`update_node(node_key, leftAdd=[要加回的资产 key])` → 加完**必须 `read_node` 确认 `left` 已更新、系统已重算出 `imageList`/`imageListOrder`** → 再 `validate_generation_plan` → **然后才能点火**；
- **反向**：去掉错误上游用 `leftRemove`；
- **★ 何时才新建节点**：**需要"内容不同的新产物"时**（改了画面/锚点本身、或原节点生成失败废弃重建）；**单纯把已有资产接回边，一律 `leftAdd`，不新建**；
- **★★ 注意**：**`leftAdd` 一个新版本锚点后，该镜头节点回到"需重新生成"状态，必须重新点火才会用上新引用。**

## 十二、每阶段最易错的一步（症状 → 提前发现的回读字段）

| 阶段 | 最易错 | 提前发现 |
|---|---|---|
| **S0** | 依赖图漏标续写关系；或**让多个镜头各自引用"重复造的同类锚点"** | `validate_generation_plan` 结构校验；**锚点清单是否"一类元素只有一个 key"** |
| **S1** | **只在文字 prompt 里写了参考节点、却没用 `left` 建边**；或**锚点未生效就拿去做镜头 `left`** | `read_node` 的 `left`/`imageList`/`imageListOrder`（非空？顺序对？）＋ 状态/产物 |
| **S2** | ① 把**未生效的镜头**放进同批/下游 `left` ② `left` 缺锚点或**引错版本** ③ **不看累计时长一路生成** | 状态/产物 · `left`+`imageList`+`imageListOrder`+**实际产物首帧** · **每镜时长字段与累计值** |
| **S3** | **10 个镜头放入顺序与分镜不一致，或漏镜/重复镜**；音量失衡 | 合成节点 `read_node` 的 **`left`（镜头 key 顺序）** ＋ 成片时长 |
| **S4** | **只看成片不回读全链**，遗留"失败/废弃/未生效"节点或旧版本锚点仍被引用 | **`read_project` 全链节点状态清单**（是否全部生效、无废弃残留、引用指向当前版本） |

## 十三、★ 中途锚点要改，已做镜头怎么办

**先判断改的是"边"还是"内容"**：
- **只是引用关系错**（镜头没接上正确锚点）→ `leftAdd`/`leftRemove` 改边即可，**锚点产物不变**；
- **锚点内容本身要改**（角色长相/服装、场景、道具样式）→ **锚点节点更新后需重新生成生效**；**一旦它在同一 key 上产出新版本（或用新节点替换），它回到"已创建/需重新生成"，重新生效前下游不得推进**。

**受影响范围（★ 沿 `left` 实际引用链排查，不凭记忆）**：
1. **直接引用该锚点的所有镜头**：现有结果**一律作废**，必须用新锚点重新生成；
2. **续写链上的间接镜头**：若 B 续写自 A，而 A 因锚点变更重做，则 **B 及之后引用 A 的镜头，衔接基础已变 → 整条续写链都要重做**；
3. **可保留的**：**完全没有引用该锚点、也不续写任何受影响镜头的镜头**可保留（**单场景单角色下，角色/场景锚点通常被多数镜头引用 → 这两类改动往往导致大部分镜头重做**；**道具锚点若仅个别镜出现，则只重做出现该道具的镜头**）。

**处理动作**：
- **优先在原锚点节点更新参数并重新生成**（**保持 key 不变 → 下游 `left` 无需改**）→ 重新生效后，把受影响镜头在各自原节点**重新点火**；
- 或按变更规范**新建锚点节点 + 旧节点标废弃** → 用 `leftRemove` 旧 key ＋ `leftAdd` 新 key 改每个受影响镜头 → 再重新点火；
- **重做仍按波次推进**：先确保新锚点生效 → 再重做直接引用镜头 → 最后重做续写链下游；每批批后回读 `left`/`imageList`/`imageListOrder`/时长/连续性；
- **★ 合成节点必须在所有受影响镜头重做生效后重新生成**，避免拼入旧画面。

## 附 · 一页速查流程

```
S0 定稿依赖图/锚点/left 预案 → validate + get_model（不点火）
→ S1 同批建 3 锚点(run=false) → 校验 → 点火 → read_node(状态/产物、left、imageList、imageListOrder) 全生效
→ S2 按波次：建(run=false, left 只放已生效) → read + validate + get_model → 点火
     → read_node 回读(状态/产物、left、imageList、imageListOrder、时长、连续性)
     → 回填 key、重排下一波，直到 10 镜生效
→ S3 建合成节点(left 按序放 10 镜 + BGM) → 点火 → read 成片(顺序、≈40s、音量)
→ S4 read_project 全链无废弃残留 → 对照剧本分镜验收交付
拉回 = update_node(leftAdd=[key])，不是新建；
改锚点内容 = 锚点重生效后，沿引用链/续写链作废重做，合成最后重生成。
```

---

# 第三部分 · 读通道故障排查（**已拆卷 → `references/libtv-op-manual-part2.md`**）

**本节全部内容已迁至续册 `libtv-op-manual-part2.md`**，编号连续：§十四 三层判据表 · §十五 键名算法规格 · §十六 五条常见误判 · §十七 处置顺序 · §十八 阶段闸 · §十九 外部读通道全灭 + 禁解密红线 · §二十 宿主周期实测（**步长不恒定 · 事件驱动**）。
**何时读续册**：`read_project` / `read_node` 不在工具索引、读回恒 0 时——**先读续册 §十四 定位故障层**。

---

---

> **本册续见 `libtv-op-manual-part3.md`**：**第二十六节 点火审批链** 已移入续册（本册到 300 行上限，故拆）。

---

## 附录 · CLI 写入纪律：`-s` / `-u` 到底在哪一步被拒（**REA 静态 · 2026-10-15**）

- **`-s` 四类直接拒绝**：空项 · 没有 `=`（或 `=` 在首位）· key 为空 · **同一个 key 重复出现**；
- **`-s` 值解析顺序**：`true` → `false` → `null` → 数字 → `JSON.parse` → **原文**；
  **★ 兜底返回的是未 trim 的原文**（`-s k= foo ` 会保留尾随空格）；
- **★★ `-u` 8 条拒改键（逐字）**：`params`（改用 `--set key=value` 或 `--prompt`）·
  `label`（改用 `--name`，且同步时 `label` 归一为 `name`）· `type` · `action` · `taskInfo` ·
  `prevTaskInfo` · `generatorType` · `isStale`——**后六条一律"不可通过 CLI 变更"**；
- **schema 合并只保留允许字段**；**非法旧值用 schema 默认值替换**（不保留、不报错）；
- **同步清洗比网页端窄**：CLI **只清 `url[]` 与 `poster` 的 `blob:`/`data:`**，
  **不可把网页端 canvas service 的清洗规则套到 CLI 上**；
- **`nodes/batch` 节点体形态**：`position`/`measured` 是**字符串**、`data` 是 **JSON 字符串**、
  无父节点时 `parentKey` 是空串、有 `resourceMeta` 时**双写 `resourceMeta` + `_resourceMeta`**。

**详见** `outputs/libtv_rea_20261014/33_CLI节点写入管线.md`（证据 C161–C165）。

### 附 · 分派表与"禁止手填媒体列表"的机器执法（**REA 静态 · 2026-10-15**）

- **三张类型表互不相同**：创建/构造 payload **同 7 个**（`audio · image · script · storyboard · text · video · video-clip`，**无 `group`**）；运行 **8 个**（多 `group`，其 handler 固定报"无独立 generation/create 流程"）。`CREATE_TYPE_CHOICES` 取自创建表 ⟹ **help 行（含 group）≠ 真实可创建集合**；
- **★ `-t video-clip` 的创建体会写 `type: 1`**：`buildCreateNodePayload6` 传 `data.type="video-clip"`，映射表无此键、回落 TEXT（源码级 observed；**服务端如何处理仍是 unknown**）；对照 **`storyboard` 用 `data.type="script"` → backend 20**，不受影响；
- **★ 八条禁止参数键（CLI 直接拒绝）**：`imageList` · `videoList` · `audioList` · `imageListOrder` · `videoListOrder` · `audioListOrder` · `mixedList` · `mixedListOrder`——报错原文指向 **`--left` / `--left-add`**，**这是"绝不手填 `imageList`"的机器级执法**；
- **`--update` 白名单只有 `name` 与 `params`**；`params` 必须是 JSON object，否则报错；
- **两套枚举别混**：`node create -t` 有 `group`/`video-clip`；`model search -t` 有 `storyboard`、**无** `group`/`video-clip`。

**详见** `outputs/libtv_rea_20261014/35_CLI分派表与数据补丁白名单.md`（证据 C171–C176）。

- **网页端独有（CLI 载荷 0 命中，字段名/模型名必须字面出现才能进请求体）**：`clientContext`（角色卡上报）· `params.draft`（`star-video2.5-draft` 样片模式）· 长视频 `agent_name` 注入 · `refMap` · `imageLabelList` · `editSegments` ⟹ **走 CLI 时这些机制不存在**；反向不成立（服务端容忍度 unknown）；
- **CLI 独有**：`mixed2video` 且 `mixedList` 为空时，**由 image/video/audio + `mixedListOrder` 自动合成**；
- **★ 字段名澄清 + 一致项**：**线上 `*ListV2` 条目的键是 `duration`**（`durationSec` 是节点侧/探测侧字段名），**两端一致**；另有一致 11 项（模式剪枝五条 · `asset://` 同时改写 url+nodeId · `textList` 展开 · 列表三形态 · `cameraPresets`→prompt 串 · 时长回填 · `loraList`/`elementList`/`effectTemplateUuids`）——
  详见 `outputs/libtv_rea_20261014/36_CLI与网页端提交口径对照.md`（C177–C181）。
