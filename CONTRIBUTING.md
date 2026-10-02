# Contributing

Follow the local setup in [README.md](README.md). Use Python 3.12+ and Node.js 22+.

Install backend development dependencies and run all checks before opening a pull request:

```bash
cd backend
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

For dashboard changes:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Backend tests use temporary, isolated databases and mocked provider calls. Add coverage for behavior changes, particularly streaming, persistence, filtering, and aggregate accuracy. Never put real provider keys or prompts into fixtures.

Keep API changes backward compatible where practical. Schema changes must preserve existing telemetry. Unknown costs and unavailable usage must remain distinguishable from actual zero values. Dashboard cards and charts must use server aggregates rather than whichever request page is visible.

For frontend work, read the installed Next.js guides as required by [frontend/AGENTS.md](frontend/AGENTS.md). Verify loading, empty, disconnected, filtered, and populated states, including narrow screens and keyboard navigation.

Create a branch, use a descriptive Conventional Commit (`feat:`, `fix:`, `docs:`, or `test:`), and open a pull request with a concise behavior summary and validation results. GitHub Actions runs the checks above.
