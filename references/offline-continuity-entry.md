# 离线连续性、局部返工与审片回执绑定

> 何时读：镜头需固定具体资产版本，或需判定一次改动影响哪些已有计划/产物时；以及校验已有审片回执是否仍对应同一媒体时。
> 本册只说明现有编译器的离线接口，不提供生成授权，不替代 `review-passes.md` 的实际观看与判定。

## 逐镜资产与版本

在输入的 `entities[]` 给资产正整数 `version`（缺省为1）。在 `shots[]` 给本镜 `version`，并用 `asset_refs` 显式指定本镜依赖，例如：

```json
{"id":"shot_01","version":1,"asset_refs":[{"entity_id":"coat","version":2}]}
```

资产图中coat必须确有version=2；未知资产、重复引用或版本不匹配会拒绝。`asset_refs: []` 表示无资产引用；没有该字段时保留旧调用行为，但标为 `legacy_all_unconfirmed`，不能据此声称已证实最小依赖。文字交付中的引用边是规划记录，不证明参考素材已经生成或就绪。意图交接入口保留以上机械字段，用户仍不必填写JSON。

## 同一资产的历史版本共存

需要跨镜保留不同状态时，在实体首次建立就给history:[]，稳定进入base__vN命名空间。
没有history字段的旧调用保留原ID；不得在已有媒体后悄悄换命名空间并声称旧记录未变。
各镜必须显式asset_refs，使用原base entity_id和确有定义的version，不把全部引用转到当前版。

升版时，把旧02_asset_graph_plan.json相应资产的definition完整复制进history，当前实体增加version并写新状态。
历史definition保留id/kind/name/description/state/version/aspect_ratio/reference_purpose/reuse_count/
state_versions/requires_iteration/precision_demand/contains_text；不得只给旧状态名再继承当前其他字段。
历史版本须同一实体、唯一且早于当前版；当前state_versions至少覆盖实际定义数。
既有复用/精度/多状态迭代规则及显式豁免仍生效，旧definition保留当时计数与声明，不追溯套新默认。

资产计划保留全部完整定义；图中只为实际引用的版本建活跃节点，未引用旧定义仍保存，旧记录进归档。
active由权威逐镜引用派生，不能靠修改producer active标记逃过门禁。
资产版本命名碰撞、未知/重复版本引用、历史缺项、改写同一源版本均拒绝。
asset_definitions及graph_history保存源定义，未启用或曾移除的版本也不能被同名改写。
这里只保存声明与离线绑定，不证明任何参考图已生成或历史素材已审。

## 返工影响建议

先保留修改前的图，再按正常编译流程生成新图：

```text
python scripts/compile_shot_graph.py contract.json assets.json --previous-graph old_graph.json --out rework_advice.json
```

该选项输出两版图的失效建议；正常编图时不传它。模块接口是 `plan_rework(previous, current)`。内容、版本或引用边改变时沿新旧依赖边计算后继，移除的连线也参与分析；单纯布局移动不使媒体失效。空图、重复节点或断链不能报通过。

结果列出 `affected_record_ids / changes / invalidations`，只作定位建议，不自动删除媒体、不重生成、不自动递增下游版本或写回台账。调用方须按现有 Production Record 和失败责任层处理；真实再生成仍需对应显式批准。世界状态继承见下节；plan_rework仍只给建议；实际记录写回使用下节的主编译入口。

## 实际离线返工写回

已有记录图必须来自本版主编译入口，先保存原03_shot_graph_plan.json，再调用：

```text
python scripts/compile_intent_delivery.py changed_intent.json --out new_delivery --previous-graph old_delivery/03_shot_graph_plan.json
```

compile_production.py也接受--previous-graph，Python入口同名previous_graph参数。
不是task_type=rework，不转换用户交付终点；prompt_only继续不产05/08、不写平台。
旧图若缺实际Production Records需先用原始输入重编；不能以自报hash或READY补造正文。

新图中的production_records以node_id为record_id，记录实际输出版本version、声明版本source_version、
规范source_revision、完整来源正文及带版本依赖。Prompt Package带同一record_binding；
compile_graph_plan适配保留版本及source_record_id。记录范围是offline_plan_and_artifact_binding。

实际正文/参数/声明状态/版本或消费顺序改变时，沿新旧reference/dependency/assembly/lineage
边更新后继；删边也生效。未携旧媒体字段的新编译图不会让所有旧结果失效。
只改布局或分组名称列review，不清媒体；真正变化按invalidate_plan/invalidate_output处理，
移除记录进入既有archived状态并保留previous_state。record_history/graph_history/archived_records保存旧版，无变化重复应用幂等。
资产同一源版本不能代表不同asset_state/asset_description；派生工艺/全局设置变化会更新输出版本，
不冒充资产源事实变更。版本化资产还核对完整冻结definition，不能重用旧源版本改写历史。

新/变化记录先recovering，主编译真实合同/能力/声明门禁通过才graph_plan_ready；不自动reviewed。
局部应用函数scripts.production_records.apply_rework本身不执行重新验收，保留recovering。
rework.changes标既有failure_layer/reentry_state及真实来源，reusable_record_ids列可复用记录；
变化记录的recovery列责任层、重入状态与剩余原门禁。主编译实际门禁通过才清本地剩余门禁并记plan_revalidated，
不替代最终语义验收、媒体审片或生成批准。
镜头最终语义验收报告仍须按阶段一规则单独检查，计划就绪不是最终交付或媒体效果证明。

已有本地文件可用scripts.production_records.register_local_output(graph, record_id, path,
version=当前输出版本, source_revision=当前来源指纹, evidence_class="local_file_only")显式绑定。
它读真实非空字节，不生成文件；旧版迟到、同版换不同字节、未就绪计划拒绝。
fixture标offline_fixture；均只记generated/NOT_VERIFIED，不冒充平台回读或实际审片。

## 审片回执绑定

```text
python scripts/film_qc_gate.py --video media.mp4 --review-record record.json --review-receipt review.json
```

record需有 `record_id / version / media_sha256`。record若有source_revision，回执还必须匹配该来源指纹；回执须绑定相同三字段，包含 structure、instruction、technical、creative四层的实际证据/决定，creative下保留既有六遍专项判定；不适用须说明原因。缺素材、缺回执、旧哈希或版本错配、缺层/缺专项，均不能当作已验收。

这只核验真实本地字节与回执字段的绑定完整性：**绑定PASS仍为generated，review_status保持NOT_VERIFIED**。非空的证据文本不能证明观察真实，接口无法独立识别内容伪造；技术检测与创作审片须另按原方法执行并留真实结果。不得用字节fixture或生成成功宣称媒体质量已经过审。

绑定模式不能与 `--expect-duration / --expect-ratio / --expect-fps / --expect-cuts` 混用；混用明确报用法错，不忽略技术要求。技术QC应单独调用原参数模式。两类检查的通过范围分别报告，不相互代替。

## 结构化世界状态与真实消费

Agent按用户原话填写现有intent交接，用户不手填JSON。初始状态放world_state_initial，
镜头给world_state_delta与world_state_refs。参考样例：samples/world_state_chain/intent.json。

条目有kind、value、observable：kind沿用identity/physical/prop/world/dialogue/frame/approval；
前六类须显式observable=true，未知类、空值、非有限数拒绝。这里只校验声明，
不能机械证明自然语言状态可观察或媒体已兑现。心理词应由Agent先转成可见表演/台词。
approval只存metadata、observable=false，不进创作提示词，不授点火或任何执行许可。

每镜delta须覆盖上一状态的全部键：未变写字符串unchanged，改变给完整条目；
新键也给完整条目。开始状态继承上一镜结束，未发生的状态不能静默消失。
每项保留record_id/version/规范JSON内容hash，分别记录开始和结束来源。
这些是声明记录的版本，不是平台回读或实际审片证据。

每镜refs显式列出本镜实际消费的键；空列表表示不消费。未列入的世界状态仍继承，
却不被强加到画面；未知/重复引用、缺delta、缺refs都拒绝。节点只绑定实际消费的
角色/阶段指令与来源指纹，不能因远处不可见道具变了就让无关镜头重做。

视觉状态进入既有块：静帧与单格故事板只消费开场，不把镜尾变化写进首帧；
video_candidate、prompt及assembly记录开场与结束。dialogue类走声音块，
不进入静帧视觉；approval、版本和来源hash均留在记录，不塞进创作提示词。
追加不覆盖原工艺块，明确声音/构图等锁定项仍按原规则验收；冲突不由状态工具猜测。

world_state_start/end、world_state_sources_start/end与world_state_refs随shot graph保存，
规范Prompt Package和最终Markdown从同一图消费。source_revision是合同规范JSON指纹，
不冒充原文文件SHA；graph/node版本经compile_graph_plan转换保留，不重置为1。

本节不表示返工已执行，也不把生成或绑定PASS说成媒体已审。记录写回见上面的实际离线入口；
历史版本与完整返工链按主入口实跑离线验收；不得因绑定或局部测试通过宣称媒体效果已验证。

状态交付验收由verify_delivery_semantics从权威意图重新算继承，不相信产物的状态hash、consumed或自报PASS。逐实际角色的正本目标块校验；最终正文只核本次正式交付的主候选（视频优先，否则静帧），不要求中间包虚构最终章节。缺状态、错块、否定前缀、重复章节、跨候选借用、零候选及缺最终正文拒绝；多行状态值须完整保留。这里核规范状态原子的机械消费，不自动认可任意同义改写，也不证明媒体效果。空镜不能消费observable identity，但未引用的全局身份状态仍保留继承。
