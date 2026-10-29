"""Bounded model → tool → observation → model loop, with durable state."""
import json
from datetime import datetime, timezone

from .common import PlannerError, dumps, fingerprint, missing_fields, validate_request
from .prompts import SYSTEM_PROMPT
from .tools import BusinessTools, TOOL_SCHEMAS, error


def initial_state(request, model, data_hash):
    return {"request": request, "mode": model.mode, "model": model.model, "data_hash": data_hash,
            "status": "running", "summary": "", "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": dumps(request)}],
            "cache": {}, "retrieved_ids": [], "scripts": {}, "estimates": {},
            "latest_estimate_id": None, "saved": None, "steps": [], "trace": [],
            "tool_calls": 0, "model_calls": 0, "runs": 0}


def result_of(state, replayed=False):
    saved = state.get("saved")
    estimate = saved["plan"]["estimate"] if saved else state["estimates"].get(state.get("latest_estimate_id"))
    return {"request_id": state["request"]["request_id"], "status": state["status"], "summary": state["summary"],
            "mode": state["mode"], "model": state["model"],
            "evidence": "real_model_run" if state["mode"] == "live" else "offline_mock_flow_only",
            "saved": bool(saved), "plan_id": saved["plan_id"] if saved else None,
            "plan": saved["plan"] if saved else None, "latest_estimate": estimate,
            "total_cost": estimate["total_cost"] if estimate else None,
            "missing_fields": missing_fields(state["request"]), "steps": state["steps"],
            "successful_artifacts": {"retrieved_ids": state["retrieved_ids"], "scripts": state["scripts"]},
            "tool_calls": state["tool_calls"], "model_calls": state["model_calls"], "runs": state["runs"],
            "replayed": replayed, "trace": state["trace"]}


def run_agent(request, model, store, materials, pricing, *, now=None, max_steps=16,
              max_model_calls=20, resume=False, faults=None):
    validate_request(request)
    if max_steps < 1 or max_model_calls < 1:
        raise ValueError("调用上限必须为正整数")
    now = now or (lambda: datetime.now(timezone.utc))
    key = model.mode + ":" + request["request_id"]
    data_hash = fingerprint({"materials": materials, "pricing": pricing})
    with store.acquire(key, request, initial_state(request, model, data_hash)) as (state, owner):
        if state["data_hash"] != data_hash:
            raise PlannerError("data_changed", "素材或费用表已改变，请使用新 request_id，避免复用旧结果")
        saved = store.get_plan(key)
        if saved:
            state.update(saved=saved, status="completed", summary="已读取该请求保存的唯一方案，未重复执行或保存")
            state["trace"].append({"event": "idempotent_replay", "clock": now().isoformat(), "plan_id": saved["plan_id"], "new_tool_calls": 0, "next_action": "end"})
            store.checkpoint(key, owner, state)
            return result_of(state, replayed=True)
        if state["runs"] and not resume:
            state["trace"].append({"event": "cached_task_returned", "clock": now().isoformat(), "new_tool_calls": 0, "hint": "失败或未完成任务可显式 --resume"})
            store.checkpoint(key, owner, state)
            return result_of(state, replayed=True)
        previous_status = state["status"]
        if resume and state["runs"]:
            last_business = next((s for s in reversed(state["steps"]) if s["tool"] != "finish"), None)
            failed_action = None
            if last_business and last_business["status"] == "failed":
                failed_action = {"tool": last_business["tool"], "arguments": last_business["arguments"]}
            context = {"operation": "resume_task", "previous_status": previous_status,
                       "last_failed_action": failed_action,
                       "existing_script_ids": list(state["scripts"]),
                       "instruction": "用户显式请求恢复。保留成功产物和失败历史，基于当前观察选择下一动作；可重试失败步骤，但环境是否恢复以本次工具返回为准。不得清零执行上限或改变预算和截止时间。"}
            state["messages"].append({"role": "user", "content": dumps(context)})
            state["trace"].append({"event": "resume_requested", "clock": now().isoformat(), **context})
        state["runs"] += 1
        state["status"] = "running"
        tools = BusinessTools(store, key, owner, state, materials, pricing, now, faults)
        state["trace"].append({"event": "run_started", "run": state["runs"], "mode": model.mode,
                               "model": model.model, "clock": now().isoformat(), "faults": faults or {},
                               "resume": resume, "max_steps": max_steps, "max_model_calls": max_model_calls})
        store.checkpoint(key, owner, state)
        while state["tool_calls"] < max_steps and state["model_calls"] < max_model_calls:
            state["model_calls"] += 1
            # Persist consumed model budget even when the provider fails.
            store.checkpoint(key, owner, state)
            try:
                message = model.next_message(state["messages"], TOOL_SCHEMAS)
            except PlannerError as exc:
                state.update(status="failed", summary=str(exc))
                state["trace"].append({"event": "model_error", "code": exc.code, "message": str(exc), "next_action": "resume_or_fix_configuration"})
                break
            calls = message.get("tool_calls", []) if isinstance(message, dict) else []
            valid = isinstance(calls, list) and bool(calls) and all(
                isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"] and c.get("type") == "function"
                and isinstance(c.get("function"), dict) and isinstance(c["function"].get("name"), str)
                and isinstance(c["function"].get("arguments"), str) for c in calls)
            if not valid or len({c["id"] for c in calls}) != len(calls):
                state["trace"].append({"event": "invalid_model_action", "message": "未提供有效函数调用", "model_call": state["model_calls"]})
                state["messages"].append({"role": "user", "content": "请使用一个合法的工具函数调用；结束也必须调用 finish。"})
                store.checkpoint(key, owner, state)
                continue
            state["messages"].append(message)
            # Multi-call batches are rejected without side effects, then fed back for correction.
            if len(calls) != 1:
                for call in calls:
                    state["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": dumps(error("one_action_required", "每轮只能选择一个动作，本轮未执行工具"))})
                state["trace"].append({"event": "invalid_model_action", "message": "多动作批次已拒绝，未执行", "model_call": state["model_calls"]})
                store.checkpoint(key, owner, state)
                continue
            call = calls[0]
            function = call["function"]
            name = function["name"]
            try:
                args = json.loads(function["arguments"])
            except ValueError:
                args = None
            state["tool_calls"] += 1
            step = state["tool_calls"]
            result = tools.call(name, args)
            state["messages"].append({"role": "tool", "tool_call_id": call["id"], "content": dumps(result)})
            step_result = {"step": step, "tool": name, "arguments": args,
                           "status": "succeeded" if result["ok"] else "failed", "result": result}
            state["steps"].append(step_result)
            # Connect consecutive actions explicitly without fabricating future decisions.
            previous = next((e for e in reversed(state["trace"]) if e.get("event") == "tool_result"), None)
            if previous and previous.get("next_action") is None:
                previous["next_action"] = {"tool": name, "step": step}
            state["trace"].append({"event": "tool_result", "step": step, "model_call": state["model_calls"],
                                   "mode": model.mode, "clock": now().isoformat(), "tool": name, "arguments": args,
                                   "reason": args.get("reason", "") if isinstance(args, dict) else "参数无效",
                                   "result_summary": summarize(name, result), "result": result, "next_action": None})
            if name == "finish" and result["ok"]:
                state.update(status=result["terminal_status"], summary=result["summary"])
                state["trace"][-1]["next_action"] = "end"
                break
            store.checkpoint(key, owner, state)
        if state["status"] == "running":
            state.update(status="incomplete_limit", summary="达到工具调用或模型轮数上限，任务未完成；成功结果已保留")
            state["trace"].append({"event": "limit_reached", "tool_calls": state["tool_calls"], "model_calls": state["model_calls"], "next_action": "explicit_resume_with_higher_limit"})
        store.checkpoint(key, owner, state)
        return result_of(state)


def summarize(name, result):
    if not result["ok"]:
        return result["error"]["code"] + ": " + result["error"]["message"]
    if "count" in result:
        return f"检索到 {result['count']} 个素材"
    if name == "generate_script":
        return "已生成 " + result["script_id"]
    if name == "estimate_plan":
        e = result["estimate"]
        return f"费用 {e['total_cost']}，耗时 {e['total_minutes']} 分钟，可行={e['feasible']}"
    if name == "save_plan":
        return "保存成功 " + result["plan_id"]
    return result.get("summary", "成功")
