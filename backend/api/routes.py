import json
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from database.connection import get_session
from database.models import RequestLog

router = APIRouter()

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def log_request_to_db(
    model_name: str, provider: str, latency_ms: int, session: Session
):
    """
    Background task to log the request to the database.
    """
    try:
        log_entry = RequestLog(
            model_name=model_name,
            provider=provider,
            latency_ms=latency_ms,
            prompt_tokens=0,
            completion_tokens=0,
        )
        session.add(log_entry)
        session.commit()
        print(f"Logged request for model {model_name} with latency {latency_ms}ms")
    except Exception as e:
        print(f"Failed to log to database: {e}")


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    # Extract the payload
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model_name = body.get("model", "unknown")
    provider = "openai"  # Defaulting for this proxy endpoint

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Start timing (simplified)
    import time

    start_time = time.time()

    async def stream_response():
        # Use httpx to stream the response from OpenAI
        async with httpx.AsyncClient() as client:
            try:
                # We use stream() to proxy the chunks as they arrive
                async with client.stream(
                    "POST",
                    OPENAI_API_URL,
                    headers=headers,
                    json=body,
                    timeout=httpx.Timeout(60.0),
                ) as response:
                    # If OpenAI returns an error, we should ideally handle it gracefully,
                    # but for now we'll pass the status code back if it's not a stream

                    async for chunk in response.aiter_bytes():
                        yield chunk

            except httpx.RequestError as exc:
                yield f'data: {{"error": "Request to OpenAI failed: {str(exc)}"}}\n\n'.encode(
                    "utf-8"
                )

        # Calculate latency and schedule the background task to log it
        latency_ms = int((time.time() - start_time) * 1000)
        background_tasks.add_task(
            log_request_to_db, model_name, provider, latency_ms, session
        )

    # Return a streaming response back to the client
    return StreamingResponse(stream_response(), media_type="text/event-stream")
