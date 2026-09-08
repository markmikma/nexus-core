"""Centralized runtime configuration for Nexus-Core services."""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: Path
    webhook_secret: str
    allowed_repository: str
    repository_url: str
    status_token: str
    deploy_token: str
    poll_interval_seconds: int
    network_name: str

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
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "3")),
            network_name=os.getenv("NEXUS_NETWORK_NAME", "nexus-net"),
        )


settings = Settings.from_environment()
