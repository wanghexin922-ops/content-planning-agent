# 项目提交说明

- 项目题目：内容任务规划 Agent
- 官方题号：第 2 题（内容任务规划 Agent）。
- GitHub URL：https://github.com/wanghexin922-ops/content-planning-agent
- 仓库可见性：公开，评审无需额外授权。
- 最终 commit SHA：使用本次提交时的完整 SHA，运行 `git rev-parse HEAD` 获取，并粘贴到考试提交框或附带的提交说明 TXT。本文不嵌入自身提交的 SHA，以免产生循环更新。
- 评审入口：[README.md](README.md)
- 离线检查：`python scripts/verify.py`、`python scripts/evaluate.py --mode mock`
- 真实检查：按 README 配置自己的密钥后运行 `python scripts/evaluate.py --mode live`

已保存的验证：71 项自动化测试通过；离线 17/17；真实模型 17/17；关键场景独立重复 9/9；真实失败续跑专项 8 项检查通过。详细证据与边界见 [评估报告](docs/03-evaluation.md)。

## 考试页面如何填写

在说明框填写题号、题目、仓库 URL、最终 commit SHA 和评审入口。若页面要求上传文件，可以上传附带的提交说明 TXT 和源码 ZIP；GitHub 仓库仍按统一交付要求提供。源码 ZIP 是对应 commit 的辅助副本，不能用截图或视频代替代码。

## 提交前本人核对

1. 在第 2 题提交框填写题目、仓库链接及最终 SHA。
2. [AI 使用记录](docs/04-ai-usage.md) 和 [复盘](docs/05-retrospective.md) 已记录约 2.5 小时个人投入及实际参与范围，区分个人命令运行和 AI 执行的系统验收。
3. 如果补充材料产生新提交，重新获取最终 SHA，并更新考试提交文字及附件，确保版本一致。

仓库不包含 `.env`、真实密钥和本地数据库，仅提供 `.env.example`。真实模型记录使用合成业务资料；Mock 只证明流程，不证明真实模型决策效果。
