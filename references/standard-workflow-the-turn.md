# 标准工作流程（基准：《THE TURN 回合》可访问副本）

> **地位**：用户指定 THE TURN 为「最标准的工作流程」。做 LibTV 长片/短片的复刻、反推、新建，
> **默认以本文为基准**；除非用户对具体作品另给基准。
> **证据**：2026-10-10 对可访问副本 `fa2c927dfed048a8ac938fe008f4a3c8`
> （项目名带“- 副本”）的全量只读回读；该副本的原始项目 UUID 为
> `014c3b4b8fa3489f88993da7853463c9`，当前账号直接读取原项目返回
> `30001 private no permission`。因此本文的所有统计属于“副本层”，
> 未与原项目做过节点级差异核对。
> （581 节点 / 1550 边 / 81 组；194 video、178 image、92 text、36 audio 全部逐个 `node` 读参）。
> **只读纪律**：该画布记忆中标记 forbidden-write，全程未写、未点火。
> 标签：【已验证】= 本轮自己读出来的 ·【库规】= 本库成文约束 ·【推断】= 未验证

## 0 · 一句话

**不是"一镜一个节点"，是「一段一个节点」**：先做资产 → 每段先写中文规格书 → 编译成
6000 字级英文执行 prompt（参考清单 + 输出契约 + 秒级节拍）→ 挂到 `mixed2video` 视频节点
（4–40 秒一段、30 秒为主力）→ 命名里带版本与状态 → 人审单独成组。

## 1 · 规模与构成【已验证】

```text
节点 581 = 组 81 ｜ video 194 ｜ image 178 ｜ text 92 ｜ audio 36
边  1550 = image→video 1191 ｜ audio→video 299 ｜ video→video 33 ｜ audio→audio 8
           image→text 7 ｜ video→image 5 ｜ image→image 4 ｜ video→audio 3
画布 bbox  x −5508…12528 ｜ y −4836…139200（按段落自上而下拉开，纵向极长）
```

## 2 · 五层结构（照这个顺序建）

### 2.1 资产层 —— **在画布外做，画布内只上传**【已验证】

```text
178 张图里 174 张是 image_resource（上传），只有 4 张是画布内生成
资产单独成组，命名 TT_ASSET_<序号>_<类别>：CHAR_BOARDWORLD_UNIFORMS / CHAR_PERFORMANCE /
  LOCATION_MASTERS / VEHICLE_DETAIL / PROPS_THREE_VIEW_12（道具三视图）/ CARDS_PRINT /
  BOARDWORLD_REALMS / HABITAT42_FLEET / *_USER_LOCKED / *_NO_CANVAS_GEN
```

→ 资产不进 video 生成流程，只作为**参考图**被引用。凡是"在画布外生成再上传"的，组名直接写
`CODEX生成静态资产_…_离线_图片_NO_CANVAS_GEN`。

### 2.2 规格层 —— 每段一份**中文规格书**（text 节点）【已验证】

```text
载体：text 节点的 data.content，是【字符串数组】，不是字符串（读的时候 join）
体量：92 个 text 共 575,140 字；单篇中位 6,165 字，最长 19,256 字
骨架：# 标题 / ## Authority / ## Shot purpose / ## Audience and viewpoint /
      ## Causal spine / ## Scale and camera meaning / 时间码节拍 / 禁令
77/92 篇正文里内嵌 {{Node <uuid>}}（把被引用的节点 ID 写进正文，人眼可审计）
```

### 2.3 执行层 —— 编译成**英文执行 prompt** 挂在 video 节点上【已验证】

179/194 个 video 有非空 prompt（中位 **6,215 字**，最长 13,768，合计 102 万字）。骨架：

```text
① 头行（151/179）  ACTIVE ASSETS — <段名>, EXACT ORDER
② 参考清单（150/179）@ImageN = {{Node <uuid>}} — 这张只锁什么
                    中位 5 行，最多 30 行
                    并写明边界："Assets lock topology, materials, vehicle class and scale
                    — not action, framing or endpoint state."
③ 输出契约（138/179）OUTPUT CONTRACT：时长 / 画幅（141/179 写 21:9）/ 分辨率 / 帧率
                    （142/179 写 24fps）/ 切数
④ 秒级节拍（154/179）0.0–2.0 …／2.0–4.0 …（**一段之内按时间码写多拍**）
⑤ 硬禁令（43/179）  ABSOLUTE ZERO VISIBLE PEOPLE / no human / 不出现 UI·字幕·logo 等
```

### 2.4 视频节点参数 —— 主力是"长段 + 多参考 + 带声"【已验证】

```text
modeType：mixed2video 177/194（另有 longVideo2video / image2video / text2video 各 1）
模型    ：Seedance 2.5 178/194（另有 Topazlabs 4 = 超分后处理、Seedance 2.0 VIP 2）
时长    ：4–40 秒；30s ×58（最多）、4s ×30、15s ×22、6s ×14、18s ×12、10s ×11、20s ×9
         —— 名字里写的秒数与 settings.duration 一致 104/108
参考图  ：imageList 最多 30 张；4 张最常见（38 个），8–30 张的长尾很厚
音频    ：audioList 0–4 条（3 条 ×33、4 条 ×32）
声音    ：enableSound = on 176/194
```

### 2.5 人审与版本层 —— 写进画布结构，不写在文档里【已验证】

```text
命名即状态机：<段编号>_<时间码>_<语义名>_<时长>S_<版本>_<状态>
  video 名含版本号 98/194 ｜ 含时长 112/194 ｜ NO_RUN 35 ｜ ATTEMPT 8 ｜ RETAKE 7 ｜ _READY 4 ｜ 副本 10
  组名   含 NO_RUN 53/81 ｜ 含版本号 41/81 ｜ ASSET 19/81 ｜ SEQUENCE 4/81
人审显式组：`角色权益_用户确认_EVAN_LENA_KAI_WORLD`、`长镜头图权属_C07_C17_用户确认`、
            `TT_ASSET_游戏指挥官_开场2S角色_用户锁定_v1`
生产单元：多数组 = 1 条 text 规格 + 1 条 video（25 组严格 1:1，且 25/25 的 video prompt
          以该 text 正文开头 → **双层：中文规格书是母本，英文执行 prompt 是派生**）
```

【库规】本轮同时确认：**节点名承载语义与状态、不承载"运行状态"推导**这条本库旧规，
在本样本里被作者主动违反而获益（她用 `NO_RUN`/`READY`/`ATTEMPT` 直接标状态）。
→ 读别人的画布时按作者写实读；自己建图时仍按本库规矩（状态另存台账）。

## 3 · 与我过去做法的差异（这是要改的）

| 维度 | 基准（THE TURN） | 我过去的做法 |
|---|---|---|
| 粒度 | **一段一节点**（4–40s，30s 主力），段内秒级节拍 | 一镜一节点（116 镜 × 5s） |
| 提示词 | 6,000 字级，含参考清单/输出契约/节拍/禁令 | 约 500 字四段块 |
| 参考 | 最多 30 张（中位 5 行 @Image） | ≤7 张，且含无入边的占位节点 |
| 视频模型 | Seedance 2.5 为主 | Kling O3 一把梭 |
| 资产 | 画布外做、画布内上传（174/178 上传） | 画布内造 anchor→refine_a→refine_b |
| 音频 | 上传资源 + 挂进 video 的 audioList（0–4） | 单独的 text2audio 节点 |
| 命名 | 版本/时长/状态写进名字 | 无语义状态 |

## 4 · 用这份基准时的检查清单

```text
☐ 每段先有中文规格书（text，data.content 数组），再编译英文执行 prompt
☐ 执行 prompt 五件套齐：ACTIVE ASSETS 头 / @ImageN 清单 / OUTPUT CONTRACT / 秒级节拍 / 禁令
☐ 参考清单写"锁什么、不锁什么"，@ImageN 用 {{Node <uuid>}}
☐ 视频节点：mixed2video + Seedance 2.5 + enableSound on；时长按段给，不全局统一
☐ 资产离线做、画布内只上传；资产单独成组且组名带用途
☐ 名字带版本与状态；需要人拍板的地方单独成组（用户确认/用户锁定）
☐ 只读别人的画布；点火一律等用户显式批准
```


---

> **拆卷指针**：**§5–§6（可执行骨架与填空模板）已按职责移入 `standard-workflow-the-turn-part2.md`**（续册）。**原节号跨册连续，不重新编号**——本册保留 §0–§4、§7、§8。**★ 要照着写的时候去续册；要判断"该不该这么写"看本册 §7。**

---


## 7 · 跨作品校验：哪些是标准、哪些是这一部的做法

**七张源画布 / 七部作品**全部实测（结构层，2026-10-10 回读）：

| 作品 | 节点 | 构成 | 边 | 边的主成分 |
|---|---|---|---|---|
| 弥寿计划 W1 | 180 | image 42 ｜ video 118 ｜ text 1 ｜ 组 19 | 775 | image→video 659 ｜ **video→video 112** |
| 抵达之前 W2 | 762 | image 220 ｜ video 466 ｜ audio 11 ｜ text 5 ｜ 组 27 ｜ **video-clip 33** | 1926 | image→video 1455 ｜ audio→video 210 ｜ video→video 101 ｜ video-clip 往返 51 |
| THE TURN W3 | 581 | image 178 ｜ video 194 ｜ text 92 ｜ audio 36 ｜ 组 81 | 1550 | image→video 1191 ｜ audio→video 299 |
| 放殃 | 437 | image 319 ｜ video 61 ｜ text 7 ｜ 组 49 ｜ script 1 | 377 | image→image 286 ｜ image→video 78 |
| 出走 | 285 | image 268 ｜ video 12 ｜ 组 5 | 303 | image→image 285 ｜ image→video 18 |
| 坠星 EP3 | 81 | image 50 ｜ video 28 ｜ audio 3 | 113 | image→video 59 ｜ image→image 25 |
| Wrong Room | 138 | image 81 ｜ video 39 ｜ text 15 ｜ audio 1 ｜ 组 1 | 199 | image→video 95 ｜ image→image 73 |

视频参数（2026-10-10 逐节点全量读数；W1／W2 读全部 video 节点，其余读全部非组节点）：

| | 视频主力模式 | 模型主力 | 段长主力 | 视频 prompt 中位 | 参考图中位/最多 | enableSound |
|---|---|---|---|---|---|---|
| W1 弥寿计划 | mixed2video 112/118 | Seedance 2.5 115/118 | **30 s（38 段）** | 3,733 字 | 8 / 12 | on 115 |
| W2 抵达之前 | mixed2video 365/466 | Seedance 2.5 431/466（长片模式 151） | **30 s（330 段）** | 3,242 字 | 4 / 9 | on 431 |
| W3 THE TURN | mixed2video 177/194 | Seedance 2.5 178/194 | **30 s（58 段）** | 6,215 字 | 5 / 30 | on 176 |
| 放殃 | **singleImage2video 39/61** | **Kling 3.0 38** | **6–8 s（13+11+10 段）** | **37 字** | 1 / 4 | on 60/61 |
| 出走 | singleImage2video 9/12 | Kling O1 6 ／ O3 3 | 5 s（8）／10 s（4） | 一句话（10–30 字） | — | on（样例） |
| 坠星 EP3 | mixed2video 10 ／ text2video 5 ／ 参数缺 13 | Seedance 2.5 15 ＋ Topazlabs 13 | 20 s（5）／15 s（4） | **0 字（15 条空）** | 0 / 11 | on 15 |
| Wrong Room | mixed2video 30/39 | **Seedance 2.0 VIP 31** | **15 s（17 段）** | 303 字 | 3 / 6 | on 36 |

顺带读到的图片层：放殃 319 张图 **prompt 中位 18 字**（Style Image V7 79 张）· 坠星 50 张图
（Lib Image 2.5 Pro 23、Topazlabs 10）· Wrong Room 81 张图（Lib Image 51）＋ text 15 个（content 中位 2,496 字）。

### 7.1 七部里面真正共同的（很少，只有这四条）

```text
① 节点单位是"段／镜"：一个视频节点 = 一次生成（秒级到 30 秒级），没有逐帧节点
② 边就是连线：主体是"参考图→视频"，七部全成立；没有任何一部用 dependency／assembly 这类语义边
③ enableSound 基本都 on（115／431／176／60／36；坠星读到的 15 条也全 on）
④ 视频都吃多张参考图（例外：放殃中位 1 张、坠星中位 0 张）
```

### 7.2 做法分成几派 —— 没有唯一标准（最要紧的一条）

```text
长段长词派   W1 弥寿计划 ｜ W2 抵达之前 ｜ W3 THE TURN
             mixed2video ＋ Seedance 2.5 ＋ 30 秒段 ＋ 3,242–6,215 字长提示词 ＋ 参考 4–8 张
短段短词派   放殃 ｜ 出走
             singleImage2video ＋ Kling 3.0／O1 ＋ 5–10 秒段 ＋ 18–37 字短提示词 ＋ 参考约 1 张
中间态       Wrong Room：mixed2video ＋ Seedance 2.0 VIP ＋ 15 秒段 ＋ 303 字提示词 ＋ text 规格 2,496 字
素材态       坠星 EP3：28 段里 13 段参数缺失、15 条 prompt 为空 —— 更像素材池，不是成品链
```

【库规】**用户指定 THE TURN 为"最标准的工作流程"，那是质量标准的选择，不是平台通则。**
七部里只有三部长段长词派彼此同构，另四部走的是别的路。**给新作品定做法之前必须先问"这部要学哪一派"，
不能默认把 THE TURN 的数值套上去**——这正是我前几轮反复犯的错（先套模板，再拿一个样本当通则）。

### 7.3 THE TURN 特有（不可套到别作）

```text
text 规格书层：W3 92 个 ｜ W2 5 ｜ W1 1 ｜ 出走 0 ｜ 放殃 7（全是上传的 text_resource）｜ Wrong Room 15
音频母带层   ：W3 36 ｜ W2 11 ｜ 坠星 3 ｜ Wrong Room 1 ｜ 出走 0 ｜ W1 0
合成／时间线 ：只有 W2 有 video-clip 33 个；THE TURN 为零
分组规模     ：W3 81 ｜ 放殃 49 ｜ W2 27 ｜ W1 19 ｜ 出走 5 ｜ Wrong Room 1
迭代链形态   ：出走／放殃="图生图链" ｜ W1="视频续接链"（video→video 112）｜ W2="时间线合成"
段长上限     ：W2 到 80 s（另有 60 s×13）｜ W3 到 40 s ｜ 放殃 6–15 s
参考上限     ：W3 30 张 ｜ W1 12 ｜ W2 9 ｜ Wrong Room 6 ｜ 放殃 4 → 各按素材量给，无统一上限
```

## 8 · 边界

```text
【已验证】本文所有数字均来自 2026-10-10 对该画布的全量回读（原始 JSON 存于项目工作目录）。
【未验证】"这是作者唯一的做法"——样本只有这一部作品；其余作品（弥寿计划/抵达之前/放殃/出走/
          坠星/Wrong Room）的画布形态差异很大，不能直接套用本文数值。
【推断】§5.3 的"写作顺序"由文件组织方式推得，作者本人未确认。
【推断】"12 段骨架"之类更细的提示词分段法在项目输出目录另有旧蒸馏，未经本轮复核，不并入本文。
【已验证】§7 的六张画布结构、以及 W1／W2／W3 的视频参数，均来自 2026-10-10 全量只读回读。
【已验证】七部的参数层都逐节点读过了：放殃 388、坠星 81、Wrong Room 137、《出走》280（全部非组节点），
            W1 118、W2 466（全部 video 节点），W3 581（全部节点）。原始 JSON 25 个 / 14 MB，均在项目工作目录。
【未验证】"哪一派更好"——本文只记录七部各自的做法，不做质量比较；用户认定 THE TURN 最标准，
            但七部里只有三部长段长词派同构，另外四部走的是别的路。
```

