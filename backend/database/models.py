from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class RequestLog(SQLModel, table=True):
    __tablename__ = "request_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_name: str
    provider: str
    prompt_tokens: Optional[int] = Field(default=0)
    completion_tokens: Optional[int] = Field(default=0)
    latency_ms: int
