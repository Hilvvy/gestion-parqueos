import json
import os
import subprocess
import sys
from pathlib import Path


def test_two_requests_for_last_space(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = os.environ | {
        "PARKING_DATABASE_PATH": str(tmp_path / "concurrency.sqlite3"),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, str(root / "parking/tests/concurrency_worker.py")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout.strip().splitlines()[-1])
    assert output == {"outcomes": ["confirmed", "rejected"], "confirmed_count": 1}
