from datetime import datetime, timezone
from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel


class RequestLog(SQLModel, table=True):
    __tablename__ = "request_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: NaiveDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    model_name: str
    provider: str
    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    total_cost: Optional[float] = Field(default=None)
    latency_ms: int
    status: str = Field(default="success", index=True)
    usage_available: bool = True
    error_code: Optional[str] = None
    request_id: Optional[str] = None
    is_demo: bool = False
