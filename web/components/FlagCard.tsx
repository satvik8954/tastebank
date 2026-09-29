import { type Flag, formatDate } from "@/lib/api";

const SEVERITY: Record<Flag["severity"], { label: string; cls: string }> = {
  high: { label: "Client would reject", cls: "bg-bad-soft text-bad" },
  medium: { label: "Client would ask to change", cls: "bg-warn-soft text-warn" },
  low: { label: "Polish", cls: "bg-line/60 text-muted" },
};

const MAX_QUOTE = 260;

export function FlagCard({ flag, memory }: { flag: Flag; memory: boolean }) {
  const sev = SEVERITY[flag.severity];
  return (
    <article className="rz-enter rounded-xl border border-line bg-card p-4 shadow-[0_1px_0_rgba(0,0,0,0.03)]">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide">
        <span className={`rounded-full px-2 py-0.5 ${sev.cls}`}>{sev.label}</span>
        <span className="text-muted">{flag.topic}</span>
        {flag.directive && (
          <span className="ml-auto rounded-full border border-memory/30 px-2 py-0.5 text-memory normal-case tracking-normal">
            Directive · {flag.directive}
          </span>
        )}
      </div>
      <h4 className="mt-2 font-medium leading-snug">{flag.issue}</h4>
      <p className="mt-1 text-sm text-muted">
        <span className="font-medium text-ink/70">Fix: </span>
        {flag.suggestion}
      </p>

      {flag.citations.length > 0 && (
        <div className="mt-3 space-y-2">
          {flag.citations.map((c) => {
            const quote = c.quote.length > MAX_QUOTE ? `${c.quote.slice(0, MAX_QUOTE - 1).trimEnd()}…` : c.quote;
            const where = c.project_name ? `${c.project_name}${c.round ? `, round ${c.round}` : ""}` : c.kind === "brief" ? "Brand brief" : c.kind;
            return (
              <blockquote key={c.document_id} className="border-l-2 border-memory bg-memory-soft/60 rounded-r-lg px-3 py-2">
                <p className="font-serif italic text-[17px] leading-snug text-ink">&ldquo;{quote}&rdquo;</p>
                <footer className="mt-1 text-xs text-muted">
                  <span className="font-medium text-ink/80">{c.author}</span>, {c.role} · {where} ·{" "}
                  <time className="font-medium text-memory">{formatDate(c.date)}</time>
                </footer>
              </blockquote>
            );
          })}
        </div>
      )}
      {!memory && (
        <p className="mt-3 text-xs text-muted italic">No client evidence: general design opinion.</p>
      )}
    </article>
  );
}
