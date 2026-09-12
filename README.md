# Nexus-Core

> A local-first DevSecOps and GitOps control plane for WSL2/Linux, built as a production-minded homelab platform.

Nexus-Core demonstrates a complete secure delivery path: a Git push is verified by CI, deployed from the exact commit SHA, security-gated, health-checked, and exposed through Traefik. It is designed to be inspectable in a technical interview, not just to look like a collection of containers.

## Why this project exists

This project was built to practice the systems behind modern platform engineering:

- Native Docker Engine on WSL2 instead of Docker Desktop
- Git hosting and CI/CD with self-hosted Gitea and Gitea Actions
- Exact-SHA GitOps deployments with automated health checks and rollback
- DevSecOps evidence: secret scanning, SAST, SBOM, dependency audit, image scanning, and DAST smoke checks
- Observability with Prometheus, Grafana, cAdvisor, structured audit events, and operational alerts
- Role-based dashboard access, signed sessions, HTTPS, and local secrets
- Controlled promotion across development, staging, and production environments

## Architecture

~~~text
Developer push
    |
    v
Gitea + Gitea Actions
    |  compile, unittest, secret scan, SAST, SBOM, pip-audit, DAST smoke
    v
Orchestrator API
    |  validates deploy token and queues exact commit SHA
    v
Deployment worker
    |  clones exact SHA, creates evidence, scans image, deploys candidate
    v
Docker Engine + Traefik
    |  health check -> promote or rollback
    v
dev / staging / production application routes

Prometheus + cAdvisor --> Grafana
SQLite audit trail --> Nexus dashboard
~~~

## Key capabilities

| Area | Implementation |
| --- | --- |
| Routing and TLS | Traefik v3, HTTPS redirect, local TLS certificate, Docker label discovery |
| Source control | Self-hosted Gitea over SSH, local Gitea Actions runner |
| GitOps deployment | CI notification carries the exact commit SHA; worker checks out that SHA before build |
| Safe release | Candidate container, internal health check, rollback slot, immutable commit evidence |
| Environment promotion | Automatic dev deployment; admin-only dev -> staging -> production promotion |
| AppSec | Secret scan, custom Python AST SAST, CycloneDX SBOM, pip-audit, Trivy image gate, DAST smoke test |
| Access control | Admin/viewer RBAC, scrypt password hashes, HMAC-signed HttpOnly session cookies |
| Observability | Prometheus metrics, Grafana dashboards, cAdvisor, audit trail, deployment backlog alert |
| Recovery | SQLite-consistent control-plane backup and restore validation |

## Local services

The stack uses a local self-signed certificate. Your browser may show a trust warning until you import the certificate into a trusted local store.

| Service | URL |
| --- | --- |
| Nexus dashboard | https://nexus.localhost/dashboard |
| Gitea | https://gitea.localhost |
| Orchestrator health | https://orchestrator.localhost/healthz |
| Orchestrator readiness | https://orchestrator.localhost/readyz |
| Grafana | https://grafana.localhost |
| Production sample app | https://sample-app.localhost |
| Development sample app | https://sample-app-dev.localhost |

## Quick start

Prerequisites:

- WSL2 Ubuntu with systemd enabled
- Native Docker Engine and Docker Compose v2
- Git and OpenSSL
- A local infra/.env created from .env.example

Generate local TLS material and the dashboard session secret:

~~~bash
cd ~/nexus-core
scripts/generate_local_tls.sh
~~~

Start the platform:

~~~bash
cd ~/nexus-core/infra
set -a && . ./.env && set +a
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false docker compose --profile ci up -d
~~~

Verify the running platform:

~~~bash
cd ~/nexus-core
python3 scripts/platform_status.py
curl -kLs https://orchestrator.localhost/metrics | rg nexus_deployment_queue_depth
~~~

## Delivery and security flow

1. A commit is pushed to main.
2. Gitea Actions clones the exact triggering SHA.
3. CI compiles Python, runs unit tests, scans tracked files for secrets, generates an SBOM, runs Python SAST and dependency audit, then performs a DAST smoke test.
4. A trusted CI token calls the orchestrator.
5. The worker clones the same SHA, regenerates security evidence, runs the dependency and image gates, and builds a candidate container.
6. The candidate must pass its internal /healthz check.
7. A healthy candidate is promoted; an unhealthy one is removed and the prior release is restored.
8. The release is recorded in SQLite and available from the dashboard/audit trail.

## Security model

- No private keys, generated TLS certificates, local .env, backups, or runtime data are committed.
- Dashboard passwords are verified using scrypt hashes.
- The service receives password hashes, not dashboard plaintext passwords.
- Sessions are signed with a dedicated Docker secret and use HttpOnly, Secure, and SameSite=Strict cookie controls.
- Viewer accounts can inspect deployments but cannot read security reports or audit events.
- Admin-only promotion preserves the verified commit SHA across environments.
- CI rejects common high-risk Python execution patterns and hard-coded secrets.

## Tests and checks

~~~bash
cd ~/nexus-core
. venv/bin/activate
python -m unittest discover -s tests -v
python scripts/scan_secrets.py --output /tmp/secret-scan.json
python scripts/scan_python_security.py --output /tmp/python-sast.json
python scripts/security_smoke.py
python scripts/backup_nexus.py --output-root /tmp/nexus-backups
~~~

## Backup and recovery

scripts/backup_nexus.py creates an integrity-safe SQLite control-plane backup and stores the Compose topology alongside a manifest. scripts/verify_backup.py validates a backup before a human-approved restore.

Gitea repository data requires a separate Gitea dump and off-host retention policy; this is intentionally called out as the next recovery improvement.

## Project boundaries and next steps

Nexus-Core is a local homelab and portfolio project, not a claim of production readiness. The next logical upgrades are:

- trusted certificates and DNS instead of local self-signed TLS
- separate host/account boundaries for staging and production
- Gitea dump plus encrypted off-host backups
- Alertmanager notification routing and SLO tracking
- richer SAST rules and authenticated dynamic security testing

## Documentation

- [Operations manual](docs/OPERATIONS.md)
- [Test checklist](docs/TEST_CHECKLIST.md)
- Detailed technical interview notes are maintained locally in the accompanying project documentation.

## License

No license is currently declared. Do not reuse the code outside personal evaluation without the repository owner's permission.
