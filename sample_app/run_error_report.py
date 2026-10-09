import json
import traceback
from pathlib import Path

import httpx


def main() -> None:
    try:
        from calculator import divide
        divide(1, 0)
    except Exception as exc:
        report = {
            "source": "Sample Python Calculator",
            "repository_id": "sample-python-calculator",
            "language": "python",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "file": "calculator.py",
            "line": 2,
            "severity": "high",
            "traceback": traceback.format_exc(),
        }
        token = input("AutoHeal bearer token: ").strip()
        response = httpx.post(
            "http://127.0.0.1:8000/api/ingest/alerts",
            json=report,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
