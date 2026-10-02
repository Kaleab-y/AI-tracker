import type { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  if (
    ![
      "health",
      "v1/logs",
      "v1/logs/summary",
      "v1/logs/options",
      "v1/logs/export",
    ].includes(endpoint)
  ) {
    return Response.json(
      { detail: "Unknown telemetry endpoint" },
      { status: 404 },
    );
  }
  try {
    const base = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const upstream = await fetch(
      `${base}/${endpoint}${request.nextUrl.search}`,
      {
        cache: "no-store",
        signal: AbortSignal.timeout(30_000),
        redirect: "error",
      },
    );
    const headers = new Headers({ "Cache-Control": "no-store" });
    for (const key of [
      "content-type",
      "content-disposition",
      "x-total-count",
    ]) {
      const value = upstream.headers.get(key);
      if (value) headers.set(key, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return Response.json(
      { detail: "Cannot reach the tracker backend. Check that it is running." },
      { status: 502 },
    );
  }
}
