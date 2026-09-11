"""
NODOTO LEAD HUNTER — output layer: Google Sheets (via Composio) with an
automatic, always-available CSV fallback.

Design intent
-------------
The Composio Google Sheets *tools themselves* are not Python APIs — they are
MCP tool calls the Claude agent running this skill makes directly (e.g. a
GOOGLESHEETS_* action from Composio's toolkit). This module therefore does NOT
call Composio itself; it defines the exact contract the agent must satisfy
(what to read, what to check, what to write, in what order) and does the parts
that ARE pure logic: building the rows to write, verifying row counts after a
write, and always keeping a local CSV mirror so the run never depends on the
Sheets connection succeeding.

Concretely, the agent calling this skill should:
    1. Call the Composio connection-listing tool and find the Google Sheets /
       Drive connection whose authenticated account email matches NODOTO's
       Google account (see references/composio_tools.md). If it can't be
       determined with certainty -> STOP, do not write, report it (playbook #12).
    2. Use `plan_write()` below to get the exact rows to append + verification
       row counts.
    3. Call the Composio "read sheet" action to fetch current headers + row
       count from the identified spreadsheet/worksheet.
    4. Reconcile headers with `map_to_existing_header()`.
    5. Call the Composio "append rows" action (NEVER a full-sheet overwrite/clear).
    6. Call the Composio "read sheet" action again and pass the result to
       `verify_write()`.
    7. Regardless of steps 1-6 succeeding, call `write_csv_mirror()` so a local,
       importable CSV always exists (this is also the default/only output when
       no Composio Google Sheets connection can be verified, or when the caller
       has explicitly asked for CSV-only output for manual import).
"""

from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path
from typing import Optional

from schema import Lead, COLUMNS, WORKSHEET_QUALIFIED, WORKSHEET_CANDIDATES_OWNER_MISSING


def map_to_existing_header(existing_header: list[str]) -> list[str]:
    """Playbook rule #15: adapt to the sheet that already exists rather than
    forcing our own layout. Returns the header to actually write against:
    the existing one, extended (never reordered/removed) with any of our
    canonical columns it's missing."""
    if not existing_header:
        return list(COLUMNS)
    missing = [c for c in COLUMNS if c not in existing_header]
    return list(existing_header) + missing


def plan_write(leads: list[Lead], header: list[str]) -> list[list]:
    return [lead.to_row(columns=header) for lead in leads]


def verify_write(expected_new_rows: int, rows_before: int, rows_after: int,
                  expected_business_names: list[str], actual_last_rows: list[list],
                  header: list[str]) -> tuple[bool, str]:
    """Playbook rule #27: after writing, re-read and confirm row count + spot-check
    identity fields. Returns (ok, message). On failure the caller MUST stop and
    report rather than retry blindly."""
    if rows_after - rows_before != expected_new_rows:
        return False, (
            f"Row count mismatch: expected +{expected_new_rows}, got "
            f"+{rows_after - rows_before} ({rows_before} -> {rows_after})."
        )
    try:
        name_col = header.index("Business Name")
    except ValueError:
        return False, "Business Name column not found in header during verification."
    written_names = [row[name_col] for row in actual_last_rows if len(row) > name_col]
    missing = [n for n in expected_business_names if n not in written_names]
    if missing:
        return False, f"Business names missing from written rows: {missing}"
    return True, f"Verified: {expected_new_rows} rows appended and confirmed by re-read."


def write_csv_mirror(leads_qualified: list[Lead], leads_owner_missing: list[Lead],
                      output_dir: Path, run_id: Optional[str] = None) -> dict:
    """Always-on local output so the user can import manually regardless of
    Composio/Sheets connectivity (this is also what to use when the user asks
    for CSV instead of Sheets). Writes two files and returns their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")

    qualified_path = output_dir / f"qualified_leads_{run_id}.csv"
    owner_missing_path = output_dir / f"candidates_owner_phone_missing_{run_id}.csv"

    _write_csv(qualified_path, leads_qualified)
    _write_csv(owner_missing_path, leads_owner_missing)

    return {"qualified_csv": str(qualified_path), "owner_missing_csv": str(owner_missing_path)}


def _write_csv(path: Path, leads: list[Lead]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for lead in leads:
            writer.writerow(lead.to_row())
