#!/usr/bin/env python3
"""Quick HTTPS operational check for a local Nexus-Core installation."""
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

context = ssl._create_unverified_context()
for host, path in (
    ("nexus.localhost", "/dashboard"),
    ("orchestrator.localhost", "/readyz"),
    ("orchestrator.localhost", "/healthz"),
    ("gitea.localhost", "/api/healthz"),
    ("grafana.localhost", "/api/health"),
):
    request = Request(f"https://{host}{path}")
    try:
        with urlopen(request, context=context, timeout=10) as response:
            print(f"{host}{path}: HTTP {response.status}")
    except HTTPError as error:
        print(f"{host}{path}: HTTP {error.code}")
        raise
