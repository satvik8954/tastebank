"use client";

import { useState } from "react";
import { api, type Client } from "@/lib/api";

type Phase = "idle" | "retaining" | "consolidating" | "done" | "error";

/** Log a client's real feedback: retain() into their bank, then wait for Hindsight to
 *  consolidate it into the taste profile. */
export function FeedbackForm({ client, bank, onConsolidated }: { client: Client; bank: string; onConsolidated: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  async function submit(form: FormData) {
    setPhase("retaining");
    setMessage("Retaining into Hindsight…");
    try {
      await api.logFeedback(
        {
          client_id: client.id,
          project_name: String(form.get("project")),
          author: String(form.get("author")),
          quote: String(form.get("quote")),
          round: Number(form.get("round")),
          date: String(form.get("date")),
          approved: form.get("approved") === "on",
        },
        bank,
      );
      setPhase("consolidating");
      const started = Date.now();
      // Poll the Operations API until consolidation is idle (two quiet polls in a row).
      let quiet = 0;
      while (quiet < 2 && Date.now() - started < 120_000) {
        await new Promise((r) => setTimeout(r, 2000));
        const ops = await api.operations(bank);
        quiet = ops.active ? 0 : quiet + 1;
        setMessage(ops.active ? `Hindsight is consolidating (${ops.types.join(", ")})…` : "Finishing…");
      }
      setPhase("done");
      setMessage(`Consolidated in ${Math.round((Date.now() - started) / 1000)}s. The taste profile is updated.`);
      onConsolidated();
    } catch (e) {
      setPhase("error");
      setMessage(String(e));
    }
  }

  const busy = phase === "retaining" || phase === "consolidating";
  const field = "w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm";

  return (
    <form action={submit} className="rounded-xl border border-line bg-card p-4 space-y-3">
      <input name="project" required placeholder="Project (e.g. Hydra Mist launch post)" className={field} />
      <div className="grid grid-cols-[1fr_5rem] gap-2">
        <select name="author" className={field}>
          {client.contacts.map((c) => (
            <option key={c.name} value={c.name}>{c.name}, {c.role}</option>
          ))}
        </select>
        <input name="round" type="number" min={1} defaultValue={1} className={field} title="Revision round" />
      </div>
      <textarea name="quote" required rows={3} placeholder="What the client said, verbatim" className={`${field} font-serif italic text-base`} />
      <div className="flex items-center gap-3">
        <input name="date" type="date" defaultValue={today} className={`${field} w-auto`} />
        <label className="flex items-center gap-1.5 text-sm text-muted">
          <input name="approved" type="checkbox" /> Approved
        </label>
      </div>
      <button disabled={busy} className="rounded-full bg-memory text-white px-5 py-2 text-sm font-semibold disabled:opacity-50">
        {busy ? "Working…" : "Retain feedback"}
      </button>
      {message && (
        <p className={`text-xs ${phase === "error" ? "text-bad" : phase === "done" ? "text-ok" : "text-memory rz-pulse"}`}>{message}</p>
      )}
    </form>
  );
}
