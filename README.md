# Nexus-Core

Helyben futó, konténerizált DevSecOps és GitOps homelab WSL2/Linux környezethez.

A projekt egy Gitea push eseményt biztonságosan CI ellenőrzésen vezet át, majd az
orchestrator és a deployment worker pontosan azt a commitot telepíti Dockerbe.

## Fő komponensek

| Komponens | Feladata | Elérés |
| --- | --- | --- |
| Traefik | Reverse proxy és HTTP routing | `http://localhost`, dashboard: `http://localhost:8080` |
| Gitea | Helyi Git szerver és Actions | `http://gitea.localhost` |
| Orchestrator | Webhook és deploy API | `http://orchestrator.localhost/healthz` |
| Deployment worker | Security gate, build, health check, rollback | belső szolgáltatás |
| Gitea runner | CI workflow-k futtatása | belső szolgáltatás |
| Sample app | Referencia GitOps alkalmazás | `http://sample-app.localhost` |

## Deploy folyamat

```text
git push (main)
  -> Gitea webhook rögzíti a push eseményt
  -> Gitea Actions: fordítás, unit teszt, pip-audit
  -> hitelesített CI trigger az orchestrator felé
  -> worker: pontos commit klónozása, új image build
  -> candidate container + /healthz ellenőrzés
  -> siker: Traefik kiszolgálás; hiba: automatikus rollback
```

## Gyors ellenőrzés

WSL terminálban, a repository gyökeréből:

```bash
cd ~/nexus-core/infra
docker compose --profile ci ps

curl --noproxy '*' -H 'Host: gitea.localhost' http://127.0.0.1/api/healthz
curl --noproxy '*' -H 'Host: orchestrator.localhost' http://127.0.0.1/healthz
curl --noproxy '*' -H 'Host: sample-app.localhost' http://127.0.0.1/healthz
```

Részletes indítási, hibakeresési és visszaállítási leírás: [docs/OPERATIONS.md](docs/OPERATIONS.md).
Az ismételhető ellenőrzések listája: [docs/TEST_CHECKLIST.md](docs/TEST_CHECKLIST.md).

## Biztonsági alapelvek

