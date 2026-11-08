# 资产流水线（引用计划 · 四层 QC · 错误码 · 重试）

> **何时读**：手上已有资产、要决定"这一镜挂哪几张、过了没有、不过修哪一步"时。
> **读完回哪**：资产本体 → `asset-standard.md`；九块写法 → `block-playbook-asset.md`；平台参数 → `platform-matrix.md`。
> **★ 地位**：本册是 `asset-standard.md` 的**执行半册**——那册管"产什么、什么层、什么状态"，本册管"怎么引用、怎么判过、怎么修"。
> **★ 与规划文件的关系**：模型取自 `CHARACTER_PIPELINE_PLAN` §6–§9（ReferencePlan · 分层 QC · 错误码 · 预算），**服务层（FastAPI / Temporal / PostgreSQL / ComfyUI）不在本库实现**，见 §8。

---

## §1 流水线（本库口径）

| 规划文件 | 本库对应 | 产出 | 门禁 |
|---|---|---|---|
| C01–C04 意图 → 身份锁定 | 站 1–4 + 站 5 | 身份版本（L1） | 冻结块可判、脸部特写 approved |
| C05–C08 派生视角 / 造型 | 站 5 | L2 七件、状态版本 | 每件 approved；动测 5/5 |
| C09–C10 资产 QC / 封版 | 站 5.5 | 台账 + 清单 | `asset_manifest.py` 全过 |
| S01–S04 分镜 → 引用计划 | 站 6 | `ShotSpec` + `ReferencePlan` | 引用集合规（§2） |
| S05–S06 首帧 + 首帧 QC | 站 6 → 6.5 | 写实彩色首帧 | 身份 / 造型 / 构图硬门禁 |
| S07–S08 视频 + 时序 QC | 站 6.5 | 镜头视频 | 抽帧身份、闪烁、肢体 |
| S09 跨镜 QC | 站 6.6 / 6.7 | 连续性报告 | 按剧情时间比，不按剪辑相邻比 |
| S10 封版 | 站 6.7 | 成片 + 证据链 | 四件证据（任务号 / 参数 / 路径 / 判据） |

---

## §2 ReferencePlan（这一镜凭什么用这几张）

**每个镜头一份，不是一份全局清单。**

```json
{
  "shot_id": "SH3",
  "selector_policy_version": "ref_v1",
  "primary_asset_id": "S1VA",
  "assets": ["S1VA", "C1F", "C2F"],
  "order_reason": "本镜以空间机位图为构图锚，排第一；两角色按 prompt 首次出现排序",
  "prompt_refs": ["{{Image 1}}", "{{Image 2}}", "{{Image 3}}"],
  "resolved": [
    {"asset_id": "S1VA", "node_key": "n_c3", "image_index": 1, "effective": true},
    {"asset_id": "C1F", "node_key": "n_a1", "image_index": 2, "effective": true},
    {"asset_id": "C2F", "node_key": "n_b2", "image_index": 3, "effective": true}
  ],
  "reasons": ["face_visible", "identity_approved"],
  "excluded": [{"asset_id": "C1VR", "why": "同身份第二张脸"}],
  "capability_check": "PASSED"
}
```

**★ 引用能不能成立，只看三件**：

1. **节点已生效**：`resolved[].effective = true`（有产物 / url）；未生效的节点进下游必然失败。
2. **绑定存在**：`assets[]` 里的每个 id 都在 `resolved[]` 里有 `node_key`。
3. **插桩一一对应**：`prompt_refs[]` 与 `assets[]` 同长、同序——`{{Image N}}` 的第 N 张就是 `assets[N-1]`。

**★ 顺序对不对，看四条**：

1. **主参考＝本镜的构图锚**：有首帧（静帧）→ **首帧第一**；资产驱动 → **空间 master 第一**（正面 / 3-4 / 俯视，可多张）；特写插入 → **主体第一**。**脸部特写不是默认第一位**——它是"生成角色"的锚，不是"驱动这一镜"的锚。
2. **位置权重**：越需要精准的越靠前（`asset-consistency.md` §二）；两角色同框按 **prompt 里首次出现的先后**排。
3. **边序＝图序**：`left` 边序重算 `imageList` 与 `imageListOrder`；`params.imageList` 不可手填。**要改顺序只能拆边重建**——改 prompt 插桩顺序不会重排图序。
4. **错位＝引用错人**：`{{}}` 与 `reference_nodes` 顺序错位，是本库记录过的最常见坑。

**★ 全量口径（2026-10-31 逐节点读完两张成片画布：595 + 762 = 1357 个节点，0 缺失）**：`THE TURN` 176 个有参考的镜头——第一张＝**场景/空间 master 82%**（含世界地图、作战室正面 master）· 道具 13% · 人物 4% · 静帧 1%；参考张数中位 **5**、最多 **30**、**75% 的镜头 ≥4 张**。`抵达之前` 344 个镜头——第一张＝**场景 48% + 空间 4% + 静帧 19%** · 人物/角色 14%；中位 **4**、最多 **9**、**63% ≥4 张**。两片共同点：**第一张是构图锚（空间/首帧），不是脸**；人物按 prompt 首次出现排；道具与卡片在后；**张数由复杂度决定**。

**★ 未绑定 ≠ 通过**：只有 `assets` 没有 `resolved` 时脚本报 `REFS_UNBOUND`（warn）；上线前必须补绑定，否则是"计划对了、线上引用不成立"。

**选择规则（顺序不能反）**：

1. **身份版本锁死**：只取该镜绑定 `identity_version` 的资产；
2. **只取 approved**：draft / review / stale 一律不进；
3. **按朝向取件**：正面取①、侧面取左/右、背面取后视、俯拍取俯视、全景取前视（`asset-standard.md` §3.2）；
4. **同身份 ≤1 张脸**：第二张带脸的图必须写进 `excluded` 并给理由；
5. **模型能力兜底**：模型不支持多参考就退到"先合成首帧再 I2V"，**不得向模型传它没有的参数**；
6. **留痕**：策略版本、`primary_asset_id`、排序理由（`order_reason`）、被排除项都要落盘。

**★ 三类适配**：道具按"是否入画 + 是否物证"取（主图 / 近距版）；场景按"机位"取（L2 机位库）；**两者的 L3 状态（握持、位置、空镜）写进提示词，不另出图**。
**★ 首帧与音频（成片画布口径）**：首帧/静帧用 `first_frame` 声明，**必须排第一**（`抵达之前` 64 个镜头如此）；**音频不占 `imageListOrder`**——走 `audio→video` 边 + prompt 里的 `{{Node}}` 插桩（两片分别 299 / 210 条）。
**★ 与拆解桥的接口**：`10_breakdown.json` 的 `shots[].feed_plan` 是**选择意图**（subject＋role），不是本节的 `reference_plan`（具体 asset_id）。站 5.5 按上面六条把它解析成引用计划；未解析时脚本只报一条 `FEED_PLAN_UNRESOLVED`（warn），不逐镜报错。

---

## §3 四层 QC

| 层 | 查什么 | 硬门禁（不过不可封版） | 软指标 |
|---|---|---|---|
| **资产 QC** | 身份件 / 派生件 / 造型件 | 冻结块可判、脸部特写 approved 且有 `qc_report_id`、无第二张脸误入投喂集；**七件同人 → INDETERMINATE**（离线判据：六件 L2 的 `parent` 都指向同一张 L1 脸） | 美观、表情自然度 |
| **首帧 QC** | 写实彩色首帧 | 错误角色、换脸、错误造型、构图不成立、场景不符 | 光影质感 |
| **时序 QC** | 视频抽帧 | 明显闪烁、肢体畸变、服装跳变、角色消失 | 运动流畅度 |
| **跨镜 QC** | 按**剧情时间**比对 | 身份漂移、剧情状态错（伤 / 湿 / 道具）、造型错版 | 节奏与调性 |

**★ 三种判定，不是两种**：`PASS` / `FAIL` / **`INDETERMINATE`**。背影、远景、严重遮挡下看不清脸 → **判 INDETERMINATE 或改用外观+造型+位置证据**，**不许因为相似度低就武断判漂移，也不许当 PASS 放行**。

**★ 硬门禁与软分不能混**：硬门禁是"错误角色 / 错误造型 / 角色互换 / 严重肢体畸形 / 错误剧情状态 / 未授权资产"；软分只用于候选排序与人工优先级，**不能拿高分绕过硬门禁**。

---

## §4 运行期错误码 → 修哪一步

> **两套码不混用**：结构期（清单/层/状态/投喂）由 `asset_manifest.py` 判，码表与覆盖见 `--self-test`；本节是**生成之后**的失败分类。

| 错误码 | 症状 | 修复路线 | 作用范围 |
|---|---|---|---|
| `SCHEMA_INVALID` | 拆解 / 清单 JSON 不合法 | 修 spec，不重生成 | 当前 spec |
| `IDENTITY_DRIFT` | 脸偏离 L1 | 换参考策略 → 重做首帧 → 再生成 | 当前镜 |
| `WRONG_LOOK` | 服装 / 发型不符 L2 | 局部重绘或重做首帧 | 当前镜 |
| `BODY_ANATOMY_ERROR` | 手 / 身体严重异常 | 修首帧、重生成 | 当前镜 |
| `TEMPORAL_FLICKER` | 帧间闪烁、变形 | 改参数、重生成或短切片 | 当前视频 |
| `IDENTITY_SWAP` | 双人互换 | 修绑定与站位，重做参考计划 | 当前镜 |
| `CONTINUITY_ERROR` | 伤 / 道具 / 衣服不符 | 从剧情事件重算 state | 相关镜 |
| `REFERENCE_CONFLICT` | 不同 look / identity 混用 | 重排参考或减张数 | ReferencePlan |
| `UNSUPPORTED_REFERENCE_MODE` | 模型不支持该条件 | 换策略或换模型 | 当前阶段 |
| `RESOURCE_EXHAUSTED` | 显存 / 配额 | 降分辨率、调度重试 | 当前任务 |
| `LICENSE_BLOCKED` | 权重 / 素材未授权 | **禁止推理**，换合规模型 | 任务阻断 |
| `MASTER_IDENTITY_ERROR` | 源身份整体不合格 | 新身份版本 + 影响分析 | 身份与下游 |

**★ 修复不等于重新设计**：`IDENTITY_DRIFT` 只修当前镜，**不许顺手换 Master**；要换 Master，走 `MASTER_IDENTITY_ERROR` 并发布新版本。

---

## §5 重试、预算与 STALE

- **有限重试**：每阶段 `max_attempts`（默认 2）· `max_cost` · `timeout` · `idempotency_key`；超限转人工，**不许"再抽最后一次"**。
- **区分失败类型**：传输 / 基础设施错误可重试；**质量失败走错误码修复**，两者不共用一套重试。
- **同产物最多重建 3 次**；一镜超 8 次 → **改结构，不是改词**。
- **上游变更 → 下游 STALE**：L1 换版、L2 换造型、L4 事件回改，都要做影响分析；**旧成品保留可读，但不许直接进新镜头**。
- **幂等**：同一 key 重试不重复扣费、不重复建资产。

---

## §6 Manifest 与目录

```text
projects/PROJ_001/
  characters/CHAR_0001/
    identity/v001/{face_closeup}.png
    looks/LOOK_001/{front,back,left,right,top,body_headless}.png
    metadata/{character_spec,manifest,character_qc}.json
  scenes/SCENE_001/{plan,v_wide,v_reverse}.png
  props/PROP_001/{main,state_open,closeup}.png
  shots/SHOT_0001/{ref_plan.json,keyframes/start.png,video/accepted.mp4,qc/*.json}
```

**每件资产的最小字段**（`asset-standard.md` §9）：`asset_id · subject · role · layer · version · status · origin · sha256 · source · parent · qc_report_id · artifact_ready`；运行期再加 `origin_run_id`。
**机器可读契约**：`schemas/asset_system.schema.json`（拆解输入 + 资产注册 + ReferencePlan 三段；`additionalProperties=false`，层与角色不符直接拒）。**它由 `asset_manifest.py --self-test` 加载并校验全部 fixtures**——不是装饰。
**不许只存裸 URL**：必须有 `sha256` 与 `origin_run_id`；上传后校验哈希与可读性。

---

## §7 本库的落地工具（对账离线；建画布需批准）

| 工具 | 作用 | 命令 |
|---|---|---|
| `asset_manifest.py` | 结构对账：漏 / 多余 / 无出处 / 层状态 / 引用计划 / 顺序 | `python scripts/asset_manifest.py plan.json --self-test` |
| `libtv_canvas_build.py` | 清单 → 画布：节点 + **资产内派生边** + **每镜投喂边**；`--compose` 由 facts/brief 自动写描述 | `--compose --dry-run` · `--apply --yes --verify` |
| `wiring_plan.py` | 上下游分析：拓扑层（先建谁）、每条边的理由、入边顺序、环/割点/连通分量；**画布体检**（重名 / 参考无入边 / 顺序与边不一致 / 悬空端点） | `plan.json --report` · `--canvas <uuid> --explain <节点>` · `--canvas <uuid> --integrity` |

**建画布时两类边必须同时建**（少一类就断链）：

1. **资产内**：L2 五视角/无头 ← L1 脸（`modeType=image2image`）；机位视图 ← 平面图；
2. **投喂**：视频 ← `reference_plan.assets`，**顺序即 `imageListOrder`**。

**它不检查**：画面质量、身份相似度、模型能力——那些要真实生成（见 §8）；**它不点火**，只建节点与边，生成仍需单独批准。
**回读能验**：边序（`imageListOrder`）、父级、模式（`image2image`/`mixed2video`）、被引用资产有没有产物（空产物只 WARN，`--strict-effective` 可判失败）。**不能验**：画布坐标与分组——CLI 不回读位置，别把"看着摆好了"当证据。

---

## §8 与规划文件的差异（诚实边界）

| 规划文件有、本库没有 | 为什么 | 什么时候需要 |
|---|---|---|
| FastAPI / Temporal / PostgreSQL / 对象存储 | 本库是**方法库 + 离线脚本**，不是服务 | 要做成产品时另立仓库 |
| 真实身份相似度评分与阈值校准 | 需授权权重 + 标注集；**未校准的阈值是假保证** | 有 20–50 条标注集之后 |
| 自动修复执行器 | 修复动作要花钱、要审批 | 有预算与平台接口之后 |
| 多租户 / 许可登记 / 密钥管理 | 服务层关注点 | 对外交付时 |

**★ 一句话**：**本册把"该产什么、怎么引用、怎么判、错了修哪"定死；"谁来跑、跑在什么机器上"留给服务层。** 结构层可离线全验，**媒体层必须真实生成才算验过**。

---

## 来源与署名

- **模型来源**：`CHARACTER_PIPELINE_PLAN v1.0.0` §6（ShotBuildWorkflow）· §7（Reference Selector / Model Adapter）· §8（QC / 错误码 / 状态机）· §9（连续性）· §11（Manifest）。
- **本库改编**：把 S01–S10 映射到站 6–6.7；把"自动修复执行器"降为"错误码 → 回退站"；不引入服务层组件。
- **★ 分档**：属**本库方法论（工程口径）**；阈值、重试次数、预算均为**可配置起点，不是行业标准**。
