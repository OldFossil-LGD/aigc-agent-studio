# P1 Graph IR 报告（P1_GRAPH_IR_REPORT）

## 1 · 旧图协议盘点（逐字段，含丢失标注）

| 来源 | 节点键 | 边键 | 落到 v2 的情况 |
|---|---|---|---|
| `schemas/shot_graph_plan.schema.json` | `id / role / node_type / model / settings` | `source / target / purpose` | 边 kind 靠 `purpose` 映射；**端口缺失** → `status=UNKNOWN` |
| `graph_plan_lint.py` | `node_id / node_type / role / action` | `source_id / target_id / kind` | kind 已是语义名；`action` 保留在 `legacy` |
| `compile_production.py:_mirror_graph` | `id / node_type / role / run` | `id / source / target / kind` | **端口、输入槽位、参考顺序不保留** → 标 `LOSSY` |
| `compile_libtv_commands.py` | 逻辑 `id` | 逐边 → `node_link` | **已改为只落 `data_reference`**，其余进 `skipped_links` |

> 结论：旧链路里“有边就连”的假设被移除；`purpose` 未登记 → `kind=unknown` 且写 `loss_report`。

## 2 · 新协议

- Schema：`schemas/workflow_graph_ir.v2.schema.json`（`workflow-graph-ir/v2`）
- 实现：`scripts/workflow_graph_ir.py`
  - `build_legacy_v1()`：旧图 → v2；不可无损字段进 `loss_report`（`LOSSY` / `UNKNOWN`）
  - `validate()`：端点、种类、重复边、自环、环（可声明 `allowed_cycles`）、目标端口未知（WARN）、
    端口类型不匹配、同槽位参考顺序重复
  - `linkable()`：**仅 `data_reference`**（或 `platform_mapping.approved=true` 的 `assembly`）可落线
  - `diff()`：节点/边/参考顺序差异（供影响分析）
  - `summary()`：节点数/边数/种类分布/损失条数

## 3 · 边语义表（与任务书 §5 对齐）

| kind | 含义 | 可落 LibTV 物理线？ |
|---|---|---|
| `data_reference` | 数据/素材输入 | 仅在端口已知且映射未冲突时 |
| `control_dependency` | 先后执行 | **否**（进 `skipped_links`） |
| `assembly` | 装配/合成 | 默认否；需 `platform_mapping.approved=true` |
| `lineage` | 来源/派生 | 否 |
| `condition` | 条件分支 | 否（平台控制结构未验证） |

## 4 · 不变量核对

| 不变量 | 落点 |
|---|---|
| I-02 逻辑 ID 与平台名不混用 | `binding_map` + `logical_node_id` |
| I-03 边 kind/port/order 不无解释丢失 | `legacy` 原样保留 + `loss_report` |
| I-04 UNKNOWN 不自动落线 | `linkable()` 只认 `data_reference`，端口未知只 WARN |
| I-05 逻辑依赖不转物理线 | `compile_libtv_commands` 的 `skipped_links` |

## 5 · 测试

```text
python scripts/workflow_graph_ir.py --self-test         10/10
python -m unittest tests.test_graph_ir_v2                8/8
python -m unittest tests.test_graph_video_reference_actions tests.test_libtv_binding_uniqueness  12/12
```

覆盖：分支/重复边/自环/环/未知端口/未知 purpose/参考顺序变化/端点缺失/编译期只落数据参考边。

## 6 · 待验证与待实现项

- 端口能力注册表只有 `text/image/video` 三类的事实端口；`audio / video-clip` 标 `UNKNOWN`（平台未验证）。
- 未接真实 LibTV 读回（P3）。
- `_mirror_graph` 的端口丢失只做了**标注**，未改造其输出结构（避免破坏旧消费者）。
