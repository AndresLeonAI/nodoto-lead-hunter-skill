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
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import Lead  # noqa: E402

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


# v4.1: real niche names in memory ("Dermatólogos de tratamientos láser",
# "Bienes raíces comerciales") rarely equal the prior keys, which made every
# niche look untouched (Existing=0) and sent daily runs back into saturated
# niches. canonical_niche_key() maps any free-text niche onto a prior key.
NICHE_ALIASES: dict[str, str] = {
    "gestores de patrimonios familiares": "family offices",
    "abogados de familia divorcios": "divorcio alto conflicto",
    "bienes raices comerciales": "inmobiliario comercial",
    "liquidaciones": "patrimonio sucesiones",
    "reproduccion": "reproduccion asistida",
    "lasik": "oftalmologia lasik",
}
_STOP = {"de", "la", "el", "los", "las", "y", "en", "del", "para", "con", "alto", "altos"}


def _prefixes(slug: str) -> set[str]:
    return {t[:5] for t in slug.split() if len(t) > 2 and t not in _STOP}


def canonical_niche_key(value: str) -> str:
    slug = _slugify_niche(value)
    if slug in NICHE_VALUE_PRIORS:
        return slug
    for alias, key in NICHE_ALIASES.items():
        if alias in slug:
            return key
    mine = _prefixes(slug)
    best, best_overlap = None, 0
    for key in NICHE_VALUE_PRIORS:
        theirs = _prefixes(key)
        if theirs and (theirs <= mine or (mine and mine <= theirs)):
            overlap = len(theirs & mine)
            if overlap > best_overlap:
                best, best_overlap = key, overlap
    return best or slug


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_niche_stats_from_repo(repo_root: Path) -> dict[str, NicheStats]:
    """Derives NicheStats from ALL memory: bogota_leads.csv (qualified),
    candidates_owner_phone_missing.csv (researched but rejected) and
    niche_coverage.json (run totals, includes candidates that never made it
    into the CSVs). v4.1: previously only bogota_leads.csv was read and niche
    names were never canonicalised, so coverage was invisible."""
    stats: dict[str, NicheStats] = defaultdict(lambda: NicheStats(niche=""))
    data = repo_root / "data"
    csv_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [qualified, missing]
    for fname, is_qualified in (("bogota_leads.csv", True), ("candidates_owner_phone_missing.csv", False)):
        for row in _read_csv_rows(data / fname):
            lead = Lead.from_dict(row)
            niche_raw = (lead.niche or "unknown").strip()
            key = canonical_niche_key(niche_raw)
            s = stats[key]
            s.niche = s.niche or niche_raw
            s.existing_leads += 1
            csv_counts[key][0 if is_qualified else 1] += 1
            if lead.is_verified("website_problem"):
                s.website_problem_count += 1
            if lead.is_verified("owner_name"):
                s.owner_identified_count += 1
            if is_qualified and lead.is_verified("owner_phone"):
                s.owner_phone_count += 1
    cov_path = data / "niche_coverage.json"
    if cov_path.exists():
        import json
        try:
            coverage = json.loads(cov_path.read_text(encoding="utf-8"))
        except ValueError:
            coverage = {}
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for niche_raw, c in coverage.items():
            key = canonical_niche_key(niche_raw)
            totals[key][0] += int(c.get("total_qualified", 0) or 0)
            totals[key][1] += int(c.get("total_owner_phone_missing", 0) or 0)
            stats[key].niche = stats[key].niche or niche_raw
        for key, (q, m) in totals.items():
            s = stats[key]
            cq, cm = csv_counts[key]
            extra = max(0, q - cq) + max(0, m - cm)
            if extra:
                # Unsynced candidates: count them, assume same web-gap rate.
                rate = s.website_gap_rate
                s.existing_leads += extra
                s.website_problem_count += round(extra * rate)
                s.owner_phone_count += max(0, q - cq)
    return dict(stats)


def merge_sheet_owner_stats(stats: dict[str, NicheStats], sheet_rows: list[dict]) -> None:
    """Fold in owner-identification / owner-phone counts from whatever is
    already in the live Google Sheet (or its CSV mirror), keyed by the sheet's
    own 'Niche' column."""
    for row in sheet_rows:
        key = canonical_niche_key(row.get("Niche", ""))
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


def estimate_raw_candidates_needed(
    niche_key: str,
    stats: dict[str, NicheStats],
    target_qualified: int = 10,
    default_qualify_rate: float = 0.12,
) -> int:
    """v3.1 efficiency addition (audit 2026-09-11, "edge of perfection" pass).

    30-50 extremely qualified leads/day only happens if the RAW discovery
    funnel is sized correctly per niche — discovering a fixed 20-40 candidates
    regardless of niche wastes research effort on niches where owner phones are
    historically hard to find, and under-discovers niches where they're easy.

    Uses `owner_access_rate` (already computed from real bogota_leads.csv
    history — no new tracking file needed) as the best available proxy for the
    eventual qualify rate, since the qualification gate's hard bottleneck is
    exactly DIRECT/NAMED_ATTRIBUTION owner-phone confidence. A niche with too
    little history (<5 existing leads) falls back to `default_qualify_rate`
    (conservative: assume most candidates will fail on owner-phone alone —
    better to over-discover an unproven niche than run short of the target).

    Always returns at least 2x the target (some attrition is universal even in
    the best niches) and caps at 12x (beyond that, split across multiple
    niches in parallel per SKILL.md's "Escalamiento en paralelo" section
    instead of over-mining one niche).
    """
    s = stats.get(niche_key)
    if s and s.existing_leads >= 5:
        qualify_rate = max(s.owner_access_rate, 0.02)
    else:
        qualify_rate = default_qualify_rate
    needed = math.ceil(target_qualified / qualify_rate)
    return max(target_qualified * 2, min(needed, target_qualified * 12))


def rank_niches(repo_root: Path, sheet_rows: list[dict] | None = None) -> list[tuple[str, float, NicheStats]]:
    stats = load_niche_stats_from_repo(repo_root)
    if sheet_rows:
        merge_sheet_owner_stats(stats, sheet_rows)
    all_keys = set(NICHE_VALUE_PRIORS.keys()) | set(stats.keys())
    ranked = [(k, niche_opportunity_score(k, stats), stats.get(k, NicheStats(niche=k))) for k in all_keys]
    ranked.sort(key=lambda t: t[1], reverse=True)
    return ranked
