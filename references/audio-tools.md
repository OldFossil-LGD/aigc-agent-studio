# 音频工具与授权：**用哪个、能不能商用、怎么落地**

> **何时读**：要选音乐/音效的生成工具、要判断能不能商用、或要用命令行批量处理音频时。
> **读完回哪**：回 `sound-craft.md`（工作流）；音乐怎么写描述见 `music-craft.md` §6。
> **★ 时效声明（重要）**：本册的**版本号、定价、额度、授权条款、诉讼状态均变动很快**——
> 表里的是 **2026-09 多来源快照**。**下单前必须自己复核当期条款**（这正是本库"数字必回一手源"的纪律）。

---

## §1 生成式音乐：工具矩阵（2026-09 快照）

| 工具 | 强项 | 人声 | 分轨 | 最长 | 商用授权 | 主要风险 |
|---|---|---|---|---|---|---|
| **Suno v5** | **整歌质量基准**（人声、结构、分离度） | ✅ 强 | 付费档最多 12 | ~5–8 min | **付费档可商用** | **⚠️ 正与 Sony 诉讼**（训练数据）；**无官方 API**（第三方封装有法律风险） |
| **Udio** | **音质最强**；**inpainting（局部重生成）＋ 分轨** → 最接近"AI DAW" | ✅ 逼真 | ✅ | 可延长 | 付费档 | **⚠️ 部分渠道下载受限**（UMG 和解后条款变动）；API 锁在 Pro 档 |
| **ElevenLabs Music** | **法律最干净**（只用已授权曲库训练：Merlin / Kobalt） | ✅ | 有 | ~5 min | **商用许可** | **不得把它当"音乐"转售** |
| **Stable Audio** | **器乐 + 音效设计**（不出人声） | ❌ | 有限 | ~6 min | 付费档 | 人声场景不可用 |
| **MiniMax Music 2.5** | **开发者性价比**（约 $0.035/次 · 有 API） | ✅ | — | 50–76 s | 按平台条款 | 质量弱于 Suno/Udio |
| **Google Lyria 3** | 只授权数据训练；**RealTime 可 WebSocket 实时推器乐** | ✅（3 代起） | — | — | 按 Google 条款 | 额度与地区限制 |
| **AIVA** | **管弦/电影配乐**；可导 **MIDI 与乐谱** | ❌ | — | — | **Pro 档：完整著作权** | 非歌曲类 |
| **Meta MusicGen / Riffusion / ACE-Step** | **开源可自托管，无限量，$0** | MusicGen ❌ | — | — | **输出权利未经司法检验** | 训练数据来源不一 |

**快速决策（照场景挑）**：
- **要中文歌词的整首歌** → **Suno**（中文 prompt 与歌词理解最好——**实测补充，非表内列可推出**）；
- **要精修、要局部重来、要分轨** → **Udio**；
- **要交给客户 / 商业风险敏感** → **ElevenLabs Music**（或 Lyria）；
- **只要器乐/氛围/音效** → **Stable Audio**；
- **管弦配乐、要 MIDI 继续编** → **AIVA**；
- **零预算、能自托管** → **MusicGen 系开源**。

---

## §2 ★ 视频模型里"谁自带音频"（**选错模型＝白干**）

| 需要什么 | 选谁 | 理由 |
|---|---|---|
| **音频是承重的**（环境声、配乐、音效、对白） | **Veo 3.1** | **站点生态里唯一原生同步生成音频的模型** |
| 口播 / 说话头 | Seedance 2.0 | 人像与口型更稳 |
| 纯视觉产品演示、不靠声音 | Nano Banana Pro / Cinema Studio | 省成本 |
| 高动态角色动作，物理真实 > 音频 | Kling 3.0 | 动作质量优先 |
| **你会自己后期配音频** | **任何其他模型**（并明确要求"只出本体声、不要音乐"） | 避免生成音轨与你的音乐打架 |

**★ Seedance 2.0 的音频四模式**（原话提炼，直接可用）：
1. **默认（音乐片）**：**只要本体环境与音效，明确不要音乐**——因为真曲要后期铺：
   `Audio: no music. Diegetic ambience only — rain on metal, distant traffic, fabric movement, footsteps on wet concrete, low city hum.`
2. **让模型生成音乐**：写**流派 · BPM · 逐段能量曲线 · drop 落在哪**；
3. **用户提供音轨文件**：作为音频素材传入，并写 **`@Audio1 drives the pacing; cuts land on its beats`**；
4. **默认不要求精确口型唱词**（即使提供了歌词）：表演只写 `performing to camera, mouthing words with authentic energy`——**逐字唇形同步不可靠**，精确对口型留给后期、或明确支持音画同步的模型。

> **来源**：`higgsfield-veo-3-audio-director` · `seedance-music-video-director`（站点社区技能 · 一手）。

---

## §3 ★ 授权与法律现实（**必读，别踩**）

### 3.1 三条硬事实

1. **AI 生成的音乐，在美国现行法下一般"不具备著作权"**——**著作权需要人类作者**。
   → **你可能有"商用许可"，但那不等于"拥有版权"**。许可与所有权是两件事。
2. **许可条款随平台变动**：**免费档通常限制商用、或加水印**（或两者）。
   → **免费额度 ≠ 可用额度**。
3. **训练数据来源决定法律风险**：用**已授权 / 合作数据**训练的（ElevenLabs Music / Lyria；Stable Audio 为授权素材合作模式）
   **风险最低**；**正在诉讼**的（Suno 与 Sony）**在低风险场景可接受，在高价值交付里要回避**。

### 3.2 风险分级（按项目价值选）

```text
低风险场景（个人作品、社媒、YouTube 背景乐、内部演示）
  → 主流工具付费档都够用；免费档注意水印与商用限制

中风险（商业广告、品牌内容）
  → 优先"只用授权数据训练"的工具；留存生成记录与订阅凭证

高风险（六位数客户项目、sync 授权、影视发行）
  → 避开有未决诉讼的来源；考虑 ① 已有授权曲库 ② 人工作曲 ③ AIVA 这类"Pro 档给完整著作权"的
```

**★ 两条实务纪律**：
- **留存证据**：订阅凭证、生成时间、prompt、条款版本截图——**出事时这是唯一能拿出手的东西**；
- **不要写艺人名/曲名**去"点歌"（既违规又让模型不稳定）——**描述声音本身**（`music-craft.md` §6）。

---

## §4 制作工具（按"你会用到哪一步"分）

| 环节 | 工具 | 说明 |
|---|---|---|
| **DAW** | **Reaper**（个人授权约 $60）· Pro Tools（行业标准，年费）· Logic · 剪映/达芬奇（自带音频工具） | **能导入视频的 DAW 就够**；Reaper 被多位从业者认为"覆盖 95% 的 Pro Tools 音效设计需求" |
| **修复** | iZotope RX | 降噪、去嗡、去齿音、修复 |
| **母带/响度** | iZotope Insight · Youlean · **FabFilter Pro-L 2** · Waves WLM | **要符合 ITU-R BS.1770**（`mix-loudness.md` §5） |
| **素材库** | Freesound（免费）· Boom Library（商用）· 自制录音 | **免费库常常和商用库一样好**；差别在**组织与变化数量**——商用给你 50 个关门变体，免费给 3 个，**但你愿意多叠几次就能补上** |
| **录制** | 便携录音机 + 枪麦 | **"技巧比设备重要得多"**：$200 麦克风摆对位置 > $2000 摆错 |
| **音源合成** | NumPy + pedalboard / soundfile（见 §5） | 零成本出鼓、拨弦、气声 |

**★ 一条经济学**：**$350 录音机 + $700 枪麦 vs $3000 麦克风——音质差约 15–20%（经验估计），价格差 400%。**
→ **先把技巧与工作流练好，再升级设备。**

---

## §5 命令行与合成配方（**可复现，零素材成本**）

### 5.1 快速氛围声（ffmpeg `lavfi`，无需素材）

```bash
ffmpeg -f lavfi -i "anoisesrc=color=pink:duration=35:amplitude=0.3" \
  -af "highpass=f=80, lowpass=f=800, equalizer=f=200:width_type=o:width=2:g=-6, equalizer=f=500:width_type=o:width=2:g=4, afade=t=in:d=3, afade=t=out:st=32:d=3, volume=0.6" \
  output.mp3
```
**设计逻辑（照着改）**：**粉噪打底 → 低切去隆隆 → 高切去刺耳 → 中频提一点造"空腔/隧道"感 → 两头淡入淡出**。

### 5.2 ★ 混音时的两个坑（都踩过才写得出来）

```bash
# ① 必须写 normalize=0 —— 否则 amix 默认 normalize=1 会按输入数量把**混合结果整体衰减**（两路即约减半，人声显小；是缩放，不是压缩）
ffmpeg -i video.mp4 -i layer.wav -filter_complex \
 "[0:a]volume=1.0[va];[1:a]volume=0.55[vb];[va][vb]amix=inputs=2:duration=first:normalize=0[aout]" \
 -map 0:v -map "[aout]" output.mp4

# ② 按时间让路（对白进来自动压低背景）—— enable + adelay 给到毫秒精度
ffmpeg -i bg.mp4 -i voiceover.mp3 -filter_complex \
 "[0:a]volume=1.0:enable='lt(t,15.667)',volume=0.5:enable='gte(t,15.667)'[bg]; \
  [1:a]adelay=15667|15667,volume=2.0[vo]; [bg][vo]amix=inputs=2:duration=first:normalize=0[aout]" \
 output.mp4
```

**★ 混完必过响度检查**：上面配方里的增益叠加（如 `volume=2.0`）可能削波——**成片混音后过一遍 `loudnorm` 或 `alimiter`，目标值回 `mix-loudness.md` §1/§5**。

### 5.3 合成一个"底鼓"＝理解任何打击声的结构

**三段结构（记住这个就懂鼓了）**：
```text
① 音高扫频（the thud）—— 150 Hz → 45 Hz，在 80 ms 内完成
② 超低基线         —— 30 Hz 正弦，慢衰减
③ 瞬态攻击         —— 指数衰减的白噪（"啪"那一下）
```
→ **任何打击类声音都可以按"扫频 + 超低 + 瞬态"三段去拆或去造**。
**拨弦类**用 **Karplus-Strong**（短缓冲循环 + 滤波衰减）。
**吹管/弓弦类**的通用配方：**基音 + 轻微失谐的第二个声部（×1.003 左右）＋ 一点噪声＋慢起音包络**。

> **来源**：`ffmpeg-audio-synthesis`（站点社区技能 · 一手，含 25 个乐器合成配方）。
> **★ 但要知道它的边界**：它是**零成本的兜底/草稿方案**，用于**占位、氛围、极简配乐**；
> **要"像真乐团"仍得用采样的真乐器**。**工具能到哪一步，要说清。**

---

## §6 · ★★★ **平台自己的音色目录**（17 条 · 2026-10-16 只读取到）

> **为什么单列**：本册上面几节讲"用哪个工具"；**这一节是"平台自己的 TTS 有哪些音色"**——
> 取自 **`/api/www/landing-activities/getById?id=190`（`voiceList`）**，**只读 GET、无需点火**。
> **★ 稳定键是 `voice_id`**——**`name` 是"人名 + 形容词"拼的展示串，会改**；**要用就用 `voice_id`。**
> **★ 会过期**：2026-10-16 这一抓的快照。

| `voice_id` | 名称 | 性别 | 年龄 | 类别 | `descriptive` |
|---|---|---|---|---|---|
| `vZZLclMx4wouUtKBRfZn` | Jin - 清晰、温暖、随性 | 男声 | 中年 | 专业 | 随性 |
| `kAIqZ7fZv234ClKXwzDx` | Susan - 清晰、平静的叙述者 | 女声 | 年轻 | 专业 | 中性 |
| `Ca5bKgudqKJzq8YRFoAz` | Coco Li - 平静、年轻、可信赖 | 女声 | 年轻 | 专业 | 慵懒 |
| `bhJUNIXWQQ94l8eI2VUf` | Amy - 友好、年轻、自然 | 女声 | 年轻 | 高品质 | 随性 |
| `MQkiCZS3mnl44caDtxkJ` | 灌汤包 - 低沉、温柔、成熟 | 男声 | 中年 | 专业 | 平静 |
| `4VZIsMPtgggwNg7OXbPY` | James Gao - 平静、友好、温暖 | 男声 | 中年 | 高品质 | 平静 |
| `BZLsSg9fDGFYEEJQ4JU3` | Hayato - 禅意、舒缓、年轻 | 男声 | 年轻 | 专业 | 平静 |
| `WkcRFJo38X9XEP8kGExm` | Vincent - 清晰、干脆、成熟 | 男声 | 中年 | 专业 | 专业 |
| `Iqi0ix5WGtiSXX9VDZB4` | Helen Sun - 流畅、清晰、成熟 | 女声 | 中年 | 专业 | 正式 |
| `DVE92KG0Yd4X7RoMqy8J` | 紫菜 - 富有表现力、温暖 | 男声 | 年轻 | 专业 | 清脆 |
| `z1etx2H6NQWq1LH6oqJA` | Wilson - 低沉、严肃、中性 | 男声 | 中年 | 专业 | 随性 |
| `M0TrFmFeBJS9H4xzdk8Z` | Steven Gor - 低沉、平静、舒缓 | 男声 | 年轻 | 专业 | 平静 |
| `GgmlugwQ4LYXBbEXENWm` | Maya - 年轻、平静、流畅 | 女声 | 年轻 | 专业 | 平静 |
| `YxbjaPemDJV2xlfvkiIG` | Yun - 优雅、甜美、温柔 | 女声 | 中年 | 专业 | 平静 |
| `WuLq5z7nEcrhppO0ZQJw` | Martin Li - 沙哑、严肃、低沉 | 男声 | 中年 | 高品质 | 低沉 |
| `9lHjugDhwqoxA5MhX0az` | Anna Su - 随性、友好、明亮 | 女声 | 年轻 | 高品质 | 随性 |
| `hkfHEbBvdQFNX4uWHqRF` | Stacy - 年轻、甜美、可爱 | 女声 | 年轻 | 专业 | 愉悦 |

**★ 四条判据**：

1. **性别 `男声` 9 / `女声` 8**（**脚本复算**）；**`category` 只有两档：`专业` 13 / `高品质` 4**；
2. **`age` 的取值是 `中年` / `年轻`**——**与 `207 minimaxVoiceSearch` 的 `ageGroups`（青年/成年/儿童/老年）不是同一套枚举**，
   **不要拿 207 的筛选项去匹配 190 的 `age`**；
3. **每条还带 `description`（一句人话）与 `preview_url`**——**选音色先看 `descriptive` 与 `description`，再用 `preview_url` 试听**；
4. **口癖怎么插**（21 个英文 token：`laughs` / `sighs` / `crying` …）**→ `sound-lexicon.md` §4**。

> **来源**：**平台远端配置 `id=190`（`voiceList`）**，2026-10-16 只读 GET；**通道与取数链见 `libtv-cli-env-binding.md`**。
