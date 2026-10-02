import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Telemetry",
  description: "Token usage, costs, and latency tracking for LLM APIs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
