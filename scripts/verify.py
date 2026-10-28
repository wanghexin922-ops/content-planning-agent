"""Dependency-free test runner that also writes honest, reproducible evidence."""
from datetime import datetime, timezone
import io
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
buffer = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
report = (f"Executed at: {datetime.now(timezone.utc).isoformat()}\n"
          f"Python: {platform.python_version()}\nPlatform: {platform.system()}\n"
          "Command: python scripts/verify.py\n"
          "External model API: NOT called (transport tests use simulated responses)\n\n" + buffer.getvalue())
destination = ROOT / "examples/test-results.txt"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(report, encoding="utf-8")
print(report)
raise SystemExit(0 if result.wasSuccessful() else 1)
