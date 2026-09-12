"""Centralized runtime configuration for Nexus-Core services."""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _secret_or_environment(name: str) -> str:
    secret_file = os.getenv(f"{name}_FILE", "")
    if secret_file:
        try:
            return Path(secret_file).read_text().strip()
        except OSError:
            pass
    return os.getenv(name, "")


@dataclass(frozen=True)
class Settings:
    database_path: Path
    webhook_secret: str
    allowed_repository: str
    repository_url: str
    status_token: str
    deploy_token: str
    session_secret: str
    dashboard_cookie_secure: bool
    dashboard_admin_hash: str
    dashboard_viewer_hash: str
    poll_interval_seconds: int
    network_name: str
    image_scan_enabled: bool
    image_scan_severities: str
    trivy_ignore_unfixed: bool
    trivy_image: str
    trivy_cache_volume: str

    @classmethod
    def from_environment(cls) -> "Settings":
        database_path = Path(
            os.getenv("NEXUS_DB_PATH", str(PROJECT_ROOT / "data" / "nexus.db"))
        ).expanduser()
        return cls(
            database_path=database_path,
            webhook_secret=_secret_or_environment("GITEA_WEBHOOK_SECRET"),
            allowed_repository=os.getenv("NEXUS_ALLOWED_REPOSITORY", ""),
            repository_url=os.getenv("GITEA_REPOSITORY_URL", ""),
            status_token=_secret_or_environment("NEXUS_STATUS_TOKEN"),
            deploy_token=_secret_or_environment("NEXUS_DEPLOY_TOKEN"),
            session_secret=_secret_or_environment("NEXUS_SESSION_SECRET"),
            dashboard_cookie_secure=_environment_flag("NEXUS_DASHBOARD_COOKIE_SECURE", True),
            dashboard_admin_hash=os.getenv("NEXUS_DASHBOARD_ADMIN_PASSWORD_HASH", ""),
            dashboard_viewer_hash=os.getenv("NEXUS_DASHBOARD_VIEWER_PASSWORD_HASH", ""),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "3")),
            network_name=os.getenv("NEXUS_NETWORK_NAME", "nexus-net"),
            image_scan_enabled=_environment_flag("NEXUS_IMAGE_SCAN_ENABLED", True),
            image_scan_severities=os.getenv("NEXUS_IMAGE_SCAN_SEVERITIES", "CRITICAL"),
            trivy_ignore_unfixed=_environment_flag("NEXUS_TRIVY_IGNORE_UNFIXED", True),
            trivy_image=os.getenv("NEXUS_TRIVY_IMAGE", "aquasec/trivy:0.57.1"),
            trivy_cache_volume=os.getenv("NEXUS_TRIVY_CACHE_VOLUME", "nexus-trivy-cache"),
        )


settings = Settings.from_environment()
