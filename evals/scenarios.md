# evals/scenarios.md — 阶段一意图交付验收场景（本批新建）

> **新建声明（2026-10-22 / call8）**：本文件是**本批新建**的阶段一子集，
> 不是找回或重建旧全库 `evals/scenarios.md`。旧全库 scenarios 仍缺失且不可恢复；
> 本文件只覆盖 `INTENT-DELIVERY-01` 阶段一（意图 → 提示词正本 → 可复制 Markdown），
> 不声称恢复历史全库场景，也不削减 L1/L2 治理或全库其他场景缺口。

## 适用范围

- 目标：用户要的是一条/多条提示词，不是成片、画布或媒体。
- 正本：`04_prompt_packages.jsonl`（`prompt-package/v1`）。
- 独立验收：`scripts/verify_delivery_semantics.py`（输入只有权威输入与实际交付正文/参数）。

## 场景列表（与 `tests/test_intent_delivery.py` 对齐）

| ID | 场景 | 预期 |
|---|---|---|
| S1 | 公开样例：5 秒 / 9:16 / 剪纸空镜 / 雨声 / 固定俯拍 / 右上留白 / prompt_only | 全部显式值逐字保留并锁定 |
| S2 | 机位/构图/声音约束进入最终提示词或参数 | 通过；空镜无身份/服装/人声 |
| S3 | `prompt_only` | 不产生 `05/08` 计划、不建画布、不生成媒体；产物落盘 |
| S4 | 正本格式版本 | `prompt-package/v1`；旧渲染器仅单向适配 |
| S5 | 非空但格式未知/不支持 | 明确报错；不得 8 包 0 文档仍成功 |
| S6 | 最终俯拍改为平视 | FAIL `CONSTRAINT_SEMANTICS_VIOLATED` |
| S7 | 删除右上留白 | FAIL |
| S8 | 声音改为旁白 | FAIL |
| S9 | 正文追加 16:9 / 120 秒 | FAIL `DECISION_*_CONTRADICTED` |
| S10 | 权威图新增候选不交包 / 重复交包 / 错配 | FAIL `CANDIDATE_NODE_*` |
| S11 | 合法同义表达（正上方俯视） | PASS |
| S12 | 否定作用域（禁止音乐，旁白清晰朗读解说） | 旁白仍违规 |
| S13 | 恢复索引 | 包内可达、可校验；`evals/scenarios.md` 旧全库仍不可恢复 |

## 非覆盖

- 全库历史场景、L1/L2 全量场景库、其他任务号场景均不在本文件范围。
- 本文件不替代外部 `统一基准` 各册；仅提供阶段一迁移指针。
PY