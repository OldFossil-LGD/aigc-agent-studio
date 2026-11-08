# 反推与复刻契约（Reverse Fidelity Contract）

日期：2026-10-11  
状态：反推/复刻类任务的**唯一模式入口**。  
本文件管“这次任务到底在证明什么”，执行细则分别引用其他文件，不在此复述。

## 1. 先声明模式，后动任何东西

任何反推、复刻、蒸馏、盲测、生产建图任务，动手前必须先落一行：

```json
{
  "mode": "content_reverse | copy_reverse | source_replica | rule_distill | production_build",
  "deliverable": "mirror | production_plan",
  "source_access": "original_readback | copy_readback | public_media | text_only | none",
  "source_project_uuid": "",
  "copy_project_uuid": "",
  "allowed_claim": ""
}
```

未声明模式 → 停止。不得边做边换模式。
`source_replica` / `copy_reverse` 未声明 `deliverable` → 门禁 `DELIVERABLE_UNDECLARED`，
**不默认走生产计划路径**。

## 2. 五种模式

| mode | 回答的问题 | 必需输入 | 允许声明 | 禁止声明 |
|---|---|---|---|---|
| `content_reverse` | 成片里发生了什么 | 成片 / 公开媒体 | 镜头、字幕、叙事、声音轨 | 源画布结构已复刻 |
| `copy_reverse` | 这份可访问副本里发生了什么 | 副本只读回读 | **副本级**结构、参数、边 | 原项目级、原画布级 |
| `source_replica` | 原画布如何构成 | **原项目可读**或身份证明完整的副本对照 | 源级复刻；按 `structure_only / full_replica` 再分层 | 用成片骨架或生产图冒充源级 |
| `rule_distill` | 从哪些规则能预测源工作流 | 训练集 + 盲测隐藏集 | 可泛化规则、盲测分数 | 未盲测就称“标准” |
| `production_build` | 当前平台怎样建一张可执行生产图 | 规格 / 剧本 / 计划 | 平台可执行、结构门禁通过 | 源级忠实 / 作者原工作流 |

**默认禁止跨模式升格。** 一份 `production_build` 结果不能只靠相似度升格为
`source_replica`；一份 `copy_reverse` 不能只靠节点血缘升格为原项目级。

### 2.1 产物类型必须先声明

同一个 `copy_reverse` 名下曾经产出两种完全不同的东西，交付时却叫同一个名字——
这是"每次反推都不对"的主因（实测：《大象》v1 规范化生产图 1443 节点 / 1740 边，
源副本 234 / 196）。

```text
mirror           忠实镜像源画布。节点/边/组 1:1，每个节点带 source_node_id，
                 只允许声明式省略媒体 URL / taskId / action 三层；缺 source_graph_path 即 FAIL
production_plan  规范化生产计划。允许拆批次、加契约层、重排结构，
                 但不许声明源级或副本级忠实（fidelity_claim 越权即 FAIL）
```

| 检查 | 门禁 |
|---|---|
| 未声明 deliverable | `DELIVERABLE_UNDECLARED` |
| mirror 缺 source_graph_path | `MIRROR_SOURCE_GRAPH_MISSING` |
| mirror 节点缺 source_node_id | `MIRROR_LINEAGE_MISSING` |
| plan 声明源级忠实 | `FIDELITY_CLAIM_NOT_AUTHORIZED` |
| mirror 结构量级越界 | `FIDELITY_OVERBUILD_*` / `FIDELITY_NODE_TOTAL` 等 |

## 3. 源访问层级

```text
original_readback  原项目可直接回读
copy_readback      只能读可访问副本
public_media       只能读成片、公开详情页和公开媒体
text_only          只有提示词、规格书或文本记录
none               没有源材料
```

硬规则：

1. `source_replica` 必须有 `original_readback`；否则最多是 `copy_reverse`。
2. `copy_readback` 必须在交付件里同时记录：副本 UUID、推定原项目 UUID、二者的证明方式。
3. 副本名带 `- 副本`、节点 `tracking.commonParams.project_uuid` 指向另一 UUID，
   都只能证明“可能来自原项目”，不自动证明副本与原项目全等。
4. 原项目返回 `private no permission` / `project not found` 时，不得把副本结果写成原画布级结果。

## 4. 六层证据等级

每条节点、边、参数、提示词、媒体和规则都必须标证据等级：

| evidence_class | 含义 | 可否进“已验证”结论 |
|---|---|---|
| `source_readback` | 从原项目实际回读 | 可以 |
| `copy_readback` | 从可访问副本实际回读 | 只能证明副本级 |
| `public_media` | 成片 / 公开页 / 公开媒体直接观察 | 可以证明内容层 |
| `text_explicit` | 提示词或规格书逐字写出 | 可以证明文本声明层 |
| `inferred` | 从训练集、资产语义或统计推断 | 必须标“推断”，不能伪装实测 |
| `unresolved` | 无证据 | 只能标“不可判定”，禁止生成假结论 |

状态与证据引用 `governance-law.md` L6/L8；本文件只增加“反推专用证据等级”。

## 5. claim ledger 最低字段

反推任务产出的每条结论必须能写成：

```json
{
  "claim_id": "C001",
  "statement": "……",
  "mode": "copy_reverse",
  "source_access": "copy_readback",
  "evidence_class": "copy_readback",
  "source_project_uuid": "…",
  "copy_project_uuid": "…",
  "status": "verified | proposed | n/a | undetermined",
  "evidence": ["path-or-readback"],
  "scope": "copy-level | original-level | content-level",
  "replacement": "",
  "test": ""
}
```

门禁：

```powershell
python scripts/reverse_claim_lint.py claims.json
```

## 6. 三态引用规则

节点级引用、边、参数和历史决策必须分为：

```text
explicit    文本 / 源回读明确给出
inferred    从训练集或资产语义可推断，标注置信度
unresolved  无证据；保留空缺，不生成假边、假参数、假模型
```

禁止把 `inferred` 写成 `explicit`；禁止把 `unresolved` 补成“看起来合理”的值。

## 7. 盲测门禁

任何“新标准 / 新工作流 / 新模板”在升级前必须通过：

```text
冻结源快照 -> 切 train/holdout -> 只给隐藏输入 -> 盲测预测 -> 逐单元对照
```

未通过盲测的规则只能是：

```text
proposed / example / work_profile
```

不能写成 `cross_work` 或 `standard`。

完整协议 → `references/blind-reverse-runbook.md`。

## 8. 作品画像优先

任何作品开始前先产出 `work_profile`，至少包含：

```text
节点与类型分布
段长 / 镜长
模型与 mode 主力
prompt 长度和块结构
参考图数量与挂载顺序
音频绑定
分组和版本 / 重试方式
源访问层级
```

**禁止先套 THE TURN 或其他作品的数值，再去迁就目标作品。**
THE TURN 是“长段长词派”的已验证样本之一，不是平台通则。

**★ 2026-10-12 起这是硬门**：反推类模式（`content_reverse / copy_reverse / source_replica / rule_distill`）
缺 `work_profile` → `mode_errors` 直接报 `WORK_PROFILE_MISSING`，编译器与门禁一并拒绝（不是警告）。

```powershell
python scripts/work_profile.py --units a.json,b.json --graph readback.json --out profile.json
```

契约里用 `work_profile_path` 指向它。实测依据：跨作品迁移 model 命中 0.25 / 0.00 / 0.00、
duration 0.67 / 0.07 / 0.00（见 `blind-reverse-runbook.md` §7.5）。

## 9. 与既有文件的关系

| 内容 | 权威入口 |
|---|---|
| 源级复刻的旧细则与阈值 | `references/source-fidelity-mode.md` |
| 生产编译器只负责可执行计划 | `references/production-compiler.md` |
| 盲测步骤 | `references/blind-reverse-runbook.md` |
| 证据 / 状态 / 数字纪律 | `references/governance-law.md` |
| claim ledger 机检 | `scripts/reverse_claim_lint.py` |
| 盲测门禁 | `scripts/blind_test_gate.py` |

本文件是模式入口；旧文件继续有效，只做指针，不重复定义。

## 10. 硬边界

```text
先声明模式
先认源访问层级
先冻结源快照
先分可判定 / 可推断 / 不可判定
先盲测，再升级标准
没有源权限，不写 source_replica
没有盲测，不写 standard
没有用户显式批准，不点火、不生成、不上传、不导出
```
