"""
Proxy routing for OpenAI-compatible chat completions.

This module intercepts requests, forwards them to the target provider,
streams responses back to the client, and asynchronously logs token
usage and cost to the local database.
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session, select

from database.connection import get_session
from database.models import RequestLog
from utils.pricing import calculate_cost

router = APIRouter()

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


# ──────────────────────────────────────────────────────────────────────
# Background database logging
# ──────────────────────────────────────────────────────────────────────


def log_request_to_db(
    model_name: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    session: Session,
) -> None:
    """
    Insert a RequestLog record with real token counts and calculated cost.
    Runs as a FastAPI BackgroundTask so it never blocks the response.
    """
    try:
        total_cost = calculate_cost(model_name, prompt_tokens, completion_tokens)

        log_entry = RequestLog(
            model_name=model_name,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost=total_cost,
            latency_ms=latency_ms,
        )
        session.add(log_entry)
        session.commit()

        cost_display = f"${total_cost:.6f}" if total_cost is not None else "N/A"
        print(
            f"[LOG] model={model_name}  "
            f"prompt={prompt_tokens}  completion={completion_tokens}  "
            f"cost={cost_display}  latency={latency_ms}ms"
        )
    except Exception as exc:
        print(f"[ERROR] Failed to log to database: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Streaming token extraction helpers
# ──────────────────────────────────────────────────────────────────────


def _parse_sse_line(line: str) -> dict | None:
    """
    Parse a single Server-Sent Events line.
    Returns the parsed JSON object, or None if the line is not data.
    """
    stripped = line.strip()
    if not stripped.startswith("data:"):
        return None

    payload = stripped[len("data:") :].strip()
    if payload == "[DONE]":
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _extract_usage_from_chunks(
    raw_chunks: list[bytes],
) -> tuple[int, int]:
    """
    Walk through all raw SSE chunks collected during a stream and find
    the usage summary that OpenAI appends when stream_options.include_usage
    is True.

    Returns (prompt_tokens, completion_tokens). Defaults to (0, 0) if
    no usage data is found.
    """
    prompt_tokens = 0
    completion_tokens = 0

    for raw_chunk in raw_chunks:
        text = raw_chunk.decode("utf-8", errors="replace")
        for line in text.split("\n"):
            parsed = _parse_sse_line(line)
            if parsed is None:
                continue

            usage = parsed.get("usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

    return prompt_tokens, completion_tokens


# ──────────────────────────────────────────────────────────────────────
# Proxy endpoint
# ──────────────────────────────────────────────────────────────────────


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Pass-through proxy for OpenAI chat completions.
    Supports both streaming and non-streaming requests.
    """
    # ── Parse the incoming request body ──────────────────────────────
    try:
        request_body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model_name: str = request_body.get("model", "unknown")
    provider: str = "openai"
    is_streaming: bool = request_body.get("stream", False)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    # ── Inject stream_options for usage tracking ─────────────────────
    # When the client requests streaming, we ask OpenAI to append a
    # final chunk containing token usage statistics.
    if is_streaming:
        request_body.setdefault("stream_options", {})
        request_body["stream_options"]["include_usage"] = True

    outbound_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()

    # ── Streaming path ───────────────────────────────────────────────
    if is_streaming:
        collected_chunks: list[bytes] = []

        async def generate_stream():
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream(
                        "POST",
                        OPENAI_API_URL,
                        headers=outbound_headers,
                        json=request_body,
                        timeout=httpx.Timeout(120.0),
                    ) as upstream_response:
                        async for chunk in upstream_response.aiter_bytes():
                            collected_chunks.append(chunk)
                            yield chunk

                except httpx.RequestError as exc:
                    error_payload = json.dumps(
                        {"error": f"Upstream request failed: {exc}"}
                    )
                    yield f"data: {error_payload}\n\n".encode("utf-8")

            # ── After stream completes, extract usage and log ────────
            latency_ms = int((time.time() - start_time) * 1000)
            prompt_tokens, completion_tokens = _extract_usage_from_chunks(
                collected_chunks
            )

            background_tasks.add_task(
                log_request_to_db,
                model_name,
                provider,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                session,
            )

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
        )

    # ── Non-streaming path ───────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        try:
            upstream_response = await client.post(
                OPENAI_API_URL,
                headers=outbound_headers,
                json=request_body,
                timeout=httpx.Timeout(120.0),
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Upstream request failed: {exc}",
            )

    latency_ms = int((time.time() - start_time) * 1000)

    # Extract usage from the standard JSON response
    response_json = upstream_response.json()
    usage = response_json.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    background_tasks.add_task(
        log_request_to_db,
        model_name,
        provider,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        session,
    )

    # Return the raw upstream response to the client
    return JSONResponse(
        content=response_json,
        status_code=upstream_response.status_code,
    )


# ──────────────────────────────────────────────────────────────────────
# Telemetry Logs API
# ──────────────────────────────────────────────────────────────────────


@router.get("/v1/logs")
async def get_request_logs(
    session: Session = Depends(get_session),
    model: Optional[str] = Query(None, description="Filter by model name"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    start_date: Optional[str] = Query(
        None, description="Start date filter (ISO format, e.g. 2026-05-01)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date filter (ISO format, e.g. 2026-05-31)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Retrieve logged request telemetry with optional filtering and pagination.
    """
    statement = select(RequestLog)

    if model:
        statement = statement.where(RequestLog.model_name == model)
    if provider:
        statement = statement.where(RequestLog.provider == provider)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            statement = statement.where(RequestLog.timestamp >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid start_date format. Use ISO format."
            )
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            statement = statement.where(RequestLog.timestamp <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid end_date format. Use ISO format."
            )

    statement = statement.order_by(RequestLog.timestamp.desc())
    statement = statement.offset(offset).limit(limit)

    logs = session.exec(statement).all()

    return [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "model_name": log.model_name,
            "provider": log.provider,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "total_tokens": (log.prompt_tokens or 0) + (log.completion_tokens or 0),
            "total_cost": log.total_cost,
            "latency_ms": log.latency_ms,
        }
        for log in logs
    ]


@router.get("/v1/logs/summary")
async def get_logs_summary(
    session: Session = Depends(get_session),
):
    """
    Return aggregate telemetry statistics for the dashboard overview cards.
    """
    all_logs = session.exec(select(RequestLog)).all()

    if not all_logs:
        return {
            "total_requests": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "avg_latency_ms": 0,
            "models_used": [],
        }

    total_prompt = sum(log.prompt_tokens or 0 for log in all_logs)
    total_completion = sum(log.completion_tokens or 0 for log in all_logs)
    total_cost = sum(log.total_cost or 0.0 for log in all_logs)
    avg_latency = sum(log.latency_ms for log in all_logs) / len(all_logs)
    models_used = list({log.model_name for log in all_logs})

    return {
        "total_requests": len(all_logs),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "total_cost": round(total_cost, 6),
        "avg_latency_ms": round(avg_latency),
        "models_used": models_used,
    }
