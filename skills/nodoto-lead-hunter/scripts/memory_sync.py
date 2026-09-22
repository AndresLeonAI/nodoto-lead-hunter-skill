#!/usr/bin/env python3
"""
NODOTO LEAD HUNTER — v4.1 memory sync (append-only, programmatic).

Fixes the recurring failure logged in docs/run_log.md (2026-09-12, 09-14, 09-22):
large CSVs (owner-phone-missing candidates) were being re-typed by hand inside
a single GITHUB_COMMIT_MULTIPLE_FILES call and got skipped, so dedupe never saw
them. This script merges a run's CSV outputs into a local copy of the memory
repo ON DISK; the push is then done by `push_memory_via_composio()` reading the
files from disk inside the Composio workbench — nothing is ever transcribed.

Usage (local copy of memory repo at ./mem, cli.py outputs in ./output):
    python3 memory_sync.py merge --memory-root mem --out-dir output --run-date 2026-09-23

Append-only guarantees: existing rows are never modified or removed; a new row
is skipped if (normalized business name, niche) already exists in that file.
"""
from __future__ import annotations
import argparse
import csv
import glob
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import COLUMNS  # noqa: E402
from dedupe import normalize_text as normalize_business_name  # noqa: E402

MEMORY_FILES = {
    "qualified": "data/bogota_leads.csv",
    "owner_missing": "data/candidates_owner_phone_missing.csv",
}


def _key(row: dict) -> tuple[str, str]:
    return (normalize_business_name(row.get("Business Name", "")),
            (row.get("Niche") or "").strip().lower())


def _read(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def append_rows(target: Path, new_rows: list[dict]) -> int:
    header, existing = _read(target)
    if not header:
        header = list(COLUMNS)
    for col in COLUMNS:  # schema grew -> add column at the end, never reorder
        if col not in header:
            header.append(col)
    seen = {_key(r) for r in existing}
    to_add = []
    for row in new_rows:
        k = _key(row)
        if k[0] and k not in seen:
            seen.add(k)
            to_add.append(row)
    if not to_add and target.exists() and set(header) == set(_read(target)[0]):
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(existing)
        w.writerows(to_add)
    return len(to_add)


def update_coverage(memory_root: Path, qualified: list[dict], missing: list[dict], run_date: str) -> None:
    path = memory_root / "data" / "niche_coverage.json"
    cov = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    niches = {(r.get("Niche") or "").strip() for r in qualified + missing} - {""}
    for n in niches:
        c = cov.setdefault(n, {"times_run": 0, "total_qualified": 0,
                               "total_owner_phone_missing": 0, "last_run_date": ""})
        c["times_run"] += 1
        c["total_qualified"] += sum(1 for r in qualified if (r.get("Niche") or "").strip() == n)
        c["total_owner_phone_missing"] += sum(1 for r in missing if (r.get("Niche") or "").strip() == n)
        c["last_run_date"] = run_date
    path.write_text(json.dumps(cov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge(memory_root: Path, out_dir: Path, run_date: str) -> dict:
    q_rows, m_rows = [], []
    for p in sorted(glob.glob(str(out_dir / "qualified_leads_*.csv"))):
        q_rows += _read(Path(p))[1]
    for p in sorted(glob.glob(str(out_dir / "candidates_owner_phone_missing_*.csv"))):
        m_rows += _read(Path(p))[1]
    for r in q_rows + m_rows:
        r.setdefault("Research Date", run_date)
        if not (r.get("Research Date") or "").strip():
            r["Research Date"] = run_date
    added_q = append_rows(memory_root / MEMORY_FILES["qualified"], q_rows)
    added_m = append_rows(memory_root / MEMORY_FILES["owner_missing"], m_rows)
    update_coverage(memory_root, q_rows, m_rows, run_date)
    return {"qualified_added": added_q, "owner_missing_added": added_m,
            "qualified_in_run": len(q_rows), "owner_missing_in_run": len(m_rows)}


def append_run_log(memory_root: Path, entry_md: str) -> None:
    path = memory_root / "docs" / "run_log.md"
    prev = path.read_text(encoding="utf-8") if path.exists() else "# Run log\n"
    path.write_text(prev.rstrip("\n") + "\n\n" + entry_md.strip() + "\n", encoding="utf-8")


# ---- Composio workbench helpers (only usable inside COMPOSIO_REMOTE_WORKBENCH,
# where run_composio_tool is predefined). Kept here so the daily task runs the
# exact same code every time instead of improvising.
MEMORY_REPO = ("AndresLeonAI", "nodoto-lead-hunter-memory")
SYNCED_PATHS = ["README.md", "data/bogota_leads.csv", "data/candidates_owner_phone_missing.csv",
                "data/known_bad_contacts.csv", "data/sent_tracking.csv", "data/niche_coverage.json",
                "docs/outreach_playbook.md", "docs/run_log.md", "docs/methodology_v3.md",
                "docs/owner_phone_sources_v3.md", "docs/owner_phone_vault_v4.md",
                "data/outreach_log.csv"]


def pull_memory_via_composio(run_composio_tool, memory_root: Path) -> list[str]:
    import requests
    got = []
    for p in SYNCED_PATHS:
        r, err = run_composio_tool("GITHUB_GET_RAW_REPOSITORY_CONTENT",
                                   {"owner": MEMORY_REPO[0], "repo": MEMORY_REPO[1], "path": p})
        if err:
            continue
        url = r["data"]["content"]["s3url"]
        dest = memory_root / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(requests.get(url, timeout=60).content)
        got.append(p)
    return got


def push_memory_via_composio(run_composio_tool, memory_root: Path, paths: list[str], message: str):
    """Commits files read from disk — never transcribed by the model."""
    upserts = [{"path": p, "content": (memory_root / p).read_text(encoding="utf-8")} for p in paths]
    return run_composio_tool("GITHUB_COMMIT_MULTIPLE_FILES", {
        "owner": MEMORY_REPO[0], "repo": MEMORY_REPO[1], "branch": "main",
        "message": message, "upserts": upserts,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge a run's outputs into the memory repo (append-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--memory-root", required=True)
    m.add_argument("--out-dir", required=True)
    m.add_argument("--run-date", default=date.today().isoformat())
    a = ap.parse_args()
    print(json.dumps(merge(Path(a.memory_root), Path(a.out_dir), a.run_date), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
