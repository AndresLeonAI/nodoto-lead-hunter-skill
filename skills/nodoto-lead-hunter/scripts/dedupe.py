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
    return " ".join(sorted(tokens))


def normalize_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if value.upper() in NOT_VERIFIED_ALIASES:
        return ""
    digits = re.sub(r"\D", "", value)
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


def fingerprint_all_decision_makers(lead: Lead, source: str = "candidate") -> list[ExistingRecord]:
    records = []
    for person in lead.decision_makers:
        phone_key = normalize_phone(person.phone)
        owner_key = normalize_text(person.name)
        if not phone_key and not owner_key:
            continue
        records.append(ExistingRecord(
            source=f"{source}:decision_maker",
            business_key=normalize_text(lead.business_name),
            owner_key=owner_key,
            phone_key=phone_key,
            raw_name=f"{person.name} ({lead.business_name})",
        ))
    return records


def load_bogota_leads_csv(path: Path) -> list[ExistingRecord]:
    records = []
    if not path.exists():
        return records
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lead = Lead.from_dict(row)
            records.append(fingerprint_lead(lead, source="bogota_leads.csv"))
    return records


def load_bogota_leads_decision_makers(path: Path) -> list[ExistingRecord]:
    records = []
    if not path.exists():
        return records
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lead = Lead.from_dict(row)
            records += fingerprint_all_decision_makers(lead, source="bogota_leads.csv")
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
    records = []
    for row in rows:
        lead = Lead.from_dict(row)
        records.append(fingerprint_lead(lead, source="google_sheet"))
    return records


def find_duplicate(lead: Lead, existing: list[ExistingRecord]) -> Optional[ExistingRecord]:
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


def find_decision_maker_reuse(lead: Lead, existing_dm_records: list[ExistingRecord]) -> list[ExistingRecord]:
    hits = []
    for person in lead.decision_makers:
        phone_key = normalize_phone(person.phone)
        owner_key = normalize_text(person.name)
        for rec in existing_dm_records:
            same_phone = phone_key and rec.phone_key and phone_key == rec.phone_key
            same_name = owner_key and rec.owner_key and owner_key == rec.owner_key
            if (same_phone or same_name) and normalize_text(lead.business_name) != rec.business_key:
                hits.append(rec)
    return hits


def load_all_repo_sources(repo_root: Path) -> list[ExistingRecord]:
    records = []
    records += load_bogota_leads_csv(repo_root / "data" / "bogota_leads.csv")
    records += load_known_bad_contacts_csv(repo_root / "data" / "known_bad_contacts.csv")
    sent_path = repo_root / "data" / "sent_tracking.csv"
    if sent_path.exists():
        with open(sent_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = normalize_email(row.get("recipient_email"))
                if email:
                    records.append(ExistingRecord(source="sent_tracking.csv", email=email))
    return records
