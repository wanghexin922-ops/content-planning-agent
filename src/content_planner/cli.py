import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .agent import run_agent
from .common import PlannerError, dumps, read_json, timestamp, write_json
from .model import DeepSeekModel, MockModel, load_env
from .storage import Store

ROOT = Path(__file__).resolve().parents[2]


def write_artifacts(out, request, result):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "input.json", request)
    write_json(out / "output.json", {k: v for k, v in result.items() if k != "trace"})
    (out / "trace.jsonl").write_text("".join(dumps(event) + "\n" for event in result["trace"]), encoding="utf-8")
    if result.get("plan"):
        write_json(out / "plan.json", result["plan"])
    elif (out / "plan.json").exists():
        (out / "plan.json").unlink()  # This exact file belongs to this run's output directory.


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="内容任务规划 Agent：模型决策、预算核验、幂等保存")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--db", type=Path, default=ROOT / "runtime" / "planner.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "runtime" / "latest")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--now", help="仅用于可复现回放，ISO 时间含时区；省略则使用真实时钟")
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument("--max-model-calls", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail", action="append", default=[], metavar="TOOL:COUNT", help="故障注入：1=首次失败，-1=永久失败")
    args = parser.parse_args(argv)
    store = None
    try:
        request = read_json(args.input)
        materials, pricing = read_json(args.data_dir / "materials.json"), read_json(args.data_dir / "pricing.json")
        validate_data(materials, pricing)
        from .common import validate_request
        validate_request(request)
        faults = {}
        for value in args.fail:
            name, count = value.rsplit(":", 1)
            if name not in {"search_materials", "generate_script", "estimate_plan", "save_plan"} or int(count) < -1:
                raise ValueError("故障注入仅接受业务工具名称和 -1 或非负次数")
            faults[name] = int(count)
        if args.mode == "live":
            load_env(args.env_file)
            model = DeepSeekModel()
        else:
            model = MockModel(request)
        fixed = timestamp(args.now) if args.now else None
        now = (lambda: fixed) if fixed else None
        store = Store(args.db)
        result = run_agent(request, model, store, materials, pricing, now=now,
                           max_steps=args.max_steps, max_model_calls=args.max_model_calls, resume=args.resume, faults=faults)
        write_artifacts(args.out, request, result)
        brief = {k: result[k] for k in ("request_id", "status", "mode", "summary", "saved", "plan_id", "total_cost", "tool_calls", "replayed")}
        brief["output_directory"] = str(args.out.resolve())
        print(json.dumps(brief, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 2
    except (PlannerError, ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        code = exc.code if isinstance(exc, PlannerError) else "input_or_environment_error"
        # Environment errors intentionally omit raw paths/provider response bodies and secrets.
        message = str(exc) if isinstance(exc, (PlannerError, ValueError)) else "读取输入、数据或存储失败，请检查配置和权限"
        print(dumps({"status": "failed", "error": code, "message": message}), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


def validate_data(materials, pricing):
    from .common import money
    if not isinstance(materials, list) or not materials or len({m["id"] for m in materials}) != len(materials):
        raise ValueError("素材必须非空且 ID 唯一")
    for m in materials:
        money(m["cost"])
        if not isinstance(m.get("topic_terms"), list) or not m["topic_terms"] or any(not isinstance(t, str) or not t.strip() for t in m["topic_terms"]):
            raise ValueError("素材必须提供非空 topic_terms 适用领域关键词")
        if not isinstance(m["id"], str) or not isinstance(m["title"], str) or not isinstance(m["facts"], list) or not m["facts"] or any(not isinstance(f, str) for f in m["facts"]) or not isinstance(m["tags"], list) or any(not isinstance(t, str) for t in m["tags"]):
            raise ValueError("素材 ID、标题、标签、事实格式无效")
    if set(pricing["production_modes"]) != {"premium", "basic", "slideshow"}:
        raise ValueError("制作方式目录不完整")
    for row in [pricing["script"], pricing["review"], pricing["publish"], *pricing["production_modes"].values()]:
        money(row["cost"])
        if type(row["minutes"]) is not int or row["minutes"] < 0:
            raise ValueError("耗时必须为非负整数分钟")
