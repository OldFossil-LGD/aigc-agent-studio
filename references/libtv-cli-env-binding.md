# LibTV CLI 环境与绑定专册（凭据 / 账户 / 项目 / 分组 / 上传 / 执行层）

> **来源**：官方 `libtv-cli` 文档（`commands/*`、`model-schema/schema.md`、`node-types/*`）与**实时 schema 对账**（**一手 · 2026-10-15 读/测**）。
> **为什么单列**：原 `libtv-op-checklist.md` 到达 300 行上限——本册承接其中**整块"CLI 执行层"**内容（`-s`/`-u`、管道中段纪律、`group`/`upload`/`project`/`model`/`workspace`/`login`/`account`）；**该册保留原有的"流程坑与点火前自查清单"**，两册是同一主题的两层。
> **读完回哪**：`libtv-op-checklist.md`（点火前自查）· `libtv-cli-pipelines.md`（管道组织手法）。
> **机器可读索引**：`03_CLI语义表/command_tree_20261015.json`（13 个根命令与嵌套子命令）· `03_CLI语义表/command_flags_20261015.json`（40 页 / 141 个 flag）——用于脚本参数预检，不替代实时 `--help`。

---
## ★★ CLI 执行层权威约定（**官方 `libtv-cli` 文档 · 一手 · 2026-10-15**）

### 一、`-s/--set` 与 `-u/--update` **不能互换**

| 维度 | `-s, --set` | `-u, --update` |
|---|---|---|
| 写入位置 | **`data.params.*`** | **`data.*`（不含 `params`）** |
| 语义 | **生成器参数**——这次"怎么生成"（`prompt` / `model` / `count` / `settings` / `advancedSettings` / `modeType` …） | **节点自身属性**——节点"承载什么内容"（`content` / `rows` / `title` …），**不影响模型参数** |
| schema 校验 | **严格**：按当前 `modelKey` 的 `properties` / `config` / `rules` 校验；**`originalField` 自动归位**到 `params.settings` / `advancedSettings`；**`count` 超范围直接报错** | **不走生成器 schema**；仅**白名单式键名拒写**，按 JSON 浅写到 `data` 顶层 |
| 改展示名 | **永远走 `--name`**；**`-u label=…` 会被拒** | 同左 |

**三条易错**：
1. **`-s "model=…"` 只接受模型名（`modelName`）**，含空格要加引号；
2. **设置项两种写法等价**：`-s settings.quality=2K` 或**拍平** `-s quality=2K`（靠 `originalField` 归位）；
3. **`libtv model search --type` 只接受六个带生成模型的类型**——`text` / `image` / `video` / `audio` / `script` / `storyboard`；**`video-clip` 不在其中**；**`custom` / `group` 不要走 `libtv node`**（分组用 `libtv group`）；**`video-clip` 的 `-u` 是浅合并、无生成器 schema 校验**。

### 二、管道纪律（**脚本化执行前必读**）

```bash
set -euo pipefail
```

- **`-o pipefail` 必须有**：没有它，管道某段失败会被右端成功掩盖——现象是"`set -e` 下脚本静默跑完，画布只有前几个节点"。
- **逐层串联一律 `&&`，不要 `;`**：`;` 在左侧失败后照跑，会把半残数据喂给下游。
- **`&` 与管道互斥**：多进程同时写同一条管道会**把一行 JSON 的字节穿插进去**，下游按行解析直接炸（报 `invalid json on line N`）。要并发就让每个上游**各写独立文件**，再串行合并。
- **stdout ＝ 业务结果 JSON/NDJSON；stderr ＝ 进度 / 鉴权 / 轮询**——**不要 `2>/dev/null`**，否则失败时拿不到任何线索。
- **失败现场清理**：给本批节点加**统一前缀/时间戳**，失败后用 `node list` + `jq` 过滤后批删。
- **症状对照**：偶发"成功但下游说找不到上游" ＝ 上游把 NDJSON 丢进了 `>/dev/null`；`401` / `AUTH_*` / `PROJECT_NOT_BOUND` ＝ 凭据或项目绑定问题（见官方 `commands/login.md`、`commands/project.md`）。 **★ 管道的组织手法（旁路节点 / stdout 抑制 / 已有节点回放 / 嵌套决策表）另见 `libtv-cli-pipelines.md`。**

### 三、官方文档 vs **实时 schema** 对账（**2026-10-15 实测 · 揪出 2 处不一致**）

以 `star-video2`（UI 上的 `2.0`）为例，把官方 `node-types/video.md` 的参数表与我方 `libtv model star-video2` 的实时 schema 逐项对：

| 字段 | 官方文档 | 实时 schema（2026-10-15） | 判定 |
|---|---|---|---|
| `ratio` | `adaptive`/16:9/4:3/1:1/3:4/9:16/21:9，默认 16:9 | **完全一致** | ✅ |
| `duration` | 整数秒 **4–15**，默认 5 | `min:4` `max:15` `step:1` `default:5` | ✅ |
| `enableSound` | `on`/`off`，默认 `on` | **完全一致** | ✅ |
| **`resolution`** | **只有 `480p` / `720p`** | **`480p` / `720p` / `1080p` / `4k`**（默认 `720p`） | **⚠ 文档过时** |
| **`search_enabled`** | 文档写 **`search_enabled`**（advancedSettings） | properties 里**没有** `search_enabled`；`config.advancedSettings = ["searchEnabled","autoCompliance"]`（**驼峰**） | **⚠ 键名不一致** |
| `count` | "需符合 schema" | schema 里是 **`count: {}` 空对象** | **不可判定**——count 枚举**不能**从 schema 推出 |

**★ 纪律**：**官方文档是"意图"，实时 schema 是"当时事实"**——两者冲突时**以实时 schema 为准**，并把冲突本身记下来（本轮钉住的是 `resolution` 与 `searchEnabled` 两处）。
**★ 附带确认**：`config.advancedSettings` 里确实列着 **`autoCompliance`**，与官方 CLI 文档记载的 Seedance 真人合规校验互相印证。

---

## ★★ `libtv group`：目录绑定与整组执行（**官方 `commands/group.md` · 一手 · 2026-10-15**）

**① 目录绑定（本库此前零记录）**：`libtv group use <组>` 把**当前工作目录**绑定到画布上某个普通分组，**持久化到 `.libtv/project.json` 的 `groupNodeKey`**。此后同目录跑 `libtv node …`，**只要没写 `-g`**，列表 / 按名解析 / 更新 / 删改 / 连线**都只在 `childNodeIds` 范围内**进行，**新建节点也默认挂到该组**；临时换范围就在 `libtv node` 上加 `-g <其他组>` 覆盖。`unuse` 回 `{groupUnbound:true}`——**清 `groupNodeKey`、保留 `projectUuid`**。

**② 两条同名 `-g` 语义不同（最易错）**：`libtv group use -g` 是"**在指定父组的 `childNodeIds` 内解析名字**"（消歧义）；`libtv node -g` 是"**覆盖 node 的分组范围**"。**别混用。**

**③ 幂等 vs 新建**：`libtv group create <组>` **只新建**——同名**普通**分组已存在会报错并提示改用默认子命令；被**非普通分组**节点占用同样报错。**默认子命令 `libtv group "<显示名>"` 才是幂等的「已有就查询 / 绑定，没有就建并绑定」。**

**④ 绑定来源与"搬组"语义**：`--node <子节点>`（**id 优先，否则按展示名，重名取第一个，可重复**）与**管道 stdin**（每行一条 JSON，读 **`nodeKey` 或 `newNodeKey`**）；**两来源合并时 stdin 在前，再整体去重**。**★ 子节点若已在别的普通分组里，会先从原分组移除再挂到目标组——这是"移动"不是"复制"。**

**⑤ 整组执行**：`-r/--run` 对目标普通分组做一次**整组按顺序执行**（与网页「整组执行」一致）；**进度在 stderr，约每 3 分钟一条、前缀 `[run-group]`**；成功结果在 stdout，管道下为**单行 NDJSON**。

---

## ★★ `libtv upload`：本地文件 → 资源节点（**官方 `commands/upload.md` · 一手 · 2026-10-15**）

- 形态：`libtv upload <节点显示名> -f/--file <路径>`（**`--resource` 同义**）→ 生成 **`image` / `video` / `audio` 资源节点**，之后用 `--left/--right` 或管道接到下游；
- `-p` ＝ **项目 UUID**（**勿与 `libtv project list -p` 的"页码"混淆**——同名不同义）；
- `-g` ＝ 父级普通分组；**未传时若已用 `group use` 绑定默认组，会自动套用**；
- `-t` ＝ `image` / `video` / `audio`；**不写则按文件后缀猜**；
- **★ `--x/--y` 语义随分组变化**：**无分组＝画布绝对坐标；有分组＝组内相对坐标**；
- 输出：stdout 成功 JSON；**接管道时是一行 NDJSON，含 `nodeKey`**（可直接喂给 `libtv node` / `libtv group` 的 stdin）；stderr 上传进度前缀 **`[upload]`**。

---

## ★★ `libtv download`：节点资源落盘（**CLI help 一手 · 2026-10-15**）

- `libtv download -n <节点id或显示名>`：图片 / 视频 / 音频单节点直接存文件；普通分组或多文件场景输出 ZIP，命名对齐画布批量下载；
- `-p` 传画布 UUID，`-g` 限定普通分组；批量下载分组时，`-n` 传分组节点 id；
- `-o/--out <dir>` 指定输出目录（默认当前工作目录）；
- `--without-ai-watermark` 请求不加 AI 水印；**只有会员且账号有效时，图片 / 视频才可能走原链**；
- `--vip` 等价 `LIBTV_DOWNLOAD_IS_VIP=1`，只声明会员状态，不是登录或付费动作；
- **本轮仅读取 `--help`，未执行下载**；落盘后仍按 `delivery-engineering.md` 核 MIME、命名和哈希。

---

## ★★ `libtv project`：术语 + 目录绑定 + 项目范围（**官方 `commands/project.md` · 一手 · 2026-10-15**）

**① ★ 术语澄清（本库此前未统一）**：**CLI 里的"画布（project）"是真正的画布文件；装画布的容器叫"项目（工作区，workspace）"**。`projectUuid` ＝ **画布 UUID**。**别把 UI 上的"项目"与 CLI 的 `project` 当同一个词。**

**② `.libtv/project.json` 的四个字段（可并存）**：`projectUuid`（画布）· **`workspaceId`（所属项目）** · `teamId`（所属团队）· `groupNodeKey`（默认分组）。
- `libtv project use <画布UUID>` 会把该画布**实际所属的 `workspaceId` 与 `teamId` 一并同步写入**（画布不在任何项目下时不写 `workspaceId`）；
- `libtv workspace use` 则**写项目 + 团队但不设默认画布**。
**→ 未绑定且未传 `-p` 时，`node` / `upload` / `group` 会报错并提示先跑 `libtv project use`。**

**③ 项目（工作区）自动生效（`-w`）**：当该文件里有 `workspaceId`，**`project create` / `project list` 会自动作用在该项目下**（新画布默认建进去、列表默认只列该项目下的画布）；`-w <项目ID>` 显式覆盖，**`-w 0` 强制回到根目录**；自动生效时 **stderr 打一行 `[项目范围] …`，不污染 stdout 的 JSON**。

**④ 同名不同义第三次出现**：**`libtv project list -p` 是"页码"（默认 1）**，而 **`libtv node -p` / `libtv upload -p` 是"画布 UUID"**。列表其余选项：`-s` 每页（默认 20）· `-o` 排序（`updated_at_desc` / `edit_time_desc` / `edit_time_asc`）· `--name` 子串过滤 · `-t` 团队（>0 该团队，`0` 强制个人）· `-w` 工作区（>0 该项目，`0` 仅根）。`project update` 的 `--cover-url` **传空串可清空**，`--folder-id 0` ＝ 根目录（也可用于把画布移入项目）。

**⑤ 一条对外可直接用的惯例**：涉及某张画布时，**主动把网页链接给用户**：`https://www.liblib.tv/canvas?projectId=<画布UUID>`。

---

## ★★ `libtv model`：检索与 schema 的**官方匹配规则**（**官方 `commands/model.md` · 一手 · 2026-10-15**）

**① `search` 的硬前置**：**`--type` 与关键词不能同时省略**（否则报错）；`-t` 枚举 `text` / `image` / `video` / `audio` / `script` / `storyboard`，**`script` 与 `storyboard` 会同时扫 `scriptText` + `scriptImage` 两类模态**，**不支持 `custom`**。

**② 匹配优先级（返回值里的 `matchKind` 可直接判）**：

| 输入 | 行为 | `matchKind` |
|---|---|---|
| `modelKey` 与关键词**全等** | 只返回这些命中 | `modelKey` |
| 否则 `modelName` **不区分大小写子串包含** | 退而求其次的子串匹配 | `modelName` |
| 仅 `--type`、无关键词 | **该类型下全部条目** | `all` / `none` |
| 无 `--type` 且无关键词 | **报错** | — |

**③ 默认子命令才是最强口径**：`libtv model <name...>` 对 **supportModels + `/api/tool_spec/list`** 的记录做 **trim 后全等**解析；**唯一命中**才输出完整 schema（含 `nameOrId` / `modelName` / `modelKey` / `toolKey` / `modality` / `schema`）；**若在 supportModels 阶段全等命中多个不同 `modelKey` → 返回 409 类错误，必须改用唯一 `modelKey`**。
**→ 与本库既有纪律一致**：生成前先 `search` 找候选、再用默认子命令拉 schema——**`search` 的子串命中不等于可用**。数据来源是在线 supportModels（带本地缓存）。

---

## ★★ `libtv workspace`：绑定链的收尾（**官方 `commands/workspace.md` · 一手 · 2026-10-15**）

**① 术语再钉一次**：**项目（workspace）＝ 工作区，是"装画布的容器"；画布（project）才是画布文件**。一个项目下可放多张画布。

**② 三种绑定动作的**差分**（极易互相顶掉）**：

| 命令 | 写什么 | 顶掉什么 |
|---|---|---|
| `workspace use <项目ID>` | `workspaceId` + `teamId` | **顶掉原画布绑定**——**清除 `projectUuid` 与 `groupNodeKey`**；输出里会带 **`releasedProjectUuid`**（被解除的原画布） |
| `project use <画布UUID>` | `projectUuid`，并把 `workspaceId`/`teamId` **同步成该画布实际所属** | —— |
| `workspace unuse` | 清除 `workspaceId` + `teamId` | **保留**画布绑定；若文件里已无其它绑定**则删除整个文件** |

**→ 纪律：`workspace use` 会静默把你的默认画布和默认分组一起释放。**切换工作区后**必须重新 `project use`**。

**③ ★ 两个命令的 `-o` 排序枚举**不同**（真坑）**：

| 命令 | 允许的 `-o` 值 |
|---|---|
| `project list -o` | `updated_at_desc` / **`edit_time_desc`** / **`edit_time_asc`** |
| `workspace list -o` | `updated_at_desc` / **`updated_at_asc`** / **`created_at_desc`** / **`created_at_asc`** |

**只有 `updated_at_desc` 是两边共有的**——把一边的枚举抄到另一边会失败。

**④ `-p` 同名不同义第四次出现**：**`workspace list -p` 也是"页码"**（默认 1，**不是项目 ID**）。

**⑤ 输出与可用字段**：
- `workspace create` → stdout 含 **`workspaceId`（即新项目的文件夹 id）**，可直接喂给 `workspace use`；
- `workspace list` → 项目以 **`folders` 数组**返回，每项含 **`id`（项目 ID）· `name` · `fileCnt`（含画布数）**；
- `workspace use <workspaceId>` **只接受项目 ID（正整数），不支持按名称匹配**；会先调接口校验可访问再写本地；
- `workspace update` 至少传 `--name` / `--description` / `--cover-url` 之一；`--cover-url ""` 可清空封面；`--team-id 0` 强制个人空间。

**⑥ ★ 项目链接惯例（与本库运行时捕获互证）**：官方给的项目型链接是 **`https://www.liblib.tv/canvas?spaceId=<项目ID>&projectId=<画布UUID>`**。
**→ 本库第二轮在登录态画布上抓到的 URL 正是 `canvas?spaceId=11171432&projectId=11127ba…`** ⟹ **`spaceId` 就是 workspace id**，两条独立证据对上。

---

## ★★ 凭据、会话与"活跃账户作用域"（**官方 `commands/login.md` + `commands/account.md` · 一手 · 2026-10-15**）

**① ★ `LIBTV_CONFIG_DIR` 是本机状态的唯一开关（本库此前零记录）**：凭据目录默认 **`~/.libtv`**，内含 **`credentials.json`**。
- 它**只管本机状态写入位置（凭据 + 项目/分组绑定），不改变网络请求目标**；
- **默认目录的身份与浏览器 Cookie `usertoken` 同源**；
- **多账号 / 测试隔离的正确做法就是把 `LIBTV_CONFIG_DIR` 指向独立目录**（例如 `LIBTV_CONFIG_DIR="$HOME/.libtv-dev" libtv login web` 只影响这一条命令；`export` 则整个 shell 生效，`unset` 还原）。
**→ 纪律：任何"换账号 / 试跑"都先切 `LIBTV_CONFIG_DIR`，不要去改主目录的凭据。**

**② `login web` 的机制**：本机起**临时 HTTP 服务**，**stderr** 打印带 **`callback_url`** 的登录链接；浏览器完成登录后跳回 **`http://127.0.0.1:<端口>/callback?token=…`**，CLI 校验后写凭据。`--open` 尝试用系统默认浏览器打开（未设则**只打印链接**——可复制到另一台机器打开）。
- 环境变量：**`LIBTV_LOGIN_WEB_URL` 整段覆盖**登录前缀（设了它就**忽略** PATH 那个）；**`LIBTV_LOGIN_WEB_PATH` 只改路径**，拼在默认域名后；两者都未设时用内建的 **`config.tv.domain + /zh`**。

**③ `login phone` 是**两步**，顺序写错会失败**：
1. **发短信：`libtv login phone -p <11位手机号>`——这一步绝对不要传 `-c`**；
2. **完成登录：`libtv login phone -p <手机号> -c <6位验证码>`**。
若第 1 步提示「需要人机验证」，**在网页完成验证后把接口要求的参数经 `--captcha <json>` 传回并重试第 1 步**。频控 / 封禁 / 验证码错 → **stderr 打印原因 + 退出码非 0**。

**④ ★★ "活跃账户作用域"是第二套隐藏状态（本库此前零记录）**：
- **`account info` 与 `account use` 都会"顺手校准本机活跃账户作用域"**；
- **此后 `project list` / `project create` 在未显式传 `--team-id` 时，默认跟随当前生效账户的团队空间**；**`--team-id 0` 强制走个人**。
**→ 这是最容易误判的一处：切换账户会静默改变"默认项目列表范围与新建落点"。**

**⑤ `account use` 的解析与幂等**：**纯数字按 `accountId` 精确匹配；非数字按 `accountName` 精确匹配**；**同名账户命中多个 → 报错并要求改用 `accountId`**；**无论目标是否已经生效，都会刷新本机活跃账户作用域**；目标本来就是活跃账户时输出额外含 **`alreadyActive: true`**。

**⑥ 字段速查**：

| 命令 | stdout 关键字段 |
|---|---|
| `account info` | `user`（`uuid`/`id`/`nickname`）· `activeAccount` · **`teamId`** · `accountsCount` |
| `account list`（别名 `ls`） | `accounts[]`，每项 `accountId` · `accountName` · `accountType` · **`isActive`** · `teamId` |
| `account use <账号>` | `ok` · `accountId` · `accountName` · `accountType` · **`teamId`**（＋可选 `alreadyActive`） |

---

## ★★ `libtv logout`：清凭据（**官方 `commands/logout.md` · 一手 · 2026-10-15**）

- 行为：**删除 `LIBTV_CONFIG_DIR`（默认 `~/.libtv`）下的 `credentials.json`**，并**清除当前进程中的内存凭据快照**；
- **无子命令，仅 flags**；
- stdout JSON 含 **`credentialsPath`** 与 **`loggedOut: true`**；
- **★ 幂等**：**凭据文件本不存在时仍按"已登出"处理**，返回同结构 JSON，**退出码 0**（不是错误）；
- 与 `LIBTV_CONFIG_DIR` 配套：`LIBTV_CONFIG_DIR="$HOME/.libtv-dev" libtv logout` 只退自定义目录的那份凭据——**多账号隔离下退出也要对准目录**。

---

## ★★ 连边与改参的精确语义（**官方 `examples/workflow/*` · 一手 · 2026-10-15 读**）

### 一、`--left` 是**声明式对齐**，不是追加（本册此前未记）

| 写法 | 语义 |
|---|---|
| **`--left A --left B`** | **确保入边"就是"这 2 条——缺则补、多则剪**（**声明式对齐**） |
| `--left-add C` | **只追加**一条，不动其它入边 |
| `--left-rm A` | **只移除**一条，保留其余 |

- 三者的值都接受**显示名或 `nodeKey`**，只要**在当前项目/分组范围内唯一**；
- **★ 同一次命令里不允许混用**：**`--left` 与 `--left-add`/`--left-rm` 同时出现会被拒绝**；
- **★ 仅改入边不触发生成**——要触发必须显式加 `--run`。

### 二、`-s` / `-u` 的三个此前没落的细节

1. **`--set a.b=1` 会展开到 `data.params.a.b`**（官方 examples 的措辞是"**深合并**到已有 `params`"）；**`-u params=…` 会被拒绝**（改用 `--set`）；
2. **同一条命令里 `-s` 与 `-u` 都在一次提交里生效，顺序不重要**；
3. **改节点类型不可行**：`-u type=image` 被拒——**`data.type` 不经 CLI 变更**；要换类型就**删了重建**（`libtv node delete "X" && libtv node create …`）。

> **⚠ 一处官方文档之间的措辞冲突（如实记，不替它和解）**：`node-types/README.md` 说 `settings` 与节点已有值是**浅合并**；`examples/workflow/update-params.md` 说 `--set a.b=1` **深合并**到 `params`。**两层可能各说一层**（顶层 `params` vs `settings` 内部），但**本轮无法判定**；**涉及覆盖既有嵌套值时，先小步试一条再批量**。

### 三、`node create` 的两条接口限制

- **`libtv node create` 不接受 `--name`**——**展示名由位置参数 `<node>` 承载**；
- **`--run` 是"建完立即触发"**；省略则**只建节点不触发**（＝`node create` 把"建节点 / 改参 / 连上游 / 触发"合成一步）。

### 四、常见错误 ❌/✅ 对照（官方 6 例，可直接当排错表）

| # | ❌ 写法 | 报错形态 | ✅ 正确做法 |
|---|---|---|---|
| 1 | `-u params.prompt="…"` | 拒绝（`params` 属生成参数） | **`--set prompt="…"`** |
| 2 | `-u type=image` | 拒绝（`data.type` 不可经 CLI 变更） | **删除重建** |
| 3 | `--left A --left-add B` | 模式冲突 | **要么 `--left A --left B`（整体对齐），要么 `--left-add B`（仅追加）** |
| 4 | `--set ratio=16:9` 用在 `text` 节点 | **校验期**拒绝（该类型 schema 无此键） | **先 `libtv model search --type text` 看该类型接受哪些键** |
| 5 | 未登录/凭据过期 | **`401` / `AUTH_*`**（stderr、退出码非 0） | `libtv login web --open` |
| 6 | 未绑定项目又没给 `-p` | **`PROJECT_NOT_BOUND`** | `libtv project use <画布UUID>`，**或临时覆盖 `libtv -p <画布UUID> node list`** |

**★ 值得单独记的一条 CLI 形态**：**`-p` 可以写在子命令之前**（`libtv -p <画布UUID> node list`）——**这是"临时覆盖项目而不改目录绑定"的最短写法**。

---

## ★★ 安装、版本与"整目录替换"纪律（**官方 `libtv-cli/scripts/install.md` · 一手 · 2026-10-15 读**）

### 一、★ 安装入口的**权威来源**是一条 activity 接口

接口地址：`https://api2.liblib.art/api/www/landing-activities/getById?id=240`

响应的 **`data.linkUrl` 是一段 JSON **字符串**（要二次解析）**，字段与本库从客户端 bundle 里读到的端点表同源（`landing-activities/getById`）：

| 字段 | 含义 |
|---|---|
| `version` | **最新 CLI 版本号** |
| `install.shell` | macOS / Linux 一键安装脚本 URL（`curl -fsSL <url> \| bash`） |
| `install.PowerShell` | Windows PowerShell 安装脚本 URL |
| `install.CMD` | Windows cmd / 双击运行的 `.bat` URL |
| **`skill`** | **该版本 skill 包 zip 的 URL**（含本文档 + install 脚本） |

**★★ 铁律：直接取字段里的完整 URL，不要自己拼 `…/cli/<version>/…`**——官方明写"**拼错版本段会和发布脱节**"。

**★★ 这张 `landing-activities` 通道是“通用远端配置通道”、不是安装专用**（2026-10-16 REA 补）：
客户端配置里有 **27 个具名键**（`config.tv.remoteConfig`——`slashImage:“188”` · `supportModels:“182”` · `generatorRestriction:“309”` · `cameraControl:“186”` · `voiceList:“190”` · `videoComposeAgent:“280”` · `tvDirectorAgent:“311”` · **`cliDownload:“240”`** 等），**取数链是`名字 → useRemoteConfigHooks(id) → GET getById?id=<id> → JSON.parse(data.linkUrl) → store`**；
**本节那条 `id=240` 就是其中 `cliDownload` 一条，其余 26 个键走同一套链**——**URL 前缀由解析器按路径分流**（`/api/www` → `config.apiHost` ＝ `https://api2.liblib.art`），**底层传输是打包进来的 Axios `1.6.7`**（**默认适配器 `["xhr","http"]`、注册表里 `http` 为 `null` ⟹ 浏览器里走 XHR**）。

### 二、脚本内部的平台分包（使用者无需关心，但要能看懂报错）

- CLI 二进制 zip 的下载地址是 **`https://liblibai-web-static.liblib.cloud/cli/<version>/<zip>`**，其中 **`<version>` 取自上面接口的 `.version`**（**脚本不内置默认版本号**）；
- `zip` 按平台：macOS `-arm64` / `-x64` · Linux `-x64` / `-arm64` · Windows **`libtv-windows-amd64.zip` / `libtv-windows-arm64.zip`**；
- **zip 内要求**：**根目录或任一子目录含 `libtv` / `libtv.exe`**（脚本在临时目录里找出来再拷）；
- 依赖：**`curl` 或 `wget`**（Windows 用 `Invoke-WebRequest`）；解压用 **`unzip`**（Windows `Expand-Archive`）；
- **★ 脚本不用 `rm` 清理**：**解压目录与下载的临时 zip 会留在系统临时目录**（可自行删）；
- 安装目标是 **`cp -f`（Windows `Copy-Item -Force`）覆盖**，用于升级；
- 默认落点：macOS/Linux **`~/.libtv/libtv`**；Windows **`%USERPROFILE%\.libtv\libtv.exe`**；
- PATH：macOS/Linux 按 `$SHELL` 探测 `~/.zshrc` / `~/.zprofile` / `~/.bashrc`，**只有没写过标记行时才追加** `export PATH="<安装目录>:$PATH"`；**找不到 profile 就只打印要手动加的两行**。Windows 则**写入当前用户 Path**（需重开终端）。

### 三、★★ 更新 skill 目录必须**整目录替换**（本库此前零记录）

**理由（官方原话要点）**：`unzip -o` / `Expand-Archive -Force` **只会覆盖同名文件，不会清理旧版独有的文件**——直接覆盖会让**新版本里已删除的旧文件残留**，于是"文档看起来是新的，实际夹着旧文件"。

**正确步骤**：
1. 取 activity 接口的 **`skill`** 字段（**不要手工拼 zip 路径**）；
2. 下载该 zip；
3. **先删除**当前 skill 目录 → **新建同名空目录** → 把 zip **解压进去**（目的是与 zip 内容**严格 1:1**）；
4. **`cd` 进该目录**再执行 install 脚本（脚本会解析**同一个** `version`）。

**★ 为什么这样就"版本自洽"**：**`skill` 与 `version` 同出自一次 activity 响应 ⟹ 二者天然同版本**；在该目录下跑 install 就保证 **CLI 二进制与这套 skill 文档版本一致**。
**★ 一条目录纪律**：**skill 目录不应放任何用户私有文件**（`.libtv/` 在 skill 目录的**兄弟**位置、不会被波及）。

**→ 与本库的关系**：本册 §一 记过 CLI 版本 `1.1.3` 与 `libtv.exe` 的 SHA-256；**版本巡检应改走这条 activity 接口取 `version`，而不是猜目录名**。
