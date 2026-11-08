# P2 意图与提示词报告（P2_INTENT_PROMPT_REPORT）

## 1 · Prompt AST v2

- Schema：`schemas/prompt_ast.v2.schema.json`（`prompt-ast/v2`）
- 实现：`scripts/prompt_ast.py`
  - `build(ir)`：每镜生成 `fields{purpose, camera_spec, composition, lighting, timeline, sound}`
    + `identity_refs[{character_id, identity_version, look_id, continuity_state_id}]`
  - 每字段带 `source_decision_ids`（从 `requirements` 反查）；没有来源的字段 `status=N/A|UNKNOWN`
  - `coverage()`：locked+hard 约束逐条判定是否在 AST 文本中有消费路径；未消费 →
    `CONTRACT_UNCONSUMED_CONSTRAINT`（**ERROR**，阻断编译）
  - `render_blocks()`：12 块阅读版从 AST 渲染（缺字段写 `N/A（未给）`）

**12 块 → AST → 角色块 → 执行视图**（节选；完整表见 `docs/prompt_audit.md` 与 `block-spec.md`）：

| 12 块 | AST 字段 | 角色块（compile_prompt_packages） | 执行视图 |
|---|---|---|---|
| 4 本镜目的 | `fields.purpose` | `purpose`（本轮补齐） | `15_Canonical` / 模型短提示 |
| 5 镜头规格 | `fields.camera_spec` | `camera_spec` | 同上 |
| 6 构图 | `fields.composition` | `composition` | 同上 |
| 8 光位与影调 | `fields.lighting` | `lighting` | 同上 |
| 10 摄影机 | `fields.camera_movement`（AST 归入 camera 字段组） | `camera_movement` | 同上 |
| 11 声音 | `fields.sound` | `sound` | 同上 |

## 2 · 锁定项消费证明

`prompt_ast.py coverage --ast out/18_prompt_ast.json` 输出：

```json
{"issues": [...]}
```

- 有 locked+hard 约束但 AST 无消费 → `severity=ERROR`，退出码 1；
- 字段未给 → `PROMPT_FIELD_UNKNOWN`（WARN，渲染为 N/A，不编）。

## 3 · GrillMe（P2-02）

**`N/A_IN_THIS_REPO`**：`scripts/grill_session.py` / `grill_bank.py` / `grill_ledger.py` 与
`schemas/creative_intent_contract.schema.json` 在本仓库不存在（见 CURRENT_STATE §1）。
本仓库的意图入口是 `intent-handoff/v1`（`scripts/intent_handoff.py` + `schemas/intent_handoff.schema.json`），
其 `source / locked / evidence` 可承载用户锁定项的要求（`REQ_LOCK_OVERRIDDEN`）。
P2-02 需要先导入审查对象（zip）中的 GrillMe 源码，再进行适配。

## 4 · Rule Registry（P2-05）

- 数据：`docs/implementation/rule_registry.json`（13 条：图/IR/AST 关键规则）
- 校验：`scripts/rule_registry.py`（rule_id 唯一、severity 合法、owner_doc/test_id 真实存在）
- 实跑：`{"issues": [], "count": 13}`

## 5 · 测试

```text
python scripts/prompt_ast.py --self-test      7/7
python scripts/rule_registry.py --self-test   5/5
```

覆盖：来源 id、身份版本、锁定约束命中/未命中、未消费=ERROR、12 块渲染、注册表缺文件/重复 id。
