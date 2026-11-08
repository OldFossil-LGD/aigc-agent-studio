# 任务上下文：完整原文、依赖与例外

> 何时读：选择本任务应读哪些册，或复用当前会话已经读过的来源时。
> 活动权威：governance-law.md 的L1；本册说明接口，不另定义治理例外。

## 从真实需求形成读取计划

Agent先理解用户原话并建立现有intent交接；用户不填JSON。
选择任务profile，并联合所有适用features，不在空镜/无声/风格/固定机位间任选一个。
原文里发现额外直接依赖或例外时，用extra_refs扩充计划，未知要求写入unresolved，
不能把“清单内的文件都在”说成“自然语言需求已经全部理解”。

已有知识路由继续工作；新闭包使用同一resolve_route，再加
context-dependencies.json中的直接依赖和适用例外。全库导航在studio-workflow.md，
导航链接不自动变成每个任务都读全库的要求；适用规范及其直接例外必须全文读。

示例命令（工具输出是Agent工作记录，不塞进创作提示词）：

    python scripts/knowledge_routes.py --profile prompt_only --feature empty --feature silent --feature camera --feature stylized --intent intent.json --out context_plan.json

每个显式decision、constraint与已声明工艺字段应在coverage中有来源与触发项。
无法机械判断任意散文是否提取完整，工具不替代这一步Agent判断。
unknown feature/kind、缺依赖、越界路径、治理版本不一致或权限冲突均不可当作完整计划。

## 保留适用域与用户锁定项

- 用户明确无声优先于声音册的默认环境底噪；不把无声改成无对白，不加雨声、人声。
- 固定机位不因运镜建议被换掉；有双人同框锁定时，表演册的正反打建议不能默默拆镜。
- 风格已锁定时，写实默认模板不能覆盖水墨、剪纸等明确工艺。
- mirror是产物类型，不是source_replica权限。反推先声明mode、deliverable、source_access；
  只有副本不能报原项目级。反推契约§2与§3在副本身份证明上的差异保留为未解，
  不选择宽口径给source_replica放行；有original_readback也只表示声明，不证明权限已核实。
- 工艺建议有冲突时记录适用例外/未解，不能让机械文件计划代替导演选择。

## 同会话读取证据与版本

plan_context只返回PLAN_ONLY；reading_compliance与production_readiness仍未验证，
generation_authorized始终false。计划有效不等于这些册已读、理解正确或已获生成批准。

已读记录由Agent基于实际完整阅读填写，至少有session_id，reads中的path、sha256、
capture_path及complete。capture_path必须指向显式capture_root内的完整原文捕获，
不能只给hash、文件存在或几页摘要。完整捕获只证明源字节证据，不证明模型理解。

    python scripts/knowledge_routes.py --plan context_plan.json --receipt read_receipt.json --capture-root .context_reads --session 当前会话ID --out context_check.json

check_read_evidence会重新计算计划和来源。缺完整捕获、捕获被截断、跨会话、
源或依赖改变时不复用；计划篡改/来源变化先重新规划，再全文读变化或新增的来源。
SOURCE_EVIDENCE_VALID仅是机械源证据有效，不能作为创作已完成或质量过关。

## 发布与事实分型

全库发布仍跑index/claims/refs/既有自检及完整测试，不以某任务闭包代替发布覆盖。
入口显式library-index声明一个包内导航源；缺导航、幻影、孤立、错误数字和越界引用
必须在对应原门禁失败。全库导航与活动规范不复制成第二套权威。

平台事实用当前官方接口/回读；用户偏好保留适用范围；工艺建议不是平台能力承诺。
历史失败率、可用率、抽卡次数或后期占比若无当前可比证据，只能是历史观察或估计，
不能锁成用户决定。例子只借结构；不确定的既有偏好保留并标待确认。
实际token/费用下降未做供应商同条件对照前不宣称；入口字节和读取文件规模另行报告。

## 从来源证据到正式交付

全文件候选角色与知识域由 knowledge-catalog.json 提供发现入口；分类不等于适用性判断，更不等于正文已读。按用户情境逐域说明采用/不适用/未解，再选原文及直接依赖/例外。正式交付的任务—来源—创作依据—产物绑定接口统一见 `delivery-review.md`。SOURCE_EVIDENCE_VALID 不自动升级为该接口的可交付状态，也不证明创作质量。
