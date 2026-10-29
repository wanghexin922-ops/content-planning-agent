"""DeepSeek native function calling + explicitly labelled offline simulator."""
import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .common import PlannerError, dumps, missing_fields


def load_env(path):
    if not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PlannerError("config_error", ".env 每行应为 KEY=VALUE")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key.startswith("DEEPSEEK_"):
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key, value)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to a redirected endpoint.


class DeepSeekModel:
    mode = "live"

    def __init__(self):
        self.key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
        self.timeout = float(os.environ.get("DEEPSEEK_TIMEOUT", "60"))
        if not self.key or self.key in {"your-api-key", "sk-your-key"}:
            raise PlannerError("missing_api_key", "请在本地 .env 填写 DEEPSEEK_API_KEY；离线运行用 --mode mock")
        url = urlparse(self.base_url)
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise PlannerError("config_error", "DEEPSEEK_BASE_URL 必须为无凭据、无查询参数的 HTTPS 地址")
        if not 1 <= self.timeout <= 120:
            raise PlannerError("config_error", "DEEPSEEK_TIMEOUT 必须在 1–120 秒之间")

    def next_message(self, messages, tools):
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "stream": False, "max_tokens": 2048,
                   "thinking": {"type": "disabled"}}
        request = Request(self.base_url + "/chat/completions", data=dumps(payload).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
            choice = raw["choices"][0]
            if choice.get("finish_reason") == "length":
                raise PlannerError("model_truncated", "模型输出被截断；任务未完成，可续跑")
            message = choice["message"]
            # Do not store hidden reasoning, authentication headers, or raw HTTP bodies.
            result = {"role": "assistant", "content": message.get("content")}
            if message.get("tool_calls"):
                result["tool_calls"] = message["tool_calls"]
            return result
        except HTTPError as exc:
            hints = {401: "密钥无效", 402: "账户余额不足", 429: "请求限流"}
            raise PlannerError("model_http_error", f"DeepSeek HTTP {exc.code}: {hints.get(exc.code, '接口请求失败')}；未自动切换 Mock") from None
        except (URLError, TimeoutError, socket.timeout):
            raise PlannerError("model_network_error", "模型连接失败或超时；已保留成功步骤，可续跑") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise PlannerError("model_protocol_error", "模型接口返回无效结构") from None


def tool_message(name, args, number=0):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": f"mock-call-{number}", "type": "function", "function": {"name": name, "arguments": dumps(args)}}]}


class MockModel:
    """Rule-based observation simulator, never evidence of real model decisions."""
    mode = "mock"
    model = "offline-rule-simulator"

    def __init__(self, request):
        self.request = request
        self.counter = 0

    def next_message(self, messages, tools):
        self.counter += 1

        def call(name, reason, **args):
            return tool_message(name, dict(args, reason=reason), self.counter)

        missing = missing_fields(self.request)
        if missing:
            return call("finish", "输入缺少必要约束", status="needs_input", summary="请补充：" + ", ".join(missing))
        observations = [(i, json.loads(m["content"])) for i, m in enumerate(messages) if m["role"] == "tool"]
        if not observations:
            return call("search_materials", "需要找到主题对应的素材事实", query=self.request["theme"])
        index, last = observations[-1]
        if not last.get("ok"):
            previous = messages[index-1].get("tool_calls", [{}])[0].get("function", {})
            if last["error"].get("retryable") and previous.get("name"):
                args = json.loads(previous["arguments"])
                args["reason"] = "观察到可恢复工具错误，重试失败步骤并保留成功结果"
                return tool_message(previous["name"], args, self.counter)
            return call("finish", "观察到无法恢复的工具错误", status="failed", summary=last["error"]["message"])
        if last.get("saved"):
            return call("finish", "工具已确认方案保存成功", status="completed", summary="方案已保存，活动制作和发布尚未执行")
        if "materials" in last:
            if not last["materials"]:
                return call("finish", "检索结果为空，缺少事实依据", status="needs_input", summary="请补充相关素材或更明确的主题")
            return call("generate_script", "使用检索返回的首个相关素材生成脚本", material_ids=[last["materials"][0]["id"]], angle="功能介绍")
        if "estimate" in last:
            estimate = last["estimate"]
            if estimate["feasible"]:
                return call("save_plan", "估算满足预算和截止时间", estimate_id=last["estimate_id"])
            feasible = [a for a in last["alternatives"] if a["feasible"]]
            if feasible:
                return call("estimate_plan", "当前方案不可行，改用工具给出的可行制作方式并复核", script_id=estimate["script_id"], production_mode=feasible[0]["production_mode"])
            # Try cheaper retrieved materials before concluding no feasible solution.
            seen = {tuple(o["script"]["material_ids"]) for _, o in observations if o.get("ok") and "script" in o}
            found = [m for _, o in observations for m in o.get("materials", [])]
            cheaper = sorted((m for m in found if (m["id"],) not in seen), key=lambda m: m["cost"])
            if cheaper:
                return call("generate_script", "所有制作方式均不可行，尝试已检索到的更低成本素材", material_ids=[cheaper[0]["id"]], angle="功能介绍")
            best = min(last["alternatives"], key=lambda a: (a["budget_gap"], a["deadline_gap_minutes"]))
            return call("finish", "工具估算没有可行替代方案", status="incomplete", summary=f"未找到可行方案；最低费用 {best['total_cost']}，预算缺口 {best['budget_gap']}，超时 {best['deadline_gap_minutes']} 分钟")
        if "script_id" in last:
            return call("estimate_plan", "已取得脚本，先评估初始制作偏好", script_id=last["script_id"], production_mode=self.request.get("initial_mode", "premium"))
        return call("finish", "没有可继续的有效结果", status="incomplete", summary="缺少有效工具结果")
