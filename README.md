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

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/ai-telemetry-tracker.git
cd ai-telemetry-tracker/backend
```

### 2. Set up the environment

Create a `.env` file in the `backend/` directory by copying the example:

```bash
cp .env.example .env
```

Add your OpenAI API key to the `.env` file:
```env
OPENAI_API_KEY=sk-your-actual-api-key
```

### 3. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

### 4. Run the proxy

```bash
uvicorn main:app --reload
```

The proxy will run on `http://127.0.0.1:8000`.

### 5. Test the Proxy

Send a standard OpenAI request to the proxy:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}], "stream": true}'
```

## 🔒 Security & Privacy

This project strictly adheres to the principle of "opt-in logging". By default, we DO NOT log the contents of your prompts or completions. We only log metadata: `timestamp`, `model_name`, `provider`, `latency_ms`, and `tokens`.

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
