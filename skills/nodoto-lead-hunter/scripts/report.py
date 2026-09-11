"""
NODOTO LEAD HUNTER — final run report + clean export table (v3).
"""

from __future__ import annotations
from dataclasses import dataclass, field

from schema import Lead


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
    "Confidence", "Web", "Problema", "Redes", "Ángulo", "Notas",
]


def build_clean_export_row(lead: Lead) -> dict:
    decisor = f"{lead.owner_name} — {lead.owner_role}" if lead.is_verified("owner_name") else "NOT FOUND"
    if lead.owner_authority_level and lead.owner_authority_level not in ("UNKNOWN", ""):
        decisor += f" ({lead.owner_authority_level})"
    web = lead.website if lead.is_verified("website") else ("Sin sitio web" if lead.website_status == "no_website" else "NOT FOUND")
    problema = lead.website_problem if lead.is_verified("website_problem") else "N/A"
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
        "Web": web,
        "Problema": problema,
        "Redes": redes,
        "Ángulo": lead.angle or "",
        "Notas": lead.notes or "",
    }


def build_clean_export_table(leads: list[Lead]) -> list[dict]:
    return [build_clean_export_row(l) for l in leads]
