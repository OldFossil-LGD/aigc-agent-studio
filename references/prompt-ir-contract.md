# Production IR 契约（12 块的上游唯一事实源）

> **何时读**：要改提示词系统本身（块契约、编译器、校验规则）；或发现"同一条事实在两个块里不一样"；
> 或要把旧产物接进新链路。**写一条具体镜头的提示词，不用读本册**——那走 `block-spec.md` 与站 6。
> **本册是口径册**：定义谁权威、谁能改、缺证据怎么写。

## 1 · 一句话口径

**`production-ir/v1` 是唯一事实源；12 块是它的确定性编译结果，不是权威数据。**
下游（13 号正文、模型请求、审核报告）都从 IR 派生，**不许反向覆盖 IR**。
审计证据与缺口清单见 `docs/prompt_audit.md`。

## 2 · 数据形状（`schemas/production_ir.schema.json`）

```text
project   delivery{aspect_ratio, fps, duration_sec} · quality_profile · postproduction_plan · audio_policy
requirements[]   每条带 scope / field_path / operator / strength / source_type / locked
assets    characters[character_id, identity_version, look_id] · locations · props
shots[]   purpose · delivery · camera_spec · composition · lighting · camera_movement
          timeline.beats[] · asset_refs · audio_policy · transition
```

每个需要追溯的值都是 `ValueWithProvenance`：
`{value, source_type, source_ref, locked, approval_status, confidence, reason}`。
`source_type` 只认七种：`user_explicit / user_derived / script / approved_project_policy /
library_default / agent_proposed / tool_observation`。

**`library_default` 与 `agent_proposed` 不得伪装成用户要求**——这条是本册存在的第一原因。

## 3 · 来源与锁定的执行方式

| 情况 | 行为 |
|---|---|
| 用户原话（`user_explicit`） | 默认 `locked=true`；被改动 → `REQ_LOCK_OVERRIDDEN`（BLOCK） |
| Agent 补的（`agent_proposed`） | 只能留在自己字段里；批准后写 `approval_status=approved`，**不回写来源** |
| 库默认（`library_default`） | 必须带 `source_ref`（哪一册/哪一预设）；缺 → 视为未给 |
| 缺证据 | 值写 `null` + `reason`；渲染成 `N/A（原因）`，不编 |
| 空镜 | `character_refs=[]`；块 7 写 `人物：不适用`；禁止再写人物/局部/影子 |

## 4 · 12 块从哪来（编译映射）

| 块 | IR 字段 | 缺省写法 |
|---|---|---|
| 1 | `project.postproduction_plan` | `N/A（站 3 裁决）` |
| 2 | `project.quality_profile` | `N/A（全片质感未给）` |
| 3 | `requirements[operator=prohibits]` | `N/A（未登记禁止项）` |
| 4 | `shot.purpose` | `N/A` |
| 5 | `shot.delivery` + `shot.camera_spec` | 焦段 `未给（lens_status=…）` |
| 6 | `shot.composition` | `N/A` |
| 7 | `shot.asset_refs` | 无角色 → `人物：不适用` |
| 8 | `shot.lighting` | `N/A` |
| 9 | `shot.timeline.beats` | `N/A` |
| 10 | `shot.camera_movement` | `N/A` |
| 11 | `shot.audio_policy` | 允许/禁止/对白逐项 |
| 12 | `shot.transition` | 末镜允许 `END` |

块名：**第 10 块写作【摄影机】，与【运镜】视为同一块**（门禁 `BLOCK_ALIAS`）。
【结尾留白】不再是第 13 块，归入第 12 块的 `end_state`。

## 5 · 命令

```text
python scripts/production_ir.py build    --artifacts out/ --intent intent.json --out out/16_production_ir.json
python scripts/production_ir.py validate --ir out/16_production_ir.json
python scripts/production_ir.py render   --ir out/16_production_ir.json --out out/15_Canonical_Prompt.md
python scripts/production_ir.py --self-test
```

退出码：0 通过 ｜ 1 有 BLOCK ｜ 2 用法错误 ｜ 4 只有 WARN/UNKNOWN。
`validate` 输出按《改造书》附录 A：`issue_id / rule_id / severity / affected_paths / evidence / suggestion`。

## 6 · 规则清单（本册登记，脚本实现）

BLOCK：`REQ_SOURCE_MISSING` · `REQ_LOCK_OVERRIDDEN` · `BLOCK_DUPLICATE_AUTHORITY` ·
`SHOT_DURATION_INVALID` · `PROJECT_DURATION_MISMATCH` · `SHOT_PRESENCE_CONFLICT` ·
`CAMERA_MOTION_CONFLICT` · `AUDIO_POLICY_VIOLATION` · `ASSET_REF_UNRESOLVED` ·
`TRANSITION_TARGET_INVALID`
WARN：`EQUIPMENT_UNRESOLVED` · `CRAFT_VAGUE_LANGUAGE`

**校验以结构化字段为主**；文本扫描只作补充（`CRAFT_VAGUE_LANGUAGE` 是唯一的关键词类规则，
且只给 WARN）。不确定的物理/审美问题一律 `UNKNOWN`，不冒充 PASS。

## 7 · 迁移（旧产物 → IR）

`build` 只读 `01–04` 与 `intent-handoff/v1`，单向生成 IR，**不写回**任何既有产物；
不存在的字段写 `null` 并给 `reason`，由 `validate` 报 `REQ_SOURCE_MISSING` / `EQUIPMENT_UNRESOLVED`。

实跑样例（`C:/tmp/chain2/prod`）：3 镜 / 10 条要求 / 状态 BLOCK，
命中 `SHOT_PRESENCE_CONFLICT`（03 无逐镜角色引用）与 `PROJECT_DURATION_MISMATCH`（intent 5s vs 产物 15s）。
—— 这两条是真实缺口，不是误报。

## 7.5 · 下游三段（P3）

| 段 | 脚本 | 判据 |
|---|---|---|
| 能力预检 | `scripts/model_adapter.py`（配 `schemas/model_capability.schema.json`） | 能力 `no`／超时长上限 → BLOCK；`unknown` → WARN；**永不发请求** |
| 媒体 QC | `scripts/media_qc.py` | 复用 `film_qc_gate.py`，把问题映射到 shot_id，输出统一 issue |
| 定向修复 | `media_qc.py --repair-plan` | 只给影响域与建议；`auto_retry=false`，真实重跑须再批准 |

## 8 · 不做什么

- 不把 12 块当权威；不手改渲染结果（要改改 IR 再重编）。
- 不把 `library_default` 写成"用户要求"；不为了填满块而编器材/人物。
- 不在本册替代 `block-spec.md`（块内写法）与 `shot-craft.md`（镜头工艺）。
- 不宣称 P2/P3 已完成：资产版本冻结、`story_time/screen_order`、模型能力注册与媒体 QC
  仍是缺口，清单见 `docs/prompt_audit.md` §6。
