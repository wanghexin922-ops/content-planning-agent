"""Generate evaluation documentation from actual artifacts, never assumed results."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    test_report = (ROOT / "examples/test-results.txt").read_text(encoding="utf-8")
    count = re.search(r"Ran (\d+) tests", test_report)
    test_status = f"{count.group(1)} 项测试，结果 {'通过' if test_report.rstrip().endswith('OK') else '需检查失败'}" if count else "测试结果格式需检查"
    lines = ["# 验证结果、失败与限制", "", "本文件由 `python scripts/update_evaluation.py` 读取实际记录生成，不手填通过率。",
             "", f"最近生成时间：{datetime.now(timezone(timedelta(hours=8))).isoformat()}。",
             f"自动化验证：{test_status}。环境：Windows / Python 3.12.4。",
             "[完整测试结果](../examples/test-results.txt)。协议单测使用模拟 HTTP；下方 live 记录才是真实模型证据。", ""]
    for mode, title in [("live", "真实模型验收"), ("mock", "离线流程验收")]:
        summary_path = ROOT / "examples" / mode / "evaluation-summary.json"
        lines += [f"## {title}", ""]
        if not summary_path.exists():
            lines += ["尚无实际验收汇总，不能宣称通过。", ""]
            continue
        summary = read(summary_path)
        lines += [f"实际通过 **{summary['passed']}/{summary['total']}**。执行时间：{summary['executed_at']}。",
                  f"业务回放时钟：{summary['fixed_business_clock']}，不同于实际 API 调用时刻。",
                  f"[机器可读汇总](../examples/{mode}/evaluation-summary.json)。", "",
                  "| 案例 | 预期 | 实际 | 费用 | 调用次数 | 检查 | 证据 |",
                  "|---|---|---|---:|---:|---|---|"]
        expected = {"normal":"completed","missing_info":"needs_input","tool_failure":"completed","over_budget":"completed",
                    "repeated_request":"completed","no_feasible_plan":"incomplete","save_failure":"failed",
                    "deadline_impossible":"incomplete","step_limit":"incomplete_limit","no_materials":"needs_input",
                    "missing_budget":"needs_input","missing_deadline":"needs_input","resume_video":"completed"}
        for case in summary["cases"]:
            name = case["case"]
            base = f"../examples/{mode}/{name}"
            links = f"[输入]({base}/input.json) / [输出]({base}/output.json) / [Trace]({base}/trace.jsonl)"
            lines.append(f"| {name} | {expected.get(name, '参见案例定义')} | {case['status']} | {case['total_cost']} | {case['tool_calls']} | {'PASS' if case['passed'] else 'FAIL'} | {links} |")
        lines += ["", "非完成案例的费用列仅表示最近一次候选估算，不是实际扣费，也不表示已保存。",
                  f"重复执行第二次记录：[输出](../examples/{mode}/repeated_request/second_run/output.json) / [Trace](../examples/{mode}/repeated_request/second_run/trace.jsonl)。", ""]
        failed = [c for c in summary["cases"] if not c["passed"]]
        if failed:
            lines += ["本轮未通过检查：", ""]
            for case in failed:
                lines.append(f"- {case['case']}：" + ", ".join(k for k,v in case["checks"].items() if not v))
        else:
            lines += ["本轮所有自动检查通过；预期内的工具失败、预算不可行和上限终止并非评估失败。"]
        lines += [""]
    lines += ["## 历史真实失败记录", ""]
    for history in sorted((ROOT / "examples/history").glob("live-*/evaluation-summary.json")):
        old = read(history)
        if old["passed"] < old["total"]:
            bad = ", ".join(c["case"] for c in old["cases"] if not c["passed"])
            relative = history.relative_to(ROOT).as_posix()
            lines += [f"- [{history.parent.name}](../{relative})：{old['passed']}/{old['total']}，未通过 {bad}。"]
    lines += ["", "首轮 no_materials 的模型把量子芯片实验室活动替换成字幕工具宣传，虽然保存成功但业务不符合原主题。修正：素材增加 topic_terms，检索和脚本工具都按原始主题核验适用范围；改写查询不能扩大该范围。新增偏题改写回归测试。", "",
              "## 真实模型的观察与动作变化", ""]
    for name in ("normal", "over_budget", "tool_failure"):
        path = ROOT / "examples/live" / name / "output.json"
        if not path.exists():
            continue
        output = read(path)
        actions = []
        for step in output["steps"]:
            value = step["tool"]
            if not step["result"]["ok"]:
                value += "（" + step["result"]["error"]["code"] + "）"
            elif value == "estimate_plan":
                e = step["result"]["estimate"]
                value += f"（费用 {e['total_cost']}，可行={e['feasible']}）"
            actions.append(value)
        lines += [f"- **{name} / {output['model']}**：" + " → ".join(actions)]
    lines += ["", "Trace 的 reason 是基于可见观察的一句行动依据，不是内部思维过程。每一步包含工具参数、实际返回、摘要及后续动作。",
              "", "## 回归检查和本次改进", "",
              "覆盖预算精度、约束绕过、模型虚报完成、保存失败、并发锁、同 ID 输入冲突、资料变化、上限、跨进程续跑、协议错误和密钥脱敏。",
              "新增：受众和主题传递到脚本与活动简报；请求生成器不擅自设定受众；排期使用截止时间的时区。相同事实合并引用，创意角度明确标记待审核。",
              "", "## 失败、修正与已知限制", "",
              "首次真实简历案例存在受众默认值不匹配、总结未明确 UTC 时区的问题；原记录保存在 examples/history/first-live-demo，未改写历史输出。现通过显式 --audience 和时区统一修正，新增回归测试并重新运行真实案例 resume_video。",
              "脚本仍使用本地事实模板，不以 AI 创作质量作为已证明的效果。模型的创意角度是待人工审核建议，不能视为经过核验的产品事实。",
              "素材检索是标签匹配；费用与耗时为合成的单人串行估算；未连接真实制作、审核、发布服务。所有业务阶段仍为 planned。",
              "本轮每个场景只做一次真实模型试验，没有统计稳定性或全面安全性结论；未计量真实 API token 费用。生成成功不等于业务活动已执行。",
              "失败步骤续跑另有三个独立 CLI 进程的真实模型验证，见 [专项汇总](../examples/live_resume/evaluation-summary.json) 和 [专项说明](06-improvements.md)。",
              "重复评估会将上一版结果复制到 examples/history 后再生成新结果；历史文件的通过率和模型状态仅代表当时版本。", ""]
    (ROOT / "docs/03-evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print("Updated docs/03-evaluation.md from actual evidence.")


if __name__ == "__main__":
    main()
