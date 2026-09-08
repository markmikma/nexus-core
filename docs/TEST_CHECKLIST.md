# Nexus-Core ellenőrzőlista

Ezt a listát egy nagyobb módosítás, Docker/WSL frissítés vagy release előtt érdemes
végigvenni. A jelölőnégyzetek a kézi elfogadási tesztet dokumentálják.

## Infrastruktúra

- [ ] `docker info` sikeres a WSL terminálban.
- [ ] `cd ~/nexus-core/infra && docker compose --profile ci ps` minden elvárt szolgáltatást mutat.
- [ ] Traefik, Gitea és orchestrator státusza `healthy`.
- [ ] `http://gitea.localhost/api/healthz` a Host headerrel `pass` választ ad.
- [ ] `http://orchestrator.localhost/healthz` `status: ok` választ ad.

## CI és deploy

- [ ] Egy új, ártalmatlan commit a `main` ágra pusholható Giteára.
- [ ] A Gitea Actions `Verify, test and audit` job zöld.
- [ ] A job lefuttatja a Python fordítási ellenőrzést, unit teszteket és `pip-audit`-ot.
- [ ] A deploy job hitelesített kérést küld az orchestratornak.
- [ ] A worker a naplóban a pontos commit checkoutját írja ki.
- [ ] A deployment rekord státusza `success`.

## Alkalmazás és routing

```bash
curl --noproxy '*' -i -H 'Host: sample-app.localhost' http://127.0.0.1/healthz
curl --noproxy '*' -i -H 'Host: sample-app.localhost' http://127.0.0.1/
```

- [ ] Mindkét kérés `HTTP/1.1 200` választ ad.
- [ ] Az alkalmazás válasza a várt GitOps verziót mutatja.
- [ ] A `nexus-app-sample-app` konténer fut és a `nexus-net` hálózaton van.

## Kontrollált rollback-teszt

Ezt csak elkülönített teszt commiton vagy teszt repositoryban végezd, ne a működő
`main` release-en. A cél: egy induló, de `/healthz` végponton hibázó candidate.

- [ ] Kiindulásként rögzítve van egy működő alkalmazás commit hash-e és válasza.
- [ ] A teszt candidate nem ad 200 választ `/healthz` útvonalon.
- [ ] A worker logban megjelenik a `Rollback indítása` és `Rollback sikeres` sor.
- [ ] A deployment rekord `failed`, de a korábbi alkalmazás továbbra is 200 választ ad.
- [ ] A visszaállítás után új, helyes commit deploya ismét sikeres.

## Titkok és repository higiénia

- [ ] `git status --short` nem mutat `infra/.env`, `infra/secrets/` vagy `data/nexus.db` fájlt.
- [ ] A Gitea `NEXUS_DEPLOY_TOKEN` és `GITEA_TOKEN` secret be van állítva.
- [ ] A deploy kulcs csak olvashatóan van bemountolva a workerbe.
- [ ] A Traefik dashboard (`:8080`) csak lokális fejlesztői környezetben elérhető.
