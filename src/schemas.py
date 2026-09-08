"""HTTP response schemas kept independent from SQLite implementation details."""

from datetime import datetime

from pydantic import BaseModel


class DeploymentJobResponse(BaseModel):
    id: int
    delivery_id: str
    app_name: str
    repository: str
    commit_hash: str
    status: str
    logs: str | None = None
    container_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DeploymentListResponse(BaseModel):
    items: list[DeploymentJobResponse]
    count: int
