"""
NODOTO LEAD HUNTER — final run report, in the exact format required by the skill.
"""

from __future__ import annotations
from dataclasses import dataclass, field


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
    google_sheet_name: str = "N/A (CSV-only output)"
    worksheet: str = "N/A"
    composio_account: str = "N/A"
    csv_paths: dict = field(default_factory=dict)


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
        "Owner Phone verificado:",
        f"{stats.owner_phone_verified}/{stats.owner_phone_verified_of}",
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
