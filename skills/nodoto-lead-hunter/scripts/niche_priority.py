"""
NODOTO LEAD HUNTER — dynamic niche prioritization (playbook rules #9-#10).

Computes a Niche Opportunity Score per niche from what's ALREADY in the repo
(and, at runtime, the live Sheet), so niche selection is evidence-based instead
of arbitrary. A niche scores high when it combines: high ticket value, low
existing coverage, a high rate of website problems among what's already been
found, and few leads with an identified owner/owner phone (meaning there's
real remaining opportunity + the category hasn't already been "solved").

This module only needs a business-value lookup for the 50 niches (a static
value judgment, documented and editable — not a live signal) plus whatever
counts it can derive from bogota_leads.csv / the live Sheet.
"""

from __future__ import annotations
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Static business-value / urgency priors (0-10), one entry per niche in
# docs/outreach_playbook.md section "PERFIL DEL LEAD IDEAL" / the 50-niche list.
# Edit this table as NODOTO's own experience updates (e.g. after a niche closes
# deals faster/slower than expected). Values are directional, not measured.
NICHE_VALUE_PRIORS: dict[str, float] = {
    "cirujanos plasticos": 9.5, "dentistas cosmeticos": 8.0, "ortodoncistas": 7.5,
    "fertilidad": 9.0, "quiropracticos deportivos": 6.5, "perdida de peso medica": 7.5,
    "oftalmologia lasik": 8.5, "psicologos clinicos ejecutivos": 7.0,
    "fisioterapia deportiva": 6.0, "veterinarios premium": 6.5, "dermatologia laser": 8.5,
    "contadores tech": 6.5, "asesores financieros": 8.0, "notarios": 6.0,
    "abogados inmigracion": 7.5, "divorcio alto conflicto": 9.0, "patrimonio sucesiones": 8.5,
    "compliance": 7.0, "seguros premium": 7.5, "family offices": 9.5,
    "economistas forenses": 7.0, "arquitectos lujo": 8.5, "ingenieria sostenible": 7.0,
    "abogados corporativos": 8.0, "consultores ecommerce": 6.0, "executive coaching": 7.0,
    "terapia pareja infidelidad": 8.5, "nutricion clinica": 6.0, "implantes dentales": 8.0,
    "podologia deportiva": 5.5, "home staging": 6.0, "propiedades lujo": 9.0,
    "desarrolladores boutique": 9.0, "casas personalizadas": 8.0, "inspeccion certificada": 6.0,
    "inmobiliario comercial": 8.5, "property management premium": 7.5,
    "colegios academias elite": 8.5, "admisiones universitarias": 6.5, "idiomas premium": 5.5,
    "golf tenis alto rendimiento": 6.0, "lesiones personales": 8.5, "recuperacion deudas": 6.5,
    "ciberseguridad b2b": 7.5, "medicina del sueno": 7.0, "reproduccion asistida": 9.0,
    "propiedad intelectual": 7.5, "divorcio colaborativo": 7.5, "executive trainers": 6.5,
    "fotografia bodas lujo": 6.5, "interiorismo high end": 7.5,
}


@dataclass
class NicheStats:
    niche: str
    existing_leads: int = 0
    website_problem_count: int = 0
    owner_identified_count: int = 0
    owner_phone_count: int = 0

    @property
    def coverage_penalty(self) -> float:
        """More existing leads in this niche -> lower remaining-opportunity score."""
        return min(self.existing_leads / 20.0, 1.0)  # saturates at 20+ existing leads

    @property
    def website_gap_rate(self) -> float:
        return (self.website_problem_count / self.existing_leads) if self.existing_leads else 0.5

    @property
    def owner_access_rate(self) -> float:
        return (self.owner_phone_count / self.existing_leads) if self.existing_leads else 0.0


def _slugify_niche(value: str) -> str:
    import unicodedata, re
    v = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    v = re.sub(r"[^a-z0-9\s]", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def load_niche_stats_from_repo(repo_root: Path) -> dict[str, NicheStats]:
    """Derives NicheStats from bogota_leads.csv (has Industry/Niche + Website
    Problem columns already, no Owner columns yet -> owner_* stay at 0 until
    the new Sheet/CSV output accumulates real owner data)."""
    stats: dict[str, NicheStats] = defaultdict(lambda: NicheStats(niche=""))
    path = repo_root / "data" / "bogota_leads.csv"
    if not path.exists():
        return stats
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            niche_raw = row.get("Industry/Niche", "") or "unknown"
            key = _slugify_niche(niche_raw)
            s = stats[key]
            s.niche = niche_raw
            s.existing_leads += 1
            problem = (row.get("Website Problem") or "").strip()
            if problem and problem.upper() not in {"NONE", "N/A", "NOT_VERIFIED"}:
                s.website_problem_count += 1
    return dict(stats)


def merge_sheet_owner_stats(stats: dict[str, NicheStats], sheet_rows: list[dict]) -> None:
    """Fold in owner-identification / owner-phone counts from whatever is
    already in the live Google Sheet (or its CSV mirror), keyed by the sheet's
    own 'Niche' column."""
    for row in sheet_rows:
        key = _slugify_niche(row.get("Niche", ""))
        s = stats.setdefault(key, NicheStats(niche=row.get("Niche", "")))
        owner_name = (row.get("Owner Name") or "").strip().upper()
        owner_phone = (row.get("Owner Phone") or "").strip().upper()
        if owner_name and owner_name not in {"NOT_VERIFIED", "N/A", ""}:
            s.owner_identified_count += 1
        if owner_phone and owner_phone not in {"NOT_VERIFIED", "N/A", ""}:
            s.owner_phone_count += 1


def niche_opportunity_score(niche_key: str, stats: dict[str, NicheStats]) -> float:
    """0-10. Higher = better niche to work next."""
    value_prior = NICHE_VALUE_PRIORS.get(niche_key, 6.0)  # neutral default for unmapped niches
    s = stats.get(niche_key, NicheStats(niche=niche_key))
    remaining_opportunity = 1.0 - s.coverage_penalty
    website_gap = s.website_gap_rate
    owner_access_gap = 1.0 - s.owner_access_rate  # more room = more owners still to find

    score = (
        value_prior * 0.40
        + remaining_opportunity * 10 * 0.25
        + website_gap * 10 * 0.20
        + owner_access_gap * 10 * 0.15
    )
    return round(min(score, 10.0), 2)


def rank_niches(repo_root: Path, sheet_rows: list[dict] | None = None) -> list[tuple[str, float, NicheStats]]:
    stats = load_niche_stats_from_repo(repo_root)
    if sheet_rows:
        merge_sheet_owner_stats(stats, sheet_rows)
    all_keys = set(NICHE_VALUE_PRIORS.keys()) | set(stats.keys())
    ranked = [(k, niche_opportunity_score(k, stats), stats.get(k, NicheStats(niche=k))) for k in all_keys]
    ranked.sort(key=lambda t: t[1], reverse=True)
    return ranked
