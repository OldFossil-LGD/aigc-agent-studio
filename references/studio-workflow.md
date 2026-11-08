---
name: aigc-agent-studio
description: AI 影视工作室，从点子一路跑到成片的自主流程（剧本→资产→分镜头脚本→投喂生成→剪辑合成→交付留证），人只做批准。Use when：做 AI 短片/AI短片/短片、拍短片、拍视频、跑到成片、自己投喂生成、视频生成工作流、剧本、分镜表、分镜头脚本、故事板（单镜黑白）、资产提示词、角色一致性、参考图一致、主体库、画布、LibTV、配音/口型/声音/配乐、剪辑/调色/成片/交付规格/去 AI 味、批量出图；画风含写实电影、描边/美漫/赛璐璐/卡通渲染、定格/像素/木刻/油画/水彩/剪纸/沙画/水墨；平台含 LibTV/Updream/即梦/SeeDream/可灵；时长 15 秒短片到 90–120 分钟长片均可。NOT for：单张图片或海报、纯音频、写作与数据分析。
metadata:
  agent_created: "true"
---

# AIGC 影视工作室 · **Agent 自主版**（**任意时长**）

> ★★ **反推/复刻模式入口（2026-10-11 新，先于编译器）**：任何“反推 / 复刻 / 蒸馏 / 盲测”先声明
> `content_reverse / copy_reverse / source_replica / rule_distill / production_build`，并记录
> `original_readback / copy_readback / public_media / text_only / none`。
> **没有原项目可读权限，禁止写 `source_replica`；副本只能写副本级。**
> 权威入口 → `references/reverse-fidelity-contract.md`；盲测协议 → `references/blind-reverse-runbook.md`；
> claim ledger 只读门禁 → `scripts/reverse_claim_lint.py`；盲测门禁 → `scripts/blind_test_gate.py`。旧 `source-fidelity-mode.md` 与
> `production-compiler.md` 继续有效，但分别降级为“源级细则”和“执行器”。
>
> ★★ **生产化主入口（2026-10-08 新）**：简单输入先走 `scripts/compile_production.py`，产物是 `production_contract` → `asset_graph_plan` → `shot_graph_plan` → `prompt_packages` → `platform_execution_plan` → `capability_gate` → `libtv_command_plan`。此编译器只生成计划与提示词，不点火。用法见 `references/production-compiler.md`；源级复刻必须配 `scripts/source_fidelity_lint.py`，实施标准见 `references/source-fidelity-mode.md`；反推类任务缺作品画像即拒编（`scripts/work_profile.py` → `WORK_PROFILE_MISSING`）；成片交付前必过产物门 `scripts/film_qc_gate.py`（黑帧 / 静音 / 时长 / 画幅 / fps / 切点）。离线资产版本、局部返工与审片回执绑定 → `references/offline-continuity-entry.md`（绑定通过不代表媒体质量已审）。自动化生产路线图见 `docs/plans/2026-10-12-production-automation-roadmap.md`。旧的 `references/` 继续作为规则查询层，不再单独充当生产交付。
>
> ★★ **只要提示词的交付入口（2026-10-22 新，阶段一）**：用户要的是**提示词本身**（"只要提示词"、"给我一条空镜的提示词"）而不是成片/画布/媒体时，走 `scripts/compile_intent_delivery.py`：Agent 把用户原话理解成一份 `intent-handoff/v1` 交接文档（**用户不手填 JSON**），脚本负责结构化交接、校验、编译正本、默认派生 `<out>/13_Draft_Prompt.md` 草稿；只有当前任务、选读原文和实际产物的审阅证据齐备且独立验收通过，才派生 `<out>/13_Final_Prompt.md`，并用 `scripts/verify_delivery_semantics.py` 独立复核约束是否真的兑现（**不信自报状态**：只拿权威输入与实际交付正文判定，合法同义表达放行，篡改平视/删留白/改旁白/改结构/改来源一律 FAIL）。`prompt_only` 停在 Prompt Package：**不产 05/08 执行计划、不建画布、不生成媒体、不点火**。**入口与边界 → `references/stage1-delivery-entry.md`**（含产物表、停止点、反例表与包内缺失规范的**可核验恢复指针**）；样例 `samples/papercut_empty_shot_intent.json`；用例 `tests/test_intent_delivery.py`。工艺消费与本镜时间作用域短入口 → `references/craft-delivery-entry.md`。 包内历史快照仅作溯源（非活动权威）：`references/unified-baseline/`；历史样例目录 `references/unified-baseline/samples/`：`B1_资产_角色设定板.md`、`B2_故事板_黑白三路径.md`、`B3_视频_短片单镜_15秒.md`、`B4_视频_中片段落版_30秒.md`、`B5_视频_长片分段_5分钟.md`、`B6_声音_三层声音表.md`、`B7_合成_时间线与字幕.md`。
>
> 🟢 **接到活 → `references/run-sheet.md`（统一状态机 + 十站执行清单）** · **分册路由 → `references/run-sheet-part2.md`** · **续三（最小模板与禁令）→ `references/run-sheet-part3.md`** · **续四（路由表后半）→ `references/run-sheet-part4.md`** · **板块内思考 → `references/thinking-pipeline.md`**。**统一基准**：状态机 `outputs/统一基准/01_统一状态机与交付契约.md` · 图语法 `02_图语法_节点边分组参数.md` · 规模预算 `03_规模预算与题材时长档位.md` · 三作画像 `04_三作画像与原skill审计.md` · 世界状态 `05_世界状态与变更传播.md` · 证据分层 `claim_ledger.jsonl`。**B 路提示词编译**：`10_输入到计划编译器规范.md` · `11_提示词包与五类模板.md` · `12_创作工艺路由_人物动作灯光风格声音.md` · `13_提示词门禁与失败诊断.md` · `14_语言口型字幕与本地化.md` · 样例 `samples/B1～B7`。**C 路平台执行**：`20_LibTV图构建与分组规范.md` · `21_模型成本并发与恢复规范.md` · `22_结构回读与媒体验收规范.md` · `23_三作与合成场景回归测试.md` · 只读门禁 `graph_plan_lint.py`、`three_work_regression.py`、`numbering.py`、`source_fidelity_lint.py`；**源级复刻模式 → `references/source-fidelity-mode.md`**。**离线生成包门禁**：`render_offline_prompts.py` → `offline_package_lint.py` + `references/offline-generation-gate-ledger.md`。本文件管入口、为什么与最小状态链；长规则只引用，不复制。
>
> **★ 本 skill 是"Agent 自主版"（2026-09-20 从 `aigc-film-studio` 移植改造）**：**旧版终点是"提示词"**（因为投喂由人做）；**本版终点是"成片"**——站 6 之后补了 **5.5 参考闭环 · 6.5 投喂与生成 · 6.6 剪辑与合成 · 6.7 交付与证据**。**三条自主纪律（预算 · 证据链 · 可计算一致性）→ `references/agent-autonomy.md`**；**LibTV 画布/节点/接口/成本地图 → `references/libtv-canvas-nodes.md`** · **跨 Agent 通信协议（让它把答案写进「我能读的容器」）→ `references/libtv-agent-protocol.md`** · **★ Skill key 构造与平台协议闸门（技能命名空间 / 审核四态 / third_asset 合规 / agreement 只读）→ `references/libtv-web-api-shapes.md` §八–§九**；**用户向操作手册 → `references/start-here.md` · 续册 `references/start-here-part2.md`**。

**最小状态链**：`intake → intent_locked → feasibility_passed → brief_locked → script_draft → script_locked → style_locked → assets_draft → assets_locked → storyboard_ready → shot_contract_ready → graph_plan_ready → preflight_passed → generation_authorized → generated → reviewed → assembled → delivered → archived`。`prompt_only` 可停在 `shot_contract_ready` / `graph_plan_ready`；失败按责任层回退，不一律重试。**三步交付仍固定为剧本 → 资产 → 分镜**，每镜两个板块：故事板 + 视频提示词；剧本按 M1–M12 与 `script-format.md` 交付并跑 `script_lint.py`。平台 Agent 只能交接“验收靠人眼”的定稿权，机检维度不交定稿权（→ `references/agent-handoff-scope.md`）。

> **正式交付的考虑与留证门**：所有创作/审阅终点都先按 `references/delivery-review.md` 考虑全库领域、选读相关原文与例外，并把关键判断落实到当前产物。`references/knowledge-catalog.json` 是全库发现清单，不是全读或理解证明。缺证据只能标草稿或未解；工程 PASS 不等于创作质量已证实，亦不授权生成。用户仍用自然语言，无需手填 JSON。

## 目录

**本文件结构**：§0 定律 → 前置门（可行性）→ 前置门二（一页 brief）→ 总纲 → 第一步 剧本 → 第二步 资产 → 第三步 分镜头脚本 → 写之前的强制推演 → 参考资料索引 → 来源与署名。

---

## §0 · 先看这两条定律（先于一切，含本文件自己的改动）

**L1** → `references/governance-law.md` 的任务闭包全量检阅；具体接口见 `references/context-reading.md`。
**L2** → `references/governance-law.md` 的整合铁律：功能保留、疑项保留、单一权威，定义只在该册。
→ `references/governance-law.md`（**全库唯一定义处**，其他文件只引用、不复述） · **整合与拆卷的操作细则（加装/写不下时读）→ `references/governance-law-part2.md`** · **交付与改库纪律 → `references/governance-law-part3.md`**

## 前置门：可行性（写剧本之前，不可跳）

**可行性必须按当前模型、输入方式与实际回读判断。** 原一键成片及全平台能力观察保留为未验证历史，见 `references/legacy-feasibility-observations.md`，不作为当前能力保证。

- **高风险清单仍保留**：手指、全身走跑、口型、多人交互、剧烈动作、液体布料、画内文字、快速运镜；按当前模型逐项核可行性，未知先标待核，不凭历史失败率设全平台禁令。
- **起步选题建议**：自然、抽象、概念、风格化、低复杂度主体与固定/慢机位可作候选；是否适用于本任务仍需核需求与当前能力，不能当普遍成功保证。
- **预算与可用率**：用当前报价与可比回执计算；无当前证据时只列明示估计，不把历史可用率、抽卡次数或后期占比锁成用户决定。旧数字完整保留在 `references/legacy-feasibility-observations.md`。

→ 写剧本前先过 `references/feasibility.md`（可行性三问 + 题材优先序 + "AI 短片感"九条症状）。

## 前置门二：一页 brief（写剧本之前，与可行性门并列）

**改剧本的成本远低于改分镜——片越短越是如此，但无论多长，这一页都要先写。** 动笔前先写**一页**说清五件事，**没写清就不写剧本**：

| 项 | 写什么 | 不合格的例子 |
|---|---|---|
| **1 时长与画幅** | 精确秒数 + 竖屏 / 横屏 | "大概一分钟" |
| **2 一句话主旨** | 一句**可拍的**话（不是情绪词） | "关于孤独" |
| **3 交付物清单** | 剧本？资产？分镜？全部？ | 没说要做几步 |
| **4 难点预判** | 按可行性门扫一遍，**列出本题材里最难的 1–2 个镜头**，并写明"打算怎么绕" | 没扫，做到分镜才发现拍不出来 |
| **5 美学风格** | **一个风格编号**（如 `B10 王家卫式` / `E03 敦煌壁画`）+ 量级系（写实 / 描边 / 第三系） | 不写，或只写"电影感""高级感" · **★ 未声明风格 → 默认走写实系（量级路由的默认答案；要风格化必须显式声明）** |

**第 5 项为什么必须在这里定**：风格决定**资产的量级与材质**——先出资产再定风格，资产全部要重出。**没想好风格就先去 `references/style-library.md` 的「按氛围反查」挑，不许带着"待定"进第二步。**

**为什么单独设这一页**：brief 是**方案层**，剧本是**执行层**。混在一起写，会出现"剧本写得很漂亮、但根本没考虑能不能拍"——这正是可行性门要拦的事，而**拦在 brief 层比拦在剧本层便宜得多**。

## 总纲：提示词是工程型指令，不是文案型形容

写给模型的可执行约束，不是给读者看的散文。"电影感 / 震撼 / 精致 / 4K"一律换成**具体器材、具体动作、具体材质**。

## 第一步：剧本（一份完整文档，不拆）

七件按序装订：主旨 + Logline / 一句话梗概 / 人物（外在目标·内在需求·致命缺陷，≤3 人；**怎么推、怎么落进提示词 → `references/character-sheet.md`**）/ 节拍表（精确到秒）/ 无对白版 / 分场剧本 / 台词清单（逐字锁定，通常 ≤6 句）。**★ 剧本版式一律按 `references/script-format.md`（好莱坞标准六大元素 + 特殊情形十种 + 中文适配档 + 空模板 + 十条自查）**——不按它写 = 交付即读作业余。

**为 AI 而写的三条**：把叙事交给**旁白**而不是"演技戏"；单主体优先，需要两人就**正反打分开做**；镜头按**短**写（真实有效素材只有 1–2 秒，节奏靠剪辑不靠长镜头）。
**★ 动笔前先走剧作层两步（2026-09-16 补）**：① **量容量**——时长 → 拍数 / 反转数 / 场数 / 台词字数上限（**先量再写**，超了要换模型，不是删拍）→ `references/drama-scaling.md`；② **选结构模型**——十六种模型选一个（能直给 30–60 秒的只有四个）→ `references/drama-structure-models.md`。
剧本写完 → `references/drama-script-diagnosis.md` 过十五病。**人物在剧作层的设计（三维 / 编排 / 对立统一 / 弧光 / 对手七条规格 / **负面进展四层**）→ `references/drama-character-arc.md`；**冲突怎么动（四类冲突 / 过渡 / 出击点 / 危机—高潮—结果 / 动机心理学工具箱）→ `references/drama-conflict-craft.md`**；台词与旁白写法（**对白＝行动 / 四类瑕疵 / 四种句法 / 遮名测试 / 旁白三距离**）→ `references/drama-dialogue-craft.md`；题材的引擎与可复现原型场景 → `references/drama-genre-casebook.md`；动笔写提示词之前必读 `references/drama-aigc-conversion.md`（把剧作概念翻成"哪一行、什么句子"）。入口与边界 → `references/drama-library.md`。**★ 剧本的交付契约（十二模块 M1–M12 · 逐块接口 / 判据 / 模板 / L0–L2 阶梯）→ `references/script-module.md`；交付前跑 `scripts/script_lint.py`（缺模块即 FAIL）。★ 写完四问还要答第五问"凭什么值得看"→ `references/drama-plotcraft.md`（创意十问 · **第 ⑥⑦⑨⑩ 问是硬门槛**）+ `references/drama-tropes.md`（先认一条已验套路再变形）。** **★ 剧本的「谁写哪一段」（2026-09-22 用户定：我方定题材＋写大纲＋出初稿 → 平台 Agent 定稿 → 我方三项复核〔时长/人物生理/声音〕→ 入 Script V2）→ `references/script-agent-handoff.md`。**

**✅ 做完的判据（逐条答"是"才进第二步）**：

- [ ] 主旨能用一句话说完，且不是"情绪词"（不是"关于孤独"，而是"一个人以为没人看见他，其实一直有人"）
- [ ] 节拍表每一拍都有秒数，**秒数总和 = 总时长，无空档、无重叠**
- [ ] 无对白版能独立看懂（不靠台词也成立）
- [ ] 台词逐字锁定、通常 ≤6 句；**每句都能在这句所在镜的秒数里说完**（按中文 3.5–5 字/秒算：字数 ÷ 5 ≤ 镜时长）
- [ ] 人物 ≤3 人，每人有"外在目标 / 内在需求 / 致命缺陷"三项，且**过了档案四问**（①–④ 一个字不进提示词 · 前史只有一行且解释了某处痕迹 · 痕迹写位置不写"有" · **遮住档案只看提示词能推出经历** → `character-sheet.md` §7）

→ `references/script-craft.md`

## 第二步：资产（角色 / 道具 / 场景设定图）

**⚠️ 风格先行（未定风格不许出资产）**：资产提示词里的**量级句、材质词、色彩占比全部由风格决定**——先出图再定风格＝全部重出。进这一步之前先答三问：① 风格编号是哪个（`references/style-library.md`）？② 它属**哪个量级系**（写实 / 描边 / **第三系工艺渲染**）？③ 全片不许变的三条**一致性锚点**是什么？**三问答不出就回去 `style-library.md` §三 走选取流程。**

剧本定稿后才出资产——**资产是分镜的图纸**。三类：**场景**（多角度设定板）/ **角色**（一张设定板）/ **道具**（一件一张）；**出图走的是五步**，多出的一步是「光源」（不是一类资产，但必须先定）与「照片」（= 成片定调照，见 `start-here.md` 3.2）。
出图顺序：**场景 → 光源（先定光源）→ 道具 → 角色 → 照片**。
**一致性铁律**：**一张参考图只承担一个任务**（身份图只给脸、风格图只给风格）；**最需精准的参考图放最前**；**多视图按对象分**——**人物多视图只作设计稿、不作参考素材**（拼成一张宫格会被识别成多个主体、加剧 ID 漂移）；**无生命道具的多角度拼图允许且应当**（无面部身份风险，多角度只增信息）；人物作参考素材时用「**一张干净正面 + 一张全身**」两张独立文件（三次独立印证：火山方舟官方 / drama-skills / seedance-video-script）。
**★ 人物设定的固定要求（用户 2026-09-15 定，长期有效）**：写任何**角色设定 / 人物设定**，**一律按"可执行的具名信号"写，不写形容词**——① **每个角色给三个"偏离平均的点"**（**一处面部结构 + 一处身体或发型 + 一处行为痕迹**；**面部结构只许一处**；幅度用相对量：`左眼比右眼窄一线，约两毫米`）；② **表情与体态先取名字再落笔**（具名表情 → `expression-library.md` 96 条；肌肉动作 → `character-depth.md` §五；姿态名 → `lexicon-map.md` §3）；③ **★ 数字只用来对表，不进提示词**（三类语料的区分 → `lexicon-map.md` §0）。
→ 跨模型一致性机制与参考素材的双层角色：`references/asset-consistency.md`；**★ 三类资产各自写什么、字段下游谁继承、资产从剧本哪一行派生 → `references/asset-prompt-spec.md`**；平台落地（**Updream / LibTV 双平台**）与【批量任务】格式：`references/updream-workflow.md` · 续册 `references/updream-workflow-part2.md` · 续册 `references/asset-consistency-part2.md`；**资产板的背景与布光 / 三视图像素预算 / 读图清单 → `references/asset-prompt-spec-part2.md`**

**✅ 做完的判据（逐条答"是"才进第三步）**：

- [ ] 每个会被复用的实体（**在 2 个以上镜头/场景出现**）都已出图并锁定；只出现一次的不必出图
- [ ] 角色 / 场景 / 道具三类齐全；**一件道具一张**；**状态有变化的角色与道具都单独一版**（湿透 / 破损 / 换装 / 受伤 / 沾尘 —— 别指望模型自己保持"变了的状态"，它会自愈回滚）
- [ ] 每张参考图都有明确**用途**（身份 / 造型状态 / 地理 / 构图 / 尺度 / 效果 / 起始帧 / 结束帧 / 风格），一张图不兼两个用途
- [ ] **资产图自身合格**：纯中性灰底 · 柔光近乎无影 · 场景是 3/4 角度能见两面墙（先看光再看像不像）
- [ ] **人物参考里只有一张有效脸**——拼表时全身面板的脸已抹掉
- [ ] **有正反打 / 机位翻转的场，空间已出正反两个机位**；180° 自检问句答得出来
- [ ] **已做过兼容性动测**：角色 × 场景跑过**一组**测试镜（跨角度 / 跨景别 / 真实场次光 / 同框搭档，重复性 **5/5**）并成立（**静态好看不算数**）；至少留 2 个 finalist；道具豁免（→ `production-ledger.md` §二、§三）
- [ ] **参考图未就绪时不许写最终分镜**——缺图就停下，列出缺哪张、给谁用；**不许静默降级为文生视频**
- [ ] 参照全片光线基准出的那张（通常是光源道具 / 场景）是最先出的

## 第三步：分镜头脚本（每镜两个板块）

**板块一 · 故事板**——**三条路径先选再写**（A 原生组图 / B 原生 Storyboard / C 一镜一请求）；只锁结构（景别 / 机位 / 构图 / 人物位置 / 明暗结构 / 动作瞬间），**不写色板与色温**。
★ **"绝不拼版"已拆两条**：禁**一画布多格**（要裁切才能拿到单镜），**放行"一次请求出 N 张独立文件"**（**image2 多图批量（`n`=8/4，官方用例明写 storyboards）** / 即梦 / 可灵组图、Runway Story Panels 的原生能力）。含**输出模式声明 · 失败处方表 · 参数块与回写位**（可迭代三件套）→ `references/storyboard-frame.md` · 平台规格与来源 → `references/storyboard-platforms.md`

**板块二 · 视频提示词**——一段整合提示词，层序固定、不拆（**资产提示词不用这套结构**，它走五段式协议 → `references/block-playbook-asset.md`）：

> **先选模式（这一步决定后面怎么写）**：**单机位镜**——一条只出一个机位、一个运镜（≤10 秒），**要"缓推"以外的变化就得拆镜**；**分段镜**——**一条 15 秒（或 30 秒）里装 3 个景别 / 机位**，**按「段落 / 组合」写（段落A / 段落B / 段落C），⛔不写「镜几」**——**段内景别与构图按时间线发生改动**，**这才是"一镜多景别"的正确写法**（用单机位模板写多景别，出来必然是缓推——模板显式排除了其他运镜）→ `references/segmented-shot.md`。
> 判路（同场景同光 → 分段镜；越轴 / 跨地点 / 对白口型 / 周期动作 → 拆镜）与试错成本算术，见该文件第一节。
> **★ 镜头按顺序写，不写秒数**（时间由模型自己分配）；**只有首行总时长保留**。

> ★★ **两条路都要保留，先选路再动笔（2026-09-15 定）**
>
> | | **分镜版**（＝单机位镜） | **段落版**（＝分段镜） |
> |---|---|---|
> | **编号** | **用镜号**（`镜1 / 镜2 / 镜3`）——**这里无害**：一镜本来就是一整条生成，「镜2」不会被读成「要在镜内硬切」 | **不写镜号**，用「段落 / 组合」+ **换景词**（`画面变为` / `下一个画面是`）→ `segmented-shot.md` §七 |
> | **写前必过** | **★ 拆镜开关**：画框换过？轴线换过？**动作超过一个**？时长超了？**命中就拆出一个新镜头** → `shot-craft.md` | **★ 段内画面数下限**：每段 **≥2 个画面**，整条画面数 ≥ 段数 + 1 |
> | **它擅长** | 越轴 / 跨地点 / 对白口型 / 周期动作（走路·奔跑）/ **每镜都要独立重跑候选** | 同场景 · 同光 · 同主体 · 动作简单 · **想省生成次数** |
> | **返工成本** | **低**——出问题只废一镜 | **高**——一条废了整段重来 |
>
> **★ 拿不准就用分镜版**（可控性高）。**「镜N」的危险只在「一次生成」里**——一旦一镜一生成，镜号就不再有害；这正是两条路都要留的理由。
> **两版的板块是同一套 12 块、同一顺序**，差别只有两处：单镜有独立【构图】块（段落版并入时间线）；段落版多一块【全局约束】。
> **★ 两版都必须写满人物表演**——**表情动作的下限**（至少把「一处」写透四层：外观 / 体态 / 行为 / 矛盾，外加**眼的落点**与**呼吸**）→ `character-depth.md`。

```
【全片通用（写一次，标"每一镜逐字复用、不改字"）】
1 后期特效  大气透视 / 体积感 / 高光滚降 / 调色方向 / 颗粒
2 统一提质层  器材 / 痕迹 / 运动（逐字附上 → quality-layer.md；**只写型号与规格，观感形容词归第 1 块**）
3 风险移除（**正面状态句**）｜禁止出现（**画面内容类名词清单**）  ——成像层的禁用归第 2 块，两块不许写同一件事
────── 以上三块全片通用；以下为本镜专属 ──────
4 本镜目的  这镜在推进什么（三选一：改变情绪 / 推进动作 / 施加压力；**判据＝"这一镜结束时有什么变了"**——答不出就删掉这一镜，别靠"好看"留着）
5 镜头规格  画幅 / 焦段 / 光圈 / 机位高度与视角 / 机位距离
6 构图  构图法 + 主体落点 + 引导线 + 负空间 + 前景
7 人物与环境  身份锚点逐字复用 + 场景陈设 + 容斥句（人物三层与物理反馈落笔并进本块）
8 光位与影调  写实缺陷层（光源动机、光比、衰减、人物光影块；**皮肤与高光点归本块，第 7 块不写** → `block-spec.md` §三·补 #3）
9 时间线  起始 / 主动作 / 反应与呼吸 / 定格（**动作相位，不写秒数**；⛔ `触发 / 接触 / 落定` 是段间词，单镜与段内同样禁写 → `shot-craft.md` 作用域条）
10 运镜（＝老叫法"摄影机"块，**落笔块名统一写【运镜】——门禁按"运镜"匹配**）  观察点 + 一个运动 + 速度缓动 + 锁死项 + 按族排除 + 结尾落点（选型 → camera-movement-library.md）
11 声音  无配乐、只留现场音 + 显式列出关键环境音
12 过渡压力 · 下一镜怎么接（动作匹配点 / 视线落点 / 声音桥 / 景别落差）
```
> 写作顺序细则 → `shot-craft.md`（**权威**）· 分段镜 → `segmented-shot.md` · `segmented-shot-part2.md` §九 · 逐块思考 → `block-playbook.md`。**块数以 `shot-craft.md` 模板为准（现行 12 块）**；`block-playbook.md` 的 15 块是**思考清单**（把人物表演 / 物理反馈 / 结尾留白拆出来逼你想过一遍），**不是写作顺序**——落笔时并进上表第 7、9 块。

**动笔前必须先过三道门（不可跳）**：
1. **可行性门**（剧本阶段）→ `references/feasibility.md`：镜头里必须出现手 / 走路 / 多人 / 剧烈动作 / 画面文字超过 3 个，就改结构。
2. **双向钢人论证** → `references/steelman-protocol.md`：正题 → 反题 → 交锋 → 合成留痕。
3. **动作类镜头先过决策树** → `references/motion-control.md`：**走路 / 奔跑 / 负重这类周期动作，禁止用纯文字提示词求解**；按「参考视频驱动 → 首尾帧单步 → 构图规避 → 实拍兜底」选路径。**★ 人不动 / 写不出位移 → `references/actor-movement.md`**（四个根因诊断 · **动作可生成分级 A–D** · **位移四种写法 ①跨镜→②机位代走→③首尾帧→④镜内连续** · 一步≈0.5 秒的换算 · 症状修法八条 · **平台六项实测**）。

**★ 开生成前还有一道放行门（2026-09-13 补）**：**这一场涉及的每个资产都必须读到 `locked`**（draft→locked 需过战斗矩阵：跨角度 / 跨景别 / **真实场次光** / **同框搭档二人镜**，重复性 **5/5**）；有一个是 draft 就整场不开工。逐镜生成时记**台账**（每次一行）；**一镜超过 8 次仍不过 → 改结构（拆镜 / 换机位 / 换景别），不是换词，更不许"再抽最后一次"**。→ `references/production-ledger.md`

**三条硬纪律**：① **要表情就给近景**；② **情绪词必须翻译成形变**；③ **先出故事板定构图明暗，再照它写视频提示词**，两者人物位置与构图必须一致。

> ⚠️ **故事板不能直接当图生视频的首帧**——灰度输入会把整片锁死在单色（实测翻车）。三条正确用法见 `storyboard-frame.md` 第十节。

**✅ 做完的判据（逐条答"是"才交付）**

> ⚠️ 判据分**静态**与**动态**两类。**静态全过 ≠ 能交付**——反复出现的失败模式正是"照片过关、视频测试淘汰"。动态类必须按 `review-passes.md` 实跑一遍。

**静态类（看画面/读文档就能查）**：

- [ ] 每镜都有**时间戳**，且**累加 = 总时长，无空档、无重叠**（这条每次都要脚本或手算校验）
- [ ] 每个板块二的提示词里都有：**声音行**（无配乐 + 显式列出关键环境音）、**结尾留白**、**风险移除**
- [ ] **★ 参照与校准做过没有**（2026-09-15 补 · 可达性审计抓出的缺口）：**① 取参照**——按风格编号翻对应的 `style-sources-*.md`（8 册，全库 247 条），**截过 ≥3 帧、且来自 ≥3 件不同作品**；**② 判偏**——先读 `style-cards-scale.md`（**怎么量 · 容差表**），再翻对应的 `style-cards-*.md`（7 册），**先量参考帧、再量你出的图，把两组数填进「参照 / 生成」**；**按容差表判**（色相 ±12° · 饱和 ±25% · 明度与对比 ±15%），**超了就先回去改风格层，再写块**。
- [ ] **★「调色方向」这一行走过三查**（2026-09-15 补，**这是最容易漏的一条**）：**① 认族**——`color-grading-styles.md` 十四族里这是哪一族（辨识要点对得上吗）· **② 查科学**——`color-science.md` 的 LUT / 白平衡 / 肤色线 · **③ 查警戒**——`color-narrative.md` 的青橙陷阱（**"一听到电影感就给青橙"**）与色彩弧线；**④ 与印片同向**——调色写"高调低对比"就不能配 2383（→ `film-stock-matching.md`）；**⑤ 三个症状查管线**——偏色 / 过饱和 / 灰暗**各有成因与可验证判据**（→ `color-pipeline.md` §6：**偏色查中性物是否同向偏 · 过饱和看高饱和区有没有死色块 · 灰暗看直方图两端**）。
- [ ] **瑕疵类**已从"不要…"改成**肯定状态句**；**动作类**已写完**同族排除**（写了推镜就排除拉/摇/移/环绕/变焦）；**内容类别否定**（"不要像游戏""不要廉价特效"）已改写成"该拍什么"——**三类方向各异，都要查**（→ `quality-layer.md` 第四节 1a / 1b / 1c）
- [ ] 每镜写明了**情绪目的**（这镜在推进什么）与**进入下一镜的过渡压力**
- [ ] **若这一条是分段镜**：**先算 `总时长 ÷ 段数` ≥ 2 秒**（**< 2 秒直接砍段数**——5 秒 5 段＝每段 1 秒＝整条看不懂）·
      **按「段落 / 组合」写、⛔不写「镜几」也不写秒数** · **共用块写一次、段内变化块写进时间线** ·
      **锚点句逐字复述到每一段**（无近义词替换）· 写死"恰好 N 个段落 N-1 个切换点" · 全程不变项与排除项**写在段落之外** ·
      段内已排除同族运镜 · 末段在落定处收住 · **排镜表跑过 `shotlist_lint.py --mode gen` 且无 FAIL**（→ `segmented-shot.md` §四）
- [ ] **段内不借切镜词汇**：**段内的状态推进写"他先…；随后…；最后…"，绝不写"准备 / 接触 / 落定 / 起始 / 触发"**——那些是**段与段之间**的词，写进单段会被模型读成"这是三个镜头"（→ `segmented-shot.md` §三）· **段首景别只描述起始帧**，段内若真发生景别量级变化必须写进时间线 · **景别行点名了画框边界**（❌`中近景——手停在枪套上` → ✅`中近景——帽檐横切过面部上三分之一，画面下缘收进枪套下半截`；**景别由画框装了什么决定，不由事件多重要决定** → `sequence-craft.md` §8.1b）
- [ ] 每镜的运动方向写明（左到右 / 右到左 / 朝镜头 / 离镜头），并注明**维持轴线还是有意打破**
- [ ] 板块一与板块二的**人物位置与构图完全一致** · 需要表情的镜头**脸在画面里够大**（近景 / 中近景）
- [ ] 动作类镜头**走完了 `motion-control.md` 的决策树**，不是靠文字硬解
- [ ] 提示词块**纯净**：块内没有注释、没有"（改成你的…）"、没有元说明（**尤其**"另注：""注：""*可选*"这类思考残留——块内一切都会被当提示词执行）
- [ ] **空话词与变体已清零**：`电影感` / `电影质感` / `大片感` / `细腻` / `高级感` / `震撼` / `唯美` 全部换成了可测约束；**划掉全部形容词后，剩下应是名词与动词**（→ `prompt-ops.md` 空话词黑名单）· **★ 且"脏点"已分诊**：**放大到 200% 看纯色区 / 背景 / 皮肤大面**——**① 采样型（渐变台阶/彩噪）与 ② 分辨率型（重复平铺/多头手）是参数与尺寸的事，改提示词没用；③ 信息不足型（最平的那块最脏）与 ④ 风格外溢型（不该有风格的金属水面也有画味）才在提示词层治**（→ `ai-artifact-control.md` §五·补二）
- [ ] **无冗余双语**：只给中文；没有并列的 English 版本（除非用户明确要）
- [ ] 交付前过了 10 项自查（`steelman-protocol.md` 第 5 步）
- [ ] **交付前跑过现实逻辑九轴**（→ `real-world-logic.md`）：它管的不是某一层，是**各层之间互相推得出吗**——光与影是否同向 · 人体重心与可达范围 · 空间地理与动线 · 因果链 · 时间与动作量的算术 · 材质与守恒 · 生理常识 · 接触支撑 · 声音的因果。**每层单看都对、合起来打架，就栽在这里**；门禁已机检其中三条（轴一光源与影子矛盾 · 轴四二级动作缺因 · 轴五镜内位移超限）。
- [ ] **两条路的写法都对号**：**分镜版**已逐镜过「**拆镜开关**」——时间线里**只要有 ≥2 级景别变化 / 轴线或机位改变 / 两个各自完整的动作 / 内容超过 2–3 秒**，**就必须拆出一个新镜头**（不许用「他先…；随后…；最后…」把装不下的内容压进同一个镜）；**段落版**每段 **≥2 个画面**、换画面用**换景词**（⛔ 不用「切到 / 转到 / 镜头N」）。→ `shot-craft.md` · `segmented-shot.md` §七
- [ ] **人物表演过了下限**：每镜/每画面至少把「一处」写透四层（外观 / 体态 / 行为 / 矛盾），并有**眼的落点**与**呼吸**（→ `character-depth.md`）
- [ ] **人物真实性过了五问**：**个体化三点**（面部结构**只许一处**）· 不对称用**相对量 + 参照物**且**方向锁进身份锚** · **生理活性**至少两样且**不是恒定节律** · **静息微动写在人物层**（不是摄影机层）· 觉得"看着怪"时**先查跨通道一致性、再加细节**（→ `character-realism.md` §八）
**动态类（必须实跑一遍，逐条按 `review-passes.md` 审）**：

- [ ] **相机轨迹**能用物理动词说出完整路径（说不出 = 回去重看那个切点）
- [ ] **接触点**能解释位置与重量（手碰道具、脚下落地这些帧有没有失去物理关系）
- [ ] **脸部三区同拍**：嘴+下颌 / 颈喉 / 眼眉在同一个拍上一起动，且有准备→峰值→释放（脸太小 → 标"不可判定"，**不许判过**）
- [ ] **编舞三时刻**：Entry 从合理平衡起手 / Contact 不穿模 / Recovery 没重置（切点若落在 contact 上，重播前后各一拍）
- [ ] **世界连贯**：地标、透视、光、背景运动逻辑连通（冻结最忙的一帧问基本空间问题）
- [ ] 证据不足的一律标**不可判定**，不得因为"看不出毛病"就算通过

## 写之前的强制推演：双向钢人论证

四步：**正题**（思路 + 依据哪条原理/实测）→ **反题**（站在模型那边写最强的失败论证，每条必须拿本提示词的具体句子当证据）→ **交锋**（每条反对意见配一个"改哪句/加什么/删什么"的修法，冲突写明取舍）→ **合成与留痕**（列三到五处关键改动 + "仍可能失败在哪、先改哪个变量"）。

三条纪律：**反对意见写不到具体句子就等于没想**；**改动要有账**；**推演可以长，成品必须干净**。

> **交付规范与"改动纪律 / 收尾自检"已按职责移入 `governance-law-part2.md`「交付与改库纪律」一节**——**那一节回答"交付前必须做什么、改这个库时必须做什么"**。

## 参考资料索引（要做 X → 读 Y）

| **🟢 第一次用，先读这个** |  |
| **第一次用 / 不知道从哪开始 / 忘了怎么操作**（给用户看） | **`references/start-here.md`**（说什么 → 看什么 → 什么时候"继续"）· **`references/acceptance-check.md`**（**给你自己勾的验收清单**：勾不满 6 条就返工；附「什么时候该说哪句话」对照表）· **LibTV media hash 同层统计 → `references/libtv-media-hash-cross.md`；三作分册 → `references/libtv-media-hash-w1.md` · `references/libtv-media-hash-w2.md` · `references/libtv-media-hash-w3.md`** |
| **★★ 接到活先读（Agent 自主版十站执行清单）**：先判档 · **站 5.5 参考闭环（硬门禁）** · 站 6.5 投喂与生成 · 站 6.6 剪辑与合成 · 站 6.7 交付与证据 · 每镜强制四问 · 交付前三道自检 · 三条禁令 | **`references/run-sheet.md`** |
| **★★ LibTV 画布与节点全书**：六种节点 · 画布操作（写操作必带幂等键与 revision）· **Agent 排他（active run 持单写者锁）** · Script V2 与导演台 · 时间线与导出契约 · **成本地图（按动作计费：生成、合成、剪辑、音频编辑、导出）** · 陷阱清单 | **`references/libtv-canvas-nodes.md`** · **★ 平台官方答疑全文（一手源 · 含 12 个能力名与对账表）→ `references/libtv-official-qa.md`** · **续册二（R2–R5）→ `references/libtv-official-qa-part2.md`** · **续册三（R6–R10 + 总问）→ `references/libtv-official-qa-part3.md`** · **★ 模型参数字典（MCP 实测确证 · 含探测三步法）→ `references/libtv-model-params.md` · `references/libtv-model-params-part2.md`** · **模型目录（全量快照 · 选型与核对 · ★ 服务端下发的 9 模态 / 96 模型清单与 17 条 slash 预设的实际参数）→ `references/libtv-model-catalog.md`（★ 素材面板 11 风格模型 / 3 镜头模型与 maxCount）** · **续册四（R12 字段硬规则 · R13 错误码幂等 · R14 成本系数）→ `references/libtv-official-qa-part4.md`** · **续册五（R16 首尾帧续写与审核降级 · R17 导演台与批量编排）→ `references/libtv-official-qa-part5.md`** · **续册六（R18 非VIP三模型差异与选型 · R19 音频建立序列与审核边界 · R20 它挑我方流程的错）→ `references/libtv-official-qa-part6.md`** · **续册七（UV1 点火与提交 · UV2 合成与导出 · UV3 其余接口 10 问 · 含 `prompt_template` 13 项枚举）→ `references/libtv-official-qa-part7.md` · `libtv-official-qa-part8.md` · `libtv-official-qa-part9.md`** · **★★ 引用链与点火操作手册（按 MCP 原语 · 平台方给出）→ `references/libtv-op-manual.md`** · **★ 续册三（点火审批链 · 外部编排无法绕过审批）→ `references/libtv-op-manual-part3.md`** · **续册（读通道故障排查 §十四–§二十）→ `references/libtv-op-manual-part2.md`** · **★ 流程坑与点火前自查清单 → `references/libtv-op-checklist.md`** · **★★ 单镜提示词结构·平台审计版（5 块主干 / 150–350 字为 QA 参考、不是平台硬阈值 / 禁止项末尾）→ `references/libtv-prompt-structure.md`** · **★ 计费与积分专册（R24：计费点清单 / 图像·视频单价口径 / 失败退分四情形 / 并发预冻结 / 34s 10 镜成本估算与公式 / 省积分＝减少点火次数）→ `references/libtv-billing.md`** · **★ 审核边界专册（R25：文本·图像·视频三侧红线，每类带「被拦句 → 安全改写」/ 内容违规与技术改造必须分开 / 锚点复用 9 次不触发相似度审核 / 静默降级识别 / 点火前自检 5 条）→ `references/libtv-moderation.md`** · **★ 并发与 run 锁专册（R26：节点级互斥修正 / 契约未暴露项清单 / 死锁五出口 / 两侧工具面映射表 / ask_human 独占一轮 / 各模型成片时长范围）→ `references/libtv-concurrency.md`** · **★ 平台更新监测与四个新接口（R27：**无 changelog → 三源快照 diff 法** / `list_projects`·`project_info`·`update_project`·`show_generation_result` / ★★★ `project_info` 的 `connectionList` ＝ **首次可直读「边」** / 乐观锁 `expectedRevision` / `labels` 与白名单自查三步 / 技术目录被删的三处换源 / 破坏性变更与处置 / **1.5 官方公告五大功能对照（§十：角色造型·原创编剧·导演分身·3D-BOX·成片精修 → 客户端 UI 为主、MCP 暴露待验；导演分身＝把我方 SOP 喂成预设）**）→ `references/libtv-platform-watch.md`** · **★ 平台监测 · REA 差集索引（拆册：2026-10-14 REA 逆向差集 · CLI/模型目录/端点表/宿主表/两条实时通道/审批模式）→ `references/libtv-platform-watch-rea-index.md`** · **★ 点火链·导演台·计费口径（R29 导演台 14 个 op 与轨迹边界 / R32 计费「无明文」清单与零成本唯一口径 / R33 点火链三阶段与审批依据）→ `references/libtv-ignite-director-billing.md`** · **★★ 点火与合成实操字段 + 剧本/资产/台账接口（R37/R39）· ★★ **声音节点创建与接线（`nodeType=audio` 必带显式 `scene` · `seed-audio-1.0` · 按"连续层/点状事件层"分 2 条 · 只接合成不接镜头 · 点火顺序约束）** → `references/libtv-ignite-ops-fields.md`** · **★★ 产出规格/交付运维/内容方法（R40/R41/R42 · 含 `prompt_template` 13 项枚举与写实成功学 7 条）· ★★★ **标准 11 段板块命名（01_剧本定稿→11_交付验收）+ 账本文件层（画布是镜像、账本"引用锚点"字段才是正本）+ 节点规模扩展公式** → `references/libtv-quality-delivery-content.md`** · **★★★ 平台自家写法样本（实物学 · 资产两段式 / 镜头三段式 / `{{Image N}}` 位次插桩 / taskParams 三个新字段）→ `references/libtv-prompt-house-style.md`（★ 另含官方预演 3 条 + 落地页 6 条场景提示词）** · **★★ 能力矩阵（48 工具 × 实测状态 · 「全部应用一遍」的清单化路线图 · ★ 平台自家一键成片技能目录 15 条：`skillKey` + `templateUuid` 配对）→ `references/libtv-capability-matrix.md`** · **★★★ 资产与环节标准清单（单一入口 · 「生成什么/视角/几个/三档必要性」· 治"一会生成一会不生成"）→ `references/asset-and-stage-checklist.md`** · **★★★ 跨来源流程共识（外部 10 源 × 工业三阶段 × DAG/B-spine 节点图哲学 · 八条共识 / 三处分歧 / ★★ 六个"双方都漏"的环节（统一调色·逐字描述块·代际退化·3/4 后视·命名规范·先测3张）/ 2026 各平台一致性机制速查）→ `references/pipeline-cross-source-consensus.md`** · **续册（审计修订 §七/§八）→ `references/asset-and-stage-checklist-part2.md`** · **★★ 合成节点（`video-clip`）与时间线字段细则（`clipTimelineData` 四个必填项 / 静音字段"文档意图 vs 实测"冲突 / 两条合成路径 / 图片九宫格 shortcut 映射）→ `references/libtv-compose-timeline.md`** · **★ 节点字段补遗（`audio` 时长用毫秒 / `text` 结果写 `data.content` 且可当提示词来源 / `script` 与 `storyboard` 共用 `data.type=script` 结构 / `rows[*]` 字段与两个只读键）→ `references/libtv-node-field-notes.md`** · **★ 提案交付物的视觉与实现规范（1920×1080/16:9 与 4–6% 安全边距 · 字号阶梯 · 从资产推色卡与 4.5:1 对比度 · 九种版式家族与 8 镜网格 · 分层背景与模糊边界 · 抽帧选帧）→ `references/libtv-treatment-delivery-spec.md`** · **★ CLI 管道体系（NDJSON＝节点引用流 / 已有节点"回放"复用 / 旁路节点 / `>/dev/null` 抑制 / 嵌套决策表 / 官方真实骨架）→ `references/libtv-cli-pipelines.md`** · **★ CLI 环境与绑定专册（凭据目录 `LIBTV_CONFIG_DIR` 与 `logout` · 活跃账户作用域 · `-s`/`-u` 不可互换 · `group`/`upload`/`project`/`model`/`workspace` 的官方约定与字段 · 管道中段纪律）→ `references/libtv-cli-env-binding.md`** · **★ 本地录制与取证（乐器演奏 → 已验证 WAV 的十步 · 预设控件"调整量≠绝对值"四条坑 · 多键和弦 API · 纯画面无音轨 MP4 的选窗/预卷/裁切契约 · 「控件值≠产物事实、成功提示≠成功」取证通则）→ `references/recording-and-evidence.md`** · **★ 网页端请求形状与任务端点（`riskControl.deviceToken` 风控注入 / **生成带指纹而报价不带** / 任务·队列·Agent 端点的请求体 / 一批只读助手会**静默吞错** / `clickSuggest` 的 header-token 认证变体 / **Skill 族与 `skillKey` 构造** / **third_asset 合规轮询** / **agreement 两段式闸门只读**）→ `references/libtv-web-api-shapes.md`** | · **★ 实时通道与前端工具（FE Tool RPC：`fe_tool_call/ack/progress/result` · 单活标签页模型 · 每画布一条连接）→ `references/libtv-realtime-and-fe-tools.md`** | · **★ CLI 媒体上下行（`upload` 预签名分片 5 MiB/2 min · 内容寻址 sha1 · `download` 水印两维度）→ `references/libtv-cli-media-transfer.md`** · **★ 脚本/故事板 13 列行模型与 CSV 导出（字段全表 · 镜头对象回落链 · CLI 有损子集 vs 网页富模型）→ `references/libtv-script-rows.md`** · **★ 网页客户端失败语义（鉴权过期判定 · 静默错误白名单 · 请求装饰）→ `references/libtv-web-client-errors.md`** · **★ 脚本 V2 提交契约（镜头回写字段 / `script-generate-v2` 与 `script-recompute-prompts-v2` / 20 行上限 / `src_img_N`）→ `references/libtv-script-submit.md`** · **★ 客户端硬限制总表（上传/下载/保护节点/分镜组等上限 · 格式白名单 · 能力门）→ `references/libtv-client-limits.md`** · **★ Seedance 专册（素材门槛 `(0.4,2.5)`/`(300,6000)`/`<30MB`/`2~15s` · 样片 480P→正片 1080P 7 天 · 合规校验过一次后续免检 · **任务核验页可查实际调用模型**）→ `references/libtv-seedance.md`** · **★ 节点类型全表（客户端枚举 19 值 + 中文显示名 20 键 · "六种"只在 `create_node` 层成立）→ `references/libtv-node-types.md`** |
| **★★★ 生产画布解剖（【画布实证】级 · 2026-10-03 · 逐节点读完 180 节点真实获奖画布）**：**⭐ 与本库其他 libtv-*/platform-* 文件冲突时以本文件为准**（那些是【库规】级，本册是实测行为）。含 ★★ 连线合法性矩阵（video→video 与 video→image **均被禁** → 跨节点衔接只能靠文字）· ★★★ `{{Mixed N}}` 五组交叉实证（**序号 = mixedListOrder 的 1-indexed 位置**，文字排布不影响）· ★★★★ **禁项是"跑出来之后"才加的**（场景1 九版迭代链 + 怪兽组参考图本身就是 crocodilian 的实物佐证）· ★★★ 资产层提示词只有 **6–34 字**（与 video 层 300–3000 字相反）· ★★★ 四个跨节点衔接手段与**动作匹配切**三步写法 · ★★★ 14 条提示词高价值写法 · 多场景并置三规则 · 16 类坑位（时长三关系 / `timeoutReported` 累计 7 例与 status:2 并存 / **8 个悬空引用**）· **两个读血缘的结构化字段**（`frameCaptureSourceNodeId` 在 data 顶层不在 params / `prevTaskInfo`）· ★★★★★ **本库 11 步链路是【库规】不是平台要求**（真实画布只有「资产图→video」两层，且**资产可后补**，代价是造型失控） | **`references/libtv-canvas-anatomy.md`**（主册：规模/节点/引用/资产）· **`references/libtv-canvas-anatomy-part2.md`**（结构与衔接）· **`references/libtv-canvas-anatomy-part3.md`**（内容写法）· **`references/libtv-canvas-anatomy-part4.md`**（异常与流程）· **`references/libtv-node-topology.md`**（节点类型 / 连线矩阵 / 建链与点火顺序）· **`references/libtv-prompt-anatomy-distilled.md`**（核心骨架）· **`references/libtv-prompt-anatomy-distilled-part2.md`**（锁定与衔接）· **`references/libtv-prompt-anatomy-distilled-part3.md`**（模式与验收） |
| **★★★ 标准工作流程（基准＝《THE TURN 回合》· 2026-10-10 七张源画布逐节点全量回读）**：**没有唯一标准，七部实测分两派**——**长段长词派**（弥寿计划／抵达之前／THE TURN）：`mixed2video` ＋ **Seedance 2.5** ＋ **30 秒段** ＋ **3,242–6,215 字长提示词** ＋ 参考 4–8 张；**短段短词派**（放殃／出走）：`singleImage2video` ＋ **Kling 3.0/O1** ＋ **5–10 秒段** ＋ **18–37 字短提示词** ＋ 参考约 1 张；另有中间态（Wrong Room 15 s／303 字）与素材态（坠星：28 段里 13 段参数缺失、15 条 prompt 为空）· **七部真正共同只有四条**：节点单位是「段」不是「镜」／边就是连线（无 dependency·assembly 语义边）／`enableSound` 基本 on／视频吃多张参考图 · **⛔ 给新作品定做法前先问「学哪一派」，不许默认套 THE TURN 的数值** · THE TURN 特有的中文规格书（92 个，`data.content` 是**数组**）＋ `{{Node <uuid>}}` 五件套（ACTIVE ASSETS／`@ImageN` 顺序＝imageList／OUTPUT CONTRACT／秒级节拍／硬禁令）＋ 填空模板 T1–T4 见文档 §5–§6 · 名字即状态机（秒数与 settings 104/108 一致）· ⛔ 该画布 forbidden-write，只读 | **`references/standard-workflow-the-turn.md`** · **★ 续册（§5–§6 可执行骨架 + 填空模板 T1–T4）→ `references/standard-workflow-the-turn-part2.md`** |
| **★★ 反推模式入口与盲测（2026-10-11 新）**：先声明 `content_reverse / copy_reverse / source_replica / rule_distill / production_build`、`original_readback / copy_readback / public_media / text_only / none` 与 `deliverable: mirror / production_plan`；副本不得冒充原项目，未盲测不得升级为标准，`unresolved` 不得补假边；源门禁双向阈值 0.95–1.10，mirror 必带 `source_node_id`，缺源图返回 `NOT_VERIFIED` | **`references/reverse-fidelity-contract.md`** · **`references/blind-reverse-runbook.md`** · **`references/film-reverse-runbook.md`** · **★ 续册（§7 实体层与逐镜资产映射：实体表 / 逐镜资产映射剪枝 / 字幕带 / 剪枝后重建提示词包 / 参考图 7 张上限 / 建节点顺序）→ `references/film-reverse-runbook-part2.md`** · **`scripts/source_fidelity_lint.py`** · **`scripts/fidelity_regression.py`** · **`scripts/reverse_claim_lint.py`** · **`scripts/blind_test_gate.py`** · **`scripts/reverse_pipeline.py`** · **`scripts/work_units.py`** · **`scripts/cross_work_transfer.py`** · **`evals/fidelity/`** |
| **★★ Agent 自主三条纪律**：预算与止损（先报数 · 能免费先免费 · 压缩到上限内）· 证据链四件（任务号/参数快照/结果路径/判据结果）· 可计算一致性（容器/切片/像素/结构/可读性五级判据） | **`references/agent-autonomy.md`** |
| **★★ LibTV 学院官方教程蒸馏（UI 功能层 · 2026-10-06 逐字读完官方"图文教程"全 11 课）**：**画布四模块** · **工作流搭法与 AutoLink 智能引用（`Tab` 单次 / `Shift+Tab` 全部）** · Slash 预设 10 项 · 图片工具（全景720°/多角度/打光/宫格切分/分镜组）· 视频工具（高清/片段重拍/智能续写/逐帧拉片/深度动作捕捉/音视频分离/智能剪辑）· 音色克隆 · 图像生成器进阶（元素标记/风格/聚焦/摄像机控制）· 视频主体库（**仅 Kling O3**）与运镜预设 · **脚本节点批量产出全链路** · **3D 导演台（站位/机位/角色运动轨迹/摄像机运镜轨迹/一键跟随 + Blender 插件）** · Seedance 2.5 与真人素材合规校验 | **`references/libtv-academy.md`** · **★ 续册（课 08–10：脚本节点批量产出 / 3D 导演台 / Seedance 与真人素材合规）→ `references/libtv-academy-part2.md`** |

| **剧作层（第一步剧本：写之前 → 选型 → 写之后诊断）** |  |
| **★ 剧本交付契约（十二模块 M1–M12 · 逐块接口 / 判据 / 模板 / 门禁用法 / L0–L2 三档阶梯）→ `references/script-module.md` · 门禁 `scripts/script_lint.py`**；**★ 写作方法融合层（GitHub 检索融合：前提推演 · 主控思想＝价值＋原因 · 第三条轨道 · 戏核抽掉检验 · 中文工艺六诀 · AIGC 生产标签；**适用范围只限剧本 / AIGC 写作**，明列 NOT for 技术文档 / 学术论文 / 新闻稿 / 公文）→ `references/writing-methods.md`**；**★ 做剧集 / 长篇 → `references/drama-series.md`**（引擎四元素 · 咬合测试 · "能续多少集"与"引擎第几集失压"两条判据 · 人物网三件套 · pilot 三类型 · 地雷与记账式单元 · 分歧保留表 · 二十六条诊断 · 十五步工作流）· **破单集 / 排幕 / 放出幕 / 排季 → `references/drama-episode-structure.md`**（**幕＝交付格式、三幕＝设计工具** · 四幕功能链与三条通用律 · **出幕八型**与"至少一幕无对白或道具" · **信息管理四工具 + 赌注检验** · **场结构五件套** · 隐形幕三重判据 · 季形八装置 · **★ 中式接口三处不可换算**）· **★ 写国产剧 / IP 改剧 / 写策划文档 → `references/drama-series-cn.md`（＋ 平台自己的剧本预设：题材 15 / 字段组 5 / 结构 8 / 热预设 8）**（**国产 vs 美式差异表** · **中文"页"的折算链与体量硬数据** · 三套文档链与**"戏眼"** · **单集骨架 3 分钟 + 15 分钟 + 集尾**与**四级悬念** · 延宕五技巧 · **情境两步法** · **"一案 N 集"光谱** · 红线与送审链 · 十八条诊断）· **★ 做选集（每集独立）/ 技术寓言 / 单一地点反转剧 → `references/drama-anthology.md`**（**三台引擎对照表（黑镜 / 爱死机 / 九号）** · 三个门槛与**绑定装置** · 黑镜六条纪律 · 爱死机生产法与**好集三特征** · 九号七法 · **★ 反转的工程学（误导三技术 · 最小线索配额 · "没有反转"也是反转）** · AIGC 适配与两条成本警告）；**★ 创意层（凭什么值得看）→ `drama-plotcraft.md`**（创意的四种来源 · 六种手法：信息错位 / 因果倒置 / 视角偏移 / 代价错位 / 规则变异 / 约束生成 · **具体性引擎** · **三档俗套黑名单** · 创意十问）· **套路素材 → `drama-tropes.md`**（Booker 七种 +2 · Tobias 二十种 · **Polti 三十六种角色配置** · 套路 × 时长适配 · 反向的三条判据）· **训练 → `drama-mastery.md`**（成熟十二条判据 · 七个训练动作 · 预承诺判据四观察点）；**入口 · 量容量 · 选型**（先读入口：四问 / 十七册地图 / 不重复清单 / 使用纪律 / 惯例层声明）——**量容量（写在节拍表之前，任意时长）**：时长档位表 · 十五拍→五拍折叠 · 反转与递增预算 · 容量单；**选结构模型**：十六模型谱系（三幕 / 五段 / 八序列 / 15 拍 / 英雄之旅 / 故事圈 / 七点 / Truby / Egri / Fichtean / 起承转合 / 序破急 / Propp / 幕结构 / 微短剧三段式）+ 选型决策树 | **`references/script-module.md`** · **`writing-methods.md`** · **`drama-series.md`** · **`drama-episode-structure.md`** · **`drama-series-cn.md`** · **`drama-anthology.md`** · **`drama-conflict-craft.md`** · **`drama-library.md`** · **`drama-plotcraft.md`** · **`drama-tropes.md`** · **`drama-mastery.md`** · **`drama-scaling.md`** · **`drama-structure-models.md`** |
| **写：人物剧作层 · 对白与旁白 · 题材引擎 · 写完诊断 · ★ 动笔写提示词前必读**——人物（三维 / 弧光四型 / 对手统一对立 / 道德论证 / 九问）· 对白与旁白（六病灶 / 五种台词动作 / **旁白三种距离**）· 题材（十二类型的承诺 / 引擎 / 必写场 / **AIGC 原型场景**）· 诊断（十五病分层确诊 / 五项误诊）· **剧作 → 提示词转换（可写性三档 甲/乙/丙 · 十七行翻译表 · "模型能懂吗"五问）** | **`references/drama-character-arc.md`** · **`drama-dialogue-craft.md`** · **`drama-genre-casebook.md`** · **`drama-script-diagnosis.md`** · **`drama-aigc-conversion.md`** |

| **门禁（动笔前后必过）** |  |
| **★ 产出任何结果之前 / 改动本库之前（先读）：L1 全量检阅定律 · L2 整合铁律 · L3 改完回头核 · L4 数字与来源** | **`references/governance-law.md`**（全库唯一定义处）· `references/governance-law-part2.md`（L2 的操作细则） |
| 写剧本之前：判这个题材做不做得出来 | `references/feasibility.md` |
| **定美学风格（写 brief 的第 5 项 / 进资产之前必做）** | **`references/style-library.md`** |
| 动笔写任何提示词之前（强制） · 交付任何提示词之前（必读） | `references/steelman-protocol.md` · `references/quality-layer.md` · `references/quality-layer-part2.md` · `references/prompt-ops.md` |
| **★ 拿参考图反推提示词（风格库重写 / 拉片 / 看图仿拍）：**证据三级（Observed/Inferred/Unknown · 双模型 diff）** · 七层反推表 · 提示词堆叠顺序 · 覆盖率矩阵 · **三图比对与内核提炼** · **统一重写结构与 7 条达标判据**** | **`references/reverse-prompt-method.md`** |

| **按阶段** |  |
| **★ 落笔前的导演推理：六问推导链（命题→人物→戏剧任务→冲突形状→能量→参数）+ 每场自我批判** | **`references/direction-reasoning.md`**（先做这个，再去各库挑词）** · `direction-worked-example.md`（同题完整推导示范，只讲「为什么改」，**不是模板**） |
| 写剧本 / 排开场钩子 | `references/script-craft.md`（含「留人三件套」与 10 招「钩子菜单」） |
| 出资产、跨镜一致性 · **★ 写资产提示词（人物 / 道具 / 场景）：三类的重点差异 · 场景四字段（空间结构 / 机位清单 / 继承要素 / 状态版本）· 人物景别可判区与状态 delta · 道具三类分法（手持 / 陈设 / 环境）· 字段→下游继承映射 · 从剧本 M11 派生** | `references/asset-consistency.md` · **`references/asset-prompt-spec.md`** |
| **★ 资产放行门 / 战斗矩阵 / 生成台账 / 一镜超过 8 次怎么办 / 两个主体的大小关系** | **`references/production-ledger.md`** |
| **人物形象/特征/设定在全片不漂（五条线：身份·造型·位置·情绪·状态）** | **`references/character-continuity.md`** |
| 落地到具体平台（**Updream / LibTV / WorkRally**）、批量任务格式、参考素材纪律 | `references/updream-workflow.md` · **★ 第二条通道（WorkRally · 站 5 / 5.5 / 6.5 / 6.7）：执行层定位 · 六个能力↔工位 · 决策树→`--mode` 映射 · 参考闭环硬门禁 · 三条守卫（声音／提示词优化只作反题／阶段门命令白名单）· 预算与证据链 → `references/workrally-workflow.md`；命令与参数速查（六条陷阱 · 动态值清单 · 画布八节点 · **两侧工具面对照**）→ `references/workrally-command-map.md`；**排镜表→场次投喂包：`scripts/workrally_bridge.py`（四类机检 + 10 条自检）** |
| 选平台、查时长与审核边界、算抽卡预算、查**平台专有语法**（Hailuo 方括号运镜指令）· **★ 输入组合互斥（首帧 / 首尾帧 / 全模态参考三选一）· 负向词的形式要求 · 画幅 = 固定六值 + `adaptive` 自适应（图生视频默认按首帧取最接近值；`2.39:1` 照写、落地 21:9）· 入口决定上限 · 被误封的正确修法** | `references/platform-matrix.md` |
| 写板块一（故事板）· **★ 平台自适应：三路径 + 输出模式声明 + 失败处方表 + 参数块/回写位** | `references/storyboard-frame.md` · 平台规格 → `references/storyboard-platforms.md` |
| 写板块二（分镜结构 / 构图 / 镜头规格 / 声音七层） · **★ 每个板块该想什么 · 写哪一句 · 模型能不能懂（15 块逐个过，含逐块自查表）→ `references/block-playbook.md`** · **★ 12 块的接口规格（每块的功能 / 目标 / 输入 / 输出 / 依赖 / 边界 / 约束 + 两版差异 + 未写明项）→ `references/block-spec.md`** · **资产提示词的板块（角色 / 道具 / 场景 / 批量 · 9 块 · 含 12 条逐块自查）→ `references/block-playbook-asset.md`** | `references/shot-craft.md`（**★ 单镜容量 / 拆镜开关**） · 续册 `references/shot-craft-part2.md` · 续册 `references/block-playbook-part2.md` |
| **★ 排镜头（导演思维）：一场戏选哪几个镜 / 什么顺序 / 各多长 / 开场与结束怎么选 / 动作场节奏 / 接不上怎么救** | **`references/shot-orchestration.md`** |
| **拍一场戏（≥2 镜）：序列契约 / 几何用图 / 情绪连续性** | `references/sequence-craft.md` · **★ 人物调度（主体 / 陪体 / 群像）：四变量（方位·距离·高低·朝向）· 陪体四职能与空间五法 · 不喧宾夺主三规则 · 群像场型与不平均 · 调度→景别/焦点接口 · AIGC 三点降级与五条硬纪律 → `references/staging-craft.md`** |
| **一条生成里装多个景别（15 秒分镜法）：判路 / 段落语法 / 段数档位 / 锚点逐字复述 / 首帧策略** | `references/segmented-shot.md` |
| **选运镜：六族全谱（位移/光学/旋转/环绕/高度/复合）+ 环绕·甩镜·复杂运镜三个专项 + 意图表 + 五要素句式 + 速度尺（量纲）+ 失败模式** | `references/camera-movement-library.md` |
| **写转场：相似转场 / 动作转场 / 甩镜·推穿·缩放穿越·遮罩·白闪·墨染等 12 种 + 模板 + 失败模式** | `references/transition-library.md` |
| 写声音（对白 / 口型 / 音效 / 配乐 / 混音 / 同步） | `references/sound-craft.md` | **音乐理论** `references/music-craft.md` · **音效设计方法** `references/sound-design-craft.md` · **混音与响度** `references/mix-loudness.md` · **工具与授权 + ★ 平台音色目录（17 条 `voice_id`）** `references/audio-tools.md` · **声音提示词写法** `references/sound-prompt-craft.md` · **声音后期流程与声音表** `references/sound-post-pipeline.md` · **声音的叙事语法** `references/sound-narrative.md` · **声音训练七动作** `references/sound-drill.md` · **声音表门禁** `scripts/sound_lint.py` |
| 素材生成完之后：选片 / 修复 / 超分 / 调色 / 剪辑 / 字幕 / 交付 | `references/post-production.md` |
| **审一条生成结果能不能用（七遍法：1 裸看 + 6 专项 + 证据式笔记）** | `references/review-passes.md` |

| **按内容** |  |
| 写人物与表演、情绪外化 | `references/character-depth.md`（**★ 表情动作的下限（写透四层 + 眼 + 呼吸）**） |
| **★ 人物"不像真人"（好看但记不住 / 对称过头 / 静息像雕塑 / 越加细节越假的瘆人感）：个体化配额 · 不对称区域与方向纪律 · 生理活性参数 · 静息微动 · 恐怖谷三步诊断** | **`references/character-realism.md`**（**诊断层**——"够细了但就是不像人"从这里进） |
| **★ 指定一个具体表情却写不出"脸上到底动哪里"（96 条具名表情：基础 / 微表情 / 复合 / 伪装 / 时序 / 极端 / 社交 / 文化 / 运镜整合 / 组合 / 经典模板）——查表用** | **`references/expression-library.md`**（**★ 表里的角度 / 毫米 / Hz 是给作者对表的，不是给模型看的**；落笔要转成可见描述） |
| **★ 表情与表情之间：切换的三种过渡 · 四时间参数与惯性 · 「笑转严肃」五拍 · 眼泪四阶段（蓄/盈/决堤/滑落）· 动画作画怎么落（律表/止め/ツメ）** | **`references/expression-rhythm.md`**（**日式动画表演与"节奏不像真人"从这里进**） |
| **★★ 做情绪时"脸突然变 AI 味"（缺一块肌就换了一个情绪 / 面部融化 / 假笑 / 对称过头）：情绪 → AU 组合总表（八情绪 × FACS）· 三条分界判据（悲伤与愤怒的分界是 AU1 · 真笑与假笑的分界是 AU6 · 轻蔑是单侧）· 情绪 × AI 崩坏对照表 · 三条通用硬纪律（震颤不进提示词 · 脸要大且不离画面 · 必须给不对称）** | **`references/expression-anatomy.md`** |
| **★ 写提示词时"知道该写什么、但想不出词"——三类语料（术语词 / 可写句式 / 判断参数）的分辨 + 12 板块取词语料地图 + 构图法与姿态名词表** | **`references/lexicon-map.md`**（**取词入口**——先查这张图，再动笔） |
| **★ 写人物小传 / 角色档案：八字段怎么推出来 · 句架库 · 痕迹词表 · 到 12 板块的映射 · 反例图鉴** | **`references/character-sheet.md`**（**★ 小传是推导工具，不是交付物——只交付"可见物"那一层**） |
| **★ 第 11 块【声音】要写具体声音词（环境床 / 拟音 / 硬效 / 人声 / 设计声 / 空间混响）** | **`references/sound-lexicon.md`**（★ 含**平台 TTS 的 21 个口癖 token**：`laughs` / `sighs` / `crying` …；结构、配额、混音、同步仍在 `sound-craft.md`） |
| **这一镜要"演出"什么：僵硬/虚假分诊、内部驱动、时序破假、对手戏、表演训练** | `references/performance-craft.md` |
| **情绪词换不出形变：按情绪的微节拍词表 / 眼生命 / 台词前后节拍 / 表演量表 / 主档案 / 坏表演图鉴** | `references/performance-vocabulary.md` |
| 写动作 / 负重 / 接触的物理 | `references/physical-feedback.md` · **现实逻辑（跨层自洽）：光与影是否同向 · 人体重心与可达范围 · 空间地理与动线 · 因果链 · 时间与动作量的算术 · 材质与守恒 · 生理常识 · 接触支撑 · 声音的因果；九轴自查 + 高频矛盾对照表 → `references/real-world-logic.md`** |
| 写有动作的镜头、周期动作选路径、运镜与景别纪律 | `references/motion-control.md` · **★ 演员走位与动作（让主体真的动起来）：根因诊断 · 动作分级 A–D · 位移四种写法（跨镜/机位代走/首尾帧/镜内连续）· 步频·摆幅·重心三量 · 症状→修法 · 平台实测六项 → `references/actor-movement.md`** · **★ 动作原理（动画十二法则 → 可执行写法）：十二条按"模型能不能执行"分三档 · 七条可写原理（预备/缓入缓出/弧线/跟随与重叠/次要动作/挤压拉伸/时机）· 动作句库 · 与"一个时间节点只放一个动作"的冲突合成 → `references/motion-principles.md`** · **★ 运镜板块（镜头版四相 / **段落版逐相位对应**：行数＝时间线相位数）→ `references/block-camera.md`** · **★ 运动参数层（ft/s↔m/s 换算 · **时间轴速度曲线**（起缓—承中—转快—收慢）· **每 4 秒至少 1 个运镜** · 焦点与手持的物理量 · **五种运动钩子** · 平台速度档位 · **★ §6·补 快门角与运动模糊：曝光时间＝快门角÷360°÷帧率（180°@24fps＝1/48s）· 只写移动主体的拖影、禁写"整帧运动模糊"）→ `references/motion-parameters.md`** |
| 写光影与质感（写实向）· 材质光学 · 细节预算随景别 · 皮肤单一物理状态 | `references/tone-realism.md` |
| **★ 人物像 AI（油亮 / 蜡像 / 高光错 / 褶皱假）：成因链 · 皱纹解剖依据 · T区U区反射差 · 六条可测判据 S1–S6 · 症状→根因→改哪句处方表 · 皮肤改动验证规程**（**诊断层**——拿到坏图从这里进） | **`references/skin-realism.md`** · 续册 `references/skin-realism-part2.md` |
| **★ 皮肤光学的物理原因：六层光学结构 · 穿透深度表 · 黑色素幂律 · SSS 参数与部位表 · 高光双层模型**（**物理层·第一册**——"皮肤为什么这样"从这里进） | **`references/skin-light-physics.md`** |
| **★ 光位 · 软硬光 · 色温的物理原因：五光位精确角度 · 半影公式与接触硬化 · 开尔文标度 · 17 条规律 / 14 条误区**（**物理层·第二册**——"光为什么这样"从这里进） | **`references/light-physics.md`** |
| **★ 定器材：先读方法（六轴正交 · 跨包组合 · 不绑默认包 · 真实度选用依据），再查包** | **`references/equipment-selection.md`** → `references/camera-package-library.md`（17 包 + ★ 平台原生 29 段器材提示词片段：机身/镜头/焦段/光圈四格可叠加）+ **`references/package-extended.md`**（补充 17 包：航拍·FPV·微距·鱼眼·移轴·宝丽来·红外·热成像·夜视·录屏·卫星·内窥·CGI·AI原生·延时）+ **★ 选包速查（三问定档定包 · 氛围词直查表 · 三套可直接复制的成套句 · 五条纪律与失败模式）→ `references/camera-package-quickref.md`** |
| **载体痕迹的机理（CCD 四条 / VHS 五条 / 胶片"细节与颗粒一起失去" / 镜头性格对照 / **★ 颗粒的帧间独立重排——"颗粒是拍的还是加的"第一眼判据，含"细纹理沸腾 vs 颗粒沸腾"的区分**）** | `references/carrier-artifacts.md` |
| **光怎么写实（柔光的五种造法 / 动机光 / 双影 / 眼神光 / 逐级调暗）**——**卷首含「造法 → 提示词落地」对照表 + 第六问：这句是让它"去做"还是"去画"** | `references/light-quality-construction.md` |
| 查器材单品参数（胶片 / 机身 / 镜头 / 印片）与漫剧黑名单 · **★ 色彩：色怎么运作（理论 / 配色方案 / 校色与调色的顺序 / 实拍流程的 AIGC 落点 / 示波器与肤色线 / LUT / ★ 色彩→提示词的转化：模型怎么理解色彩 · 四层色彩词 · 写法顺序 · 环境色渲染）→ `references/color-science.md`；色怎么讲故事（青橙溯源 / 色彩弧线 / 心理三条纪律 / 类型惯例 / 带数值的案例）→ `references/color-narrative.md`** | `references/cinematic-look.md` |
| 打光需要专业深度 · **整片走系二 · 描边**（美漫描边 / 赛璐璐 / 卡通渲染）——**注意：这只是"风格化"的一半**；**系三 工艺渲染（定格 / 像素 / 木刻 / 油画 / 水彩 / 剪纸 / 沙画 / 水墨）是另一套写法，前两套量级句对它全部停用**——**★ 系三的公共层可逐字复制 → `references/stylized-look-craft.md`（十种工艺 × 六栏：材料签名·运动特性·光怎么处理·色板·两族排除句·失效症状）**（→ `style-library.md` §二） | `references/lighting-philosophy.md` · `references/stylized-look.md` · **`references/stylized-look-craft.md`** |
| **选美学风格（247 条 · 十四卷）· 选取流程四步 · 量级路由（写实 / 描边 / 第三系 / 混合）· 按叙事氛围反查** | **`references/style-library.md`**（入口） |
| **★ 选完风格之后：这一族配哪类方案包 · 哪些包是禁忌 · 叠哪个调制层（**十四族** → 包的搭配与理由；族⑬ 画作转实拍 · 族⑭ 混合媒介按"层"分派）** | **`references/style-package-matching.md`**（**出资产之前必过**） |
| **★ 选定风格后"去哪找参照、怎么搜"：逐条给 取图处（豆瓣剧照区 / 博物馆开放馆藏）+ 检索键（片名·画家·作品·摄影师）+ 该风格的检索句 + 每条挑哪一类帧。★ 全库 247 条已全部覆盖（8 册）· ★★ 2026-09-16 起改口径：**每条 1 个参照物（全库不重复）＋"为什么是它"＋三帧三轴规格**；**`【内核】` 留空 → 内核一律写进内核册** · **★★ 内核册（247 条 · 由真实参考帧逐图反推得来；**每条 1 个唯一参照物＋三轴规格**——**电影/动画按景别×场景×色调；画作·文物·平面按题材×构图×色调（它们没有景别）；G 卷等机制条目按机制怎么运作写**；**美术类允许参考同流派的相关画作**；**取图工具 · 读图者即校验者 · 宣传照/展厅照/现场照/错片/假图的剔除纪律** →  §6.1c–§6.1e**）→ 内核册与取图册（详见下方「风格库」行）**（地域与平面 30）· **`style-cores-a1.md`** · **`style-cores-a2.md`** · **`style-cores-a1.md`** · **`style-cores-a2.md`** · **`style-cores-a3.md`** · **`style-cores-b1.md`** · **`style-cores-b2.md`** · **`style-cores-b3.md`** · **`style-cores-b4.md`** · **`style-cores-c1.md`** · **`style-cores-c2.md`** · **`style-cores-c3.md`** · **`style-cores-c4.md`** · **`style-cores-c5.md`** · **`style-cores-d1.md`** · **`style-cores-d2.md`** · **`style-cores-e1.md`** · **`style-cores-e2.md`** · **`style-cores-f1.md`** · **`style-cores-g1.md`** · **（取图册 8 册，管"去哪找参照"）**：**`style-sources-a.md`**（美术史 40）· **`style-sources-b.md`** / **`style-sources-b2.md`** / **`style-sources-b3.md`**（电影与导演 60）· **`style-sources-c1.md`** / **`style-sources-c2.md`**（类型与亚文化 81）· **`style-sources-dg.md`**（动画与混合媒介 36）· **`style-sources-ef.md`**（地域与平面 30） |
| **★ 怀疑"偏色 / 过饱和 / 灰暗"时：色彩管线层（色彩空间三要素 · 三条算术：乘法=亮度·幂函数=对比·加法=抬黑位 · 场景参考 vs 显示参考 · 系统 gamma · 色调映射四件事 · 白平衡三原则 · 三个症状的成因与可验证判据 · **谁能进提示词、不能进的话去哪**）** | **`references/color-pipeline.md`**（**★ 色彩空间名与 gamma 值一律不进提示词——模型看不见容器**） |
| **★ 定"整片调色方向"时：十四族调色风格族谱（日系清新 / 港风王家卫 / 韩系 / 新中式 / 德味徕卡·蔡司 / 青橙 / 胶片褪色 / 黑白两种 / 韦斯粉彩 / 赛博霓虹 / 阳光年代 / 冷调犯罪 / 荒野土色）· 每族给 色相倾向 · 色彩构成 · 明暗与对比 · 场景 · 辨识要点 · 提示词落点** | **`references/color-grading-styles.md`**（**族谱，不是原理**；原理去 `color-science.md`） |
| **★ 选定风格后"怎么核它像不像"：逐条校准卡（色彩指标 · 光位/景深 · 构图 · 质感 · 参照/生成两个测量位）。★ 全库 247 条已全部覆盖（7 册）· ★ 定标与容差（怎么量 · 容差表 色相±12°·饱和±25%·明度与对比±15%）→ `style-cards-scale.md`** | **`references/style-cards-scale.md`**（**判偏的尺子**）· **`references/style-cards-b.md`**（B 卷 20 条**详卡**）· **`style-cards-a.md`**（美术史 40）· **`style-cards-b2.md`**（导演 40）· **`style-cards-c.md`**（C 卷 41）· **`style-cards-c2.md`**（C 续二/三 40）· **`style-cards-df.md`**（动画＋平面 33）· **`style-cards-eg.md`**（地域＋混合媒介 33） |
| **★ 选完包之后：这一部片取哪一档（胶片 × 印片 × 调制层 · 十四族推荐档 · 画幅的"胶片/数字"消歧）** | **`references/film-stock-matching.md`**（**包给机制，档给味道**） |
| 十四卷条目：美术史 21＋补编 19 / 电影 20＋导演 20＋**当代导演 20** / 类型亚文化 21＋**题材质感 20**＋**类型机制 20**＋**高频常用 20** / 动画漫画 21 / 地域民族 18 / 平面图形 12 / 选集与混合媒介 15 · **★★ 全库 247 条已 100% 加装「质感与痕迹」与「最容易被写歪成什么」两栏** · **★ 逐条一句话索引与条目字段规范 → `references/style-library-index.md`** | `references/style-library-art-history.md`、`style-library-art-history-part2.md`、`style-library-cinema.md`、`style-library-cinema-part2.md`、`style-library-cinema-part3.md`、`style-library-cinema-part4.md`、`style-library-genre.md`、**`style-library-genre-part2.md`**、**`style-library-genre-part3.md`**、**`style-library-genre-part4.md`**、`style-library-animation.md`、`style-library-regional.md`、`style-library-graphic.md`、`style-library-anthology.md` |
| **读一位导演的六把尺子（摄影·节奏·声音·调度·表演·母题）—— 解决"只像画风、节奏声音全不对"** | **`references/director-system.md`** |

| **出问题与速查** |  |
| 开写前规划脆弱元素、生成崩坏时查原理 · 出片不合格要返工 / 只想看最高频硬规则 | `references/ai-artifact-control.md`、`references/qa-failure-codes.md`、`references/cheatsheet.md` |
| 查来源、许可与授权红线 | `references/sources-and-credits.md` |

## 来源与署名

**完整清单（100 行，含全部许可、授权红线与「无许可证来源只提炼方法、不复制文本」纪律）→ `references/sources-and-credits.md`**（逐字迁出，未删减）。
| **★ 动手前 / 改脚本前 / 写长内容前（犯过的 29 类操作错）** · 查已定下来的结论 / 想推翻某条默认值之前 | **`references/pitfalls.md`** · `references/key-decisions.md`（Established 有实测支撑 / Conventional 惯例可改）「**原册已到行数上限；新结论自 E160 记入 `references/key-decisions-part2.md`**」 |
| 看整合式交付的完整样例 | `references/examples/` |
| **出片之后：命名 / 归档 / 交付包** | `references/delivery-engineering.md`（**命名三原则 · 五状态词 · 六件交付 · 元数据七字段**） |
| **镜头衔接 / 视觉呼应（切点 · 景别序列 · 呼应四种 · 镜头级情绪）** | `references/shot-linkage.md` |
| **★ 分镜的"设计感"（280ms 地基 · **十个设计装置** · **直白→有设计四条改法** · **全片视觉母题三拍** · 案例五则）** | `references/shot-design.md`（**机检 `lib_doctor.py --design`**） |
| **剪辑节奏 / 轴线（ASL · 节奏密度 · 180 度线 · 30 度原则）** | `references/editing-rhythm.md` |
| **多段拼成一条片：拼接点 / 定格相 / 重编码** | `references/cross-shot-interface.md`（**三接口 · 拼前四查 · 泊能定格 · 统一 fps 与像素格式**） |
| **交付前查"AI 味" / 改完 skill 查退化 / 拆卷后查断链** | `scripts/ai_smell_check.py`（空话词表在 `prompt-ops.md`）+ `evals/scenarios.md` + `scripts/audit_prompt.py` + **`scripts/lib_health.py`（改布局 / 拆卷 / 增删册后必跑：悬空指针 · 学了没用上 · 跨册重复 · **行号引用越界 `refs`**）** |
