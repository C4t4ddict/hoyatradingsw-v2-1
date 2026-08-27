from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_ml_collection import collect_once


ROOT = Path(__file__).resolve().parent
MAX_SECONDS = int(os.getenv("ML_RETRAIN_MAX_SECONDS", str(8 * 60 * 60)))
INTERVAL_SEC = int(os.getenv("ML_RETRAIN_INTERVAL_SEC", str(60 * 60)))
TRAIN_SCRIPT = ROOT / "train_model_bidirectional.py"


def run_training(command: list[str] | None = None) -> dict:
    selected = command or [sys.executable, str(TRAIN_SCRIPT)]
    completed = subprocess.run(
        selected,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": selected,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_cycle() -> dict:
    started_at = datetime.now(timezone.utc)
    collection = collect_once(now=started_at)
    training = run_training()
    return {
        "started_at": started_at.isoformat(),
        "ok": training["exit_code"] == 0,
        "collection": collection,
        "training": training,
    }


def main() -> None:
    if MAX_SECONDS <= 0 or INTERVAL_SEC <= 0:
        raise ValueError("ML retrain duration and interval must be positive")

    started = time.monotonic()
    while time.monotonic() - started < MAX_SECONDS:
        try:
            result = run_cycle()
        except Exception as exc:
            result = {
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        print(json.dumps(result, ensure_ascii=False), flush=True)

        remaining = MAX_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            break
        time.sleep(min(INTERVAL_SEC, remaining))


if __name__ == "__main__":
    main()
