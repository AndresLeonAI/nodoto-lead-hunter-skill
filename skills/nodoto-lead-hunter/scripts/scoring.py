"""
NODOTO LEAD HUNTER — qualification gate + scoring.

This is the one place that decides whether a researched candidate becomes a
Qualified Lead, a Candidate-Owner-Phone-Missing, or gets discarded. The gate is
intentionally stricter than the numeric score: a high score can NEVER buy its way
past a missing owner phone (playbook rules #6, #21, #22).

The four component scores (high_ticket, website_opportunity, owner_access,
data_quality) are 0-10 inputs the research/agent step must set on the Lead based
on what it actually found — this module does not invent them, it only combines
them and enforces the gate.
"""

from __future__ import annotations
from dataclasses import dataclass

from schema import (
    Lead, REQUIRED_FOR_QUALIFIED, NOT_VERIFIED,
    QUALIFICATION_STATUS_QUALIFIED, QUALIFICATION_STATUS_OWNER_PHONE_MISSING,
    QUALIFICATION_STATUS_DISCARDED,
)

WEIGHTS = {
    "high_ticket_score": 0.25,
    "website_opportunity_score": 0.30,
    "owner_access_score": 0.20,
    "data_quality_score": 0.15,
    # "market/urgency" (10%) is folded into high_ticket_score by the research step
    # unless the sheet schema grows a dedicated column; documented in SKILL.md.
}
MARKET_URGENCY_WEIGHT = 0.10

TIER_THRESHOLDS = [
    (9.0, "VIP"),
    (8.0, "A"),
    (7.0, "B"),
]
MIN_QUALIFYING_SCORE = 7.0


@dataclass
class GateResult:
    passed: bool
    status: str
    reasons: list[str]


def owner_phone_is_verified(lead: Lead) -> bool:
    if not lead.is_verified("owner_phone"):
        return False
    if not lead.is_verified("owner_phone_source"):
        return False
    # Hard rule: never accept the business phone silently relabeled as the owner phone.
    if lead.is_verified("business_phone") and lead.owner_phone.strip() == lead.business_phone.strip():
        if "owner" not in (lead.owner_phone_source or "").lower() and lead.owner_phone_source not in (
            "personal_confirmed", "same_number_confirmed_by_owner"
        ):
            # Same digits as the business line, with no explicit confirmation the
            # owner personally publishes that same number -> treat as unverified.
            return False
    return True


def run_qualification_gate(lead: Lead, market_urgency_score: float | None = None) -> GateResult:
    reasons = []

    if not owner_phone_is_verified(lead):
        return GateResult(
            passed=False,
            status=QUALIFICATION_STATUS_OWNER_PHONE_MISSING,
            reasons=["Owner phone missing or not publicly/professionally verifiable"],
        )

    for field_name in REQUIRED_FOR_QUALIFIED:
        attr = field_name.lower().replace(" ", "_").replace("-", "_")
        if not lead.is_verified(attr) and attr != "owner_phone":  # owner_phone already checked above
            reasons.append(f"Missing/unverified required field: {field_name}")

    score = compute_lead_score(lead, market_urgency_score)
    lead.lead_score = score
    lead.lead_tier = tier_for_score(score) if score is not None else ""

    if reasons:
        return GateResult(passed=False, status=QUALIFICATION_STATUS_DISCARDED, reasons=reasons)

    if score is None or score < MIN_QUALIFYING_SCORE:
        reasons.append(f"Lead Score {score} below minimum {MIN_QUALIFYING_SCORE}")
        return GateResult(passed=False, status=QUALIFICATION_STATUS_DISCARDED, reasons=reasons)

    return GateResult(passed=True, status=QUALIFICATION_STATUS_QUALIFIED, reasons=[])


def compute_lead_score(lead: Lead, market_urgency_score: float | None = None) -> float | None:
    components = {
        "high_ticket_score": lead.high_ticket_score,
        "website_opportunity_score": lead.website_opportunity_score,
        "owner_access_score": lead.owner_access_score,
        "data_quality_score": lead.data_quality_score,
    }
    if any(v is None for v in components.values()):
        return None

    weighted = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    if market_urgency_score is not None:
        weighted += market_urgency_score * MARKET_URGENCY_WEIGHT
    else:
        # Renormalize across the 90% that IS known if market/urgency wasn't scored separately.
        weighted = weighted / (1 - MARKET_URGENCY_WEIGHT)
    return round(min(weighted, 10.0), 2)


def tier_for_score(score: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "DESCARTAR"
