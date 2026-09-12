"""Centralized runtime configuration for Nexus-Core services."""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _environment_flag(name: str, default: bool) -> bool:
    """Reads a strict boolean setting from the environment."""
    value = os.getenv(name, str(default)).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


@dataclass(frozen=True)
class Settings:
    database_path: Path
    webhook_secret: str
    allowed_repository: str
    repository_url: str
    status_token: str
    deploy_token: str
    dashboard_username: str
    dashboard_password: str
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
            webhook_secret=os.getenv("GITEA_WEBHOOK_SECRET", ""),
            allowed_repository=os.getenv("NEXUS_ALLOWED_REPOSITORY", ""),
            repository_url=os.getenv("GITEA_REPOSITORY_URL", ""),
            status_token=os.getenv("NEXUS_STATUS_TOKEN", ""),
            deploy_token=os.getenv("NEXUS_DEPLOY_TOKEN", ""),
            dashboard_username=os.getenv("NEXUS_DASHBOARD_USERNAME", "admin"),
            dashboard_password=os.getenv("NEXUS_DASHBOARD_PASSWORD", ""),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "3")),
            network_name=os.getenv("NEXUS_NETWORK_NAME", "nexus-net"),
            image_scan_enabled=_environment_flag("NEXUS_IMAGE_SCAN_ENABLED", True),
            image_scan_severities=os.getenv("NEXUS_IMAGE_SCAN_SEVERITIES", "CRITICAL"),
            trivy_ignore_unfixed=_environment_flag("NEXUS_TRIVY_IGNORE_UNFIXED", True),
            trivy_image=os.getenv("NEXUS_TRIVY_IMAGE", "aquasec/trivy:0.57.1"),
            trivy_cache_volume=os.getenv("NEXUS_TRIVY_CACHE_VOLUME", "nexus-trivy-cache"),
        )


settings = Settings.from_environment()
