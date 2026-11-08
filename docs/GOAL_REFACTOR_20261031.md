# 架构审查与标准化实施记录（2026-10-31 起）

> 依据：
> - `AIGC_Agent_Studio_Architecture_Audit_20261031.md`
> - `AIGC_Agent_Studio_Codex_Standardization_Implementation_Plan_v1.0.md`
>
> 前一个目标（12 块提示词系统改造）见 `docs/GOAL_12Block_Refactor.md`，本文件接续它。
> 纪律：先审计后改；先红后绿；不宣称未验证的完成；不碰真实画布与付费生成。

## 1 · 任务状态

| 任务 | 状态 | 证据 |
|---|---|---|
| P0-01 video 引用边 NameError | **IMPLEMENTED / TESTED_OFFLINE** | `tests/test_graph_video_reference_actions.py` 6/6（先红：NameError） |
| P0-02 逻辑 ID → 平台名碰撞 | **IMPLEMENTED / TESTED_OFFLINE** | `tests/test_libtv_binding_uniqueness.py` 6/6（先红：3!=2） |
| P0-03 统一错误契约 | **IMPLEMENTED / TESTED_OFFLINE** | `scripts/error_contract.py` 4/4 |
| P1-01 图协议盘点 | **IMPLEMENTED** | `docs/implementation/P1_GRAPH_IR_REPORT.md` §1 |
| P1-02 Graph IR v2 | **IMPLEMENTED / TESTED_OFFLINE** | Schema + `workflow_graph_ir.py`（自检 10/10） |
| P1-03 端口能力注册 | **IMPLEMENTED（契约层）** | `schemas/port_registry.json`；text/image/video 事实端口，audio/video-clip 显式 UNKNOWN 并进 loss_report |
| P1-04 V1→V2 迁移 | **IMPLEMENTED / TESTED_OFFLINE** | `build_legacy_v1()` + `loss_report`（8/8） |
| P1-05 Graph Analyzer | **IMPLEMENTED（只读）** | `summary / diff / linkable / upstream / downstream / path / edge_references`（自检 14/14） |
| P2-01 Intent 来源链 | **PARTIAL** | `intent-handoff/v1` + `REQ_LOCK_OVERRIDDEN`；无 revision 历史表 |
| P2-02 GrillMe | **N/A_IN_THIS_REPO** | 本仓库无 `grill_*.py` / `creative_intent_contract.schema.json` |
| P2-03 Prompt AST v2 | **IMPLEMENTED / TESTED_OFFLINE** | Schema + `prompt_ast.py`（7/7） |
| P2-04 人物版本引用 | **PARTIAL** | 字段已接；未接真实资产库 |
| P2-05 Rule Registry | **IMPLEMENTED / TESTED_OFFLINE** | 13 条 + `rule_registry.py`（5/5） |
| P3-01～04 LibTV 闭环 | **BLOCKED_EXTERNAL_DEPENDENCY** | 无真实画布授权 |
| P4-01～03 媒体 QC/基准 | **BLOCKED_EXTERNAL_DEPENDENCY** | 无生成环境与人工标注集 |

## 2 · 复跑命令

```powershell
$PY='python'
& $PY -m unittest tests.test_graph_video_reference_actions tests.test_libtv_binding_uniqueness tests.test_graph_ir_v2
& $PY scripts\workflow_graph_ir.py --self-test
& $PY scripts\prompt_ast.py --self-test
& $PY scripts\rule_registry.py --self-test
& $PY scripts\studio_run.py --self-test
& $PY scripts\lib_health.py
& $PY scripts\lib_doctor.py
```

## 3 · 阻断与待完成项

1. LibTV 真实读回 / 写前版本指纹 / PARTIAL_APPLY 恢复：无授权环境。
2. 真实媒体 QC 与基准集：无生成环境与人工标注。
3. GrillMe：本仓库缺该模块，P2-02 需要相应源码。
4. 资产版本与 revision 历史：字段已留，未接素材库。

## 4 · 变更日志

| 日期 | 内容 |
|---|---|
| 2026-10-31 | P0 三项修复（先红后绿）；Graph IR v2 + 迁移 + 只读分析；只 data_reference 落线；Prompt AST v2 + 约束覆盖；Rule Registry；`studio_run` 增 18/19 号产物；实现文档 5 份 |
