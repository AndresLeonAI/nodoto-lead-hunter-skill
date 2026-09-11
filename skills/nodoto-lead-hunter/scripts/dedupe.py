"""
NODOTO LEAD HUNTER — deduplication.

Compares a candidate Lead against every existing source of truth in the repo
(and, at runtime, against whatever is already in the target Google Sheet) so the
same business or the same owner never gets inserted twice, even when the naming
differs (playbook rule #23: "Dr. Juan Pérez Dermatología" == "Juan Pérez Laser Center").

This module is pure Python / stdlib only — no network calls — so it can run
identically whether the source rows come from local CSVs or from a Composio
Google Sheets read.
"""

from __future__ import annotations
import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from schema import Lead, NOT_VERIFIED_ALIASES

# Below this, two normalized names are considered "close enough to review" but
# NOT an automatic duplicate on their own (fuzzy match alone never silently
# drops a lead — it only flags for a second look, per anti-fabrication caution).
FUZZY_NAME_THRESHOLD = 0.87

_STOPWORDS = {
    "sas", "s.a.s", "s.a", "sa", "ltda", "cia", "compania", "compañia", "clinica",
    "clínica", "centro", "de", "del", "la", "el", "los", "las", "y", "e", "consultorio",
    "studio", "estudio", "group", "grupo", "co", "corp", "inc",
}


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    tokens = [t for t in value.split() if t and t not in _STOPWORDS]
    return " ".join(sorted(tokens))  # order-insensitive, e.g. "Laser Center Juan" == "Juan Laser Center"


def normalize_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    digits = re.sub(r"\D", "", value)
    # Normalize Colombian numbers: drop leading country code / trunk prefix so
    # "+57 601 555 1234", "601 555 1234" and "6015551234" all collapse to one key.
    if digits.startswith("57") and len(digits) > 10:
        digits = digits[2:]
    return digits.lstrip("0")


def normalize_domain(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    netloc = urlparse(value).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def normalize_handle(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    value = value.rstrip("/").split("/")[-1]
    return value.lstrip("@").lower()


@dataclass
class ExistingRecord:
    """Minimal normalized fingerprint of a row already present somewhere
    (Sheet, bogota_leads.csv, sent_tracking.csv, known_bad_contacts.csv)."""
    source: str
    business_key: str = ""
    owner_key: str = ""
    phone_key: str = ""
    domain_key: str = ""
    email: str = ""
    ig_key: str = ""
    raw_name: str = ""


def normalize_email(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    return value.lower()


def fingerprint_lead(lead: Lead, source: str = "candidate") -> ExistingRecord:
    return ExistingRecord(
        source=source,
        business_key=normalize_text(lead.business_name),
        owner_key=normalize_text(lead.owner_name),
        phone_key=normalize_phone(lead.owner_phone) or normalize_phone(lead.business_phone),
        domain_key=normalize_domain(lead.website),
        email=normalize_email(lead.business_email),
        ig_key=normalize_handle(lead.instagram) or normalize_handle(lead.owner_instagram),
        raw_name=lead.business_name,
    )


def load_bogota_leads_csv(path: Path) -> list[ExistingRecord]:
    """bogota_leads.csv header:
    #,Business Name,Industry/Niche,Bogota Location,Website,Website Problem,
    Business Email,Evidence/Source,Why High-Ticket Prospect,Lead Score
    """
    records = []
    if not path.exists():
        return records
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records.append(ExistingRecord(
                source="bogota_leads.csv",
                business_key=normalize_text(row.get("Business Name")),
                phone_key="",
                domain_key=normalize_domain(row.get("Website")),
                email=normalize_email(row.get("Business Email")),
                raw_name=row.get("Business Name", ""),
            ))
    return records


def load_known_bad_contacts_csv(path: Path) -> list[ExistingRecord]:
    records = []
    if not path.exists():
        return records
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records.append(ExistingRecord(
                source="known_bad_contacts.csv",
                domain_key=normalize_domain(row.get("domain")),
                email=normalize_email(row.get("email")),
            ))
    return records


def load_sheet_rows(rows: Iterable[dict]) -> list[ExistingRecord]:
    """rows: list of dicts keyed by the canonical schema.COLUMNS header (or whatever
    header the live sheet actually uses, already mapped by sheets_io)."""
    records = []
    for row in rows:
        lead = Lead.from_dict(row)
        records.append(fingerprint_lead(lead, source="google_sheet"))
    return records


def find_duplicate(lead: Lead, existing: list[ExistingRecord]) -> Optional[ExistingRecord]:
    """Returns the first existing record that plausibly refers to the same
    business/owner, or None. Matches on any single strong signal:
    exact phone match, exact domain match, exact email match, exact IG handle
    match, or a normalized business-name/owner-name match."""
    fp = fingerprint_lead(lead)
    for rec in existing:
        if fp.phone_key and rec.phone_key and fp.phone_key == rec.phone_key:
            return rec
        if fp.domain_key and rec.domain_key and fp.domain_key == rec.domain_key:
            return rec
        if fp.email and rec.email and fp.email == rec.email:
            return rec
        if fp.ig_key and rec.ig_key and fp.ig_key == rec.ig_key:
            return rec
        if fp.business_key and rec.business_key and fp.business_key == rec.business_key:
            return rec
        if fp.owner_key and rec.owner_key and fp.owner_key == rec.owner_key:
            return rec
    return None


def find_fuzzy_candidates(lead: Lead, existing: list[ExistingRecord],
                           threshold: float = FUZZY_NAME_THRESHOLD) -> list[tuple[ExistingRecord, float]]:
    """Near-miss name matches that `find_duplicate` would NOT catch (typos,
    partial renames, e.g. 'Centro Dermatologico Bogota' vs 'Centro
    Dermatologico de Bogota SAS'). Returned for human/agent review, not
    auto-dropped — a fuzzy match alone is not proof of duplication."""
    fp = fingerprint_lead(lead)
    hits = []
    for rec in existing:
        for a, b in ((fp.business_key, rec.business_key), (fp.owner_key, rec.owner_key)):
            if not a or not b:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= threshold:
                hits.append((rec, round(ratio, 3)))
                break
    hits.sort(key=lambda t: t[1], reverse=True)
    return hits


def load_all_repo_sources(repo_root: Path) -> list[ExistingRecord]:
    records = []
    records += load_bogota_leads_csv(repo_root / "data" / "bogota_leads.csv")
    records += load_known_bad_contacts_csv(repo_root / "data" / "known_bad_contacts.csv")
    # sent_tracking.csv only has recipient_email; folded in via a lightweight pass.
    sent_path = repo_root / "data" / "sent_tracking.csv"
    if sent_path.exists():
        with open(sent_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = normalize_email(row.get("recipient_email"))
                if email:
                    records.append(ExistingRecord(source="sent_tracking.csv", email=email))
    return records
