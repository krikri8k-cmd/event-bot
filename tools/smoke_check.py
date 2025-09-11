# tools/smoke_check.py
import os
import sys

import requests

BASE = os.environ.get("BASE_PUBLIC_URL") or os.environ.get("SMOKE_BASE_URL")

if not BASE:
    print("SMOKE_BASE_URL/BASE_PUBLIC_URL is required", file=sys.stderr)
    sys.exit(2)


def main():
    """Выполняет smoke-тесты для API"""
    try:
        # 1) Health check
        print("Тестируем health endpoint...")
        r = requests.get(f"{BASE}/health", timeout=15)
        print(f"Health: {r.status_code} - {r.text[:200]}")

        # 2) Тест синка baliforum
        print("Тестируем baliforum sync...")
        payload = {"lat": -8.6500, "lng": 115.2167, "radius_km": 15.0}
        r2 = requests.post(f"{BASE}/events/sources/baliforum/sync", json=payload, timeout=30)
        print(f"Baliforum sync: {r2.status_code} - {r2.text[:400]}")

        print("Smoke tests completed successfully!")

    except Exception as e:
        print(f"Smoke test failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
