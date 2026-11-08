# 成片反推 Runbook · **续册：实体层与逐镜资产映射**

> **拆卷指针**：本册是 `film-reverse-runbook.md` 的续册，**原节号跨册连续，不重新编号**（§7）。
> **主册**：`film-reverse-runbook.md`（**§0–§6：能力现状 / 三步法 / 交付格式 / 统一图语法 / 复现命令 / 端到端演练**）。
> **何时读**：**镜头表已经有了，要把它变成"可执行、过门禁的图计划"**时——
> 实体表怎么产出 · 逐镜资产映射怎么剪掉假边 · 字幕带怎么抽 ·
> 剪枝后为什么要重建提示词包 · 参考图 7 张上限怎么裁 · 建节点顺序的坑。
> **读完回哪**：`production-compiler.md` · `source-fidelity-mode.md` · `libtv-op-manual.md`。

---

## 7. ⭐ 实体层与逐镜资产映射（2026-10-09 新增，补掉编译器的两个硬伤）

### 7.1 ⛔ 编译器的实体是**硬编码关键词**，不是抽取

`compile_text_input.py` 只有一张 8 词表：

```text
main_character  ← 旅人 / 男人 / 女人 / 孩子 / 阿婆 / 孙子
primary_scene   ← 房间 / 酒店 / 旅馆 / 走廊 / 村寨 / 梯田
primary_prop    ← 行李箱 / 行李 / 杯子 / 证件 / 风筝 / 门 / 钥匙
```

**反推任意一部新片时，它只会给出这 3 个占位实体。**（实测：WrongRoom 17 镜只得到
`main_character` / `primary_scene` / `primary_prop`。）

→ **反推必须自己产出实体表**，走 JSON 契约（不是 `.md`）：
`entities: [{id, kind, reuse_count, state_versions}]`，`shots[]` 逐条带 `description`。

### 7.2 ⛔ 编译器把每个资产连到**全部镜头**（全交叉积）

实测（17 镜演练）：`main_character__asset_refine_b` / `primary_scene__asset_refine_b` /
`primary_prop__asset_refine_b` **各连 17 个镜头** = 3×17 全交叉积。
画布上那个「135 = 3 资产 × 45 镜头」就是它来的。

**而反推最独特的价值恰恰在这里**：读片就知道"哪个资产出现在哪一镜"。

```powershell
python scripts/prune_asset_links.py <production_out>\03_shot_graph_plan.json `
  --map <shot_assets>.json --out <production_out>\03_pruned.json
```

`shot_assets.json` 形如 `{"shot_03": ["traveler","suitcase"], "shot_13": []}`（黑场就是空）。

**实测（17 镜 / 7 实体）**：跨积边 388 → 284，**删掉 104 条假边**；随后
`compile_graph_plan` → `make_graph_overlay` → `graph_plan_lint`：

```text
graph_plan.structure   exit=0  pass
graph_plan.reference   exit=0  pass
graph_plan.media       exit=3  not_verified
graph_plan.cost        exit=5  not_applicable
```

### 7.3 反推产出的完整形状（做到这里才算够）

```text
① 镜头表（时间码来自印相 + 原始帧核对）
② 实体表（真实角色 / 场景 / 道具，不是 8 词表命中）
③ 逐镜资产映射 shot_assets.json（哪个资产出现在哪一镜）
④ 字幕 / 台词轨（成片有字幕时必须单独抽；见待补项）
```

### 7.4 ⭐ 字幕 / 台词轨（2026-10-09 新增，已验证可用）

1 秒间隔的整帧印相会落在字幕不显示的帧上。新的字幕带工具只裁**画面底部 16%**、
密集抽样、竖排烧时间码：

```powershell
python scripts/subtitle_bands.py <视频> --out <outdir>\subs --start 170 --end 210 --interval 1.0
```

**实测（WrongRoom 170–193s）**：03:08–03:10 完整读出双语字幕
`"You should not enter this room" / 你不应该进这个房间`。

⭐ 同一轮还抓到 **02:50–02:51 的洋红/黄绿闪帧**（转场特效）——这类瞬时帧
1 秒整帧印相会漏，只有密集抽样（`--interval 0.5`）或字幕带才看得到。

### 7.5 ⛔ 剪枝之后必须用**剪枝图**重建提示词包（2026-10-10 实测，原来漏了这一步）

一键入口 `compile_production.py` 的提示词包是从**未剪枝**的图生成的。剪枝把
假边删掉之后，prompt 里仍列着被删掉的节点 —— 平台一律拒建：

```text
{{Node "laotaitai_asset_refine_b"}}：找不到名称为「…」的节点
{{Node "paodao_richu_asset_anchor"}}：名称为「…」的节点未连接到当前节点（无引用线）
```

修法（《出走》116 镜实测通过）：

```powershell
python scripts/compile_prompt_packages.py out\01_production_contract.json `
       out\02_asset_graph_plan.json out\03_pruned.json --out out\04_pruned_prompts.jsonl
python scripts/compile_libtv_commands.py out\03_pruned.json `
       --prompts out\04_pruned_prompts.jsonl --out out\08_commands.json
```

实测：`shot_001_candidate_image_A` 的占位符由 42 条降到 7 条，与 `left` 完全一致。
⛔ 注意 `compile_libtv_commands.py` 里那条 `_sanitize_refs` 只处理 `__`→`_`，
它不会帮你删引用；**引用集是 `left` 决定的，prompt 必须跟着 `left` 重建。**

### 7.6 ⛔ image2image 参考图上限 = 7 张（2026-10-10 新测到的平台硬限制）

```text
参数校验失败：图片/图参考/参考图数量上限：当前模型最多 0~7 张
```

反推里"5 资产 + 3 镜头级引用"就会到 8 条，直接建不出来（实测命中 3 个候选图节点）。
确定性裁法：**资产优先（character > scene > prop），再 scene_ref > composition_ref >
identity_ref**，砍到 7 条。工具：`scripts/cap_image_refs.py`。

⚠ 参考位次 = 建节点时 `left` 数组顺序（见 `20_LibTV图构建与分组规范.md` §2.1），
所以裁剪必须在**生成命令之前**做，不能事后重排。

### 7.7 ⚠ `apply_libtv_plan.py` 的建节点顺序 ≠ 依赖顺序

资产链的唯一上游是 `global_asset_manifest`，而它在计划里排得很后；
Kahn 分轮次时"零依赖"的 116 个镜组节点整批排到了资产链前面。
结果：建图能成，但**报错点会落在很后面**（《出走》是第 103 镜才炸，前面 1073 个节点已经建完）。
→ 建图前把 manifest 一类全局上游提到计划最前，或按 role 分波次建。

### 7.8 仍待补

`graph_plan.media`：需真建图后 `read_node` 回读才能从 `not_verified` 转正。

其他已知偏差（《出走》实测，尚未修）：

```text
① video 节点 settings.duration 由编译器统一给 5 秒，不等于实测镜头时长
   （《出走》实测 0.10–12.13 s）→ 建结构无影响，真生成前必须逐镜改回。
② 每镜的 assembly 落成 video 节点（mixed2video/videoEdit2video），
   而 20_ 规范 §6 主张"合成位用 video-clip"；本图只有 global_final_composite 是 video-clip。
③ image2image 的镜头级 refs（scene_ref/identity_ref/composition_ref/state_ref）
   在编译器图里**没有入边**（是声明式占位），被平台当成纯 text2image 节点建出来。
```

