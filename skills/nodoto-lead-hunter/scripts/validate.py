"""
NODOTO LEAD HUNTER — evidence-quality validation.

The qualification gate (scoring.py) checks that required fields are non-empty
and not NOT_VERIFIED. It does NOT check whether a field is actually specific
enough to count as real evidence rather than a vague placeholder someone typed
to get past the gate. This module catches that: it flags generic phone
sources, vague website-problem text, and other "technically filled in but not
actually verifiable" patterns described in playbook rules #17 and #25.

Use it as an additional check before writing to Qualified Leads — a lead can
pass `scoring.run_qualification_gate` and still fail `validate_evidence_quality`
if the research was shallow.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from schema import Lead

# Sources too generic to count as "Owner Phone Source" — the source must name
# WHERE specifically (e.g. "Instagram oficial @drname, bio destacada" is fine;
# "Instagram", "internet", "Google" alone are not).
_GENERIC_SOURCE_PATTERNS = [
    r"^internet$", r"^google$", r"^web$", r"^social media$", r"^redes sociales$",
    r"^instagram$", r"^facebook$", r"^linkedin$", r"^search$", r"^b[uú]squeda$",
    r"^unknown$", r"^varios$", r"^online$",
]

# Website-problem phrasing too vague to be checkable (playbook rule #17: never
# "Website is bad", always a specific, testable observation).
_VAGUE_PROBLEM_PATTERNS = [
    r"^(the )?website is (bad|old|ugly|poor|weak)\.?$",
    r"^(el )?(sitio|website|pagina|página) (es|esta|está) (malo|mala|feo|anticuado|debil|débil)\.?$",
    r"^no good\.?$", r"^needs improvement\.?$", r"^could be better\.?$",
    r"^mala presencia digital\.?$", r"^presencia web deficiente\.?$",
]

MIN_EVIDENCE_LENGTH = 40  # characters; a real, specific observation is rarely shorter


@dataclass
class ValidationResult:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _matches_any(value: str, patterns: list[str]) -> bool:
    v = (value or "").strip().lower()
    return any(re.match(p, v) for p in patterns)


def validate_evidence_quality(lead: Lead) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if lead.owner_phone_source and lead.owner_phone_source != "NOT_VERIFIED":
        if _matches_any(lead.owner_phone_source, _GENERIC_SOURCE_PATTERNS):
            errors.append(
                f"Owner Phone Source is too generic to audit: '{lead.owner_phone_source}'. "
                "Name the specific page/profile/section, e.g. "
                "'Instagram oficial @dr.perez, bio' or 'Website profesional, pagina de contacto'."
            )

    if lead.website_problem and lead.website_problem != "NOT_VERIFIED":
        if _matches_any(lead.website_problem, _VAGUE_PROBLEM_PATTERNS):
            errors.append(
                f"Website Problem is a vague adjective, not a checkable observation: "
                f"'{lead.website_problem}'."
            )
        if len(lead.website_problem.strip()) < MIN_EVIDENCE_LENGTH:
            warnings.append(
                f"Website Problem is short ({len(lead.website_problem.strip())} chars) — "
                "confirm it's a specific, testable claim and not a shorthand label."
            )

    if lead.website_evidence and lead.website_evidence != "NOT_VERIFIED":
        if len(lead.website_evidence.strip()) < MIN_EVIDENCE_LENGTH:
            warnings.append(
                f"Website Evidence is short ({len(lead.website_evidence.strip())} chars) — "
                "should describe what was actually seen (page, element, date checked)."
            )
    elif lead.website_problem and lead.website_problem != "NOT_VERIFIED":
        errors.append("Website Problem is set but Website Evidence is missing — evidence is mandatory (rule #17).")

    if lead.owner_name and lead.owner_name != "NOT_VERIFIED" and not lead.owner_role:
        errors.append("Owner Name is set but Owner Role is missing.")

    return ValidationResult(ok=(len(errors) == 0), warnings=warnings, errors=errors)
