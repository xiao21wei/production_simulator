#!/usr/bin/env python3
"""Send two DRL and two HLS reoptimization API requests."""

import json
import time
import urllib.request


BASE_URL = "http://127.0.0.1:8000"
WAIT_BETWEEN_REQUESTS_SECONDS = 20.0
REQUESTS = [
    ("DRL", {"num_samples": 1, "seed": 0}),
    ("HLS", {"seed": 0, "total_time_seconds": 20}),
    ("DRL", {"num_samples": 1, "seed": 1}),
    ("HLS", {"seed": 1, "total_time_seconds": 20}),
]


def send_reoptimization(method, config):
    payload = json.dumps(
        {
            "method": method,
            "config": config,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/api/reoptimize-command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("success"):
        raise RuntimeError(result.get("error", "reoptimization failed"))
    print(
        json.dumps(
            {
                "method": method,
                "config": config,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main():
    for index, (method, config) in enumerate(REQUESTS):
        send_reoptimization(method, config)
        if index < len(REQUESTS) - 1:
            time.sleep(WAIT_BETWEEN_REQUESTS_SECONDS)


if __name__ == "__main__":
    main()
