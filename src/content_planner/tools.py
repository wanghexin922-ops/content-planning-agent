"""Local business tools. The model chooses actions; code owns arithmetic and writes."""
from datetime import timedelta
from decimal import Decimal
import sqlite3

from .common import dumps, fingerprint, missing_fields, money, timestamp

SAFE_ANGLES = ["功能介绍", "操作演示", "场景引导"]


def schema(name, description, properties, required):
    properties = dict(properties, reason={"type": "string", "description": "一句基于可见结果的行动理由"})
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required + ["reason"], "additionalProperties": False}}}


TOOL_SCHEMAS = [
    schema("search_materials", "检索本地合成素材；返回匹配素材及费用耗时目录", {"query": {"type": "string"}}, ["query"]),
    schema("generate_script", "从已检索素材生成事实可追溯的本地模板脚本", {
        "material_ids": {"type": "array", "items": {"type": "string"}},
        "angle": {"type": "string", "enum": SAFE_ANGLES, "description": "选择表达形式；产品能力只能取自素材事实，不能附加一键、自动或效果承诺"}}, ["material_ids", "angle"]),
    schema("estimate_plan", "按价格表核算预算与串行完成时间；返回替代制作方式的估算", {
        "script_id": {"type": "string"}, "production_mode": {"type": "string", "enum": ["premium", "basic", "slideshow"]}}, ["script_id", "production_mode"]),
    schema("save_plan", "重新核验可行性并幂等保存方案；返回确切保存状态", {"estimate_id": {"type": "string"}}, ["estimate_id"]),
    schema("finish", "观察工具结果后完成、请求补充、报告失败或未完成", {
        "status": {"type": "string", "enum": ["completed", "needs_input", "incomplete", "failed"]},
        "summary": {"type": "string"}}, ["status", "summary"]),
]


def validate_args(name, args):
    spec = next((x["function"]["parameters"] for x in TOOL_SCHEMAS if x["function"]["name"] == name), None)
    if spec is None:
        return "未知工具名称"
    if not isinstance(args, dict):
        return "工具参数必须是对象"
    if set(args) - set(spec["properties"]) or set(spec["required"]) - set(args):
        return "工具参数包含未知字段或缺少必需字段"
    for key, value in args.items():
        rule = spec["properties"][key]
        if rule["type"] == "string" and (not isinstance(value, str) or not value.strip() or len(value) > 2000):
            return key + " 必须是非空且不超过 2000 字的字符串"
        if rule["type"] == "array" and (not isinstance(value, list) or not value or len(value) > 20 or any(not isinstance(v, str) for v in value) or len(value) != len(set(value))):
            return key + " 必须是 1–20 个不重复字符串"
        if "enum" in rule and value not in rule["enum"]:
            return key + " 不在允许范围内"
    return None


def error(code, message, retryable=False, **extra):
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}, **extra}


class BusinessTools:
    def __init__(self, store, key, owner, state, materials, pricing, now, faults=None):
        self.store, self.key, self.owner, self.state = store, key, owner, state
        self.materials = {m["id"]: m for m in materials}
        self.pricing, self.now = pricing, now
        self.faults = dict(faults or {})

    def call(self, name, args):
        invalid = validate_args(name, args)
        if invalid:
            return error("invalid_action", invalid)
        if name == "finish":
            return self.finish(args)
        missing = missing_fields(self.state["request"])
        if missing:
            return error("missing_input", "需补充必要约束", missing_fields=missing)
        arguments = {k: v for k, v in args.items() if k != "reason"}
        cache_key = fingerprint({"tool": name, "args": arguments})
        # A cached estimate may be stale in wall-clock mode, so always recompute it.
        if name in {"search_materials", "generate_script"} and cache_key in self.state["cache"]:
            return dict(self.state["cache"][cache_key], cached=True)
        remaining = self.faults.get(name, 0)
        if remaining:
            if remaining > 0:
                self.faults[name] -= 1
            return error("injected_failure", "演示用工具故障：" + name, retryable=remaining > 0)
        try:
            result = getattr(self, name)(**arguments)
        except (sqlite3.Error, OSError):
            return error("storage_error", "本地存储操作失败；未确认成功", retryable=True)
        if result["ok"] and name in {"search_materials", "generate_script"}:
            self.state["cache"][cache_key] = result
        return result

    def search_materials(self, query):
        q = query.lower().strip()
        ranked = []
        original_theme = self.state["request"]["theme"].lower()
        for material in self.materials.values():
            # Query rewrites may improve retrieval, but may not change the user's topic.
            if not any(term.lower() in original_theme for term in material["topic_terms"]):
                continue
            score = sum(tag.lower() in q for tag in material["tags"])
            score += int(q == material["id"].lower()) * 10
            if score:
                ranked.append((score, material))
        ranked.sort(key=lambda item: -item[0])
        found = [m for _, m in ranked]
        self.state["retrieved_ids"] = sorted(set(self.state["retrieved_ids"]) | {m["id"] for m in found})
        return {"ok": True, "materials": found, "count": len(found), "pricing": self.pricing,
                "hint": "只返回原始主题符合素材适用领域的结果。无匹配时可保持原意改写查询或请求补充；不得把用户主题替换为其他产品宣传"}

    def generate_script(self, material_ids, angle):
        if angle not in SAFE_ANGLES:
            return error("unsupported_claim", "请仅选择功能介绍、操作演示或场景引导；不能自由添加产品能力")
        if any(mid not in self.state["retrieved_ids"] or mid not in self.materials for mid in material_ids):
            return error("unknown_material", "只能使用当前任务已检索到的素材 ID")
        if any(not any(term.lower() in self.state["request"]["theme"].lower() for term in self.materials[mid]["topic_terms"]) for mid in material_ids):
            return error("topic_mismatch", "素材适用领域与原始主题不符，请补充资料而非替换活动主题")
        request = self.state["request"]
        audience = request.get("audience") or "未指定受众（待运营确认）"
        scenes = [{"index": 1, "visual": "主题标题卡：" + request["theme"],
                   "narration": f"面向{audience}，本期围绕“{request['theme']}”介绍素材中已有的功能。",
                   "source_ids": [], "kind": "campaign_context"}]
        fact_sources = {}
        for mid in material_ids:
            for fact in self.materials[mid]["facts"]:
                fact_sources.setdefault(fact, []).append(mid)
        for fact, sources in fact_sources.items():
            scenes.append({"index": len(scenes)+1, "visual": " / ".join(self.materials[mid]["title"] for mid in sources),
                           "narration": fact, "source_ids": sources, "kind": "product_fact"})
        scenes.append({"index": len(scenes)+1, "visual": "主题回顾与体验入口",
                       "narration": f"如果你也关注“{request['theme']}”，可根据自己的需求了解和体验。",
                       "source_ids": [], "kind": "call_to_action"})
        script = {"theme": request["theme"], "audience": audience, "angle": angle, "material_ids": material_ids,
                  "creative_direction": {"text": angle, "status": "proposal_requires_review", "is_product_fact": False},
                  "scenes": scenes, "generator": "local_fact_template", "editable": True}
        sid = "script-" + fingerprint(script)[:12]
        self.state["scripts"][sid] = script
        return {"ok": True, "script_id": sid, "script": script}

    def calculate(self, script_id, production_mode):
        script = self.state["scripts"][script_id]
        req, prices = self.state["request"], self.pricing
        current = self.now().astimezone(timestamp(req["deadline"]).tzinfo)
        material_cost = sum((money(self.materials[mid]["cost"]) for mid in script["material_ids"]), Decimal(0))
        mode = prices["production_modes"][production_mode]
        rows = [
            ("materials", "素材授权/准备", material_cost, 0, []),
            ("script", "脚本整理", money(prices["script"]["cost"]), prices["script"]["minutes"], ["materials"]),
            ("production", mode["label"], money(mode["cost"]), mode["minutes"], ["script"]),
            ("review", "内容审核", money(prices["review"]["cost"]), prices["review"]["minutes"], ["production"]),
            ("publish", "人工确认与发布", money(prices["publish"]["cost"]), prices["publish"]["minutes"], ["review"]),
        ]
        total = sum((r[2] for r in rows), Decimal(0))
        total_minutes = sum(r[3] for r in rows)
        cursor = current
        steps = []
        for step_id, label, cost, minutes, depends in rows:
            end = cursor + timedelta(minutes=minutes)
            steps.append({"id": step_id, "name": label, "depends_on": depends, "cost": float(cost),
                          "duration_minutes": minutes, "start": cursor.isoformat(), "end": end.isoformat(),
                          "status": "planned"})
            cursor = end
        deadline = timestamp(req["deadline"])
        return {"script_id": script_id, "production_mode": production_mode, "total_cost": float(total),
                "currency": prices["currency"], "budget": req["budget"], "budget_gap": float(max(Decimal(0), total - money(req["budget"]))),
                "total_minutes": total_minutes, "estimated_finish": cursor.isoformat(), "deadline": req["deadline"],
                "deadline_gap_minutes": max(0, round((cursor-deadline).total_seconds()/60, 4)),
                "feasible": total <= money(req["budget"]) and cursor <= deadline,
                "steps": steps, "assumptions": prices["assumption"]}

    def estimate_plan(self, script_id, production_mode):
        if script_id not in self.state["scripts"]:
            return error("missing_dependency", "请先生成有效脚本")
        estimate = self.calculate(script_id, production_mode)
        eid = "estimate-" + fingerprint(estimate)[:12]
        self.state["estimates"][eid] = estimate
        self.state["latest_estimate_id"] = eid
        alternatives = []
        for mode in self.pricing["production_modes"]:
            candidate = self.calculate(script_id, mode)
            alternatives.append({k: candidate[k] for k in ("production_mode", "total_cost", "total_minutes", "feasible", "budget_gap", "deadline_gap_minutes")})
        return {"ok": True, "estimate_id": eid, "estimate": estimate, "alternatives": alternatives}

    def save_plan(self, estimate_id):
        estimate = self.state["estimates"].get(estimate_id)
        if not estimate:
            return error("missing_dependency", "不存在该估算，请先调用 estimate_plan")
        script = self.state["scripts"][estimate["script_id"]]
        if script.get("angle") not in SAFE_ANGLES or any(
            scene["narration"] not in self.materials[mid]["facts"]
            for scene in script["scenes"] for mid in scene["source_ids"]
        ):
            return error("unsupported_claim", "脚本未通过当前事实规则，请重新生成；旧版自由创意不可直接保存")
        # Recompute to prevent changed time or forged model feasibility from bypassing constraints.
        verified = self.calculate(estimate["script_id"], estimate["production_mode"])
        if not verified["feasible"]:
            return error("constraint_violation", "当前预算或截止时间不满足，未保存", estimate=verified)
        plan = {"request_id": self.state["request"]["request_id"], "theme": self.state["request"]["theme"],
                "audience": self.state["request"].get("audience", "未指定"), "script": self.state["scripts"][verified["script_id"]],
                "estimate": verified, "execution_status": "not_executed", "source_mode": self.state["mode"]}
        plan["campaign_brief"] = {
            "objective": "围绕用户主题向目标受众介绍有素材依据的功能，形成可执行内容方案",
            "theme": plan["theme"], "audience": plan["audience"],
            "creative_direction": plan["script"]["creative_direction"],
            "deliverables": ["带来源 ID 的可编辑脚本", "一份按所选制作方式执行的内容成片计划", "费用与阶段排期"],
            "pending_confirmation": ["发布渠道和账号", "创意角度及最终文案", "实际执行人员"],
            "success_criteria": ["费用不超过预算", "串行预计完成时间不晚于截止时间", "发布前完成人工审核"],
        }
        existing = self.store.get_plan(self.key)
        if existing:
            return {"ok": True, "saved": True, "duplicate": True, **existing}
        saved = self.store.save_plan(self.key, self.owner, plan)
        self.state["saved"] = saved
        return {"ok": True, "saved": True, "duplicate": False, **saved}

    def finish(self, args):
        saved = self.store.get_plan(self.key)
        if args["status"] == "completed" and not saved:
            return error("completion_rejected", "数据库中没有已保存方案，不能宣称完成")
        if saved and args["status"] != "completed":
            return error("status_mismatch", "方案已保存，请根据观察结果结束为 completed")
        # Model prose remains an untrusted proposal in the trace, not the final report.
        status = args["status"]
        missing = missing_fields(self.state["request"])
        if saved:
            e = saved["plan"]["estimate"]
            summary = f"方案 {saved['plan_id']} 已保存；费用 {e['total_cost']} / 预算 {e['budget']} {e['currency']}；预计耗时 {e['total_minutes']} 分钟，完成时间 {e['estimated_finish']}。制作、审核和发布均未执行。"
        elif missing:
            summary = "方案未保存，请补充：" + ", ".join(missing)
        elif status == "failed":
            last = next((s for s in reversed(self.state["steps"]) if s["status"] == "failed"), None)
            summary = "方案未保存；" + (f"失败步骤 {last['tool']}：{last['result']['error']['message']}。" if last else "模型停止执行，未报告可核验的工具失败。") + "成功产物已保留，可修复后显式续跑。"
        elif not self.state["scripts"]:
            summary = "方案未保存；尚无可用脚本，请补充与原始主题相关的素材或继续检索。"
        else:
            candidates = [self.calculate(sid, mode) for sid in self.state["scripts"] for mode in self.pricing["production_modes"]]
            best = min(candidates, key=lambda e: (e["budget_gap"], e["deadline_gap_minutes"]))
            summary = f"方案未保存；在已生成脚本及现有制作方式范围内，候选费用 {best['total_cost']}，预算缺口 {best['budget_gap']}，时间缺口 {best['deadline_gap_minutes']} 分钟。"
            summary += "可由用户调整预算、截止时间，或补充素材后重新规划；审核与发布等必需环节不可省略。"
        return {"ok": True, "terminal_status": status, "summary": summary,
                "summary_source": "verified_tool_state",
                "missing_fields": missing_fields(self.state["request"])}
