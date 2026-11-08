# aigc-agent-studio · 自动化生产长远路线图

日期：2026-10-12  
状态：阶段化推进中（P0 未开始）  
依据：下文的「已有 / 缺」记录来自 2026-10-12 本机实测，保留该次路线规划的状态。

---

## 0 · 规划终态

> **给一份规格（剧本 / 分镜 / work_profile），在一次显式批准之后不需要人再介入，
> 就能产出可播放成片 + 证据包；失败能自动停车或续跑且不重复付费；
> 成本开工前可估、完工后可对账。**

验收按以下四个维度记录。

```text
可跑通    至少一次真实端到端生产，产物可播放
可算账    单价来自实测，估算与实际可对账
可恢复    中途失败能续跑，且不重复付费
可自证    产物由机器判据验收，不靠「看着像」
```

---

## 1 · 就绪度基线（2026-10-12 实测）

### 已有

```text
编排器    scripts/libtv_orchestrate.py（2873 行）
          子命令：preflight / compile / pipeline / ingest / compliance /
                  propagate / classify / verify / resume
          自检：122 通过 / 0 失败
          已实现：幂等键、依赖拓扑、批次切分（4 个/批 · 上限 5 留 1）、
                  预算闸、断点续跑状态、接口契约校验 K0–K24、止损阶梯
开工体检  preflight → 注册 / 缓存 / 凭据 三层 ok，verdict「就绪：三层都在，可以开工」
          第 4 层网络由 agent 侧确认（脚本发网络请求是红线，保持 0 行）
编译器    compile_production.py → contract / asset graph / shot graph /
          prompt packages / capability gate / libtv command plan（run 全 false）
判据层    source_fidelity_lint 双向阈值 + 血缘；golden 7 例通过
回读工具  work_units.py（全类型逐节点回读，带缓存）
证据工具  orchestrate verify → evidence@1（任务号 / 参数快照 + ffprobe 容器级 +
          ffmpeg 数硬切点 + 色板 RGB 均值 + 平台边界逐字照抄）
产物闸件  ai_smell_check.py / subtitle_bands.py / sound_lint.py / shotlist_lint.py /
          storyboard_lint.py / script_lint.py / offline_package_lint.py
知识层    222 册 references + 十站 run-sheet（299 行）+ 4 个 schema
```

### 缺（全部有实测证据）

```text
真实生产  0 次。outputs 全量检查无任何点火 / 成片 / 导出记录
成本基线  0。price_per_second 表不存在 → graph_plan_lint 的 cost 段长期 N/A
QC 实测   合成片段已验证（2026-10-12），**但从未对真实生成的成片跑过**
恢复实测  0。resume 代码在，但从未在真实中断上验证过
生产画像  已落地（P4 完成）：缺画像即拒编；跨作品迁移实测不成立
```

**2026-10-12 补测：`orchestrate verify` 端到端跑通**（此前是「代码在、从未跑过」）

```text
方法    ffmpeg 合成三段硬切片段 → concat 成 9.023s 母版 → verify --plan --spec
结果    exit 0 · evidence@1 生成
        容器 9.023s / 320x180 / h264 / 音轨 1（aac）
        拼接点 **恰好 2 个**（2.023 / 5.023），与 expected_cuts=2 一致
        证据链含 task_id + 参数快照 + idempotencyKey
        色板 RGB 均值 85.37 / 81.59 / 96.88 · 平台边界逐字照抄 · 契约校验全过
反例①   expected_cuts 写成 3 → exit 1（不被放过）
反例②   状态 succeeded 但 task_id 为空 → exit 1，报 F67a「已成功却没有任务号」
注意    反例② 前半段一度被 PowerShell 读成 RC=0：`& $PY -c ...` 会覆盖 `$LASTEXITCODE`，
        读退出码必须 `cmd; $rc=$LASTEXITCODE` 紧邻取
```

当时已有编排与验收工具，但尚未完成真实生产闭环。

---

## 2 · 阶段计划

### P0 · 跑通一次真实生产（最小闭环）

**目标**：用最小体量换一次完整、留证的真实生产。

```text
体量    15 秒 / 3 镜 / 一个角色 + 一个场景
路线    站 1 命题 → 站 2 brief → 站 3 风格 → 站 4 剧本 → 站 5 资产
        → 站 6 分镜 → 站 6.5 投喂生成 → 站 6.6 剪辑合成 → 站 6.7 交付证据
顺序    选项目 → 挑模型读 prompt.maxLength → 免费 dry-run（validate_generation_plan
        或 generate_video(run:false)）→ 报预算 → run:true 带 idempotencyKey
        → task_status 轮询 → 下载落盘 → 按后缀分诊
```

**验收判据（每条都要能指回原始证据）**

- [ ] 成片可播放；容器级参数（时长 / 分辨率 / fps / 音轨）由 `ffprobe` 给出，不是目测
- [ ] 每个付费节点留档：`taskId` + 点火前 `taskParams` 回读 + 点火后 `status` / `urlCount` 回读
- [ ] 硬切点数与分镜契约一致（`ffmpeg select=gt(scene,0.30)` 计数）
- [ ] 总花费是实测数字，并与开跑前的预算报数并列
- [ ] 全程只有一个花钱批准点

**成本**：要花钱，**必须用户显式批准**；门禁全绿不算批准。  
**依赖**：无（其余阶段都不阻塞它）。  
**状态**：未开始。

---

### P1 · 成本基线

**目标**是建立可对账的成本记录。

```text
交付物  单价表（按模型 × 计价单位，标注来源与采集时间）
        首次真实生产的「估算 vs 实际」对照表
改动    graph_plan_lint 的 cost 段从 N/A 变成真闸：超 ceiling 直接 FAIL
```

**验收判据**

- [ ] 单价表里每个数字都有来源（实测账单 / 平台接口回读），无来源的不许填
- [ ] 连跑 3 次生产，估算偏差有明确范围，不写「差不多」
- [ ] 缺单价时行为明确：锁死付费闸并标「未解」，不允许脚本猜一个数

**成本**：纯记录，零花钱（沿用 P0 账单）。  
**依赖**：P0。  
**状态**：未开始。

**★ 2026-10-12 实测障碍**：CLI 不暴露单价。

```text
libtv model "Seedance 2.5" → 返回 {modality, modelKey, modelName, nameOrId, schema, toolKey}
逐字检查无 price / credit / cost / 积分 字段（唯一命中是无关的 checkpointId）
→ 单价只能来自两处：用户提供的账页/已知单价，或首次真实生成后的账单
→ 因此 P0 的预算报数必须由用户给出单价，或先把 P0 压到"单镜最小验证"再据账单回填
```

---

### P2 · 幂等与失败恢复（实测版）

**目标**：把库规里的生产事故变成执行链的硬步骤。

```text
要做  ① 点火前强制回读 taskParams（E216：params 新 ≠ taskParams 新）
      ② 改 params 后回读确认字段真的变了（E214：嵌套 settings 会被静默忽略）
      ③ 断点续跑：进程被杀 / 网络断，重跑不重复点火（幂等键落到平台）
      ④ 失败分类：可重试 / 必须换模型 / 必须停下问人
      ⑤ 一镜最多 3 次；超 8 次不许「再抽最后一次」（站 7 铁律）
```

**验收判据**

- [ ] 故意打断一次真实生成，续跑成功且账单不重复（用真实付费动作验证，不许模拟顶替）
- [ ] 人为构造「params 改了但 taskParams 没跟上」的场景，流程必须拦下
- [ ] 失败分类表里每一类都有一次真实样本

**成本**：少量花钱（重试样本）。  
**依赖**：P0（需要真实失败）。  
**状态**：未开始。

---

### P3 · 产物自动验收（QC 门）

**目标**是交付前自动检查下列技术缺陷。

```text
接门  orchestrate verify 的 evidence@1 + 既有闸件合成「成片门」：
      黑帧 / 静音 / 时长偏差 / 分辨率 / fps / 音轨 / 字幕对齐 / 响度 / 重复帧
      复用素材：ai_smell_check.py、subtitle_bands.py、sound_lint.py
```

**验收判据**

- [x] 每一类缺陷至少一个反例，且被门拦下（故意做坏的成片不算交付）
- [ ] ffmpeg / ffprobe 缺失时按既有先例只报 WARN（EXIT=4）。代码路径就绪，**未实测**（本机两者都在）
- [x] 门跑在交付前，不是交付后补（已接进 SKILL.md 生产入口）

**成本**：零花钱（用已有素材与自造成片）。  
**依赖**：无（可与 P0 并行）。  
**状态**：已完成（2026-10-12）。

```text
交付物  scripts/film_qc_gate.py
自检    9 / 9 通过
        good_clip_passes · good_clip_reports_numbers · wrong_duration_fails ·
        no_expectation_not_verified · black_frames_detected · silence_detected ·
        ratio_mismatch_detected · fps_mismatch_detected · cut_count_mismatch_detected
反例    用 ffmpeg 现场合成：纯黑 + 静音片段、4:3 片段、12fps 片段、错时长、错切点
退出码  0 PASS · 1 FAIL · 2 usage · 3 not_verified（没给期望值）
        4 WARN（ffmpeg/ffprobe 缺失时不判 PASS 也不判 FAIL）
已知边界 平台导出会强制加一条静音 aac →「零音轨」不当交付判据，只记 WARN（站 6.6 实测）
```

---

### P4 · 作品画像变成强制前置

**目标**：因为已实测跨作品不可迁移，画像必须挡在编译之前。

```text
已实测  大象 → 出走 / 大象 → 坠星 / THE TURN → 大象
        model 命中 0.25 / 0.00 / 0.00；duration 0.67 / 0.07 / 0.00
        → 任何单作品的 model / ratio / duration / 参考数都不是通则
要做    work_units.py 全类型回读 → 生成 work_profile → 契约必须引用它
        未画像 → 拒绝编译（是拒绝，不是警告）
可选    组归属用 libtv group <name> 拉 childNodeIds / executionPlan（已实测可行）
```

**验收判据**

- [x] 新作品不画像时编译被拒，且报明确 code（实测 `WORK_PROFILE_MISSING`）
- [x] 画像字段包含：节点与类型分布、模型与 mode 主力、时长分布、画幅、声音、参考图数量、
      prompt 长度与块结构、源访问层级
- [ ] 画像还缺两项专门字段：音频绑定细节、分组与版本方式（**未覆盖**，当前只在 structure 里给出组数）
- [x] 画像数值全部来自回读，不引用别的作品（`derived_from` + `evidence_class` 随画像落盘）

**成本**：零花钱（只读回读）。  
**依赖**：无。  
**状态**：已完成（2026-10-12）。

```text
交付物  scripts/work_profile.py（--self-test 7 / 7）
        scripts/reverse_contract.py 的 mode_errors 新增 WORK_PROFILE_MISSING
        scripts/compile_production_contract.py 支持 work_profile_path
回归    reverse_regression.py 15 → 18 例（新增三条画像门用例）全过
实测 A  带画像 mirror：gate PASS，产 03_mirror_graph.json（581 节点）
实测 B  不带画像 copy_reverse：gate FAIL WORK_PROFILE_MISSING，契约 questions 写明原因
真实画像 THE TURN（fa2c927d）：581 节点 / 1550 边 / 81 组；
        video 194 · text 92 · image 178 · audio 36；
        model 主力 Seedance 2.5 ×178；时长 30s×58 / 4s×30 / 15s×22；
        block 采用率 0.64 / 0.79 / 0.71 / 0.92；text 正文中位 6165 字
```

---

### P5 · 规模化与素材复用

**目标**：从「能生产一条」到「能生产一批且风格一致」。

```text
要做  角色 / 场景 / 风格跨片复用与一致性度量
      批量生产 N 条的可复算调用序列
      失败隔离：单条失败不拖垮整批（失败隔离换 v2 随下批重跑）
```

**验收判据**

- [ ] 同一角色跨两部片子的一致性可量化（像素级 / 色板比对，给数不给形容词）
- [ ] 批量生产的（估算成本 / 实际成本 / 失败率）有账

**成本**：按产量花钱。  
**依赖**：P0 至 P4。  
**状态**：未开始。

---

## 3 · 凭据与付费授权

1. **令牌不许解，执行者只能是 agent。** 凭据路径可解密但绝对不许解；正解是让用户点一次「重连」。
   自动化能做的是消灭即兴发挥，让同一份输入产出同一份调用序列。
2. **花钱必须显式批准。** 门禁全绿 / 生成成功 / agent 自己的判断都不算批准。
   终态是「**批准一次，之后自动**」，不是「完全无人」。

P0 的首次付费执行需要用户明确批准。

---

## 4 · 风险与反例（已发生或已实测）

```text
风险一  没有真实生产数据时继续堆结构
        证据：库 222 册 / 47 脚本，真实生产 0 次 → 再堆册不产生生产价值
风险二  把单作品结论当通则
        证据：跨作品 model 命中 0.00–0.25 → 必须每作品画像
风险三  用「看着像」顶替验收
        库规已禁（站 6.7 第 4 条），P3 把它变成机器门
风险四  单向判据造成的假绿
        已修：source_fidelity_lint 双向阈值 + 血缘；golden 7 例锁住
风险五  静默失败白烧积分
        实测先例：E214（params 嵌套被忽略）、E216（taskParams 未跟上）→ P2 处理
```

---

## 5 · 起手式

并行起两条零成本线，把花钱那一步准备好再按批准：

```text
线 A（零成本，可立即开始）  P3 成片 QC 门：verify 的 evidence@1 与既有闸件接成门，
                            用自造成片做反例测试
线 B（零成本，可立即开始）  P4 画像前置：work_profile 生成 + 编译前置拒绝
花钱的那一步               P0 最小生产包：3 镜规格 + 分镜 + 资产提示词 + 预算上限，
                            等用户批准后一次点火
```

P0 的生产账单和失败记录将用于 P1 / P2 的验收。

### P0 准备件状态（2026-10-12）

```text
已就绪   spec.json 12 节点（A 资产 / T 分镜卡 / S 故事板 / I 首帧 / V 五镜 / X 合成，
         五层齐）· contract.json 由 libtv model 真实回读拼出
         三载体齐且各自 rc=0：shotlist(--mode gen) / storyboard / sound
         闸门实测：G1 上游门禁 · G2 资产锁定 · G3 预算 · G4 契约 · G5 内容合规 全过
         G6 引用可生效**正确地拦下**了"上游未点火就建下游引用"
         → P0 必须分 4 批依次点火：锚点 → 首帧 → 三镜 → 合成，每批 ingest 回填再进下一批
待补     ① 真实画布 UUID（现为占位符）
         ② 真实单价（CLI 不暴露；由用户给，或先跑最小单镜按账单回填）
         ③ 用户显式批准
```

**五镜方案的约束推导**。三项约束在 3 镜上无解。节奏对比要求 `最长 ≥ 2×最短`，
生成单元最短受模型时长下限约束（Seedance 2.5 = 4s）→ 最长 ≥8s；单一景别又须 ≤35% 总长
→ 总长 ≥22.9s，3 镜放不下。5 镜 4/5/8/4/4=25s 同时满足节奏 2.0×、单一景别 32%、
中近景 20%、单段 ≤8s。这些时长按上述模型约束和节奏条件推导。

```text
已修（都影响"能不能真开跑"）
  ★ G1 口径：pipeline 调 shotlist_lint 不带 --mode → 生成单元表被按 cut 口径判 → 假 WARN
    → rc=4 → 挡住生成。已改按 --mode gen，自检 124 → 125（E226）。
  ★ L4 付费闸：缺 --prices 时用"量级区间"兜底放行，与自己的纪律矛盾 → 已改 FAIL（E225）。
  ★ run=false 空转：付费节点数=0 时钱闸根本不参与判定 → 验证钱闸必须先 run=true（E225）。
  ★ 单价键写错静默按 0：per_call / per_image 混用会让预算显示 0.00 却"各闸全过"
    → 已改成键缺失即「未解」，自检 125 → 127（E227）。
  ★ mirror 静默退回纯结构：`param_cache_dir` 没被契约透传 → 缓存增强整段被跳过，
    覆盖率还报「0/0」像是正常 → 已修契约透传 + 覆盖率加 `enabled` 标记（E228）。
    修后 THE TURN 参数级镜像：581 节点 / with_params 284 / missing 81（全是 group）。
  ★ 量级表键对不上：VIDEO_BANDS 键是大写 720P，模型 schema 给的是小写 720p
    → 无单价时的兜底估算对最贵的视频段恒为 None → 已加分辨率归一（E229）。
    修后 P0 四批量级区间：8–16 / 2–4 / 75–151 / 0–0（合计 85–171 积分，拟订、仅供参考）。
```

**分批点火已就绪**（G6 判据＝`run=true` 节点的引用链上全部 `generated: true`）：

```text
stage1  A1 A2 A3 S1（无引用）      预算 4.00
stage2  I1（引用 A1 A2）           预算 1.00
stage3  V1–V5（引用 I1 与资产）     预算 25.00
stage4  X1（合成，引用 V1–V5）      预算 0.00（video-clip 不计价）
四批实测：G1–G6 全过 · 「可否开跑：可以」 · exit=4（只 WARN：K11 未显式给 idempotencyKey，自动派生）
每批跑完回读并把上一批节点置 generated:true，否则下一批会被 G6 正确挡住。
```


---

## 6 · 状态表

| 阶段 | 目标 | 成本 | 依赖 | 状态 |
|---|---|---|---|---|
| P0 | 一次真实生产跑通 | 要花钱（需批准） | 无 | 未开始 |
| P1 | 成本基线 | 零 | P0 | 未开始 |
| P2 | 幂等与恢复实测 | 少量花钱 | P0 | 未开始 |
| P3 | 成片 QC 门 | 零 | 无 | **已完成 2026-10-12**（1 项未实测：缺 ffmpeg 的 WARN 路径） |
| P4 | 画像强制前置 | 零 | 无 | **已完成 2026-10-12**（2 个画像字段未覆盖） |
| P5 | 规模化与复用 | 按产量 | P0–P4 | 未开始 |

**推进纪律**：每阶段完成时把验收判据逐条打勾，并把证据路径写进本节；
未验证项标「未验证」，不许拿「看着像」顶替。
