"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Client, type ProjectRow, type TasteProfile as Profile } from "@/lib/api";
import { FeedbackForm } from "./FeedbackForm";
import { RoundsChart } from "./RoundsChart";
import { TasteProfile } from "./TasteProfile";

export function ClientDashboard({ clientId }: { clientId: string }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [selectedBank, setBank] = useState<string | null>(null);
  // Profile is stored with the bank + version it was fetched for; "loading" is derived.
  const [loaded, setLoaded] = useState<{ key: string; profile: Profile } | null>(null);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const client = clients.find((c) => c.id === clientId);
  const bank = selectedBank && client?.banks.some((b) => b.id === selectedBank) ? selectedBank : client?.banks[0].id ?? null;
  const key = `${bank}#${version}`;
  const profile = loaded?.key === key ? loaded.profile : null;

  useEffect(() => {
    api.clients().then(setClients).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!bank) return;
    let live = true;
    api.profile(bank).then((p) => live && setLoaded({ key, profile: p })).catch((e) => live && setError(String(e)));
    api.projects(clientId).then((p) => live && setProjects(p)).catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [bank, clientId, key]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  if (error) return <p className="p-10 text-sm text-bad">{error}</p>;
  if (!client) return <p className="p-10 text-sm text-muted">Loading…</p>;

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6 space-y-8">
      <nav className="flex gap-2 text-sm">
        {clients.map((c) => (
          <Link
            key={c.id}
            href={`/clients/${c.id}`}
            className={`rounded-full px-3 py-1 ${c.id === clientId ? "bg-ink text-paper" : "text-muted hover:bg-line/50"}`}
          >
            {c.name}
          </Link>
        ))}
      </nav>

      <header className="flex flex-wrap items-end gap-6">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">{client.industry}</p>
          <h1 className="font-serif text-5xl leading-tight">{client.name}</h1>
          <p className="text-sm text-muted mt-1">
            {client.contacts.map((c) => `${c.name} (${c.role})`).join(" · ")}
          </p>
        </div>
        <Palette colours={client.brand.palette} label="Brand palette" />
        {client.brand_after_rebrand && <Palette colours={client.brand_after_rebrand.palette} label="After rebrand" />}
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-8 items-start">
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold">Taste profile</h2>
            <span className="text-xs text-muted">Hindsight observations, consolidated from every piece of feedback</span>
            {client.banks.length > 1 && (
              <div className="ml-auto inline-flex rounded-full bg-line/60 p-1">
                {client.banks.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => setBank(b.id)}
                    className={`rounded-full px-3 py-1 text-xs font-medium ${b.id === bank ? "bg-card shadow-sm" : "text-muted"}`}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {bank && <TasteProfile profile={profile} bank={bank} />}
        </section>

        <aside className="space-y-8">
          <section>
            <h2 className="text-xl font-semibold">Revision rounds</h2>
            <p className="text-xs text-muted mb-3">Rounds to approval per project, oldest first</p>
            <RoundsChart projects={projects} />
          </section>
          <section>
            <h2 className="text-xl font-semibold">Log client feedback</h2>
            <p className="text-xs text-muted mb-3">Retained into {bank}; the taste profile updates after consolidation</p>
            {bank && <FeedbackForm client={client} bank={bank} onConsolidated={refresh} />}
          </section>
        </aside>
      </div>
    </div>
  );
}

function Palette({ colours, label }: { colours: Record<string, string>; label: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted mb-1">{label}</p>
      <div className="flex gap-1.5">
        {Object.entries(colours).map(([name, hex]) => (
          <div key={name} title={`${name} ${hex}`} className="h-8 w-8 rounded-md border border-black/10" style={{ background: hex }} />
        ))}
      </div>
    </div>
  );
}
