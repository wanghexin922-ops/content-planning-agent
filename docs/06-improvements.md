# 第 1、2 项专项优化

## 第 1 项：事实与规则边界

传播角度限定为“功能介绍、操作演示、场景引导”，不接受自由添加的能力或效果承诺。产品事实仍来自素材原文，保存前再次核验。取舍：牺牲一部分开放创意表达，保证本考核范围内可验证。

最终 summary 由已保存方案和工具状态生成。模型提交的 summary、reason 只作为原始动作提案保留在 Trace 中，不能当作经过核验的业务结论。用户输入的主题和受众仍是用户提供的信息，不等于产品事实。

审核和发布等阶段由程序固定计入费用，不能通过工具参数删除；预算不足时只建议用户调整约束或资料，不建议省略必需环节。不同候选方案的缺口仅针对已生成脚本范围，不声称完成全局最优搜索。

阶段验证：48 项自动化测试通过；normal、over_budget、no_feasible_plan 三组真实 DeepSeek 验证通过。完整历史记录保留在 examples/history；后续全量评估代表最新版本。

尚不宣称完全解决任意自然语言事实校验；原始 Trace 中可能包含模型被拒绝的提案，评审应区分提案与最终结构化产物。

## 第 2 项：从真正失败状态跨进程恢复

`--resume` 在原有工具对话后追加显式恢复请求，包含此前终态、最近失败动作和成功脚本 ID。由模型选择下一步，执行器不自动替模型执行保存。失败记录和工具调用计数不重置。永久故障注入仅对单次运行生效，移除参数代表尝试恢复；如果故障仍在，工具依然返回失败，不假设已经修好。

专项验收通过三个独立 CLI 进程验证：首次保存工具永久失败，返回 failed；第二次无故障注入并显式 resume，复用素材和脚本后完成；第三次原样重复提交，返回同一方案，无新增工具调用。额外检查原失败步骤逐项相等、脚本 ID/内容相等、数据库只有一份方案。

手工复现（新请求使用当前时间的截止时间）：

```powershell
python scripts/new_request.py --budget 10 --audience "短视频创作者" --out runtime/recovery-request.json
python planner.py --mode live --input runtime/recovery-request.json --fail save_plan:-1 --out runtime/recovery-first
python planner.py --mode live --input runtime/recovery-request.json --resume --out runtime/recovery-second
python planner.py --mode live --input runtime/recovery-request.json --out runtime/recovery-repeat
```

自动复现并生成可提交的证据（使用固定历史业务时钟）：

```powershell
python scripts/evaluate_resume.py --mode mock
python scripts/evaluate_resume.py --mode live
```

[真实专项汇总](../examples/live_resume/evaluation-summary.json)；[首次失败](../examples/live_resume/first_run/output.json)；[恢复结果](../examples/live_resume/resumed/output.json)；[恢复 Trace](../examples/live_resume/resumed/trace.jsonl)；[重复提交](../examples/live_resume/repeated/output.json)。

新增回归覆盖：故障未解除时仍失败、恢复时不清零步数上限、恢复时截止时间已过则拒绝保存，以及跨进程真实终态恢复。第1、2项完成时自动化测试合计 53 项；后续新增数量见最新评估。测试结果和全量模型验收以最新评估报告为准。

本次验证脚本曾暴露 Windows 下 sqlite3 连接上下文不自动关闭连接的问题，导致临时数据库清理失败；已改为显式 closing 并重新执行成功。这是验收脚本资源释放问题，不改变业务失败记录。

实现和验证由 AI 辅助完成，未代填个人贡献。旧版本原始 Trace 保留，不回写或清洗旧版模型提案。
