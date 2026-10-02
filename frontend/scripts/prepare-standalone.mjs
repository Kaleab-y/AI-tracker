import { cp } from "node:fs/promises";

// Next's minimal server needs these assets when no external CDN is configured.
await cp("public", ".next/standalone/public", { recursive: true });
await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
