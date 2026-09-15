"""
NODOTO LEAD HUNTER — qualification gate + scoring (v4.0 "VAULT").

Audit finding v3 fixed: the old scoring blended "is this a good business to
sell to" and "can we actually reach the decision-maker" into one number, so a
great business with only a switchboard number scored the same contactability
as one with a verified direct line. v3 keeps them separate:

  LEAD QUALITY    = is this business worth pursuing at all (money, need, gap)
  CONTACT QUALITY = can we actually reach the person who decides

The gate is still stricter than either score: a lead can never reach
QUALIFIED without a decision-maker phone at DIRECT or NAMED_ATTRIBUTION
confidence, no matter how high Lead Quality is (playbook rules #6, #21, #22,
extended in v3 to also require the decision-maker still be current/in-charge).

v4.0 fixes the critical failure the user reported directly (2026-09-15):
`phone_confidence` (DIRECT/NAMED_ATTRIBUTION/...) only measures how solid the
evidence is that a phone belongs to a NAMED PERSON — it says nothing about
whether that person is actually the owner/decision-maker rather than a
receptionist, secretary, scheduler, call-center agent, or a general business
line. A receptionist's own extension, proven with excellent evidence, still
scored DIRECT before this change. `decision_maker_phone_is_verified()` now
ALSO hard-requires `contact_role` (schema.py) to be a decision-maker role —
`UNKNOWN` or any staff role fails the gate exactly like a missing phone — and
cross-checks the claim against the evidence text itself via
`role_guard.role_contradicts_evidence()`, so a mis-tagged `contact_role`
cannot ride through on a mistaken label. This is deliberately biased toward
false negatives: "Prefiero perder 10 leads antes que recibir 10 números de
recepción" (the user's own words). See `docs/owner_phone_vault_v4.md` in the
memory repo for the full root-cause analysis.
"""

from __future__ import annotations
import re
from dataclasses import dataclass

from schema import (
    Lead, REQUIRED_FOR_QUALIFIED, VALID_OWNER_PHONE_CONFIDENCE, ALL_PHONE_CONFIDENCE_LEVELS,
    ALL_VERIFICATION_STATUSES, ALL_AUTHORITY_LEVELS,
    PHONE_CONFIDENCE_DIRECT, PHONE_CONFIDENCE_NAMED_ATTRIBUTION, PHONE_CONFIDENCE_VERIFIED_BUSINESS,
    PHONE_CONFIDENCE_GENERIC, AUTHORITY_FINAL, AUTHORITY_INFLUENCER,
    VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_CONTRADICTED,
    QUALIFICATION_STATUS_QUALIFIED, QUALIFICATION_STATUS_OWNER_PHONE_MISSING,
    QUALIFICATION_STATUS_DISCARDED,
    ALL_CONTACT_ROLE_TYPES, DECISION_MAKER_CONTACT_ROLES, NON_DECISION_MAKER_CONTACT_ROLES,
    CONTACT_ROLE_UNKNOWN,
)
from role_guard import role_contradicts_evidence

LEAD_QUALITY_WEIGHTS = {
    "high_ticket_score": 0.45,
    "website_opportunity_score": 0.40,
    "data_quality_score": 0.15,
}

TIER_THRESHOLDS = [
    (9.0, "VIP"),
    (8.0, "A"),
    (7.0, "B"),
]
MIN_QUALIFYING_SCORE = 7.0

COMBINED_WEIGHTS = {"lead_quality": 0.6, "contact_quality": 0.4}

_CO_PHONE_RE = re.compile(r"^[0-9]{7,10}$")


@dataclass
class GateResult:
    passed: bool
    status: str
    reasons: list[str]


def _normalize_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("57") and len(digits) > 10:
        digits = digits[2:]
    return digits.lstrip("0")


def phone_format_is_plausible(phone: str) -> bool:
    digits = _normalize_digits(phone)
    return bool(_CO_PHONE_RE.match(digits))


def decision_maker_phone_is_verified(lead: Lead) -> bool:
    if not lead.is_verified("owner_phone"):
        return False
    if not lead.is_verified("owner_phone_source"):
        return False
    if not lead.is_verified("owner_phone_evidence"):
        return False
    confidence = (lead.owner_phone_confidence or "").strip().upper()
    if confidence not in VALID_OWNER_PHONE_CONFIDENCE:
        return False
    if not phone_format_is_plausible(lead.owner_phone):
        return False
    if lead.owner_is_current is False:
        return False
    if (lead.owner_verification_status or "").strip().upper() == VERIFICATION_STATUS_CONTRADICTED:
        return False
    if lead.is_verified("business_phone") and lead.owner_phone.strip() == lead.business_phone.strip():
        if confidence not in VALID_OWNER_PHONE_CONFIDENCE or "owner" not in (lead.owner_phone_source or "").lower():
            return False

    # --- v4.0 VAULT: a strong phone-evidence tier is worthless if the person
    # answering isn't the decision-maker. `contact_role` is mandatory and
    # must be an actual decision-maker role — UNKNOWN (unclassified) and any
    # explicit staff role (reception/secretary/scheduling/call-center/
    # general-WhatsApp/business-line) fail exactly like a missing phone. ---
    contact_role = (lead.owner_contact_role or "").strip().upper()
    if contact_role not in DECISION_MAKER_CONTACT_ROLES:
        return False

    # Second, independent line of defense: even a correctly-tagged
    # decision-maker role is rejected if the phone's own source/evidence
    # text names a staff/generic-line signal — never trust the tag blindly.
    if role_contradicts_evidence(
        contact_role, lead.owner_role, lead.owner_phone_source,
        lead.owner_phone_evidence, lead.owner_phone_discrepancy,
    ):
        return False

    return True


def owner_contact_role_rejection_reason(lead: Lead) -> str | None:
    """Human-readable reason `decision_maker_phone_is_verified` failed
    specifically on the v4.0 vault check, or None if that's not why. Kept
    separate from `decision_maker_phone_is_verified` (which stays a plain
    bool) so `run_qualification_gate` can surface a reason that names the
    actual problem — "receptionist number" — instead of the generic "phone
    missing" message, per the user's explicit ask to document this clearly."""
    contact_role = (lead.owner_contact_role or "").strip().upper()
    if contact_role in NON_DECISION_MAKER_CONTACT_ROLES:
        return (
            f"Owner Contact Role is '{contact_role}' — a receptionist/secretary/scheduler/call-center/"
            "general-WhatsApp/business-line contact is never eligible as the qualifying Owner Phone, "
            "no matter the phone-evidence tier (vault rule v4.0). Find the actual owner/decision-maker's "
            "own number, or leave this lead as OWNER_PHONE_MISSING."
        )
    if contact_role == CONTACT_ROLE_UNKNOWN or contact_role not in ALL_CONTACT_ROLE_TYPES:
        return (
            "Owner Contact Role is not classified (UNKNOWN) — vault rule v4.0 treats an unclassified "
            "contact exactly like a missing phone. Classify who actually answers this number "
            "(owner/founder, partner, director/manager, other decision-maker, or sole practitioner) "
            "before this phone can count as Owner Phone."
        )
    contradictions = role_contradicts_evidence(
        contact_role, lead.owner_role, lead.owner_phone_source,
        lead.owner_phone_evidence, lead.owner_phone_discrepancy,
    )
    if contradictions:
        return "; ".join(contradictions)
    return None


owner_phone_is_verified = decision_maker_phone_is_verified


def compute_lead_quality_score(lead: Lead) -> float | None:
    components = {
        "high_ticket_score": lead.high_ticket_score,
        "website_opportunity_score": lead.website_opportunity_score,
        "data_quality_score": lead.data_quality_score,
    }
    if any(v is None for v in components.values()):
        return None
    weighted = sum(components[k] * LEAD_QUALITY_WEIGHTS[k] for k in LEAD_QUALITY_WEIGHTS)
    return round(min(weighted, 10.0), 2)


def compute_contact_quality_score(lead: Lead) -> float:
    score = 0.0

    if lead.is_verified("owner_name"):
        score += 1.5
    if lead.is_verified("owner_role"):
        score += 0.5
    if (lead.owner_authority_level or "").strip().upper() in (AUTHORITY_FINAL, AUTHORITY_INFLUENCER):
        score += 1.0

    confidence = (lead.owner_phone_confidence or "").strip().upper()
    phone_points = {
        PHONE_CONFIDENCE_DIRECT: 5.0,
        PHONE_CONFIDENCE_NAMED_ATTRIBUTION: 3.5,
        PHONE_CONFIDENCE_VERIFIED_BUSINESS: 0.75,
        PHONE_CONFIDENCE_GENERIC: 0.25,
    }.get(confidence, 0.0)
    score += phone_points

    if phone_points > 0 and lead.is_verified("owner_phone_evidence"):
        score += 0.5
    if (lead.owner_verification_status or "").strip().upper() == VERIFICATION_STATUS_VERIFIED:
        score += 0.5
    if lead.is_verified("owner_email") or lead.is_verified("owner_linkedin") or lead.is_verified("owner_instagram"):
        score += 0.5
    if lead.owner_is_current is False:
        score = min(score, 1.0)

    return round(min(score, 10.0), 2)


def compute_lead_score(lead: Lead) -> float | None:
    lq = compute_lead_quality_score(lead)
    if lq is None:
        return None
    cq = compute_contact_quality_score(lead)
    lead.lead_quality_score = lq
    lead.contact_quality_score = cq
    weighted = lq * COMBINED_WEIGHTS["lead_quality"] + cq * COMBINED_WEIGHTS["contact_quality"]
    return round(min(weighted, 10.0), 2)


def tier_for_score(score: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "DESCARTAR"


def _validate_enum_fields(lead: Lead) -> list[str]:
    errors = []
    if lead.is_verified("owner_phone_confidence"):
        val = (lead.owner_phone_confidence or "").strip().upper()
        if val not in ALL_PHONE_CONFIDENCE_LEVELS:
            errors.append(f"Owner Phone Confidence '{lead.owner_phone_confidence}' is not a recognized tier "
                          f"(expected one of {sorted(ALL_PHONE_CONFIDENCE_LEVELS)})")
    if lead.owner_verification_status and lead.owner_verification_status.strip().upper() not in ALL_VERIFICATION_STATUSES:
        errors.append(f"Owner Verification Status '{lead.owner_verification_status}' is not recognized "
                      f"(expected one of {sorted(ALL_VERIFICATION_STATUSES)})")
    if lead.owner_authority_level and lead.owner_authority_level.strip().upper() not in ALL_AUTHORITY_LEVELS:
        errors.append(f"Owner Authority Level '{lead.owner_authority_level}' is not recognized "
                      f"(expected one of {sorted(ALL_AUTHORITY_LEVELS)})")
    if lead.is_verified("owner_contact_role") and lead.owner_contact_role.strip().upper() not in ALL_CONTACT_ROLE_TYPES:
        errors.append(f"Owner Contact Role '{lead.owner_contact_role}' is not a recognized value "
                      f"(expected one of {sorted(ALL_CONTACT_ROLE_TYPES)})")
    if lead.is_verified("owner_phone") and not phone_format_is_plausible(lead.owner_phone):
        errors.append(f"Owner Phone '{lead.owner_phone}' does not look like a valid Colombian number "
                      f"after normalization — check for a transcription error before accepting it")
    return errors


def run_qualification_gate(lead: Lead) -> GateResult:
    reasons = []

    enum_errors = _validate_enum_fields(lead)
    if enum_errors:
        return GateResult(passed=False, status=QUALIFICATION_STATUS_DISCARDED, reasons=enum_errors)

    if not decision_maker_phone_is_verified(lead):
        reason = "Decision-maker phone missing or not publicly/professionally verifiable"
        if lead.owner_is_current is False:
            reason = "Identified decision-maker is no longer current (sold/left/retired) — needs a current one"
        elif (lead.owner_verification_status or "").strip().upper() == VERIFICATION_STATUS_CONTRADICTED:
            reason = "Owner Phone has unresolved contradicting sources (see Owner Phone Discrepancy)"
        else:
            vault_reason = owner_contact_role_rejection_reason(lead)
            if vault_reason:
                reason = vault_reason
        return GateResult(passed=False, status=QUALIFICATION_STATUS_OWNER_PHONE_MISSING, reasons=[reason])

    for field_name in REQUIRED_FOR_QUALIFIED:
        attr = field_name.lower().replace(" ", "_").replace("-", "_")
        if attr in ("owner_phone",):
            continue
        if not lead.is_verified(attr):
            reasons.append(f"Missing/unverified required field: {field_name}")

    score = compute_lead_score(lead)
    lead.lead_score = score
    lead.lead_tier = tier_for_score(score) if score is not None else ""

    if reasons:
        return GateResult(passed=False, status=QUALIFICATION_STATUS_DISCARDED, reasons=reasons)

    if score is None or score < MIN_QUALIFYING_SCORE:
        reasons.append(f"Lead Score {score} below minimum {MIN_QUALIFYING_SCORE}")
        return GateResult(passed=False, status=QUALIFICATION_STATUS_DISCARDED, reasons=reasons)

    return GateResult(passed=True, status=QUALIFICATION_STATUS_QUALIFIED, reasons=[])
