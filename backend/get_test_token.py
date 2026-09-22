import json
import os
import sys

import requests

ADMIN_KEY = os.getenv("ADMIN_KEY")
if not ADMIN_KEY:
    print("ERROR: ADMIN_KEY environment variable is not set.", file=sys.stderr)
    raise SystemExit(1)

url = "http://localhost:8000/admin/drivers"
headers = {"x-admin-key": ADMIN_KEY}
payload = {"name": "TestDriver", "phone": "20000000"}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    try:
        body = response.json()
    except ValueError:
        body = response.text
    print(f"HTTP {response.status_code}")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    response.raise_for_status()
except requests.exceptions.RequestException as exc:
    print(f"ERROR: request failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

if isinstance(body, dict) and "token" in body:
    print(f"TOKEN={body['token']}")
else:
    print("ERROR: response did not include a token.", file=sys.stderr)
    raise SystemExit(1)
