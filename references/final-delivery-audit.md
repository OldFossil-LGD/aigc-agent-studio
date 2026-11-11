# 交付前最终审计

> **何时读**：任何影视任务准备交付时，完成其他适用工序后读本册。文本审阅、提示词、资产与制作计划、画布、成片都要走到这里。
> **读完回哪**：有问题回责任工位修复，再重新审计；通过后交付。入口见 `run-sheet.md`。

## 最后一道环节

Agent 先冻结本次待交付版本，按用户原话、站 0 契约和最新修订逐项审阅实际交付物，再运行机器审计。审计报告记录当前输入和产物哈希。修复、重编译、替换素材、调整节点或改正文之后，旧报告失效，重新跑整轮最终审计。各工位已有检查继续保留，最终审计在它们之后。

未通过时停止交付，不向用户报“已完成”。缺证据、工具不可用、没有检查到对象和无法判断的关键项均保留为阻断。只审阅文本时，真实媒体效果属于后续范围；交付成片时，媒体审阅是必需项。

## 逐项审阅范围

| 层面 | 必须核对的实际对象 |
|---|---|
| 用户真实需求 | 原话、Creative Intent Contract、最新修订和实际结果逐项对照；时长、画幅、风格、声音、必有禁有、交付终点和委托边界均覆盖 |
| 内容与创作 | 故事因果、信息与情绪、人物动机、动作可达性、空间与时间、连续性、视觉工艺、声音和剪辑；按当前任务选择适用册全文核查 |
| 完整性与可用性 | 清单中每个文件可打开且有正文；每镜、每资产逐项有对应产物；提示词能直接使用，无占位、空块、内部注释和遗漏；同源视图与正本一致 |
| 结构与执行 | 节点身份、类型、角色、数量、父子依赖、引用顺序、设置与实际提示词；回读平台实际值，与当前计划逐项对账；已有画布中的无关节点保持范围外 |
| 来源与证据 | 当前任务、引用原文、审阅依据和实际产物绑定；检查范围覆盖所有需求，读回、来源哈希、版本与修订有效；历史例子按实际适用性使用 |
| 实际媒体 | 逐镜看片听音，核动作、人物与空间连续性、穿帮、口型、声音、切点、字幕、容器和交付规格；使用 `review-passes.md` 与现有四层审阅回执 |
| 交付状态与范围 | 交付清单和停止点吻合；草稿、规划、已建图、已生成、已审阅分别标明；链接与本地路径可访问，关键未验证项不能包装成完成 |

Agent 逐项留下短结论、实际证据位置和发现的问题，写入现有 `creative-review/v1` 的 consideration、decisions、applied_to 和 unresolved。艺术与意图判断由实际审阅承担。工程检查器覆盖其已实现的约束，证据绑定通过不能替代看片、听音或创作判断。

每个待审文件都须有实际 applied_to 位置。一个文件中的片段不能代替另一个文件的审阅。文本审阅中明确引用的原文和代码示例可以包含问题标记，待交付正文中的独立 TODO、TBD、待补等段落及附注仍会阻断。

使用现有检查器补足当前交付物的专项检查。提示词用 `audit_prompt.py`、`ai_smell_check.py` 和独立语义验收；多镜排镜表用 `shotlist_lint.py`；当前图与资产用既有图门禁和清单检查；成片用技术 QC、四层与六遍审阅。把适用检查的实际结果和例外理由纳入审阅，不以“总表通过”代替逐项检查。

## 机器审计入口

Agent 根据本次明确的交付终点写审计清单，用户无需填写 JSON。使用当前项目的任务、文件和回执，路径以清单文件所在目录为基准。

```bash
python scripts/final_delivery_audit.py audit.json --report delivery/final_audit.json
```

退出码为 0 才允许继续交付。非零时读取 checks 中的具体阻断项。脚本只读交付对象和平台，只写指定的审计报告。

共同字段如下。

```json
{
  "audit_format": "final-delivery-audit/v1",
  "kind": "text",
  "task": "task.json",
  "artifacts": ["review.md"],
  "review": "creative-review.json",
  "capture_root": ".context_reads",
  "session": "当前实际会话标识"
}
```

kind 与真实终点对应，不能把提示词任务改称 text 绕过提示词检查。

### 权威交付契约

Agent 应把已理解的交付终点、必交文件、目标项目和适用检查写入 task.delivery，使用 endpoint、required_artifacts、project_uuid 和 required_checks。required_artifacts 接受文件名或带 name、requirement_ids 的对象。明确指定的目录也是交付要求。自由文本中直接命名的交付句只作辅助识别，复杂或未命名的自然语言需求仍由 Agent 转成结构化声明。

可另传 contract 文件，格式为 delivery-contract/v1。契约可以增加必交对象和检查，不能降低任务已明确的范围或改换目标项目。空白豁免原因无效。审计范围或目标不匹配时，先阻断，再回任务与契约修正。

任务明确声明的 required_checks 不能由额外契约单方面豁免。用户确实改变范围时，先更新保留原话来源的任务，在 task.delivery.exemptions 中记录对应原因，再重新审阅。

film 默认需要画布审计。外来成片审阅没有画布时，可在契约 exemptions 中给 canvas 写明实际原因，无须虚设画布 UUID。任务已指定的项目、声明参数和当前媒体仍须按适用范围核对。

| kind | 额外字段与检查 |
|---|---|
| text | 文本审阅或文本交付；检查实际正文、当前来源及决策证据 |
| prompt | prompt_dir、prompt_markdown、grill；读回 01 合同、02 资产图、03 镜头图、04 提示词包与实际 Markdown，重跑生产门禁、GrillMe 与语义验收 |
| plan | prompt_dir、grill；重跑 01–04 的生产角色、图依赖、提示词包与 GrillMe 门禁 |
| canvas | canvas_plan、project；重新读取实际节点，核对提示词、类型、模式、设置、引用与资产产物 |
| film | video、media_record、media_review；对实际视频重跑技术 QC 与现有媒体审阅绑定；涉及画布时同时提供 canvas_plan 和 project |

artifacts 是本次审计的实际文件清单，包括决定结果的计划和正本。prompt/plan 必须列出 01–04，prompt_markdown 和 canvas_plan 也必须在清单内。同 basename 的文件有歧义，应先整理成无歧义的交付包。JSON/JSONL 会实际解析，空文件与纯占位正文会阻断。

creative-review 的 artifact_sha256 按这份文件清单的 basename → 实际 UTF-8 正文映射计算，正文换行沿用现有 Path.read_text 的 LF 归一方式，审计输入哈希仍绑定原始字节。二进制 video 对应值使用 `sha256:<实际十六进制摘要>;bytes:<实际字节数>`。media_record 与 media_review 的字段沿用 `film_qc_gate.py` 和 `review-passes.md`，绑定实际视频哈希与版本。

### 正式提示词的两阶段交付

1. 带当前 --grill、--review、--capture-root、--session 编译。满足前置门禁后生成 13_Final_Prompt.pending.md。缺最终审计时返回 FINAL_AUDIT_REQUIRED，候选仍留在审计阶段。
2. 建立独立的最终审阅回执，绑定 01–04 和 pending 文件的实际正文。它与编译器使用的 prompt_packages 正本回执分别绑定各自对象，不能混用哈希。
3. audit.json 使用 kind=prompt，prompt_markdown 指向 pending，artifacts 包含 01–04 和 pending。运行最终审计，保存脚本产生的完整报告。
4. 使用同一任务与目录重新编译，并传 --final-audit-report <报告路径>。正式出口核对任务、prompt 终点、候选字节和所有审计输入，再按报告中的 manifest 重新执行审计，通过后才提升为 13_Final_Prompt.md。

手写 PASS 标签或只给正文哈希不能放行。任一输入改变，先重新审阅并生成当前报告。报告中的 manifest 路径、task_sha256、检查结果和输入哈希须由脚本实际产生。

### 专项检查执行回执

required_checks 会合并终点默认检查和任务、契约额外声明。review、production、prompt、canvas、film 使用已有检查器。shotlist、prompt_style、ai_smell 分别调用排镜、提示词块和 AI 味检查器，manifest.specialists 中为每项提供 path，文件须在 artifacts 中并已审阅。shotlist 的 mode 为 cut 或 gen，prompt_style 可用 asset=true。未识别、缺参数、未执行、超时或未通过的必需检查会阻断，不能靠漏填清单跳过。

例如，task.delivery.required_checks 声明 ["shotlist"] 后，manifest 增加 specialists.shotlist={"path":"shotlist.md","mode":"gen"}。脚本记录真实退出码和输出，required_check_execution_receipts 汇总所有必需项。检查器的 WARN 和未扫描状态需要处置，不能当作 PASS。

canvas 终点可交付尚未生成的画布，引用资产暂无媒体时报告保留警告。film 终点会严格要求已引用资产有有效产物。技术检查和媒体回执任何一项缺失、失败或未验证都会阻断成片交付。

画布对账以当前计划认领的节点为范围，其他任务节点保留在范围外。声明的模型、settings 和 position 会参与核对。position 的 x/y 进入 CLI 创建坐标，w/h 用于计划尺寸与实际尺寸核对；无效或非有限坐标先阻断。group、layout、order 等当前未支持字段显式阻断。审计前后读取认领节点的完整详情以检查变化。字段映射与模型名称/标识仍需在真实 CLI 回读中验证。

当前入口支持表中的文件与 asset-system 画布格式。其他平台、图格式或无法读取的交付物保留未验证，先使用其现有适配器取证，不能为了得到通过改写终点或伪造报告。脚本报告中的 creative_quality_verified 和 media_quality_verified 保持 false，具体审阅结论来自实际审阅及相应回执。

## 修复与复审

发现问题后，由执行 Agent 在用户已授权范围内自动修复，再重跑最终审计。

1. 本地遗漏、失效派生件和结构问题，回权威输入或原编译入口修复，再生受影响产物，不只修改报告状态。
2. 平台问题先重新读取目标节点与当前参数。已有授权覆盖且修复可逆时，按当前官方 CLI/MCP 契约修复并回读。删除重建、付费生成、重新点火、扩大范围或覆盖用户后续改动，先通过宿主询问工具取得对应确认。
3. 缺少事实、意图冲突或艺术判断不可确定时，不编造答案补齐。把真实分岔带回 GrillMe，用宿主原生询问工具收敛，再修复和复审。
4. 每次修复记录错误、责任层、修改位置和复审结果。同一失败重复两轮仍未收敛时，停止盲目重试，向用户说明阻断及所需信息。
5. 只有全部适用检查通过，且关键 unresolved 为空，才向用户交付当前已审计的版本。任何最后一分钟修改都要重新审计。
