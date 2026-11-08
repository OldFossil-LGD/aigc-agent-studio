# 提示词系统改造记录

> 依据：`AIGC_12Block_Prompt_System_Universal_Refactor_Spec_v1.0.md`（以下简称《改造书》）。
> 纪律：先审计实际源码，再改；保留 12 块名称与顺序；不针对任何剧情写特例；缺证据标 UNKNOWN，不宣称完成。
> 已执行结果与 §6 待办分别列出。

---

## 1 · 现状审计（代码证据）

| # | 事实 | 证据 | 判定 |
|---|---|---|---|
| A1 | 12 块规格存在，第 10 块名为【摄影机】 | `references/block-spec.md` §二 第 10 小节标题 | 规范齐 |
| A2 | 门禁按【运镜】判块齐全，B3 样例也写【运镜】 | `scripts/audit_prompt.py:170-171`；`references/unified-baseline/samples/B3_视频_单镜_15秒.md` | **命名不一致（已修）** |
| A3 | 样例有第 13 块【结尾留白】，规格只定 12 块 | B3 样例末尾；`block-spec.md` 目录 | **规格外条目（已并入第 12 块语义）** |
| A4 | 机器提示词包按角色分裂：`video_candidate` 无 composition/lighting/camera_spec/purpose | `scripts/compile_prompt_packages.py:19-34`（REQUIRED_BLOCKS） | 缺口确认 |
| A5 | 13 号交付正文与语义复核强绑定（逐镜 `##` 分段、工艺消费、时长矛盾、禁用词） | `scripts/verify_delivery_semantics.py:1532,1564` | 不能直接改排法 |
| A6 | 直接把 13 号改成 12 块排法 → 78 个契约测试里 14 个红（实测，已回滚） | 本轮执行记录 | 需先改复核器/测试 |
| A7 | 空镜在块门禁里被当"有人"判：3 条假 WARN（生理活性/静息微动/面部证据） | `scripts/audit_prompt.py:655-680`（改动前） | **空镜无豁免（已修）** |
| A8 | 此前不存在任何字段级权威 IR；事实分散在 01 至 04 + 13 号正文 | 仓库 `schemas/` 清单 | **P1 已补** |

---

## 2 · 本轮落地（P0 审计 + P1 核心）

| 交付 | 文件 | 验收 |
|---|---|---|
| IR 数据契约 | `schemas/production_ir.schema.json`（`production-ir/v1`，ValueWithProvenance） | 结构校验通过；`build` 产出可被 `validate` 读 |
| IR 构建 / 校验 / 编译 | `scripts/production_ir.py`（build / validate / render + `--self-test`） | 自检 14 项 0 失败 |
| 12 块确定性编译 | `production_ir.py render`：块 4/5/8/10 与块 6 从 IR 直取；空镜写 `人物：不适用` | 自检"12 块齐全""编译确定性""空镜 N/A"通过 |
| 块名对齐 | `audit_prompt.py` `BLOCK_ALIAS`：摄影机 ↔ 运镜 视为同一块 | 示例 rc 0 |
| 空镜豁免 | `audit_prompt.py`：`人物：不适用 / 空镜 / 无人物入画` 时跳过人物真实性检查 | 示例 rc 0；audit 自检 78/78 |
| 块 7 必需元素放宽 | 无角色镜头写 N/A 不再判"缺身份锚点" | 示例 rc 0 |
| 示例回归 | `提示词模板示例_12块_v4_20261031.md` | `audit_prompt blocks` **rc 0**；`ai_smell_check` **rc 0** |

---

## 3 · IR 字段 → 12 块映射（实现即契约）

| 块 | IR 来源 | 缺省行为 |
|---|---|---|
| 1 后期特效 | `project.postproduction_plan` | `N/A（调色与后期未给，站 3 裁决）` |
| 2 统一提质层 | `project.quality_profile` | `N/A（全片质感未给）` |
| 3 风险移除 | `requirements[operator=prohibits]` 汇总 | `N/A（未登记禁止项）` |
| 4 本镜目的 | `shot.purpose` | `N/A（本镜目的未给）` |
| 5 镜头规格 | `shot.delivery` + `shot.camera_spec` | 焦段写 `未给（lens_status=…）` |
| 6 构图 | `shot.composition` | `N/A` |
| 7 人物与环境 | `shot.asset_refs` | `character_refs=[]` → `人物：不适用` |
| 8 光位与影调 | `shot.lighting` | `N/A` |
| 9 时间线 | `shot.timeline.beats` | `N/A` |
| 10 摄影机 | `shot.camera_movement` | `N/A` |
| 11 声音 | `shot.audio_policy` | 允许/禁止/对白逐项打印 |
| 12 过渡压力 | `shot.transition`（`target_shot_id` 或 `END`） | 末镜允许 `END`，不虚构下一镜 |

---

## 4 · 已实现的结构化校验规则

`REQ_SOURCE_MISSING` · `REQ_LOCK_OVERRIDDEN` · `BLOCK_DUPLICATE_AUTHORITY` ·
`SHOT_DURATION_INVALID` · `PROJECT_DURATION_MISMATCH` · `SHOT_PRESENCE_CONFLICT` ·
`CAMERA_MOTION_CONFLICT` · `AUDIO_POLICY_VIOLATION` · `ASSET_REF_UNRESOLVED` ·
`TRANSITION_TARGET_INVALID` · `EQUIPMENT_UNRESOLVED`（WARN）· `CRAFT_VAGUE_LANGUAGE`（WARN）

输出格式按《改造书》附录 A：`issue_id / rule_id / severity / affected_paths / evidence / suggestion / validator_version`。

**实跑证据**（用 `C:/tmp/chain2/prod` 的真实编译产物建 IR）：
`3 镜 / 10 条要求 / 状态 BLOCK`，命中 `SHOT_PRESENCE_CONFLICT`（03 没有逐镜角色引用）与
`PROJECT_DURATION_MISMATCH`（intent 5s vs 产物 15s），外加 3 条 `EQUIPMENT_UNRESOLVED` WARN。
这些结果对应《改造书》R-05（资产漂移）与时长单一事实的要求。

---

## 5 · 兼容性处理

- 12 块名称与顺序不动；`摄影机/运镜` 双名并存（`BLOCK_ALIAS`），旧稿不返工。
- 13 号交付正文的排法**本轮不动**（A6 已证直接改会破 14 个测试）；IR 编译出的 12 块作为
  `15_Canonical_Prompt.md` 的权威版本，两者同源。
- 旧产物 → IR 的迁移是单向的：`build` 只读 01 至 04 + intent，不写回任何既有产物。

---

## 6 · 待完成项

| 项 | 状态 | 说明 |
|---|---|---|
| `REQUIRED_BLOCKS['video_candidate']` 扩到 4/5/8/10 + 统一 composition | **未做** | 需同时改 `compile_prompt_packages.py` 的产出与 78 个契约测试；本轮只做到"编译层可从 IR 取到这些块" |
| 13 号直接改成 12 块 | **未做** | 需重写 `verify_delivery_semantics.py` 的按段判定与 14 个测试 |
| 资产注册表 / identity_version / look_id 实际冻结 | **未做（P2）** | IR 已留字段，builder 目前填 `v001` 占位 |
| `story_time` 与 `screen_order` 区分 | **未做（P2）** | 字段已留，值为 null |
| 模型能力注册与适配器 | **未做（P3）** | IR 里 `required_capabilities` 未接 |
| 媒体 QC 与定向修复 | **未做（P3）** | 现有 `film_qc_gate.py` 仍是独立门禁 |
| 真实模型端到端验证 | **未做** | 无模型环境，不编造结果 |

---

## 7 · 下一步（按《改造书》顺序）

1. **P1 收尾**：把 `purpose / camera_spec / composition / lighting / camera_movement` 五个块
   写进 `REQUIRED_BLOCKS`，并让 `compile_prompt_packages` 从 IR 取值；同步改 14 个契约测试。
2. **13 号统一**：让 13 号直接渲染 IR 的 12 块，复核器改为"按块判约束"，保留逐镜时长与工艺消费。
3. **P2**：资产版本冻结与变更影响图；`story_time/screen_order` 接入连续性校验。
4. **P3**：能力注册表 + 适配器 + 媒体 QC 闭环。
