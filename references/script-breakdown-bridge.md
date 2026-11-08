# 剧本拆解桥（剧本 → 资产 → 分镜 的缝合册）

> **何时读**：拿到一份剧本，要回答"这部片需要哪些资产、多少镜、每镜什么景别"；
> 或用户说"帮我把剧本拆成分镜和资产清单"。**拆解不是创作**，它只把剧本里已经写着的东西
> 变成可对账的结构；写景别、定风格、出提示词仍在站 3–6。

## 1 · 为什么单独成册

本库原链是 `01_production_contract → 08`，而 01 是**人写好的计划**。真正卡住人的一步
在更前面：剧本读完了，谁把它变成"17 个角色 / 26 场 / 616 镜 / 每镜挂哪几张图"？
此前只有 `compile_text_input.py` 的极简解析，认 `镜头N` 行与一份写死的关键词表，
中文文学剧本一进来就退化成段落占位。

本册补的就是这一层，并把两家外部项目的做法各取一段（只取方法，不引入依赖）：

| 来源 | 取什么 | 不取什么 |
|---|---|---|
| CineCrew | **资产先行**：先把 AssetLibrary 建起来，再逐镜写；景别/角度/运动用固定枚举；回修从约束开始 | 它的生成后端、它的 FilmDSL 存储（我们只做投影，见 `filmdsl-interchange.md`） |
| ViMax | `shot_brief` 五字段（idx / is_last / cam_idx / visual_desc / audio_desc）、场景→镜头**相机树**、`<角色>` 标记纪律 | 它的三工作流入口（执行侧归 `vimax-runtime.md`） |
| 本库 | 字段口径、资产四层与数量裁决、站序、门禁（唯一权威） | — |

## 2 · 产物（一份拆解，三个视图）

```text
python scripts/breakdown_compile.py --script 剧本.md --out out/ \
    [--duration 90] [--aspect 16:9] [--style 写实电影纪录片] [--asset-spec 资产描述.json]
```

| 产物 | 是什么 | 交给谁 |
|---|---|---|
| `10_breakdown.json` | 拆解单：scenes / characters（含 aliases）/ props / shots / camera_tree | `scripts/asset_manifest.py` 做资产派生与对账；`filmdsl_bridge.py` 的输入来源之一 |
| `11_compiler_input.json` | 编译输入（形状对齐 `parse_text_input`） | `scripts/compile_production.py` → 01–08 |
| 12 号分镜表（12_shotlist.md） | 人读分镜表（景别/机位/时长/出场/道具/台词/未解） | 站 6 逐镜复核 |
| `--asset-spec` | 站 5 的接口：`{"char_01": "描述"}` 或 `{"林": {...}}` | 补齐后编译门禁才可能全绿 |

`--asset-spec` 的存在是故意的：**拆解不写视觉描述**。没描述的资产，编译门禁会停在
`PROMPT_UNRESOLVED`，这正是站 5 该干的活，不许由脚本代写。

## 3 · 认哪些版式（真实中文剧本）

- **场景标题**：`场景一 …`、`内景 日 客厅`、**加粗剧作 slugline** `**1-1 非洲某国·首都港口 日 外**`。
  内外景取 `内/外/内外/INT/EXT` 或行尾单字；时间取 清晨/傍晚/雨夜/深夜/夜/日。
- **人物表**：一行式 `人物：A、B`；列表式 `**人物**` + `- **周正华（老周）**，41岁…`
  —— 括号里的是别名，`老周` 与 `周正华` 归同一个人；`罗杰·汉密尔顿` 自动登记 `罗杰`。
- **对白**：`名字：台词`、`**名字**：台词`、`名字（情绪）：台词`；台词逐字入单，改一个字即 FAIL。
- **前导信息不成镜**：`#` 标题、`## 幕`、`**类型**`、`**写法**`、`---`、表格行一律跳过；
  只有第一个场景标题之后才开始切镜。
- **没有场景标题**时退回单场景模式并报 `NO_SCENE_HEADINGS`，不假装切好了。

## 4 · 拆解单字段契约

| 字段 | 语义 | 谁填 |
|---|---|---|
| `characters[].id / name / aliases` | 稳定 id `char_NN`，别名用于对白识别 | 脚本 |
| `characters[].declared` | 是否出现在人物表；`false` 且说过话 → `ENTITY_CANDIDATE` | 脚本 |
| `props[].id / name` | 道具**只从道具表取**，不从行文里猜 | 脚本 |
| `shots[].scale / camera / angle` | 景别/运动/角度的枚举值；文本没有就 `UNSPECIFIED` | 脚本 + 站 6 补 |
| `shots[].duration_sec` | 文本里的 `N秒`；没有就留空 | 脚本 + `--duration` |
| `shots[].characters / props` | 本镜出场与入画（决定参考图职责） | 脚本 |
| `shots[].dialogues` | 按剧本顺序保存本镜全部说话人 id 与逐字台词，编译输入及分镜表逐句消费 | 脚本 |
| `shots[].dialogue` | 兼容旧单句文档的末句摘要，新文档从 dialogues 派生 | 脚本 |
| `shots[].feed_plan` | 参考计划草案（场景 view + 身份 face/body + 道具 anchor/closeup，≤4 张） | 脚本生成，站 5.5 复核 |
| `camera_tree` | 场景→镜头的父子树，带 `cam_idx` / `is_last` | 脚本 |

## 5 · 站序（拆解插在哪）

```text
站 4 剧本锁 → ① 拆解（本册）→ ② 站 5 资产（asset_manifest 派生对账 + 描述）→
站 6 分镜（compile_production 出 01–04）→ 站 6.5 生成（vimax_runtime / LibTV）
```

- 拆解**不锁**任何东西：它给的是"剧本里有据的结构 + 明确的未解清单"。
- 资产数量裁决仍在 `asset-standard.md`；12 号分镜表（12_shotlist.md） 只是拆解的副本，不是分镜终稿。
- 站 6 的景别/机位补写之后，要重跑拆解或直接改 11 号输入，再重新编译——**不要手改 03**。

## 6 · 错误码（本册唯一登记处）

| 码 | 含义 | 处置 |
|---|---|---|
| `SHOTS_EMPTY` | 没拆出镜头 | 不是通过；先查场景标题与段落 |
| `SHOT_WITHOUT_ACTION` | 既无动作也无对白 | 回剧本补，或删掉空段 |
| `DUPLICATE_SHOT_ID` | 镜号重复 | 重跑拆解，不要手拼 |
| `DIALOGUE_NOT_VERBATIM` | 台词与剧本原文不一致 | 台词逐字锁定，改字即回退 |
| `DIALOGUE_SPEAKER_MISSING` | 有对白缺说话人/台词 | 回剧本 |
| `UNRESOLVED_ASSET` | 引用了不存在的角色/道具 id | 修拆解，不许改 id 蒙混 |
| `ENTITY_CANDIDATE` | 说过话但不在人物表 | 确认同人/漏登，再补人物表 |
| `CAMERA_UNSPECIFIED` | 若干镜没写景别 | 站 6 补；单镜详情在 `unresolved` |
| `DURATION_MISSING` / `DURATION_SUM_MISMATCH` | 无时长 / 合计与目标差 >20% | 补时长或改档 |
| `PROPS_NONE` | 没有道具表 | 道具只能显式给，脚本不猜 |
| `NO_SCENE_HEADINGS` | 没有场景标题 | 补标题，否则资产无法按空间归组 |
| `SCENE_EMPTY` | 场景里没有镜头 | 删场景或补内容 |

## 7 · 实测（2026-10-31）

- 夹具链 `cn_three_scenes`（15s）：拆解 0 FAIL → `compile_production` **PASS**（0 failure）
  → `filmdsl_bridge export` 0 FAIL，14 项自检全过。
- 真实稿《雪与热土》定稿（70659 字节、1619 行）：26 场 / 18 角色 / 616 镜 /
  5 个未登记说话人 / 616 镜缺景别，**0 FAIL**。
  这说明拆解能在真实文学剧本上工作，也说明它不会替你编景别——那 616 条 `UNSPECIFIED`
  就是站 6 的工作量清单。

## 8 · 不做什么

- 不写视觉描述、不选风格、不出提示词（站 3–6 的活）。
- 不把段落数当镜数定稿：`SHOT_SPLIT_FROM_PARAGRAPH` 只是起点，镜数要人核。
- 不生成媒体、不点火、不联网。
- 不当 `source_replica` 的凭据；反推先看 `reverse-fidelity-contract.md`。
