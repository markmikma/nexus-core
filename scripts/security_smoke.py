#!/usr/bin/env python3
"""Authenticated-surface-free DAST smoke test for the running control plane."""
import os
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

base_url = os.getenv("NEXUS_DAST_BASE_URL", "https://nexus.localhost").rstrip("/")
host = os.getenv("NEXUS_DAST_HOST", "")
context = ssl._create_unverified_context()

def request(path):
    headers = {"Host": host} if host else {}
    request = Request(base_url + path, headers=headers)
    try:
        with urlopen(request, context=context, timeout=10) as response:
            return response.status, dict(response.headers.items())
    except HTTPError as error:
        return error.code, dict(error.headers.items())

dashboard_status, headers = request("/dashboard")
if dashboard_status != 200:
    raise SystemExit(f"Dashboard endpoint failed: HTTP {dashboard_status}")
required_headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
for name, expected in required_headers.items():
    if headers.get(name) != expected:
        raise SystemExit(f"Missing or invalid security header: {name}")
status, _ = request("/deployments")
if status != 401:
    raise SystemExit(f"Unauthenticated API must return HTTP 401, received {status}")
print("DAST smoke passed: security headers and unauthenticated API boundary verified.")
