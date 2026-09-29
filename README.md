# Round Zero

**Catch the client's feedback before the client gives it.**

Round Zero is an AI pre-reviewer for creative agencies. It remembers every piece of feedback
each client has ever given, and reviews new design drafts against that memory *before* they
go out. Every flag cites the client's own words: who said it, on which project, and when.

Built for the Hindsight (Vectorize) memory hackathon. Hindsight is the core of the system,
not an add-on: remove it and the reviewer falls back to generic design opinions (see
[Memory ON vs OFF](#memory-on-vs-off)).

> Status: memory layer and reviewer complete and frozen (reviewer v1.0); FastAPI + SSE API and
> Next.js frontend working (review workspace, client dashboard, feedback logging).

---

## How Hindsight memory is used

| Hindsight feature | Where | What it does in Round Zero |
|---|---|---|
| **One memory bank per client** | `roundzero/memory/banks.py` | `rz-hale-whitford`, `rz-crunchd`, `rz-dewpoint`. Client tastes never mix. |
| **Mission** | per client, `data/clients/*.yaml` | "You are Round Zero, the pre-review assistant for <client>…" |
| **retain_mission** | `banks.py` | Extract colours (with hex), type, layout, imagery, copy, compliance, who said it, and reversals. |
| **observations_mission** | `banks.py` | Observations are the client's **taste profile**: one topic each (`[Colour]`, `[Typography]`, `[Layout]`, `[Imagery]`, `[Copy]`, `[Compliance]`), updated in place when a preference reverses. |
| **reflect_mission + disposition** | `banks.py`, YAML | Reviewer persona. Dewpoint (claims-heavy skincare) is maximally literal; Crunchd is flexible. |
| **Directives** | `banks.py`, YAML | Hard rules: bar-advertising disclaimer, no drug claims, no before/after, "evidence required", "most recent direction wins". |
| **retain()** | `scripts/seed.py`, `roundzero/memory/retain.py` | Every client quote is retained as its own document, **backdated** to when it was said, tagged `client:/project:/phase:`, with the quote, author, role, project and date in metadata. |
| **observation_scopes** | `retain.py` | `[["client:<id>"]]`. Hindsight's default scopes consolidation to the exact tag set, which would silo every project; client scope makes all feedback feed one taste profile. |
| **Operations API** | `roundzero/memory/client.py` | Seeding waits for extraction + consolidation after each project, so observations evolve in chronological order. |
| **Observations (+ proof_count, history)** | `scripts/inspect_bank.py`, `demo_rebrand.py` | The taste profile, with proof counts and observation history. |
| **recall()** | `roundzero/review/evidence.py` | One query per draft aspect (colour, typography, layout/imagery, copy) with `include_source_facts`, giving numbered, **dated** client quotes and observations. |
| **reflect()** | `roundzero/review/reviewer.py` | Reasons over the bank with mission, directives and disposition, and returns flags via `response_schema`, each citing evidence ids. |
| **clone_bank()** | `seed.py`, `demo_rebrand.py` | Server-side snapshots for the rebrand demo (`-before`, `-after`) and instant reset. |

### The review pipeline

```
draft.png
  ├─ palette.py   colours, background, grain: measured from pixels (never guessed)
  ├─ vision.py    layout, type, copy, imagery: qwen/qwen3.8-27b on Groq (cached per image)
  │
  ├─ recall ×4    what has this client said about colour / type / layout / copy?  (Hindsight)
  ├─ reflect      predict the client's feedback, cite evidence ids                  (Hindsight)
  ├─ verify       is each flag really in the draft, backed by a current, applicable
  │               client instruction? fill missing citations                         (Groq, gpt-oss-120b)
  └─ resolve      evidence ids → real quotes: author, role, project, date
```

Progress streams as events (`roundzero/review/progress.py`) so the UI shows memory working:
recall counts per aspect, the observations being checked, flags proposed, verified and discarded.

---

## The demo

**1. Memory ON vs OFF (Dewpoint skincare).** Same draft, same description, only memory differs.
Without memory, the reviewer recommends a *more clinical* look. Dewpoint's founder has said
the opposite twice ("blue feels like a pharmacy. We're warm"). With memory, the reviewer
catches the drug claim, before/after, product angle, missing ingredient percentages,
gradients and "anti-aging", each with the client's quote.

**2. Memory knows *when* (Crunchd rebrand).** The same pastel draft is:
- **ready for client** against Crunchd's memory *before* the June 2026 rebrand (it matches
  their approved pattern exactly), and
- **flagged** against memory *after* it, citing Theo's rebrand brief (2026-06-02) and
  "Drop the grain and the vintage grade" (2026-06-18).

A memory-less reviewer gives the same advice at both moments, so it is wrong at one of them.

```bash
python scripts/demo_rebrand.py            # live: retain the rebrand, show observations change (+ timing)
python scripts/demo_rebrand.py --fallback # no writes: before vs after taste profile
python scripts/demo_rebrand.py --reset    # restore the pre-rebrand bank
```

### Stage fallback: record/replay

Every live review is recorded to `data/recordings/` (committed). If the network or rate
limits misbehave on stage, replay plays the same review back, including progress events at
their original pace:

```bash
RZ_REVIEW_MODE=replay   # always replay     (also switchable per request from the UI)
RZ_REVIEW_MODE=auto     # live, fall back to the recording on any failure
```

---

## Setup

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[drafts]"   # Windows paths shown
cp .env.example .env        # HINDSIGHT_URL, HINDSIGHT_API_KEY, GROQ_API_KEY
python scripts/seed.py      # ~7 min on Hindsight Cloud; uses Cloud credits
python scripts/final_check.py   # re-runs + re-records every demo review

# app
.venv/Scripts/uvicorn api.main:app --port 8000          # API (SSE review stream)
cd web && npm install && npm run dev                     # UI on http://localhost:3000
```

The UI: **Review** (pick client + draft, compare memory ON vs OFF or before vs after the
rebrand, with streaming progress and cited flag cards; Live / fallback / Recording switch)
and **Clients** (taste profile by topic with proof counts and history, revision rounds per
project, and a form that logs real client feedback via `retain()` and waits for consolidation).
Logging feedback writes to the client's Hindsight bank: don't use it on demo banks before judging.

| Script | Purpose |
|---|---|
| `seed.py` | Create banks, retain 91 client quotes chronologically, build the Crunchd before/after banks |
| `inspect_bank.py <bank> [--history]` | Print a taste profile with proof counts and history |
| `review_draft.py <png> [--bank] [--no-memory]` | Review one draft with live progress |
| `compare_draft.py <png>` | Memory ON vs OFF side by side |
| `check_rebrand_case.py [--runs N]` | Acceptance test for the rebrand demo |
| `final_check.py` | All demo reviews, live, recorded |
| `make_drafts.py` | Re-render demo drafts from HTML templates with Playwright |

Synthetic data: three fictional clients in `data/clients/` (a conservative law firm, a Gen-Z
snack brand, a D2C skincare brand), 27 projects, 91 dated client quotes, with stakeholder
contradictions and one taste shift. Demo drafts and their deliberately planted issues:
`data/drafts/drafts.yaml`.

---

## Limitations

We would rather you hear these from us.

**Known misses (reviewer v1.0, final recorded run):**
- **"Clinically proven"** (Dewpoint) was never raised by memory-ON review, although the
  "No drug claims" directive names it. The memory-OFF reviewer did catch it.
- **Ice-blue palette** (Dewpoint) was missed in the final recorded run; it was caught in 3
  of 4 earlier runs. This is run-to-run variance in reflect's proposals.
- **"anti-aging"** (Dewpoint) was caught in the final run, but in 2 of 4 earlier runs the
  verifier wrongly discarded it as "specific to the web banner project".
- **Logo position** (Hale & Whitford) was missed in every run except the last, where the
  flag is vaguely worded.

**Nondeterminism.** reflect proposes a somewhat different flag set each run. Verdicts on the
demo cases held with the final reviewer (the rebrand check passed every run after the last
verifier change: 2 live, 1 with a replayed reflect; the final check gave every expected
verdict), but that is a handful of runs, and earlier development versions failed several.
Individual flags come and go between runs.

**Observations do not always update in place.** When the Crunchd rebrand reversed the pastel
palette, Hindsight consolidation sometimes *replaced* the old colour observation instead of
updating it, so its history does not link back to the pastel version (the new text still
says what it superseded). The rebrand demo therefore compares the `-before` and `-after`
banks directly; the history API is shown where it exists.

**In-sample tuning.** Prompts, the verifier's rules and one demo draft were adjusted during
development against these same drafts. There is no held-out evaluation set, so treat the
catch rates above as a demo, not a benchmark. Changes made, for transparency:
- Verifier rule: medium-specific rules (photo grading, retouching, OOH legibility) only apply
  to that medium; scope-based discards are only honoured for Imagery/Layout flags.
- The pastel Crunchd draft was changed to match the client's approved pre-rebrand pattern
  (one medium-weight line, no text pill), because the first version genuinely broke two
  pre-rebrand rules.

**Model limits.** The vision model misreads things occasionally (it once called a peach
background "white" and an off-centre product "central"), which is why colours, background
and grain are measured in code and extractions are cached. On Groq's free tier (8k
tokens/min per model), a verify call is ~2-3k tokens, so reviews back-to-back within a
minute switch to the fallback model or slow down; use replay mode on stage.
