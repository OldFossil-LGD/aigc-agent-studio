# LibTV 网页端请求形状与任务端点（客户端侧 API 契约）

> **来源**：登录态编辑器 bundle（146 个脚本）静态阅读（**一手 · 2026-10-15 读**）。
> **为什么单列**：`libtv-cli-env-binding.md`（280 行）· `libtv-billing.md`（274）· `libtv-ignite-ops-fields.md`（271）都已接近上限，而这块内容自成一类——**网页端每条任务接口"发什么字段、走哪个 host、失败怎么处理"**。
> **读完回哪**：`libtv-ignite-ops-fields.md`（点火字段）· `libtv-billing.md`（报价）· `libtv-cli-env-binding.md`（CLI 侧）。 **失败语义（鉴权过期 / 静默错误 / 请求装饰）→ `libtv-web-client-errors.md`。**

---

## 一、★★ 风险控制：`riskControl.deviceToken`（本库此前零记录）

客户端有一个包装函数，**在满足条件时给请求体加一个字段**：

```text
条件：config.region === "cn"  且  config.aliyunDeviceFingerprint.appKey 存在
动作：body = { ...body, riskControl: { deviceToken: <设备指纹 token> } }
      （取不到 token 时先触发初始化，并原样返回 body）
```

**★ 三条读法**：
1. **这是"设备指纹/风控"字段，不是内容审核**——它的作用是标识设备，不是判断内容合规；
2. **只在 `cn` 区域且配了阿里云指纹 appKey 时才附加** ⟹ **海外区域/无该配置时请求体里没有这个字段**；
3. **我方走 CLI 或自建请求时不会带它** ⟹ **两侧请求体在当前账号区域下本来就不同构**，对照抓包时要预期这个差异。

## 二、★★ 生成带指纹、**报价不带**（关键差异）

| 接口 | 是否过 `riskControl` 包装 | 其它预处理 |
|---|---|---|
| **创建生成任务** | **★ 是** | 剥 `clientContext` → 清洗 → `params` 过异步处理 → **图像类先做本地图拦截** |
| **光照任务**（`generateLighting`） | 未观察到该包装 | 同上（剥 clientContext / 清洗 / 图像类拦截） |
| **视频优化任务**（`videoOpt`） | 未观察到 | **只清洗**（不做 `params` 异步处理、不做图像拦截） |
| **报价**（`calculatePower`） | **★ 否** | 同上（剥 clientContext / 清洗 / `params` 异步处理 / 图像类拦截） |

**→ 结论**：**"报价"与"生成"的请求体并非完全同构——生成的会多一个 `riskControl`**。做"算分与提交同体"的推断时，**要扣掉这一处差异**。

## 三、任务与队列类端点的请求体（逐条）

| 用途 | 请求体 |
|---|---|
| 创建生成任务 | 见上（另可带 **`headers: {"x-language": <语言>}`**——**生成调用支持语言头**，此前未记录） |
| 查询进度 | `{ taskIds }`，**可选 `teamId`（>0 才带）**，支持 `AbortSignal` |
| 批量查询进度 | **`{ teamId }`（>0）**；**否则完全不发 body** |
| 停止批量 | `{ taskIds }` |
| **跳过排队** | **`{ taskId }`**，可选 `teamId`（>0 才带）；**★ 失败被吞掉并返回 `null`**（前端不弹错） |
| **Agent 预算** | **原样透传入参**（无清洗） |
| **Agent 让出** | **`{ taskId }`** |
| 提示词优化 | **`{ prompt }`** |

## 四、模型/素材类只读助手：**走另一批 host，且错误被静默吞掉**

| 用途 | host + 路径 | 备注 |
|---|---|---|
| 模型目录流 | `internalApiHost` + `/api/www/model/feed/stream` | body **`{ platform:"libtv", ...e }`** |
| 视频模型流 | `internalApiHost` + `/api/www/model/video/stream` | 同上 |
| 模型搜索 | `internalApiHost` + `/api/www/model/search` | — |
| **SD 模型搜索 v2** | **`bridgeApiHost` + `/gateway/sd-api/model/searchV2`** | 同样带 `platform:"libtv"` |
| 风格库 | `internalApiHost` + `/api/www/image1/styleList` | — |
| 公共标签 | `internalApiHost` + `/api/www/public/tag/v3` | — |
| 订阅/退订模型版本 | `internalApiHost` + `/api/www/model/model-version/subscribe` / `unsubscribe` | — |
| 记录模型使用 | `internalApiHost` + `/api/www/model/used/history/add` | — |

**★★ 一条会影响排查的行为**：**上面这批 `internalApiHost` 调用几乎都在 `catch` 里静默返回空**（`catch{}` / 静默 return）。
**→ 后果**：**这些接口挂了，界面上不会有任何报错**——"模型列表空/风格库空"很可能是**网络或域名问题被吞掉了**，而不是"平台没有数据"。
**→ 排查动作**：遇到这类空数据，**先看网络层（host 是否可达、是否 4xx/5xx）**，别先怀疑平台侧目录。

## 五、认证变体：`clickSuggest` 用 **header `token`**（不是常规鉴权）

该接口自己拼 `Content-Type: application/json`，并**从 cookie 取 token 后放进请求头 `token`**；非 2xx 直接抛错（**不吞**）。
**→ 与上面那批"静默吞错"的助手形成对照**：**同是辅助调用，处置策略不同**。

---

## 六、主体库（entity-library）与两条"内置小流水线"（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

### 一、主体库 CRUD（逐条）

| 操作 | 方法与请求体 |
|---|---|
| 建 | `POST` **原样透传** |
| 列 | `POST`，**默认入参 `{}`**（可空调用） |
| 改 | `POST` 原样透传 |
| 删 | `POST` 原样透传 |
| **查进度** | **`GET`，params `{ taskId }`**（从入参的 `taskId` 取） |

**→ 结构读法**：**只有"查进度"是 GET**（且**只吃 `taskId`**）；**建/改/删/列都是 POST 透传** ⟹ **字段集由服务端定义**。**"主体库"的产物是任务化的**（有 progress 查询 ⟹ **生成/解析是异步任务**，不是同步返回）。

### 二、★ 内置小流水线 A：**单图 → 多镜头图组**（`kling-multi-shot`）

客户端内置了一条"补全/多镜头"链路，参数逐字：

```text
提交：params = { imageList: [<单图>] }
      provider = "kling"    model = "kling-multi-shot"    taskType = "image"
      metadata = { node_id: "", project_id: "" }           requestId = <客户端生成>
轮询：按 taskId（+ 可选 teamId）取进度
解析：优先取 result.batches[]；若没有 batches 但有 images[]，
      则把 images 包成单个 batch，逐图配 label；
      两者都没有 → 返回 { batches: [] }
```

**★ 两条可用读法**：
1. **"多镜头/智能补全"在客户端是一条"预设 provider+model 的生成任务"**——**不是独立接口**；要复刻就照这组字段发；
2. **结果解析有三级兜底**（`batches` → `images` → 空），⟹ **抓回读时两种形状都要认**。

### 三、★ 内置小流水线 B：**图 → 角色描述**（`qwen-3-vl-flash`）

```text
提交：params = { count: 1, model: "qwen-3-vl-flash",
                 imageList: [<参考图…>], scene: "character_description" }
      provider = "qwen"    model = "qwen-3-vl-flash"    taskType = "text"
轮询：同上
解析：取 result.texts[] → 逐条 trim → 丢空 → 用换行拼成一段 → { description }
```

**★★ 意义**：**"看图写角色描述"是平台内置的一条文本任务**，而且**用 `scene:"character_description"` 这个显式场景值**（与本库记过的"音频节点必带显式 `scene`"同源思路）。
**→ 与我方一致性主线的接口**：**这条链路产出的是"描述文本"，`userCharacterParse` 产出的是"可复用 `generation_prompt`"**——**两者是不同的东西**：前者用于**给人读/写进提示词**，后者用于**存成角色卡跨项目复用**。**别混用。**

---

## 七、智能片头（opening）接口族 + 版本族"声明存在但无调用点"（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

### 一、片头预设 CRUD（三条，全部 POST）

| 操作 | 请求体 | 返回值 | 失败处置 |
|---|---|---|---|
| **列预设** | `POST openingList` **`{ page: 1, pageSize: 100, type?, … }`** | `data.list` | **抛错**（`code!==0` 即抛），**外层捕获后回退到缓存或内置默认预设并 `warn`** |
| **存预设（upsert）** | `POST openingUpdate` 传整个预设对象 | **`data.opening`** | 抛错 |
| **删预设** | `POST openingDelete` **`{ uuid }`** | **`data.deleted`** | 抛错 |

**★ 三条读法**：
1. **"更新"端点承担 upsert**——**存新品与改旧品走同一个接口**，按有无 `uuid` 区分（新预设会拿到平台分配的 uuid 并缓存）；
2. **列表固定按 `page:1, pageSize:100` 拉**（前端一次性取前 100 条）⟹ **预设数超过 100 时前端只认前 100 条**；
3. **响应统一过一道"`code` 校验"**：`if (!e || 0 !== e.code) throw Error(e?.msg || <兜底文案>)`，**成功值一律取 `e.data`**——与那批"静默吞错"的助手形成第三类处置（**抛错但有降级**）。

### 二、★ 片头预设的缓存策略（可直接照抄）

- **缓存 TTL ＝ 300 000 ms（5 分钟）**：命中缓存先立刻用缓存渲染，**只有当 `Date.now() - fetchedAtMs > 5 分钟` 时才在后台重拉**；
- **拉取失败**：**回退到缓存；无缓存则回退到内置默认预设**，并只发一条 `warn`（**不阻断界面**）；
- **删预设**时**同时更新本地状态与缓存里的 list**（两处都过滤）。
**→ 含义**：**片头预设列表不是"每次打开都最新"**——**改完别人的预设可能要等一个 TTL 或手动重载**。**要拿"当前真实列表"，别只看一次界面。**

### 三、`draft/update` 的请求体带**视口三要素**（本库此前未记）

遥测字段集反推出 `canvas/project/draft/update` 的入参形态：
**`{ projectUuid, draftJson, viewportX, viewportY, viewportZoom }`**（遥测里还带 `hasDraftJson` / `draftJsonSize` / `draftJsonBytes` 等派生量）。
**→ 含义**：**画布草稿保存会把"视口位置与缩放"一起存**——**所以"打开画布看到的位置"是服务端存下来的，不是本地记忆**。

### 四、`project/user-state/update`：**`10051` 是特殊错误码**

该接口在抛错前**先判 `code`**；其中 **`10051` 走一个专门分支**（触发一个内部处理函数）后才继续抛。
**→ 记法**：**`10051` 不能当普通业务错误处理**——它被客户端单独识别（**语义未在本轮判定**，只确证"有专属分支"）。

### 五、★ 版本族（`canvas/project/version/create|list|snapshot`）：**声明存在，但两个 bundle 里都没有调用点**

**事实**：这三个端点在**端点表里有声明**，但**登录态画布 bundle（146 脚本）与公开首页 bundle（85 脚本）里都找不到调用点**（本库也早已在静态端点表里列出过它们）。
**→ 判定**：**"端点存在、调用点不在本次抓到的两个 bundle 内"**——**不是"端点不存在"**，而是**它可能由别的页面/入口（或旧版本遗留）使用**。
**★ 纪律**：**"没找到调用点"只能记成"调用点未知"，不能记成"没有这个能力"**——这两者在证据等级上差一整级。

### 六、附带：分享类接口的两种处置

| 接口 | 方法 | 失败处置 |
|---|---|---|
| `project/share/detail` | `GET { params:{ shareId } }` | **静默吞错**（`catch{}`） |
| `project/share/set-enabled` | `POST` 透传 | **记录并继续**（不阻断） |
| `project/copy-to-team` · `copy-to-team/status` · `project-space/copy` | `POST` 透传 | — |

---

## 八、Skill 族（模板/`/` 面板/案例）（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

### 一、★ Skill 引用串是怎么拼出来的（把上一轮的"格式"补成"构造函数"）

客户端有一个专职构造函数，逐字逻辑：

```text
常量 命名空间 = "libtv-user-generated"
normalize(key): trim → 去掉首尾的 "/"
build({id, skillKey, namespace}):
  取 key = skillKey ?? id
  若 key 里已经含 "/"  → 原样返回
  否则 → normalize(namespace ?? 默认命名空间) + "/" + key
```

**★ 三条读法**：
1. **`libtv-user-generated/…` 里那串 `slug-<32位hex>` 整体就是"skillKey"**——**hex 不是客户端拼上去的**，是 key 自带的；
2. **key 里若已含 `/` 就不再前缀** ⟹ **引用串既可能是"带命名空间的全串"，也可能是"裸 key"**，两端都要认；
3. **命名空间可由调用方覆盖**（不传才用默认 `libtv-user-generated`）。
**另有**一个"把 JSON 串解析成 `{skillId, prompt, draft}`"的小函数（**三者都可选，`draft` 必须是布尔 `true` 才生效**）——**说明存在"以 JSON 串携带 skill 引用"的调用形态**。

### 二、★★ 枚举常量表（本库此前零记录，可直接当判据）

| 维度 | 取值 |
|---|---|
| **来源/作者类型** | **`Manual = 0`** · **`Agent = 1`** |
| **结果类型** | **`Text = 1`** · `Image = 2` · `Video = 3` · `Audio = 4` |
| **★ 审核状态（四态）** | **`Offline = -1`** · **`Pending = 0`** · **`Approved = 1`** · **`Rejected = 2`** |
| **归属** | **`User = 1`** · **`Platform = 2`** |
| **分类** | **`General = 0`** · **`DirectorRole = 2`**（**1 被跳过** ⟹ 疑为废弃值，**不可判定**） |

**★ 三条可当判据的**：
1. **Skill 模板有审核四态** ⟹ **"发布"不是即时生效**，**`Pending` 是正常中间态**；
2. **`Manual` / `Agent` 区分"人工编的"与"Agent 生成的"**——**与我方"Agent 产出物要留痕"同向**；
3. **`User` / `Platform` 归属是显式数值**（与上一轮片头预设的 `official` 布尔同源思路）。

### 三、接口族（逐条）

**★ 一个公共前置**：多数 skill 接口会**先取当前 `teamId`，有则注入 `{ ...body, teamId }`**（少数几个如 `skillBizList` **不走**这个注入）。

| 操作 | 方法与请求体 | 返回/失败 |
|---|---|---|
| skill 键查询 | **`GET`** | `data.items[]` |
| 建 | `POST` **`{ skill, updateType, bizType? }`**（+teamId） | `data.skill`；**失败抛自定义错误类 `SkillApiError(msg, code)`** |
| 优化 | `POST` **`{ skill }`**（+teamId） | `data.skill` |
| 改 | `POST` **`{ skill, skillUuid, updateType }`**（+teamId） | `data.skill` |
| 列 | `POST`（+teamId） | `{ list, total, hasMore }` |
| 业务列 | `POST`（**不注入 teamId**） | `{ list, total, hasMore }` |
| **★ `/` 面板搜索** | `POST`（+teamId） | **`data.list[]`** |
| 详情 | **`GET` + params `{ skillUuid, teamId? }`** | `data.skill ?? data` |
| 删 | `POST` **`{ skillUuid }`**（+teamId） | — |
| 使用上报 | `POST`（不消费返回） | — |
| 模板流 / 收藏流 | `POST` | `{ list, total, hasMore }` |
| **模板详情** | **`GET` + URLSearchParams `{ templateUuid, version? }`** | `data.skill ?? data` |
| **★ 点赞模板** | `POST` **`{ targetType: 8, targetUuid }`**（用通用的社区点赞接口） | — |

**★ 两条新料**：
- **`targetType: 8` 就是"skill 模板"**（社区点赞/取消赞共用接口，靠 `targetType` 区分对象类型）；
- **模板详情支持 `version` 参数** ⟹ **模板是带版本的**（与"skillKey + skillVersion"对得上）。

### 四、★ "案例"三联结构（本库此前零记录）

客户端把案例归一成：**`productionCaseUrl`（生产案例）· `canvasCaseUrl`（画布案例）· `canvasCasePower`（画布案例积分）**；**优先读结构化的 `caseItems[]`**（只保留带 `productionCaseUrl` 的），**否则从 `productionCaseUrls[]` + 单个 `canvasCaseUrl` + `canvasCasePowers[]` 按下标配对构造**。
**→ 含义**：**"这个 skill 用起来大概花多少积分"平台是有数据结构的**（`canvasCasePower`）——**可作我方差旅式"预算前置"的参照**。

---

## 九、第三方素材（third_asset）与**两种协议闸门**（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15 读**）

### 一、素材族接口（含两个错误码）

| 操作 | 请求体 | 备注 |
|---|---|---|
| 视觉验证-取码 | `POST {}` | 失败 `Notify.error("qrCodeFetchFailedRetry")` |
| 视觉验证-查结果 | `POST` **`{ bytedToken }`** | **走"字节 token"** |
| 视觉验证-列 | `POST e ?? {}` | `{list,total}` |
| 视觉验证-改 | `POST` **`{ id, title }`** | 返回 `success` 布尔 |
| **建素材** | `POST` **`{ ...入参, version: 1 }`**（**强制 `version:1`**） | **★ `10025` ＝ 资产保存**数量上限**（`assetSaveLimitReached`）——只 `warn` 不抛** |
| **★ 素材检查** | `POST` **`{ uuids }`** | **`code!==0` 抛 `assetAuditCheckFailed`** ⟹ **这是一个"审计/合规检查"入口**（**检查对象是素材 uuid 列表**） |
| 列素材 | `POST e ?? {}` | **吞错给空**（`{list:[],total:0}`） |
| **删素材** | `POST` **`{ uuid }`** | **★ `10051` ＝ 该素材已不存在（被删过）** → 提示 `assetNotFoundDeleted` 并返回 `false` |

**★ 与上一轮的呼应**：**`10051` 第二次出现**（上次在 `project/user-state/update`）——**它是"对象已不存在/已失效"这一族的码**（**语义仍属推断，但两处都判"不必重试"**）。

### 二、★★ 两种协议（agreement）——**这就是第 2 轮实测的"承诺书闸门"的接口级形态**

| 协议类型（逐字） | 检查 | 签署 |
|---|---|---|
| **`star-video`** | `POST agreementCheck { agreementType: "star-video" }` → 读 **`data.signed`** | `POST agreementSign { agreementType: "star-video", version: "v1.0" }` → 成功判 **`code === 0`** |
| **`doubao-visual`** | `POST agreementCheck { agreementType: "doubao-visual" }` → 读 **`data.signed`** | `POST agreementSign { agreementType: "doubao-visual", version: "v1.0" }` → 成功判 **`code === 0`** |

**★ 三条结论**：
1. **第 2 轮在登录态 UI 上撞到的《Seedance模型使用承诺书》闸门，在接口层就是 `agreementType: "star-video"` 的"先 check 后 sign"两段式**——**闸门的存在由此从"UI 现象"升级为"接口契约"**；
2. **协议是"类型 + 版本字符串"两个维度**（`"v1.0"` 是**客户端硬编码的版本**）⟹ **协议改版可能只改这个串**，做巡检时可盯它；
3. **`doubao-visual` 是第二类协议**（豆包视觉），说明**闸门不止一道，且按"能力/模型族"分**。

**★ 纪律不变（重申）**：**`sign` 是"以用户名义同意法律条款"的动作**——**任何自动化都不得代签**；我方只允许**读 `signed` 状态**，遇到未签**就停下报告**。

---

## 十、VFS 文件接口族（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15**）

| 用途 | 方法 / 路径 | 关键请求字段 | 关键返回字段 |
|---|---|---|---|
| 读文件 | `POST /api/canvas/folder/vfs/read` | `projectSpaceId`、`path`、`teamId?` | `data.content`、部分场景 `data.name` |
| 写文件 | `POST /api/canvas/folder/vfs/script/write` | `projectSpaceId`、`path`、`content`、`teamId?` | 调用方检查 `code===0` 与 `data.success` |
| 推草稿 | `POST /api/canvas/folder/vfs/draft/push` | `projectSpaceId`、`status:1`、`canvasId`、`sessionId`、`paths[]`、`teamId?` | 调用方检查 `code===0` 与 `data.success` |
| 脚本 diff | `POST /api/canvas/folder/vfs/script/diff` | `projectSpaceId`、`workKey`、`teamId?` | `data.pairs[]`：`origin_path` / `change_path` |
| 脚本清单 | `POST /api/canvas/folder/vfs/scripts` | 未见独立调用点 | **调用点未知** |

**Folder 枚举**：`VFS_OLD=11`、`VFS=15`（与 `PROJECT_SPACE=10` 等并存）。

**★ 行为判据**：
1. VFS read/write 是 **project-space 文件**操作，不是画布节点操作；
2. 剧本编辑器写入有 **1500ms debounce**，不能把 UI 编辑当成服务端保存；
3. VFS wrapper 的普通错误可能在 wrapper 层被吞，调用点再检查 `code` / `data.success`；
4. **`scripts` 清单只有端点与 wrapper，没有调用点，必须标 unknown**。

---

## 十一、节点 payload 侧车（**登录态编辑器 bundle 静态 · 一手 · 2026-10-15**）

| 用途 | 方法 / 路径 | 客户端契约 |
|---|---|---|
| 读节点 payload | `GET /api/canvas/node/payload/get` | params `{projectUuid,nodeKey}`；消费 `data.payload`、`data.updatedAtMs` |
| 写节点 payload | `POST /api/canvas/node/payload/save` | body `{projectUuid,nodeKey,payload}`；`payload` 是 JSON 字符串 |
| 批量读 | `POST /api/canvas/node/payload/batch/get` | **只有端点常量，wrapper 与请求/响应均 unknown** |

**读改写 wrapper**：按 `projectUuid+nodeKey` 合并并发；空 payload 按 `{}`，数组/标量拒绝；结果不变则不保存；序列化 UTF-8 **`>4,194,304` 字节即拒绝**。
**已证实用途**：OpeningEditor 存 `opening.title/versions/lastView/task`；Seedance 在 `seedanceDraft.version=1` 下缓存成功样片详情，命中即跳过重复任务详情查询。
**纪律**：这证明的是“按节点存侧车对象”，**不能外推为任意节点通用扩展位**；未观测服务端冲突、清理与 `batch/get` 契约。
