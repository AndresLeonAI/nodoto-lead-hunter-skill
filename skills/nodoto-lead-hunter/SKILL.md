---
name: nodoto-lead-hunter
description: High-ticket sales opportunity engine for NODOTO AGENCY. Discovers Bogotá businesses in one niche at a time with weak digital presence, identifies the owner/decision-maker and their publicly-verifiable professional phone, audits the real website, scores and dedupes the result, and writes only fully-qualified leads to the NODOTO Google Sheet via Composio (with an automatic CSV fallback/mirror). Use when asked to find leads, prospect, hunt for clients, or run lead generation for NODOTO.
---

# NODOTO LEAD HUNTER

A high-ticket sales opportunity engine, not a generic scraper. It exists to answer
one question per business: **can NODOTO actually reach the person who decides,
with a real reason to talk to them?**

```
BUSINESS → OWNER/DECISION MAKER → PHONE → WEBSITE/SOCIALS → DIGITAL OPPORTUNITY
```

This skill is **additive** to the existing repo. It does not touch
`docs/outreach_playbook.md`'s cold-email sending policy, `data/sent_tracking.csv`,
follow-up logic, or the blacklist mechanics — it only discovers and qualifies new
leads and writes them somewhere new (a fresh Google Sheet / worksheet, or CSV).
Read `docs/outreach_playbook.md` and `docs/methodology_and_status.md` first, every
run — they are still the operative source of truth for niches, anti-fabrication
rules, and Bogotá-only scope, which this skill inherits rather than redefines.

## The one rule that overrides every other rule

**A lead is never "Qualified" without a publicly verifiable, professional phone
number belonging to the OWNER/decision-maker — not the business's generic line.**
No score, no amount of polish on the website audit, no urgency in the niche
buys past this. If it's missing: `Owner Phone = NOT_VERIFIED`,
`Qualification Status = OWNER_PHONE_MISSING`, and the lead goes to the
`Candidates - Owner Phone Missing` list, never to `Qualified Leads`.

Owner phone priority (highest to lowest):
1. Phone the professional publishes themselves (own website, own booking page).
2. Professional WhatsApp of the owner specifically.
3. Phone/WhatsApp publicly associated with the owner by name (news, interview, directory).
4. Phone on the owner's personal/professional website.
5. Phone in the owner's own professional social profiles (Instagram bio, LinkedIn).
6. Reliable public professional directories (medical boards, bar associations, etc.).
7. Public business registries where legally available.

Never: guess, infer, autocomplete, pad digits, use leaked/private databases, or
silently relabel the business's generic phone as the owner's. If the same digits
as the business line are the only thing found, that is **not** an owner phone
unless there's explicit evidence the owner personally publishes that same number.

## Pipeline

```
READ REPO → READ GOOGLE SHEET → SELECT NICHE (opportunity score) →
DISCOVER (20-40 candidates, one niche only) → RESEARCH →
IDENTIFY OWNER → FIND OWNER PHONE → AUDIT WEBSITE → FIND SOCIALS →
SCORE + GATE → DEDUPE (repo + sheet) → WRITE (append-only) → READ BACK → VERIFY
```

### 0. Read repo + read Sheet

- Read `docs/outreach_playbook.md` and `docs/methodology_and_status.md`.
- Load existing dedupe fingerprints: `python3 skills/nodoto-lead-hunter/scripts -c` isn't
  a thing — import and call `dedupe.load_all_repo_sources(repo_root)` (covers
  `bogota_leads.csv`, `known_bad_contacts.csv`, `sent_tracking.csv`).
- Identify the correct Composio-connected NODOTO Google account and the
  operative spreadsheet. Follow `references/composio_tools.md` step by step.
  **If the account can't be determined with certainty, stop before writing
  anything and say so in the final report** — proceed with discovery/research
  regardless, output goes to CSV only for that run.
- Read the target worksheet's header + existing rows; fold them into the same
  dedupe fingerprint set via `dedupe.load_sheet_rows()`.

### 1. Select the niche (dynamic, not random)

Pick ONE niche from the 50 in `docs/outreach_playbook.md` for the entire run.
Rank candidates by a **Niche Opportunity Score** combining:
economic potential, urgency, existing lead count for that niche (fewer = more
room), % with a bad/missing website, % with an identified owner, % with an
owner phone, competition, and ease of reaching a decision-maker. Favor
HIGH TICKET + WEBSITE GAP + LOW COVERAGE + OWNER ACCESS. Cross-reference
against `bogota_leads.csv`'s `Industry/Niche` column and the Sheet's `Niche`
column to see what's already saturated. Do not mix niches within a run.

### 2. Discover (20-40 candidates)

Search Google/Maps/directories for real businesses in that niche, in Bogotá,
matching the high-ticket profile in `docs/outreach_playbook.md` section 1 and
respecting its exclusions (section 2). Real businesses only — no invented
names, no invented addresses.

### 3. Research + owner discovery engine

For each candidate, go beyond the Maps listing. Search:
`"<business>" owner`, `"<business>" fundador`, `"<business>" director`,
`"<business>" Dr.`, `"<business>" LinkedIn`, `site:linkedin.com "<business>"`,
`site:instagram.com "<business>"`. Objective: business → decision-maker.
Roles to look for: Owner, Founder, Co-Founder, Partner, Managing Partner,
Director, lead Doctor/Professional, CEO, Principal, Administrador/propietario.

### 4. Owner phone discovery

Once the owner is named, search specifically:
`"<owner name>" Bogotá teléfono`, `"<owner name>" WhatsApp`,
`"<owner name>" Instagram`, `"<owner name>" LinkedIn`, `"<owner name>" website`,
`"<owner name>" clínica/despacho/estudio`, plus relevant professional
directories. Only public, professionally-published numbers count — never
private or leaked data. Record `Owner Phone Source` with enough specificity to
audit later (e.g. "Instagram oficial @drname, bio", not just "Instagram").

### 5. Website audit (visit it for real)

Actually open the site (or confirm it doesn't exist / is down). Judge it
against: missing/dead site, outdated design, generic template, weak
hierarchy, poor mobile experience, weak/absent CTA, no WhatsApp link, no
booking, no social proof, weak value prop, poor photography, weak branding,
stale content, broken links/errors, poor local SEO, positioning below the
business's real market level. Record exactly ONE primary `Website Problem`
with concrete, checkable `Website Evidence` — never a vague adjective.

Bad: `Website is bad.`
Good: `The homepage has no clear primary CTA above the fold and the only
contact path is a generic phone number in the footer.`

### 6. Social discovery

Find and verify (don't guess) official Instagram, Facebook, LinkedIn, TikTok
(if relevant), and the owner's own professional profile. A profile only
counts as "official" if there's real evidence it belongs to this business/person
(bio matches, linked from the real site, tagged posts, etc.) — never assume from
a similar-looking username.

### 7. Score, validate, and gate

Populate `high_ticket_score`, `website_opportunity_score`, `owner_access_score`,
`data_quality_score` (0-10 each, based on what was actually found) on a
`schema.Lead`, then run it through the gate AND the evidence-quality check
(a lead can satisfy the gate's "field is non-empty" test while still being
too vague to trust — `validate.py` catches that):

```python
import sys; sys.path.insert(0, "skills/nodoto-lead-hunter/scripts")
from schema import Lead
from scoring import run_qualification_gate
from validate import validate_evidence_quality

lead = Lead(business_name=..., niche=..., owner_name=..., owner_role=...,
            owner_phone=..., owner_phone_source=..., website_problem=...,
            website_evidence=..., high_ticket_score=..., website_opportunity_score=...,
            owner_access_score=..., data_quality_score=...)
result = run_qualification_gate(lead)
# result.passed, result.status, result.reasons ; lead.lead_score, lead.lead_tier now set
quality = validate_evidence_quality(lead)
# quality.ok must also be True — a generic Owner Phone Source ("Instagram" alone)
# or a vague Website Problem ("website is bad") fails validation even if the
# gate's non-empty check passed.
```

Weights: Business Value 25%, Website Opportunity 30%, Owner Access 20%, Contact
Data Quality 15%, Market/Urgency 10% (fold urgency into `high_ticket_score` unless
you pass `market_urgency_score` explicitly). Tiers: 9.0-10 VIP, 8.0-8.9 A,
7.0-7.9 B, below 7 discard. **`OWNER_PHONE_MISSING` always overrides tier/score.**

### 8. Dedupe

```python
from dedupe import load_all_repo_sources, load_sheet_rows, find_duplicate, find_fuzzy_candidates
existing = load_all_repo_sources(repo_root) + load_sheet_rows(sheet_rows_as_dicts)
dup = find_duplicate(lead, existing)          # exact-signal match -> auto-drop
fuzzy = find_fuzzy_candidates(lead, existing)  # near-miss names -> flag for a second look, don't auto-drop
```

Matches on normalized owner phone, domain, email, Instagram handle, or
normalized business/owner name (order- and stopword-insensitive, catches
"Dr. Juan Pérez Dermatología" == "Juan Pérez Laser Center" when other signals
agree). A match means the candidate is dropped, not silently merged.
`find_fuzzy_candidates` additionally catches near-miss spellings (e.g. "SAS"
suffix, missing "de") that the exact matcher wouldn't — surface these to the
agent/user as a warning rather than silently dropping or silently keeping.

### 9. Write (append-only, Sheets + CSV mirror)

Follow `references/composio_tools.md` for the exact Composio call sequence.
Then, always — the CLI does this automatically (see "Running it end-to-end"
below), or call it directly:

```python
from sheets_io import write_csv_mirror
paths = write_csv_mirror(qualified_leads, owner_missing_leads,
                          output_dir=Path("skills/nodoto-lead-hunter/output"))
```

Never clear, overwrite, or replace a worksheet. Append only. If the user has
asked for CSV instead of Sheets for a given run (or the correct Composio
account/spreadsheet can't be verified — see step 0), **this CSV mirror is the
entire output for that run**: say so plainly, hand over the two file paths, and
skip the Sheets write rather than guessing at a connection.

## Running it end-to-end (CLI)

Everything from dedupe through CSV writing and the final report is one
deterministic command once research is done. The agent still has to do the
actual discovery/owner-research/website-audit work (that needs live browsing
and judgment) and produce a JSON file of candidates — `tests/candidates_sample.json`
shows the shape — but from there:

```bash
python3 skills/nodoto-lead-hunter/scripts/cli.py run candidates.json \
    --repo-root . \
    --niche "Dermatólogos de tratamientos láser" \
    --out-dir skills/nodoto-lead-hunter/output
    # optional: --sheet-rows sheet_export.json  (a Composio read of the live Sheet, as JSON)
```

This validates each candidate, dedupes against the repo's CSVs (+ the Sheet
export if provided) AND against other candidates in the same batch, runs the
qualification gate and evidence-quality check, writes
`qualified_leads_<run>.csv` and `candidates_owner_phone_missing_<run>.csv`,
and prints the fixed-format run report — with discard/duplicate reasons on
stderr for auditing. To rank niches before picking one:

```bash
python3 skills/nodoto-lead-hunter/scripts/cli.py rank-niches --repo-root .
```

### 10. Verify

Re-read the worksheet (if written) and run `sheets_io.verify_write(...)`. If
it fails, stop and report — do not retry blindly. For CSV-only runs, verify by
re-reading the written CSV row count against the in-memory qualified list.

### 11. Report

Render with `scripts/report.py`:

```python
from report import RunStats, render_report
print(render_report(RunStats(niche=..., candidates_found=..., ...)))
```

Output format (fixed):

```
NODOTO LEAD HUNTER — RUN COMPLETE

Nicho:
<niche>

Candidatos encontrados:
<n>

Investigados:
<n>

Descartados:
<n>

Qualified Leads:
<n>

VIP:
<n>

A:
<n>

B:
<n>

Owner identificado:
<n>/<n>

Owner Phone verificado:
<n>/<n>

Website auditado:
<n>/<n>

Instagram:
<n>/<n>

Duplicados:
<n>

Google Sheet:
<name or "N/A (CSV-only output)">

Worksheet:
<name>

Cuenta Composio:
<verified account, or "N/A">
```

## Batching target

Discover 20-40, research all, expect real attrition. Target 10-20 truly
qualified leads per run. If only 6 are genuinely good, deliver 6 — never pad
the batch with weak leads to hit a round number.

## Anti-fabrication (inherited, non-negotiable)

Never invent: owner name, phone, website, socials, score, observations,
pricing, or revenue. Anything unverifiable is `NOT_VERIFIED`, not a guess.
This mirrors `docs/outreach_playbook.md`'s existing anti-fabrication rule for
emails — this skill extends the same discipline to owners and phones.

## What this skill does NOT do

It does not send emails, does not touch `sent_tracking.csv` or
`known_bad_contacts.csv` write paths, does not modify follow-up sequencing,
and does not change the existing 3-account Gmail round-robin. It only
discovers, qualifies, and writes new leads. Log the run in
`docs/methodology_and_status.md` following the existing entry format, same as
every other run in this repo's history — but as its own dated entry, not
mixed into the cold-email run log.

## Files in this skill

- `scripts/schema.py` — canonical `Lead` dataclass + column schema.
- `scripts/dedupe.py` — normalization + exact and fuzzy duplicate detection against Sheet + repo CSVs.
- `scripts/scoring.py` — the owner-phone qualification gate + weighted score/tier.
- `scripts/validate.py` — evidence-quality checks (rejects generic phone sources, vague website-problem text).
- `scripts/niche_priority.py` — Niche Opportunity Score ranking from real repo/Sheet coverage data.
- `scripts/sheets_io.py` — Sheets write-plan/verify contract + CSV fallback writer.
- `scripts/report.py` — fixed-format run report.
- `scripts/cli.py` — single entrypoint running dedupe → gate → validate → score → write → report over a JSON candidates file.
- `references/composio_tools.md` — exact Composio call sequence + account-verification steps.
- `tests/test_pipeline.py` — 20 self-checks covering normalization, exact + fuzzy
  dedupe, the gate (including the "business phone relabeled as owner phone"
  trap and the "unset email falsely matches another unset email" trap this
  suite actually caught during development), evidence validation, niche
  ranking, and CSV output. Run after any change:
  `python3 skills/nodoto-lead-hunter/tests/test_pipeline.py`.
- `tests/candidates_sample.json` — example input shape for `cli.py run`.
