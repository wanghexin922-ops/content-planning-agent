# 内容任务规划 Agent

小影校招 AI Agent 开发考核项目。输入活动主题、预算和截止时间，Agent 调用素材检索、脚本生成、成本估算与方案保存工具，根据实际结果调整计划，并输出方案、步骤状态、费用和未完成原因。

采用 **Python 标准库 + SQLite + DeepSeek 原生工具调用**，提供 CLI 和离线 Mock。模型负责选动作与重规划，工具负责预算、时间、依赖和保存结果的确定性校验。交付的是内容活动方案，实际制作、审核和发布仍为待执行阶段。

## 评审快速入口

| 检查内容 | 入口 |
|---|---|
| 需求、范围及验收映射 | [需求说明](docs/01-requirements.md) |
| 决策循环和工程取舍 | [方案设计](docs/02-solution.md) |
| 真实结果、失败历史与局限 | [评估报告](docs/03-evaluation.md) |
| AI 使用范围与个人贡献 | [AI 使用记录](docs/04-ai-usage.md) |
| 复盘、用时及未完成内容 | [复盘](docs/05-retrospective.md) |
| 事实约束与失败续跑 | [优化说明 1、2](docs/06-improvements.md) |
| 约束变化与独立评估 | [优化说明 3、4](docs/07-replanning-evaluation.md) |
| 提交方式 | [提交说明](SUBMISSION.md) |

已保存的验证结果：**71 项自动化测试通过，离线验收 17/17，真实模型验收 17/17，关键场景三轮独立重复 9/9**。真实失败终态的跨进程续跑专项通过 8 项检查。记录来自本次实际运行，样本规模有限，不代表未来调用必然成功。

## 1. 安装与离线运行

环境：Python 3.10+；已在 Windows、Python 3.12.4 验证。运行及内置测试只使用标准库，无须安装第三方包；[requirements.txt](requirements.txt) 说明可选测试依赖。

```powershell
git clone https://github.com/wanghexin922-ops/content-planning-agent.git
cd content-planning-agent
python scripts/verify.py
python scripts/evaluate.py --mode mock
```

第一条 Python 命令运行自动化测试并写入 `examples/test-results.txt`；第二条运行 17 个离线案例，生成 `examples/mock/` 下的输入、输出、Trace 和审计结果。Mock 采用模拟决策，仅验证流程，不证明真实模型决策效果。

单独运行超预算案例：

```powershell
python planner.py --mode mock --input examples/inputs/over_budget.json --now "2026-10-28T10:00:00+08:00" --out runtime/demo
```

`--now` 固定业务时钟，用于历史案例回放。日常任务省略该选项，程序按当前时间检查截止时间。

## 2. 配置真实模型

仓库仅包含空密钥模板 `.env.example`，不包含 `.env`。在 PowerShell 中执行：

```powershell
Copy-Item .env.example .env
```

在本地 `.env` 中填写自己的密钥：

```dotenv
DEEPSEEK_API_KEY=填写你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT=60
```

系统环境变量优先于 `.env`；`.env` 已被 Git 忽略。真实调用需要相应模型访问权限，会产生服务商 API 费用，与题目中的模拟活动预算分开计算。缺少密钥或接口失败会明确报错，不会自动切换成 Mock。

生成截止时间为当前时间后 24 小时的新任务，再执行：

```powershell
python scripts/new_request.py --budget 10 --audience "短视频创作者"
python planner.py --mode live --input runtime/request.json --out runtime/live-demo
```

可编辑 `runtime/request.json` 修改主题、预算、截止时间和受众。补齐或改变输入时使用新的 `request_id`；同一 ID 的不同输入会被拒绝。

输出目录包含 `output.json`（任务状态、工具结果、费用、保存状态）、`trace.jsonl`（动作、参数、简要依据、返回摘要、后续动作），成功保存时另有 `plan.json`（方案、脚本、依赖与排期）。任务状态保存在本地 `runtime/planner.sqlite`。

## 3. 决策闭环与边界

```text
用户主题、预算、截止时间
         ↓
模型选择动作 → 执行工具 → 工具结果反馈模型
         ↑                       ↓
         └── 补查 / 替换 / 重估 ──┘
                                 ↓
                    保存可行方案 / 说明未完成
```

模型采用原生 function calling；执行器将工具结果以 `role=tool` 反馈，再由模型选择下一步。可用工具为 `search_materials`、`generate_script`、`estimate_plan`、`save_plan`，另有 `finish` 结束动作。没有使用 Agent 框架。

- **预算调整**：真实记录中，初始费用 12 超过预算 10；模型观察结果后改用费用 8 的方案，重新估算并保存。见 [输出](examples/live/over_budget/output.json) 和 [Trace](examples/live/over_budget/trace.jsonl)。
- **正常路径**：检索、生成、估算可行后保存，见 [输出](examples/live/normal/output.json) 和 [Trace](examples/live/normal/trace.jsonl)。
- **失败处理**：记录真实工具错误，保留成功步骤；模型可调整方案、再尝试或停止。持续失败不能记为成功。
- **硬性约束**：模型不能改变预算或截止时间；保存前再次核算费用、当前时间与步骤依赖。最终保存状态以工具和数据库为准。
- **事实来源**：素材和价格均为合成数据。脚本工具基于素材原文生成本地模板，模型负责规划决策；不将模板质量当作模型创作效果。检索改写不能替换用户原始主题。

费用由素材、脚本整理、制作、审核和发布构成；耗时按单人串行估算。活动执行阶段的 `planned` 与 Agent 工具步骤的 `succeeded` 分开记录，保存方案不代表执行了活动。

## 4. 重复执行、故障与续跑

同一模式、同一 `request_id`、相同输入重复执行会返回已有结果，不重复保存；Mock 和 live 的状态隔离。SQLite 唯一约束与任务锁用于防止重复方案。

模拟脚本工具首次失败：

```powershell
python scripts/new_request.py --out runtime/failure-request.json
python planner.py --mode mock --input runtime/failure-request.json --fail generate_script:1 --out runtime/failure-demo
```

`--fail save_plan:-1` 表示持续保存失败。故障注入会记录在 Trace 中。

跨进程续跑演示：

```powershell
python scripts/new_request.py --out runtime/resume-request.json
python planner.py --mode mock --input runtime/resume-request.json --max-steps 2 --out runtime/resume-demo
python planner.py --mode mock --input runtime/resume-request.json --resume --max-steps 16 --out runtime/resume-demo
```

默认同一任务累计最多 16 次工具动作（含 finish）、20 轮模型调用；达到上限返回 `incomplete_limit`，进程重启不清零。续跑需显式 `--resume`，若耗尽原有上限，还需提高上限。失败终态也支持续跑，保留原有成功产物及失败记录。

CLI 退出码：`0` 已完成；`2` 待补充、失败或未完成等有效业务结果；`1` 配置、输入或基础设施错误。评估脚本根据用例预期判断通过与否。

## 5. 验证与复现

| 验证层次 | 已提交结果 | 说明 |
|---|---|---|
| 自动化测试 | [71 项通过](examples/test-results.txt) | 不调用真实模型，包含协议模拟与错误路径 |
| 离线流程 | [17/17](examples/mock/evaluation-summary.json) | 不能证明模型决策效果 |
| 真实模型 | [17/17](examples/live/evaluation-summary.json) | 正常、缺信息、超预算、工具失败、重复等 |
| 独立重复运行 | [9/9](examples/live_stability/evaluation-summary.json) | 正常、超预算、工具失败各 3 轮 |
| 失败后跨进程恢复 | [8 项检查通过](examples/live_resume/evaluation-summary.json) | 首次失败、恢复、重复提交三个进程 |

真实模型复现命令（需要本地密钥）：

```powershell
python scripts/evaluate.py --mode live
python scripts/evaluate.py --mode live --cases normal over_budget tool_failure --repeats 3
python scripts/evaluate_resume.py --mode live
python scripts/update_evaluation.py
```

验收包括时间紧张、费用表变化、素材替换、持续故障和无可行方案。每个案例保留实际输入、输出及 Trace；独立审计器从数据快照复算金额、时间、依赖与来源，不调用业务工具的计算方法。篡改反例用于验证审计器能识别错误。

评估采用固定业务时钟，执行时间另行记录；每轮使用独立状态。源码哈希和数据快照用于追溯运行版本。旧结果保留在 `examples/history/`，不删除真实失败来凑通过率。中断的汇总标记 `complete=false`，不算全量通过。

## 6. 项目结构

```text
planner.py                  CLI 入口
src/content_planner/        决策循环、模型适配、工具、存储、独立审计
tests/                      可执行测试
scripts/                    请求生成、验收、续跑与报告脚本
data/                       合成素材和费用、耗时规则
examples/                   输入、实际输出、Trace、测试结果与历史记录
docs/                       需求、设计、评估、AI 使用、复盘和优化说明
.env.example                本地配置模板
requirements.txt            依赖说明
SUBMISSION.md               提交说明
```

## 7. 已知限制与贡献说明

检索依赖领域词表，复杂同义词可能需要扩充；素材、费用和耗时是合成数据，串行排期未模拟多人资源；脚本为有来源约束的模板。项目提供 CLI，没有前端、真实内容平台或生产级分布式运行环境。小样本评估不构成线上可靠性保证。

本项目使用 Codex 辅助实现代码、测试和文档，范围及候选人已确认的贡献见 [AI 使用记录](docs/04-ai-usage.md)。候选人的个人阅读、修改、自测、学习收获和实际投入时间仍有待本人填写的部分，未以 AI 执行记录代替个人经历。
