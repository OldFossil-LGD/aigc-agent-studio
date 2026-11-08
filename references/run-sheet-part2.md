# 总流程（续册）：**分册路由** —— 按决策点查

> **何时读**：走到总流程某一站、要做一个具体决策时（例：写【光位与影调】之前、交付前审片之前）。
> **读完回哪**：回 `run-sheet.md`（七站流程 · 每站过什么才许走）。
> **★ 本册只做一件事**：**告诉你「这个决策该读哪一册」**——**规则仍在原册，本册不复述**。

---

## 统一基准三路路由

| 要决定什么 | owner | 只读入口 |
|---|---|---|
| 状态机、交付契约、知识权威 | A | `outputs/统一基准/00_总纲_知识分层与权威模型.md` · `01_统一状态机与交付契约.md` |
| 节点、边、分组、权威层 | A | `02_图语法_节点边分组参数.md` · `graph_plan.schema.json` |
| 时长/题材/复杂度规模预算 | A | `03_规模预算与题材时长档位.md` |
| W1/W2/W3 画像与原库取舍 | A | `04_三作画像与原skill审计.md` · `claim_ledger.jsonl` |
| 世界状态与下游失效 | A | `05_世界状态与变更传播.md` |
| 输入到 prompt、craft prior、提示词门禁 | B | `10_输入到计划编译器规范.md` · `11_提示词包与五类模板.md` · `12_创作工艺路由_人物动作灯光风格声音.md` · `13_提示词门禁与失败诊断.md` · `14_语言口型字幕与本地化.md` · `samples/B1～B7` |
| LibTV 图执行、模型成本、回读恢复 | C | `20_LibTV图构建与分组规范.md` · `21_模型成本并发与恢复规范.md` · `22_结构回读与媒体验收规范.md` · `23_三作与合成场景回归测试.md` · `C_平台执行回执.md` |
| 剧本离线包总门禁（不点火） | A+C | `offline-generation-gate-ledger.md` · `scripts/render_offline_prompts.py` · `scripts/offline_package_lint.py` |

**规则**：B、C 不改 A 的 schema；A 最终读取 B/C 回执后统一挂索引与工位。

---

## 七 ★ 分册路由（**按决策点查** —— 此前 119 册无工位，2026-09-19 补）

> **为什么要这一节**：**实测**——`references/` 共 156 册，其中 **119 册在总流程里没有任何工位**。
> **后果**：**写稿时只会沿本页给的指针走，没被派去读的册等于不存在**。
> **实例**：`color-grading-styles.md` 早就有 14 族调色，但没工位 → 我批量写的 31 份稿里**调色方向 22/31 同款**。
> **用法**：**走到哪一站、要做什么决策 → 先查下表那一行**。

### 站 5.5 / 6.5 / 6.6 · 落到 LibTV 时（**自主版新增 · 2026-09-20**）

| 要决定什么 | 读哪册 |
|---|---|
| **平台自己的口径**（八步顺序 / 防漂移三规则 / 派生锚点 / 尾帧拉回 / `{{node_key}}` 插桩 / 模式选择表 / 成本量级 / **12 个能力名**） | **`libtv-official-qa.md`（★ 一手源 · 含对账表与 R1 剧本）** · **续册二（R2–R5）`libtv-official-qa-part2.md`** · **续册三（R6–R10）`libtv-official-qa-part3.md`** · **★ 模型参数字典（实测字段真相）`libtv-model-params.md`** · **模型目录（该选哪个模型 / modelKey 是什么）`libtv-model-catalog.md`** · **续册四（R12 硬规则／R13 错误码／R14 成本）`libtv-official-qa-part4.md`** · **续册五（R16 首尾帧续写与审核／R17 导演台与批量）`libtv-official-qa-part5.md`** · **续册六（R18 非VIP三模型差异与选型／R19 音频建立序列与审核边界／R20 它挑我方流程的错）`libtv-official-qa-part6.md`** · **续册七（UV1 点火与提交／UV2 合成与导出／UV3 其余接口 10 问）`libtv-official-qa-part7.md` · `libtv-official-qa-part8.md`** · **★★ 引用链与点火操作手册（按 MCP 原语）`libtv-op-manual.md`** · **★ 续册三 点火审批链 `libtv-op-manual-part3.md`** · **★ 流程坑与点火前自查清单 `libtv-op-checklist.md`** · **★★ 单镜提示词结构·平台审计版 `libtv-prompt-structure.md`** · **★ 点火链·导演台·计费口径 `libtv-ignite-director-billing.md`** · **★★ 点火与合成实操字段（R37/R39）`libtv-ignite-ops-fields.md`** · **★★ 产出规格/交付运维/内容方法（R40/R41/R42）`libtv-quality-delivery-content.md`** · **★★★ 平台自家写法样本（实物学）`libtv-prompt-house-style.md`（★ 官方预演 3 条 + 落地页 6 条场景提示词）** · **★★ 能力矩阵（48 工具×实测状态）`libtv-capability-matrix.md`** · **★★★ 资产与环节标准清单（单一入口）`asset-and-stage-checklist.md`** · **续册（审计修订）`asset-and-stage-checklist-part2.md`** · **★ 网页端请求形状与任务端点 `libtv-web-api-shapes.md`** · **★ 本地录制与取证 `recording-and-evidence.md`** |
| 画布与节点怎么调（六种节点 / 幂等键与 revision / Agent 排他 / 导出契约 / 陷阱） | `libtv-canvas-nodes.md`  · **要它回答时（写进我能读的容器）：`libtv-agent-protocol.md`** · **统计 media hash / binding 分层：`libtv-media-hash-cross.md`；W1/W2/W3 分册：`libtv-media-hash-w1.md` · `libtv-media-hash-w2.md` · `libtv-media-hash-w3.md`** · **★ 节点字段补遗 `libtv-node-field-notes.md` · ★ 合成节点与时间线 `libtv-compose-timeline.md` · ★ CLI 环境与绑定 `libtv-cli-env-binding.md` · ★ CLI 管道体系 `libtv-cli-pipelines.md`** |
| **画布实证与提示词写法分册** | `libtv-canvas-anatomy.md` 主册/续册 · `libtv-prompt-anatomy-distilled.md` 主册/续册 · **★ 节点拓扑与顺序 `libtv-node-topology.md`** |
| **标准工作流程基准**（做新作品前**先定"学哪一派"**：七部实测分长段长词派 / 短段短词派 / 中间态 / 素材态，**没有唯一标准**） | **`standard-workflow-the-turn.md`** 主册（§0–§4 结构 · §7 跨作品校验 · §8 边界）· **★ 续册（§5–§6 骨架与填空模板 T1–T4）→ `standard-workflow-the-turn-part2.md`** |
| **UI 层：在 LibTV 界面里点哪里**（官方学院 11 课蒸馏：画布四模块 / 工作流与 AutoLink / Slash 预设 / 图片·视频·音频节点工具 / 生成器进阶）· **课 08–10（脚本节点批量产出 / 3D 导演台 / Seedance 与真人素材合规）** | **`libtv-academy.md`** 主册 · **续册 → `libtv-academy-part2.md`** |
| **这一趟要花多少积分 / 失败退不退 / 怎么把钱花在刀刃上** | **`libtv-billing.md`（R24：计费点清单 · 单价口径 · 退分四情形 · 并发预冻结 · 成本公式）** |
| **这条 prompt 会不会被拦 / 被拦了怎么改 / 关了声还会不会被审** | **`libtv-moderation.md`（R25：三侧红线带「被拦句 → 安全改写」· 内容违规与技术改造分开 · 静默降级识别）** |
| **并发开几个 / 卡住了怎么解 / 两个 run 冲突 / ask_human 能不能同批** | **`libtv-concurrency.md`（R26：节点级互斥 · 契约未暴露项清单 · 死锁五出口 · 两侧工具面映射表）** |
| **平台是不是更新了 / 有没有新接口 / 这次更新要不要改我的做法** | **`libtv-platform-watch.md`（R27：无 changelog → 三源快照 diff 法 · 四个新接口 · `project_info` 的 `connectionList` 边表 · 乐观锁 · `labels` 与白名单自查 · 1.5 公告五大功能对照 §十）** · **REA 差集索引 → `libtv-platform-watch-rea-index.md`** |
| **Agent 面板怎么操作浏览器 / FE 调用被拒怎么办** | **`libtv-realtime-and-fe-tools.md`（实时通道与 FE Tool RPC：`fe_tool_*` 四事件 · ack→执行→result 三段 · 30 s 默认超时 · **单活标签页模型**：另一窗口打开同画布时本窗口调用被拒并要求重试）** |
| **★ 哪些板块能交给平台 Agent"定稿"（剧本可交出去定稿；资产/分镜/故事板/声音**只取它的维度与列、不交定稿权**）** | **`agent-handoff-scope.md`** |
| 预算 / 证据链 / 可计算一致性 | `agent-autonomy.md` |

### 站 4 · 剧本（**此前只挂了 `script-craft.md` 一份**）

| 要决定什么 | 读哪册 |
|---|---|
| **★ 剧本的"谁写哪一段"（2026-09-22 用户定：我方定题材＋写大纲＋出初稿 → 平台 Agent 定稿 → 我方三项复核 → 入 Script V2）** | **`script-agent-handoff.md`** |
| 前提 / 命题 / 主控思想 | `direction-reasoning.md` · `direction-worked-example.md` |
| 情节骨架 / 结构模型 / 出招顺序 | `drama-plotcraft.md` · `drama-structure-models.md` |
| 冲突怎么动（四类冲突 / 出击点 / 危机-高潮-结果） | `drama-conflict-craft.md` |
| 人物弧光 / 对手规格 / 负面进展 | `drama-character-arc.md` |
| 台词（说情绪 / 说明性 / 旁白越界） | `drama-dialogue-craft.md` |
| 套路与变量控制 | `drama-tropes.md` |
| 按类型找参照 | `drama-genre-casebook.md` |
| **交付前的十五病** | `drama-script-diagnosis.md` |
| 剧集形态（集/季/单集/长篇） | `drama-series.md` · `drama-series-cn.md`（★ 平台剧本预设 §12：题材15/字段组5/结构8/热预设8） · `drama-anthology.md` · `drama-episode-structure.md` |
| 时长档位与折叠 | `drama-scaling.md` |
| 与 AIGC 的对接 | `drama-aigc-conversion.md` |
| **练** | `drama-mastery.md` |
| 写作方法融合 | `writing-methods.md` · `script-module.md` · `script-format.md` |

### 站 6 · 写【人物与环境】/【时间线】时（**此前全缺**）

| 要决定什么 | 读哪册 |
|---|---|
| 人物三层 / 表情下限 | `character-depth.md` |
| 生理活性 / 静息微动 | `character-realism.md` |
| 小传八字段 / 句架库 | `character-sheet.md` |
| 跨镜连续性 | `character-continuity.md` |
| **具名表情取词（96 条）** | `expression-library.md` |
| 表情解剖 / 节奏（起势·峰值·消退） | `expression-anatomy.md` · `expression-rhythm.md` |
| **表演（出戏成因 / 内在生活）** | `performance-craft.md` · `performance-vocabulary.md` |
| 皮肤与皱纹（换光位比改形容词有效） | `skin-realism.md` · `skin-realism-part2.md` · `skin-light-physics.md` |

### 站 6 · 写【光位与影调】时（**此前全缺**）

| 要决定什么 | 读哪册 |
|---|---|
| 光为什么这样（物理层） | `light-physics.md` |
| 光质怎么构造 | `light-quality-construction.md` |
| 打光的立场与顺序 | `lighting-philosophy.md` |
| 影调写实（写实缺陷层） | `tone-realism.md` |

### 站 6 · 写【运镜】时（**此前只挂了四条**）

| 要决定什么 | 读哪册 |
|---|---|
| 运镜库与族 | `camera-movement-library.md` |
| 运动控制 | `motion-control.md` |
| **受力反馈**（他要推动什么、推到什么程度） | `physical-feedback.md` |
| 载体痕迹（谁留下的） | `carrier-artifacts.md` |

### 站 6 · 写【统一提质层】时（**此前只挂了 `camera-package-library`**）

| 要决定什么 | 读哪册 |
|---|---|
| 包的速查 | `camera-package-quickref.md` |
| 扩展包 | `package-extended.md` |
| **胶片档与印片档** | `film-stock-matching.md` |
| 质感 / 颗粒 / 高光 / 印片 | `cinematic-look.md` |

### 站 6 · 写【后期特效】的调色时（**2026-09-19 补工位**）

| 要决定什么 | 读哪册 |
|---|---|
| **族与量级（选哪一族、推多少）** | `color-grading-styles.md` |
| 色彩理论 / 示波器 / LUT | `color-science.md` |
| **谁能进提示词**（分流表） | `color-pipeline.md` |
| 色彩承担叙事 | `color-narrative.md` |

### 站 5 · 资产（**此前缺规格册**）

| 要决定什么 | 读哪册 |
|---|---|
| **三类资产各自写什么** | `asset-prompt-spec.md` |
| **板子的背景与布光 / 像素预算 / 读图清单** | `asset-prompt-spec-part2.md` |
| 跨模型一致性 | `asset-consistency.md` · `asset-consistency-part2.md` |

### 站 7 / 交付前（**此前只有 `qa-failure-codes` 与 `production-ledger`**）

| 要检查什么 | 读哪册 |
|---|---|
| **验收标准** | `acceptance-check.md` |
| **复看轮次**（该看几遍、每遍看什么） | `review-passes.md` |
| 已踩过的坑 | `pitfalls.md` |
| **提示词运维（删比造安全）** | `prompt-ops.md` |
| AI 缺陷与脏点分诊 | `ai-artifact-control.md` |
| 工程参数（色空间 / 交付规格） | `post-production.md` |
| 反向取词法 | `reverse-prompt-method.md` |
| 全库速查 | `cheatsheet.md` · `director-system.md` · `lexicon-map.md` |

### 风格查阅（**49 册 style-\*：不逐册挂站，但要经入口**）

**统一入口**：`style-library-index.md`（挑风格）→ 详卡（`style-cards-*`）→ 定标（`style-cores-*`）→ 出处（`style-sources-*`）。
**站 3 必须经过这个入口**；**不许凭记忆写风格编号**（`governance-law.md` L5 引用优先律）。

> **★ 本节自身的纪律**：**它是路由表，不是内容**——每册的规则仍在原册；
> **若将来新增一册而没有加进本表，就等于没建**（`MEMORY.md`：**新增一册的第四件事，是在 `run-sheet.md` 给它一个入口**）。

<!-- knowledge-routes:v1 -->
| profile | kind | aliases | required_refs | reason |
|---|---|---|---|---|
| full_film | production_task | full_film;full;feature;whole_film;完整成片;全片 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/production-ledger.md;references/delivery-engineering.md | 完整生产任务需要从入口、治理、编译器到交付证据链的基线导航 |
| prompt_only | production_task | prompt_only;prompt-only;prompt only;prompt;仅提示词;只出提示词 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/prompt-ops.md | 只生成提示词包时仍需入口、治理、编译边界和提示词运维规则 |
| single_shot | production_task | single_shot;single-shot;single shot;one_shot;单镜头;单镜 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/shot-craft.md | 单镜头任务需要镜头规格与生产编译器的最小读取集合 |
| empty | shot_kind | empty;empty_shot;no_character;visual_only;空镜;空镜头;无角色 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/segmented-shot.md | 空镜/无角色镜头需读取分段镜头与生产编译器约束 |
| silent | shot_kind | silent;no_audio;mute;静默;静音;无声;无音 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/sound-craft.md;references/sound-narrative.md | 静默镜头需确认声音叙事与混音边界，即使不生成对白 |
| no_dialogue | contract_flag | no_dialogue;no-dialogue;无对白;无对话;silent_dialogue | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/prompt-ops.md | 无对白能力来自契约与提示词包，需读取编译器和提示词运维规则 |
| mirror | deliverable | mirror;镜像;source_replica;copy_reverse | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/delivery-engineering.md | 镜像交付只做结构忠实复制，仍需治理、编译器和交付证据规则 |
| rework | unsupported_task | rework;返工;revision;返修 | SKILL.md;references/governance-law.md;references/production-compiler.md;references/agent-autonomy.md;references/review-passes.md;references/pitfalls.md | 返工在当前正式编译器中未支持，只能作为未支持路由而非 full_film fallback |
<!-- /knowledge-routes -->

任务上下文工位：读 `context-reading.md`；全片完整工作流/全库导航在 `studio-workflow.md`；提示词工位按 `stage1-delivery-entry.md` → `craft-delivery-entry.md`；连续性/返工工位读 `offline-continuity-entry.md`；`legacy-feasibility-observations.md` 只作历史观察查阅，不当当前平台能力门槛。
