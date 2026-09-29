"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ReviewPanel, type PanelSpec } from "@/components/ReviewPanel";
import { UploadDraft } from "@/components/UploadDraft";
import { api, assetUrl, type Client, type Draft, type ReviewMode } from "@/lib/api";

type Comparison = "memory" | "rebrand";

// Demo order: Dewpoint (memory ON vs OFF) first, then Crunchd (before vs after rebrand).
const CLIENT_ORDER = ["dewpoint", "crunchd", "hale-whitford"];

export default function ReviewWorkspace() {
  const [clients, setClients] = useState<Client[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [clientId, setClientId] = useState("dewpoint");
  const [draftFile, setDraftFile] = useState<string | null>(null);
  const [comparison, setComparison] = useState<Comparison>("memory");
  const [mode, setMode] = useState<ReviewMode>("live");
  const [runId, setRunId] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.clients(), api.drafts(), api.config()])
      .then(([c, d, cfg]) => {
        setClients([...c].sort((a, b) => CLIENT_ORDER.indexOf(a.id) - CLIENT_ORDER.indexOf(b.id)));
        setDrafts(d);
        setMode(cfg.review_mode);
      })
      .catch((e) => setLoadError(String(e)));
  }, []);

  const client = clients.find((c) => c.id === clientId);
  const clientDrafts = useMemo(() => drafts.filter((d) => d.client === clientId), [drafts, clientId]);
  const draft = clientDrafts.find((d) => d.file === draftFile) ?? clientDrafts[0] ?? null;
  const hasRebrand = !!client?.banks.some((b) => b.id.endsWith("-after"));

  function pickClient(id: string) {
    setClientId(id);
    setDraftFile(null);
    setRunId(0);
    setComparison(id === "crunchd" ? "rebrand" : "memory");
  }

  const panels: [PanelSpec, PanelSpec] | null = !client
    ? null
    : comparison === "rebrand" && hasRebrand
      ? [
          { title: "Memory before the rebrand", subtitle: "What Crunchd had said up to May 2026", memory: true, bank: `${client.banks[0].id}-before` },
          { title: "Memory after the rebrand", subtitle: "Including the June 2026 rebrand and what followed", memory: true, bank: `${client.banks[0].id}-after` },
        ]
      : [
          { title: "Without memory", subtitle: `A capable reviewer who has never worked with ${client.name}`, memory: false },
          { title: "With Hindsight memory", subtitle: `Everything ${client.name} has told us, recalled and reasoned over`, memory: true, bank: client.banks[0].id },
        ];

  if (loadError)
    return (
      <div className="mx-auto max-w-xl p-10 text-sm">
        <p className="font-medium">Can&apos;t reach the Round Zero API.</p>
        <p className="text-muted mt-1">Start it with <code>uvicorn api.main:app --port 8000</code>. ({loadError})</p>
      </div>
    );

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6 grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
      {/* Left rail: client + draft */}
      <aside className="space-y-5">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">Client</h2>
          <div className="flex flex-col gap-1">
            {clients.map((c) => (
              <button
                key={c.id}
                onClick={() => pickClient(c.id)}
                className={`text-left rounded-lg px-3 py-2 transition ${
                  c.id === clientId ? "bg-ink text-paper" : "hover:bg-line/50"
                }`}
              >
                <div className="text-sm font-medium">{c.name}</div>
                <div className={`text-xs truncate ${c.id === clientId ? "text-paper/70" : "text-muted"}`}>{c.industry}</div>
              </button>
            ))}
          </div>
          {client && (
            <Link href={`/clients/${client.id}`} className="mt-2 inline-block text-xs text-memory hover:underline">
              {client.name}&apos;s taste profile →
            </Link>
          )}
        </div>

        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">Draft</h2>
          <div className="grid grid-cols-2 gap-2">
            {clientDrafts.map((d) => (
              <button
                key={d.file}
                onClick={() => {
                  setDraftFile(d.file);
                  setRunId(0);
                }}
                className={`rounded-lg overflow-hidden border-2 transition ${
                  d.file === draft?.file ? "border-ink" : "border-transparent hover:border-line"
                }`}
                title={d.project}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={assetUrl(d.url)} alt={d.project} className="aspect-square w-full object-cover bg-line" />
              </button>
            ))}
          </div>
          {client && <UploadDraft client={client} onUploaded={(d) => { setDrafts((prev) => [...prev, d]); setDraftFile(d.file); setRunId(0); }} />}
        </div>
      </aside>

      {/* Main: draft + controls + comparison */}
      <div className="space-y-6 min-w-0">
        {draft && (
          <div className="grid grid-cols-1 md:grid-cols-[minmax(0,420px)_1fr] gap-6 items-start">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={assetUrl(draft.url)} alt={draft.project} className="w-full rounded-xl border border-line shadow-sm bg-card" />
            <div className="space-y-4">
              <div>
                <p className="text-xs text-muted uppercase tracking-wide">{client?.name} · {draft.format.replace(/_/g, " ")}</p>
                <h1 className="font-serif text-4xl leading-tight mt-1">{draft.project}</h1>
              </div>

              <Segmented
                label="Compare"
                value={comparison}
                onChange={(v) => { setComparison(v as Comparison); setRunId(0); }}
                options={[
                  { value: "memory", label: "Memory ON vs OFF" },
                  ...(hasRebrand ? [{ value: "rebrand", label: "Before vs after rebrand" }] : []),
                ]}
              />
              <Segmented
                label="Source"
                value={mode}
                onChange={(v) => setMode(v as ReviewMode)}
                options={[
                  { value: "live", label: "Live" },
                  { value: "auto", label: "Live, fallback to recording" },
                  { value: "replay", label: "Recording" },
                ]}
              />

              <button
                onClick={() => setRunId((n) => n + 1)}
                className="rounded-full bg-ink text-paper px-6 py-3 text-sm font-semibold hover:bg-ink/85 transition"
              >
                Run pre-client review
              </button>
            </div>
          </div>
        )}

        {panels && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start">
            <ReviewPanel key={`${panels[0].title}-${draft?.file}-${runId}`} spec={panels[0]} draft={draft} mode={mode} runId={runId} />
            <ReviewPanel key={`${panels[1].title}-${draft?.file}-${runId}`} spec={panels[1]} draft={draft} mode={mode} runId={runId} />
          </div>
        )}
      </div>
    </div>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-muted w-16">{label}</span>
      <div className="inline-flex rounded-full bg-line/60 p-1">
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              o.value === value ? "bg-card shadow-sm text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
