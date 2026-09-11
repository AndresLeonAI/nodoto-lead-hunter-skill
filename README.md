# NODOTO Lead Hunter Skill

High-ticket sales opportunity engine for **NODOTO AGENCY**.

Discovers businesses in targeted niches with weak digital presence, identifies the owner/decision-maker along with their publicly-verifiable professional phone number, audits digital assets, scores opportunities, deduplicates against existing records, and outputs to Google Sheets (via Composio) with automatic local CSV mirrors.

---

## 🎯 The Non-Negotiable Rule

> **A lead is NEVER "Qualified" without a publicly verifiable, professional phone number belonging to the OWNER or direct decision-maker — not the business's generic line.**

If the owner's verified direct phone number is missing:
- `Owner Phone = NOT_VERIFIED`
- `Qualification Status = OWNER_PHONE_MISSING`
- The lead is routed to the `Candidates - Owner Phone Missing` queue, never to `Qualified Leads`.

---

## 📁 Repository Structure

```
nodoto-lead-hunter-skill/
├── .gitignore
├── README.md
└── skills/
    └── nodoto-lead-hunter/
        ├── SKILL.md                 # Antigravity / Claude skill specification
        ├── references/
        │   └── composio_tools.md    # Composio & Google Sheets integration guide
        ├── scripts/
        │   ├── cli.py               # Deterministic pipeline CLI entrypoint
        │   ├── dedupe.py            # Deduplication engine (repo + sheet cross-match)
        │   ├── niche_priority.py    # Opportunity scoring and ranking across niches
        │   ├── report.py            # Structured run report generator
        │   ├── schema.py            # Lead schema definition and canonical columns
        │   ├── scoring.py           # Qualification gates and tier scoring
        │   ├── sheets_io.py         # Google Sheets mapping and local CSV fallback
        │   └── validate.py          # Evidence and quality validation rules
        └── tests/
            ├── candidates_sample.json
            └── test_pipeline.py     # Deterministic pipeline self-tests
```

---

## 🚀 Quickstart & Usage

### 1. Run Pipeline Self-Tests
Verify that normalization, deduplication, scoring gates, and CSV generation are working properly:

```bash
python skills/nodoto-lead-hunter/tests/test_pipeline.py
```

### 2. Rank Niches
To determine which niche presents the highest opportunity based on prior coverage:

```bash
python skills/nodoto-lead-hunter/scripts/cli.py rank-niches --repo-root /path/to/nodoto-cold-outreach
```

### 3. Run Pipeline on Discovered Candidates

Once candidates have been researched and compiled into a JSON file matching the schema:

```bash
python skills/nodoto-lead-hunter/scripts/cli.py run path/to/candidates.json \
    --repo-root /path/to/nodoto-cold-outreach \
    --niche "Dermatólogos de tratamientos láser" \
    --out-dir skills/nodoto-lead-hunter/output
```

---

## 📋 Integration with Composio & Google Sheets

For direct synchronization to the active Google Sheet:
- Refer to `skills/nodoto-lead-hunter/references/composio_tools.md`.
- Ensure write operations are strictly **append-only** and verified row-by-row.
- If Google Sheets credentials or connections fail, local CSV mirrors are generated under `output/`.

---

## ⚖️ License & Confidentiality

Internal operational skill developed for NODOTO AGENCY. All rights reserved.
