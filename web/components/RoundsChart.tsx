import { type ProjectRow, formatDate } from "@/lib/api";

/** Bars = revision rounds per project, chronological. Round Zero-reviewed projects in memory
 *  colour, with before/after averages. */
export function RoundsChart({ projects }: { projects: ProjectRow[] }) {
  if (!projects.length) return <p className="text-sm text-muted">No projects yet.</p>;
  const max = Math.max(...projects.map((p) => p.rounds), 5);
  const before = projects.filter((p) => !p.reviewed_with_round_zero);
  const after = projects.filter((p) => p.reviewed_with_round_zero);
  const avg = (xs: ProjectRow[]) => (xs.length ? xs.reduce((s, p) => s + p.rounds, 0) / xs.length : null);
  const [avgBefore, avgAfter] = [avg(before), avg(after)];

  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <div className="flex items-end gap-1.5 h-40">
        {projects.map((p) => (
          <div key={p.project_id} className="flex-1 flex flex-col items-center justify-end h-full group relative">
            <span className="text-[10px] tabular-nums text-muted mb-0.5">{p.rounds}</span>
            <div
              className={`w-full rounded-t ${p.reviewed_with_round_zero ? "bg-memory" : "bg-muted/35"}`}
              style={{ height: `${(p.rounds / max) * 100}%` }}
            />
            <div className="pointer-events-none absolute bottom-full mb-1 hidden group-hover:block z-10 w-44 rounded-md bg-ink text-paper text-[11px] p-2">
              <p className="font-medium">{p.name}</p>
              <p className="opacity-70">{formatDate(p.started)} · {p.rounds} round{p.rounds > 1 ? "s" : ""}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-xs">
        <Legend cls="bg-muted/35" label="Before Round Zero" value={avgBefore} />
        <Legend cls="bg-memory" label="Pre-reviewed by Round Zero" value={avgAfter} />
      </div>
    </div>
  );
}

function Legend({ cls, label, value }: { cls: string; label: string; value: number | null }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-2.5 w-2.5 rounded-sm ${cls}`} />
      <span className="text-muted">{label}</span>
      {value !== null && <span className="font-semibold tabular-nums">avg {value.toFixed(1)}</span>}
    </div>
  );
}
