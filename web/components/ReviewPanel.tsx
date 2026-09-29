"use client";

import { useEffect, useRef, useState } from "react";
import { type Draft, type Review, type ReviewEvent, type ReviewMode, streamReview } from "@/lib/api";
import { FlagCard } from "./FlagCard";
import { ProgressTimeline } from "./ProgressTimeline";

export interface PanelSpec {
  title: string;
  subtitle: string;
  memory: boolean;
  bank?: string;
}

type Status = "idle" | "running" | "done" | "error";

/** One side of a comparison. The parent remounts it (key includes runId) for every run, so
 *  a panel instance streams at most one review; runId 0 means "not run yet". */
export function ReviewPanel({
  spec,
  draft,
  mode,
  runId,
}: {
  spec: PanelSpec;
  draft: Draft | null;
  mode: ReviewMode;
  runId: number;
}) {
  const [status, setStatus] = useState<Status>(runId && draft ? "running" : "idle");
  const [events, setEvents] = useState<ReviewEvent[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Props captured at mount: this instance reviews exactly what it was mounted with.
  const request = useRef({ draft, spec, mode, runId });

  useEffect(() => {
    const { draft, spec, mode, runId } = request.current;
    if (!runId || !draft) return;
    let stop: (() => void) | null = null;
    // Start on the next tick: React Strict Mode (dev) mounts effects twice, and the server
    // keeps running a review after the browser disconnects, so an immediate start would
    // cost a second set of Hindsight reflect calls.
    const timer = setTimeout(() => {
      stop = streamReview(
        { draft, memory: spec.memory, bank: spec.bank, mode },
        {
          onEvent: (e) => setEvents((prev) => [...prev, e]),
          onResult: (r) => {
            setReview(r);
            setStatus("done");
          },
          onError: (m) => {
            setError(m);
            setStatus("error");
          },
        },
      );
    }, 0);
    return () => {
      clearTimeout(timer);
      stop?.();
    };
  }, []);

  const accent = spec.memory ? "border-t-memory" : "border-t-muted/50";

  return (
    <section className={`rounded-2xl border border-line border-t-4 ${accent} bg-card/60 p-5 flex flex-col gap-4 min-w-0`}>
      <header className="flex items-start gap-3">
        <div className="min-w-0">
          <h3 className={`text-lg font-semibold ${spec.memory ? "text-memory" : ""}`}>{spec.title}</h3>
          <p className="text-xs text-muted">{spec.subtitle}</p>
        </div>
        {review && <Verdict review={review} />}
      </header>

      {status === "idle" && <p className="text-sm text-muted">Pick a draft and run the review.</p>}
      {events.length > 0 && (
        <details open={status === "running"} className="group">
          <summary className="cursor-pointer text-xs font-medium text-muted select-none">
            {status === "running" ? "Working…" : `How this review was made · ${review?.elapsed_s ?? ""}s`}
          </summary>
          <div className="mt-2">
            <ProgressTimeline events={events} running={status === "running"} />
          </div>
        </details>
      )}
      {error && <p className="rounded-lg bg-bad-soft text-bad text-sm px-3 py-2">{error}</p>}

      {review && (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed">{review.summary}</p>
          {review.flags.length === 0 && (
            <p className="rounded-lg bg-ok-soft text-ok text-sm px-3 py-2">
              Nothing in this draft conflicts with what the client has asked for.
            </p>
          )}
          {review.flags.map((f, i) => (
            <FlagCard key={i} flag={f} memory={review.memory} />
          ))}
          {review.discarded.length > 0 && (
            <details className="text-xs text-muted">
              <summary className="cursor-pointer select-none">
                {review.discarded.length} proposed issue{review.discarded.length > 1 ? "s" : ""} discarded by the verifier
              </summary>
              <ul className="mt-2 space-y-1.5">
                {review.discarded.map((d, i) => (
                  <li key={i}>
                    <span className="text-ink/70">{d.flag.issue}</span> <span className="italic">({d.reason})</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-[11px] text-muted">
            {review.engine}
            {review.memory && ` · ${review.memories_consulted} memories consulted`}
            {review.source === "replay" && ` · replayed recording${review.recorded_at ? ` from ${review.recorded_at.slice(0, 10)}` : ""}`}
          </p>
        </div>
      )}
    </section>
  );
}

function Verdict({ review }: { review: Review }) {
  const ready = review.verdict === "ready_for_client";
  return (
    <span
      className={`rz-enter ml-auto shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
        ready ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad"
      }`}
    >
      {ready ? "Ready for client" : `Needs changes · ${review.flags.filter((f) => f.severity !== "low").length}`}
    </span>
  );
}
