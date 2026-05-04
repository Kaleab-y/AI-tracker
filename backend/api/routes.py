"""
Proxy routing for multi-provider LLM chat completions.

This module intercepts OpenAI-formatted requests, routes them through
LiteLLM (which supports OpenAI, Anthropic, Gemini, and many more),
streams the response back to the client, and asynchronously logs
token usage and cost to the local database.

Supported model prefixes (via LiteLLM):
  - OpenAI:    gpt-4o, gpt-4.1, o1, o3, ...
  - Anthropic: claude-3-5-sonnet-... (pass as "anthropic/claude-...")
  - Google:    gemini-2.0-flash, gemini-2.5-pro, ...
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Optional

import litellm
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session, select

from database.connection import get_session
from database.models import RequestLog
from utils.pricing import calculate_cost

# Suppress LiteLLM's verbose startup/request logging
litellm.suppress_debug_info = True

router = APIRouter()


def _detect_provider(model_name: str) -> str:
    """Infer the provider name from the model string."""
    m = model_name.lower()
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return "openai"
    if m.startswith("claude") or m.startswith("anthropic/"):
        return "anthropic"
    if m.startswith("gemini") or m.startswith("google/"):
        return "google"
    if m.startswith("mistral") or m.startswith("mixtral"):
        return "mistral"
    return "unknown"


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
# Proxy endpoint — powered by LiteLLM
# ──────────────────────────────────────────────────────────────────────


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Pass-through proxy for LLM chat completions (OpenAI, Anthropic, Gemini, …).

    Accepts an OpenAI-formatted request body. The model name determines
    which provider LiteLLM routes to. API keys are loaded automatically
    from environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.).
    """
    try:
        request_body: dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model_name: str = request_body.get("model", "gpt-4o-mini")
    provider: str = _detect_provider(model_name)
    is_streaming: bool = request_body.get("stream", False)
    messages: list[dict] = request_body.get("messages", [])

    # Pull any extra params the caller may have forwarded
    extra_params = {
        k: v
        for k, v in request_body.items()
        if k not in ("model", "messages", "stream")
    }

    start_time = time.time()

    # ── Streaming path ───────────────────────────────────────────────
    if is_streaming:
        prompt_tokens = 0
        completion_tokens = 0

        async def generate_stream():
            nonlocal prompt_tokens, completion_tokens
            try:
                response = await litellm.acompletion(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                    **extra_params,
                )
                async for chunk in response:
                    # Capture usage from the final chunk
                    if hasattr(chunk, "usage") and chunk.usage:
                        prompt_tokens = chunk.usage.prompt_tokens or 0
                        completion_tokens = chunk.usage.completion_tokens or 0

                    # Yield SSE-formatted chunk to the client
                    chunk_dict = chunk.model_dump(exclude_unset=True)
                    yield f"data: {json.dumps(chunk_dict)}\n\n".encode("utf-8")

                yield b"data: [DONE]\n\n"

            except litellm.exceptions.AuthenticationError:
                err = json.dumps({"error": f"Invalid API key for provider: {provider}"})
                yield f"data: {err}\n\n".encode("utf-8")
            except litellm.exceptions.NotFoundError as exc:
                err = json.dumps({"error": f"Model not found: {exc}"})
                yield f"data: {err}\n\n".encode("utf-8")
            except Exception as exc:
                err = json.dumps({"error": f"Upstream error: {exc}"})
                yield f"data: {err}\n\n".encode("utf-8")

            # Log after stream completes
            latency_ms = int((time.time() - start_time) * 1000)
            background_tasks.add_task(
                log_request_to_db,
                model_name,
                provider,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                session,
            )

        return StreamingResponse(generate_stream(), media_type="text/event-stream")

    # ── Non-streaming path ───────────────────────────────────────────
    try:
        response = await litellm.acompletion(
            model=model_name,
            messages=messages,
            stream=False,
            **extra_params,
        )
    except litellm.exceptions.AuthenticationError:
        raise HTTPException(
            status_code=401, detail=f"Invalid API key for provider: {provider}"
        )
    except litellm.exceptions.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Model not found: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")

    latency_ms = int((time.time() - start_time) * 1000)

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    background_tasks.add_task(
        log_request_to_db,
        model_name,
        provider,
        prompt_tokens,
        completion_tokens,
        latency_ms,
        session,
    )

    return JSONResponse(content=response.model_dump())


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
