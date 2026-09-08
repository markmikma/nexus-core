import hashlib
import hmac
import json
import subprocess
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "infra" / ".env"


def load_secret() -> str:
    for line in ENV_FILE.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "GITEA_WEBHOOK_SECRET":
            return value.strip()

    raise RuntimeError("GITEA_WEBHOOK_SECRET nem található az infra/.env fájlban.")


def current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()


secret = load_secret()
payload = {
    "ref": "refs/heads/main",
    "after": current_commit(),
    "repository": {
        "full_name": "nexusadmin/nexus-core",
    },
}

body = json.dumps(payload, separators=(",", ":")).encode()
signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

request = Request(
    "http://127.0.0.1/webhooks/gitea",
    data=body,
    method="POST",
    headers={
        "Host": "orchestrator.localhost",
        "Content-Type": "application/json",
        "X-Gitea-Event": "push",
        "X-Gitea-Delivery": str(uuid.uuid4()),
        "X-Gitea-Signature": signature,
    },
)

try:
    with urlopen(request) as response:
        print(f"HTTP {response.status}")
        print(response.read().decode())
except HTTPError as error:
    print(f"HTTP {error.code}")
    print(error.read().decode())
