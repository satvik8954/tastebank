import type { ReviewEvent } from "@/lib/api";

const STAGE_LABEL: Record<string, string> = {
  extract: "Read draft",
  recall: "Recall",
  evidence: "Evidence",
  reflect: "Reflect",
  verify: "Verify",
  done: "Done",
  error: "Fallback",
};

/** Live list of what the reviewer is doing. Start events are replaced by their done event. */
export function ProgressTimeline({ events, running }: { events: ReviewEvent[]; running: boolean }) {
  const rows: ReviewEvent[] = [];
  for (const e of events) {
    const last = rows[rows.length - 1];
    if (last && last.status === "start" && last.stage === e.stage && e.status !== "start") rows[rows.length - 1] = e;
    else rows.push(e);
  }
  return (
    <ol className="space-y-1.5 text-sm">
      {rows.map((e, i) => {
        const active = running && i === rows.length - 1 && e.status === "start";
        const checking = (e.data.checking as string[] | undefined) ?? [];
        const proposed = (e.data.proposed as string[] | undefined) ?? [];
        return (
          <li key={i} className="rz-enter grid grid-cols-[3.2rem_4.6rem_1fr] gap-2">
            <span className="tabular-nums text-xs text-muted pt-0.5">{e.t.toFixed(1)}s</span>
            <span className={`text-xs font-medium pt-0.5 ${e.stage === "recall" || e.stage === "reflect" ? "text-memory" : "text-ink/70"}`}>
              {STAGE_LABEL[e.stage] ?? e.stage}
            </span>
            <div>
              <span className={active ? "rz-pulse" : ""}>{e.message}</span>
              {checking.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {checking.map((c, j) => (
                    <li key={j} className="text-xs text-muted truncate">
                      <span className="text-memory">checking</span> {c.replace(/^\[\w+\]\s*/, "")}
                    </li>
                  ))}
                </ul>
              )}
              {proposed.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {proposed.map((p, j) => (
                    <li key={j} className="text-xs text-muted truncate">proposed · {p}</li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
