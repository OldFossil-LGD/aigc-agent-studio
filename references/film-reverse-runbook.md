# 成片反推 Runbook（2026-10-09 实测校准）

> **何时读**：用户给一部**成片**（mp4/链接），要求"反推"成生产画布时。
> 本文只讲"成片 → 镜头表"这第一步**怎么做才可信**，后续建图引用
> `production-compiler.md` 与 `source-fidelity-mode.md`。

## 0. 能力现状（先看这段，别高估工具）

**已验工具**：`cv2` 5.0 / `av` 19.0 / `imageio_ffmpeg` 0.6（自带 ffmpeg 可执行）。
本机 **PATH 里没有 ffmpeg/ffprobe**，要用就取
`imageio_ffmpeg.get_ffmpeg_exe()`。

**⚠️ 关键教训（WrongRoom 成片实测，224.17s / 30fps / 6725 帧）**：

| 方法 | 得到"切点"数 |
|---|---|
| OpenCV 帧差（全局 median+MAD） | 76 |
| OpenCV + 局部自适应窗口 | 77 |
| ffmpeg `scene>0.2` | 107 |
| ffmpeg `scene>0.3` | 54 |
| ffmpeg `scene>0.4` | 21 |
| 人工逐秒读片（该片交付版镜头表） | **44** |

**双算法只有 26 条互相吻合。** 且 172–207s 出现一个 35 秒"长镜"——
调出帧一看是**10 个不同镜头**（视觉已验证）：
该段亮度低至 0（黑场/淡变），且 175.3–175.8s 是**持续高帧差**（连续快切），
被"尖峰过滤"整串滤掉。

⛔ **结论：自动切点检测只能当提示，不能当结论。**
人工镜头表（场景级）与自动检测（镜头级）在**粒度**上本就不同——不要拿一个去否定另一个。

### 0.1 ⛔ 「人工逐秒读片」也不是可靠的时间基准（2026-10-09 定点核实）

那份 44 切点的人工镜头表**本身带时间漂移**。用原始帧定点核对（左右并排，非印相目测）：

```text
t = 22.0s  原始帧 = 手拿房卡在门前（刷卡）
t = 27.0s  原始帧 = 已进入房间、扶着外套

人工镜头表的写法：
  镜头5（25–30s）房门前刷卡
  镜头6（30–35s）进入房间，放下行李
  镜头7（35–40s）房间内整理衣物与外套
→ 三条都晚了约 5–8 秒。
```

**→ 时间的唯一可信来源是「烧了时间码的接触印相」与 `probe.json`；**
任何手写/口述的秒数都要用这两样回验，不要直接采信。

## 1. 三步法（提示 → 交叉 → 看片）

### 第 1 步 · 机器探测（要体积事实 + 切点候选）

```powershell
python scripts/reverse_shotlist.py <视频或URL> --out <outdir>
```

产出 `<outdir>/probe.json`（fps / 帧数 / 时长）/ `<outdir>/shotlist.json` / `<outdir>/shotlist.md` /
`frames/shot_XXX.jpg`（每镜一张静帧）。

### 第 2 步 · 双算法交叉（标出争议点）

```powershell
python scripts/consensus_cuts.py <视频> --shots <outdir>\shotlist.json --out <outdir>\consensus --scene 0.30
```

产出 `consensus.json`（confirmed / cv2_only / ffmpeg_only）+
`disputed_sheet.jpg`（争议点前后帧三联）。

### 第 3 步 ⭐ · 看片定稿（**唯一权威**）

```powershell
python scripts/film_contact_sheets.py <视频> --out <outdir>\sheets --interval 1.0
```

每张 5×4=20 帧、**每帧左上角烧时间码**。逐张读，写镜头表。
**密集段（快切/黑场/淡变）改用 `--interval 0.5` 或 `--start/--end` 局部加密。**

⭐ 这一步对应旧方法里的"逐秒抽帧"，是整个流程里**唯一可信**的依据。

## 2. 镜头表交付格式

```text
镜号 | 入点 | 出点 | 时长 | 画面描述（写了什么、机位、运动、光）
```

写完先跑 `scripts/shotlist_lint.py` 再往下走。

## 3. 之后（不是本文范围，但必须接上）

```text
镜头表 → compile_production.py → 生产契约/资产图/镜头图/提示词包/门禁/命令计划
       → apply_libtv_plan.py（只建结构，永不 --run）
```

红线：**不点火、不生成、不上传、不导出**；建图顺序与"谁连谁"按
`references/libtv-op-manual.md`（引用即连边、`{{Node ...}}` 双写）。

### ⚠️ 权威规范不在这里，在 `outputs/统一基准/`（2026-10-07 A/C 路契约）

反推出来的图**必须编译成那套图语义**，不要另造：

| 文件 | 管什么 |
|---|---|
| `outputs/统一基准/02_图语法_节点边分组参数.md` | **9 个节点 role**（`source/asset/storyboard/shot/audio/composite/qa/archive/group`）· **4 类边**（`reference/dependency/assembly/lineage`）· 每类边**是否携带顺序** · 10 条图不变量 |
| `outputs/统一基准/20_LibTV图构建与分组规范.md` | 落到平台的映射：`nodeType` 6 档、`storyboard`→`image`、`audio` 必带 `params.scene`；**`reference`→`left`+`{{node_key}}`、`assembly`→`video-clip` 的 left 顺序、`dependency`/`lineage` 不落边**；参考位次＝**建节点时 `left` 数组顺序，事后不可重排** |
| `outputs/统一基准/22_结构回读与媒体验收规范.md` | 建完怎么回读验收 |
| `outputs/统一基准/23_三作与合成场景回归测试.md` | 三作基线回归 |

⛔ 三条禁止（A §2 / C §1.2）：**用边表达 group 归属 / 用边代替 timeline /
用边代替 prompt 插桩**——都属错误建图。

## 4. ⭐ 镜头表 → 统一图语法（2026-10-09 新增，实测已通过）

编译器（`compile_shot_graph.py`）用的是**自造角色**（`asset_refine` / `candidate_image` /
`selection` / `assembly` …），**不能直接过统一基准的图门禁**（实测直接喂进去：
`structure FAIL 1155` / `reference FAIL 730`）。

新增适配器 `scripts/compile_graph_plan.py`，把它的产物映射成 A 路图语义：

| 映射 | 规则 |
|---|---|
| role | `asset_anchor`/`asset_refine`/`*_ref`/`candidate_image`/`refined_image` → `asset`；`storyboard` → `storyboard`；`prompt`/`selection`/`*_manifest`/`*_ledger` → `source`；`video_candidate` → `shot`；`audio` → `audio`；`assembly`/`final_composite` → `composite`；`qa` → `qa` |
| 边 kind | 指向 `composite` 的 → `assembly`；**text→text → `dependency`（按契约不落平台边，顺带消除真画布里不存在的 text 边）**；其余 → `reference` |
| order | 同一目标的引用/装配边按原计划边序 **0,1,2…** 递增（否则 `REF_ORDER_DUP`） |
| group_role | 每个节点必须带，且与所属组一致（否则 `STRUCT_GROUP_ROLE_MISMATCH`，实测一次命中 553 条） |

```powershell
python scripts/compile_graph_plan.py <production_out>\03_shot_graph_plan.json `
  --out <production_out>\graph_plan.json --project-id <UUID> --profile generic
python scripts/graph_plan_lint.py gate --plan <production_out>\graph_plan.json `
  --out <production_out>\graph_gate.json
```

**实测（WrongRoom 553 节点 / 730 边；边 kind：reference 459 / assembly 180 / dependency 91）**：

```text
graph_plan.structure   exit 0  pass            ← 由 1155 FAIL 降到 0
graph_plan.reference   exit 3  not_verified    ← 离线验不了，需平台回读
graph_plan.media       exit 3  not_verified    ← 同上
graph_plan.cost        exit 5  not_applicable
```

⛔ **exit 3 ≠ 通过**：结构过了；引用位次与媒体有效性必须等建图后回读才算验到。

### 4.2 补 overlay：把 `reference` 从"没验到"推到"通过"（2026-10-09）

`graph_plan.reference` 里有一项 `check_derived`，**没有 `--overlay` 就只出「没验到」**。
overlay 只能填**事实**，不能编：

```powershell
python scripts/make_graph_overlay.py <production_out>\08_libtv_command_plan.json `
  --out <production_out>\overlay.json
python scripts/graph_plan_lint.py gate --plan <production_out>\graph_plan.json `
  --overlay <production_out>\overlay.json --out <production_out>\graph_gate_ov.json
```

`make_graph_overlay.py` 只从命令计划里取三样：`operation="create"`、
每节点 `model`/`modeType`、**扁平** `settings`；`media_ready` **故意留空**——
还没生成过任何产物，媒体验收必须保持"没验到"，不许填假。

**实测（演练 17 镜计划）**：

```text
graph_plan.structure   exit=0  pass
graph_plan.reference   exit=0  pass          ← 由 exit=3 变通过
graph_plan.media       exit=3  not_verified  ← 诚实：未生成
graph_plan.cost        exit=5  not_applicable
```

⛔ 剩下的 `media` 只能靠**真建图 + read_node 回读**转正；`cost` 需要平台单价与预算上限，
不得自行编价。

## 5. 复现命令（WrongRoom 校准样本）

```powershell
python scripts/reverse_shotlist.py "https://libtv-res.liblib.art/upload-images/a379033239b44269ae4bf0ec96dc6773/ff000753fe9f6433bf48f82bde4e1804cc65a596.mp4" --out work\reverse_test_wrongroom
python scripts/consensus_cuts.py work\reverse_test_wrongroom\<file>.mp4 --shots work\reverse_test_wrongroom\shotlist.json --out work\reverse_test_wrongroom\consensus
python scripts/film_contact_sheets.py work\reverse_test_wrongroom\<file>.mp4 --out work\reverse_test_wrongroom\sheets --interval 1.0
```

## 6. ⭐ 端到端演练结果（2026-10-09 · 用自己的读数，不用继承的人工表）

取 WrongRoom 成片 **0–59 秒**，从印相读片自写一份 17 镜镜头表（时间码来自印相 + 原始帧定点核对），
再跑完整链：

```text
1) compile_production            → status PASS（shot_role_coverage / asset_iteration /
                                    link_downstream / prompt_packages / no_ignition 全 true）
2) compile_graph_plan            → nodes 217 / edges 282
                                    边 kind：reference 179 / assembly 68 / dependency 35
                                    角色：asset 111 / source 36 / composite 18 /
                                          shot 17 / storyboard 17 / audio 17 / qa 1
3) graph_plan_lint gate          → structure exit=0 pass
                                    reference exit=3 not_verified
                                    media     exit=3 not_verified
                                    cost      exit=5 not_applicable
```

⭐ 这一步证明的是：**"我从印相读出来的镜头表"可以一路走到结构合规的图计划**，
不需要继承任何人工成果。⛔ 仍不等于建图验收（`not_verified` 那两项要建图后回读）。

**本次演练顺带抓到的、旧人工表漏掉/写错的东西**：

```text
① 42.0–46.x 秒有约 4.5 秒纯黑场 —— 旧人工镜头表完全没有这一条（ffmpeg 独立解码复验，
   t=42.0/42.5/44.0/46.0 三通道均值为 0.00，t=41.0=28.20、t=46.5=56.90）。
② 旧表的秒数是"估"的且累积漂移：t=22.0 才是刷卡、t=27.0 已在房内扶外套，
   而旧表把刷卡写在 25–30s、进房写在 30–35s。
```


---

> **拆卷指针**：**§7（实体层与逐镜资产映射，含 §7.1–§7.8）已按职责移入 `film-reverse-runbook-part2.md`**（续册）。
> **原节号跨册连续，不重新编号**——本册保留 §0–§6。
> **★ 分工：本册回答"怎么反推出一张可信的镜头表"；续册回答"这张表怎么变成可执行的图"。**
