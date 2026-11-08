# 源级复刻模式（Source Fidelity Mode）

> **模式入口已升级**：先按 `references/reverse-fidelity-contract.md`
> （`reverse-fidelity-contract.md`）区分
> `content_reverse / copy_reverse / source_replica / rule_distill / production_build`。
> 本文件保留为 `source_replica` 的结构量级细则与阈值，不再独自定义“反推”全流程。
> 盲测细则另见 `blind-reverse-runbook.md`；旧反推执行记录见 `film-reverse-runbook.md`。
> 副本级任务不得因本文件标题含“源级”就升格为原项目级。

日期：2026-10-08  
状态：新增硬门规则，防止把“成片骨架图”冒充“源画布复刻”。

## 1. 两种任务必须先分型

```text
film_reverse
= 从成片反推叙事、镜头、声音和装配
= 验收对象是成片，不要求复刻源画布生产图

source_replica
= 复刻已有源画布的节点、边、分区、素材迭代和候选版本
= 验收对象是源画布，不能用成片骨架替代
```

未声明模式时，不得声称“复刻源画布”。禁止把两种任务的结果混在同一张画布里验收。

## 2. 源级复刻必须先冻结源基线

开始建图前，先只读回读源画布，产出：

```json
{
  "node_total": 0,
  "edge_total": 0,
  "type_counts": {},
  "edge_pair_counts": {},
  "group_total": 0,
  "media_node_counts": {},
  "candidate_chain_counts": {}
}
```

基线必须来自实际回读，不用目录、摘要、截图或转述。

## 3. 硬门

源级复刻的计划图必须通过 `scripts/source_fidelity_lint.py`。

阈值是**双向区间**：低于下限是丢结构，高于上限是造结构，两边都 `FAIL`。

```text
维度              下限      上限
node_total        0.95      1.10
edge_total        0.95      1.10
主要类型计数       0.90      1.10
group_total       0.80      1.10
```

任一核心维度越界 → `FAIL`，不得声称源级复刻完成。

`mirror`（忠实镜像）还要逐个节点带 `source_node_id`，源节点覆盖必须 100%：

```text
缺字段              FIDELITY_NO_LINEAGE
对不上源节点        FIDELITY_UNMAPPED_SOURCE_NODES（带 coverage）
指向源里没有的节点  FIDELITY_EXTRA_PLAN_NODES
```

当 deliverable=mirror 且 lineage=on 时，血缘还须一对一，重复指向同一源节点报
FIDELITY_DUPLICATE_LINEAGE。按 source_node_id 把计划边端点映射回源节点后，对照有向边及其重数。
报告 topology_fidelity 列出实际匹配、缺失和额外边，源边覆盖率低于 --min-edge-ratio 时
报 FIDELITY_EDGE_TOPOLOGY。原有双向数量阈值继续生效，production_plan 保留结构重排能力。
镜像拓扑对照遇到重复或缺失节点 ID、悬空边时分别报 FIDELITY_NODE_IDS_INVALID、
FIDELITY_DANGLING_EDGES。该检查仍仅覆盖离线结构。

★ 实测动机（2026-10-11）：单向阈值下，《大象》v1 规范化生产图 **1443 节点 / 1740 边**
（源副本 234 / 196，比例 6.17 / 8.88）在 `node_total` 与 `edge_total` 两项上是**通过**的；
同时计划用 `node_type`、源回读用 `type`，类型层两边都读不到数，报出来的 `FIDELITY_TYPE_*`
是假失败。两条叠在一起，就是"错的产物拿走一个像样的绿"的机制。

### 3.1 源级复刻不是只比节点数

全量对照至少覆盖以下维度：

```text
项目元数据与名称
节点类型与 action
节点顺序与 parent/group
节点位置与重复坐标
边数量与边型矩阵
模型与 modeType 分布
settings 参数分布
提示词非空数量、长度与模板结构
{{Node}} 等引用占位符
image/video/text/audio 引用列表与 Order
媒体 URL、poster、assetId
taskId、status、完成数量
text/data.content 正文
audio、装配和 video-story/video-clip 层
```

### 3.2 两种源级模式

```text
structure_only
= 只复刻结构，不生成媒体
= 必须明确 media/task/status 层未复刻

full_replica
= 需要复刻媒体、任务和完成状态
= 任一媒体/任务维度缺失即 FAIL
```

`structure_only` 不得被写成 `full_replica` 或“源级等价复刻”。

《Wrong Room》实测反例：

```text
副本：138 节点 / 199 边 / 119 有 URL 节点 / 79 taskId / 78 status=2
逆推：600 节点 / 501 边 / 0 有 URL 节点 / 0 taskId / 0 status=2
```

即使逆推节点更多，也不能判为源级等价复刻。

允许有意省略媒体 URL、任务号和生成结果；不允许用“无点火”当理由删掉结构性图片迭代链、参考边、候选视频和分组批次。

## 4. 已踩过的反例

《放殃》：

```text
源副本：437 节点 / 377 边 / 319 image / 61 video / 49 group
错误替代：157 节点 / 167 边 / 12 image / 41 video / 9 group
```

图片覆盖率只有 `12 / 319 ≈ 3.8%`，`image→image` 迭代链基本缺失。该图只能是 `film_reverse` 骨架，不能称为 `source_replica`。

## 5. 命令

```powershell
python scripts/source_fidelity_lint.py `
  --source source_project.json `
  --plan plan_project.json `
  --mode copy_reverse `
  --deliverable mirror `
  --json-out source_fidelity_result.json
```

可调项：`--min-node-ratio / --max-node-ratio / --min-edge-ratio / --max-edge-ratio /
--min-type-ratio / --max-type-ratio / --min-group-ratio / --max-group-ratio`、
`--deliverable auto|mirror|production_plan`、`--lineage auto|on|off`。

`--deliverable mirror` 会把血缘检查打开；`production_plan` 默认关闭，因为规范化计划
本来就会重排节点，血缘不由它承担。自检：

```powershell
python scripts/source_fidelity_lint.py --self-test
python scripts/fidelity_regression.py     # evals/fidelity 里的真实数据 golden 用例
```

退出码：

```text
0 = PASS
1 = FAIL
2 = 输入或参数错误
3 = NOT_VERIFIED（源图没有节点与边，缺失基线时不判 PASS/FAIL）
```

本门禁只判结构与量级，不点火、不生成、不上传、不导出。

## 6. 与生产编译器的关系

`source_replica` 也必须先经过生产编译器：

```text
compile_production.py
→ source_baseline 必须写入 production_contract
→ production_capability_gate.py
→ source_fidelity_lint.py
```

只跑源结构比对、不跑生产角色门禁，不算完成源级复刻。
