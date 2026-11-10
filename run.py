import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from nlrunner.agent import run_test

# Page text can hold characters the Windows console codepage cannot encode.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ap = argparse.ArgumentParser(description="Run a plain-English test case in a real browser.")
ap.add_argument("test_case")
ap.add_argument("--url", required=True, help="start URL")
ap.add_argument("--max-steps", type=int, default=25)
ap.add_argument("--headed", action="store_true", help="show the browser window")
ap.add_argument("--env-file", default=".env")
args = ap.parse_args()

load_dotenv(args.env_file, override=True)
for var in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
    if not os.environ.get(var):
        print(f"missing environment variable: {var}", file=sys.stderr)
        sys.exit(2)

started = datetime.now()
evidence = Path("runs") / started.strftime("%Y%m%d-%H%M%S")
evidence.mkdir(parents=True)
t0 = time.perf_counter()
result = run_test(args.test_case, args.url, args.max_steps, args.headed, str(evidence / "final.png"))
duration = f"{time.perf_counter() - t0:.1f}"
steps = "\n".join(result.history)
(evidence / "log.txt").write_text(
    f"TEST CASE: {args.test_case}\nURL: {args.url}\nMODEL: {os.environ['LLM_MODEL']}\n"
    f"STARTED: {started.isoformat(timespec='seconds')}\nDURATION: {duration}s\n\nSTEPS:\n{steps}\n\n"
    f"RESULT: {result.status}\nREASON: {result.reason}\nSTEPS TAKEN: {result.steps}\n", encoding="utf-8")
print(f"\nRESULT: {result.status}\nREASON: {result.reason}\nSTEPS: {result.steps}\n"
      f"DURATION: {duration}s\nEVIDENCE: {evidence}")
sys.exit({"PASS": 0, "FAIL": 1}.get(result.status, 2))
