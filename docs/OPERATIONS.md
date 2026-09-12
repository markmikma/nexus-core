# Nexus-Core üzemeltetési kézikönyv

## Stack indítása és leállítása

```bash
cd ~/nexus-core/infra
DOCKER_BUILDKIT=0 COMPOSE_BAKE=false docker compose --profile ci up -d
docker compose --profile ci ps
```

A jelenlegi WSL Docker környezetben a Buildx hibája miatt a két környezeti változó
szükséges. Leállításkor a konténerek állnak le, a Gitea adatai, volume-ok és adatbázis
nem törlődnek:

```bash
docker compose --profile ci stop
```

## Állapot és logok

```bash
docker compose --profile ci ps
docker logs --tail=100 nexus-orchestrator
docker logs --tail=100 nexus-deployment-worker
docker logs --tail=100 nexus-gitea-runner
docker logs --tail=100 nexus-traefik
```

Az alap infrastruktúra (`nexus-traefik`, `nexus-gitea`, `nexus-orchestrator`)
Docker healthcheckkel rendelkezik. Az alkalmazás health endpointja:

```bash
curl --noproxy '*' -H 'Host: sample-app.localhost' http://127.0.0.1/healthz
```

## Deploy állapot lekérdezése

A státusz API tokennel védett. A token értékét ne írd shell historyba és ne commitold.

```bash
curl --noproxy '*' \
  -H 'Host: orchestrator.localhost' \
  -H "X-Nexus-Status-Token: $NEXUS_STATUS_TOKEN" \
  http://127.0.0.1/deployments
```

Alternatívaként az SQLite rekordok az orchestrator konténerből csak olvasva:

```bash
docker exec nexus-orchestrator python -c \
"import sqlite3; c=sqlite3.connect('/app/data/nexus.db'); print(c.execute('SELECT id,status,commit_hash,logs FROM deployment_jobs ORDER BY id DESC LIMIT 10').fetchall())"
```

## Sikertelen deploy és rollback

Minden új verzió candidate konténerként indul. A worker a candidate saját hálózati

## Security alert és első válasz

A Prometheus riaszt, ha tíz percen belül legalább öt hibás dashboard/API hitelesítés történik. A riasztás neve `NexusRepeatedFailedDashboardLogin`.

Első válasz: ellenőrizd a `GET /security-events` audit eseményeket, ne oszd meg a jelszót vagy tokent, szükség esetén cseréld a `NEXUS_DASHBOARD_PASSWORD` értéket az `infra/.env` fájlban, majd indítsd újra az orchestrátort. Ezután vizsgáld meg, hogy a sikertelen kérések folytatódnak-e.
