# FilmDSL 交换层（CineCrew 对接册）

> **何时读**：要把本库的分镜契约交给外部 crew / 别的 agent 系统；或要拿别人产出的
> `SceneBlueprint` 回填本库；或评审问"这一镜的约束有没有落到可机判的结构上"。
> **本册只定义交换视图，不定义生产规则**；生产仍从 `production-compiler.md` 进。

## 1 · 一句话定位

本库 01–04 已经是"剧本与视频模型之间的结构层"，但格式是私有的。`filmdsl/v1` 是给
外部 crew 读的**投影**：形状对齐 CineCrew（ECCV 2026）的 `SceneBlueprint`——
`metadata / global_style / assets / memory / clips[]`，每镜四层
（narrative / staging / render / assembly）。

**权威不变**：`01_production_contract` → `04_prompt_packages` 仍是唯一裁决源。
交换视图被改一份，不能反过来说计划变了；判据是 `origin.artifacts` 里的 sha256。

## 2 · 为什么值得接（不是凑热闹）

CineCrew 的结论与本库的实战是同一件事：长片漂移的主因不是模型不行，而是**剧本在
关键机位/连续性处欠定义**，于是每镜各自发挥。它给出的解法是把这些欠定义项显式写进
结构化字段，并在生成前用资产库把它们钉住。本库早已这样做（分镜契约 + 资产四层 + 引用计划），
差别只在：**我们的字段名别人不认识**。交换层补的就是这一层翻译。

## 3 · 五层归属（谁写、写什么、读谁）

| 层 | FilmDSL 字段 | 本库来源 | 写入方（唯一） |
|---|---|---|---|
| L0 元信息/风格 | `metadata`、`global_style` | 01 的 goal / 画幅 / fps / `visual_style` | 本库编译产物，投影不改写 |
| L1 叙事 | `clips[].narrative_layer` | 03 `shots[].description` + 04 storyboard 契约行 + 对白字段 | Story Editor 对应站 4 剧本 |
| L2 调度 | `clips[].staging_layer` | 03 `shots[]` 的时长表 / 机位 / 光线 / 环境 / 实体 | Cinematographer 对应站 3 方案包 |
| L3 渲染 | `clips[].render_layer` | 04 `candidate_image` / `video_candidate` 的 blocks | Technical Director 对应站 6 提示词包 |
| L4 装配 | `clips[].assembly_layer` | 03 `shot_timing.cut_range`、转场字段 | Post Supervisor 对应站 6.6 |

**一册一写者**：外部系统只能写它那一层，且必须经 `filmdsl_bridge.py check` 复核。
跨层改写（例如 critic 直接改 L1 叙事）在本库口径里属于越权，回到站 7 判责任层。

## 4 · 资产 ID 纪律

- 角色 / 场景 / 道具的 `id` 只能来自 02（`char_*`、`loc_*` 或本库实体 id）；交换视图不新造 id。
- 每个资产的迭代链（`iteration_chain`）原样带出；链上的节点 id 是引用凭据，断链即 FAIL。
- 镜头实体三档来源：`shots[].entities`（显式）> 节点自带 `asset_id` > 迭代链反查。
  三档都查不到的，**报 `UNRESOLVED_ASSET`，不补一个看起来合理的 id**。

## 5 · 十个 crew 角色 → 本库工位

外部 crew 的岗位名与本库十站不是一一对应，按下表换算；换算不了的不硬凑。

| crew 角色 | 本库工位 | 边界 |
|---|---|---|
| Showrunner | 站 1 命题 + 站 2 一页 brief | 只定方向与预算，不写提示词 |
| Story Editor | 站 4 剧本（M1–M12） | 节拍与台词交站 4 判据 |
| Art Department | 站 5 资产四层 | 数量与版本裁决在 `asset-standard.md` |
| Acting Coach | 表演册（情绪/强度字段） | 只在有人的镜头成立，空镜不补 |
| Cinematographer | 站 3 风格编号 + 机位包 | 一片一包，定了不换 |
| Technical Director | 站 6 分镜四步 + 提示词包 | 提示词块缺一即 FAIL |
| Production Operator | 站 6.5 投喂与生成 | 见 `vimax-runtime.md` |
| Dailies Reviewer | 站 7 返工判层 + `qa-failure-codes.md` | 只给定位，不自动重抽 |
| VO Director | 声音册与对白轨 | 无声镜头不补人声 |
| Post Supervisor | 站 6.6 合成 + 站 6.7 交付 | 交付前过 `delivery-engineering.md` 的规格门 |

## 6 · 回修梯度（粗到细，抄它这一条值得）

CineCrew 的 dailies 回修顺序是**先改约束、再改关键帧、最后改视频提示词**。本库的
"失败按责任层回退"是同一件事的具体化，顺序照此执行：

1. 连续性与约束字段（禁止/必需道具、锁定实体、环境 id）——改这里最便宜；
2. 关键帧提示词（构图与身份锚点）；
3. 视频提示词（动作、声音）；
4. 仍不过才回上游重排镜头（站 6 的分镜结构或站 3 的包）。

**先改第 3 步是本库历史上最贵的错误**：提示词越写越长，约束却还是空的，下一镜照漂。
返工回执与版本绑定仍按 `offline-continuity-entry.md`；审片口径仍按 `review-passes.md`。

## 7 · 命令

```text
python scripts/filmdsl_bridge.py export --artifacts out/ --out out/09_filmdsl.json
python scripts/filmdsl_bridge.py check  --filmdsl out/09_filmdsl.json --artifacts out/ --require-complete
python scripts/filmdsl_bridge.py --self-test
```

`export` 附 `import_report`：`status`（complete / partial / empty）、`codes`、
`unmapped_or_missing`（连位置一起给）。`check` 会**重投影再逐键比对**，
所以"视图里偷偷少了一镜"或"风格被换掉"都会红。

常驻错误码（本册唯一登记处）：

| 码 | 含义 | 处置 |
|---|---|---|
| `STYLE_MISSING` | 没有 `visual_style` | 回站 3 定风格编号，不许留空 |
| `CLIP_DURATION_MISSING` | 镜头没有正的时长 | 回站 6 补时长表 |
| `NARRATIVE_ACTION_MISSING` | 既无 description 也无契约行 | 回站 6 补分镜 |
| `UNRESOLVED_ASSET` | 引用了 02 里没有的资产 | 回站 5 补资产或删引用，不许改 id 蒙混 |
| `DIALOGUE_SPEAKER_MISSING` | 声明有对白却缺说话人或台词 | 回站 4，台词逐字锁定 |
| `AUTHORITY_LEAK` | 视图夹带 `run:true` / `ignition_allowed:true` | 删掉；批准只走站 6.5 的显式通道 |
| `DROPPED_FIELD` | 重投影后与权威不一致 | 重导；不要手工修补视图 |
| `STALE_EXPORT` | 01–04 已变，视图过期 | 重导后再评审 |
| `SHOTS_EMPTY` | 没有可投影的镜头 | 不是通过，回站 6 |

## 8 · 不做什么

- 不产计划、不建画布、不点火、不联网；交换视图不是执行计划，替代不了 08 号命令计划。
- 不当 `source_replica` 的凭据：反推类任务先看 `reverse-fidelity-contract.md`。
- 不把外部系统当第二权威：它只能提出改动建议，落库前必须重投影复核。
- 不承诺媒体质量：结构一致 ≠ 画面成立，画面仍靠站 7 与人的眼睛。

配套：执行侧看 `vimax-runtime.md`；库内编译主链看 `production-compiler.md`。
