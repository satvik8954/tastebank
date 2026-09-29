"use client";

import { useState } from "react";
import { api, type Observation, type ObservationChange, type TasteProfile as Profile } from "@/lib/api";

export function TasteProfile({ profile, bank }: { profile: Profile | null; bank: string }) {
  if (!profile) return <p className="text-sm text-muted rz-pulse">Reading observations from Hindsight…</p>;
  const max = Math.max(1, ...Object.values(profile.topics).flat().map((o) => o.proof_count));
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {Object.entries(profile.topics).map(([topic, items]) => (
        <div key={topic} className="rounded-xl border border-line bg-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-memory mb-3">{topic}</h3>
          <ul className="space-y-3">
            {items.map((o) => (
              <ObservationRow key={o.id} obs={o} bank={bank} max={max} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ObservationRow({ obs, bank, max }: { obs: Observation; bank: string; max: number }) {
  const [history, setHistory] = useState<ObservationChange[] | null>(null);
  const [open, setOpen] = useState(false);

  async function toggle() {
    setOpen((o) => !o);
    if (!history) setHistory(await api.history(bank, obs.id).catch(() => []));
  }

  return (
    <li className="text-sm">
      <div className="flex items-start gap-3">
        <div className="w-14 shrink-0 pt-1" title={`${obs.proof_count} supporting pieces of feedback`}>
          <div className="h-1.5 rounded-full bg-line overflow-hidden">
            <div className="h-full bg-memory" style={{ width: `${(obs.proof_count / max) * 100}%` }} />
          </div>
          <p className="text-[10px] text-muted mt-0.5 tabular-nums">proof {obs.proof_count}</p>
        </div>
        <div className="min-w-0">
          <p className="leading-snug">{obs.text}</p>
          <button onClick={toggle} className="mt-1 text-[11px] text-memory hover:underline">
            {open ? "Hide history" : "How this changed"}
          </button>
          {open && (
            <div className="mt-2 border-l-2 border-line pl-3 space-y-2">
              {history === null && <p className="text-xs text-muted rz-pulse">Loading…</p>}
              {history?.length === 0 && <p className="text-xs text-muted">No earlier versions: formed as it reads now.</p>}
              {history?.map((h, i) => (
                <p key={i} className="text-xs text-muted leading-snug">
                  <span className="font-medium text-ink/60">Previously: </span>
                  {h.previous_text}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
