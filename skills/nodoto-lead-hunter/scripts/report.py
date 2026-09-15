"""
NODOTO LEAD HUNTER — final run report + clean export table (v3.2).

v3.2 change (user directive, 2026-09-15): the clean export / Excel deliverable
must always be split ONE FILE PER NICHE — a single spreadsheet may never mix
leads from two different niches, even when a run discovered/researched
several niches in parallel for efficiency. `split_leads_by_niche()` and
`build_clean_export_tables_by_niche()` below are what enforce that at the
data layer; the caller (cli.py, or whoever builds the final .xlsx) must loop
over the returned dict and produce one file per key, never one combined file.

v3.2 also adds `Lead.cold_call_hook`: a literal, conversational line an SDR
can read (almost) verbatim on a cold call, addressed to the business owner in
second person, built from the SAME verified `website_problem`/`website_evidence`
already required for the qualification gate — never new invented specifics.
It exists to raise the booked-meeting rate, not to replace `angle` (which
stays a short strategist's note TO the seller about pitch positioning).
`_fallback_cold_call_hook()` derives a serviceable one from the technical
fields for leads researched before this field existed.
"""

from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field

from schema import Lead, NOT_VERIFIED_ALIASES


@dataclass
class RunStats:
    niche: str
    candidates_found: int = 0
    investigated: int = 0
    discarded: int = 0
    qualified: int = 0
    vip: int = 0
    tier_a: int = 0
    tier_b: int = 0
    owner_identified: int = 0
    owner_identified_of: int = 0
    owner_phone_verified: int = 0
    owner_phone_verified_of: int = 0
    website_audited: int = 0
    website_audited_of: int = 0
    instagram_found: int = 0
    instagram_found_of: int = 0
    duplicates: int = 0
    multi_decision_maker_leads: int = 0
    avg_contact_quality: float = 0.0
    avg_lead_quality: float = 0.0
    decision_maker_reuse_flags: int = 0
    google_sheet_name: str = "N/A (CSV-only output)"
    worksheet: str = "N/A"
    composio_account: str = "N/A"
    csv_paths: dict = field(default_factory=dict)

    @classmethod
    def from_qualified(cls, qualified_leads: list[Lead], **kwargs) -> "RunStats":
        """Convenience constructor that derives the v3 quality-breakdown
        fields from the actual qualified leads instead of leaving them at 0.

        Named `qualified_leads` (not `qualified`) deliberately: RunStats
        already has an int field called `qualified` (the count) passed via
        **kwargs by callers — a same-named positional arg here collides with
        it (`got multiple values for argument 'qualified'`), which is exactly
        what happened the first time cli.py actually called this in a real
        run instead of only in a unit test that never exercised this path."""
        stats = cls(**kwargs)
        if qualified_leads:
            stats.multi_decision_maker_leads = sum(1 for l in qualified_leads if l.decision_maker_count > 1)
            lq = [l.lead_quality_score for l in qualified_leads if l.lead_quality_score is not None]
            cq = [l.contact_quality_score for l in qualified_leads if l.contact_quality_score is not None]
            stats.avg_lead_quality = round(sum(lq) / len(lq), 2) if lq else 0.0
            stats.avg_contact_quality = round(sum(cq) / len(cq), 2) if cq else 0.0
        return stats


def render_report(stats: RunStats) -> str:
    lines = [
        "NODOTO LEAD HUNTER — RUN COMPLETE",
        "",
        "Nicho:",
        stats.niche,
        "",
        "Candidatos encontrados:",
        str(stats.candidates_found),
        "",
        "Investigados:",
        str(stats.investigated),
        "",
        "Descartados:",
        str(stats.discarded),
        "",
        "Qualified Leads:",
        str(stats.qualified),
        "",
        "VIP:",
        str(stats.vip),
        "",
        "A:",
        str(stats.tier_a),
        "",
        "B:",
        str(stats.tier_b),
        "",
        "Owner identificado:",
        f"{stats.owner_identified}/{stats.owner_identified_of}",
        "",
        "Owner Phone verificado (DIRECT/NAMED_ATTRIBUTION):",
        f"{stats.owner_phone_verified}/{stats.owner_phone_verified_of}",
        "",
        "Leads con multiples decisores:",
        str(stats.multi_decision_maker_leads),
        "",
        "Lead Quality promedio (calificados):",
        str(stats.avg_lead_quality),
        "",
        "Contact Quality promedio (calificados):",
        str(stats.avg_contact_quality),
        "",
        "Website auditado:",
        f"{stats.website_audited}/{stats.website_audited_of}",
        "",
        "Instagram:",
        f"{stats.instagram_found}/{stats.instagram_found_of}",
        "",
        "Duplicados:",
        str(stats.duplicates),
        "",
        "Decisores reutilizados (flag, no auto-drop):",
        str(stats.decision_maker_reuse_flags),
        "",
        "Google Sheet:",
        stats.google_sheet_name,
        "",
        "Worksheet:",
        stats.worksheet,
        "",
        "Cuenta Composio:",
        stats.composio_account,
    ]
    if stats.csv_paths:
        lines += ["", "Archivos CSV:"]
        for label, path in stats.csv_paths.items():
            lines.append(f"  {label}: {path}")
    return "\n".join(lines)


CLEAN_EXPORT_HEADERS = [
    "Empresa", "Decisor principal", "Otros decisores", "Teléfono decisor",
    "Confidence", "Sitio Web (URL)", "Qué decirle en la llamada", "Redes", "Ángulo", "Notas",
]


def _is_verified_text(value: str) -> bool:
    return bool(value) and str(value).strip().upper() not in NOT_VERIFIED_ALIASES


def _fallback_cold_call_hook(lead: Lead) -> str:
    """Best-effort conversational rewrite for leads researched before
    `cold_call_hook` existed (or where an agent forgot to fill it in).
    Never invents anything beyond `website_problem`/`website_evidence` —
    it only changes VOICE (third person technical -> second person spoken),
    so it stays inside the same evidence already required by the gate."""
    if not _is_verified_text(lead.website_problem):
        return "N/A (sin sitio web o sin problema verificado — no forzar un gancho de llamada)"
    problem = lead.website_problem.strip()
    # Lowercase the first letter only if the sentence doesn't start with a
    # proper noun/acronym, so the stitched sentence still reads naturally.
    lead_in = problem[0].lower() + problem[1:] if problem and problem[0].isupper() else problem
    return (
        f"Cuando entré a su sitio noté que {lead_in} "
        "— eso puede estarle costando clientes que no llegan a agendar. "
        "¿Tiene 15 minutos esta semana para mostrarle exactamente qué está pasando y cómo se arregla?"
    )


def build_clean_export_row(lead: Lead) -> dict:
    decisor = f"{lead.owner_name} — {lead.owner_role}" if lead.is_verified("owner_name") else "NOT FOUND"
    if lead.owner_authority_level and lead.owner_authority_level not in ("UNKNOWN", ""):
        decisor += f" ({lead.owner_authority_level})"
    web = lead.website if lead.is_verified("website") else ("N/A (sin sitio web)" if lead.website_status == "no_website" else "NOT FOUND")
    gancho = lead.cold_call_hook if _is_verified_text(lead.cold_call_hook) else _fallback_cold_call_hook(lead)
    redes = ", ".join(
        v for v in (lead.instagram, lead.facebook, lead.linkedin, lead.owner_instagram, lead.owner_linkedin)
        if v and v.upper() != "NOT_VERIFIED"
    ) or "NOT FOUND"
    telefono = lead.owner_phone if lead.owner_phone_confidence in ("DIRECT", "NAMED_ATTRIBUTION") else "NOT FOUND"
    return {
        "Empresa": lead.business_name,
        "Decisor principal": decisor,
        "Otros decisores": lead.secondary_decision_makers_summary or "—",
        "Teléfono decisor": telefono,
        "Confidence": lead.owner_phone_confidence,
        "Sitio Web (URL)": web,
        "Qué decirle en la llamada": gancho,
        "Redes": redes,
        "Ángulo": lead.angle or "",
        "Notas": lead.notes or "",
    }


def build_clean_export_table(leads: list[Lead]) -> list[dict]:
    return [build_clean_export_row(l) for l in leads]


def niche_slug(niche: str) -> str:
    """Filesystem/filename-safe slug for a niche name, used so one clean
    export / one .xlsx per niche never collide or get overwritten."""
    if not niche or not str(niche).strip():
        return "sin_nicho"
    text = unicodedata.normalize("NFKD", str(niche)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "sin_nicho"


def split_leads_by_niche(leads: list[Lead]) -> dict[str, list[Lead]]:
    """Groups leads by their exact `niche` string. A single run may
    discover/research several niches in parallel for efficiency, but the
    deliverable (clean export / .xlsx) must never mix them — one file per
    niche, always. Returns an ordered dict keyed by the niche name as it
    appears on the leads (first-seen order), so callers can build one
    output file per key without guessing niche names."""
    groups: dict[str, list[Lead]] = {}
    for lead in leads:
        key = lead.niche if _is_verified_text(lead.niche) else "(nicho no especificado)"
        groups.setdefault(key, []).append(lead)
    return groups


def build_clean_export_tables_by_niche(leads: list[Lead]) -> dict[str, list[dict]]:
    """Same as `build_clean_export_table`, but pre-split by niche so the
    caller can write/deliver one file per niche directly from the result."""
    return {
        niche: build_clean_export_table(niche_leads)
        for niche, niche_leads in split_leads_by_niche(leads).items()
    }
