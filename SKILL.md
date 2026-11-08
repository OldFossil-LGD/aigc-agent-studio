---
name: aigc-agent-studio
description: AI影视工作室。Use when：制作AI短片/长片、影视剧本、资产与角色一致性、分镜/故事板、影视提示词、风格化与声音设计、镜头生成工作流、剪辑交付、局部返工、作品反推/复刻，或操作LibTV影视画布。含写实及各类工艺渲染。NOT for：独立单张图片/海报、纯音频、一般写作或数据分析。
metadata:
  agent_created: "true"
---

# AIGC 影视工作室

先确认用户要停在哪里；只交提示词就停在提示词，不自动变成画布或成片任务。
用户不用填写JSON：Agent理解原话并形成现有intent交接，脚本负责校验和机械派生。

## 共同边界

- 先读唯一治理源 references/governance-law.md 的L1/L2/L6–L8；读取方法见 references/context-reading.md。
- 用户显式值、参考素材用途及适用例外必须进入当前任务的实际交付，不能被默认模板替换。
- 结构/工程、文本创作判断、实际媒体效果分别报告；未验证就保留未验证。
- 点火、媒体生成或其他付费动作必须有对应显式批准；已发起任务先只读回查，不重复提交。
- 交换视图（`filmdsl/v1`）与后端作业单（`vimax-job/v1`）都是**派生件**：不授权生成、不替代 01–04 与 08；其 `origin.artifacts` 与权威 sha256 不一致即视为过期。

## 制作执行链（按已确定的交付终点进入）

已确定交付终点包含**画布就绪或完整制作**时，执行：
拆解（`breakdown_compile`）→ 补资产事实 → **`libtv_canvas_build --compose`（资产描述由脚本组装）** → `asset_manifest` 对账 → 建节点＋**两类边**（L2←L1 派生边、镜头←引用计划顺序）→ `--verify` 回读。
剧本审阅、文本改写、资产清单和提示词分别停在用户要求的交付物；提示词任务使用 prompt_only。
“不要生成”只限制媒体生成，不自动改变交付类型；画布操作按用户要求进入。终点不明确时先确认。生成始终单独批准。
**已进入的制作站出口跑 `scripts/stage_gate.py --stage Sx`；适用站的跳过按 `references/default-standard.md` §4 记录用户原话。** 文本任务与终点之后的站不适用，未进入不记为通过。

## 按交付终点进入

| 用户要什么 | 必读入口与真实执行路径 |
|---|---|
| 可复制提示词，含空镜/风格化/人物镜 | references/stage1-delivery-entry.md → scripts/compile_intent_delivery.py；工艺消费见 references/craft-delivery-entry.md。**块序由 block-spec.md 裁决，用户不选模板**：一次出 13（交付正文）+ 15（统一 12 块标准视图，scripts/canonical_prompt.py） |
| 用户只说一句话要做一条片子 | **唯一入口 scripts/studio_run.py**（拆解→编译→IR→12 块视图一条命令跑完，产物 10/11/12/15/16 自动落盘）；用户不需要知道 IR / 12 块 / 拆解单这些词；停下来就地说明缺什么、回哪一站 |
| 要改提示词系统本身（块契约 / 编译器 / 校验规则） | **先读 references/prompt-ir-contract.md**（IR 唯一事实源、来源与锁定、12 块映射、规则清单）＋ docs/prompt_audit.md（审计与缺口）；再用 scripts/production_ir.py build/validate/render；不改 13 号排法前先看审计 §6 |
| 单镜或完整影视生产 | 完整读 references/studio-workflow.md 与 references/run-sheet.md，再用 references/production-compiler.md 的主编译链 |
| 影视任务内的角色/道具/场景资产 | **先读 references/asset-standard.md（四层 / 版本 / 状态 / 数量的唯一裁决）**，再读 references/asset-pipeline.md（引用计划与四层 QC）与 references/asset-prompt-spec.md；**清单→画布用 scripts/libtv_canvas_build.py（七件＋两类边，默认 dry-run）**；先按 references/style-library.md 确定风格，不给空镜补人物 |
| 反推、复刻、蒸馏或盲测 | 先读唯一 references/reverse-fidelity-contract.md，分别声明mode、deliverable、source_access；副本不能升格原项目，未解不编 |
| 局部返工、版本变化、审片回执 | references/offline-continuity-entry.md 与 references/review-passes.md；图失效建议不等于已执行返工，绑定PASS不等于媒体已审 |
| 剧本要拆成资产与分镜（"哪些资产、多少镜、每镜什么景别"） | **唯一入口 references/script-breakdown-bridge.md**（认哪三种版式、字段契约、未解怎么记），再用 scripts/breakdown_compile.py 出 10/11/12 三件；站 5 用 asset_manifest 对账，站 6 用 compile_production 编译 |
| 与外部 crew / 别的 agent 系统交换分镜契约 | **唯一入口 references/filmdsl-interchange.md**（派生视图与权威分界、五层归属、crew 角色换算、回修梯度），再用 scripts/filmdsl_bridge.py 导出与对账；`filmdsl/v1` 不是新权威 |
| 交给 agent 后端跑到成片（ViMax / 同类 runtime） | **先读 references/vimax-runtime.md**（工作流点名闸门、会话产物权威、十阶段绑定、跳过≠通过），再用 scripts/vimax_backend_compile.py 出**不执行**的作业单；点火仍须显式批准 |

prompt_only停在Prompt Package与草稿/受审阅门控的正式Markdown：不产05/08执行计划，不建画布、不生成媒体。
正本是prompt-package/v1，最终文档从同一正本派生；未知格式或未支持task_type不得静默换成full_film。

## 最小状态链

定义与停止点见 references/studio-workflow.md 开篇“最小状态链”及 references/run-sheet.md §一。

## 交付前自检

按 references/studio-workflow.md 的分镜交付检查及 references/run-sheet.md 对应工位执行；提示词交付另按 references/stage1-delivery-entry.md §4 独立验收。

## 任务读取计划

用 scripts/knowledge_routes.py 联合任务、全部适用features与结构化intent，不能在空镜/无声/固定机位/风格间任选一个。
原文中发现额外直接依赖或例外时加入extra_refs；未覆盖的需求必须保留未解。
完整原文只在同会话、来源未变且实际读过有证据时复用；hash或路由命中不能当作已读。
该工具仅规划来源和核对机械证据，不解析任意散文、不证明理解或生产就绪、不授生成权限。

调用示例与回执格式统一见 references/context-reading.md。

## 正式交付门禁

先按 references/delivery-review.md 完成全目录知识域的情境适用性判断，相关来源全文阅读并记录简短创作依据与实际产物落实位置。目录、字节捕获和工程绿灯均不证明已经理解。
未具备当前任务与产物绑定的审阅证据时，只能给明确草稿，不能报正式交付；compile_intent_delivery 的 --draft 是离线调试入口，正式 Final 还须独立约束复核通过。纯文字审阅使用同一证据边界，不强迫进入媒体生产链。
未识别的创作字段不得静默丢弃，相关知识、依赖或判断有缺口时保留未解；不得为过门禁自行刷新目录、虚构读回、捏造选择依据或给自己授予生成权限。

## 知识与事实

工艺、平台事实、用户偏好、库规、历史观察和例子按治理L8分型。
当前平台能力/参数需当前官方接口或回读；历史失败率、可用率、抽卡次数不是当前通用保证。
不确定的旧偏好保留待确认；明确风格、声音、机位与同框锁定项优先于工艺默认建议。
完整工作流、风格/动作/声音/剧作等全部原目录在下列唯一导航册；按任务选中后全文读，不截尾。
旧outputs/统一基准指针按stage1-delivery-entry.md的包内恢复索引解析，不依赖私人工作区。

<!-- library-index: references/studio-workflow.md -->
全库导航与完整片工作流：references/studio-workflow.md（旧入口迁移，旧活跃行号引用改指该册）。
改库/发布仍需全文件索引、数字、依赖、行号与既有回归核验，不以某任务计划代替全库审计。
