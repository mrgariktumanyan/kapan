import type { ReactNode } from "react";

export function StatusDot({ level }: { level: "ok" | "warning" | "error" | string }) {
  const c = level === "ok" ? "bg-green-500" : level === "warning" ? "bg-yellow-400" : level === "error" ? "bg-red-500" : "bg-graphite-600";
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${c}`} />;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-md border border-red-800 bg-red-950/50 px-3 py-2 text-sm text-red-300">{error}</div>;
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-graphite-200">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Kpi({ label, value, unit, hint }: { label: string; value: string; unit?: string; hint?: string }) {
  return (
    <div className="rounded-md border border-graphite-800 bg-graphite-850 p-3" title={hint}>
      <div className="text-xs text-graphite-400">{label}</div>
      <div className="mt-1 font-mono text-xl text-white">
        {value}
        {unit && <span className="ml-1 text-sm text-graphite-400">{unit}</span>}
      </div>
    </div>
  );
}
