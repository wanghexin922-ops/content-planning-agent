"""Generate ACTUAL outputs and traces; mock/live evidence goes to separate folders."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import shutil
from copy import deepcopy
import hashlib
import time
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from content_planner.agent import run_agent
from content_planner.cli import validate_data, write_artifacts
from content_planner.common import PlannerError, read_json, timestamp, write_json
from content_planner.model import DeepSeekModel, MockModel, load_env
from content_planner.storage import Store
from content_planner.audit import audit_result

NOW = "2026-10-28T10:00:00+08:00"
CASES = {
    "normal": {"budget": 15, "expect": "completed"},
    "missing_info": {"omit": ["budget", "deadline"], "expect": "needs_input"},
    "tool_failure": {"budget": 15, "faults": {"generate_script": 1}, "expect": "completed"},
    "over_budget": {"budget": 10, "expect": "completed"},
    "repeated_request": {"budget": 15, "repeat": True, "expect": "completed"},
    "no_feasible_plan": {"budget": 2, "expect": "incomplete"},
    "save_failure": {"budget": 15, "faults": {"save_plan": -1}, "expect": "failed"},
    "deadline_impossible": {"budget": 15, "deadline": "2026-10-28T10:10:00+08:00", "expect": "incomplete"},
    "step_limit": {"budget": 15, "max_steps": 2, "expect": "incomplete_limit"},
    "no_materials": {"budget": 15, "theme": "量子芯片实验室的活动", "expect": "needs_input"},
    "missing_budget": {"omit": ["budget"], "expect": "needs_input"},
    "missing_deadline": {"omit": ["deadline"], "expect": "needs_input"},
    "resume_video": {"budget": 10, "theme": "推广字幕工具：以应届毕业生的求职简历介绍视频为使用场景，仅介绍字幕添加和编辑能力，不生成个人简历", "audience": "应届毕业生", "expect": "completed"},
    "time_pressure": {"budget": 15, "deadline": "2026-10-28T11:40:00+08:00", "expect": "completed"},
    "price_changed": {"budget": 7, "mode_costs": {"premium":9,"basic":8}, "expect": "completed"},
    "material_switch": {"budget": 4, "expect": "completed"},
    "persistent_failure": {"budget": 15, "faults": {"generate_script":-1}, "expect": "failed"},
}


def case_data(materials, pricing, spec):
    materials, pricing = deepcopy(materials), deepcopy(pricing)
    for mode, cost in spec.get("mode_costs", {}).items():
        pricing["production_modes"][mode]["cost"] = cost
    return materials, pricing


def request_for(name, spec):
    req = {"request_id": "demo-" + name, "theme": spec.get("theme", "推广一款视频字幕工具"),
           "budget": spec.get("budget", 10), "deadline": spec.get("deadline", "2026-10-29T18:00:00+08:00"),
           "initial_mode": "premium", "audience": spec.get("audience", "短视频创作者")}
    for key in spec.get("omit", []):
        req.pop(key)
    return req


def check_result(name, spec, result, previous=None):
    checks = {"expected_status": result["status"] == spec["expect"]}
    if result["status"] == "completed":
        checks["saved_and_feasible"] = bool(result["saved"] and result["plan_id"] and result["plan"]["estimate"]["feasible"])
        checks["budget_matches_sum"] = round(sum(s["cost"] for s in result["plan"]["estimate"]["steps"]), 2) == result["total_cost"]
        checks["audience_preserved"] = result["plan"]["audience"] == spec.get("audience", "短视频创作者")
        checks["script_matches_audience"] = result["plan"]["script"]["audience"] == result["plan"]["audience"]
    else:
        checks["no_false_save"] = not result["saved"]
    if name in {"over_budget", "time_pressure", "price_changed"}:
        estimates = [s["result"]["estimate"] for s in result["steps"] if s["tool"] == "estimate_plan" and s["result"]["ok"]]
        checks["observed_replanning"] = len(estimates) >= 2 and not estimates[0]["feasible"] and estimates[-1]["feasible"]
    if name == "tool_failure":
        checks["failure_was_observed"] = any(s["status"] == "failed" for s in result["steps"])
        checks["successful_search_preserved"] = sum(s["tool"] == "search_materials" and s["status"] == "succeeded" for s in result["steps"]) == 1
    if name == "material_switch":
        checks["affordable_material_selected"] = result["saved"] and result["total_cost"] <= spec["budget"]
    if name == "persistent_failure":
        checks["persistent_error_observed"] = any(s["status"] == "failed" and s["tool"] == "generate_script" for s in result["steps"])
    if previous:
        checks["idempotent"] = result["replayed"] and result["plan_id"] == previous["plan_id"] and result["tool_calls"] == previous["tool_calls"]
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--repeats", type=int, choices=range(1,6), default=1, help="独立重复次数；大于1时写入独立 stability 目录")
    args = parser.parse_args()
    load_env(ROOT / ".env")
    # Fail fast before creating any 'live' results if the key is missing.
    if args.mode == "live":
        DeepSeekModel()
    output_name = args.mode + ("_stability" if args.repeats > 1 else "")
    previous_root = ROOT / "examples" / output_name
    if previous_root.exists():
        archive = ROOT / "examples/history" / (output_name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        shutil.copytree(previous_root, archive)
    data, pricing = read_json(ROOT / "data/materials.json"), read_json(ROOT / "data/pricing.json")
    validate_data(data, pricing)
    results = []
    manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'src').rglob('*.py')), Path(__file__).resolve()]}
    summary = {"mode": args.mode, "evidence": "offline_mock_flow_only" if args.mode == "mock" else "real_model_run",
               "executed_at": datetime.now(timezone.utc).isoformat(), "fixed_business_clock": NOW,
               "note": "固定业务时钟回放；每轮独立任务与状态。Mock 不证明模型决策效果。重复运行样本很小，不构成稳定性保证。",
               "source_sha256":manifest,"repeats":args.repeats,"requested_cases":args.cases,
               "expected_runs":args.repeats*len(args.cases),"complete":False,"passed":0,"total":0,"cases":results}
    with tempfile.TemporaryDirectory(prefix="content-planner-eval-") as tmp:
        store = Store(Path(tmp) / "evaluation.sqlite")
        try:
            for trial, name in [(i,name) for i in range(1,args.repeats+1) for name in args.cases]:
                spec = CASES[name]
                case_materials, case_pricing = case_data(data, pricing, spec)
                req = request_for(name, spec)
                if args.repeats>1:
                    req['request_id'] += f'-trial-{trial}'
                write_json(ROOT / "examples/inputs" / (name + ".json"), req)
                model = MockModel(req) if args.mode == "mock" else DeepSeekModel()
                kwargs = dict(now=lambda: timestamp(NOW), max_steps=spec.get("max_steps", 16), faults=spec.get("faults"))
                started=time.perf_counter()
                result = run_agent(req, model, store, case_materials, case_pricing, **kwargs)
                elapsed=time.perf_counter()-started
                directory = previous_root / (f'trial-{trial:02d}' if args.repeats>1 else '') / name
                write_artifacts(directory, req, result)
                write_json(directory / "data-snapshot.json", {"materials":case_materials,"pricing":case_pricing,"clock":NOW,"faults":spec.get("faults",{})})
                previous = None
                if spec.get("repeat"):
                    previous = result
                    result = run_agent(req, model, store, case_materials, case_pricing, **kwargs)
                    write_artifacts(directory / "second_run", req, result)
                checks = check_result(name, spec, result, previous)
                independent=audit_result(req,result,case_materials,case_pricing,NOW,store.get_plan(args.mode+':'+req['request_id']),previous)
                checks.update({'audit_'+key:value for key,value in independent.items()})
                write_json(directory/'audit.json',{'checks':independent,'passed':all(independent.values()),'oracle':'原始输入+素材费用快照+独立预算/串行时间规则+SQLite实际记录'})
                rows = store.db.execute("SELECT count(*) FROM plans WHERE task_key=?", (args.mode+":"+req["request_id"],)).fetchone()[0]
                checks["database_plan_count"] = rows == (1 if result["saved"] else 0)
                row = {"case": name, "status": result["status"], "passed": all(checks.values()), "checks": checks,
                       "trial":trial,"expected_status":spec['expect'],"elapsed_seconds":round(elapsed,3),"model_calls":result['model_calls'],
                       "tool_calls": result["tool_calls"], "total_cost": result["total_cost"],
                       "output": (directory/'output.json').relative_to(ROOT/'examples').as_posix(), "trace": (directory/'trace.jsonl').relative_to(ROOT/'examples').as_posix()}
                results.append(row)
                summary.update(passed=sum(r['passed'] for r in results),total=len(results))
                write_json(previous_root/'evaluation-summary.json',summary)
                print(f"trial {trial} {name}: {result['status']} | checks={'PASS' if row['passed'] else 'FAIL'}", flush=True)
        finally:
            store.close()
    summary['complete']=len(results)==summary['expected_runs']
    summary['per_case']={name:{'passed':sum(r['passed'] for r in results if r['case']==name),
        'runs':sum(r['case']==name for r in results),
        'status_counts':dict(Counter(r['status'] for r in results if r['case']==name)),
        'mean_tool_calls':round(sum(r['tool_calls'] for r in results if r['case']==name)/args.repeats,2),
        'mean_elapsed_seconds':round(sum(r['elapsed_seconds'] for r in results if r['case']==name)/args.repeats,3)} for name in args.cases}
    write_json(previous_root / "evaluation-summary.json", summary)
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlannerError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        raise SystemExit(1)
