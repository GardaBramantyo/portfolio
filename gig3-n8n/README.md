# Gig 3 portfolio: n8n AI automation samples

Three importable n8n workflows (plus a shared error handler) that show what the gig delivers. Built by Claude with an AI-assisted process and verified on a local **n8n 2.40.7** instance: imported through the editor API **and** the `n8n import:workflow` CLI on a clean instance, opened on the canvas with no unknown nodes, and run end-to-end through mock scenarios (all passing, see `tests/`).

All credentials are placeholders (`"id": "REPLACE_ME"`). No API keys, tokens or real personal data are in any file. Every buyer-specific value is marked **SET ME**.

| File | What it shows | Nodes | Apps | Canvas |
|---|---|---|---|---|
| `01-ai-lead-qualifier.json` | Webhook/form → AI score → Google Sheets → Slack + email for hot leads | 12 (+4 notes) | Webhook, OpenAI, Sheets, Slack, Gmail | `01-ai-lead-qualifier.canvas.png` |
| `02-ai-support-email-triage.json` | Gmail → Claude categorises + drafts reply → label, draft in thread, log, escalate | 14 (+4 notes) | Gmail, Anthropic, Sheets, Slack | `02-ai-support-email-triage.canvas.png` |
| `03-ai-invoice-processor.json` | Email attachment or Drive upload → PDF text → **AI Agent with tools** → validation → Sheets + anomaly alerts | 18 (+5 notes) | Gmail, Drive, OpenAI, Sheets (as agent tools too), Slack | `03-ai-invoice-processor.canvas.png` |
| `00-error-handler.json` | Error Trigger → formatted Slack + email alert for any failed workflow | 4 (+3 notes) | Slack, Gmail | n/a |

Target compatibility: n8n Cloud and self-hosted **1.100+ and 2.x** (typeVersions chosen to exist in both; checked against 2.40.7's node catalogue).

---

## 01 · AI Lead Qualifier
**Flow:** `Lead Webhook` → `Normalize Lead` (maps common form field names) → `Valid Lead?` → instant `200`/`400` reply → `AI Qualify Lead` (OpenAI gpt-4.1-mini, JSON mode, ideal-customer rubric in the system prompt) → `Parse AI Score` (validates JSON, clamps score, tier from thresholds hot ≥ 70 / warm ≥ 40) → `Log Lead to Sheet` → `Hot Lead?` → Slack alert + email to the sales owner.
**Error handling:** AI node retries 3× then uses its **error output** into the parser, so the lead is still logged with tier `review`; Sheets/Slack/Gmail retry 3×; shared Error Handler for anything else.
**Tests (4/4 pass):** hot lead (logged + Slack + email), cold lead (logged only, fenced ```json output parsed), AI outage (logged as `review`, no alert), invalid submission (HTTP 400, AI never called).

## 02 · AI Support Email Triage
**Flow:** `New Support Email` (Gmail trigger, unread inbox, skips promotions and already-triaged) → `Config (SET ME)` (label IDs, company name, signature) → `Prepare Email` (strips quoted history, flags no-reply/auto-replies) → `Needs AI Triage?` → `AI Triage & Draft` (Claude Haiku 4.5) → `Parse Triage` (allowed values only) → `Apply Gmail Label` → `Save Draft Reply in Thread` (never auto-sends) → `Log Ticket` (Sheets) → `Escalate?` → Slack for urgent / negative / needs-human.
**Error handling:** Claude retries 3×; on failure the email is still labelled, logged as `needs_human`, and escalated with no draft.
**Tests (4/4 pass):** urgent technical email (full path + escalation, quoted history stripped), routine billing (draft, no escalation, category case normalised), no-reply auto-reply (skipped, no AI call), AI outage (no draft, escalated).

## 03 · AI Invoice & Receipt Processor (AI Agent)
**Flow:** two triggers (`Invoice Email Received` with PDF attachments, `New File in Invoices Folder` on Drive) → one item per PDF → `Extract PDF Text` → `Readable Text?` (scans go to manual review) → `Invoice Extraction Agent` (AI Agent v2, OpenAI) using tools **Vendor Directory** (Sheets), **Invoice Log Lookup** (Sheets, `$fromAI` invoice number), **Calculator**, with a **structured output parser** (JSON schema) → `Validate & Flag Anomalies` (plain code: line items vs subtotal, subtotal + tax + shipping − discount vs total, approval limit, currency, unapproved vendor, duplicate, date sanity, low confidence) → `Append to Invoice Log` → Slack alert when status is `review`.
**Error handling:** agent retries 2× then its error output goes to the manual-review Slack alert; unreadable PDFs take the same route; nothing is dropped silently.
**Tests (6/6 pass):** a **real generated PDF** through the real attachment-split and PDF-extraction nodes, clean invoice (`ok`, no alert), anomalous invoice (6 flags, alert), scanned PDF (manual review, no AI call), agent failure (manual review), Drive upload path.

---

## How these were tested (honest scope)
- `tests/*.mocks.json` + `tools/gig3-n8n/local-n8n.mjs mockrun` build a credential-free copy of each workflow on local n8n: the trigger becomes a webhook, and AI/app nodes (Gmail, Sheets, Slack, Drive, the AI chain/agent) return **mocked** outputs. Everything else runs for real: routing, IF branches, error outputs, Code-node parsing and validation, and (in the invoice test) PDF extraction from a real file. Results: `tests/*.mockrun-result.json`.
- This proves the wiring, the parsing and the fallbacks. It does not prove the model's judgement on a buyer's data, which is why every delivery includes a guided test run with the buyer's own key.

## Import a sample
n8n → **Create workflow** → **⋯ → Import from File…** → choose the JSON (or paste the JSON onto the canvas). Connect credentials, fill the SET ME fields (sheet headers in `sample-data/sheet-headers.md`), run once with `sample-data/`, then **Publish** (2.x) / **Active** (1.x).

## Files
- `sample-data/`: sample form submission, Gmail-trigger email, a fictional invoice PDF, Google Sheet header rows.
- `tests/`: mock scenario files and their latest results.
- Regenerate samples: `node tools/gig3-n8n/samples-src/build-samples.mjs` (see `tools/gig3-n8n/README.md`).
