"""Generate ACTUAL outputs and traces; mock/live evidence goes to separate folders."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import shutil
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from content_planner.agent import run_agent
from content_planner.cli import validate_data, write_artifacts
from content_planner.common import PlannerError, read_json, timestamp, write_json
from content_planner.model import DeepSeekModel, MockModel, load_env
from content_planner.storage import Store

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
    "resume_video": {"budget": 10, "theme": "推广带字幕的求职简历介绍视频制作", "audience": "应届毕业生", "expect": "completed"},
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
    args = parser.parse_args()
    load_env(ROOT / ".env")
    # Fail fast before creating any 'live' results if the key is missing.
    if args.mode == "live":
        DeepSeekModel()
    previous_root = ROOT / "examples" / args.mode
    if previous_root.exists():
        archive = ROOT / "examples/history" / (args.mode + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        shutil.copytree(previous_root, archive)
    data, pricing = read_json(ROOT / "data/materials.json"), read_json(ROOT / "data/pricing.json")
    validate_data(data, pricing)
    results = []
    with tempfile.TemporaryDirectory(prefix="content-planner-eval-") as tmp:
        store = Store(Path(tmp) / "evaluation.sqlite")
        try:
            for name in args.cases:
                spec = CASES[name]
                case_materials, case_pricing = case_data(data, pricing, spec)
                req = request_for(name, spec)
                write_json(ROOT / "examples/inputs" / (name + ".json"), req)
                model = MockModel(req) if args.mode == "mock" else DeepSeekModel()
                kwargs = dict(now=lambda: timestamp(NOW), max_steps=spec.get("max_steps", 16), faults=spec.get("faults"))
                result = run_agent(req, model, store, case_materials, case_pricing, **kwargs)
                directory = ROOT / "examples" / args.mode / name
                write_artifacts(directory, req, result)
                write_json(directory / "data-snapshot.json", {"materials":case_materials,"pricing":case_pricing,"clock":NOW,"faults":spec.get("faults",{})})
                previous = None
                if spec.get("repeat"):
                    previous = result
                    result = run_agent(req, model, store, case_materials, case_pricing, **kwargs)
                    write_artifacts(directory / "second_run", req, result)
                checks = check_result(name, spec, result, previous)
                rows = store.db.execute("SELECT count(*) FROM plans WHERE task_key=?", (args.mode+":"+req["request_id"],)).fetchone()[0]
                checks["database_plan_count"] = rows == (1 if result["saved"] else 0)
                row = {"case": name, "status": result["status"], "passed": all(checks.values()), "checks": checks,
                       "tool_calls": result["tool_calls"], "total_cost": result["total_cost"],
                       "output": f"{args.mode}/{name}/output.json", "trace": f"{args.mode}/{name}/trace.jsonl"}
                results.append(row)
                print(f"{name}: {result['status']} | checks={'PASS' if row['passed'] else 'FAIL'}", flush=True)
        finally:
            store.close()
    summary = {"mode": args.mode, "evidence": "offline_mock_flow_only" if args.mode == "mock" else "real_model_run",
               "executed_at": datetime.now(timezone.utc).isoformat(), "fixed_business_clock": NOW,
               "note": "固定业务时钟用于回放，不是当时真实业务任务。Mock 不证明模型决策效果。",
               "passed": sum(r["passed"] for r in results), "total": len(results), "cases": results}
    write_json(ROOT / "examples" / args.mode / "evaluation-summary.json", summary)
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlannerError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        raise SystemExit(1)
