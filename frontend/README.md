# AI Tracker dashboard

Next.js App Router, React, TypeScript, Tailwind CSS, and Recharts.

```bash
npm ci
npm run dev
```

Run the backend on port 8000 and open http://localhost:3000. Set `BACKEND_URL` in `.env.local` if the backend lives elsewhere. This setting is read by the dashboard server at runtime; provider keys never belong in the frontend.

The dashboard fetches full-history aggregates separately from paginated rows. Filters apply to both and to CSV exports. Dates in filters and daily charts use UTC; individual request timestamps display in your local timezone. Auto-refresh pauses while the tab is hidden and can be switched off.

```bash
npm run lint
npm run build
npm run start
```

See the [root README](../README.md) for provider setup, sample data, Docker, and proxy examples.
