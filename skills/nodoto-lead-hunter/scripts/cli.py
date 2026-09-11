#!/usr/bin/env python3
"""
NODOTO LEAD HUNTER — pipeline CLI.

This is the one real, deterministic entrypoint for everything after research.
The agent (or a human) does the actual discovery/owner-research/website-audit
work — that part inherently needs judgment and live browsing and cannot be a
script — then hands the results to this CLI as a JSON file of candidates. From
there, everything is mechanical and gets run the same way every time:

    validate -> dedupe against repo + sheet -> qualification gate -> score ->
    split into Qualified / Owner-Phone-Missing / Discarded -> write CSVs ->
    print the fixed-format run report.

Usage:
    python3 cli.py run candidates.json \\
        --repo-root /path/to/nodoto-cold-outreach \\
        --niche "Dermatólogos de tratamientos láser" \\
        --sheet-rows sheet_export.json \\
        --out-dir skills/nodoto-lead-hunter/output

    python3 cli.py rank-niches --repo-root /path/to/nodoto-cold-outreach

candidates.json shape: a JSON list of objects, each with the same keys as
schema.Lead's fields (snake_case) OR the canonical column names in schema.COLUMNS
(Lead.from_dict accepts either). Unresearched fields should be omitted or set to
"NOT_VERIFIED" — never guessed.

sheet_export.json (optional): a JSON list of row-dicts already in the live
Google Sheet (from a Composio read), keyed by schema.COLUMNS headers, used for
dedupe and niche-coverage stats. Omit it for a CSV-only run.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import Lead, QUALIFICATION_STATUS_QUALIFIED, QUALIFICATION_STATUS_OWNER_PHONE_MISSING  # noqa: E402
from dedupe import load_all_repo_sources, load_sheet_rows, find_duplicate, find_fuzzy_candidates  # noqa: E402
from scoring import run_qualification_gate  # noqa: E402
from validate import validate_evidence_quality  # noqa: E402
from sheets_io import write_csv_mirror  # noqa: E402
from report import RunStats, render_report  # noqa: E402
from niche_priority import rank_niches  # noqa: E402


def cmd_run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    candidates_raw = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    if not isinstance(candidates_raw, list):
        print("candidates file must be a JSON list of lead objects", file=sys.stderr)
        return 2

    sheet_rows = []
    if args.sheet_rows:
        sheet_rows = json.loads(Path(args.sheet_rows).read_text(encoding="utf-8"))

    existing = load_all_repo_sources(repo_root) + load_sheet_rows(sheet_rows)

    qualified, owner_missing, discarded, duplicates = [], [], [], []
    investigated = 0

    for raw in candidates_raw:
        investigated += 1
        lead = Lead.from_dict(raw)

        dup = find_duplicate(lead, existing)
        if dup is not None:
            duplicates.append((lead, dup))
            continue
        fuzzy_hits = find_fuzzy_candidates(lead, existing)
        if fuzzy_hits:
            print(f"[REVIEW] '{lead.business_name}' is a fuzzy name match "
                  f"({fuzzy_hits[0][1]:.0%}) against '{fuzzy_hits[0][0].raw_name or fuzzy_hits[0][0].source}' "
                  f"— not auto-dropped, verify manually.", file=sys.stderr)

        gate = run_qualification_gate(lead)
        if gate.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING:
            owner_missing.append(lead)
            continue
        if not gate.passed:
            discarded.append((lead, gate.reasons))
            continue

        quality = validate_evidence_quality(lead)
        if not quality.ok:
            discarded.append((lead, quality.errors))
            continue

        # A qualified lead's own fingerprint joins `existing` immediately so two
        # near-identical candidates in the SAME batch can't both slip through.
        existing.append(_fingerprint(lead))
        qualified.append(lead)

    stats = RunStats(
        niche=args.niche or "(no especificado)",
        candidates_found=len(candidates_raw),
        investigated=investigated,
        discarded=len(discarded),
        qualified=len(qualified),
        vip=sum(1 for l in qualified if l.lead_tier == "VIP"),
        tier_a=sum(1 for l in qualified if l.lead_tier == "A"),
        tier_b=sum(1 for l in qualified if l.lead_tier == "B"),
        owner_identified=sum(1 for l in qualified + owner_missing if l.is_verified("owner_name")),
        owner_identified_of=len(qualified) + len(owner_missing),
        owner_phone_verified=len(qualified),
        owner_phone_verified_of=len(qualified) + len(owner_missing),
        website_audited=sum(1 for l in qualified if l.is_verified("website_problem") or l.website_status != "NOT_VERIFIED"),
        website_audited_of=len(qualified),
        instagram_found=sum(1 for l in qualified if l.is_verified("instagram") or l.is_verified("owner_instagram")),
        instagram_found_of=len(qualified),
        duplicates=len(duplicates),
    )

    out_dir = Path(args.out_dir)
    paths = write_csv_mirror(qualified, owner_missing, out_dir)
    stats.csv_paths = paths

    print(render_report(stats))

    if discarded:
        print("\n--- DISCARDED (reasons) ---", file=sys.stderr)
        for lead, reasons in discarded:
            print(f"- {lead.business_name}: {'; '.join(reasons)}", file=sys.stderr)
    if duplicates:
        print("\n--- DUPLICATES SKIPPED ---", file=sys.stderr)
        for lead, rec in duplicates:
            print(f"- {lead.business_name} matches existing record from {rec.source}", file=sys.stderr)

    return 0


def _fingerprint(lead: Lead):
    from dedupe import fingerprint_lead
    return fingerprint_lead(lead, source="this_batch")


def cmd_rank_niches(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    sheet_rows = []
    if args.sheet_rows:
        sheet_rows = json.loads(Path(args.sheet_rows).read_text(encoding="utf-8"))
    ranked = rank_niches(repo_root, sheet_rows)
    print(f"{'Niche Opportunity Score':<26}{'Niche key':<40}{'Existing leads':<16}{'Website gap %':<15}")
    for key, score, stats in ranked[:20]:
        print(f"{score:<26}{key:<40}{stats.existing_leads:<16}{stats.website_gap_rate * 100:<15.0f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NODOTO LEAD HUNTER pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run dedupe+gate+score+write over researched candidates")
    p_run.add_argument("candidates", help="Path to a JSON list of researched candidate leads")
    p_run.add_argument("--repo-root", default=".", help="Path to nodoto-cold-outreach repo root")
    p_run.add_argument("--niche", default="", help="Niche worked in this run (for the report)")
    p_run.add_argument("--sheet-rows", default=None, help="Optional JSON export of the live Sheet's rows")
    p_run.add_argument("--out-dir", default="skills/nodoto-lead-hunter/output", help="Where to write CSVs")
    p_run.set_defaults(func=cmd_run)

    p_rank = sub.add_parser("rank-niches", help="Print the Niche Opportunity Score ranking")
    p_rank.add_argument("--repo-root", default=".", help="Path to nodoto-cold-outreach repo root")
    p_rank.add_argument("--sheet-rows", default=None, help="Optional JSON export of the live Sheet's rows")
    p_rank.set_defaults(func=cmd_rank_niches)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
