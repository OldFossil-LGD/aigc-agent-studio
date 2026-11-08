# 短入口指引：工艺消费与本镜时间作用域

> 可达入口：`SKILL.md`（阶段一交付段）与 `references/production-compiler.md` §2.5 均链接本文件。
> 本文件只给**接口与校验单位**，不重写知识册条款；知识册原条款仍以各自文件为准。

## 适用范围
- 阶段一 `prompt_only` 交付：`intent-handoff/v1` → `prompt-package/v1` → `<out>/13_Final_Prompt.md`。
- 任意镜头级工艺（performance / action_feedback / continuity_state / transition / style_detail / sound_craft / motion_path / style_notes）必须进入对应候选的正本块与最终 Markdown 段。
- 权威源仍是单一 `intent-handoff/v1`；用户不手填 JSON；不做通用自然语言解析。

## 知识来源（按需读取，不伪造条款）
按镜头需要读取下列知识册的**适用原条款及例外**；本文件不复制其内容：

| 知识册路径 | 用途 | 映射到 |
|---|---|---|
| `references/direction-reasoning.md` | 导演推理与镜头任务 | 本镜目的/过渡压力 |
| `references/asset-prompt-spec.md` | 资产字段与下游继承 | 正本块（visual/composition 等） |
| `references/shot-craft.md` | 分镜结构、块写法、拆镜 | 正本块（duration/action/camera） |
| `references/stylized-look-craft.md` | 工艺渲染（定格/木刻/水彩等） | style_detail → 正本块/最终行 |
| `references/sound-craft.md` | 声音设计与混音 | sound_craft → 对应镜头声音块 |

提交映射时必须给出：`知识册路径 / 节 / 来源 SHA → 本镜具体决定 → 正本块或最终行`。不得伪造条款；不得改原书/治理/风格目录。

包内成对样例 → `samples/craft_pairs/`：先读冻结 brief，再对照 `intents/` 与 `knowledge_decisions.json`。在 skill 根目录运行 `python samples/craft_pairs/reproduce.py --out <输出目录>`，十份输入均经 `compile_intent_delivery.py` 派生正本与最终正文；样例记录不代替实际消费检查，也不证明媒体效果。样例中的时长、位置与动作只适用于各自 brief。

## 本镜时间作用域（非全局）
- 全片时长（如 17 秒）是**全片**决定，只在全片/总览表面与 settings 中核对。
- 镜头时长、生成时长、裁切区间是**本镜**控制值，按 `shot_id` / `node_id` 绑定；不得跨镜借用。
- 声音局部时序（如滴答余响、雨声窗口）只在**该镜声音消费域**处理；其秒数不得与全片时长混比，也不得被其他镜头借用。
- P4 的时钟/雨窗/2 秒仅是**当前样例**，不是通用规则。

## 校验单位
1. 逐实际候选（`video_candidate` / `candidate_image`），不聚合。
2. 逐正本块（`prompt-package/v1` 的 `blocks`），不以任一表面背书。
3. 逐最终 Markdown 段（`## <node_id>`），不拼接全文。
4. 逐本镜时长/声序，不使用全局数值豁免。

## 拒绝条件
- 错总时长、错本镜时长、漏候选、漏最终段工艺：FAIL 或 UNVERIFIED。
- 跨镜借用合法数字、待验包自证：FAIL。
- source/audit 元数据进入提示词正文：FAIL。
- 未知约束、零判定：不得报 PASS。
