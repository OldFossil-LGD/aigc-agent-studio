# 标准工作流程 · **续册：可执行骨架与填空模板**（基准＝《THE TURN 回合》）

> **拆卷指针**：本册是 `standard-workflow-the-turn.md` 的续册，**原节号跨册连续，不重新编号**（§5–§6）。
> **主册**：`standard-workflow-the-turn.md`（**§0–§4 结构与差异 · §7 跨作品校验 · §8 边界**）。
> **何时读**：**要照着写**的时候——三份文本的分工 · 执行 prompt 的块清单 · 写作顺序 ·
> 三条绑定机制 · 可直接改用的填空模板 T1–T4。
> **⚠ 先读主册的 §7**：**七部实测分两派，没有唯一标准**——**给新作品定做法前先问"学哪一派"。**
> **证据**：与主册同源（2026-10-10 对该副本的全量只读回读；该画布 forbidden-write）。

---

## 5 · 可执行的骨架（照这个写）

### 5.1 三份文本的分工【已验证】

```text
① 全片合同 text（示例节点 WORLD_V2_完整剧本_人物边界_12条BROLL_总合同 / 19,256 字 / 96 节）
   # 片名｜版本｜主旨
     结构：8×30 秒 ／ 范围：C07–C14 ／ 状态：SCRIPT_PRIORITY_CANDIDATE_V3 ／ 本版核心修正：…
   ## 全局声音与场景规则      ← bullet 锁死：某空间只允许出现哪些声音；禁止 HUD／字幕／WORLD VOICE…
   # C07｜30S｜三方发展，中央盆地出现居民      ← 段标题自带时长
     00:00–00:03｜作战室 ／ 00:03–00:06｜游戏世界：蓝方 …   ← 时间码｜场地 的节拍表

② 段合同 text（示例 ROOM_V2_R03_完整剧本提示词 / 7,106 字 / 5 节 / 含 7 处 {{Node}}）
   # R03 完整剧本／B-roll设计
   # R03｜交易破裂与越界争执｜纯作战室30秒
     目的：<一句话，可英文>
   ## 精确对白        ← 逐字，说话人（EVAN／KAI／LENA）分行，作为硬锁
   ## 时间设计        ← 逐拍时间码
   # R03 完整提示词    ← 执行词正文（之后挂到 video 节点）

③ 设计规格书 text（3 份，序列级）
   # 标题 → ## Authority → ## Shot purpose → ## Audience and viewpoint → ## Causal spine →
   ## Scale and camera meaning → ## Spatial truth → ## Behavior and human stakes →
   ## Exit and next-shot handoff → ## Rejection test
```

### 5.2 执行 prompt 的块清单（179 条非空 prompt 里的出现次数）【已验证】

```text
必选四件
  ACTIVE ASSETS 头（151）｜@ImageN = {{Node <uuid>}} 清单（150，中位 5 行、最多 30 行）
  OUTPUT CONTRACT（138）｜秒级节拍 x.x–x.x（154）
高频块
  CAUSAL SPINE 107 ｜ AUDIO 76 ｜ ACCEPTANCE LOCKS 71 / ACCEPTANCE 56 ｜ TIMED ACTION 34
  ACTING AND REACTION 31 ｜ PHYSICS / PERSISTENCE 30 ｜ WORLD AND CONTINUITY LOCK 30
  FIRST FRAME AND SPATIAL BLOCKING 30 ｜ FORMAT AND CAMERA 30 ｜ DRAMATIC PURPOSE 28
  LIGHTING AND GRADE 27 ｜ CAMERA 25
按段型加挂
  对白段：LOCKED DIALOGUE — EXACT ORDER, ONCE EACH 22 ｜ SPEAKER / AUDIO HARD LOCK 22
  世界/播客段：NO WORLD CONTAMINATION 17 ｜ ROOM B-ROLL ONLY 17

四件套齐备率（ACTIVE ASSETS + @ImageN + OUTPUT CONTRACT + 秒级节拍）：
  133/179 = 74% 齐 ｜ 20 条缺 1 件 ｜ 26 条只含 ≤1 件（多为短句 prompt，不是段级执行词）
  单件齐备率：ACTIVE ASSETS 151（84%）· @ImageN 150（84%）· 秒级节拍 154（86%）· OUTPUT CONTRACT 138（77%）
  【推断】四件套是段级执行词的"合格线"，短句 prompt 属于另一类用法（B-roll 单动作）
```

### 5.3 写作顺序【推断】（顺序本身是我从文件组织推的，未经作者确认）

```text
1. 全片合同（结构／范围／状态／全局声音与场景规则 + 段级时间码表）
2. 逐段合同（目的 + 精确对白 + 时间设计）
3. 编译执行 prompt（五件套：ACTIVE ASSETS / @ImageN 清单 / OUTPUT CONTRACT / 节拍 / 禁令）
4. 资产生成（画布外）→ 上传 → 建 video 节点（mixed2video + Seedance 2.5 + 时长 + audioList）
5. 命名带版本与状态；人审单独成组；重试走 RETAKE／ATTEMPT，不覆盖旧版
```

### 5.4 三条绑定机制【已验证】

```text
① 参考挂载顺序：prompt 里的 @ImageN 编号顺序 = 节点的 imageList 顺序（逐一对应）
   139/149 完全一致，45 条无法判定（清单或实挂为空）
   10 条不一致的共同形态是「清单条数 < 实挂条数」：9/10、6/7、26/27、28/30、23/25、7/8 —— 漏写
   → 写作要求：@ImageN 按 left（imageList）顺序编号；漏写会留下无法审计的参考
   ⚠ 本轮我先用 UUID 字符串去比对象列表，得到"0 一致"的假结论，改比 nodeId 后才是 139/149

② 版本阶梯：只有主线迭代，其余一次成型
   多版本系列 7 个：C06_30S_RETAKE[4,5,7,8,9,10] ｜ END_MERGED[5,6,7,8,9] ｜ END_MAIN[12,14,15]
                   ｜ TAIL[5,6] ｜ WORLD[2,3] ｜ ROOM[2,3] ｜ POSTCREDIT_FULL[7,8]
   单版本系列 24 个（其余段落一次成型）
   → 版本号写在名字里，且"这一版改了什么"也写进名字（例：END_MERGED_V9_最新补充_尾AT处理）

③ 音频绑定：audio 是母带／台词轨级共享资源，不是逐段生成
   36 个 audio 中 16 个被引用、20 个零引用；单个 audio 最多挂到 47 个视频（另有 32、35）
   → 建图顺序：先做音频母带，再挂进相关 video 的 audioList（0–4 条）
```

## 6 · 填空模板（从上面的骨架抽出来，可直接改用）

> 用法：先填 T1（全片），再逐段填 T2，最后把 T2 的末节写成 T3。
> 方括号 `<…>` 是槽位；`←` 后面是本模板那一行的实测依据。

### T1 · 全片合同（text 节点正文）

```text
# <片名>｜<版本>｜<一句话主旨>                      ← 实测最长一篇以此开头
结构：<N>×<段长> 秒                                  ← "结构：8×30 秒"
范围：<段编号区间>                                   ← "范围：C07–C14"
状态：<SCRIPT_PRIORITY_CANDIDATE_Vn>                 ← 版本状态写进头部
本版核心修正：<这一版改了/删了什么>                   ← 实测每版都写

## 全局声音与场景规则
- <空间A> 只允许出现：<对白／呼吸／衣料／椅子／HVAC／真实空间反射…>
- <空间A> 不出现：<WORLD VOICE／系统提示音／回合播报／HUD／全息地图／发光线路／字幕／科技文字…>
- <世界声音层> 只能出现在 <空间B> 画面里；它不解释动机、情绪或道德，只确认已发生的客观状态
- <每一处技术部署必须先被看见实际启动，世界才能说 deployed>
- <主要角色的身体／脸／年龄／发型／服装只能出现在 <空间A> 内>

# <段编号>｜<段长>S｜<这一段的功能一句话>            ← 段标题自带时长
00:00–00:03｜<场地A>                                ← 时间码｜场地 的节拍表
00:03–00:06｜<场地B：<势力>>
…
```

### T2 · 段合同（text 节点正文）

```text
# <段编号> 完整剧本／B-roll设计
# <段编号>｜<段功能>｜<场地>｜<段长>秒
目的：<一句话，可中文可英文>                          ← 实测样例为一句英文

## 精确对白                                        ← 逐字，说话人分行，当作硬锁
**<说话人A>**

<逐字台词>

**<说话人B>**

<逐字台词>

## 时间设计                                        ← 逐拍时间码
- <时间码>｜<这一拍发生什么>

# <段编号> 完整提示词                               ← 末节即 T3 的正文
```

### T3 · 执行 prompt（挂到 video 节点的 params.prompt）

```text
ACTIVE ASSETS — <段名>, EXACT ORDER                  ← 151/179 的写法
  （另一变体：ACTIVE ASSETS — ATTACH IN THIS ORDER ONLY，41 次；功能相同）
@Image1 = {{Node <uuid>}} — <这张图只锁什么>
@Image2 = {{Node <uuid>}} — <…>
…                                                     ← 中位 5 行，最多 30 行；顺序必须等于 imageList 顺序
Assets lock topology, materials, vehicle class and scale — not action, framing or endpoint state.
                                                      ← 明确"参考锁什么、不锁什么"

OUTPUT CONTRACT                                       ← 138/179
<X.X>s, 21:9, <480p／…>, 24fps. <N> <cuts 类型>.      ← 141 条写 21:9、142 条写 24fps

DRAMATIC PURPOSE                                      ← 28
CAUSAL SPINE                                          ← 107
FIRST FRAME AND SPATIAL BLOCKING                       ← 30
TIMED ACTION                                          ← 34；正文用 0.0–2.0／2.0–4.0 逐拍
CAMERA ／ FORMAT AND CAMERA                            ← 25 ／ 30
LIGHTING AND GRADE                                     ← 27
PHYSICS / PERSISTENCE ／ PHYSICS AND MATERIAL RESPONSE ← 30 ／ 30
ACTING AND REACTION                                    ← 31
WORLD AND CONTINUITY LOCK                              ← 30
AUDIO ／ WORLD VOICE / AUDIO                           ← 76 ／ 18
  对白段再加：LOCKED DIALOGUE — EXACT ORDER, ONCE EACH（22）＋ SPEAKER / AUDIO HARD LOCK（22）
  世界段再加：NO WORLD CONTAMINATION（17）＋ ROOM B-ROLL ONLY（17）
ACCEPTANCE LOCKS ／ ACCEPTANCE                         ← 71 ／ 56
<硬禁令：ABSOLUTE ZERO VISIBLE PEOPLE／不出现 UI·字幕·logo·水印…>   ← 43/179 写硬禁令
```

### T4 · 建节点与命名（对应 §2.4／§2.5）

```text
video 节点：mixed2video + Seedance 2.5 + duration=<段长> + enableSound=on
            imageList=按 @ImageN 顺序挂（≤30）＋ audioList=<母带 0–4 条>
节点名：<段编号>_<时间码>_<语义名>_<段长>S_<版本>_<状态>      ← 名字里的秒数应与 settings.duration 一致（104/108）
组名：  每段一个组（1 text + 1 video）；资产另组 TT_ASSET_*；人审另组（用户确认／用户锁定）
重试：  不覆盖旧版，新开 RETAKE／ATTEMPT 命名，并在名字里写"改了什么"
```
