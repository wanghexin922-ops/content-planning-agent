# 验证结果、失败与限制

本文件由 `python scripts/update_evaluation.py` 读取实际记录生成，不手填通过率。

最近生成时间：2026-10-29T13:54:40.422472+08:00。
自动化验证：71 项测试，结果 通过。环境：Windows / Python 3.12.4。
[完整测试结果](../examples/test-results.txt)。协议单测使用模拟 HTTP；下方 live 记录才是真实模型证据。

## 真实模型验收

实际通过 **17/17**。执行时间：2026-10-29T05:51:23.774987+00:00。
业务回放时钟：2026-10-28T10:00:00+08:00，不同于实际 API 调用时刻。
[机器可读汇总](../examples/live/evaluation-summary.json)。

| 案例 | 预期 | 实际 | 费用 | 调用次数 | 检查 | 证据 |
|---|---|---|---:|---:|---|---|
| normal | completed | completed | 12.0 | 5 | PASS | [输入](../examples/live/normal/input.json) / [输出](../examples/live/normal/output.json) / [Trace](../examples/live/normal/trace.jsonl) |
| missing_info | needs_input | needs_input | None | 2 | PASS | [输入](../examples/live/missing_info/input.json) / [输出](../examples/live/missing_info/output.json) / [Trace](../examples/live/missing_info/trace.jsonl) |
| tool_failure | completed | completed | 12.0 | 6 | PASS | [输入](../examples/live/tool_failure/input.json) / [输出](../examples/live/tool_failure/output.json) / [Trace](../examples/live/tool_failure/trace.jsonl) |
| over_budget | completed | completed | 8.0 | 6 | PASS | [输入](../examples/live/over_budget/input.json) / [输出](../examples/live/over_budget/output.json) / [Trace](../examples/live/over_budget/trace.jsonl) |
| repeated_request | completed | completed | 12.0 | 5 | PASS | [输入](../examples/live/repeated_request/input.json) / [输出](../examples/live/repeated_request/output.json) / [Trace](../examples/live/repeated_request/trace.jsonl) |
| no_feasible_plan | incomplete | incomplete | 12.0 | 4 | PASS | [输入](../examples/live/no_feasible_plan/input.json) / [输出](../examples/live/no_feasible_plan/output.json) / [Trace](../examples/live/no_feasible_plan/trace.jsonl) |
| save_failure | failed | failed | 12.0 | 5 | PASS | [输入](../examples/live/save_failure/input.json) / [输出](../examples/live/save_failure/output.json) / [Trace](../examples/live/save_failure/trace.jsonl) |
| deadline_impossible | incomplete | incomplete | 6.0 | 5 | PASS | [输入](../examples/live/deadline_impossible/input.json) / [输出](../examples/live/deadline_impossible/output.json) / [Trace](../examples/live/deadline_impossible/trace.jsonl) |
| step_limit | incomplete_limit | incomplete_limit | None | 2 | PASS | [输入](../examples/live/step_limit/input.json) / [输出](../examples/live/step_limit/output.json) / [Trace](../examples/live/step_limit/trace.jsonl) |
| no_materials | needs_input | needs_input | None | 3 | PASS | [输入](../examples/live/no_materials/input.json) / [输出](../examples/live/no_materials/output.json) / [Trace](../examples/live/no_materials/trace.jsonl) |
| missing_budget | needs_input | needs_input | None | 1 | PASS | [输入](../examples/live/missing_budget/input.json) / [输出](../examples/live/missing_budget/output.json) / [Trace](../examples/live/missing_budget/trace.jsonl) |
| missing_deadline | needs_input | needs_input | None | 1 | PASS | [输入](../examples/live/missing_deadline/input.json) / [输出](../examples/live/missing_deadline/output.json) / [Trace](../examples/live/missing_deadline/trace.jsonl) |
| resume_video | completed | completed | 8.0 | 6 | PASS | [输入](../examples/live/resume_video/input.json) / [输出](../examples/live/resume_video/output.json) / [Trace](../examples/live/resume_video/trace.jsonl) |
| time_pressure | completed | completed | 6.0 | 6 | PASS | [输入](../examples/live/time_pressure/input.json) / [输出](../examples/live/time_pressure/output.json) / [Trace](../examples/live/time_pressure/trace.jsonl) |
| price_changed | completed | completed | 6.0 | 6 | PASS | [输入](../examples/live/price_changed/input.json) / [输出](../examples/live/price_changed/output.json) / [Trace](../examples/live/price_changed/trace.jsonl) |
| material_switch | completed | completed | 4.0 | 7 | PASS | [输入](../examples/live/material_switch/input.json) / [输出](../examples/live/material_switch/output.json) / [Trace](../examples/live/material_switch/trace.jsonl) |
| persistent_failure | failed | failed | None | 4 | PASS | [输入](../examples/live/persistent_failure/input.json) / [输出](../examples/live/persistent_failure/output.json) / [Trace](../examples/live/persistent_failure/trace.jsonl) |

非完成案例的费用列仅表示最近一次候选估算，不是实际扣费，也不表示已保存。
重复执行第二次记录：[输出](../examples/live/repeated_request/second_run/output.json) / [Trace](../examples/live/repeated_request/second_run/trace.jsonl)。

本轮所有自动检查通过；预期内的工具失败、预算不可行和上限终止并非评估失败。

## 离线流程验收

实际通过 **17/17**。执行时间：2026-10-29T05:51:20.748171+00:00。
业务回放时钟：2026-10-28T10:00:00+08:00，不同于实际 API 调用时刻。
[机器可读汇总](../examples/mock/evaluation-summary.json)。

| 案例 | 预期 | 实际 | 费用 | 调用次数 | 检查 | 证据 |
|---|---|---|---:|---:|---|---|
| normal | completed | completed | 12.0 | 5 | PASS | [输入](../examples/mock/normal/input.json) / [输出](../examples/mock/normal/output.json) / [Trace](../examples/mock/normal/trace.jsonl) |
| missing_info | needs_input | needs_input | None | 1 | PASS | [输入](../examples/mock/missing_info/input.json) / [输出](../examples/mock/missing_info/output.json) / [Trace](../examples/mock/missing_info/trace.jsonl) |
| tool_failure | completed | completed | 12.0 | 6 | PASS | [输入](../examples/mock/tool_failure/input.json) / [输出](../examples/mock/tool_failure/output.json) / [Trace](../examples/mock/tool_failure/trace.jsonl) |
| over_budget | completed | completed | 8.0 | 6 | PASS | [输入](../examples/mock/over_budget/input.json) / [输出](../examples/mock/over_budget/output.json) / [Trace](../examples/mock/over_budget/trace.jsonl) |
| repeated_request | completed | completed | 12.0 | 5 | PASS | [输入](../examples/mock/repeated_request/input.json) / [输出](../examples/mock/repeated_request/output.json) / [Trace](../examples/mock/repeated_request/trace.jsonl) |
| no_feasible_plan | incomplete | incomplete | 10.0 | 6 | PASS | [输入](../examples/mock/no_feasible_plan/input.json) / [输出](../examples/mock/no_feasible_plan/output.json) / [Trace](../examples/mock/no_feasible_plan/trace.jsonl) |
| save_failure | failed | failed | 12.0 | 5 | PASS | [输入](../examples/mock/save_failure/input.json) / [输出](../examples/mock/save_failure/output.json) / [Trace](../examples/mock/save_failure/trace.jsonl) |
| deadline_impossible | incomplete | incomplete | 10.0 | 6 | PASS | [输入](../examples/mock/deadline_impossible/input.json) / [输出](../examples/mock/deadline_impossible/output.json) / [Trace](../examples/mock/deadline_impossible/trace.jsonl) |
| step_limit | incomplete_limit | incomplete_limit | None | 2 | PASS | [输入](../examples/mock/step_limit/input.json) / [输出](../examples/mock/step_limit/output.json) / [Trace](../examples/mock/step_limit/trace.jsonl) |
| no_materials | needs_input | needs_input | None | 2 | PASS | [输入](../examples/mock/no_materials/input.json) / [输出](../examples/mock/no_materials/output.json) / [Trace](../examples/mock/no_materials/trace.jsonl) |
| missing_budget | needs_input | needs_input | None | 1 | PASS | [输入](../examples/mock/missing_budget/input.json) / [输出](../examples/mock/missing_budget/output.json) / [Trace](../examples/mock/missing_budget/trace.jsonl) |
| missing_deadline | needs_input | needs_input | None | 1 | PASS | [输入](../examples/mock/missing_deadline/input.json) / [输出](../examples/mock/missing_deadline/output.json) / [Trace](../examples/mock/missing_deadline/trace.jsonl) |
| resume_video | completed | completed | 8.0 | 6 | PASS | [输入](../examples/mock/resume_video/input.json) / [输出](../examples/mock/resume_video/output.json) / [Trace](../examples/mock/resume_video/trace.jsonl) |
| time_pressure | completed | completed | 6.0 | 6 | PASS | [输入](../examples/mock/time_pressure/input.json) / [输出](../examples/mock/time_pressure/output.json) / [Trace](../examples/mock/time_pressure/trace.jsonl) |
| price_changed | completed | completed | 6.0 | 6 | PASS | [输入](../examples/mock/price_changed/input.json) / [输出](../examples/mock/price_changed/output.json) / [Trace](../examples/mock/price_changed/trace.jsonl) |
| material_switch | completed | completed | 4.0 | 8 | PASS | [输入](../examples/mock/material_switch/input.json) / [输出](../examples/mock/material_switch/output.json) / [Trace](../examples/mock/material_switch/trace.jsonl) |
| persistent_failure | failed | failed | None | 3 | PASS | [输入](../examples/mock/persistent_failure/input.json) / [输出](../examples/mock/persistent_failure/output.json) / [Trace](../examples/mock/persistent_failure/trace.jsonl) |

非完成案例的费用列仅表示最近一次候选估算，不是实际扣费，也不表示已保存。
重复执行第二次记录：[输出](../examples/mock/repeated_request/second_run/output.json) / [Trace](../examples/mock/repeated_request/second_run/trace.jsonl)。

本轮所有自动检查通过；预期内的工具失败、预算不可行和上限终止并非评估失败。

## 历史真实失败记录

- [live-20261028T123841311225Z](../examples/history/live-20261028T123841311225Z/evaluation-summary.json)：12/13，未通过 no_materials。
- [live-20261029T054327634396Z](../examples/history/live-20261029T054327634396Z/evaluation-summary.json)：3/4，未通过 persistent_failure。
- [live-20261029T055123691309Z](../examples/history/live-20261029T055123691309Z/evaluation-summary.json)：16/17，未通过 resume_video。

首轮 no_materials 的模型把量子芯片实验室活动替换成字幕工具宣传，虽然保存成功但业务不符合原主题。修正：素材增加 topic_terms，检索和脚本工具都按原始主题核验适用范围；改写查询不能扩大该范围。新增偏题改写回归测试。

## 真实模型的观察与动作变化

- **normal / deepseek-flash**：search_materials → generate_script → estimate_plan（费用 12.0，可行=True） → save_plan → finish
- **over_budget / deepseek-flash**：search_materials → generate_script → estimate_plan（费用 12.0，可行=False） → estimate_plan（费用 8.0，可行=True） → save_plan → finish
- **tool_failure / deepseek-flash**：search_materials → generate_script（injected_failure） → generate_script → estimate_plan（费用 12.0，可行=True） → save_plan → finish

Trace 的 reason 是基于可见观察的一句行动依据，不是内部思维过程。每一步包含工具参数、实际返回、摘要及后续动作。

## 回归检查和本次改进

覆盖预算精度、约束绕过、模型虚报完成、保存失败、并发锁、同 ID 输入冲突、资料变化、上限、跨进程续跑、协议错误和密钥脱敏。
新增：受众和主题传递到脚本与活动简报；请求生成器不擅自设定受众；排期使用截止时间的时区。相同事实合并引用，创意角度明确标记待审核。

## 失败、修正与已知限制

首次真实简历案例存在受众默认值不匹配、总结未明确 UTC 时区的问题；原记录保存在 examples/history/first-live-demo，未改写历史输出。现通过显式 --audience 和时区统一修正，新增回归测试并重新运行真实案例 resume_video。
脚本仍使用本地事实模板，不以 AI 创作质量作为已证明的效果。模型的创意角度是待人工审核建议，不能视为经过核验的产品事实。
素材检索是标签匹配；费用与耗时为合成的单人串行估算；未连接真实制作、审核、发布服务。所有业务阶段仍为 planned。
全量场景单次验证，关键场景另有小样本重复试验（见后文），不保证未来成功率或全面安全性；未计量真实 API token 费用。生成成功不等于业务活动已执行。
失败步骤续跑另有三个独立 CLI 进程的真实模型验证，见 [专项汇总](../examples/live_resume/evaluation-summary.json) 和 [专项说明](06-improvements.md)。
重复评估会将上一版结果复制到 examples/history 后再生成新结果；历史文件的通过率和模型状态仅代表当时版本。

## 独立评估与重复真实运行

最新评估器从原始输入、费用和素材快照独立复算，不调用业务工具的 calculate 方法；每个案例的 audit.json 给出逐项检查。源码哈希与本次数据快照随结果保存。详见 [第3、4项说明](07-replanning-evaluation.md)。

实际通过 9/9，计划试验 9 次，complete=True。
[汇总与全部结果路径](../examples/live_stability/evaluation-summary.json)。

| 场景 | 通过/执行 | 平均工具调用 | 平均墙钟耗时（秒） |
|---|---:|---:|---:|
| normal | 3/3 | 5.0 | 9.825 |
| over_budget | 3/3 | 6.0 | 11.464 |
| tool_failure | 3/3 | 6.0 | 12.12 |

每次试验独立请求和状态，无旧结果缓存；三次重复只说明本次小样本观察，不构成可靠性保证。失败记录也计入分母，未用后续成功替换失败。
