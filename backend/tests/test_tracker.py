import asyncio
import csv
import io
from datetime import datetime

import litellm
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import main
import seed
from api import routes
from database import connection
from database.models import RequestLog
from utils.pricing import calculate_cost


@pytest.fixture
def client(monkeypatch):
    database = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(connection, "engine", database)
    monkeypatch.setattr(routes, "engine", database)
    monkeypatch.setattr(main, "engine", database)
    monkeypatch.setattr(seed, "engine", database)
    with TestClient(main.app) as test_client:
        yield test_client
    database.dispose()


def insert(count=1, **overrides):
    with Session(connection.engine) as session:
        for _ in range(count):
            values = dict(
                model_name="gpt-4o-mini",
                provider="openai",
                prompt_tokens=100,
                completion_tokens=50,
                total_cost=0.001,
                latency_ms=100,
                timestamp=datetime(2026, 5, 31, 18, 30),
            )
            session.add(RequestLog(**(values | overrides)))
        session.commit()


def response(usage=True):
    return litellm.ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"role": "assistant", "content": "Hello"}}],
        usage=litellm.Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        if usage
        else None,
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"messages": []},
        {"model": " ", "messages": [{"role": "user", "content": "hi"}]},
        {"messages": [{"content": "hi"}]},
        {"messages": [{"role": "user", "content": "hi"}], "stream": "false"},
        {
            "messages": [{"role": "user", "content": "hi"}],
            "api_base": "https://example.com",
        },
    ],
)
def test_invalid_input_does_not_call_provider(client, monkeypatch, body):
    async def forbidden(**kwargs):
        pytest.fail("Invalid input reached the provider")

    monkeypatch.setattr(routes.litellm, "acompletion", forbidden)
    assert client.post("/v1/chat/completions", json=body).status_code == 422


def test_health_and_empty_summary(client):
    assert client.get("/health").json() == {"status": "ok"}
    summary = client.get("/v1/logs/summary").json()
    assert summary["total_requests"] == summary["total_cost"] == 0
    assert summary["daily"] == summary["by_model"] == []


def test_full_history_filters_pagination_and_export(client):
    insert(230)
    insert(
        model_name="claude-test", provider="anthropic", timestamp=datetime(2026, 6, 1)
    )
    params = {
        "provider": "openai",
        "start_date": "2026-05-31",
        "end_date": "2026-05-31",
    }
    summary = client.get("/v1/logs/summary", params=params).json()
    assert summary["total_requests"] == 230
    assert summary["total_tokens"] == 34500
    assert summary["total_cost"] == pytest.approx(0.23)
    assert summary["by_model"][0]["total_requests"] == 230
    assert summary["daily"][0]["total_requests"] == 230
    first = client.get("/v1/logs", params=params | {"limit": 25})
    second = client.get("/v1/logs", params=params | {"limit": 25, "offset": 25})
    assert first.headers["X-Total-Count"] == "230"
    assert len(first.json()) == len(second.json()) == 25
    assert not {row["id"] for row in first.json()} & {
        row["id"] for row in second.json()
    }
    assert first.json()[0]["timestamp"].endswith("+00:00")
    rows = list(
        csv.DictReader(io.StringIO(client.get("/v1/logs/export", params=params).text))
    )
    assert len(rows) == 230
    assert client.get("/v1/logs/options").json()["providers"] == ["anthropic", "openai"]


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "bad"},
        {"end_date": "bad"},
        {"start_date": "2026-06-02", "end_date": "2026-06-01"},
    ],
)
def test_date_errors_consistent_across_views(client, params):
    for endpoint in ["/v1/logs", "/v1/logs/summary", "/v1/logs/export"]:
        assert client.get(endpoint, params=params).status_code == 400


def test_timezone_filter(client):
    insert()
    assert (
        len(
            client.get(
                "/v1/logs", params={"start_date": "2026-05-31T21:00:00+03:00"}
            ).json()
        )
        == 1
    )
    assert (
        client.get(
            "/v1/logs", params={"start_date": "2026-05-31T22:00:00+03:00"}
        ).json()
        == []
    )


@pytest.mark.parametrize(
    "model,provider,routed",
    [
        ("openai/gpt-4o-mini", "openai", "openai/gpt-4o-mini"),
        ("claude-test", "anthropic", "anthropic/claude-test"),
        ("gemini-test", "google", "gemini/gemini-test"),
    ],
)
def test_nonstreaming_logs_and_routes(client, monkeypatch, model, provider, routed):
    async def completion(**kwargs):
        assert kwargs["model"] == routed
        assert kwargs["temperature"] == 0.2
        return response()

    monkeypatch.setattr(routes.litellm, "acompletion", completion)
    result = client.post(
        "/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
        },
    )
    assert result.status_code == 200
    log = client.get("/v1/logs").json()[0]
    assert log["provider"] == provider
    assert log["request_id"] == result.headers["X-Request-ID"]
    assert log["total_tokens"] == 150
    assert "hello" not in client.get("/v1/logs").text


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "error,status,code",
    [
        (
            litellm.AuthenticationError("secret-sensitive-details", "openai", "gpt"),
            401,
            "authentication_error",
        ),
        (
            litellm.RateLimitError("secret-sensitive-details", "openai", "gpt"),
            429,
            "rate_limit_error",
        ),
        (
            litellm.Timeout("secret-sensitive-details", "gpt", "openai"),
            504,
            "timeout_error",
        ),
        (RuntimeError("secret-sensitive-details"), 502, "upstream_error"),
    ],
)
def test_initial_errors_have_http_status_and_are_recorded(
    client, monkeypatch, stream, error, status, code
):
    async def completion(**kwargs):
        raise error

    monkeypatch.setattr(routes.litellm, "acompletion", completion)
    result = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": stream},
    )
    assert result.status_code == status
    assert result.json()["error"]["code"] == code
    assert "secret-sensitive-details" not in result.text
    log = client.get("/v1/logs", params={"status": "error"}).json()[0]
    assert log["total_cost"] is None
    assert log["total_tokens"] is None
    assert log["prompt_tokens"] is None
    assert log["completion_tokens"] is None


@pytest.mark.parametrize(
    "has_usage,breaks", [(True, False), (False, False), (False, True)]
)
def test_streaming_usage_and_midstream_failure(client, monkeypatch, has_usage, breaks):
    async def chunks():
        yield litellm.ModelResponseStream(
            model="gpt-4o-mini", choices=[{"delta": {"content": "Hello"}}]
        )
        if breaks:
            raise RuntimeError("private provider details")
        if has_usage:
            yield litellm.ModelResponseStream(
                model="gpt-4o-mini",
                choices=[],
                usage=litellm.Usage(
                    prompt_tokens=100, completion_tokens=50, total_tokens=150
                ),
            )

    async def completion(**kwargs):
        assert kwargs["stream_options"] == {"include_usage": True}
        return chunks()

    monkeypatch.setattr(routes.litellm, "acompletion", completion)
    result = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "stream_options": {"include_usage": False},
        },
    )
    assert result.status_code == 200
    assert result.text.endswith("data: [DONE]\n\n")
    assert "private provider details" not in result.text
    log = client.get("/v1/logs").json()[0]
    assert log["usage_available"] == has_usage
    assert log["status"] == ("error" if breaks else "success")
    assert log["total_tokens"] == (150 if has_usage else None)


def test_cancelled_stream_persists_and_closes(client, monkeypatch):
    closed = []

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise asyncio.CancelledError()

        async def aclose(self):
            closed.append(True)

    async def completion(**kwargs):
        return Stream()

    monkeypatch.setattr(routes.litellm, "acompletion", completion)

    async def consume():
        result = await routes.proxy_chat_completions(
            routes.ChatRequest(
                messages=[{"role": "user", "content": "hi"}], stream=True
            ),
            BackgroundTasks(),
        )
        with pytest.raises(asyncio.CancelledError):
            await anext(result.body_iterator)

    asyncio.run(consume())
    assert closed == [True]
    assert client.get("/v1/logs").json()[0]["status"] == "cancelled"


def test_missing_usage_is_not_zero_cost(client, monkeypatch):
    async def completion(**kwargs):
        result = response()
        result.usage = None
        return result

    monkeypatch.setattr(routes.litellm, "acompletion", completion)
    client.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    summary = client.get("/v1/logs/summary").json()
    assert summary["unpriced_requests"] == summary["missing_usage_requests"] == 1


def test_pricing_and_csv_formula_handling(client):
    assert calculate_cost("openai/gpt-4o-mini", 100, 50) == pytest.approx(0.000045)
    assert calculate_cost("unregistered-model-xyz", 100, 50) is None
    insert(model_name="=HYPERLINK(bad)")
    rows = list(csv.DictReader(io.StringIO(client.get("/v1/logs/export").text)))
    assert rows[0]["model_name"].startswith("'=")


def test_upgrade_preserves_existing_logs(client, monkeypatch):
    legacy = create_engine("sqlite://", poolclass=StaticPool)
    with legacy.begin() as db:
        db.execute(
            text(
                "CREATE TABLE request_logs (id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL, model_name VARCHAR NOT NULL, provider VARCHAR NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER, total_cost FLOAT, latency_ms INTEGER NOT NULL)"
            )
        )
        db.execute(
            text(
                "INSERT INTO request_logs VALUES (1, '2026-05-31 18:30:00', 'gpt-4o-mini', 'openai', 100, 50, .001, 100)"
            )
        )
    monkeypatch.setattr(connection, "engine", legacy)
    connection.create_db_and_tables()
    connection.create_db_and_tables()
    with Session(legacy) as session:
        log = session.exec(select(RequestLog)).one()
        assert log.id == 1 and log.status == "success" and not log.is_demo
    assert "is_demo" in {
        column["name"] for column in inspect(legacy).get_columns("request_logs")
    }
    legacy.dispose()


def test_demo_is_idempotent_and_removal_keeps_real_logs(client):
    insert()
    seed.seed()
    seed.seed()
    summary = client.get("/v1/logs/summary").json()
    assert summary["total_requests"] == 281
    assert summary["demo_requests"] == 280
    seed.seed(clear_demo=True)
    assert client.get("/v1/logs/summary").json()["total_requests"] == 1
