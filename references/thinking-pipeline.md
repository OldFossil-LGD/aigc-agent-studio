# 思考流程总册 · 板块序 × 四步法（检索 → 思考 → 选择 → 输出）

> **本册管"站内思考"，`run-sheet.md` 管"站间顺序"——两册配合，不互替。** 凡接到一个板块的任务（剧本 / 资产 / 分镜 / 声音 / 画布…），**按本册对应节的四步走完才算做完**；跳过任何一步必须**显式声明**（"本任务跳过 X 板块的 Y 步，因为…"）——**不声明的跳过＝静默＝违例**（历史上所有"学了没用上"都从静默开始）。
>
> **流程骨架（R51 审计修订）**：**Step 0 廉价闸门（30 秒）→ 检索 ⇄ 思考 → 选择 → 输出 → 验证半步**；整板块交付另有两条回路：**思考→检索**（发现缺知识先回检索）、**验证→选择/思考**（门禁 FAIL 改方案与判据，不是只改词）。
> - **Step 0 只问三句（否决型判据前置）**：① 题材/合规有无一票否决（可行性红线）？② **交付终点与验收人是谁**（提示词 or 成片；中途改终点＝变更，走 §12.8）？③ 任务量级（决定本节裁剪幅度）？**闸门答不了（brief 含糊）→ 唯一合法动作是问人，不是猜。**
> - **四步定义**：① **检索**＝动笔前先查指定册（定向，不翻全库；改口径前先 grep 全库防另起定义）；② **思考**＝把"必想清单"逐项过一遍（**清单同时是检索的提问单**——带着问题去查，两步时间上交织、**台账上分行**）；③ **选择**＝用"判据"做取舍，**每项取舍留一句依据**；④ **输出**＝产出物 + 过指定门禁（**读退出码：0 过 / 1 FAIL / 3 没扫到≠过**）+ 留痕；⑤ **验证半步**＝机检 rc + **对外部系统自述的回读**（平台 Agent 说"已建好"必须回读核对）+ 产物与上游定稿对表。
>
> **量级适配（R51 修订：白名单制，防"口子变合法借口"）**：**可裁剪的任务类型只限白名单**——改错别字 / 改单句台词且不改变时长与镜头数 / 纯格式调整；白名单外一律全流程。**任何裁剪都不可裁掉最小核**：① 开工前对 `key-decisions.md` 与上游定稿的一次对表；② 产物 rc / 回读。**裁剪声明写在开工前**（含一句"本任务不改变 X、Y、Z"），不写进事后交付说明；事后发现改变了→按违例记账。新任务类型入白名单：先走一次全流程并在 `key-decisions.md` 登记后方可。

## §00 · 统一基准接口（先编译，再进入板块四步）

| 记录 | 用途 | 权威 |
|---|---|---|
| `production_record.schema.json` | 剧本、场景、镜头、资产、世界状态、审批 | A 路共享契约 |
| `graph_plan.schema.json` | 节点、边、分组、权威层、派生字段 | A 路共享契约 |
| `prompt_package.schema.json` | asset/storyboard/video/audio/composite 提示词包 | A 定 schema，B 填内容 |
| `gate_result.schema.json` | 门禁退出码、证据、债务和下一步 | A 定 schema，B/C 产出 |
| `claim_ledger.jsonl` | 平台事实、跨作规律、单作画像、craft prior、库规、例子、未知 | A 路 |

**B 路编译入口**：`10_输入到计划编译器规范.md` → `11_提示词包与五类模板.md`；人物/动作/灯光/风格/声音走 `12_创作工艺路由_人物动作灯光风格声音.md`；失败定位走 `13_提示词门禁与失败诊断.md`；语言、口型、字幕走 `14_语言口型字幕与本地化.md`。

**C 路执行入口**：图计划与分组走 `20_LibTV图构建与分组规范.md`；模型、成本、并发和恢复走 `21_模型成本并发与恢复规范.md`；回读与媒体验收走 `22_结构回读与媒体验收规范.md`；三作回归走 `23_三作与合成场景回归测试.md`。生成前用 `graph_plan_lint.py`，只读回归用 `three_work_regression.py`；`rc=3` 表示没验到，不是通过。

**编译顺序**：简单输入 → Production Record → Graph Plan / Prompt Package → 板块四步 → Gate Result。craft prior 必须进入 Prompt Package 或验收门禁，不许只留参考文章。

**离线生成包落盘后**：先跑 `scripts/render_offline_prompts.py <包目录>` 生成文档与哈希清单，再跑 `scripts/offline_package_lint.py <包目录> --schema-dir outputs/统一基准`；它检查重复 JSON 键、Production/Prompt schema、全链 ID/时长/引用/locked_text 对账、生成文档漂移、离线包无点火字段、视频提示词、声音表、时间线和 AI 味。失败先修，介质与成本 `rc=3/5` 按未验/不适用分账，不得冒充通过。

## §0 · 通用四步（任何板块开工前）

| 步 | 动作 |
|---|---|
| **Step 0** | 廉价闸门三问（见头部）：否决型判据前置——**先判"做不做/给谁/多大"，再花检索成本** |
| 检索 | ① `governance-law.md`（L1 全量检阅 / L2 整合铁律 / L3 改完回头核）② `pitfalls.md`（14 类操作错）③ `key-decisions.md`（已定结论先对表，别推翻有实测支撑的）④ `cheatsheet.md`（高频硬规则速查）⑤ `sources-and-credits.md`（授权红线）⑥ `start-here.md` + `start-here-part2.md`（用户向操作）⑦ 本板块对应节 |
| 思考 | 我在哪个板块？上游谁定稿了？产物给谁用？哪条门禁说了算？ |
| 选择 | 任务量级（整板块 / 单点修改）；平台（LibTV 首选 / Updream / WorkRally 并行通道 → `workrally-workflow.md`）；哪些定稿权可交平台 Agent（`agent-handoff-scope.md`：验收靠人眼可交、靠机检只取维度） |
| 输出 | 交付形态按 `SKILL.md` 交付规范（整合式、全中文、代码块纯净）；留痕进台账 / 账本 |
| ★静默点 | **不 grep 就动手**（另起重复定义）· **不读 key-decisions 就推翻默认值** |

## §1 · 接活与 brief（站 1–2）

| 步 | 内容 |
|---|---|
| 检索 | `feasibility.md`（可行性三问 + 题材优先序）· `drama-scaling.md`（量容量）· `drama-structure-models.md`（选结构）· `style-library.md`（风格编号）· `platform-matrix.md`（平台边界与预算） |
| 思考 | ① 一页 brief 五件齐了吗（时长画幅 / 可拍的主旨 / 交付物清单 / 难点预判+怎么绕 / **风格编号+量级系**）？② 题材踩了可行性红线吗（手 / 全身走 / 口型 / 多人 / 剧烈动作 / 画面文字）？③ 容量超吗（超了换模型不是删拍）？④ 交付终点是提示词还是成片？ |
| 选择 | 题材做不做得出来（做不好就绕：单主体 / 固定慢推 / 旁白）；结构模型（30–60s 只有四个能直给）；**未声明风格 → 默认写实系，风格化必须显式声明（系二描边 `stylized-look.md` / 系三工艺渲染公共层 `stylized-look-craft.md` + 打光哲学 `lighting-philosophy.md`——三系量级句互不通用）** |
| 输出 | 一页 brief 文本；预算与预期管理话术（素材 2–3 倍 / 后期 60–70%） |
| ★静默点 | **[全量] 交付终点与验收人未确认**——中途改终点让前面所有门禁口径失效（R51）· **[全量] 难点预判没逐镜列**（做到分镜才发现拍不出来）· **[全量] 风格"待定"带进下一步**（资产全重出） |
| 横切 | 预算（首报预估）｜问询（brief 含糊→问人不猜）｜条件路由（出海/多平台/试映→§12.9，Step 0 识别） |

## §2 · 风格定档（站 3，写任何提示词之前）

| 步 | 内容 |
|---|---|
| 检索 | `style-library.md`（入口·选取四步·量级路由）→ 选完 `style-package-matching.md`（**出资产之前必过**：族→方案包/禁忌/调制层）· `equipment-selection.md` → `camera-package-library.md` + `package-extended.md`（器材包）+ `camera-package-quickref.md`（选包速查·三问定档）· `film-stock-matching.md`（胶片×印片档）· `director-system.md`（导演六把尺子：参照核"只像画风、节奏声音不对"）· `style-package-matching.md` 之后 `tone-realism.md` |
| 思考 | ① 编号是哪条（247 条哪一卷）？② 量级系（写实 / 描边 / 工艺渲染——**三系量级句互不通用**）？③ 配哪个方案包、有没有禁忌？④ 全片三条一致性锚点是什么？⑤ 取过参照吗（`style-sources-*.md` ≥3 帧 ≥3 作品）？ |
| 选择 | 按叙事氛围反查；写实默认；**同一部片只用一个调色族**（`color-grading-styles.md`）；包给机制、档给味道 |
| 输出 | 风格编号 + 量级系 + 方案包 + 器材包 + 锚点三条（写进 brief 与账本）；**风格档＝V1，以 §4 首批资产验证为准（允许一次受控回环）**；**纯写实单子本节可压成 §1 的一行默认值（显式声明）** |
| ★静默点 | **[全量] 跳过 style-package-matching 直接出资产** · **[全量] 参照帧没截**（风格只靠印象写）· **[条件·有参考图时] 风格编号与参考图实际不符——只对编号没对实物**（R51；用 style-cards 判偏对图） |
| 横切 | 锚点（三条一致性锚点在本节定） |

## §3 · 剧本（站 4）

| 步 | 内容 |
|---|---|
| 检索 | `script-module.md`（M1–M12 交付契约）+ `script-format.md`（版式）+ `scripts/script_lint.py`；创意层 `drama-plotcraft.md`（十问，⑥⑦⑨⑩ 硬门槛）+ `drama-tropes.md`；写前 `writing-methods.md`；人物 `character-sheet.md` / `drama-character-arc.md`；冲突与台词 `drama-conflict-craft.md` / `drama-dialogue-craft.md`；开场钩子 `script-craft.md`（留人三件套+10 招）；题材 `drama-genre-casebook.md`；剧作入口与训练 `drama-library.md` / `drama-mastery.md`；写后诊断 `drama-script-diagnosis.md`（十五病）；**转提示词前 `drama-aigc-conversion.md`**；剧集/长篇另查 `drama-series.md` / `drama-episode-structure.md` / `drama-series-cn.md`（★ 平台剧本预设 §12：题材15/字段组5/结构8/热预设8） / `drama-anthology.md`；**谁写哪段 `script-agent-handoff.md`** |
| 思考 | ① 主旨一句话可拍吗？② 节拍表秒数总和=总时长？③ 人物 ≤3 且三维齐？④ 台词 ≤6 句且每句说得完？⑤ 无对白版独立成立？⑥ 十五病过了吗？⑦ 每场可写性甲/乙/丙（乙以下改写法）？⑧ 交接：我方初稿→Agent 定稿→三项复核（时长/生理/声音）→ Script V2？ |
| 选择 | 叙事交旁白不交演技；单主体优先；镜头按短写；容量超限→换模型；POC 判据：`drama-plotcraft.md` 创意十问 |
| 输出 | 按 `script-module.md` 的 L0/L1/L2 档位整合交付，日常默认 L1、正式交付用 L2。执行 `script_lint.py <文件> --level <档位>` 并核对退出码。L0 带最小版声明，提供诊断模块时包含副作用栏。 |
| ★静默点 | **[全量] 写完不跑 script_lint** · **[全量] 忘了 drama-aigc-conversion 直接进分镜**（剧作概念没翻译成可写行）· **[全量] 无对白版只在脑内删了台词、没真的独立试写**（R51） |
| 横切 | 锚点（人物基线句在此定稿）｜变更（剧本改版→账本新版本，§12.8） |

## §4 · 资产（站 5）

| 步 | 内容 |
|---|---|
| 检索 | `asset-prompt-spec.md`（三类写什么/字段继承/从 M11 派生）· `block-playbook-asset.md`（五段式协议）· `asset-consistency.md` + 续册 · `asset-and-stage-checklist.md` + `asset-and-stage-checklist-part2.md`（**标准清单：生成什么/几个/三档必要性**）· `asset-prompt-spec-part2.md`（背景布光/像素预算）· **LibTV 口径 → `libtv-op-manual-part3.md` §二十五 + `pipeline-cross-source-consensus.md`** · Updream 通道与【批量任务】格式 `updream-workflow.md` + `updream-workflow-part2.md` |
| 思考 | ① 风格三问答了吗？② 哪些实体 ≥2 镜要出图（只出现一次的不出）？③ 三类齐全、状态变化单独一版？④ 每图用途唯一？⑤ 人物多视图=设计稿不作参考素材；道具可拼多角度？⑥ 具名信号三偏离点写了没（数字只对表不进提示词）？⑦ 平台结构：母锚点唯一 / 派生锚点引母锚点 / 场景平面图→机位视图 / **资产按需不凑层**（单镜演练不建 A4 即范例）？⑧ 参考位与插桩计划好了吗？ |
| 选择 | 一张图一个任务；**三档必要性（必出/条件出/点名才出，跳过留痕）**；派生锚点默认只服务故事板/首帧、不扇出镜头层；人参考=干净正面+全身两张 |
| 输出 | 资产提示词（五段式，`audit_prompt.py blocks --asset`）**（未过 §5 前，本板块产物状态＝draft）**；LibTV：`create_node`（图参考前先 `modeType=image2image` · **left 数组序=参考位序·建时定** · 插桩每图一次+用途）· 账本锚点集登记 node_key |
| ★静默点 | **[全量] 资产清单与分镜表未双向核对**——镜头引用了不存在的资产 / 资产不知被哪镜用（R51·"缺图静默降级文生视频"的上游根因）· **[全量] 状态变化没单独一版**（模型会自愈回滚）· **[条件·LibTV] 忘 image2image 先行** · **[条件·LibTV] node_key 没进账本**（下游引用失据）· **[条件·LibTV] 官方模板字段不可用还硬试**（prompt_template 两条路径已实测全拒，三视图用自由文本+同一主体多视角并置声明） |
| 横切 | 锚点（node_key 登记账本锚点集）｜预算（本批生成数×单价→`libtv-billing.md`）｜问询（modeType 被拒→按 §12.3 追问工具面/能力层） |

## §5 · 参考闭环（站 5.5，硬门禁）

| 步 | 内容 |
|---|---|
| 检索 | （**本节＝§4 产物的放行门**）`production-ledger.md`（§二放行门 / §三战斗矩阵 / 台账）· `asset-consistency.md` |
| 思考 | 每个本场所需资产读到 `locked` 了吗（跨角度/跨景别/真实场次光/同框搭档，重复 5/5）？兼容性动测跑了吗？ |
| 选择 | 有一个 draft 就整场不开工；**缺图不静默降级为文生视频**；一镜超 8 次→改结构不换词 |
| 输出 | 台账逐镜一行；finalist ≥2 |
| ★静默点 | **[全量] 静态好看就放行**（没跑动态测试）· **[条件·≥2 资产同框] 只测单资产动态、没测组合**——两个 5/5 同框可能互相污染（R51）· **[全量] 台账漏记**（返工时无据可查） |

## §6 · 分镜与故事板（站 6 板块一）

| 步 | 内容 |
|---|---|
| 检索 | `direction-reasoning.md`（六问推导链·每场自我批判，**先做这个**）· `shot-orchestration.md`（排镜）· `shot-design.md`（设计感十装置）· `storyboard-frame.md`（三路径+失败处方）· `storyboard-platforms.md`（平台规格）· `transition-library.md`（转场 12 种+模板）· `sequence-craft.md` / `staging-craft.md`（调度）· `shot-linkage.md`（衔接）· `direction-worked-example.md`（六问推导完整示范） |
| 思考 | ① 每镜目的三选一（改变情绪/推进动作/施加压力）——**这镜结束时什么变了**？② 排镜表秒数列齐（节奏数学靠它，**秒数不进提示词**）？③ 景别序列有起伏（跳级/收放）？④ 故事板只锁结构不写色温？⑤ 输出模式声明了吗（绝不拼版 vs 原生批量）？⑥ 切点有过渡压力吗？ |
| 选择 | 拿不准单机位；稳镜可合难镜必拆；故事板一镜一张纯灰度；**图像主力 image2（单次 n=8/4，官方用例 storyboards）** |
| 输出 | 分镜表（排镜表留时长列）+ 每镜一张黑白故事板；`storyboard_lint.py` rc=0；LibTV：分镜表节点→分镜卡节点→`D→S` 边（**加一层就补一层到直接下游的边**） |
| ★静默点 | **[全量] 排镜表总时长与确认时长未做 ±0 数值对表**（R51）· **[全量] 故事板画完不连下游**（做它干什么）· **[条件·批量出图] 忘声明输出模式**（被拼成九宫格）· **[条件·image2] 文字标注混进图**（image2 文字渲染强，必须显式禁） |
| 横切 | 锚点（分镜表"引用锚点"字段＝生成引用正本）｜预算（故事板张数≤平台上限） |

**§6.4 · 首帧/尾帧帧管理（R51 新增 · 条件节：用首尾帧驱动的通道才走；纯文生视频→显式声明裁剪）**

| 步 | 内容 |
|---|---|
| 检索 | `libtv-op-manual-part3.md`（start_frame_image_node / continue_from 语义）· `libtv-official-qa-part5.md`（R16 首尾帧续写与审核降级）· `libtv-prompt-structure.md`（首帧之后只写发生什么） |
| 思考 | 首帧从哪来（故事板精修 / 资产派生 / 上一镜尾帧抽帧）？首帧排 left 首位了吗？要不要尾帧（收束锁型才建）？链式衔接的 continue_from 断点对吗？ |
| 选择 | 首帧驱动优先；**每 3 段插一次 upscale 防代际退化**（外部多源共识） |
| 输出 | 帧节点+引用边+插桩；台账记帧来源 |
| ★静默点 | **[条件] V 层 prompt 重复描述首帧内容**（引导模型重绘首帧）· **[条件·链式] 代际退化未防** |

## §7 · 镜头提示词（站 6 板块二）

| 步 | 内容 |
|---|---|
| 检索 | **写前 `steelman-protocol.md`（双向钢人四步 + 10 项自查）· 动作类先过 `motion-control.md` 决策树（周期动作禁纯文字求解）**；`shot-craft.md`（拆镜开关·权威模板）+ `shot-craft-part2.md`；分段镜 `segmented-shot.md` · `segmented-shot-part2.md`；**逐块规格 `block-spec.md`（12 块接口+归属去重表）**；逐块思考 `block-playbook.md` + `block-playbook-part2.md`；人物与表演 `character-depth.md`（四层+眼+呼吸）/ `character-realism.md`（五问）/ `expression-library.md`（查表）/ `expression-rhythm.md` / `expression-anatomy.md` / `performance-craft.md` / `performance-vocabulary.md` / `physical-feedback.md`；皮肤与光 `skin-realism.md` / `skin-light-physics.md` / `light-physics.md` / `light-quality-construction.md` / `tone-realism.md`；运镜与动作 `camera-movement-library.md` / `block-camera.md` / `actor-movement.md` / `motion-principles.md` / `motion-parameters.md`；取词 `lexicon-map.md`；声音行 `sound-lexicon.md`；提质层 `quality-layer.md` / `quality-layer-part2.md`；器材参数与漫剧黑名单 `cinematic-look.md`；载体痕迹机理 `carrier-artifacts.md`；空话词黑名单 `prompt-ops.md`；调色 `color-grading-styles.md`→`color-science.md`→`color-narrative.md`；器材句从站 3 包里逐字粘 |
| 思考 | **12 块一块不漏地想过**（用户铁律·思考层）；写前钢人论证四步走满；每块问三件：该想什么/写哪一句/模型能不能懂；写实片三件（写脏≥2 带尺寸·磨损分布·材质受光）；人物三条下限（生理活性≥2·静息微动·微表情"部位+动作"）；皱纹不写纹名+换光位；**输出层按平台口径**：LibTV 单镜输出 5 块主干 + 附属短句（`libtv-prompt-structure.md` §六/§七；思考层仍为 12 块；官方预演/落地页范例 → `libtv-prompt-house-style.md` §七）· 起始景别声明 · 运镜四要素 · 时间线四相 · 尾帧状态 · 禁止项"画面中只有…；不出现…"末尾可数 3–6 条；**秒数只活在排镜表** |
| 选择 | 分镜版 vs 段落版（判路表）；**视频层参考瘦身（首帧驱动优先，派生锚点不扇出 V；身份漂移实测显著才补母锚点——R50）**；微表演 5s 内 ≤3 节拍（过密易糊）；f 值不进视频 prompt（不可控参数） |
| 输出 | 整合提示词（代码块纯净·零装饰符·零空话词）；`audit_prompt.py blocks` rc=0（**镜头类查 12 块；静帧用 --asset/--storyboard，别混**）+ `ai_smell_check.py`；LibTV：F 排 `left` 首位·V1 承接首帧"只写首帧之后发生什么"·`enableSound=off` 声音不写进 V 层执行口径 |
| ★静默点 | **[全量] ★跨镜文字措辞漂移——同一实体的外貌/服装描述句每镜重写、近义替换**（锚点句必须**原句复用**；我方核验非伪需求：R49"锚点句必须保留"+R50"同一串钥匙"缺失均为文字层漂移）· **[全量] prompt 里写秒数**（AI 自己分配）· **[全量] 块名自造**（门禁认旧名）· **[条件·LibTV] 插桩没写或写两次以上无用途** · **[全量] 思考层跳块**（用户点过名） |
| 横切 | 锚点（身份锚点句原句复用）｜问询（拿不准写法→先查 R 系列答疑册，不凭印象） |

## §8 · 画布建造与投喂（站 6.5 · LibTV 主通道）

| 步 | 内容 |
|---|---|
| 检索 | `libtv-canvas-nodes.md`（节点/写锁/成本）· `libtv-canvas-anatomy.md` 主册/续册（画布实证）· `libtv-prompt-anatomy-distilled.md` 主册/续册（提示词写法）· `libtv-op-manual.md` + `libtv-op-manual-part2.md` + `-3.md`（引用链/点火审批/合成导出/台账）· `libtv-model-params.md`（三层引用字段·实测口径） · `libtv-model-params-part2.md`（工程后果/待验/派生字段/官方字段字典） · `libtv-model-catalog.md` §三·补 6（素材面板 11 风格/3 镜头与 maxCount）· `libtv-official-qa.md` 至 `-9.md` 全七册+续（R1–R50 答疑一手源）· `libtv-official-qa-part9.md` · `libtv-ignite-ops-fields.md`（点火字段+**声音节点创建**）· `libtv-concurrency.md`（run 锁）· `libtv-billing.md` · `libtv-moderation.md`（审核红线）· `libtv-op-checklist.md`（点火前 10 项）· `libtv-capability-matrix.md`（48 工具×实测状态）· `libtv-platform-watch.md`（平台更新监测+新接口）· `libtv-prompt-house-style.md`（平台自家写法实物 + 官方预演 3 条/落地页 6 条）· `libtv-quality-delivery-content.md`（板块命名/账本/扩展公式）· `libtv-ignite-director-billing.md`（导演台 14 op+计费判据）· `pipeline-cross-source-consensus.md`（外部共识对表）· `agent-autonomy.md`（预算/证据链/纪律七） |
| 思考 | ① 建造顺序（内容源先建→母锚点→派生→分镜→S→F→V→AU→X1；AU 可并行）？② 每条边为什么连（邻接表）；**D→A 是登记边，消费与否取决于 reference+插桩**？③ 参考位序=建时 left 序（事后不可重排）？④ 写锁串行（PROJECT_WRITE_BUSY）？⑤ 预算折算与点火审批（`ask_human` approve_run_node_once，外部绕不过）？⑥ 台账与账本（画布是镜像、账本是正本）？ |
| 选择 | **平台 Agent 自述 ≠ 事实，一切以 get_project_snapshot 为准**；对表优先：我方实测 > 外部多源共识（≥3 源）> 它单方自述；"做不到"先追问是工具面还是能力层；文生图/图生图先 modeType 后连线 |
| 输出 | 节点+边+插桩 prompt；每次写操作带幂等键；台账记录 runId；**点火必须有人在场** |
| ★静默点 | **[全量] 它说"已建好"不回读核对**（自述≠事实，多次实测打脸）· **[全量] 批量建节点中途失败，已建部分未清点就继续**——幂等键防重复不防半成品（R51；PROJECT_WRITE_BUSY 即半成品场景）· **[条件·改上游] 忘下游级联作废** · **[条件·点火] 忘审批链**（无人点火=卡死） |
| 横切 | 预算（结构/读取/预检免费；生成、合成、剪辑、音频编辑、导出按动作计费；幂等键防重复扣）｜问询（四段式模板）｜对表（三源优先序） |

## §9 · 声音

| 步 | 内容 |
|---|---|
| 检索 | `sound-craft.md`（结构/配额/混音/同步权威）· 取词 `sound-lexicon.md` · 写法 `sound-prompt-craft.md` · 设计 `sound-design-craft.md` · 音乐 `music-craft.md` · 响度 `mix-loudness.md` · 工具 `audio-tools.md` · 流程与声音表 `sound-post-pipeline.md`（**表跑 `sound_lint.py`**）· 叙事 `sound-narrative.md` · 训练 `sound-drill.md` · **LibTV 声音节点 → `libtv-ignite-ops-fields.md` 声音节** |
| 思考 | ① 本片要不要声音、要哪几层（环境床/点状音效/对白/BGM）？② 声音是后置独立还是随镜生成（LibTV：各镜 off、AU 只接合成）？③ 点状声锁了相对时刻吗（合成轨级 start_time 无事件偏移）？④ 电平三原则与混音电平陷阱（video_volume=0）？⑤ 对白口型可行性？ |
| 选择 | 按层分条不按事件个数；无对白片声音=底噪+点状两层；模型 seed-audio-1.0、scene 必带 |
| 输出 | 声音提示词/声音表（`sound_lint.py` rc=0）；LibTV audio 节点+入合成边；AU 先于 X1 生效 |
| ★静默点 | **[条件·LibTV] V 层 prompt 详写声音与 enableSound=off 打架**（R50 实抓）· **[条件·LibTV] AU 没先生效就点合成** · **[条件·对白/长片] 声音总时长未与成片时长对表、各层起止未列时间线**（R51） |
| 横切 | 预算（audio 生成计费） |

## §10 · 合成、导出与交付（站 6.6–6.7）

| 步 | 内容 |
|---|---|
| 检索 | `post-production.md`（选片/修复/超分/调色/剪辑/字幕）· `real-world-logic.md`（九轴跨层自洽，交付前必跑）· `color-pipeline.md`（偏色/过饱和/灰暗三症状查管线）· `editing-rhythm.md`（ASL/轴线）· `cross-shot-interface.md`（拼接点/重编码）· `delivery-engineering.md`（命名/归档/六件交付）· `review-passes.md`（七遍法）· `acceptance-check.md` · **统一调色一道（外部共识：成片必有、不靠 AI）**· LibTV：`export_readiness` 预检→`export_video`（clips 序=拼接序·video_volume=0·audio_tracks 轨级 start_time）→`export_status` 收件 |
| 思考 | ① 每镜素材审过七遍法吗（证据式笔记）？② 拼接点/定格相/fps 统一？③ 调色方向与全片族一致？④ 交付六件齐（含命名与元数据）？⑤ 验收清单显式（时长/画幅/电平/无字幕/光位/状态连续/尾帧）？⑥ 证据链四件（任务号/参数快照/结果路径/判据结果）？ |
| 选择 | 素材可用率 30–40% 是常态；修复先参数后提示词（`ai-artifact-control.md` §五·补二 分诊）；**超过 25 镜拆子合成** |
| 输出 | 成片 + 交付包 + 证据链 + 验收清单逐条勾；**商用片随附授权清单**（参考帧/音乐/字体的授权状态，`sources-and-credits.md`）；**对目标平台核技术规格**（响度制式 / 封装码率 / 色彩空间 Rec.709·HDR——R51） |
| ★静默点 | **[条件·LibTV] 没跑 export_readiness 直接导出** · **[全量] 验收清单口头过**（没落账）· **[全量] 证据链缺件**（复盘无据）· **[条件·商用] 交付规格未对目标播放平台核验**（只在制作机上看——R51） |
| 横切 | 证据链（四件）｜授权（商用片授权清单随交付） |

## §11 · 复盘与返工（站 7）

| 步 | 内容 |
|---|---|
| 检索 | `review-passes.md` · `qa-failure-codes.md`（失败码+责任层）· `pitfalls.md` / `key-decisions.md`（记账 E 系列）· `production-ledger.md` |
| 思考 | 失败归哪层（提示词/参数/模型能力/平台）？要不要改结构（拆镜/换机位）而不是换词？新教训记账了吗？ |
| 选择 | 一镜超 8 次→改结构；系统性问题→入库（走 §13 库变更 SOP） |
| 输出 | 台账复盘行 + 记账条目 |
| ★静默点 | **[全量] 换词硬试不改结构** · **[全量] 返工后未对已交付下游产物级联重验**（R51）· **[全量] 教训只留在对话里没入库**（下个项目再犯） |

## §12 · 横切段（跨板块，随时生效）

1. **一致性锚点**：锚点三条在站 3 定、账本登记、各板块原句复用；改锚点=全链同步；人物不漂五线（身份/造型/位置/情绪/状态）→ `character-continuity.md`。
2. **预算与止损**：每板块输出带预算折算（`platform-matrix.md` 四·补 / `libtv-billing.md`）；能免费先免费（结构、读取、预检与门禁免费；媒体生成、合成、剪辑、音频编辑与导出按动作计费）。
3. **平台 Agent 问询纪律**（`agent-autonomy.md` 纪律七·四段式模板）：要求**给依据（四选一·推断显式标）+ 给反例 + 自我审计（最不确定 3 条+怎么验）**；追问"做不到"是工具面还是能力层；**它的自述必须回读核对**。
4. **对表优先序**：我方实测 > 外部多源共识（≥3 源独立重复，`pipeline-cross-source-consensus.md`）> 平台 Agent 单方自述；**用户裁决 > 以上全部（执行层），但用户的判断同样要记依据与反例**——执行前若有实测/共识冲突，**先摆事实给用户再动**，用户确认后按裁决走并记账（含"用户原话+日期+反例"）。**用户的话不是免检铁律，是最高优先级的待验输入**。
5. **双通道**：WorkRally（`workrally-workflow.md` + `workrally-command-map.md` + `scripts/workrally_bridge.py`）与 LibTV 并行，选通道看任务形态（`workrally-workflow.md` §0·补）。
6. **账本文件层**：画布是镜像、账本是正本（`production-ledger.md` + 项目账本目录：TASK/定稿/分镜表含引用锚点/锚点集）。
7. **拉片/仿拍/风格库重写类任务**：走 `reverse-prompt-method.md`（证据三级+七层反推+三图比对），不按 §1–§11 顺走。
8. **brief 变更（R51 新增）**：中途改需求 → 影响评估 → 重估预算 → 用户确认 → 账本新版本号；**以"小修改"名义绕过门禁＝违例**（小修改只走检索→输出的白名单口径不适用于需求变更）。
9. **条件路由（R51 新增 · B 级环节，触发才走，识别点在 Step 0）**：多语言/本地化（口型重配+字幕轨+画面内文字多语+文化禁忌）· **多平台分发（在 §6 排镜阶段做安全框与构图双版本，不是导出时裁画幅）** · 观众试映（粗剪→反馈归类→改剪；区别于 §11 内部复盘）· 数据回收（跨项目，归 run-sheet 站间层）。
10. **门禁扩张警告（R51 新增）**：审美类判断（方案包配得好不好 / 表演到位否）**不追求机检**；防"扫到了＝好"——rc=3"没扫到≠过"的纪律同样适用于门禁数量本身。

## §13 · SOP · 防静默三件套（本册的存在理由）

**SOP-A 使用**：每板块开工 → 读本册对应节 → 四步走满（或显式声明裁剪）→ 末尾答"★静默点"逐条 → 门禁 rc=0 才算完。
**SOP-B 库变更**：新增/修改任何册子 → ①挂 `SKILL.md` 索引 ②挂 `run-sheet-part2.md` 工位 ③**挂进本册对应板块的"检索"步（漏挂=使用时静默）** ④跑 `lib_doctor.py` + `lib_health.py` ⑤动脚本跑 `--self-test` ⑥教训进 `key-decisions.md` 记账。**⑦ [TODO·下次改 lib_doctor 时实现·不在本轮动脚本] 新增第⑨项：本册各板块"检索"步的册名覆盖核对**（防"有册没进思考流程"——与现有①④项同构）。
**SOP-C 审计（R51 修订：事件驱动，不靠自觉）**：① E 系列记账**必须打标签**（命中哪条静默点 / 新型静默点 / 非静默），**不打标签不能关单**；② "连续 90 天检索次数＝0"的册由台账自动出孤立清单（检索留痕已在台账，人工只做处置裁决：过时 / 重复 / 从未接入 / 待命）；③ 新增静默点必须同时给出处（记账编号或日期），且**挂量级标签**（[全量]/[条件]）防清单膨胀稀释信噪比——本册静默点均标了标签与出处，新增时照此格式。
> **本册维护纪律**：板块结构变了（如新增板块）→ 先改本册骨架再动别的；本册"检索"步里的册名必须真实存在（`lib_health.py` 悬空指针会抓）。
