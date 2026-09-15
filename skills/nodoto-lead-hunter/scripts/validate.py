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

v4.0 addition (2026-09-15): also re-runs `role_guard.role_contradicts_evidence()`
as defense in depth against the receptionist/secretary/scheduling/call-center/
general-WhatsApp/business-line problem documented in `schema.py`'s v4.0 note —
the same cross-check the gate uses, applied here too so a mis-tagged Owner
Contact Role is caught with a specific reason rather than silently passing.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from schema import Lead
from role_guard import role_contradicts_evidence

_GENERIC_SOURCE_PATTERNS = [
    r"^internet$", r"^google$", r"^web$", r"^social media$", r"^redes sociales$",
    r"^instagram$", r"^facebook$", r"^linkedin$", r"^search$", r"^b[uú]squeda$",
    r"^unknown$", r"^varios$", r"^online$",
]

_VAGUE_PROBLEM_PATTERNS = [
    r"^(the )?website is (bad|old|ugly|poor|weak)\.?$",
    r"^(el )?(sitio|website|pagina|página) (es|esta|está) (malo|mala|feo|anticuado|debil|débil)\.?$",
    r"^no good\.?$", r"^needs improvement\.?$", r"^could be better\.?$",
    r"^mala presencia digital\.?$", r"^presencia web deficiente\.?$",
]

MIN_EVIDENCE_LENGTH = 40

_GENERIC_EVIDENCE_PATTERNS = [
    r"^confirmed\.?$", r"^verified\.?$", r"^confirmado\.?$", r"^verificado\.?$",
    r"^yes\.?$", r"^s[ií]\.?$", r"^checked\.?$", r"^revisado\.?$",
]


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

    if lead.owner_phone_evidence and lead.owner_phone_evidence != "NOT_VERIFIED":
        if _matches_any(lead.owner_phone_evidence, _GENERIC_EVIDENCE_PATTERNS):
            errors.append(
                f"Owner Phone Evidence is a bare claim, not evidence: '{lead.owner_phone_evidence}'. "
                "Describe what specifically proves this number belongs to this person (e.g. 'wa.me link "
                "in the source of dr.perez's own Instagram bio, checked 2026-09-11')."
            )
        elif len(lead.owner_phone_evidence.strip()) < MIN_EVIDENCE_LENGTH:
            warnings.append(
                f"Owner Phone Evidence is short ({len(lead.owner_phone_evidence.strip())} chars) — "
                "confirm it actually demonstrates the person<->number link, not just where it was seen."
            )

    if lead.owner_phone_discrepancy and lead.owner_phone_discrepancy.strip():
        warnings.append(
            f"Owner Phone Discrepancy is non-empty ('{lead.owner_phone_discrepancy}') — a lead with an "
            "unresolved contradiction between sources should not be treated as fully clean even if it "
            "otherwise passes the gate; double-check before outreach."
        )

    if lead.decision_maker_count > 1 and not lead.secondary_decision_makers_summary:
        errors.append(
            "Decision Maker Count > 1 but Secondary Decision Makers is empty — the secondary "
            "decision-maker(s) were found but not recorded, which silently loses them."
        )

    # v4.0 VAULT — defense in depth: re-run the same keyword cross-check the
    # gate uses (scoring.decision_maker_phone_is_verified) here too, so a
    # lead that somehow reaches validation with a mis-tagged Owner Contact
    # Role still gets caught, with a message naming exactly why.
    primary_role_contradictions = role_contradicts_evidence(
        lead.owner_contact_role, lead.owner_role, lead.owner_phone_source,
        lead.owner_phone_evidence, lead.owner_phone_discrepancy,
    )
    errors.extend(primary_role_contradictions)

    for person in lead.decision_makers:
        if person.phone_confidence in ("DIRECT", "NAMED_ATTRIBUTION") and person.phone_source and \
                _matches_any(person.phone_source, _GENERIC_SOURCE_PATTERNS):
            errors.append(
                f"Decision maker '{person.name}' has confidence '{person.phone_confidence}' but a generic "
                f"phone source ('{person.phone_source}') — confidence that high requires a specific source."
            )
        person_role_contradictions = role_contradicts_evidence(
            person.contact_role, person.role, person.phone_source, person.phone_evidence, person.phone_discrepancy,
        )
        for msg in person_role_contradictions:
            errors.append(f"Decision maker '{person.name}': {msg}")

    return ValidationResult(ok=(len(errors) == 0), warnings=warnings, errors=errors)
