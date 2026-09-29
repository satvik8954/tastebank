"use client";

import { useState } from "react";
import { api, type Client, type Draft } from "@/lib/api";

const FORMATS = ["instagram_post", "instagram_carousel", "linkedin_post", "web_banner", "poster"];

export function UploadDraft({ client, onUploaded }: { client: Client; onUploaded: (d: Draft) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(form: FormData) {
    const file = form.get("file") as File | null;
    if (!file || !file.size) return setError("Choose an image");
    setBusy(true);
    setError(null);
    try {
      onUploaded(await api.uploadDraft(file, client.id, String(form.get("project")), String(form.get("format"))));
      setOpen(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <button onClick={() => setOpen(true)} className="mt-2 w-full rounded-lg border border-dashed border-line py-2 text-xs text-muted hover:text-ink hover:border-muted">
        + Upload a draft for {client.name}
      </button>
    );

  return (
    <form action={submit} className="mt-2 space-y-2 rounded-lg border border-line bg-card p-3 text-xs">
      <input name="file" type="file" accept="image/png,image/jpeg,image/webp" className="w-full" />
      <input name="project" required placeholder="Project name" className="w-full rounded border border-line bg-paper px-2 py-1.5" />
      <select name="format" className="w-full rounded border border-line bg-paper px-2 py-1.5">
        {FORMATS.map((f) => (
          <option key={f} value={f}>{f.replace(/_/g, " ")}</option>
        ))}
      </select>
      {error && <p className="text-bad">{error}</p>}
      <div className="flex gap-2">
        <button disabled={busy} className="rounded-full bg-ink text-paper px-3 py-1.5 font-medium disabled:opacity-50">
          {busy ? "Uploading…" : "Upload"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-muted">Cancel</button>
      </div>
    </form>
  );
}
