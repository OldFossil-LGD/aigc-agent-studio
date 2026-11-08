# LibTV CLI 管道体系（NDJSON · 嵌套 DAG · 旁路与抑制）

> **来源**：官方 `libtv-cli/examples/pipes/README.md`、`examples/pipes/nested-dag.md`、`examples/pipes/error-handling.md`（**一手 · 2026-10-15 读**）。
> **为什么单列**：`libtv-op-checklist.md` 已 294 行（警戒区），而管道体系本身含**四项独立手法**（旁路节点 / stdout 抑制 / 已有节点回放 / 嵌套决策表），此前本库只有零散一条。本册只收**组织与手法**；管道的中断纪律见 `libtv-cli-env-binding.md` 的「管道纪律」节。
> **读完回哪**：`libtv-op-checklist.md`（CLI 执行层）· `libtv-canvas-nodes.md`（节点全书）。

---

## 一、核心约定：NDJSON 就是"节点引用流"

| 角色 | 约定 |
|---|---|
| **上游** | **接到管道（非交互终端）时**，成功输出为**一行一个 JSON 对象**；多节点写操作 → **多行**。**只有接管道时才保证是单行 JSON**——不接管道时是常规格式化 JSON。 |
| **下游** | 从 `stdin` **按行解析 JSON**，取每行的 **`nodeKey` 或 `newNodeKey`** 作上游引用——**语义等价 `--left`，默认接到 `<node>` 的左侧入边**。 |
| **stdout / stderr 分工** | **stdout ＝ 业务结果 JSON/NDJSON**；**stderr ＝ 进度、上传百分比、生成轮询**，常见前缀 **`[run]` / `[run-group]` / `[upload]` / `[storyboard image-run]`**。 |
| **stdin 与 `-p`/`-g` 的关系** | **stdin 里的 key 不覆盖 `-p` / `-g`**——当前项目 / 分组仍由 `.libtv/project.json`（`project use` / `group use`）或命令行 `-p` / `-g` 决定。 |

## 二、★ 四项手法（本册核心）

**① 已有节点"回放"——不重建、只引用**
`libtv node "<名字>"`（**不传写参数**）**只查询**并吐**一行 NDJSON** ⟹ 用来在管道后段**再次引用**早先建好的节点。
**→ 纪律：某个上游被多个下游复用（如"主KV"）时，先 `create` 好，后面用 `libtv node "主KV" | …` 反复引用——不要重复建。**

**② 旁路节点——建在画布上，但不进下游**
把某节点用 `&&` 接在主管道**之后**、**但放在外层 `(` 括号之外**，它的 NDJSON 就**不会**流到外层下游。
**→ 适用：建了要留在画布、但不挂给此下游的资源节点**（官方例子：旁路一条 `audio` 氛围乐）。

**③ stdout 抑制 `>/dev/null`——掐掉某一支**
在 `create` 结尾加 **`>/dev/null`** 丢弃它自己的 NDJSON。
**→ 两种用途**：**终点节点**（本来没人读它的 stdout）；**不让这一支混进外层管道的 stdin**（官方例子：抑制 `Seed段`，避免 `完片F` 误把它当左侧输入）。

**④ 顺序即语义——"最后一行"决定最后一个引用**
`( … ) && libtv node "主KV"` 让主 KV 的 NDJSON 作**最后一行**喂给下游 ⟹ 官方例子里 `完片F` 的左侧是「拼图D + Kling段 + 主KV」，**不是**「… + Seed段」。
**→ 纪律：管道里的节点顺序 ＝ 左侧引用顺序，改顺序就是改引用关系。**

## 三、什么时候嵌套、什么时候拆脚本

| 场景 | 建议 |
|---|---|
| 上游输出恰好就是下游 `--left` 来源，**且只用一次** | **直接管道嵌套**，最紧凑 |
| 某上游**被多个下游复用** | **先 `create` 好，再 `libtv node "<名>" \| …` 反复引用**，不要重复建 |
| 链路**跨越多个 `set -e` 生命周期**（中间要人工检查再继续） | **拆成两条脚本或分段执行**——长嵌套中途失败难排错 |
| 想要**真并发**加速 | **绝不并行写同一条管道**（会撞 NDJSON）；**各自写临时文件再顺序合并** |

## 四、三条硬纪律（与 `libtv-cli-env-binding.md` 的「管道纪律」节互补）

1. **`set -euo pipefail` 起手**——少 `pipefail` 会让管道某段失败被右端成功掩盖；
2. **逐层串联一律 `&&`**（不用 `;`）；
3. **`&` 与管道互斥**——多进程同写一条管道会把一行 JSON 的字节穿插进去，下游按行解析直接炸（`invalid json on line N`）。

## 五、官方真实骨架（含旁路与抑制，可直接改）

结构：**多张图 → 拼图D → 旁路 audio → Kling段 / Seed段 → 完片F**

```bash
set -euo pipefail
(
  (
    ( create "选题" && create "辅视" && create "主KV" ) | create "拼图D"
  ) && create "氛围乐" -t audio      # 旁路：在括号外，不进 F
) && (
  ( node "选题" && node "主KV" ) | create "Kling段"
) && (
  node "主KV" | create "Seed段" >/dev/null    # 抑制：不让 Seed 段混进 F
) && node "主KV"                      # 最后一行成为 F 的第三个左侧输入
) | create "完片F" >/dev/null
```

**结果自检（官方给法）**：`libtv project | jq '.nodes | length'`（该例子期望 ≥8 个节点）。

## 六、可复用的三层心智模型

1. **流层**：stdout/NDJSON 是"引用流"，不是"日志流"——日志在 stderr；
2. **结构层**：`( … )` 决定"哪些输入汇聚到哪个下游"，`&&` 决定"顺序"，`>/dev/null` 决定"哪一支不外流"；
3. **状态层**：**项目与分组的归属不由管道决定**（`-p`/`-g` 或目录绑定决定），管道**只解决"谁引用谁"**。

---

## 七、组内管道与 `{}` vs `()`（**官方 `examples/pipes/group-and-node.md` · 一手 · 2026-10-15 读**）

### 1. 组内批量建节点：**不写 `-g` 就在组内**

```bash
libtv group create 首集分镜
libtv group use 首集分镜          # 写入 groupNodeKey

( node create "大纲" && node create "角-三视图" && node create "角-服饰" ) \
  | node create "角-汇总" -t image --set modeType=image2image
```

- **所有 `node create` 都不写 `-g`**——既然已 `group use`，**默认就落在该组内**；
- `( a && b && c ) | d` **等价于 `d --left a --left b --left c`**（三个上游的 NDJSON 一并喂给下游）；
- **`group create` 的 stdout 接管道时吐 NDJSON（含 `newNodeKey`），不接管道时是普通 JSON**。

### 2. ★ 临时跳出当前组（本册此前未记）

分组绑定会**静默收窄**后续 `libtv node` 的作用域。要**只绑项目、不进组**：

- 单次命令加 **`-g ""`**（空串）；
- 或**改用 `-p <画布UUID>` 且不带 `-g`**；
- 或干脆 **`libtv group unuse`** 解除绑定（**`libtv project unuse` 则解项目绑定**）。

### 3. 把"已在画布上但没进组"的节点收编

```bash
libtv group 首集分镜 --node 镜头A --node 镜头B --node 镜头C   # 一次性收编
libtv group 首集分镜                                          # 无 --node ＝ 查询组内子节点
libtv group 首集分镜 --run                                    # 整组触发（每个子节点各跑一次）
```

### 4. ★★ `{}` 与 `()` 的语义差（最容易被忽略的一条）

| 形态 | 含义 | 该用在哪 |
|---|---|---|
| **`( a && b && c ) \| d`** | **a 成功才跑 b**，逐条串联 | **凡涉及 `create` 这类有副作用的写操作** |
| **`{ a; b; c; } \| d`** | **不要求前一条成功再跑下一条** | **"都是已存在节点的查询"**（只读场景失败概率低） |

**→ 纪律：写操作一律用 `&&`；`{}` 只留给纯查询。**

### 5. 官方「组内素材 + 新建节点 → 终剪」骨架

```bash
{ node "镜-01"; node "镜-02"; node "镜-03"
  node create "BGM" -t audio --set instrumental=1 ; } \
  | node create "终剪" -t video-clip >/dev/null
```

- 这里 `{}` 之所以可用：`node "镜-0N"` 是**只读查询**；
- **`终剪` 的 `>/dev/null` 丢掉自己的 NDJSON**——**它是终点，没有下游再消费**。
