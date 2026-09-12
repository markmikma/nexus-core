"""HTTP response schemas kept independent from SQLite implementation details."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Environment = Literal["dev", "staging", "production"]


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
    environment: Environment = "dev"


class DeploymentListResponse(BaseModel):
    items: list[DeploymentJobResponse]
    count: int


class DeploymentTriggerRequest(BaseModel):
    """Trusted CI notification used to release a verified commit."""

    delivery_id: str = Field(min_length=1, max_length=255)
    repository: str = Field(min_length=1, max_length=255)
    ref: str = Field(min_length=1, max_length=255)
    commit_hash: str = Field(min_length=40, max_length=40)
    environment: Environment = "dev"


class PromotionRequest(BaseModel):
    source_environment: Literal["dev", "staging"]
    target_environment: Literal["staging", "production"]
