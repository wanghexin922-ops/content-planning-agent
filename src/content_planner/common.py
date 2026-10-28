"""Small, explicit validation helpers; no runtime dependencies."""
import hashlib
import json
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def fingerprint(value):
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("时间必须包含时区，例如 +08:00")
    return dt


def money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("预算必须为非负有限数字")
    result = Decimal(str(value))
    if result.as_tuple().exponent < -2:
        raise ValueError("预算最多两位小数")
    return result


def validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("输入必须是 JSON 对象")
    allowed = {"request_id", "theme", "budget", "deadline", "initial_mode", "audience"}
    if set(request) - allowed:
        raise ValueError("未知输入字段: " + ", ".join(sorted(set(request) - allowed)))
    for name in ("request_id", "theme"):
        if not isinstance(request.get(name), str) or not request[name].strip():
            raise ValueError(name + " 必须为非空字符串")
    if len(request["request_id"]) > 100 or len(request["theme"]) > 1000:
        raise ValueError("request_id 或 theme 过长")
    if request.get("budget") is not None:
        money(request["budget"])
    if request.get("deadline") is not None:
        timestamp(request["deadline"])
    if request.get("initial_mode", "premium") not in {"premium", "basic", "slideshow"}:
        raise ValueError("initial_mode 必须是 premium/basic/slideshow；仅为初始偏好，可调整")
    if "audience" in request and (not isinstance(request["audience"], str) or len(request["audience"]) > 500):
        raise ValueError("audience 必须为不超过 500 字的字符串")


def missing_fields(request):
    return [name for name in ("budget", "deadline") if request.get(name) is None]


class PlannerError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
