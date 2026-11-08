# 生产编译器使用入口

> **模式约束**：本文件只负责 `production_build` 的可执行编译。
> 反推、副本级、源级和盲测模式先走 `references/reverse-fidelity-contract.md`
> （`reverse-fidelity-contract.md`）与 `references/blind-reverse-runbook.md`
> （`blind-reverse-runbook.md`）；编译器产物不得直接升格为 `source_replica`。

日期：2026-10-08  
状态：v1，可生成计划、提示词包和未执行的 LibTV 命令；不点火。

## 1. 适用

```text
production_build
film_reverse
source_replica
```

简单输入可以是 JSON、`.txt` 或 `.md`。文本输入优先识别 `镜头N 时长 描述` 行；没有结构化镜头时会按段落生成镜头占位。其余缺失项会被编译器写入 `assumptions` 或 `questions`。

**产物类型必须先声明**（见 `reverse-fidelity-contract.md` §2.1）：

```text
deliverable = production_plan   默认；规范化生产计划，允许重排结构
deliverable = mirror            忠实镜像；必须给 source_graph_path，产物是 03_mirror_graph.json
```

`copy_reverse` / `source_replica` 不声明 `deliverable` → 门禁 `DELIVERABLE_UNDECLARED`，
不会默认走生产计划路径。

## 2. 命令

```powershell
python scripts/compile_production.py input.json --out out/
```

产物：

```text
01_production_contract.json
02_asset_graph_plan.json
03_shot_graph_plan.json          production_plan 路径
03_mirror_graph.json             mirror 路径（每节点带 source_node_id）
04_prompt_packages.jsonl
05_platform_execution_plan.json
06_gate_results.json
07_regression_ledger.json
08_libtv_command_plan.json
```

`08_libtv_command_plan.json` 含节点创建、分组、模型、settings、提示词和连线计划，但所有 `run` 必须为 `false`。

平台适配器：

```powershell
python scripts/apply_libtv_plan.py 08_libtv_command_plan.json --project-uuid <UUID>
```

默认只 dry-run。只有显式传 `--execute` 才会创建分组/节点/连线；执行器拒绝任何 `run=true` 命令，永不自动点火。

## 2.5 阶段一：只要提示词时的真实入口（2026-10-22）

用户要的是**提示词本身**（"只要提示词"、"给我一条空镜的提示词"），而不是成片、平台画布或媒体生成时，
走阶段一入口：

```powershell
python scripts/compile_intent_delivery.py <intent_handoff.json> --out out/ --draft
```

Agent 负责把用户原话理解成 `intent-handoff/v1` 交接文档（**用户不手填 JSON**），
脚本负责结构化交接、校验和编译正本，`--draft` 派生 13_Draft_Prompt.md。正式 13_Final_Prompt.md 另需当前任务绑定的 `--review`、`--capture-root` 与 `--session`，证据要求见 `delivery-review.md`。
`prompt_only` 停在 Prompt Package：不产 `05_platform_execution_plan.json`、不产 `08_libtv_command_plan.json`、
不创建画布、不生成媒体、不点火。

约束是否真的兑现，由 `scripts/verify_delivery_semantics.py` **独立复核**：判定输入只有权威输入与实际交付正文，
**不信 `consumed` / `READY` / `constraint_evidence` 这类自报状态**；合法同义表达放行，篡改机位/构图/声音/结构/来源一律 FAIL。
零判定不是通过。

完整产物表、停止点、反例表、**包内缺失规范的可核验恢复指针**与本阶段不支持的输入 → `references/stage1-delivery-entry.md`。工艺消费与本镜时间作用域短入口 → `references/craft-delivery-entry.md`。

## 2.6 任务范围与提前停止（task_type）

`task_type` 为可选字段，缺省按 `full_film`。允许值：`full_film`、`prompt_only`、`single_shot`。它控制停止点，不改变 `production_mode` 或 `deliverable`。

- `prompt_only`：在图规划与 Prompt Package 停止；不生成 `05_platform_execution_plan.json` 或 `08_libtv_command_plan.json`。
- `single_shot`：必须且只能有一个显式输入 shot；在 Prompt Package 停止。
- `rework` 尚未实现，当前必须报错，不得静默降级为 `full_film`。
- 冲突：`prompt_only`/`single_shot` 与 `delivery.requires_media_generation=true` 或 `requires_export=true` 冲突；`single_shot` 与 `deliverable=mirror` 冲突。`prompt_only+mirror` 允许，并保留源节点、参数、prompt/settings/lineage。
- 若输出目录已存在任一执行计划文件，提前停止任务拒绝覆盖，保留原文件。
- 编译产物中的 `11_task_profile.json` 记录 `task_type`、`target_state`、`compiler_state`、`production_complete=false`；`compiler_state` 只反映编译/门禁状态，不声称媒体完成。
- 门禁对提前停止图中的下游角色（assembly、final_composite、production_ledger、qa）返回 `TASK_STAGE_EXCEEDED`；每个 video_candidate 必须连到同 shot 的 selection，缺失返回 `TASK_SELECTION_INPUT_MISSING`。

## 2.7 无对白与声音

- `no_dialogue` 为 project/shot 布尔值；shot 的 `false` 覆盖 project 的 `true`；silent 等别名按静默处理。
- 无对白镜头只保留 ambience/环境声，不生成人声或无依据音乐。

## 3. 门禁

`scripts/production_capability_gate.py` 检查：

```text
每镜生产角色完整
复用/状态资产有迭代链或豁免
提示词包块完整
无点火
source_replica 有源基线
deliverable 已声明（DELIVERABLE_UNDECLARED）
mirror 必须有 source_graph_path 且每节点带 source_node_id
production_plan 不得声明源级忠实（FIDELITY_CLAIM_NOT_AUTHORIZED）
```

`mirror` 只验结构忠实，不按生产角色检查（会打 `MIRROR_SKIPS_PRODUCTION_ROLES` warning）；
它的结构量级与血缘由 `scripts/source_fidelity_lint.py --deliverable mirror` 判定。

结构量级对比使用：

```text
scripts/source_fidelity_lint.py
```

## 4. 回归

```powershell
python scripts/production_regression.py
```

回归覆盖 W1/W2/W3/放殃源副本基线，并编译一个两分钟无源画布 fixture。

## 5. 边界

- 编译器只做编译，不执行 `--run`。
- `apply_libtv_plan.py --execute` 也只建结构，不点火。
- 生成、上传、导出必须单独获得用户批准。
- 节点数不是目标；生产角色、迭代、候选、依赖闭环和提示词可执行性才是验收对象。
- `text` 节点必须把正文写入 `data.content`，不能只写 `params.prompt`。
- 有上游引用的提示词必须写出对应的 `{{Node ...}}` 引用，而不是只在内部保留引用列表。
- `source_replica` 必须同时检查 action、模型、modeType、settings、提示词、媒体 URL、taskId/status 和正文层；只比节点/边不算源级复刻。

## 6 · 画布排版规则（建节点时必须遵守）

> 来源：2026-10-12 在真实画布上建 15 节点时实测。**属于"不照做就一定会返工"的硬约束。**

```text
① 坐标只认创建那一刻
   `libtv node --x N --y N create <名> -t <型> ...`（--x/--y 写在 create 之前）
② 已建节点**无法移动**
   实测：单独跑 `--x/--y` 是空操作（exit 0 但不改）；`-u position={"x":..,"y":..}` 同样 exit 0 而不生效。
   → 没带坐标建出来的节点只能**删掉重建**，没有"事后排版"这条路。
③ 入组会**打乱**排版（关键）
   绑定到普通分组后，节点坐标变成**组内相对**并被平台重排。
   实测：15 个节点显式排成 3×6 网格（零重叠）→ 建 3 个分组后，(20,20) 一个坐标挤进 3 个节点，
   重叠对从 0 涨到 24。
   → **要么不建组；要么一开始就按"组内相对坐标"规划每个组内的布局**（不要先排好再入组）。
④ 推荐网格（本库默认）
   节点约 620×350 → 列间距 **820**、行间距 **760**（留出引线空间，不贴边）。
⑤ 按依赖分行，引线方向统一
   资产行 y=0 → 分镜行 y=760 → 镜头行 y=1520；同行按 x 递增排。
   示例（本库 PATCH MOTHER 复刻包）：
     A1..A6  x=0/820/1640/2460/3280/4100  y=0
     T1 S1 I1 x=0/820/1640                 y=760
     V1..V5 X1 x=0/820/1640/2460/3280/4100 y=1520
⑥ 建完必须核验，不许目测
   跑 `check_layout.py --project <uuid>`：要求 `overlapping_pairs=(none)` 且 `shared_slots=(none)`。
```

**可执行入口**（规则不只写在文档里，`scripts/canvas_layout.py` 直接算坐标）：

```powershell
# 建节点之前先算槽位；它同时会把重叠检出来
python scripts/canvas_layout.py --spec spec.json --out layout.json
# 输出 status=PASS 且 overlapping_pairs=[] / shared_slots=[] 才允许开始建
python scripts/canvas_layout.py --self-test      # 5 条自检
```

建站脚本按 `layout.json` 的 (x,y) 逐条 `--x <x> --y <y> create ...` 即可；
**不要**在建完之后再补坐标或再建分组（见③）。

## 7 · 反推运镜与调度：**静帧读不出来，必须做帧间测量**

> 来源：2026-10-12 用户当面质疑"你看静帧真能看懂镜头运动吗"。答案是**不能**，已实测修正。

**静帧能读的**：构图 / 景别 / 透视 / 光位与色温 / 画面内容与人物位置（某一瞬间）。
**静帧读不出的**：机位是否在动、动的方向与速度、是否跟移或手持、人物调度（走位、
转身、进出画）、镜内节奏、支撑方式（手持/稳定器/轨道）、焦段、快门。

```text
纪律：凡要写"跟移 / 推近 / 摇 / 手持 / 机位固定"，必须先跑
      python scripts/motion_readback.py --video <成片> --shots shots.json [--fps 15] [--roi x,y,w,h]
      没跑过就写 = 把推断当实测（本库明令禁止）。
```

工具怎么读：

```text
边缘区域位移 → 估**机位**（边缘多半是环境，被试主体带偏的概率低）
中央区域能量 → 估**主体动作**
远处小主体：低分辨率测不到 → 加 --roi（并按需 --scale）提高分辨率复测
短镜（<2s）：6fps 采样不稳 → 必须 --fps 15 复测；**两次采样结论不一致 = 记「不可判定」**
★ 报运镜类型**必须**加 --similarity：只搜平移会把「环绕 / 推拉」误判成平移
  （实测：第一个镜头是**环绕上升**，纯平移估计读成"横移 + 升降"，漏掉 4.5°/s 的旋转）
```

```powershell
# 三件一起跑：机位(平移) + 主体能量 + 运镜类型(旋转/缩放/平移)
python scripts/motion_readback.py --video in.mp4 --shots shots.json
python scripts/motion_readback.py --video in.mp4 --shots shots.json --similarity
python scripts/motion_readback.py --video in.mp4 --shots shots.json --roi 0.36,0.30,0.18,0.28 --fps 15
```

★ PATCH MOTHER 0–20s 的实测结论（三段采样，2026-10-12）：

```text
V1  机位在动（横移 +5.6 · 升降 +9.1 px/s，两次一致）→ 可用
V2  机位静止（0.86 / 1.02 / 1.86 px/s，三次一致）→ 可用
V3  **不可判定**（6fps: −1.7 / 13.0，15fps: +28.1 —— 差异过大；1.1s 短镜 + 主体动作强）
    但"主体动作强"是稳定的（三组采样中央能量均最高之一）
V4  机位静止（0/0 与 −4.0/−4.6，两次均在阈值内）；远处二人有位移（ROI 6.78，96×54 测不到）
V5  机位基本静止（0.95 / −2.21 px/s）
```

**不可判定就不许写成实测**：V3 的机位在交付件里必须标「复刻选择」而不是「实测」。

## 8 · 方法可及性边界表（断言前先查这张表）

> 2026-10-12 连错两次（静帧断运镜 → 只搜平移把**环绕上升**读成"横移+升降"）之后立的规矩：
> **先看方法能到哪，再决定能不能下这个结论。**

| 方法 | 能确立 | **不能**确立 |
|---|---|---|
| 静帧（抽帧看图） | 构图 · 景别 · 透视 · 光位色温 · 某一瞬的画面内容 | 运镜 · 人物调度 · 镜内节奏 · 支撑方式 · 焦段 · 快门 |
| 帧间平移估计 | 有无全局平移、方向与速度 | **旋转（环绕）与缩放（推拉）** —— 会被硬套成平移 |
| 相似变换（旋转+缩放+平移） | 环绕 / 推进 / 拉远 / 升降 / 横移的有无与量级 | 支撑方式（手持/稳定器/轨道/无人机）· 弧线半径 · 焦段 · 快门 |
| ROI 高分辨率复测 | 远处小主体**有没有位移** | 他们的身份、意图、台词 |
| 画布 summary 回读 | 节点 / 边 / 类型 / 坐标 | 节点参数（model / settings / prompt） |
| 节点级回读 | 参数、任务状态、产物 URL | 平台是否**真吃得下**这套参数（那是预检的事） |
| 平台预检 `validate_generation_plan` | **仅"要新建的节点"** | 已建节点的点火前预演（实测直接报"已存在同名"） |
| 本库编排器门禁（R/K/G 系列） | 本库自己的规则 | 平台真实行为 |
| 盲测门禁 | 同作品的字段可复现性 | 跨作品泛化（实测 model 命中 0.00–0.25，不成立） |

**执行**：任何交付件里出现高危断言（运镜 / 排版 / 占位符 / 点火），必须
**① 附对应测量证据**，或 **② 该行显式标注 `推断 / 不可判定 / 复刻选择 / 拟订 / 未验证 / 待确认`**。
二者都不满足 = 把推断写成实测。**这条有闸**：

```powershell
python scripts/claim_method_lint.py --dir <交付包> --evidence-dir <证据目录> [--evidence-dir ...]
# 退出码：0 PASS · 1 有违例 · 3 没扫到断言（≠通过）
python scripts/claim_method_lint.py --self-test     # 5 条自检
```

**为什么写进流程**：节点重叠不是"不好看"，是**审计与执行都会出事**——
人看不清连线、批量选不中目标、组执行顺序判断不了。这条与"文字不进画面"同级，
属于建站阶段必须机械保证的事，不能靠事后目测。

## 知识路由补充：实体画幅字段（2026-10-20）

- `entities[].aspect_ratio` 必须是严格正整数 ASCII `W:H`（例如 `16:9`、`9:16`）；不得使用小数、全角冒号或负数。
- 缺省时按 `project.aspect_ratio`，再按默认 `16:9`；来源标记为 `aspect_ratio_source = entity | project_default`。
- 只有资产节点的 `settings.ratio` 可写实体/项目画幅；镜头与视频节点保持项目画幅，不得被实体画幅覆盖。
- 本补充只描述编译器字段合同，不代表真实模型比例或平台渲染比例已验证。

## 知识路由补充：production-compiler 路由用法与限制（2026-10-20）

- CLI：`python scripts/lib_doctor.py --route-json <key>` 输出单一 JSON 对象；`--route <key>` 保留旧文本查询。
- 状态与退出码：`matched` → 0；`no_match`/`unsupported` → 3；`invalid_catalog` → 1；用法错误 → 2。
- 来源/载荷口径：`files` 为唯一规范路径列表并附 `origins`（来源文件/行号/原因）；`load` 仅含 `raw_bytes`/`unique_bytes`/`duplicate_bytes`；`source_versions` 绑定路由与能力来源 SHA；字节为真实字节，不以字符数冒充 token。
- 导航不等于生产就绪：本路由只给按需阅读清单，不判定规则适用、不评估 production readiness、不授权生成；L2 强制阅读保留，L1 不做全局豁免。
- 实体画幅字段见上节：`entities[].aspect_ratio` 可选，仅显式存在时严格校验；元数据记录于资产计划。
