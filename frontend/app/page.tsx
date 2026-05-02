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
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

// ──────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────

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
const CHART_COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#10b981",
  "#f59e0b",
  "#f43f5e",
  "#06b6d4",
  "#ec4899",
];

// ──────────────────────────────────────────────────────────────────
// Helper Components
// ──────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  subtitle,
  accentColor,
  icon,
}: {
  label: string;
  value: string;
  subtitle?: string;
  accentColor: string;
  icon: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-card-bg border border-card-border p-6 transition-all duration-300 hover:border-opacity-60 hover:scale-[1.02] group">
      {/* Gradient glow */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity duration-500 rounded-2xl"
        style={{
          background: `radial-gradient(circle at top right, ${accentColor}, transparent 70%)`,
        }}
      />
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-3">
          <span className="text-muted text-sm font-medium tracking-wide uppercase">
            {label}
          </span>
          <span className="text-2xl">{icon}</span>
        </div>
        <p className="text-3xl font-bold tracking-tight text-foreground">
          {value}
        </p>
        {subtitle && (
          <p className="text-muted text-sm mt-1">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-6xl mb-6">📡</div>
      <h2 className="text-2xl font-bold text-foreground mb-3">
        No Telemetry Data Yet
      </h2>
      <p className="text-muted max-w-md leading-relaxed">
        Start sending requests through the proxy at{" "}
        <code className="bg-card-bg border border-card-border px-2 py-0.5 rounded text-accent-blue text-sm">
          http://localhost:8000/v1/chat/completions
        </code>{" "}
        and your usage data will appear here automatically.
      </p>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Custom Recharts Tooltip
// ──────────────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="bg-card-bg border border-card-border rounded-xl px-4 py-3 shadow-xl">
      <p className="text-xs text-muted mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-semibold" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value}
        </p>
      ))}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Dashboard Page
// ──────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, logsRes] = await Promise.all([
        fetch(`${API_BASE}/v1/logs/summary`),
        fetch(`${API_BASE}/v1/logs?limit=200`),
      ]);

      if (!summaryRes.ok || !logsRes.ok) {
        throw new Error("Failed to fetch data from the backend.");
      }

      const summaryData: Summary = await summaryRes.json();
      const logsData: LogEntry[] = await logsRes.json();

      setSummary(summaryData);
      setLogs(logsData);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not connect to backend."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Auto-refresh every 5s
    return () => clearInterval(interval);
  }, [fetchData]);

  // ── Derived chart data ──────────────────────────────────────────

  // Cost over time (group by day)
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

  // Model distribution (pie chart)
  const modelDistribution = logs.reduce<{ name: string; value: number }[]>(
    (acc, log) => {
      const existing = acc.find((d) => d.name === log.model_name);
      if (existing) {
        existing.value += 1;
      } else {
        acc.push({ name: log.model_name, value: 1 });
      }
      return acc;
    },
    []
  );

  // Latency per model (bar chart)
  const latencyPerModel = logs.reduce<
    { model: string; avg_latency: number; count: number }[]
  >((acc, log) => {
    const existing = acc.find((d) => d.model === log.model_name);
    if (existing) {
      existing.avg_latency =
        (existing.avg_latency * existing.count + log.latency_ms) /
        (existing.count + 1);
      existing.count += 1;
    } else {
      acc.push({ model: log.model_name, avg_latency: log.latency_ms, count: 1 });
    }
    return acc;
  }, []);

  // ── Render ──────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-3 border-accent-blue border-t-transparent rounded-full animate-spin" />
          <p className="text-muted text-sm">Loading telemetry data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-card-bg border border-accent-rose/30 rounded-2xl p-8 max-w-md text-center">
          <p className="text-4xl mb-4">⚠️</p>
          <h2 className="text-xl font-bold text-foreground mb-2">
            Connection Error
          </h2>
          <p className="text-muted text-sm mb-4">{error}</p>
          <p className="text-muted text-xs">
            Make sure the backend is running on{" "}
            <code className="text-accent-blue">localhost:8000</code>
          </p>
          <button
            onClick={() => {
              setLoading(true);
              fetchData();
            }}
            className="mt-6 px-6 py-2 bg-accent-blue/20 border border-accent-blue/30 text-accent-blue rounded-xl text-sm font-medium hover:bg-accent-blue/30 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const hasData = summary && summary.total_requests > 0;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-card-border bg-card-bg/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center text-white text-sm font-bold">
              AI
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground tracking-tight">
                AI Telemetry
              </h1>
              <p className="text-xs text-muted -mt-0.5">
                Token & Cost Dashboard
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent-emerald/10 border border-accent-emerald/20">
              <div className="w-2 h-2 rounded-full bg-accent-emerald animate-pulse" />
              <span className="text-xs text-accent-emerald font-medium">
                Live
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {!hasData ? (
          <EmptyState />
        ) : (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <StatCard
                label="Total Requests"
                value={summary.total_requests.toLocaleString()}
                subtitle={`${summary.models_used.length} model${summary.models_used.length !== 1 ? "s" : ""} used`}
                accentColor="#3b82f6"
                icon="📊"
              />
              <StatCard
                label="Total Tokens"
                value={summary.total_tokens.toLocaleString()}
                subtitle={`${summary.total_prompt_tokens.toLocaleString()} in / ${summary.total_completion_tokens.toLocaleString()} out`}
                accentColor="#8b5cf6"
                icon="🔤"
              />
              <StatCard
                label="Total Cost"
                value={`$${summary.total_cost.toFixed(4)}`}
                subtitle="Based on model pricing"
                accentColor="#10b981"
                icon="💰"
              />
              <StatCard
                label="Avg Latency"
                value={`${summary.avg_latency_ms.toLocaleString()}ms`}
                subtitle="Per request average"
                accentColor="#f59e0b"
                icon="⚡"
              />
            </div>

            {/* Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* Cost Over Time — spans 2 columns */}
              <div className="lg:col-span-2 bg-card-bg border border-card-border rounded-2xl p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 tracking-wide">
                  Cost & Tokens Over Time
                </h3>
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={costOverTime}>
                    <defs>
                      <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 12 }} />
                    <YAxis
                      yAxisId="cost"
                      orientation="left"
                      tick={{ fill: "#64748b", fontSize: 12 }}
                      tickFormatter={(v) => `$${v}`}
                    />
                    <YAxis
                      yAxisId="tokens"
                      orientation="right"
                      tick={{ fill: "#64748b", fontSize: 12 }}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                      yAxisId="cost"
                      type="monotone"
                      dataKey="cost"
                      stroke="#10b981"
                      strokeWidth={2}
                      fill="url(#costGradient)"
                      name="Cost ($)"
                    />
                    <Area
                      yAxisId="tokens"
                      type="monotone"
                      dataKey="tokens"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      fill="url(#tokenGradient)"
                      name="Tokens"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Model Distribution Pie */}
              <div className="bg-card-bg border border-card-border rounded-2xl p-6">
                <h3 className="text-sm font-semibold text-foreground mb-4 tracking-wide">
                  Model Distribution
                </h3>
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie
                      data={modelDistribution}
                      cx="50%"
                      cy="45%"
                      innerRadius={55}
                      outerRadius={85}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {modelDistribution.map((_, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={CHART_COLORS[index % CHART_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<CustomTooltip />} />
                    <Legend
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ fontSize: "12px", color: "#94a3b8" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Latency Per Model */}
            <div className="bg-card-bg border border-card-border rounded-2xl p-6 mb-8">
              <h3 className="text-sm font-semibold text-foreground mb-4 tracking-wide">
                Average Latency by Model
              </h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={latencyPerModel} barCategoryGap="20%">
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="model" tick={{ fill: "#64748b", fontSize: 12 }} />
                  <YAxis
                    tick={{ fill: "#64748b", fontSize: 12 }}
                    tickFormatter={(v) => `${v}ms`}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar
                    dataKey="avg_latency"
                    name="Avg Latency (ms)"
                    radius={[8, 8, 0, 0]}
                  >
                    {latencyPerModel.map((_, index) => (
                      <Cell
                        key={`bar-${index}`}
                        fill={CHART_COLORS[index % CHART_COLORS.length]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Logs Table */}
            <div className="bg-card-bg border border-card-border rounded-2xl overflow-hidden">
              <div className="px-6 py-4 border-b border-card-border">
                <h3 className="text-sm font-semibold text-foreground tracking-wide">
                  Request Logs
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" id="logs-table">
                  <thead>
                    <tr className="border-b border-card-border text-left">
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider">
                        Timestamp
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider">
                        Model
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider">
                        Provider
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider text-right">
                        Prompt
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider text-right">
                        Completion
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider text-right">
                        Cost
                      </th>
                      <th className="px-6 py-3 text-muted font-medium text-xs uppercase tracking-wider text-right">
                        Latency
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr
                        key={log.id}
                        className="border-b border-card-border/50 hover:bg-table-hover transition-colors"
                      >
                        <td className="px-6 py-3 text-muted font-mono text-xs">
                          {new Date(log.timestamp).toLocaleString()}
                        </td>
                        <td className="px-6 py-3">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-accent-blue/10 text-accent-blue border border-accent-blue/20">
                            {log.model_name}
                          </span>
                        </td>
                        <td className="px-6 py-3 text-muted text-xs capitalize">
                          {log.provider}
                        </td>
                        <td className="px-6 py-3 text-right font-mono text-xs text-foreground">
                          {log.prompt_tokens.toLocaleString()}
                        </td>
                        <td className="px-6 py-3 text-right font-mono text-xs text-foreground">
                          {log.completion_tokens.toLocaleString()}
                        </td>
                        <td className="px-6 py-3 text-right font-mono text-xs text-accent-emerald">
                          {log.total_cost !== null
                            ? `$${log.total_cost.toFixed(6)}`
                            : "N/A"}
                        </td>
                        <td className="px-6 py-3 text-right font-mono text-xs text-accent-amber">
                          {log.latency_ms.toLocaleString()}ms
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

      {/* Footer */}
      <footer className="border-t border-card-border mt-auto py-6">
        <p className="text-center text-xs text-muted">
          AI Telemetry Tracker · Open Source · MIT License
        </p>
      </footer>
    </div>
  );
}
