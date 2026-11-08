# LibTV 脚本 V2 提交契约：镜头回写与两个 scene（【REA静态】）

**这一册是"写方向"：行 → 服务端镜头对象、载荷怎么拼、两个 scene 名与各自上限。**
读方向（服务端对象 → 13 列行）见 `libtv-script-rows.md`。**两半合起来才是完整的行契约。**
出处：`outputs/libtv_rea_20261014/57_脚本V2提交契约与镜头回写序列化.md`。

## 一、★★ 镜头回写序列化（逐字字段与省略规则）

```text
shot_id              ← id
shot_number          ← shotNumber
duration_seconds     ← durationSeconds
plot_description     ← plotDescription
plot_description_entity_refs  ← {text, asset_id}[]（空则整个键不写）
shot_size            ← shotSize
dialogue_lines       ← 每项 { character_ref?, kind?, text, entity_refs? }
cinematics           ← { shot_size?, camera_movement?, lighting? }（三项全空则整键不写）
scene_asset_ids      ← 非空才写
prop_asset_ids       ← 非空才写
lighting_and_atmosphere ← 非空才写
audio_effects           ← 非空才写
final_image_prompt_entity_refs  ← {text, asset_id}[]
final_video_prompt_entity_refs  ← {text, asset_id}[]
legacy_emotion_hint  ← emotion（trim 后非空才写）
```

**★ 三条**：
1. **`emotion` 是以 `legacy_emotion_hint` 发出去的**（名字里带 `legacy`）；
   运镜 / 光影走的是 **`cinematics`**；
2. **`characters` 数组不在这里**——角色靠**顶层 `assets`** ＋ `character_ref` / `*_asset_ids` 引用；
3. **空值一律"整键不写"** ⟹ **回写后回读看到字段缺失是正常态**，不是丢数据。

## 二、★★ 载荷构造：`shots` / `context_shots` / `assets` / `story_context` / `meta`

```text
shots          = 本次要处理的行，逐行按 §一 序列化（**必带**）
context_shots  = 节点上"不在本次行里"的那些行（按 id 差集）→ **最多 100 条**（非空才带）
assets         = { characters, scenes, props }（见 §四；有存活项才带）
story_context  = { original_story_text }（有才带）
meta           = { visual_style }（styleDescription trim 后非空才带）
```

**→ 判据**：**`context_shots` 是"给对方当上下文、本次不重算"的那批，上限 100**；
**原有文风走 `meta.visual_style`，原始故事文本走 `story_context.original_story_text`。**

## 三、★ 两个 `scene` 与各自上限

| 用途 | `scene` | 上限 / 报错 |
|---|---|---|
| **生成 / 整体重算** | **`script-generate-v2`** | — |
| **只重算分镜提示词** | **`script-recompute-prompts-v2`** | **0 行直接抛**；**> 20 行抛 `[scriptV2TaskBridge] recompute rows 超过上限：<n> > 20`** |

同模块导出常量 **`20`**（上限）。**两个闸都在客户端** ⟹ **批量重算必须自己分批**，别指望平台兜。

## 四、★ 资产过滤（发出去的不是原样）

**只保留**：`id` 非空串 · `name` trim 后非空 · **`status !== "lost"`**；
**重写为** `{id, role, name, description?, thumbnailUrl?}`（`role` 规范到 `character`/`scene`/`prop`；
后两个可选字段**只在是字符串时保留**）。
⟹ **标了 `lost` 的资产永远进不了载荷**，哪怕它还在画布上。

## 五、★ 参考图 `refId` 与列表重排

```text
imageList 先按 imageListOrder 重排 → 逐项 { ref_id: `src_img_${序号}`, node_id, url, display_name? }
videoList 按 videoListOrder 重排 · audioList 按 audioListOrder 重排
```

**→ 判据**：**顺序由 `*ListOrder` 决定，不由你传数组的先后决定**；
**`ref_id` 是按重排后序号现生成的**（`src_img_1`…）⟹ **不是稳定标识**，**稳定标识是 `node_id`**。

## 六、边界

1. 全部为客户端**只读静态**证据；**未提交任何文本任务**；
2. **服务端是否接受这些字段名与结构，未验证**；
3. **两个 `scene` 各自产出什么、是否计费，未验**；
4. 函数取自**多模块合并的 chunk**，本册只锚**函数体与字面量**，不锚压缩名。
