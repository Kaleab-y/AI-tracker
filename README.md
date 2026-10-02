# AI Tracker

A local dashboard for seeing what your AI calls cost, how many tokens they use, and how long they take. Point your app's OpenAI-compatible client at the FastAPI proxy; LiteLLM routes requests to the provider and SQLite keeps the telemetry.

## What it does

- Proxies streaming and non-streaming chat completions, including OpenAI, Anthropic, and Gemini models.
- Records successful, failed, and cancelled requests with provider, token counts, estimated cost, latency, and a request ID.
- Filters by model, provider, status, and UTC date range. Cards, charts, and model breakdowns cover the **entire matching history**, independently of the paginated request table.
- Exports all matching requests to CSV, including rows outside the current page.
- Refreshes automatically every 10 seconds while the tab is visible, with a pause switch and manual refresh.
- Includes labeled, removable sample data so you can explore without an API key.

Prompts, replies, and API keys are not saved to the telemetry database. This is a **local development tool** without account authentication; Docker binds the published ports to your computer's loopback interface.

## Quick start with Docker

```bash
git clone https://github.com/Kaleab-y/AI-tracker.git
cd AI-tracker
cp backend/.env.example .env
docker compose up --build
```

On PowerShell, use `Copy-Item backend/.env.example .env` instead of `cp`. Add keys to the root `.env` for the providers you want to call. Leave them empty to explore sample data.

Open **http://localhost:3000**. API documentation is at **http://localhost:8000/docs**.

```bash
docker compose exec backend python seed.py
```

Refresh the dashboard to see 280 sample requests. Repeating the seed does not add duplicates. Remove only the labeled sample rows with:

```bash
docker compose exec backend python seed.py --clear-demo
```

Real requests are preserved. Older versions of the seed generated unlabeled data, so those historical rows cannot automatically be distinguished from real activity.

## Run locally

Use Python 3.12+ and Node.js 22+.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. Edit `backend/.env` to set provider keys. The backend loads this file before creating the database or initializing providers. In another terminal with the same environment activated, run `python seed.py` if you want sample data.

### Dashboard

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. The dashboard's server connects to `http://127.0.0.1:8000` by default. Set `BACKEND_URL` in `frontend/.env.local` to change it; this is a server-only runtime setting. The browser uses same-origin telemetry endpoints, so it does not need a hardcoded backend hostname or access to provider keys.

## Connect your app

Install the OpenAI SDK (`pip install openai`) and use the tracker as its base URL:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="local")
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

The placeholder `api_key="local"` satisfies the SDK; the proxy reads the real provider key from its environment. Actual calls use your provider account and incur its charges. To stream, add `stream=True` and iterate over the returned chunks.

Use `anthropic/claude-…` for Anthropic or `gemini/gemini-…` for Gemini, with a model your account supports. Bare `claude-…` and `gemini-…` names are normalized to these prefixes. Other LiteLLM provider prefixes are forwarded as supplied, but require their own server environment configuration. Standard generation options, tools, structured responses, and stream usage options are supported. Request-level API keys, custom upstream URLs, and arbitrary LiteLLM settings are rejected; configure routing on the server.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Database connectivity check |
| `POST /v1/chat/completions` | OpenAI-format chat proxy |
| `GET /v1/logs` | Paginated array of request metadata; `X-Total-Count` gives the matching count |
| `GET /v1/logs/summary` | Full-history totals, daily aggregates, and per-model breakdowns |
| `GET /v1/logs/options` | Available model and provider filter values |
| `GET /v1/logs/export` | CSV of all matching requests |

Logs, summary, and export accept `model`, `provider`, `status`, `start_date`, and `end_date`. Status is `success`, `error`, or `cancelled`. Date-only values use UTC and include the whole end date; ISO timestamps with offsets are also accepted. Logs additionally accept `limit` (1–1000) and `offset` (0+). Returned timestamps include an explicit UTC offset.

Provider failures return an OpenAI-style error and HTTP 400, 401, 404, 429, 502, or 504. Failures after streaming begins are sent as an SSE error followed by `[DONE]`; the original HTTP status remains 200. A request ID is returned in `X-Request-ID` and stored with the metadata. Malformed input is rejected with 422 before contacting a provider.

## Costs and persistence

Prices are estimates from the catalog bundled with the installed LiteLLM version, including available usage details such as cached tokens. Update LiteLLM to update that catalog, or set `LITELLM_LOCAL_MODEL_COST_MAP=False` to opt into its remote refresh. Estimates can differ from invoices because of provider discounts, special tiers, or incomplete usage.

Unknown pricing and absent token usage remain `null`, not zero. The dashboard shows how many requests lack pricing or usage and excludes unknown costs from spend totals. An interrupted stream may have no final usage information. Latency measures the proxy's elapsed time through completion or interruption, not just time to first token.

SQLite defaults to `backend/telemetry.db` when launched from that directory; Docker stores it in the `ai_telemetry_db` volume. Startup adds the new telemetry fields to older databases without deleting history. Back up your database before upgrading. Telemetry persistence is best effort: a database write failure is reported in server logs without replacing an otherwise valid provider response.

Environment settings are documented in `backend/.env.example`. `UPSTREAM_TIMEOUT_SECONDS` defaults to 60. Docker passes through OpenAI, Anthropic, and Gemini keys. Keep `.env` files out of version control.

## Checks

```bash
# From backend, with its virtual environment activated:
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q

# From frontend:
npm ci
npm run lint
npm run build
```

Tests use isolated databases and mocked providers: no API keys or paid calls are required. GitHub Actions runs backend tests and formatting checks plus the dashboard lint and production build on pushes and pull requests.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance. Licensed under [MIT](LICENSE).
