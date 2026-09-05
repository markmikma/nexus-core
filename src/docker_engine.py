import docker
import os
from src.db import register_or_update_app, log_deployment

try:
    client = docker.from_env()
except Exception as e:
    print(f"[!] Hiba a Docker csatlakozáskor: {e}")
    client = None

NETWORK_NAME = "nexus-net"

def get_nexus_network():
    """Megkeresi a docker-compose által létrehozott nexus-net hálózatot."""
    if not client:
        return None
    networks = client.networks.list(names=[NETWORK_NAME])
    if networks:
        return networks[0]
    # Ha nem létezik, létrehozza
    return client.networks.create(NETWORK_NAME, driver="bridge")

def stop_and_remove_container(container_name: str):
    """Megállítja és eltávolítja a korábbi konténert."""
    try:
        container = client.containers.get(container_name)
        print(f"[*] Meglévő konténer leállítása: {container_name}")
        container.stop(timeout=5)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
    except Exception as e:
        print(f"[!] Hiba a konténer eltávolításakor ({container_name}): {e}")

def build_and_deploy_app(app_name: str, app_dir: str, repo_url: str = "", internal_port: int = 8000) -> dict:
    if not client:
        raise RuntimeError("A Docker SDK nem tudott csatlakozni a daemonhoz.")

    target_network = get_nexus_network()
    container_name = f"nexus-app-{app_name}"
    image_tag = f"nexus-{app_name}:latest"
    
    print(f"[*] Build folyamat indítása: {app_name} ({app_dir})")
    register_or_update_app(app_name, repo_url, status="building")
    
    try:
        # 1. Docker image build
        image, build_logs = client.images.build(
            path=app_dir,
            tag=image_tag,
            rm=True,
            forcerm=True
        )
        print(f"[✓] Docker image felépült: {image_tag}")
        
        # 2. Régi konténer leállítása
        stop_and_remove_container(container_name)
        
        # 3. Traefik címkék
        labels = {
            "traefik.enable": "true",
            "traefik.docker.network": NETWORK_NAME,
            f"traefik.http.routers.{app_name}.rule": f"Host("{app_name}.localhost")",
            f"traefik.http.routers.{app_name}.entrypoints": "web",
            f"traefik.http.services.{app_name}.loadbalancer.server.port": str(internal_port)
        }
        
        # 4. Új konténer indítása
        container = client.containers.run(
            image=image_tag,
            name=container_name,
            detach=True,
            labels=labels,
            restart_policy={"Name": "unless-stopped"}
        )
        
        # Hálózathoz csatlakoztatás explicit módon
        target_network.connect(container)
        
        print(f"[✓] Konténer elindítva és hálózatra kötve: {container.short_id}")
        
        register_or_update_app(
            name=app_name,
            repo_url=repo_url,
            status="running",
            port=internal_port,
            container_id=container.short_id
        )
        log_deployment(app_name, status="success", logs="Sikeres deploy.")
        
        return {
            "status": "success",
            "app_name": app_name,
            "container_id": container.short_id,
            "url": f"http://{app_name}.localhost"
        }

    except Exception as e:
        error_msg = str(e)
        print(f"[!] Deploy hiba ({app_name}): {error_msg}")
        register_or_update_app(app_name, repo_url, status="failed")
        log_deployment(app_name, status="failed", logs=error_msg)
        return {"status": "error", "message": error_msg}