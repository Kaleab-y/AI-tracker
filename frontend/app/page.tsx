"use client";

import { useEffect, useState, useCallback } from "react";
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
  Cell,
} from "recharts";

// ── Types ───────────────────────────────────────────────────────

interface LogEntry {
  id: number;
  timestamp: string;
  model_name: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost: number | null;
  latency_ms: number;
}

interface Summary {
  total_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
  models_used: string[];
}

const API_BASE = "http://localhost:8000";

// ── Tooltip ─────────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-bg-secondary border border-border rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-text-muted mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.color }} className="font-medium">
          {entry.name}: {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [sRes, lRes] = await Promise.all([
        fetch(`${API_BASE}/v1/logs/summary`),
        fetch(`${API_BASE}/v1/logs?limit=200`),
      ]);
      if (!sRes.ok || !lRes.ok) throw new Error("Backend returned an error.");
      setSummary(await sRes.json());
      setLogs(await lRes.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 5000);
    return () => clearInterval(id);
  }, [fetchData]);

  // ── Derived data ──────────────────────────────────────────────

  const costOverTime = logs
    .slice()
    .reverse()
    .reduce<{ date: string; cost: number; tokens: number }[]>((acc, log) => {
      const date = new Date(log.timestamp).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
      const existing = acc.find((d) => d.date === date);
      if (existing) {
        existing.cost += log.total_cost || 0;
        existing.tokens += log.total_tokens;
      } else {
        acc.push({ date, cost: log.total_cost || 0, tokens: log.total_tokens });
      }
      return acc;
    }, []);

  const latencyPerModel = logs.reduce<
    { model: string; latency: number; count: number }[]
  >((acc, log) => {
    const existing = acc.find((d) => d.model === log.model_name);
    if (existing) {
      existing.latency =
        (existing.latency * existing.count + log.latency_ms) / (existing.count + 1);
      existing.count += 1;
    } else {
      acc.push({ model: log.model_name, latency: log.latency_ms, count: 1 });
    }
    return acc;
  }, []);

  // ── Loading state ─────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-text-muted text-sm">Loading…</p>
      </div>
    );
  }

  // ── Error state ───────────────────────────────────────────────

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center max-w-sm">
          <p className="text-text-primary text-sm font-medium mb-1">Cannot reach backend</p>
          <p className="text-text-muted text-xs mb-4">{error}</p>
          <button
            onClick={() => { setLoading(true); fetchData(); }}
            className="text-xs text-accent hover:underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  const hasData = summary && summary.total_requests > 0;

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* ── Nav ─────────────────────────────────────────────────── */}
      <nav className="border-b border-border-subtle sticky top-0 z-50 bg-bg-primary/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <span className="text-sm font-semibold text-text-primary tracking-tight">
            telemetry<span className="text-accent">.</span>
          </span>
          {hasData && (
            <span className="text-[11px] text-text-muted">
              {summary.total_requests} request{summary.total_requests !== 1 && "s"} tracked
            </span>
          )}
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-10">
        {!hasData ? (
          /* ── Empty state ───────────────────────────────────────── */
          <div className="text-center py-32">
            <p className="text-text-primary text-sm font-medium mb-2">
              No data yet
            </p>
            <p className="text-text-muted text-xs max-w-xs mx-auto leading-relaxed">
              Point your LLM API calls to{" "}
              <code className="text-accent">localhost:8000</code>{" "}
              and usage will appear here.
            </p>
          </div>
        ) : (
          <>
            {/* ── Metrics row ──────────────────────────────────── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-border rounded-xl overflow-hidden mb-10">
              {[
                {
                  label: "Requests",
                  value: summary.total_requests.toLocaleString(),
                },
                {
                  label: "Tokens",
                  value: summary.total_tokens.toLocaleString(),
                  detail: `${summary.total_prompt_tokens.toLocaleString()} in · ${summary.total_completion_tokens.toLocaleString()} out`,
                },
                {
                  label: "Cost",
                  value: `$${summary.total_cost < 0.01 ? summary.total_cost.toFixed(6) : summary.total_cost.toFixed(2)}`,
                },
                {
                  label: "Avg latency",
                  value: `${summary.avg_latency_ms.toLocaleString()} ms`,
                },
              ].map((m) => (
                <div key={m.label} className="bg-bg-secondary p-5">
                  <p className="text-[11px] text-text-muted uppercase tracking-widest mb-2">
                    {m.label}
                  </p>
                  <p className="text-xl font-semibold text-text-primary tabular-nums">
                    {m.value}
                  </p>
                  {m.detail && (
                    <p className="text-[11px] text-text-muted mt-1">{m.detail}</p>
                  )}
                </div>
              ))}
            </div>

            {/* ── Charts ───────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 mb-10">
              {/* Spend over time */}
              <div className="lg:col-span-3 border border-border rounded-xl p-5">
                <p className="text-xs text-text-muted uppercase tracking-widest mb-5">
                  Spend over time
                </p>
                <ResponsiveContainer width="100%" height={240}>
                  <AreaChart data={costOverTime}>
                    <defs>
                      <linearGradient id="fillCost" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.15} />
                        <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v) => `$${v}`}
                      width={48}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="cost"
                      stroke="#a78bfa"
                      strokeWidth={1.5}
                      fill="url(#fillCost)"
                      name="Cost ($)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Latency by model */}
              <div className="lg:col-span-2 border border-border rounded-xl p-5">
                <p className="text-xs text-text-muted uppercase tracking-widest mb-5">
                  Latency by model
                </p>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={latencyPerModel} layout="vertical" barSize={16}>
                    <CartesianGrid stroke="#27272a" strokeDasharray="3 3" horizontal={false} />
                    <XAxis
                      type="number"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v) => `${v}ms`}
                    />
                    <YAxis
                      type="category"
                      dataKey="model"
                      tick={{ fill: "#a1a1aa", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      width={100}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="latency" name="Avg (ms)" radius={[0, 4, 4, 0]}>
                      {latencyPerModel.map((_, i) => (
                        <Cell key={i} fill={i % 2 === 0 ? "#a78bfa" : "#7c3aed"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* ── Model breakdown ──────────────────────────────── */}
            {summary.models_used.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-10">
                {summary.models_used.map((model) => {
                  const modelLogs = logs.filter((l) => l.model_name === model);
                  const totalTokens = modelLogs.reduce((s, l) => s + l.total_tokens, 0);
                  const totalCost = modelLogs.reduce((s, l) => s + (l.total_cost || 0), 0);
                  return (
                    <div
                      key={model}
                      className="border border-border rounded-lg px-4 py-3 bg-bg-secondary text-xs"
                    >
                      <span className="text-text-primary font-medium">{model}</span>
                      <span className="text-text-muted ml-3">
                        {modelLogs.length} req · {totalTokens.toLocaleString()} tok · ${totalCost.toFixed(4)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── Logs table ───────────────────────────────────── */}
            <div className="border border-border rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-border">
                <p className="text-xs text-text-muted uppercase tracking-widest">
                  Recent requests
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-left">
                      {["Time", "Model", "Provider", "In", "Out", "Cost", "Latency"].map(
                        (h) => (
                          <th
                            key={h}
                            className={`px-5 py-2.5 text-text-muted font-medium ${
                              ["In", "Out", "Cost", "Latency"].includes(h)
                                ? "text-right"
                                : ""
                            }`}
                          >
                            {h}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr
                        key={log.id}
                        className="border-b border-border-subtle hover:bg-bg-secondary/50 transition-colors"
                      >
                        <td className="px-5 py-2.5 text-text-muted font-mono whitespace-nowrap">
                          {new Date(log.timestamp).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </td>
                        <td className="px-5 py-2.5 text-text-primary font-medium">
                          {log.model_name}
                        </td>
                        <td className="px-5 py-2.5 text-text-muted capitalize">
                          {log.provider}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-text-secondary tabular-nums">
                          {log.prompt_tokens.toLocaleString()}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-text-secondary tabular-nums">
                          {log.completion_tokens.toLocaleString()}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-positive tabular-nums">
                          {log.total_cost !== null
                            ? `$${log.total_cost.toFixed(6)}`
                            : "—"}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono text-text-secondary tabular-nums">
                          {log.latency_ms.toLocaleString()} ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
