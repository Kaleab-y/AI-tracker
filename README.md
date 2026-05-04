# AI Telemetry and Tracking Platform

A free, open-source AI Gateway and Telemetry Proxy. This project allows developers to point their LLM API calls (e.g., to OpenAI) to a local proxy which seamlessly streams responses back to the user while asynchronously tracking token usage, cost, and latency in the background.

## 🚀 Why It Exists

Observability is critical when building AI applications. You need to know how fast your requests are processing, how many tokens you are consuming, and what the associated costs are. However, passing every request through a slow, blocking cloud proxy ruins the user experience (especially for streaming interfaces).

This project acts as a **local-first, ultra-fast proxy**. It intercepts the request, streams the response immediately back to the client, and handles the logging to a local SQLite database in the background.

## 🏗️ Architecture

- **Backend Proxy**: Built with Python, FastAPI, and `httpx` for fast, asynchronous streaming.
- **Database**: SQLite integrated with SQLModel (easily swappable to PostgreSQL).
- **Frontend Dashboard**: (Coming Soon!) A Next.js application to visualize the telemetry data.

## ⚡ Quick Start

### Using Docker (Recommended)
The easiest way to run the entire stack (proxy + dashboard) is with Docker Compose.

1. Clone the repository
   ```bash
   git clone https://github.com/Kaleab-y/AI-tracker.git
   cd AI-tracker
   ```

2. Set up your environment variables
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env and add your OPENAI_API_KEY
   ```

3. Start the stack
   ```bash
   docker compose up -d --build
   ```

- The **Proxy** is now running on `http://localhost:8000`
- The **Dashboard** is now running on `http://localhost:3000`

### Manual Setup (Local Development)

If you prefer to run the services without Docker:

#### 1. Backend Proxy
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add OPENAI_API_KEY to .env
uvicorn main:app --reload
```

#### 2. Frontend Dashboard
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```

### Test the Proxy

Send a standard OpenAI request to the local proxy:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}], "stream": true}'
```

## 🔒 Security & Privacy

This project strictly adheres to the principle of "opt-in logging". By default, we DO NOT log the contents of your prompts or completions. We only log metadata: `timestamp`, `model_name`, `provider`, `latency_ms`, and `tokens`.

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
