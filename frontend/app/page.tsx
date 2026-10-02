"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface Stats {
  total_requests: number;
  total_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  failed_requests: number;
  unpriced_requests: number;
  missing_usage_requests: number;
  demo_requests: number;
}
interface Summary extends Stats {
  by_model: (Stats & { model: string })[];
  daily: (Stats & { date: string })[];
}
interface LogEntry {
  id: number;
  timestamp: string;
  model_name: string;
  provider: string;
  status: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  total_cost: number | null;
  latency_ms: number;
  error_code: string | null;
  request_id: string | null;
  is_demo: boolean;
}
interface Snapshot {
  summary: Summary;
  logs: LogEntry[];
  total: number;
  updated: Date;
  query: string;
  options: { models: string[]; providers: string[] };
}
const emptyFilters = {
  model: "",
  provider: "",
  status: "",
  start_date: "",
  end_date: "",
};
const pageSize = 25;
const api = "/api/telemetry";
const number = (value: number | null) =>
  value === null ? "—" : value.toLocaleString();
const money = (value: number | null) =>
  value === null
    ? "Unknown"
    : `$${value.toFixed(value < 0.01 && value > 0 ? 6 : 4)}`;
const control =
  "rounded-lg border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary";
const panel = "rounded-xl border border-border bg-bg-secondary/50";
const snippet = `from openai import OpenAI\n\nclient = OpenAI(base_url="http://localhost:8000/v1", api_key="local")\nresponse = client.chat.completions.create(\n    model="gpt-4o-mini",\n    messages=[{"role": "user", "content": "Hello!"}],\n)\nprint(response.choices[0].message.content)`;

async function checked(response: Response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}).`,
    );
  }
  return response;
}

export default function DashboardPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [live, setLive] = useState(true);
  const [notice, setNotice] = useState("");
  const [exporting, setExporting] = useState(false);
  const search = new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value),
  ).toString();
  const query = `${search}&limit=${pageSize}&offset=${page * pageSize}`;
  const invalidDates = Boolean(
    filters.start_date &&
    filters.end_date &&
    filters.start_date > filters.end_date,
  );

  useEffect(() => {
    if (invalidDates) return;
    const controller = new AbortController();
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(20_000),
    ]);
    Promise.all([
      fetch(`${api}/v1/logs/summary?${search}`, {
        signal,
        cache: "no-store",
      }).then(checked),
      fetch(`${api}/v1/logs?${query}`, { signal, cache: "no-store" }).then(
        checked,
      ),
      fetch(`${api}/v1/logs/options`, { signal, cache: "no-store" }).then(
        checked,
      ),
    ])
      .then(async ([summary, logs, options]) => {
        const [summaryData, logData, optionData] = await Promise.all([
          summary.json(),
          logs.json(),
          options.json(),
        ]);
        if (controller.signal.aborted) return;
        const total = Number(
          logs.headers.get("X-Total-Count") || summaryData.total_requests,
        );
        if (page > 0 && page * pageSize >= total) {
          setPage(Math.max(0, Math.ceil(total / pageSize) - 1));
          return;
        }
        setSnapshot({
          summary: summaryData,
          logs: logData,
          options: optionData,
          total,
          updated: new Date(),
          query,
        });
        setError(null);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error ? reason.message : "Connection failed.",
          );
      });
    return () => controller.abort();
  }, [search, query, page, refresh, invalidDates]);

  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible")
        setRefresh((value) => value + 1);
    }, 10_000);
    return () => clearInterval(timer);
  }, [live]);

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilters((previous) => ({ ...previous, [key]: value }));
    setPage(0);
  }
  function reset() {
    setFilters(emptyFilters);
    setPage(0);
  }
  async function copySnippet() {
    try {
      await navigator.clipboard.writeText(snippet);
      setNotice("Python example copied.");
    } catch {
      setNotice("Copy unavailable. You can select the example below.");
    }
  }
  async function exportCsv() {
    setExporting(true);
    try {
      const response = await checked(
        await fetch(`${api}/v1/logs/export?${search}`, {
          signal: AbortSignal.timeout(30_000),
        }),
      );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "ai-tracker-requests.csv";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("Exported all matching requests.");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  }
  const summary = snapshot?.summary;
  const stale = snapshot && snapshot.query !== query;
  const ready = snapshot && !stale && !invalidDates;
  const active = Object.values(filters).some(Boolean);
  const chartStyle = {
    background: "#18181b",
    border: "1px solid #3f3f46",
    borderRadius: 8,
    color: "#fafafa",
    fontSize: 12,
  };

  return (
    <div className="min-h-screen bg-bg-primary">
      <header className="border-b border-border-subtle">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-5 sm:px-8">
          <Link href="/" className="text-lg font-semibold tracking-tight">
            AI tracker<span className="text-accent">.</span>
          </Link>
          <div className="flex items-center gap-4 text-xs text-text-secondary">
            <span className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 rounded-full ${error ? "bg-warning" : snapshot ? "bg-positive" : "bg-text-muted"}`}
              />
              {error
                ? "Connection interrupted"
                : snapshot
                  ? "Connected"
                  : "Connecting"}
            </span>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={live}
                onChange={(event) => setLive(event.target.checked)}
              />
              Auto-refresh
            </label>
            <button
              className={control}
              onClick={() => setRefresh((value) => value + 1)}
            >
              Refresh
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-xs uppercase tracking-[.2em] text-accent">
              Your AI, in view
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">
              Usage overview
            </h1>
            <p className="mt-2 text-sm text-text-secondary">
              Requests, tokens, estimated spend, and the time in between.
            </p>
          </div>
          <button
            className={control}
            disabled={!ready || exporting || !snapshot.total}
            onClick={exportCsv}
          >
            {exporting ? "Exporting…" : "Export CSV ↗"}
          </button>
        </div>
        <section
          aria-label="Filter requests"
          className={`${panel} flex flex-wrap items-end gap-3 p-4`}
        >
          {(["model", "provider", "status"] as const).map((key) => (
            <label
              key={key}
              className="flex min-w-36 flex-1 flex-col gap-2 text-xs capitalize text-text-secondary"
            >
              {key}
              <select
                className={control}
                value={filters[key]}
                onChange={(event) => updateFilter(key, event.target.value)}
              >
                <option value="">
                  All {key === "status" ? "statuses" : `${key}s`}
                </option>
                {(key === "status"
                  ? ["success", "error", "cancelled"]
                  : key === "model"
                    ? snapshot?.options.models || []
                    : snapshot?.options.providers || []
                ).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {(["start_date", "end_date"] as const).map((key) => (
            <label
              key={key}
              className="flex flex-col gap-2 text-xs text-text-secondary"
            >
              {key === "start_date" ? "From (UTC)" : "Through (UTC)"}
              <input
                aria-label={key === "start_date" ? "Start date" : "End date"}
                className={control}
                type="date"
                value={filters[key]}
                onChange={(event) => updateFilter(key, event.target.value)}
              />
            </label>
          ))}
          <button className={control} disabled={!active} onClick={reset}>
            Reset
          </button>
        </section>
        <div aria-live="polite" className="space-y-2 text-sm">
          {invalidDates && (
            <p className="text-warning" role="alert">
              The start date must be on or before the end date.
            </p>
          )}
          {error && (
            <div
              className="rounded-lg border border-warning/30 bg-warning/5 p-4 text-warning"
              role="alert"
            >
              {error} {snapshot && "Showing the last successful update."}{" "}
              <button
                className="ml-2 underline"
                onClick={() => setRefresh((value) => value + 1)}
              >
                Retry
              </button>
            </div>
          )}
          {stale && !invalidDates && !error && (
            <p className="text-text-secondary">Updating results…</p>
          )}
          {notice && (
            <p className="text-accent">
              {notice}{" "}
              <button
                aria-label="Dismiss notification"
                className="ml-2 underline"
                onClick={() => setNotice("")}
              >
                Dismiss
              </button>
            </p>
          )}
          {Boolean(summary?.demo_requests) && (
            <p className="rounded-lg border border-accent/20 bg-accent-dim p-3 text-accent">
              This view contains {number(summary!.demo_requests)} sample
              requests. Demo rows are labeled below.
            </p>
          )}
        </div>
        {!snapshot ? (
          <section className={`${panel} p-10 text-center`}>
            <h2 className="font-medium">
              {error ? "Let’s get connected" : "Loading your tracker…"}
            </h2>
            <p className="mt-2 text-sm text-text-secondary">
              Start the backend on port 8000. For Docker, run{" "}
              <code>docker compose up --build</code>.
            </p>
          </section>
        ) : (
          <div
            className={`space-y-6 ${stale || invalidDates ? "opacity-50" : ""}`}
            aria-busy={Boolean(stale)}
          >
            <section
              className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
              aria-label="Summary"
            >
              {[
                [
                  "Requests",
                  number(summary!.total_requests),
                  `${number(summary!.failed_requests)} failed or cancelled`,
                ],
                [
                  "Tokens",
                  number(
                    summary!.total_requests > 0 &&
                      summary!.missing_usage_requests ===
                        summary!.total_requests
                      ? null
                      : summary!.total_tokens,
                  ),
                  `${number(summary!.missing_usage_requests)} requests without full usage`,
                ],
                [
                  "Estimated spend",
                  money(
                    summary!.total_requests > 0 &&
                      summary!.unpriced_requests === summary!.total_requests
                      ? null
                      : summary!.total_cost,
                  ),
                  `${number(summary!.unpriced_requests)} requests with unknown cost`,
                ],
                [
                  "Average latency",
                  `${number(summary!.avg_latency_ms)} ms`,
                  "Includes successful and failed requests",
                ],
              ].map(([label, value, hint]) => (
                <div key={label} className={`${panel} p-5`}>
                  <h2 className="text-sm text-text-secondary">{label}</h2>
                  <p className="mt-3 text-3xl font-semibold tracking-tight">
                    {value}
                  </p>
                  <p className="mt-3 text-xs text-text-muted">{hint}</p>
                </div>
              ))}
            </section>
            {summary!.total_requests === 0 ? (
              <section className={`${panel} py-14 text-center`}>
                <h2 className="text-lg font-medium">
                  {active
                    ? "No requests match these filters"
                    : "Your first request starts the story"}
                </h2>
                <p className="mt-2 text-sm text-text-secondary">
                  {active
                    ? "Try a different date range, model, or provider."
                    : "Connect your app below, or load sample data to explore."}
                </p>
                {active && (
                  <button onClick={reset} className={`${control} mt-5`}>
                    Clear filters
                  </button>
                )}
              </section>
            ) : (
              <>
                <section
                  className="grid gap-5 lg:grid-cols-2"
                  aria-label="Usage charts"
                >
                  <div className={`${panel} p-5`}>
                    <h2 className="font-medium">Spend over time</h2>
                    <p className="mb-6 mt-1 text-xs text-text-muted">
                      USD · daily totals in UTC · known costs only
                    </p>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={summary!.daily}>
                          <defs>
                            <linearGradient
                              id="spend"
                              x1="0"
                              y1="0"
                              x2="0"
                              y2="1"
                            >
                              <stop
                                offset="0%"
                                stopColor="#a78bfa"
                                stopOpacity={0.35}
                              />
                              <stop
                                offset="100%"
                                stopColor="#a78bfa"
                                stopOpacity={0}
                              />
                            </linearGradient>
                          </defs>
                          <CartesianGrid stroke="#27272a" vertical={false} />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 11, fill: "#a1a1aa" }}
                            tickFormatter={(value) => String(value).slice(5)}
                          />
                          <YAxis
                            width={65}
                            tick={{ fontSize: 11, fill: "#a1a1aa" }}
                            tickFormatter={(value) => `$${value}`}
                          />
                          <Tooltip
                            contentStyle={chartStyle}
                            formatter={(value) => [
                              money(Number(value)),
                              "Estimated spend",
                            ]}
                          />
                          <Area
                            type="monotone"
                            dataKey="total_cost"
                            stroke="#a78bfa"
                            fill="url(#spend)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className={`${panel} p-5`}>
                    <h2 className="font-medium">Requests by model</h2>
                    <p className="mb-6 mt-1 text-xs text-text-muted">
                      All matching requests · scroll the model table for details
                    </p>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={[...summary!.by_model]
                            .sort((a, b) => b.total_requests - a.total_requests)
                            .slice(0, 8)}
                          layout="vertical"
                          margin={{ left: 10 }}
                        >
                          <CartesianGrid stroke="#27272a" horizontal={false} />
                          <XAxis
                            type="number"
                            allowDecimals={false}
                            tick={{ fontSize: 11, fill: "#a1a1aa" }}
                          />
                          <YAxis
                            type="category"
                            dataKey="model"
                            width={125}
                            tick={{ fontSize: 10, fill: "#a1a1aa" }}
                            tickFormatter={(value) =>
                              String(value).length > 20
                                ? `${String(value).slice(0, 19)}…`
                                : String(value)
                            }
                          />
                          <Tooltip
                            contentStyle={chartStyle}
                            formatter={(value) => [
                              number(Number(value)),
                              "Requests",
                            ]}
                          />
                          <Bar
                            dataKey="total_requests"
                            fill="#a78bfa"
                            radius={[0, 4, 4, 0]}
                            barSize={18}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </section>
                <section className={`${panel} overflow-hidden`}>
                  <h2 className="px-5 py-4 font-medium">Model breakdown</h2>
                  <div className="overflow-x-auto">
                    <table className="w-full whitespace-nowrap text-left text-sm">
                      <thead className="border-y border-border text-xs text-text-secondary">
                        <tr>
                          {[
                            "Model",
                            "Requests",
                            "Tokens",
                            "Est. spend",
                            "Avg. latency",
                            "Failures",
                            "Unknown costs",
                          ].map((title) => (
                            <th className="px-5 py-3 font-normal" key={title}>
                              {title}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {summary!.by_model.map((model) => (
                          <tr
                            key={model.model}
                            className="border-b border-border-subtle"
                          >
                            <td className="px-5 py-3 font-mono text-xs">
                              {model.model}
                            </td>
                            {[
                              number(model.total_requests),
                              number(
                                model.missing_usage_requests ===
                                  model.total_requests
                                  ? null
                                  : model.total_tokens,
                              ),
                              money(
                                model.unpriced_requests === model.total_requests
                                  ? null
                                  : model.total_cost,
                              ),
                              `${number(model.avg_latency_ms)} ms`,
                              number(model.failed_requests),
                              number(model.unpriced_requests),
                            ].map((value, i) => (
                              <td
                                className="px-5 py-3 text-text-secondary"
                                key={i}
                              >
                                {value}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
            <section className={`${panel} overflow-hidden`}>
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <h2 className="font-medium">Request history</h2>
                <span className="text-xs text-text-muted">
                  Times in your local timezone
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full whitespace-nowrap text-left text-sm">
                  <thead className="border-y border-border text-xs text-text-secondary">
                    <tr>
                      {[
                        "Time",
                        "Model / provider",
                        "Status",
                        "In / out tokens",
                        "Est. cost",
                        "Latency",
                      ].map((title) => (
                        <th key={title} className="px-5 py-3 font-normal">
                          {title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.logs.map((log) => (
                      <tr
                        key={log.id}
                        className="border-b border-border-subtle hover:bg-bg-tertiary/40"
                      >
                        <td className="px-5 py-3 text-xs text-text-secondary">
                          <time dateTime={log.timestamp}>
                            {new Date(log.timestamp).toLocaleString()}
                          </time>
                          {log.is_demo && (
                            <span className="ml-2 rounded bg-accent-dim px-1.5 py-1 text-accent">
                              demo
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <p className="font-mono text-xs">{log.model_name}</p>
                          <p className="mt-1 text-xs text-text-muted">
                            {log.provider}
                          </p>
                        </td>
                        <td
                          className="px-5 py-3"
                          title={[log.error_code, log.request_id]
                            .filter(Boolean)
                            .join(" · ")}
                        >
                          <span
                            className={`text-xs ${log.status === "success" ? "text-positive" : "text-warning"}`}
                          >
                            {log.status}
                          </span>
                          {log.error_code && (
                            <p className="mt-1 text-xs text-text-muted">
                              {log.error_code.replaceAll("_", " ")}
                            </p>
                          )}
                        </td>
                        <td className="px-5 py-3 text-xs text-text-secondary">
                          {number(log.prompt_tokens)} /{" "}
                          {number(log.completion_tokens)}
                        </td>
                        <td className="px-5 py-3 text-xs text-text-secondary">
                          {money(log.total_cost)}
                        </td>
                        <td className="px-5 py-3 text-xs text-text-secondary">
                          {number(log.latency_ms)} ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-xs text-text-secondary">
                <span>
                  {snapshot.total
                    ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, snapshot.total)} of ${number(snapshot.total)}`
                    : "0 requests"}
                </span>
                <div className="flex items-center gap-3">
                  <button
                    className={control}
                    disabled={page === 0 || !ready}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    Previous
                  </button>
                  <span>
                    Page {page + 1} of{" "}
                    {Math.max(1, Math.ceil(snapshot.total / pageSize))}
                  </span>
                  <button
                    className={control}
                    disabled={(page + 1) * pageSize >= snapshot.total || !ready}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </section>
            <p className="text-xs text-text-muted">
              Last updated {snapshot.updated.toLocaleTimeString()} · Charts and
              totals cover all matching requests. Prices are estimates; unknown
              costs are excluded.
            </p>
          </div>
        )}
        <details
          className={`${panel} p-5`}
          open={!snapshot || snapshot.total === 0}
        >
          <summary className="cursor-pointer font-medium">
            Connect your app & explore sample data
          </summary>
          <div className="mt-5 grid gap-6 lg:grid-cols-2">
            <div>
              <p className="mb-3 text-sm text-text-secondary">
                Set your provider key in <code>backend/.env</code>, then point
                the OpenAI SDK at the tracker. Calls use your provider account.
              </p>
              <div className="flex items-center justify-between pb-2 text-xs text-text-muted">
                <span>Python · install the openai package</span>
                <button onClick={copySnippet} className="text-accent underline">
                  Copy example
                </button>
              </div>
              <pre className="overflow-x-auto rounded-lg bg-bg-primary p-4 text-xs leading-6 text-text-secondary">
                <code>{snippet}</code>
              </pre>
            </div>
            <div className="text-sm text-text-secondary">
              <h3 className="mb-3 font-medium text-text-primary">
                Try it without an API key
              </h3>
              <p>
                From the backend folder, run{" "}
                <code className="text-accent">python seed.py</code>, then
                refresh. Docker users can run:
              </p>
              <pre className="my-3 overflow-x-auto rounded-lg bg-bg-primary p-4 text-xs">
                <code>docker compose exec backend python seed.py</code>
              </pre>
              <p>
                Sample rows are labeled and the seed is safe to run again.
                Remove only sample rows with{" "}
                <code className="text-accent">python seed.py --clear-demo</code>
                .
              </p>
              <p className="mt-4 text-xs text-text-muted">
                The tracker stores request metadata. Prompts, replies, and API
                keys are never saved to its database. This app is intended for
                local use.
              </p>
            </div>
          </div>
        </details>
      </main>
      <footer className="mx-auto max-w-7xl px-5 pb-8 text-xs text-text-muted sm:px-8">
        AI Tracker · Built to make usage visible.
      </footer>
    </div>
  );
}
