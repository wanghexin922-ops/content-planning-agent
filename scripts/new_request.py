"""Create a fresh request with a future deadline, so demos do not expire."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from content_planner.common import write_json

parser = argparse.ArgumentParser()
parser.add_argument("--budget", type=float, default=10)
parser.add_argument("--theme", default="推广一款视频字幕工具")
parser.add_argument("--audience", help="明确目标受众；省略时不擅自设定")
parser.add_argument("--hours", type=int, default=24)
parser.add_argument("--out", type=Path, default=ROOT / "runtime/request.json")
args = parser.parse_args()
req = {"request_id": "campaign-" + uuid.uuid4().hex[:12], "theme": args.theme, "budget": args.budget,
       "deadline": (datetime.now(timezone(timedelta(hours=8)))+timedelta(hours=args.hours)).isoformat(),
       "initial_mode": "premium"}
if args.audience:
    req["audience"] = args.audience
write_json(args.out, req)
print(str(args.out.resolve()))
