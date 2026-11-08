# 离线生成门禁台账（script -> plan -> prompt -> gate）

适用范围：用户给剧本或一句话目标，要求先做离线生成、检查节点/链接/提示词/工作流，但不点火、不生成媒体。

本文件只属于 `aigc-agent-studio` 技能域，不进入全局记忆。

## 1. 使用时机

```text
剧本已定
-> Production Record / Graph Plan / Prompt Package 已落盘
-> 运行 scripts/offline_package_lint.py <包目录>
-> 通过后才讨论是否申请点火
```

它不是执行器，不联网、不建节点、不点火、不上传、不导出。

## 2. 已犯错误与机器门禁

| # | 犯过的错误 | 门禁 | 正确处理 |
|---:|---|---|---|
| 1 | 人物块缺身份锚点，模型只靠服装猜身份 | `audit_prompt.py blocks` | 在【人物与环境】写“身份锚点：X 与 Y 是同一人物，五官/发型/服装/状态不变” |
| 2 | 人物块混入“起身、走过来、提箱”等动作过程 | `audit_prompt.py blocks` | 动作链只放【时间线】，人物块只写姿态与状态 |
| 3 | 镜头规格只写 mm，没写视场角和空间结果 | `audit_prompt.py blocks` | 写 `24°（85mm）`，并说明长焦压缩/广角拉伸等空间结果 |
| 4 | 面部只写一处动作，形成静态表情 | `audit_prompt.py blocks` | 至少两处“部位 + 动作”，写清起止、节拍和不同步关系 |
| 5 | 人物块生理活性不足 | `audit_prompt.py blocks` | 呼吸/眨眼/瞳孔/泪膜等至少两种，且不是恒定节律 |
| 6 | 写了“额纹/眉间/鼻唇沟”等皱纹名 | `audit_prompt.py blocks` | 不写纹名；年龄由眼下凹陷、颈部、发际线、肩背结构承载 |
| 7 | 时间线的“起始”仍写成待机态 | `audit_prompt.py blocks` | 起始必须是“已在途中”：视线已在追、列车已进入启动中段、身体保持上一拍 |
| 8 | 声音表类别写“人声”，解析器拒绝 | `sound_lint.py` | 使用允许类别：对白/环境/硬效/拟音/设计声/音乐 |
| 9 | 合成时间线用自定义行名，没有识别为镜头 | `audit_prompt.py timeline` | 镜头行统一 `SH01 / SH02`，时间列用秒，如 `0–30` |
| 10 | JSON/JSONL 有重复键，`json.loads` 静默覆盖 | `offline_package_lint.py` | 解析时检查重复键；重复键是 FAIL，不靠 schema 事后发现 |
| 11 | 把“未点火”的媒体门禁 `rc=3` 写成通过 | 所有门禁 | `rc=3` = 没验到；媒体和成本保持未验/不适用 |

## 3. 固定命令

```text
python3 scripts/render_offline_prompts.py <离线生成包目录>
python3 scripts/offline_package_lint.py <离线生成包目录> --schema-dir outputs/统一基准
```

`render_offline_prompts.py` 从 `03_Prompt_Packages.jsonl` 生成 canonical `04-07` 提示词文档和 `prompt_render_manifest.json`；禁止手改生成文档。`offline_package_lint.py` 内部至少检查：

```text
01_Production_Records.jsonl
02_Graph_Plan.json
03_Prompt_Packages.jsonl
04_Source_Node_Map.json
offline_package_manifest.json
06*_audit.md
18*.md
19*.md
04-07 生成文档、审计载体与 prompt_render_manifest.json
```

语义对账：

```text
Record.prompt_package_id -> Prompt Package
Record.asset_ids -> Graph Plan 节点或 Source Node Map 映射
Package.reference_nodes -> Graph Plan reference 边与 order
Record 时长合计 -> A/V/Audio/Composite 包时长
locked_text -> 包内 blocks 原文
观测节点 ID -> 逻辑计划节点 ID
```

`offline_package_manifest.json` 用来声明组件是 `required` 还是 `not_applicable`：

```text
sound_table=not_applicable       -> 静音项目合法
composite_timeline=not_applicable -> 无合成项目合法
```

“没有文件且没有声明”仍按没验到处理，不能靠缺文件冒充不适用。

## 4. 分账

```text
结构/引用/提示词/时间线失败       -> rc=1，必须修
JSON 重复键                        -> rc=1，必须修
媒体未点火                         -> rc=3，不是通过
缺平台单价                         -> rc=5，不是通过
审美、表演、身份和节奏             -> 人工或多模态验收
```

## 5. 不沉淀什么

不得把单次作品的具体节点数、时长分配、人物距离、模型或像素值写成通用规则。
这些只能留在项目画像或 claim ledger 的 scope 内。
