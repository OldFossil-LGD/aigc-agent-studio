# 12 块提示词系统通用化实施记录

> 记录时状态为**进行中**。下文保留该次改造的任务状态与验证输出。
> 依据：`AIGC_12Block_Prompt_System_Universal_Refactor_Spec_v1.0.md`（P0 至 P4）。
> 纪律：不宣称未验证的完成；BLOCK 类问题必须修，不能绕过；每一项都要有可复跑的命令。

---

## 验收总表（按改造书章节）

| 章节 | 要求 | 状态 | 验证 |
|---|---|---|---|
| P0 §2 | 盘点实际代码、保留 12 块名称与顺序 | **DONE** | `docs/prompt_audit.md` §1（A1 至 A8，逐条代码证据） |
| P0 §10.2 | `REQUIRED_BLOCKS` 覆盖全部 12 块、跨角色一致 | **DONE** | `scripts/compile_prompt_packages.py` 块表；`pytest`/unittest 76 例 |
| P1 §3 | Production IR（唯一事实源 + 字段级 provenance） | **DONE** | `schemas/production_ir.schema.json`；`production_ir.py --self-test` 14 项 |
| P1 §4 | 12 块 Canonical Prompt 确定性编译、块所有权唯一 | **DONE** | `production_ir.py render`；自检「12 块齐全/确定性/空镜 N/A」 |
| P1 §4.1.5/§4.1.8 | 空镜 `人物：不适用`；缺证据 `N/A`，不编 | **DONE** | `audit_prompt blocks` 于 v4 示例 rc 0 |
| P1 §6 | 结构化校验规则（BLOCK/WARN）+ 统一 issue 格式 | **DONE** | `production_ir.py validate`；规则清单见 `prompt-ir-contract.md` §6 |
| P1 §6.2 | 13 号交付正文由 IR 渲染（单一实现） | **DONE（开关式）** | `--canonical-13`：13 号渲染 12 块；示例实测 `verification_status=PASS`、15 个【块】；默认仍走旧排法保护 78 个契约测试 |
| P2 §3.2 | 资产注册表：identity_version / look_id / 角色一致性 | **PARTIAL** | IR 字段与 `asset_registry` 占位已接；**未接真实素材库** |
| P2 §5 | story_time 与 screen_order 分离 | **DONE** | `production_ir.py` 写入 `story_time` / `screen_order`；规则 `STORY_TIME_INVALID` |
| P2 §5 | 连续性状态与变更传播 | **PARTIAL** | `continuity_state_id` 字段 + `CONTINUITY_UNRESOLVED` WARN；无状态图谱 |
| P3 §7 | 模型能力注册表 | **DONE（契约层）** | `schemas/model_capability.schema.json`；`CAPABILITY_UNREGISTERED` WARN |
| P3 §8 | 适配器接口 / 请求渲染 / 响应归一 | **PARTIAL** | `scripts/model_adapter.py`（接口 + 校验 + dry-run 请求体），**无真实 provider** |
| P3 §6 | 媒体 QC（黑帧/静音/时长/画幅/fps/切点） | **DONE（封装）** | `scripts/media_qc.py` 调 `film_qc_gate`，输出统一 issue 格式 |
| P3 §6.4 | 定向重生成（最小影响域 + 成本估算） | **PARTIAL** | `media_qc.py --repair-plan` 只给影响域与建议，不自动重跑 |
| P4 §9 | 跨题材/风格回归 fixtures | **DONE** | `tests/fixtures/ir_matrix/*.json`（5 例：空镜/人物/对白/机位冲突/空泛）+ `tests/test_ir_matrix.py`（5 例断言规则命中与 12 块形态） |
| P4 §9 | 迁移报告与兼容性 | **DONE** | `docs/prompt_audit.md` §5/§6 + 本表 |
| 全局 | 真实模型端到端 | **BLOCKED** | 无 provider 凭据与模型环境；不编造结果（见 §缺口） |
| **有机纳入** | 默认执行标准流程，使用单命令入口和阶段门 | **DONE** | `scripts/studio_run.py`（一条命令出 10/11/12/15/16，自检 8 项）；`stage_gate.py` 默认在 S4 查拆解、S6 查 IR 与 12 块视图（老工程实测 S4/S6 双红）；零改造项目不再能绕过 |

---

## 待完成项

1. **真实模型端到端**：仓库里没有可用的图像/视频 provider 凭据与本机模型服务，P3 的"真实适配"只能到接口与请求体层。要打通需用户提供：provider、模型名、endpoint、密钥注入方式。
2. **资产注册表接素材库**：`identity_version/look_id` 目前由 02 的 `state_versions` 推导，未接实际出图记录（B1/B2 资产册）。
3. **连续性图谱**：`continuity_state_id` 只是字段，没有"状态变更影响哪些镜头"的图。

---

## 复跑命令（每次改动后必跑）

```powershell
$PY='python'
& $PY scripts\production_ir.py --self-test
& $PY scripts\audit_prompt.py --self-test
& $PY -m unittest tests.test_intent_delivery tests.test_other_constraint_delivery tests.test_delivery_evidence_entry tests.test_quality_fixes_20261025 tests.test_craft_delivery tests.test_ir_matrix
& $PY scripts\lib_health.py
& $PY scripts\lib_doctor.py
```

全部退出码 0（`lib_doctor` 允许既有 `unified-baseline` 的 315 行 WARN；`audit_prompt index` 的 rc 4 属基线）。

---

## 变更日志

| 日期 | 内容 |
|---|---|
| 2026-10-31 | P0 审计 + P1 核心（IR/编译/校验）；空镜与块名口径修复；示例 v4 rc 0 |
| 2026-10-31 | **有机纳入**：新增 `studio_run.py` 单入口；`stage_gate.py` 增 `extras`（S4→10_breakdown.json，S6→16 IR 无 BLOCK + 15 视图），自检补正反例；`default-standard.md` 必产列同步；25 脚本自检全过 |
| 2026-10-31 | P1 收尾：`REQUIRED_BLOCKS` 覆盖 12 块（补 purpose/camera_spec/composition/lighting/camera_movement/style_detail/transition），13 号增 `--canonical-13`（实测 verification PASS）；P2 story_time/screen_order + STORY_TIME_INVALID/CONTINUITY_UNRESOLVED；P3 能力注册表 + `model_adapter.py` + `media_qc.py`；P4 五例 IR matrix（83 tests OK） |
