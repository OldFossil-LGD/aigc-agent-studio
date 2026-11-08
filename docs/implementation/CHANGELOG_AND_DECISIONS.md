# 变更与决策记录（CHANGELOG_AND_DECISIONS）

## 2026-10-31

### 修复
- `graph_plan_lint.py`：video→video 引用边改为 `_video_action()` 三态判定，消除 `NameError`；
  未知 action → `UNDET`（不推定安全）。
- `compile_libtv_commands.py`：`binding_map`（单射、确定性、带哈希后缀）+ `logical_node_id`；
  `{{Node "..."}}` 与建图共用同一映射；只有 `data_reference` 落 `node_link`，其余进 `skipped_links`。

### 新增
- `scripts/error_contract.py`（统一错误契约）
- `schemas/workflow_graph_ir.v2.schema.json` + `scripts/workflow_graph_ir.py`
  （build/validate/summary/diff/linkable）
- `schemas/prompt_ast.v2.schema.json` + `scripts/prompt_ast.py`（build/coverage/12 块渲染）
- `scripts/rule_registry.py` + `docs/implementation/rule_registry.json`（13 条）
- `scripts/studio_run.py` 增 18 号 Prompt AST、19 号 Graph IR 两个产物
- 测试：`test_graph_video_reference_actions.py`、`test_libtv_binding_uniqueness.py`、`test_graph_ir_v2.py`

### 决策
1. **边语义不猜**：旧 `purpose` 未登记 → `unknown` + `loss_report`，绝不默认成引用边（I-04/I-05）。
2. **端口未知不落线**：`GRAPH_TARGET_PORT_UNKNOWN` 只 WARN，落线闸门只认 `data_reference`。
3. **命名不做先来后到**：同基名冲突时**全部**加哈希后缀，保证同一输入多次编译映射稳定。
4. **错误契约只新增不批量改造**：旧模块保持返回结构，新模块统一 `code/severity/path/...`，避免破坏消费者。
5. **GrillMe 不做代替实现**：本仓库缺该模块，标 `N/A_IN_THIS_REPO`，不凭空重写并宣称完成。

### 兼容性
- 旧 CLI 参数与既有 JSON 文件名不变；新增字段（`binding_map`、`skipped_links`、`logical_node_id`）为增量。
- v1 Schema 未改动；v2 为新增文件。

### 未验证（明确）
- 未连接真实 LibTV；未做平台读回、写前指纹、PARTIAL_APPLY 恢复。
- 未做真实媒体生成与人工评审；`media_qc.py` 仅归一 + 计划，不自动重跑。
