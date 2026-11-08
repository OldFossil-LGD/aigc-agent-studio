# WorkRally 命令与参数速查（**查表用** · 不复述「为什么」）

> **何时读**：写投喂命令、排错、或要核「这个参数到底取什么值」时。
> **为什么这样用 → `workrally-workflow.md`**（本册只给命令与字段，**不重复它的纪律**）。
> **投喂桥 → `scripts/workrally_bridge.py`**（它已把下面的命令按站拼好，先用它再查本册）。
> **数据时效纪律同 `platform-matrix.md` §0**：本册是**某时点快照**（2026-09-23 · 源＝Tencent/workrally v2.9.1）；
> **模型 id / 分辨率枚举 / 时长档一律现场取**，本册**只写取值方法，不写具体值**。

---

## §1 安装与认证

```bash
npm install -g workrally
workrally auth login                 # 交互式（推荐）；--token <KEY> 可命令行传入
workrally auth status                # 验证登录状态 —— **接通道第一步必跑**
```

| 环境变量 | 作用 |
|---|---|
| `WORKRALLY_API_KEY` | Bearer Token。**仅推荐 CI/CD**——Agent/子进程**可能读不到 shell 配置**（所以优先 `auth login` 落盘） |
| `WORKRALLY_ENDPOINT` | API 端点（默认平台 MCP 地址） |
| `WORKRALLY_CONFIG_DIR` | 配置目录（非持久化容器**必须**指向持久卷，否则登录态每次丢） |
| `WORKRALLY_NO_UPDATE_CHECK=1` | 关自动版本检查（CI/CD 推荐） |

> **通道自检**：接通道前先跑 `workrally auth status` 与一次最轻只读命令（如 `workrally project list`）。
> **回 not found / 未登录 ＝ 通道未挂载 → 立刻停手，不要反复重试**（空转烧轮次）。

---

## §2 按站分组命令速查

### 站 5（资产）· 三步上传 ＋ 挂资产库

```bash
workrally project list                                        # 拿项目 ID（用户没指定 → 找「默认项目」）
workrally upload ./character.png -o json                      # ① → CDN URL（走 COS SDK 直传）
workrally asset create --url <cdn_url> --project-id <PID> -o json   # ② 入媒资库（**必做**，返回 asset_id + asset_details）
workrally material add --json-list '[{"material_id":"<asset_id>","material_name":"角色名_状态",
  "material_type":2,"parent_id":"role_person","material_detail":<完整 asset_details>}]' --project-ids <PID>   # ③ 挂资产库
workrally material list role_person                           # 人物｜role_prop 道具｜role_scene 场景｜root 网盘
workrally material get <material_id> -o json                  # 详情 → 从中取 role_id
workrally role get <role_id> -o json                          # 角色详情（LoRA / 提示词 / 版本）
```

> **`material_type`**：`1` 文件夹 · `2` 图片 · `3` 视频 · `4` 音频（另有 `0` 资产 / `5` 角色状态）。
> **③ 缺 `material_id` 或 `material_detail` → 素材在资产库里根本不显示**（不是报错，是静默）。

### 站 6.5（投喂与生成）· 场次线

```bash
workrally series create --project-id <PID> --name "第一集" -o json          # → 剧集 id
workrally shotlist create --series-id <SID> --json-list '[{"image_prompt":"…","animation_prompt":"…"}]'
workrally shotlist models --category image,video,videoSingle,videoFrame,upscale,audio -o json   # ⭐ 必先跑
workrally shotlist set-model --series-id <SID> --image-model <ID> --image-aspect-ratio 16:9 \
  --video-mode SubjectToVideo --video-model <ID> --duration <D> --video-aspect-ratio 16:9 --no-enable-sound
workrally shotlist recognize --series-id <SID> --project-id <PID> --match-rule symbol_text
workrally shotlist get <story_id> -o json                                   # ★ 放行检查：参考字段空 → 不开工
workrally shotlist generate-image --project-id <PID> --story-ids st_1,st_2 [--count N]
workrally shotlist generate-video --project-id <PID> --story-ids st_1,st_2
workrally shotlist upscale-video --project-id <PID> --story-ids st_1 --model <ID> --scale 2
workrally shotlist get-result --story-id <st_1> --type image|video|audio [--watch]
```

### 站 6.5 · 画布线

```bash
workrally canvas list / create "名称"
workrally generate image --prompt "…" --model <ID> --project-id <画布ID> --poll   # 传画布 ID 自动建占位节点
workrally canvas build-draft <canvas_id> --file nodes.json                        # 增量合并（默认）
workrally canvas build-draft <canvas_id> -n '[...]' -d "old1,old2"                # 同时增删
workrally canvas build-draft <canvas_id> -n '[...]' --mode overwrite              # 全量覆盖（**多人场景慎用**）
```

### 声音后置（**视频定稿之后才跑**）

```bash
workrally shotlist generate-audio --project-id <PID> --story-ids st_1 --count N   # 场次配音/音效（音色写 `<音色名>`）
workrally generate audio-models -o json
workrally generate audio  --prompt "雨声和脚步" --model <ID> --poll
workrally generate music  --prompt "摇滚吉他" --model <ID> --lyrics-mode none --poll
```

### 交付

```bash
workrally download <asset_id> [-d ./output/]      # 自动处理私有读签名
workrally url build "页面名" [--params '{}']      # **前端链接一律用它，禁止自行拼接**
workrally generate task <task_id> [--poll]        # 任务状态与产物（output_assets / output_text）
workrally tools list / tools describe <tool>      # 白名单自检（**不要用 tools call——已移除**）
```

---

## §3 参数陷阱（**六条，每条都踩得起代价**）

| # | 陷阱 | 正确做法 |
|---|---|---|
| 1 | **生图 `--resolution` 与生视频不是一套** | 生图旧档位 `1/2` 仍是 **2K/4K**，不是视频的 480P/540P。**一律用该模型 `resolution_options[].value`**（数值随模型下发，以当次返回为准，勿硬编码） |
| 2 | **音效默认开** | 生视频不传＝**开音效**；要关就显式 `--no-enable-sound`。**`VideoEdit` 模式不要传音效参数** |
| 3 | **`project` ≠ `canvas`** | 两者 ID **不能互换**。`--project-id` 在 `generate image/video` 下是**画布 ID**；在 `asset create` / `shotlist generate-*` 下是**项目 ID**。混用是平台侧最高频的错 |
| 4 | **`shot` 与 `shotlist` 不互通** | 两套的配置字段不同（扁平字段 vs `gen_config`）；**一个剧集固定用一套**，不要混 |
| 5 | **`material_id` ≠ `role_id`** | `material_id` 形如 `abc_0`（带后缀），`role_id` 形如 `abc`。**先 `material get` 取 `role_id`**，再 `role get` |
| 6 | **音视频 URL 不要用 `original_url`** | 音视频是**私有读**，只有 `url` / `download_url` 可直接访问且会过期；过期用 `asset get` 重新取 |

**另外两条平台级硬规则**：

- **URL 白名单**：所有 URL 类参数**只接受平台官方媒资 URL**——合法来源只有三种：
  ① `workrally upload` 的返回值 ② `asset get/search` 的返回值 ③ 用户已提供的官方 URL。
  **本地文件或第三方 URL 必须先 `upload`**。提示「非法或已过期」时，用 `asset get` 重新取即可。
- **素材命名**：`--name` 传「画布名_素材特征」（画布场景）或 prompt 关键词（非画布场景）。

---

## §4 输出格式与退出码

```bash
-o json    # Agent 推荐（结构化，便于解析）—— 本库一律用它
-o table   # 人类阅读
-o text    # 管道 / 脚本
workrally config set output_format json      # 设全局默认
```

**`shotlist get-result` 关键字段**：`state`（`all_done` / `running` / `no_data`）· `doing_count` · `done_count` ·
`failed_count` · `results[]` · `doing_tasks[]` · `failed_tasks[]`。
**`doing_count === 0` 即该类型任务全部结束**——image / video / audio 是**三条独立进度，分别用 `--type` 查**。

**`generate task` 的任务状态**：`1` 排队 · `2` 运行 · `3` 暂停 · `4` 成功 · `5` 失败（看 `error_message`）· `6` 已取消。
**产物字段**：生图/生视频成功看 `output_assets`（`output_type="assets"`）；
**提示词优化成功看 `output_text`（`output_type="text"`）——不要去找 `output_assets`**。

---

## §5 动态值获取清单（**五条 `models` 命令，投喂前必跑**）

| 要什么值 | 命令 | 从返回里读哪个字段 |
|---|---|---|
| 生图模型 id · 分辨率枚举 · **参考图上限** · 推理质量选项 | `generate image-models` | `model_id` · `resolution_options[].value` · `kontext_config.max_input_images` · `infer_quality_options[]`（**空列表就不许传 `--quality`**） |
| 生视频模型 id · 时长档 · 分辨率 · 输入类型与上限 | `generate video-models` | 按**驱动模式分组**：`text_providers` / `first_last_frame_providers` / `subject_to_video_providers` / `video_edit_providers` / `smart_edit_providers`；取 `provider` · `duration_options[]` · `resolution_options[]` · `max_image_count` |
| 音频 / 音乐模型 | `generate audio-models` | `audio_models[]` / `music_models[]`；`is_minimax=true` 的**不要传 `--ref-audios`** |
| 提示词优化模型 | `generate content-models` | `model_id`（**严禁硬编码**） |
| **场次批量制作**的模型 | `shotlist models --category …` | 返回的 `id` 直接写进 `gen_config`（**与画布同源**） |

> **为什么必须现场取**：模型列表**动态下发**，不同环境的可用模型可能完全不同。
> **硬编码 id ＝ 换一个环境就失效**，而且失效方式是「报错」还是「用了另一个模型」**不可预期**。
> **混元 3D 是唯一例外**：模型固定，只需 `--asset-id`（且 `--project-id` 是短番项目 ID，不是画布 ID）。

---

## §6 两侧工具面对照（**对照，不是规则** —— 两侧规则各自归其权威册）

| 库内环节 | LibTV 侧（**对照，非规则**） | WorkRally 侧（本册） |
|---|---|---|
| 素材容器 | 画布节点（6 种）＋ 主体库 | 画布节点（**8 种**）＋ 媒资库 / 资产库树 |
| 一致性机制 | 锚点节点 ＋ `{{node_key}}` 插桩 ＋ 引用节点 | 媒资入库 ＋ `material` 挂载 ＋ `shotlist recognize/bind` |
| 顺序即身份 | `{{}}` 与引用节点列表 **一一对应且顺序一致** | prompt「第一张图片」与 `--input-images` **顺序一致** |
| 免费预检 | `validate` / `run:false` 类预检 | **无** → 用「结构层全免费 ＋ 先 1 条」替代 |
| 幂等 / 并发 | 幂等键 · 乐观锁 · run 锁 | **未暴露幂等键** → 靠提交前记账 |
| 结构化编排 | Script V2 式脚本对象 | 项目→剧集→场次三层 ＋ `set-model` 写 `gen_config` |
| 任务查询 | 平台任务状态接口 | `generate task <task_id>` / `shotlist get-result --type` |
| 导出 | 平台侧导出契约（**「能编不等于能出」**） | **无导出契约** → 成片拼接回本地（`cross-shot-interface.md`） |
| 计费口径 | 有积分专册 | **无明文** → 以平台账单为准 |

> **⚠️ 两侧不要互推**：LibTV 的「预检通过 ≠ 渲染正确」**不能**直接套到 WorkRally 上（WorkRally 根本没有预检）。
> **接口/字段不知道时**：先「探 schema」（用空参数调用，**在校验阶段就被拒、不扣费**），或**先问平台内 Agent（不计费）**——
> **写操作绝不在真画布上盲试**。

---

## §7 画布八节点（与另一侧六节点**不是同一套**，别照抄）

| type | 必填 | 可放进画板 |
|---|---|---|
| `image` / `video` | `data.asset.id`（已有素材）**或** `data.task`（生成中占位） | ✅ |
| `audio` | **必须** `data.asset.id`（**音频没有生成器**） | ✅ |
| `imageGenerator` / `videoGenerator` | 无必填（**通常不用手建**——传画布 ID 生成时自动创建） | ❌ |
| `artboard` | 无（缺尺寸自动补 600×800） | ❌（**画板不可嵌套**） |
| `text` | `data.text.content`（**最大 2000 字符**） | ❌ |
| `freehand` | `data.freehand.points` + `initialSize` | ❌ |

**三条会被服务端拒绝的写法**：① 画板里放 `text` / `freehand` / 生成器节点 ·
② `image` / `video` 既无 `asset.id` 也无 `task` · ③ 给画板子节点设 `extent`（**别设**——会锁死拖不出来）。
**一条会自动生效的便利**：传画布 ID 生成后**系统自动建 running 占位节点**，**不需要再手动 `build-draft`**。

---

**来源与署名**：同 `workrally-workflow.md`（2026-09-23 通读 `Tencent/workrally` v2.9.1 的 `SKILL.md` 与 `references/` 五册后按本库口径重编）。
**冲突处置**：平台 README 与 `SKILL.md` 不一致处**以 `SKILL.md` 为准**，并按本册 §5 现场核。
