import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from content_planner.agent import run_agent
from content_planner.common import PlannerError, read_json, timestamp, validate_request
from content_planner.model import MockModel, tool_message
from content_planner.storage import Store

ROOT = Path(__file__).resolve().parents[1]
NOW = timestamp("2026-10-28T10:00:00+08:00")


class SequenceModel:
    mode = "mock"
    model = "test-sequence-not-real-model"

    def __init__(self, actions):
        self.actions = iter(actions)

    def next_message(self, messages, tools):
        return next(self.actions)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "test.sqlite")
        self.addCleanup(self.store.close)
        self.materials = read_json(ROOT / "data/materials.json")
        self.pricing = read_json(ROOT / "data/pricing.json")
        self.request = {"request_id": "test-1", "theme": "推广视频字幕工具", "budget": 15,
                        "deadline": "2026-10-29T18:00:00+08:00", "initial_mode": "premium"}

    def run_task(self, model=None, **kwargs):
        return run_agent(self.request, model or MockModel(self.request), self.store, self.materials,
                         self.pricing, now=kwargs.pop("now", lambda: NOW), **kwargs)

    def test_normal_saved_plan_has_dependencies_and_grounded_facts(self):
        out = self.run_task()
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["total_cost"], 12)
        self.assertEqual(out["plan"]["estimate"]["total_minutes"], 240)
        self.assertEqual(out["plan"]["execution_status"], "not_executed")
        phases = out["plan"]["estimate"]["steps"]
        self.assertTrue(all(p["status"] == "planned" for p in phases))
        for index, phase in enumerate(phases):
            self.assertTrue(set(phase["depends_on"]) <= {p["id"] for p in phases[:index]})
        facts = {m["id"]: m["facts"] for m in self.materials}
        for scene in out["plan"]["script"]["scenes"]:
            for source in scene["source_ids"]:
                self.assertIn(scene["narration"], facts[source])
        self.assertEqual(out["trace"][-1]["next_action"], "end")

    def test_over_budget_changes_mode_after_observation(self):
        self.request["budget"] = 10
        out = self.run_task()
        estimates = [s["result"]["estimate"] for s in out["steps"] if s["tool"] == "estimate_plan"]
        self.assertEqual([e["total_cost"] for e in estimates], [12, 8])
        self.assertEqual(out["plan"]["estimate"]["production_mode"], "basic")
        self.assertEqual(self.request["budget"], 10)

    def test_missing_constraints_never_invented(self):
        for field in ("budget", "deadline"):
            with self.subTest(field=field):
                req = dict(self.request, request_id="missing-" + field)
                req.pop(field)
                out = run_agent(req, MockModel(req), self.store, self.materials, self.pricing, now=lambda: NOW)
                self.assertEqual(out["status"], "needs_input")
                self.assertEqual(out["missing_fields"], [field])
                self.assertFalse(out["saved"])
                self.assertEqual([s["tool"] for s in out["steps"]], ["finish"])

    def test_transient_failure_preserves_search(self):
        out = self.run_task(faults={"generate_script": 1})
        self.assertEqual(out["status"], "completed")
        self.assertEqual(sum(s["tool"] == "search_materials" for s in out["steps"]), 1)
        statuses = [s["status"] for s in out["steps"] if s["tool"] == "generate_script"]
        self.assertEqual(statuses, ["failed", "succeeded"])

    def test_permanent_save_failure_not_reported_success(self):
        out = self.run_task(faults={"save_plan": -1})
        self.assertEqual(out["status"], "failed")
        self.assertFalse(out["saved"])
        self.assertIsNone(self.store.get_plan("mock:test-1"))
        self.assertTrue(out["successful_artifacts"]["scripts"])

    def test_real_sqlite_failure_is_explicit(self):
        with patch.object(self.store, "save_plan", side_effect=sqlite3.OperationalError("disk full")):
            out = self.run_task(max_steps=6)
        self.assertFalse(out["saved"])
        errors = [s["result"]["error"]["code"] for s in out["steps"] if s["status"] == "failed"]
        self.assertIn("storage_error", errors)

    def test_duplicate_executes_no_new_tools_and_saves_once(self):
        first = self.run_task()
        second = self.run_task()
        self.assertTrue(second["replayed"])
        self.assertEqual(first["plan_id"], second["plan_id"])
        self.assertEqual(first["tool_calls"], second["tool_calls"])
        self.assertEqual(second["trace"][-1]["event"], "idempotent_replay")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM plans").fetchone()[0], 1)

    def test_same_id_changed_input_rejected(self):
        self.run_task()
        self.request["budget"] = 20
        with self.assertRaisesRegex(PlannerError, "输入已改变"):
            self.run_task()

    def test_impossible_budget_has_no_saved_plan(self):
        self.request["budget"] = 2
        out = self.run_task()
        self.assertEqual(out["status"], "incomplete")
        self.assertFalse(out["saved"])
        self.assertIn("预算缺口", out["summary"])

    def test_deadline_forces_faster_mode(self):
        self.request["deadline"] = "2026-10-28T12:00:00+08:00"
        out = self.run_task()
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["plan"]["estimate"]["production_mode"], "basic")
        self.assertEqual(timestamp(out["plan"]["estimate"]["estimated_finish"]), timestamp(self.request["deadline"]))

    def test_impossible_deadline_stops(self):
        self.request["deadline"] = "2026-10-28T10:10:00+08:00"
        out = self.run_task()
        self.assertEqual(out["status"], "incomplete")
        self.assertFalse(out["saved"])

    def test_no_materials_requests_input(self):
        self.request["theme"] = "量子芯片实验室"
        out = self.run_task()
        self.assertEqual(out["status"], "needs_input")
        self.assertFalse(out["successful_artifacts"]["scripts"])

    def test_step_limit_and_resume_without_redo(self):
        first = self.run_task(max_steps=2)
        self.assertEqual(first["status"], "incomplete_limit")
        second = self.run_task(resume=True, max_steps=16)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(sum(s["tool"] == "search_materials" for s in second["steps"]), 1)
        self.assertEqual(sum(s["tool"] == "generate_script" for s in second["steps"]), 1)

    def test_failure_resume_uses_successful_script(self):
        first = self.run_task(faults={"estimate_plan": 1}, max_steps=3)
        self.assertEqual(first["status"], "incomplete_limit")
        second = self.run_task(resume=True)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(first["successful_artifacts"]["scripts"], second["successful_artifacts"]["scripts"])

    def test_failed_task_does_not_silently_retry(self):
        first = self.run_task(faults={"save_plan": -1})
        second = self.run_task()
        self.assertEqual(first["status"], second["status"])
        self.assertEqual(first["tool_calls"], second["tool_calls"])
        self.assertTrue(second["replayed"])

    def test_hallucinated_completion_rejected(self):
        model = SequenceModel([tool_message("finish", {"status": "completed", "summary": "已保存", "reason": "测试伪造成功"})])
        out = self.run_task(model, max_steps=1)
        self.assertEqual(out["status"], "incomplete_limit")
        self.assertFalse(out["saved"])
        self.assertEqual(out["steps"][0]["result"]["error"]["code"], "completion_rejected")

    def test_unknown_tool_and_bad_arguments_are_observations(self):
        actions = [tool_message("delete_everything", {"reason": "test"}),
                   tool_message("search_materials", {"query": 2, "reason": "test"}),
                   tool_message("generate_script", {"material_ids": ["P01", "P01"], "angle": "test", "reason": "test"})]
        out = self.run_task(SequenceModel(actions), max_steps=3)
        self.assertTrue(all(s["status"] == "failed" for s in out["steps"]))
        self.assertEqual(out["status"], "incomplete_limit")

    def test_invalid_json_becomes_tool_error(self):
        message = tool_message("search_materials", {"reason": "test", "query": "字幕"})
        message["tool_calls"][0]["function"]["arguments"] = "{broken"
        out = self.run_task(SequenceModel([message]), max_steps=1)
        self.assertEqual(out["steps"][0]["result"]["error"]["code"], "invalid_action")

    def test_non_tool_responses_have_model_round_cap(self):
        out = self.run_task(SequenceModel([{"role": "assistant", "content": "已成功"}]*3), max_model_calls=3)
        self.assertEqual(out["model_calls"], 3)
        self.assertEqual(out["tool_calls"], 0)
        self.assertEqual(out["status"], "incomplete_limit")

    def test_parallel_calls_have_no_side_effects(self):
        message = tool_message("search_materials", {"query": "字幕", "reason": "test"})
        second = copy.deepcopy(message["tool_calls"][0])
        second["id"] = "another-call"
        message["tool_calls"].append(second)
        out = self.run_task(SequenceModel([message]), max_model_calls=1)
        self.assertEqual(out["tool_calls"], 0)
        self.assertFalse(out["successful_artifacts"]["retrieved_ids"])

    def test_missing_script_cannot_estimate_or_save(self):
        model = SequenceModel([tool_message("estimate_plan", {"script_id": "fake", "production_mode": "basic", "reason": "test"}),
                               tool_message("save_plan", {"estimate_id": "fake", "reason": "test"})])
        out = self.run_task(model, max_steps=2)
        self.assertTrue(all(s["result"]["error"]["code"] == "missing_dependency" for s in out["steps"]))

    def test_save_cannot_bypass_budget(self):
        self.request["budget"] = 10
        self.run_task(max_steps=3)  # initial premium estimate costs 12
        class ForceSave(MockModel):
            def next_message(inner, messages, tools):
                estimate = json.loads(messages[-1]["content"])
                return tool_message("save_plan", {"estimate_id": estimate["estimate_id"], "reason": "测试强制保存超预算方案"})
        out = self.run_task(ForceSave(self.request), resume=True, max_steps=4)
        self.assertFalse(out["saved"])
        self.assertEqual(out["steps"][-1]["result"]["error"]["code"], "constraint_violation")

    def test_save_rechecks_elapsed_time(self):
        self.request["deadline"] = "2026-10-28T14:00:00+08:00"
        self.run_task(max_steps=3)  # exactly four hours was feasible
        out = self.run_task(resume=True, max_steps=4, now=lambda: timestamp("2026-10-28T10:01:00+08:00"))
        self.assertFalse(out["saved"])
        self.assertEqual(out["steps"][-1]["result"]["error"]["code"], "constraint_violation")

    def test_replaced_material_facts_change_script(self):
        self.materials[0]["facts"] = ["仅支持手动字幕编辑"]
        out = self.run_task()
        facts = [s["narration"] for s in out["plan"]["script"]["scenes"]]
        self.assertIn("仅支持手动字幕编辑", facts)
        self.assertNotIn("支持为视频添加字幕", facts)

    def test_changed_data_does_not_reuse_old_state(self):
        self.run_task(max_steps=2)
        self.pricing["production_modes"]["premium"]["cost"] = 999
        with self.assertRaisesRegex(PlannerError, "费用表已改变"):
            self.run_task(resume=True)

    def test_decimal_budget_exact_boundary(self):
        self.pricing["script"]["cost"] = 0.1
        self.pricing["review"]["cost"] = 0.2
        self.request["budget"] = 10.3
        out = self.run_task()
        self.assertEqual(out["total_cost"], 10.3)
        self.assertEqual(out["status"], "completed")

    def test_same_task_concurrent_lock_rejected(self):
        from content_planner.agent import initial_state
        from content_planner.common import fingerprint
        state = initial_state(self.request, MockModel(self.request), fingerprint({"materials": self.materials, "pricing": self.pricing}))
        other = Store(Path(self.tmp.name) / "test.sqlite")
        try:
            with self.store.acquire("mock:test-1", self.request, state):
                with self.assertRaisesRegex(PlannerError, "正在执行"):
                    with other.acquire("mock:test-1", self.request, state):
                        pass
        finally:
            other.close()

    def test_recover_plan_if_checkpoint_after_save_was_lost(self):
        self.run_task(max_steps=4)  # plan is durable, model has not finished yet
        out = self.run_task()
        self.assertEqual(out["status"], "completed")
        self.assertTrue(out["replayed"])
        self.assertTrue(out["saved"])

    def test_invalid_budgets_and_unzoned_deadlines(self):
        for value in (-1, True, float("nan"), float("inf"), "10", 0.001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_request(dict(self.request, budget=value))
        with self.assertRaises(ValueError):
            validate_request(dict(self.request, deadline="2026-10-29T18:00:00"))

    def test_model_error_preserves_artifacts(self):
        self.run_task(max_steps=2)
        class FailingModel(MockModel):
            def next_message(inner, messages, tools):
                raise PlannerError("model_network_error", "模型超时")
        out = self.run_task(FailingModel(self.request), resume=True)
        self.assertEqual(out["status"], "failed")
        self.assertTrue(out["successful_artifacts"]["scripts"])
        recovered = self.run_task(resume=True)
        self.assertEqual(recovered["status"], "completed")

    def test_audience_and_theme_reach_script_and_campaign_brief(self):
        self.request.update(theme="推广带字幕的求职简历介绍视频制作", audience="应届毕业生")
        out = self.run_task()
        plan = out["plan"]
        self.assertEqual(plan["audience"], "应届毕业生")
        self.assertEqual(plan["script"]["audience"], plan["audience"])
        self.assertIn(self.request["theme"], plan["script"]["scenes"][0]["narration"])
        self.assertIn("应届毕业生", plan["script"]["scenes"][0]["narration"])
        self.assertFalse(plan["campaign_brief"]["creative_direction"]["is_product_fact"])
        self.assertEqual(plan["campaign_brief"]["creative_direction"]["status"], "proposal_requires_review")

    def test_schedule_uses_deadline_timezone(self):
        out = self.run_task(now=lambda: timestamp("2026-10-28T02:00:00+00:00"))
        self.assertEqual(out["plan"]["estimate"]["estimated_finish"], "2026-10-28T14:00:00+08:00")

    def test_query_rewrite_cannot_replace_original_topic(self):
        self.request["theme"] = "量子芯片实验室活动"
        model = SequenceModel([tool_message("search_materials", {"query": "字幕视频产品宣传", "reason": "测试偏离原主题的改写"})])
        out = self.run_task(model, max_steps=1)
        self.assertEqual(out["steps"][0]["result"]["count"], 0)
        self.assertFalse(out["successful_artifacts"]["retrieved_ids"])
        self.assertFalse(out["saved"])


if __name__ == "__main__":
    unittest.main()
