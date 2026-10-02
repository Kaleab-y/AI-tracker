"""OpenAI-compatible proxy and filtered, database-backed telemetry."""

import asyncio
import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Literal
from uuid import uuid4

import anyio
import litellm
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func
from sqlmodel import Session, select

from database.connection import engine, get_session
from database.models import RequestLog
from utils.pricing import calculate_cost

litellm.suppress_debug_info = True
router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=200)
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = Field(default=False, strict=True)
    stream_options: dict[str, Any] | None = None

    @field_validator("model")
    @classmethod
    def nonempty_model(cls, value):
        if not value.strip():
            raise ValueError("Model must not be blank")
        return value.strip()

    @field_validator("messages")
    @classmethod
    def valid_messages(cls, value):
        for message in value:
            if message.get("role") not in {
                "system",
                "developer",
                "user",
                "assistant",
                "tool",
                "function",
            }:
                raise ValueError("Each message needs a valid role")
            if "content" not in message and "tool_calls" not in message:
                raise ValueError("Each message needs content or tool_calls")
        return value

    @model_validator(mode="after")
    def server_owned_configuration(self):
        allowed = {
            "temperature",
            "top_p",
            "n",
            "stop",
            "max_tokens",
            "max_completion_tokens",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "user",
            "seed",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "response_format",
            "logprobs",
            "top_logprobs",
            "reasoning_effort",
            "metadata",
            "store",
            "modalities",
            "audio",
            "prediction",
            "service_tier",
        }
        if set(self.model_extra or {}) - allowed:
            raise ValueError(
                "Unsupported parameter; configure credentials and routing on the server"
            )
        return self


def _detect_provider(model_name: str) -> str:
    model = model_name.lower()
    if "/" in model:
        prefix = model.split("/", 1)[0]
        return {"gemini": "google", "vertex_ai": "google"}.get(prefix, prefix)
    if model.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "google"
    if model.startswith(("mistral", "mixtral")):
        return "mistral"
    return "unknown"


def _routing_model(model: str) -> str:
    if "/" not in model and model.startswith("gemini"):
        return f"gemini/{model}"
    if "/" not in model and model.startswith("claude"):
        return f"anthropic/{model}"
    return model


def _usage(response) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None
    return getattr(usage, "prompt_tokens", None), getattr(
        usage, "completion_tokens", None
    )


def log_request_to_db(**values) -> None:
    usage_object = values.pop("usage_object", None)
    pricing_response = values.pop("pricing_response", None)
    prompt, completion = values["prompt_tokens"], values["completion_tokens"]
    available = prompt is not None and completion is not None
    cost = (
        calculate_cost(
            values["model_name"], prompt, completion, usage_object, pricing_response
        )
        if available
        else None
    )
    try:
        with Session(engine) as session:
            session.add(
                RequestLog(**values, usage_available=available, total_cost=cost)
            )
            session.commit()
    except Exception:
        logger.error("Could not persist telemetry for request %s", values["request_id"])


def _upstream_error(exc) -> tuple[int, str, str]:
    if isinstance(exc, litellm.AuthenticationError):
        return (
            401,
            "authentication_error",
            "Provider authentication failed. Check the server's API key.",
        )
    if isinstance(exc, litellm.NotFoundError):
        return 404, "model_not_found", "The provider could not find that model."
    if isinstance(exc, litellm.RateLimitError):
        return 429, "rate_limit_error", "The provider's rate limit was reached."
    if isinstance(exc, (litellm.Timeout, asyncio.TimeoutError)):
        return 504, "timeout_error", "The provider timed out."
    if isinstance(exc, litellm.BadRequestError):
        return (
            400,
            "invalid_request_error",
            "The provider rejected the request parameters.",
        )
    return 502, "upstream_error", "The provider could not complete the request."


@router.post("/v1/chat/completions")
async def proxy_chat_completions(body: ChatRequest, background_tasks: BackgroundTasks):
    started = time.perf_counter()
    request_id = str(uuid4())
    values = dict(
        model_name=body.model,
        provider=_detect_provider(body.model),
        prompt_tokens=None,
        completion_tokens=None,
        status="success",
        error_code=None,
        request_id=request_id,
    )

    def record():
        return partial(
            log_request_to_db,
            **values,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    params = dict(body.model_extra or {})
    if body.stream:
        params["stream_options"] = {
            **(body.stream_options or {}),
            "include_usage": True,
        }
    try:
        upstream = await litellm.acompletion(
            model=_routing_model(body.model),
            messages=body.messages,
            stream=body.stream,
            timeout=float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60")),
            num_retries=0,
            **params,
        )
    except Exception as exc:
        status, code, message = _upstream_error(exc)
        values.update(status="error", error_code=code)
        await anyio.to_thread.run_sync(record())
        return JSONResponse(
            {"error": {"message": message, "type": code, "code": code}},
            status_code=status,
            headers={"X-Request-ID": request_id},
        )

    if not body.stream:
        values["prompt_tokens"], values["completion_tokens"] = _usage(upstream)
        values.update(
            usage_object=getattr(upstream, "usage", None), pricing_response=upstream
        )
        background_tasks.add_task(record())
        return JSONResponse(upstream.model_dump(), headers={"X-Request-ID": request_id})

    async def generate_stream():
        try:
            async for chunk in upstream:
                prompt, completion = _usage(chunk)
                if prompt is not None or completion is not None:
                    values.update(prompt_tokens=prompt, completion_tokens=completion)
                    values.update(
                        usage_object=getattr(chunk, "usage", None),
                        pricing_response=chunk,
                    )
                yield f"data: {json.dumps(chunk.model_dump(exclude_unset=True))}\n\n"
            yield "data: [DONE]\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            values.update(status="cancelled", error_code="client_disconnected")
            raise
        except Exception as exc:
            _, code, message = _upstream_error(exc)
            values.update(status="error", error_code=code)
            yield f"data: {json.dumps({'error': {'message': message, 'type': code, 'code': code}})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(record())
                close = getattr(upstream, "aclose", None)
                if close:
                    try:
                        await close()
                    except Exception:
                        logger.warning("Could not close provider stream %s", request_id)

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_date(value: str | None, end: bool = False):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        if end and len(value) == 10:
            parsed += timedelta(days=1)
        return parsed
    except ValueError:
        raise HTTPException(400, "Dates must be ISO dates or timestamps") from None


def get_filters(
    model: str | None = None,
    provider: str | None = None,
    status: Literal["success", "error", "cancelled"] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    start, end = _parse_date(start_date), _parse_date(end_date, end=True)
    if start and end and (start >= end if len(end_date) == 10 else start > end):
        raise HTTPException(400, "Start date must be before end date")
    conditions = []
    for column, value in (
        (RequestLog.model_name, model),
        (RequestLog.provider, provider),
        (RequestLog.status, status),
    ):
        if value:
            conditions.append(column == value)
    if start:
        conditions.append(RequestLog.timestamp >= start)
    if end:
        conditions.append(
            RequestLog.timestamp < end
            if len(end_date) == 10
            else RequestLog.timestamp <= end
        )
    return conditions


def _serialize(log):
    result = log.model_dump()
    result["timestamp"] = log.timestamp.replace(tzinfo=timezone.utc).isoformat()
    result["total_tokens"] = (
        (log.prompt_tokens or 0) + (log.completion_tokens or 0)
        if log.usage_available
        else None
    )
    return result


@router.get("/v1/logs")
def get_request_logs(
    response: Response,
    session: Session = Depends(get_session),
    filters=Depends(get_filters),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    response.headers["X-Total-Count"] = str(
        session.exec(select(func.count(RequestLog.id)).where(*filters)).one()
    )
    logs = session.exec(
        select(RequestLog)
        .where(*filters)
        .order_by(RequestLog.timestamp.desc(), RequestLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_serialize(log) for log in logs]


def _aggregates():
    return (
        func.count(RequestLog.id),
        func.coalesce(func.sum(RequestLog.prompt_tokens), 0),
        func.coalesce(func.sum(RequestLog.completion_tokens), 0),
        func.coalesce(func.sum(RequestLog.total_cost), 0),
        func.coalesce(func.avg(RequestLog.latency_ms), 0),
        func.coalesce(func.sum(case((RequestLog.status != "success", 1), else_=0)), 0),
        func.coalesce(func.sum(case((RequestLog.total_cost.is_(None), 1), else_=0)), 0),
        func.coalesce(
            func.sum(case((RequestLog.usage_available.is_(False), 1), else_=0)), 0
        ),
        func.coalesce(func.sum(case((RequestLog.is_demo.is_(True), 1), else_=0)), 0),
    )


def _stats(row):
    count, prompt, completion, cost, latency, failed, unpriced, missing, demo = row
    return dict(
        total_requests=count,
        total_prompt_tokens=prompt,
        total_completion_tokens=completion,
        total_tokens=prompt + completion,
        total_cost=round(float(cost), 8),
        avg_latency_ms=round(latency),
        failed_requests=failed,
        unpriced_requests=unpriced,
        missing_usage_requests=missing,
        demo_requests=demo,
    )


@router.get("/v1/logs/summary")
def get_logs_summary(
    session: Session = Depends(get_session), filters=Depends(get_filters)
):
    result = _stats(session.exec(select(*_aggregates()).where(*filters)).one())
    models = session.exec(
        select(RequestLog.model_name, *_aggregates())
        .where(*filters)
        .group_by(RequestLog.model_name)
        .order_by(RequestLog.model_name)
    ).all()
    result["models_used"] = [row[0] for row in models]
    result["by_model"] = [dict(model=row[0], **_stats(row[1:])) for row in models]
    day = func.date(RequestLog.timestamp)
    daily = session.exec(
        select(day, *_aggregates()).where(*filters).group_by(day).order_by(day)
    ).all()
    result["daily"] = [dict(date=row[0], **_stats(row[1:])) for row in daily]
    return result


@router.get("/v1/logs/options")
def get_options(session: Session = Depends(get_session)):
    return {
        "models": session.exec(
            select(RequestLog.model_name).distinct().order_by(RequestLog.model_name)
        ).all(),
        "providers": session.exec(
            select(RequestLog.provider).distinct().order_by(RequestLog.provider)
        ).all(),
    }


@router.get("/v1/logs/export")
def export_logs(filters=Depends(get_filters)):
    fields = [
        "id",
        "timestamp",
        "model_name",
        "provider",
        "status",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "total_cost",
        "latency_ms",
        "usage_available",
        "error_code",
        "request_id",
        "is_demo",
    ]

    def generate():
        with Session(engine) as export_session:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            yield output.getvalue()
            logs = export_session.exec(
                select(RequestLog)
                .where(*filters)
                .order_by(RequestLog.timestamp.desc(), RequestLog.id.desc())
                .execution_options(yield_per=500)
            )
            for log in logs:
                output.seek(0)
                output.truncate(0)
                row = _serialize(log)
                for key in ("model_name", "provider"):
                    if row[key].startswith(("=", "+", "-", "@", "\t", "\r")):
                        row[key] = "'" + row[key]
                writer.writerow(row)
                yield output.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="ai-tracker-requests.csv"',
        },
    )
