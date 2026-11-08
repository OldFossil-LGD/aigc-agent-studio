# Key Decisions · 续（明确不改 / 加条规则 / 历史册名对照）

> **何时读**：`key-decisions.md` 前两节读完后。
> **读完回哪**：回 `key-decisions.md`。
>
## 三、明确不改（连同理由，避免以后重复讨论）

| 不做 | 理由 |
|---|---|
| 拆成 20 个小 skill | 用户要"一句话跑完三步"；拆分只增加调用负担 |
| 允许跨 skill 文档重复（抄 Higgsfield） | 他们需要"独立可安装"；我们不需要，重复只是维护债 |
| 提示词一律写英文（抄 Higgsfield explainer） | 与用户"只给中文"冲突；**且官方自己写了例外**：`Chinese-developed models like Seedance and Kling sometimes respond better to Chinese for nuanced motion`——我们用的即梦/Seedance 正属该例外（见 C6） |
| 把"升格/慢动作"一律禁用（抄短剧口径） | 那是抖音竖屏打戏的完播率口径；写实短片不是同一场景 |
| 把影片锚点（如"像《铁西区》的光"）直接写进提示词 | 会被平台 IP 过滤拒词（Higgsfield 的终端状态码含 `ip_detected`）；必须翻译成风格描述 |
| 加 `allowed-tools` 字段 | Higgsfield 全线写 `Bash` 是因为他们只调 CLI；我们不调外部 API，加了可能误伤其他工具 |
| 抄 Cinema Studio 的 50+ 调色模板 / 6 灯光预设 / 10 摄影师运镜风格的**具体值** | 那是**平台私有资产**，我们拿不到具体参数，抄不了。**要学的是"参数化"这个做法**（写成设置映射表），不是那些值 |
| 抄 229 条运镜预设的**名字表** | 只有英文名，且含 66 条特效类（与本 skill 的"运镜"不是一回事）。**要学的是分类法 + "运镜/特效正交可组合"这个设计**。**2026-09-12 补充**：`camera-movement-library.md` 已建立**六族分类谱系**（其中收录 108 种运镜的**命名对照**作术语索引，未复制任何原文）；**收录名字是为了查全，不是为了堆名字**——真正落地的是"每族给本质定义 + 感知结果 + 时长下限" |
| 把 Seedance 的 `@character / @style / @motion / @audio` 当通用语法 | 这是**平台专属**的角色命名。写进提示词前必须先确认 Updream 是否识别，否则是添乱 |
| **给"人物真实性五问"加机器检查项**（`audit_prompt.py` / `ai_smell_check.py`） | **做了会造误报，而误报比漏报更隐蔽（E23）**：① 「面部不对称只许一处」的词表是开放的——`从左到右`（**运动方向**）、`亮面在右脸`（**光位**）都是正当写法，正则必误伤；② 「微动写在人物层」若按"画面…晃"判，**会把统一提质层里合法的那句「画面带轻微的机械片门晃动与手持呼吸，从不完全静止」判死**——**每条提示词都会报 FAIL**。**替代（已在库）**：判据留在 `SKILL.md` 静态判据 + `character-realism.md` §八 自检五问 + `evals/scenarios.md` 场景 25——**人工判得比脚本准**。**要真做，先按 E23 拿全库真实语料量一遍 + 补守正/守负双向用例**，不许直接往表里加词 |
| **为每个新 reference 在 `start-here.md` 单独加一行入口** | 该文件**顶格 300 行**，且它是**用户手册**（用户看得懂的话）——压缩它去换"一个内部文档的独立行"，与 L2"不得移除功能性内容"相抵。**正确做法是行内改写 + 把"用户会说的症状"补进给用户看的那张速查表**（→ `pitfalls.md` PF13） |

## 四、怎么往里加一条

新结论进来时，**先回答两个问题**：

1. 它是 Established 还是 Conventional？
   - 有对照实验数据 → Established，**必须附上证据与日期**
   - 只是"多数来源这么说" → Conventional，写进第二张表并注明"待测"
2. 若要推翻一条 Established，格式必须是：**"X 优于 Y，因为 N 次运行里指标 M 得到 Z%"**。拿不出数字，不动。

---

## 五、E160–E163 · 资产标准统一（2026-10-31）

| # | 结论 | 处置 | 依据 |
|---|---|---|---|
| E160 | **数量争议的根源是对象混淆**：设计板 / 投喂参考 / 机位视图被同一个"资产视图"称呼，于是十格、三格、4–5 视角、正反两张各说各话 | 新建 `asset-standard.md` 作**唯一裁决**；旧口径 7 处按该册 §7 表改判 | 平台审计 A1/A2 + 本库既有实测；**未新增平台事实** |
| E161 | **三视图默认是设计板，不是投喂件**；"三格里的胸上特写能当身份锚点"**不成立** | `asset-standard.md` §3.3 收窄为"封装通道成立时才可作辅助"；checklist A3 从【必出】降【条件出】 | 官方 R3（三视图会污染、不作唯一锚点）+ 平铺"两张脸"观察 |
| E162 | **场景主锚点＝平面图**；空镜＝某个机位的 view（`empty_plate`）；**3/4 与正对中轴都只是机位选择**，不是资产硬规则 | §1/§5；checklist B1/B2 改判；`asset-consistency.md` 一·补③ 的裁决改写 | checklist-part2 §12.3（用户定案）+ 平台审计 A1 |
| E163 | **视角由镜头需求决定**，且资产清单可以机检——"剧本→清单→视角→投喂"不再靠人记 | 新增 `scripts/asset_manifest.py`（派生 / 对账 / 投喂三层，`--self-test` 4 例）；挂进 `lib_doctor` ⑤ | 本库自建（`asset-standard.md` §9） |
| E164 | **人物资产改七件套（用户定案 2026-10-31）**：脸部特写取代正面半身；前/后/左/右/俯五视角＋无头身体**全部作为资产被引用** | `asset-standard.md` §3 整节重写；checklist A2/A3 改判为「1 张特写 + 5+1 张视角」；manifest 角色槽位改为 face/view/body；**每镜带脸图 ≤1** 的硬规则保留 | 用户指令；平铺多视图的下降段风险按 §8 记录并接受（对冲见 §3.2） |
| E166 | **资产系统按四层模型重设（用户 2026-10-31）**：L1 身份核心 / L2 外观版本 / L3 镜头态 / L4 连续性；资产＝带版本、出处、状态的对象，不再是散图 | `asset-standard.md` 整册重写；checklist A2–C1 标 L1/L2；`schemas/asset_system.schema.json` | CHARACTER_PIPELINE_PLAN v1.0.0 §2/§4；**按本库口径改编，未引入服务层** |
| E167 | **道具与场景沿用同一套层与状态机**：道具 L1 主图+工艺锚点 / L2 开合亮灭等状态；场景 L1 平面图 / L2 时段灯态+机位库；两者 L4 由剧情事件驱动 | `asset-standard.md` §2/§4/§5 | 同上；子地标按 L1 单出 |
| E168 | **引用计划与四层 QC 成册**：每镜一份 ReferencePlan（策略版本/理由/排除项），QC 三判定含 INDETERMINATE，错误码回退到站而非自动重抽 | 新增 `asset-pipeline.md`；`asset_manifest.py` 增 layer/status/origin/version/FEED_UNAPPROVED/IMMUTABLE_CONFLICT 检查 | 规划文件 §6–§9；阈值为可配置起点 |
| E169 | **按陌生审计修复 10 项**：① 统一 canonical 字段（asset_id/parent/reference_plan）并让脚本自检加载 Schema 校验全部 fixtures ② self-test 改为完整元组 + 34 例变异 + 覆盖率断言（34/34 码） ③ 造型只产 L2、脸不随造型 ④ 投喂表改「主挂/补脸/带脸数」，背面俯拍允许 0 张脸 ⑤ locked 降为 approved∧artifact_ready ⑥ 场景连线表按 L1/L2 重写、平面图不得当场景投喂 ⑦ 色板基准归脸部特写第 7 块、设计板降为人读副本 ⑧ 七件同人降 INDETERMINATE + parent 离线判据 ⑨ covers 按视角个数计脸 ⑩ sha256/qc_report_id 真校验 | `asset-standard.md` §3.2/§3.5/§9 · `asset-pipeline.md` §3/§4/§6 · `asset-and-stage-checklist.md` §六 · `production-ledger.md` §二 · `block-playbook-asset.md` §7 · `schemas/asset_system.schema.json` · `scripts/asset_manifest.py` | 两份陌生审计报告（%TEMP%\audit_content.md / audit_contract.md）；修复后自检 4 fixtures + 34 变异 0 失败 |
| E172 | **外部 crew 只走交换视图（2026-10-31）**：`filmdsl/v1` 是 01–04 的派生投影，形状对齐 CineCrew 的 SceneBlueprint（metadata/global_style/assets/memory/clips 四层）；五层各一写者，crew 十角色按表换算到本库十站；回修梯度改为「约束字段 → 关键帧提示 → 视频提示 → 上游调度」 | 新增 `filmdsl-interchange.md`；`scripts/filmdsl_bridge.py`（export / check 重投影逐键比对）；`schemas/filmdsl.schema.json`；fixtures `agentic_backends` 10 例 | CineCrew（ECCV 2026）论文与仓库里的 FilmDSL 与 dailies 顺序；本库 01–04 既有字段，未新增平台事实 |
| E173 | **ViMax 只做站 6.5 的第三条执行通道（2026-10-31）**：工作流必须显式点名且无默认值；`script2video` 要实存剧本、`novel2video` 要小说原文，`idea2video` 取自 01 goal 时标为隐含源；会话目录只放本库源、不预造后端产物；`render.run` 与 `generation_authorized` 恒 false | 新增 `vimax-runtime.md`；`scripts/vimax_backend_compile.py`（11 项自检）；`schemas/vimax_job.schema.json`；`run-sheet.md` 站 6.5 补第三条通道 | HKUDS/ViMax 仓库的 workflow 协议与 `.working_dir` 产物账本；本库 L7 批准纪律 |
| E174 | **剧本拆解插在站 4 与站 5 之间（2026-10-31）**：`10_breakdown.json`（角色/道具/场景/镜数/相机树/feed_plan）→ `11_compiler_input.json` → 站 6 编译；认加粗 slugline、人物表括号别名、`**名字**：台词` 三种版式；拆解**不写视觉描述**，缺描述的资产停在 `PROMPT_UNRESOLVED`（站 5 的活）；未写景别记 `UNSPECIFIED`，不许编 | 新增 `script-breakdown-bridge.md`；`scripts/breakdown_compile.py`（14 项自检）；fixtures `breakdown/`；`run-sheet.md` 站 5 补"先拆解"；`--asset-spec` 作站 5 接口 | CineCrew 的资产先行与枚举 + ViMax 的 shot_brief/相机树/`<角色>` 标记；本库 `asset-standard.md` 与站序 |
| E175 | **交付块序由库定，用户不选模板（2026-10-31）**：任何输入（含一句话）一律按 `block-spec.md` 12 块排；15_Canonical_Prompt 号文件 为统一标准视图，逐块标「已填 / 未给（缺什么→哪一站补）」，缺块不代写；13 号仍是受语义复核约束的交付正文，二者同源同正本，不许互改 | 新增 `scripts/canonical_prompt.py`（9 项自检）；`compile_intent_delivery.py` 增 15 号输出；`block-spec.md` 加口径banner；`stage1-delivery-entry.md` 与 `SKILL.md` 补两件并列 | 直接改 13 号会让 14 个契约测试红（实测 78→14 fail），故改为并存视图；把 13 改 12 块须先改写 `verify_delivery_semantics.py` |
| E176 | **十站默认标准化（用户 2026-10-31）**：每站绑定「必产 + 默认值 + 出口机检 + 豁免协议」，agent 不许随机也不许静默跳过 | 新增 `default-standard.md`；`stage_gate.py`（S1–S7 出口门，自检含空话/缺失/豁免三例）；挂进 lib_doctor；SKILL.md 默认链与 run-sheet 每站出口 | 用户要求"所有环节默认标准化，不再随机或偷懒"；默认值取本库既有实测与平台口径 |
| E177 | **提示词系统的权威上移为 Production IR（2026-10-31）**：`production-ir/v1` 为唯一事实源，12 块改为由它确定性编译；字段级 ValueWithProvenance（七种 source_type）；空镜写 `人物：不适用`；第 10 块【摄影机】=【运镜】；【结尾留白】并入第 12 块 `end_state` | 新增 `schemas/production_ir.schema.json`；`scripts/production_ir.py`（build/validate/render，14 项自检）；新增 `prompt-ir-contract.md` 与 `docs/prompt_audit.md`；`audit_prompt.py` 补 `BLOCK_ALIAS` 与空镜豁免 | 《12 块提示词系统通用化改造建议书》v1.0 §3/§4/§6/§10；实跑：真实产物建 IR 命中 SHOT_PRESENCE_CONFLICT 与 PROJECT_DURATION_MISMATCH |
| E178 | **门禁补三条口径（2026-10-31）**：① 空镜/无人物镜头不再判生理活性与面部证据（此前每个空镜 3 条假 WARN）；② 块 7 允许写 N/A，不判缺身份锚点；③ 摄影机/运镜双名同块 | `scripts/audit_prompt.py` 三处；示例 `提示词模板示例_12块_v4` 由 rc 4 → **rc 0**；audit 自检 78/78 | 实测：v4 在改动前 6 WARN（3 条空镜误报）、改动后 0 WARN |
| E179 | **连线顺序以成片画布为准修正（用户 2026-10-31 要求读 THE TURN / 抵达之前）**：两张成片的第一张参考**永远是空间/首帧**，不是脸——THE TURN 4 张＝场景锁+3 角色、9 张＝3 空间+2 站位+特写位+道具+3 角色、C06 25 张；抵达之前 S05 2–3 张＝静帧+角色+环境。**参考张数由复杂度决定，2–4 只是资产生成建议** | `asset-pipeline.md` §2 顺序四条改写 + 实拍口径；`asset-standard.md` §3.2/§6 张数与顺序注；`default-standard.md` 每镜参考默认值；`asset_manifest.py` 主参考不再强制为脸/视角（只排除无头身体与设计板） | LibTV 画布 11127ba0（595 节点）· 9acfd448（762）· b8e8d92b（26）只读抽样；不改用户的画布 |
| E180 | **全量研读后的其余修正（用户 2026-10-31「除了七件那条，其他全部修改」）**：① 首帧用 `first_frame` 声明且必须第一；② 新增顺序嫌疑 `ORDER_SUSPECT`（有空间图却不排第一）；③ `wiring_plan --integrity` 体检重名/参考无入边/顺序与边不一致/悬空端点；④ 音频不占 imageList、走 audio→video + {{Node}}；⑤ fixtures 全部改为空间优先 | `asset_manifest.py`（3 个新码 + 47 例变异）· `wiring_plan.py`（integrity + 自检）· `libtv_canvas_build.py`（first_frame 校验）· schema `first_frame` · `asset-pipeline.md` §2/§7 · fixtures | 两张成片画布 1357 节点全量数据；实测：抵达之前 100 个重名、22 参考无入边、8 顺序不一致、12 悬空端点 |
| E165 | **七件可按脸数合并成节点（用户 2026-10-31）**：前+后 / 左+俯 / 右 / 无头 → 加特写共 5 节点；**四合一（3 张脸）仍禁**，只有封装主体通道例外 | `asset-standard.md` §3.1 合并段；manifest 支持 `covers[]`；fixtures A/D 已按合并跑通 | 脸数≤1 的既有判据，不新增平台事实 |

**★ 记账边界**：本轮**不新增 REA 台账 claim**——没有新的平台事实，只有库内口径收敛；按 `governance-law.md` L8 记「库规」，不按「插件实测」记。

---

## 附 · 历史册名对照（历史条目里出现的旧名 → 现名）

本表只做对照，**不修改历史条目**（改动历史会篡改记录）。

| 历史条目里的旧名 | 现在的册 |
|---|---|
| `prompt-engineering.md` | `prompt-ops.md`（提示词运营纪律） |
| `acting-performance.md` | `performance-craft.md`（表演工艺） |
| `performance-micro-beats.md` | `performance-vocabulary.md`（微节拍与眼生命） |
| `drama-scaling-shortform.md` | `drama-scaling.md`（时长与结构量级） |
| `style-cores-c.md` | `style-cores-c1.md` 到 `style-cores-c5.md`（C 卷五册） |
