# 阶段一 · 意图 → 提示词正本 → 可复制 Markdown（交付入口）

> **何时读**：用户要的是**提示词本身**（"只要提示词"、"给我一条空镜的提示词"），
> 而不是成片、平台画布或媒体生成时，先读这一份。
> **读完回哪**：`references/production-compiler.md`（生产编译器全量用法）·
> `references/run-sheet.md`（整片执行清单）· `references/governance-law.md`（产出前的不可跳项）。
> **本文件是入口与边界说明**；长规则只引用、不复制（治理定律 L2）。

日期：2026-10-26 · 状态：阶段一 · 草稿可执行，正式交付须当前审阅证据

---

## 1. 真实入口

```powershell
# 阶段一真实入口：意图交接文档 → 正本 → 可复制 Markdown
python scripts/compile_intent_delivery.py <intent_handoff.json> --out out/ --draft
```

**用户不手填 JSON。** 自然语言理解由 Agent 负责：Agent 读用户原话，写出一份
`intent-handoff/v1` 文档（模板见 `samples/papercut_empty_shot_intent.json`），
再交给上面的脚本做结构化交接、校验与转换。默认仅草稿；正式交付所需的全领域考虑、相关原文全读、当前任务与产物绑定证据，以及 --review / --capture-root / --session 接口，以 `references/delivery-review.md` 为准。没有有效证据时去掉 --draft 会非零退出，不得以工程 PASS 充当正式创作交付。

**一次运行出两件，用户不用选**（2026-10-31）：13_Draft_Prompt 号文件 是受语义复核约束的交付正文；
15_Canonical_Prompt 号文件 是统一 12 块标准视图（`block-spec.md` 的块序，逐块标"已填 / 未给"）。
两件同源同正本，13 不许当 12 块用，15 不许手改。样例：`samples/one_sentence_intent.json`（一句话单镜）。

**分工**（`scripts/intent_handoff.py` 开头写明了为什么这样分）：

| 谁 | 做什么 |
|---|---|
| **Agent** | 读用户原话 → 写 `intent-handoff/v1`。每个决定带 `source`（`user_explicit` / `agent_proposed` / `default`）与 `locked`。 |
| **脚本** | 校验交接文档；**逐字保留**用户显式值；凡是自己补的一律标 `agent_proposed` 且**不得 locked**；转成编译器输入。 |

**不做的事**（是刻意的，不是没做完）：不用正则从散文里猜"5 秒 / 9:16 / 剪纸"，
也不要求所有自然语言都能被脚本读懂。猜错会悄悄交付**另一部片子**（120 秒 / 16:9 / 写实），
这比"读不懂"危险得多。**读不懂就用 Agent 理解，不要绕开脚本去猜。**

## 2. 交接文档的关键字段

```text
intent_format   必须是 "intent-handoff/v1"，否则报错
goal            一句话目标
task_type       prompt_only | single_shot | full_film
decisions       duration_sec / aspect_ratio / visual_style（必填）+ 其他决定
shots[]         id / duration_sec / description（+ shot_kind / sound）
constraints[]   id / kind / text / delivery / source / locked / semantics
```

三条硬纪律（`scripts/intent_handoff.py` 会强制）：

1. **用户显式值逐字保留**，不被默认值替换。
2. **`agent_proposed` 不能 `locked`**；`user_explicit` 必须 `locked`。锁一个自己猜的值 = 造假。
3. **交付到 prompt 的约束必须带 `semantics`**（`required_any` / `required_all` / `forbidden`）。
   没有可判定语义，验收就无从判断"到底兑现没有"——脚本会直接拒绝这份交接。

`semantics` 是**验收依据**，不是提示词正文：它写"判定时找什么、禁什么"，
编译器据此把约束路由到各角色的提示词块，验收器据此独立复核。

### 原话到可编译交接

先整理本次任务的有效决定，再填接口。已有原话或brief记录时引用轮次/位置；没有记录时只留支撑关键决定的必要片段，不复制整段聊天。用户后续明确纠正替换旧值；原话和修订依据留在内部记录，shots/constraints只写当前有效的画面与声音指令。每项user_explicit须能指回原话；推导的镜头组织仍为未锁定提案。

交接按现有字段分工，避免把同一要求在多处重抄：
- decisions保存时长、画幅、风格等决定；已经在sound、shots、constraints表达的具体执行要求使用对应字段。
- visual_style.value是对象，含text和register，不是一个风格字符串。text保留用户风格原文；register按接口枚举选择photoreal/stylized/illustration/graphic，仅为机械分类，不增加创作偏好。
- 全片共用声音写顶层sound，单镜有差异才在该镜覆盖。mode仅用silent/ambience_only/dialogue_allowed/unspecified；“只留环境/物件声”可用ambience_only并列allowed/forbidden，未确定就保持unspecified，不自造模式。
- constraints.text写可执行的当前要求，semantics写对应肯定/禁止判据。“旧值作废”“上次说过”等修订说明留在来源记录，不混进正向创作正文；真正禁止项写清禁止对象。

semantics只支持有限的肯定/否定范围与已有同义组，不负责通用语义理解。判据选正文实际使用的原子事实；required_any表示可替代说法，required_all表示必须同时成立的独立事实。不要把自造的摘要标签当作正文必含短语。整段结构提案留在导演说明；只有对某镜真正适用的执行要求才绑定该镜，不能让“首尾同框”一类提案自动约束所有镜头。机器标记检查通过后，仍需核对整段因果、信息与情绪是否符合目标。

精确形状以schemas/intent_handoff.schema.json与scripts/intent_handoff.py为准。只输出必要字段与影响本任务的判断；提交后仍以真实编译和14验收结果为准，不能用“我已理解”代替可用交付。

## 3. 产物与停止点

```text
01_production_contract.json      合同（含 decision_log：每个决定的来源与锁定态）
03_shot_graph_plan.json          权威图
04_prompt_packages.jsonl         正本，格式 prompt-package/v1
rendered/03_Prompt_Packages.jsonl 正本 → 旧离线渲染器的单向适配副本
rendered/*.md                     旧渲染器产出的分角色提示词
12_intent_delivery_package.json   约束兑现证据 + 停止点 + 声明边界
13_Draft_Prompt.md                默认草稿（不是正式交付）
13_Final_Prompt.md                仅当前审阅证据有效且独立约束验收通过时产生
14_delivery_verification.json     独立语义验收结果
```

`prompt_only` **停在图规划与 Prompt Package**：不产生 `05_platform_execution_plan.json`、
不产生 `08_libtv_command_plan.json`、不创建画布、不生成媒体、不点火。

**正本只有一个**：`04_prompt_packages.jsonl`（`prompt-package/v1`）。
旧离线渲染器通过 `rendered/` 的单向适配副本消费它，不另手写一份。
非空输入若格式未知/不支持 → **明确报错**；8 个包、0 份文档**不算成功**。

## 4. 独立验收（不信自报状态）

```powershell
python scripts/verify_delivery_semantics.py --intent <intent.json> --out out/
# 退出码：0 PASS · 1 FAIL/UNVERIFIED · 2 用法错误
```

验收的输入**只有两样**：权威输入（intent / 合同）**和实际交付出去的正文与参数**。
`consumed` / `READY` / `constraint_evidence` 这类**自报状态一律不作判定依据**。

四条纪律：

1. **按语义判定，不按整句字串**："正上方俯视" 判为兑现 "固定俯拍"；
   "禁止人声" 不算人声违规，"旁白朗读解说" 算违规。
2. **不许别的节点掩盖本候选的错误**：每个消费角色单独判定。
3. **没判过 ≠ 通过**：缺包、漏候选、零判定、未知约束一律不报 PASS。
4. **可判定的约束必须真的被判过**：`judgements_performed` 为 0 直接 FAIL。

路由表取自 `scripts/compile_prompt_packages.py` 的 `CONSTRAINT_DELIVERY_BY_KIND`。
**该表加载失败会直接报错，不会退化成空表**——空表会让所有约束"无消费角色"，
一次判定都不发生，却看起来跑过了。

## 5. 反例（验收必须能抓住的）

| 篡改 | 结果 |
|---|---|
| 把"固定俯拍"改成"平视" | FAIL `CONSTRAINT_SEMANTICS_VIOLATED` |
| 把"固定俯拍"改成"禁止俯拍"（**否定正向要求**） | FAIL `DELIVERY_TEXT_CONSTRAINT_VIOLATED` |
| 删掉"右上角留白" | FAIL |
| 把"仅保留雨声"改成"旁白朗读解说" | FAIL |
| 同句"禁止音乐，旁白清晰朗读解说"（**禁止不得掩盖真实旁白**） | FAIL `DELIVERY_TEXT_CONSTRAINT_VIOLATED` |
| 正文追加"画幅16:9横屏"（**违背权威画幅**） | FAIL `DECISION_ASPECT_RATIO_CONTRADICTED` |
| 正文时长改成 120 秒（**违背权威时长**） | FAIL `DECISION_DURATION_CONTRADICTED` |
| 权威图新增第二个 video_candidate 却不交其包（**逐节点核对**） | FAIL `CANDIDATE_NODE_PACKAGE_MISSING` |
| 同一个候选节点交两份包（重复） | FAIL `CANDIDATE_NODE_PACKAGE_DUPLICATED` |
| 候选节点包角色/镜头与权威图不符（错配） | FAIL `CANDIDATE_NODE_ROLE_MISMATCH` / `CANDIDATE_NODE_SHOT_MISMATCH` |
| 改包的结构（角色与图不一致） | FAIL `PROMPT_PACKAGE_ROLE_MISMATCH` |
| 改包的来源（`source` / `locked` 与权威输入不符） | FAIL `CONSTRAINT_PROVENANCE_TAMPERED` |
| 正文改成"相机平视" | FAIL `DELIVERY_TEXT_CONSTRAINT_VIOLATED` |
| 合法同义表达（"正上方俯视"） | **PASS**（不许误杀） |
| 0 个包 | FAIL `NO_PROMPT_PACKAGES` |

用例见 `tests/test_intent_delivery.py`（工程渲染/约束测试明确使用草稿）及 `tests/test_bound_delivery_review.py`（正式门禁与篡改反例）。

**否定作用域的两条规则**（`scripts/constraint_semantics.py`）：

1. 否定词只管住它**引入的那个枚举**（"禁止人声、对白、旁白"），不越界到同分句后面的独立断言
   （"禁止音乐，旁白清晰朗读解说" → 旁白仍是违规）。
2. 否定词紧跟的词被否定（"禁止俯拍" / "无对白"）；**只以否定形式出现的正向要求不算兑现**
   （"相机禁止俯拍" → 俯拍要求缺失 → FAIL）。

## 6. 本阶段**不支持**的输入

写清楚比假装支持好：

| 输入 | 现状 |
|---|---|
| 任意散文一句话直出提示词 | **不支持**。必须由 Agent 理解后写 `intent-handoff/v1`。 |
| `compile_text_input.py` 的文本解析 | 只认 `镜头N 时长 描述` 这类显式行，**不是自然语言理解引擎**。 |
| `task_type: rework` | 未实现，必须报错，不得静默降级为 `full_film`。 |
| `prompt_only` 下要参考图/图生视频 | 不在本阶段范围：须先按 `references/production-compiler.md` 补齐素材。 |
| 生成媒体 / 导出 / 点火 | 本阶段一律不做，需单独批准。 |

## 7. 包内规范可达性与历史来源（可核验，不伪造）

本包引用的 21 册 `统一基准` 已迁入包内作为历史快照；公开视图仅对私人路径/标识作明示脱敏，原始来源哈希保留，改变的目标哈希与 byte_identical=false 记入清单：
`references/unified-baseline/`（含 `samples/`），运行时只读包内文件，
不再打开外部私人工作区。历史来源使用不透明别名，SHA-256 记录在
**随包分发**的 `references/unified-baseline/MIGRATION_MANIFEST.json`，
仅作溯源与证据，不作为运行依赖。

索引随包可达并可现场核验：

```powershell
python scripts/verify_recovery_index.py
# 退出码：0 PASS · 1 FAIL（断链 / 哈希过期 / 未迁入）· 2 索引缺失
```

活动权威仍为包内 `references/*` 与 `scripts/*`（每册的 `in_package_substitute`）；
迁移快照 `authority=historical_snapshot_not_active_authority`，**不覆盖、不替代**
活动规范，也不与之冲突。L2 单一权威源保持。

包内**已经可用**的对应物：

| 缺失/历史外部册 | 包内迁移快照 | 包内活动权威 |
|---|---|---|
| `01_统一状态机与交付契约.md` | `references/unified-baseline/01_统一状态机与交付契约.md` | `SKILL.md` §"最小状态链" + `references/run-sheet.md` §一 |
| `10_输入到计划编译器规范.md` | `references/unified-baseline/10_输入到计划编译器规范.md` | `references/production-compiler.md` |
| `11_提示词包与五类模板.md` | `references/unified-baseline/11_提示词包与五类模板.md` | `references/production-compiler.md` §2–§3 + `scripts/compile_prompt_packages.py` |
| `13_提示词门禁与失败诊断.md` | `references/unified-baseline/13_提示词门禁与失败诊断.md` | `references/production-compiler.md` §3 + `scripts/production_capability_gate.py` |
| `samples/B1～B7` | `references/unified-baseline/samples/B*.md` | `references/examples/delivery-samples.md` |
| 旧全库 `evals/scenarios.md` | 不可恢复（仅新 partial） | `evals/scenarios.md`（本批新建，仅阶段一意图交付验收场景） |

`evals/scenarios.md` 旧全库仍不可恢复；本包新增的 `evals/scenarios.md`
仅覆盖 INTENT-DELIVERY-01 阶段一验收场景，明确为本批新建，不声称恢复旧文。

## 8. 自检

```powershell
python scripts/compile_intent_delivery.py --self-test
python scripts/verify_delivery_semantics.py --self-test
python scripts/verify_recovery_index.py
python -m unittest tests.test_intent_delivery -v
```
