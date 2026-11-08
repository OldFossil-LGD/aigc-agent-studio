# P0 修复报告（P0_FIX_REPORT）

## T-P0-01｜video→video 引用边 NameError

修复前的测试结果如下。

```text
python -m unittest tests.test_graph_video_reference_actions
NameError: name 'sa' is not defined  （4 errors）
```

根因是`graph_plan_lint.py` 的 `check_edges()` 在 video→video `reference` 分支使用未定义变量 `sa`。

修复时新增 `_video_action(node)`，从 `action / task_action / op / operation` 以及
`params / settings / model_config / overlay / meta` 中提取三态：

- `video_generate` → `FAIL / EDGE_V2V_REF_FORBIDDEN`（生成物不得进下游引用槽位）
- `video_resource` → `PASS / EDGE_V2V_RESOURCE`
- 取不到 → `UNDET / EDGE_V2V_UNDETERMINED`（**不推定安全**，I-04）

端点缺失仍走 `EDGE_DANGLING`，不再抛异常；非引用边行为不变（`EDGE_V2V_NONREF`）。

修复后 6/6 通过；`graph_plan_lint.py --self-test` 仍通过。

## T-P0-02｜逻辑 ID → LibTV 名称碰撞

修复前，`shot__a` 与 `shot_a` 编译成同名 `shot_a`（测试断言 `3 != 2`）。

修复包含以下改动。

- 新增 `_platform_base()` 与 `build_binding_map()`：基名相同的 ID **全部**加 `_<sha1(逻辑ID)[:6]>` 后缀（不做先来后到）；后缀仍撞则加长哈希；映射确定性可复现。
- `node_create` 增加 `logical_node_id`；输出增加 `binding_map`。
- `_sanitize_refs(text, binding)`：提示词里的 `{{Node "..."}}` 与建图**共用同一张映射表**，不再各自 `replace("__","_")`。

**修复后**：6/6 通过（含"多次编译映射一致""引用与建图同名""链接端点存在"）。

## T-P0-03｜统一错误契约

新增 `scripts/error_contract.py`：`mk_error(code, severity, message, path, node_id, edge_id, fix, evidence)`，
severity 仅 `ERROR / WARN / UNDET`；`normalize()` 可把旧三元组 `(verdict, code, message)` 归一。
**新代码一律走该契约**；旧模块保留原返回结构（兼容，不批量改造）。

## 验收对照

| 要求 | 结果 |
|---|---|
| 三类 video reference 可预测返回 | PASS / FAIL / UNDET 三态已覆盖（6 例） |
| 名称冲突在编译阶段阻断 | 同基名自动后缀，整图唯一（6 例） |
| 现有相关回归不退化 | `test_apply_libtv_plan`、`test_graph_integrity` 等 31 例通过 |
| 未触碰真实画布 | 是（全部 dry-run/离线） |
