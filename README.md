# 内容任务规划 Agent

面向小影校招 AI Agent 开发考核的 CLI 项目。用户提供主题、预算和截止时间，模型选择工具，根据实际返回值调整制作方式、替换素材或停止；程序负责预算计算、依赖检查、持久化和防重复。

**当前验证状态：53 项自动化测试通过；13/13 组离线案例通过；真实 `deepseek-flash` 验收 13/13。** 已提交正常、信息不足、工具失败、超预算、重复执行等输入、实际输出和 Trace，见 [真实模型评估](docs/03-evaluation.md)。首轮真实验收的失败记录及修正说明也已保留。Mock 仅用于流程验证。

## 1. 环境与最快运行方式

- Python 3.10+；本次验证：Windows、Python 3.12.4。
- 运行和内置测试均只使用标准库，无须安装框架或运行时依赖。
- 在项目根目录运行命令。Windows PowerShell 示例：

```powershell
cd 'F:\找工作简历项目\小影科技笔试项目\内容任务规划 Agent'
python scripts/verify.py
python scripts/evaluate.py --mode mock
```

第二条命令会实际运行 13 组案例，将输入、输出、Trace 和检查结果写入 `examples/mock/`。测试结果在 `examples/test-results.txt`。如更喜欢 pytest，可选安装 `python -m pip install "pytest>=7,<10"` 后运行 `python -m pytest -q`。

单独回放“预算 10、初始费用 12、调整后费用 8”的案例：

```powershell
python planner.py --mode mock --input examples/inputs/over_budget.json --now '2026-10-28T10:00:00+08:00' --out runtime/demo
```

`--now` 固定业务时钟，仅用于历史案例回放。正常使用省略它，程序会按真实时间检查截止时间。

## 2. 填写 Key，运行 DeepSeek

项目交付目录包含空密钥的 `.env`。若从 GitHub 克隆，先复制：

```powershell
Copy-Item .env.example .env
```

只需修改 `.env` 第一项：

```dotenv
DEEPSEEK_API_KEY=在本地填入你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT=60
```

已有系统环境变量优先于 `.env`。Key 不进入提示词、Trace 或数据库；`.env` 已被 Git 忽略。模型调用会产生模型服务商的实际 API 费用，不计入本项目的模拟活动预算。

创建从当前时间起 24 小时内截止的新任务并运行：

```powershell
python scripts/new_request.py --budget 10 --audience "短视频创作者"
python planner.py --mode live --input runtime/request.json --out runtime/live-demo
```

结果文件：

- `output.json`：任务状态、步骤及工具实际结果、费用和保存状态。
- `plan.json`：成功保存的活动方案、可编辑脚本、阶段依赖和时间安排；未保存时不存在。
- `trace.jsonl`：每步动作参数、简要依据、返回摘要、下一动作。
- `runtime/planner.sqlite`：任务和方案持久化，仅存本地，不提交。

真实模型使用 DeepSeek 原生 function calling，关闭 thinking 模式以简化接入。模型返回函数调用，执行器执行工具后将结果以 `role=tool` 反馈，模型再选择后续动作。没有 Key、请求超时、限流或认证失败时会明确报错，**绝不静默回退 Mock**。

接入依据（2026-10-28 核对）：[模型名称及接口地址](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)。

## 3. 真实模型验收与提交前步骤

先运行核心案例，检查真实工具结果是否改变后续动作：

```powershell
python scripts/evaluate.py --mode live --cases normal over_budget missing_info tool_failure repeated_request
```

完整验收：

```powershell
python scripts/evaluate.py --mode live
```

记录独立保存到 `examples/live/`，不会冒充离线记录。每次评估使用临时数据库，因此重复运行评估会重新调用模型；旧结果先完整复制到 `examples/history/`，再生成所选案例的新结果。评估使用固定业务时钟，不代表当时正在执行真实业务。

必须阅读 `examples/live/evaluation-summary.json`，核对至少两条真实模型路径。例如：正常估算后保存；观察超预算后改选制作方式、重新估算再保存。真实模型也可能产生不同选择或失败，检查器会如实标出，不修改记录来凑通过。运行 `python scripts/update_evaluation.py` 可从实际记录重新生成评估文档。

提交前还需要本人填写 `docs/04-ai-usage.md`、`docs/05-retrospective.md` 中明确标出的待补充项；将所有代码、文档、测试和案例放到一个 GitHub 仓库。文件上传入口可提交 `SUBMISSION.md` 的 PDF/TXT 版本，但仍须提供仓库链接与最终 commit SHA。这里不猜测官方题号。

## 4. 输入与约束

```json
{
  "request_id": "campaign-001",
  "theme": "推广一款视频字幕工具",
  "budget": 10,
  "deadline": "2026-10-30T18:00:00+08:00",
  "initial_mode": "premium",
  "audience": "短视频创作者"
}
```

`request_id`、`theme` 必需。缺少 `budget` 或 `deadline` 是合法的资料不足场景，返回待补充状态；无效数字、无时区时间等属于输入错误。`initial_mode` 是可调整的初始偏好，支持 `premium/basic/slideshow`，不是硬性要求。预算和截止时间不能被模型改变。

费用来自 `data/pricing.json`，素材来自 `data/materials.json`，均为合成数据。最终方案费用 = 素材成本 + 脚本整理 + 制作 + 审核 + 发布。采用单人串行耗时估算。所有活动执行阶段状态为 `planned`；Agent 步骤的 `succeeded` 仅表示对应规划工具执行成功。

## 5. 异常、重复执行与续跑

相同模式、相同 `request_id`、相同输入重复提交，读取已有结果，不重新保存；同一 ID 改变输入会拒绝。Mock 与 live 的存储命名空间隔离。修改数据源后请换新请求 ID，防止混用旧估算。

模拟首次脚本工具失败：

```powershell
python scripts/new_request.py --out runtime/failure-request.json
python planner.py --mode mock --input runtime/failure-request.json --fail generate_script:1 --out runtime/failure-demo
```

永久保存失败使用 `--fail save_plan:-1`。故障注入只用于验证，完整写入 Trace。

验证跨进程续跑：

```powershell
python scripts/new_request.py --out runtime/resume-request.json
python planner.py --mode mock --input runtime/resume-request.json --max-steps 2 --out runtime/resume-demo
python planner.py --mode mock --input runtime/resume-request.json --resume --max-steps 16 --out runtime/resume-demo
```

`--resume` 保留成功步骤，继续从工具观察处决策。默认同一任务累计最多 16 次工具动作（含 finish）、20 轮模型调用；重新启动不会隐式清零。达到上限返回 `incomplete_limit`，续跑时需显式提高原有上限。未成功任务不加 `--resume` 只返回既有结果。补齐缺失输入时使用新的 `request_id`。

退出码：`0` 已完成，`2` 待补充/失败/未完成等有效业务结果，`1` 配置、输入或基础设施错误。评估脚本对预期内失败按用例验收，不因为业务结果是 failed 就误报整个测试失败。

## 6. 评审导航

| 内容 | 入口 |
|---|---|
| 需求与验收映射 | [docs/01-requirements.md](docs/01-requirements.md) |
| 模型决策、状态和取舍 | [docs/02-solution.md](docs/02-solution.md) |
| 实际验证与不足 | [docs/03-evaluation.md](docs/03-evaluation.md) |
| AI 辅助范围 | [docs/04-ai-usage.md](docs/04-ai-usage.md) |
| 复盘与后续计划 | [docs/05-retrospective.md](docs/05-retrospective.md) |
| 决策循环 | [src/content_planner/agent.py](src/content_planner/agent.py) |
| 模型与 Mock | [src/content_planner/model.py](src/content_planner/model.py) |
| 工具与预算守卫 | [src/content_planner/tools.py](src/content_planner/tools.py) |
| 全部自动化检查 | [tests/](tests/) |
| 离线验收汇总 | [examples/mock/evaluation-summary.json](examples/mock/evaluation-summary.json) |

不包含 UI、真实素材平台、真实发布、多 Agent 或生产级分布式 Runtime。业务脚本是基于素材事实的本地模板；模型负责决策和调整，不把模板输出包装为模型创作效果。

## 7. 简历视频主题示例与当前提交状态

```powershell
python scripts/new_request.py --budget 10 --theme "推广带字幕的求职简历介绍视频制作" --audience "应届毕业生" --out runtime/resume-request.json
python planner.py --mode live --input runtime/resume-request.json --out runtime/resume-demo
```

受众省略时保持未指定，不擅自套用默认人群。脚本开头和结尾带入主题、受众，产品事实合并来源；创意角度标记为待审核建议。活动简报列出交付物和待确认的发布渠道、账号、执行人员。

`data/materials.json` 的 `topic_terms` 限制素材适用领域。检索改写不能把缺资料的活动替换成另一产品的宣传。当前规则基于领域关键词，有意限制支持范围；复杂同义词可能需要扩充词表。更改数据后使用新的 request_id。

本地工程与真实验收记录已具备评审条件；发布到 GitHub 仍需确定目标仓库、配置本地 Git 提交姓名/邮箱并提交。个人经历、实际用时及官方题号需本人补充。GitHub 连接与本地 Git 作者/推送凭据是不同配置。

## 8. 事实边界与失败恢复专项

传播角度限定为三种表达形式，产品事实只取素材原文；最终金额、时间、保存状态由工具状态生成。模型原始 summary/reason 只保留在 Trace 中作为未核验提案。

真正 failed 状态也支持跨进程恢复，已用真实 DeepSeek 验证。运行 `python scripts/evaluate_resume.py --mode live` 可复现失败、恢复和重复提交三个进程；离线用 `--mode mock`。详见 [专项说明](docs/06-improvements.md)。
