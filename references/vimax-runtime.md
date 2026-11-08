# ViMax 执行后端（HKUDS · agent runtime 对接册）

> **何时读**：用户要"交给 agent 跑到成片"、要复用已定稿计划直接出片、或要核对
> 后端到底产了哪些文件。**先读本册再谈命令**；计划怎么来仍看 `production-compiler.md`。

## 1 · 定位

ViMax 是"输入创意/剧本/小说 → 剧本、角色、分镜、机位树、关键帧、片段、成片"的
agent runtime。在本库里它只占一个位置：**站 6.5 的第三条执行通道**，与 LibTV 画布、
WorkRally 并列，不替代任何一条。

- 计划权威：本库 01–04。
- 执行权威：ViMax 会话目录里**实际存在**的产物。
- 判据：计划看本库文件，效果看产物回读，两者不许互相顶替。

## 2 · 工作流点名闸门（硬）

ViMax 自己的协议要求用户**明确点名** `idea2video` / `script2video` / `novel2video`
才许规划；本库的站 6.5 也要求点火前有显式批准。两条叠起来的实现就是：

- `--workflow` 必填，无默认值。缺 → `WORKFLOW_NOT_CONFIRMED`，退出码 2。
- `script2video` 必须有**实存且非空**的剧本文件（`--script`）。拿一句创意去顶替 → 拒绝。
- `novel2video` 必须有小说原文（`--novel`）。
- `idea2video` 允许从 01 的 `goal` 取创意句，但会打 `IDEA_SOURCE_IMPLICIT`：
  源不是用户直给的，交付时要说明这一点。

**为什么这么死板**：三种工作流的产物 DAG 不同，混用的后果是"分镜按小说切、时长按剧本排"，
取件时看着都齐、剪起来全错。这不是格式问题，是重做成本问题。

## 3 · 会话产物权威

```text
.working_dir/<session_id>/<workflow>/     ← 产物账本（唯一）
.vimax/sessions.json                      ← 只是索引，不是产物
.vimax/memory.md                          ← 只存用户偏好
```

三条同名规矩：

1. 所有工作流产物必须落在**当前会话**目录下；根级 `idea2video/`、`script2video/`、
   `novel2video/` 一律不读不写（读错目录＝读到上一部片的东西）。
2. 本库只往会话目录里放**自己提供的源**（`script.txt` / `novel/novel.txt` / `idea.txt`），
   绝不预造 `characters.json`、`storyboard.json`、`shots/<idx>/video.mp4` 这类后端该产的文件。
3. 拍片顺序变了要新会话，不要在一个会话里换工作流糊过去。

源文件按读取时捕获的 UTF-8 原始字节暂存，保留原换行形式、尾部空行及是否有末尾换行。
作业单 source.sha256 对应实际暂存字节。Python compile_job 直接调用传入源文本时，
以其 UTF-8 编码为源字节。声明哈希不符报 SOURCE_HASH_MISMATCH，并在写入前拒绝。

## 4 · 十个阶段 ← 本库哪份产物

作业单里的 `stage_bindings` 就是这张表的机读版，`state` 只有四值：
`provided`（计划里有据）/ `derived`（可从计划派生）/ `missing`（计划里没有，后端会自行发挥）/
`backend_generated`（本来就该后端产）。

| ViMax 阶段 | 本库来源 | 期望 state |
|---|---|---|
| input_idea / input_script / input_novel | 用户确认的源原文 | provided |
| project_brief | 01 `goal` | provided（idea2video 才有） |
| characters | 02 `kind=character` | provided |
| storyboard | 03 `shots[]` | provided |
| shot_decomposition | 03 `shots[].shot_timing` | derived |
| camera_tree | 03 `shots[].camera` | derived |
| frame_prompts | 04 `role=candidate_image` | provided |
| keyframes | 04 `candidate_image` / `refined_image` | backend_generated |
| video_clips | 04 `role=video_candidate` | provided |
| final_video | `assembly_layer.cut_range` | backend_generated |

任何 `missing` 都会打 `STAGE_MISSING` 并记进作业单：**后端会自己补，回读时必须逐项核**。
`missing` 之后还能跑，但它产的东西不是本库计划里的，不能反过来当成计划已定稿的证据。

## 5 · 幂等、回读与"跳过≠通过"

ViMax 遇到已存在的产物会跳过并打印提示。本库口径：

- 跳过只说明文件在，不说明内容对；`--kind final` 取件后仍要过 `film-qc-gate`（黑帧/静音/时长）。
- 回读只读现存文件；文件不在就报缺，不拿上一轮的印象补。
- 已发起过的任务先只读回查，不重复提交；要重跑就换会话 id，别在原会话里覆盖。
- 同一个输出目录已有别的作业单（会话 id 或源 sha 不同）→ `SESSION_EXISTS_CONFLICT`，退出码 2。

## 6 · 批准与点火

`render.run` 恒为 false，`studio.generation_authorized` 恒为 false——这两个字段是这个
作业单存在的意义。`--approve-render NOTE` 只是**记录**一次批准（`scope: recorded_not_executed`），
脚本本身永不发请求、永不建任务。

真实执行的边界：

1. 人看过作业单（工作流、源 sha、stage 绑定、预算）→ 明确说"跑"；
2. 由人或 ViMax agent 在其环境里执行；密钥走环境变量或本机 `configs/agent.local.yaml`，
   **不进库、不进作业单**（模板里 `api_key` 是空串）；
3. 产出按第 5 节回读核验，再进站 6.6。

## 7 · 失败 → 责任层

| 现象 | 责任层 | 回哪 |
|---|---|---|
| 角色不像同一个人 | 资产（02 / 角色锚点） | 站 5 重锚，不在提示词里补救 |
| 分镜切点乱、镜数不对 | 分镜（03） | 站 6 重排，别让后端自己补镜 |
| 关键帧构图错 | 提示词包（04 candidate_image） | 站 6 改块，改完重投影 |
| 动作/物理不对 | 视频提示词（04 video_candidate） | 站 7 判层后再改 |
| 合成音画不同步 | 装配（06.6） | 站 6.6 时间线，不重抽镜头 |

判层方法、回执绑定见 `review-passes.md` 与 `offline-continuity-entry.md`；
错误码词典与站 7 共用 `qa-failure-codes.md`。

## 8 · 与 LibTV 通道的差别（不许照搬纪律）

| 维度 | LibTV 画布 | ViMax 后端 |
|---|---|---|
| 预检 | 有免费 dry-run（`run:false` 校验） | **无**，只能靠作业单前置检查 |
| 幂等键 | 有 `idempotencyKey` | **无**，靠会话 id + 目录隔离 |
| 产物账本 | 画布节点与回读 | `.working_dir` 文件树 |
| 模型清单 | 以平台下发为准 | 以 ViMax 配置为准，两者不可混引 |

所以：LibTV 的"先预检再开跑"在 ViMax 这边要换成"先出作业单再人工批"，
别把两套假设混着用。

## 9 · 命令与错误码

```text
python scripts/vimax_backend_compile.py --artifacts out/ --out out/ \
    --workflow script2video --script script.txt
python scripts/vimax_backend_compile.py --artifacts out/ --out out/ --workflow idea2video
python scripts/vimax_backend_compile.py --self-test
```

| 码 | 含义 | 退出码 |
|---|---|---|
| `WORKFLOW_NOT_CONFIRMED` | 没点名工作流 | 2 |
| `SCRIPT_SOURCE_REQUIRED` / `NOVEL_SOURCE_REQUIRED` | 源缺失或不存在 | 2 |
| `IDEA_SOURCE_REQUIRED` | 创意句与 01 goal 都空 | 2 |
| `SOURCE_EMPTY` | 源文件是空白 | 2 |
| `SOURCE_HASH_MISMATCH` | 源字节与声明哈希不符 | 1 |
| `SESSION_EXISTS_CONFLICT` | 目录里已有另一份作业单 | 2 |
| `AUTHORITY_LEAK` | 计划本身带点火/生成许可 | 1 |
| `PLAN_EMPTY` | 03 里没有镜头 | 3 |
| `STAGE_MISSING` / `IDEA_SOURCE_IMPLICIT` | 警告项，须在回读时核 | 4 |

## 10 · 不做什么

- 不代替 08 号 LibTV 命令计划，也不代替 `apply_libtv_plan.py`。
- 不在作业单里写密钥、不代跑模型、不把"跑过"当"交付"。
- 不因为后端能自动补缺就把 `STAGE_MISSING` 当无事：补出来的东西没有本库计划背书。
- 跨系统交换格式与角色换算看 `filmdsl-interchange.md`；站 6.5 的站位见 `run-sheet.md`。
