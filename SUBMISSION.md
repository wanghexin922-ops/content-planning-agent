# 项目提交说明

- 项目题目：内容任务规划 Agent
- 官方题号：待按正式试卷确认（不依据粘贴顺序猜测）
- GitHub URL：待上传后填写
- 最终 commit SHA：待最终提交后填写，可通过 `git rev-parse HEAD` 获取
- 评审入口：README.md
- 离线检查：`python scripts/verify.py`、`python scripts/evaluate.py --mode mock`
- 真实模型检查：配置本地 `.env` 后执行 `python scripts/evaluate.py --mode live`

当前提交准备状态：44 项测试通过；离线 13/13；真实模型 13/13。真实记录在 examples/live/，历史失败和修正在 docs/03-evaluation.md。个人贡献补充、正式题号、Git 提交作者配置、目标 GitHub 仓库、上传及最终 SHA 尚待完成。

如果提交页面只有文件上传，可把本说明填写完整后另存为 TXT/PDF 上传，并在备注栏同步填写仓库 URL。所有代码、文档、测试、实际输出与 Trace 应在同一 GitHub 仓库。私有仓库须为指定评审账号开放读取权限。

不得上传 `.env`、真实密钥和含隐私的输入。仓库应包含 `.env.example`，不包含本地数据库和运行缓存。真实模型使用本项目合成数据生成的验收记录可放在 `examples/live/` 提交。
