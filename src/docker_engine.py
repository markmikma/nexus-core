import time
from pathlib import Path

import docker

from src.config import settings
from src.db import log_deployment, register_or_update_app
from src.image_security import scan_image

try:
    client = docker.from_env()
except Exception as error:
    print(f"[!] Hiba a Docker csatlakozáskor: {error}")
    client = None

NETWORK_NAME = settings.network_name
HEALTHCHECK_ATTEMPTS = 10
HEALTHCHECK_INTERVAL_SECONDS = 1


def get_nexus_network():
    """Finds or creates the shared Nexus Docker network."""
    if not client:
        return None
    networks = client.networks.list(names=[NETWORK_NAME])
    if networks:
        return networks[0]
    return client.networks.create(NETWORK_NAME, driver="bridge")


def get_container_or_none(container_name: str):
    """Returns a container when it exists, otherwise None."""
    try:
        return client.containers.get(container_name)
    except docker.errors.NotFound:
        return None


def wait_for_healthcheck(container, internal_port: int) -> tuple[bool, str]:
    """Checks the candidate from inside its own network namespace."""
    check_script = (
        "from urllib.request import urlopen\n"
        f"response = urlopen('http://127.0.0.1:{internal_port}/healthz', timeout=2)\n"
        "raise SystemExit(0 if response.status == 200 else 1)"
    )
    last_error = "Health check did not return a successful response."

    for attempt in range(1, HEALTHCHECK_ATTEMPTS + 1):
        container.reload()
        if container.status != "running":
            return False, f"Candidate container stopped unexpectedly (status={container.status})."

        result = container.exec_run(["python", "-c", check_script])
        if result.exit_code == 0:
            print(f"[✓] Health check sikeres ({attempt}/{HEALTHCHECK_ATTEMPTS}).")
            return True, "Health check passed."

        output = result.output.decode(errors="replace").strip()
        if output:
            last_error = output[-500:]
        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)

    return False, f"Health check failed: {last_error}"


def move_current_container_to_rollback_slot(container_name: str):
    """Preserves the current release until the candidate is proven healthy."""
    current = get_container_or_none(container_name)
    if current is None:
        return None

    rollback_name = f"{container_name}-rollback"
    stale_rollback = get_container_or_none(rollback_name)
    if stale_rollback is not None:
        stale_rollback.remove(force=True)

    print(f"[*] Előző verzió megőrzése rollbackhez: {container_name}")
    image_repository = f"nexus-{container_name.removeprefix('nexus-app-')}"
    current.image.tag(repository=image_repository, tag="rollback", force=True)
    current.stop(timeout=5)
    current.rename(rollback_name)
    return current


def restore_rollback_container(previous, container_name: str) -> str | None:
    """Restores the preserved release after a failed candidate deploy."""
    if previous is None:
        return None

    print("[*] Rollback indítása az előző működő verzióra.")
    previous.rename(container_name)
    previous.start()
    previous.reload()
    if previous.status != "running":
        raise RuntimeError("Rollback container could not be started.")
    print(f"[✓] Rollback sikeres: {previous.short_id}")
    return previous.short_id


def build_and_deploy_app(
    app_name: str,
    app_dir: str,
    repo_url: str = "",
    internal_port: int = 8000,
    commit_hash: str | None = None,
    image_scan_report_path: Path | None = None,
) -> dict:
    if not client:
        raise RuntimeError("A Docker SDK nem tudott csatlakozni a daemonhoz.")

    get_nexus_network()
    container_name = f"nexus-app-{app_name}"
    image_repository = f"nexus-{app_name}"
    image_tag = f"{image_repository}:{commit_hash[:12] if commit_hash else 'candidate'}"
    previous = None
    candidate = None
    promoted = False

    print(f"[*] Build folyamat indítása: {app_name} ({app_dir})")
    register_or_update_app(app_name, repo_url, status="building")

    try:
        image, _build_logs = client.images.build(
            path=app_dir,
            tag=image_tag,
            rm=True,
            forcerm=True,
        )
        print(f"[✓] Docker image felépült: {image_tag}")

        scan_summary = scan_image(client, image_tag, image_scan_report_path)
        if scan_summary["enabled"]:
            print("[✓] Image security gate passed: no blocking findings.")

        previous = move_current_container_to_rollback_slot(container_name)
        labels = {
            "traefik.enable": "true",
            "traefik.docker.network": NETWORK_NAME,
            f"traefik.http.routers.{app_name}.rule": f"Host(`{app_name}.localhost`)",
            f"traefik.http.routers.{app_name}.entrypoints": "web",
            f"traefik.http.services.{app_name}.loadbalancer.server.port": str(internal_port),
        }

        candidate = client.containers.run(
            image=image_tag,
            name=container_name,
            detach=True,
            labels=labels,
            network=NETWORK_NAME,
            restart_policy={"Name": "unless-stopped"},
        )
        print(f"[✓] Candidate elindult a {NETWORK_NAME} hálózaton: {candidate.short_id}")

        healthy, health_message = wait_for_healthcheck(candidate, internal_port)
        if not healthy:
            raise RuntimeError(f"Candidate health check failed. {health_message}")

        image.tag(repository=image_repository, tag="latest", force=True)
        if previous is not None:
            previous.remove(force=True)
            previous = None
        promoted = True

        register_or_update_app(
            name=app_name,
            repo_url=repo_url,
            status="running",
            port=internal_port,
            container_id=candidate.short_id,
        )
        log_deployment(
            app_name,
            status="success",
            commit_hash=commit_hash,
            logs="Health check passed; successful deployment.",
        )
        return {
            "status": "success",
            "app_name": app_name,
            "container_id": candidate.short_id,
            "url": f"http://{app_name}.localhost",
        }

    except Exception as error:
        error_msg = str(error)
        rollback_id = None
        print(f"[!] Deploy hiba ({app_name}): {error_msg}")

        if candidate is not None and not promoted:
            try:
                candidate.remove(force=True)
            except Exception as cleanup_error:
                error_msg = f"{error_msg} Candidate cleanup failed: {cleanup_error}"

        if previous is not None:
            try:
                rollback_id = restore_rollback_container(previous, container_name)
            except Exception as rollback_error:
                error_msg = f"{error_msg} Rollback failed: {rollback_error}"

        active_container = get_container_or_none(container_name)
        if active_container is not None:
            register_or_update_app(
                app_name,
                repo_url,
                status="running",
                port=internal_port,
                container_id=active_container.short_id,
            )
        else:
            register_or_update_app(app_name, repo_url, status="failed")

        log_deployment(
            app_name,
            status="failed",
            commit_hash=commit_hash,
            logs=f"{error_msg} Rollback container: {rollback_id or 'not available'}.",
        )
        return {"status": "error", "message": error_msg, "rollback_container_id": rollback_id}
