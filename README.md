# AI Tracker

**Local AI request telemetry with a FastAPI proxy and a Next.js dashboard.**

AI Tracker routes OpenAI-formatted chat completion requests through LiteLLM and stores token usage, estimated cost, and latency in a local SQLite database. A web dashboard helps explore that telemetry.

## Features

- Streaming and non-streaming chat completion requests.
- Provider routing through LiteLLM, including OpenAI, Anthropic, and Gemini.
- Background telemetry logging after requests.
- Log filtering by model, provider, and date, with pagination.
- Dashboard summaries and Recharts visualizations.

## Architecture

| Component | Technologies | Purpose |
| --- | --- | --- |
| Backend | Python, FastAPI, LiteLLM | Proxy requests and expose telemetry APIs |
| Storage | SQLite, SQLModel | Persist request metadata |
| Dashboard | Next.js, TypeScript, Recharts | Explore usage, cost, and latency |
| Local stack | Docker Compose | Run the backend and dashboard together |

## Quick start with Docker

```bash
git clone https://github.com/Kaleab-y/AI-tracker.git
cd AI-tracker
cp backend/.env.example .env
# Set OPENAI_API_KEY in the root .env file.
docker compose up -d --build
```

The current Compose configuration forwards the OpenAI key to the backend. Other provider keys must also be forwarded in Compose to use those providers.

- Dashboard: http://localhost:3000
- Proxy: http://localhost:8000

## Manual development

In the backend directory:

```bash
cd backend
python -m venv venv
source venv/bin/activate
# Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Set the API key for the provider you intend to use.
uvicorn main:app --reload
```

In a second terminal, starting from the repository root:

```bash
cd frontend
npm install
npm run dev
```

## API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/chat/completions` | Proxy streaming or non-streaming chat completion requests |
| `GET /v1/logs` | Retrieve filtered, paginated telemetry |
| `GET /v1/logs/summary` | Retrieve aggregate request, token, cost, and latency statistics |

Example request body:

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hello!"}],
  "stream": true
}
```

Use a model available through your configured provider account.

## Telemetry and privacy

The telemetry database stores request metadata rather than prompt or completion text. Requests are forwarded to the selected model provider. Cost values are estimates from the project's pricing table; coverage and provider usage reporting affect their accuracy.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

## License

[MIT](LICENSE).
