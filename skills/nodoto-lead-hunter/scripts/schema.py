"""
NODOTO LEAD HUNTER — canonical column schema (v3: multi-decision-maker).

This is the single source of truth for the shape of a lead row, used by:
  - dedupe.py        (which fields to normalize/compare)
  - scoring.py        (Lead Quality vs Contact Quality + the qualification gate)
  - sheets_io.py       (what gets written to Google Sheets / CSV)
  - report.py          (the clean export table + run report)

v3 change (audit finding): a business is never assumed to have exactly one
decision-maker. `decision_makers_json` carries the FULL list this run found
(primary + secondary, each with its own phone/confidence/evidence). The flat
`owner_*` fields are kept for backward compatibility and ARE the mirror of the
PRIORITIZED PRIMARY decision-maker — they are what dedupe.py/scoring.py's gate
actually operate on, so existing call sites did not need to change shape.

v4.0 change (user directive, 2026-09-15 — "VAULT" upgrade): root-cause fix for
a critical failure the user reported directly: the pipeline was delivering
"Owner Phone" numbers that actually belonged to receptionists, secretaries,
scheduling/appointment lines, call centers, general customer-service WhatsApp,
or generic business lines — never the owner/decision-maker. See
`docs/owner_phone_vault_v4.md` in the memory repo for the full root-cause
analysis. The root cause: `owner_phone_confidence` (DIRECT/NAMED_ATTRIBUTION/
...) measures how solid the evidence is that a PHONE belongs to a NAMED
PERSON — it says nothing about whether that named person is actually the
decision-maker rather than staff. A receptionist's own direct extension,
proven with excellent evidence, still scored DIRECT. `owner_authority_level`
existed but only affected the Contact Quality *score* — it was never a gate
requirement, so a lead could sail through the gate with `Owner Authority
Level = UNKNOWN` as long as the phone-evidence tier was high.

The fix adds a SEPARATE, mandatory classification of WHO the phone actually
reaches — `Owner Contact Role` (`contact_role` on each `DecisionMaker`) — with
its own vocabulary that a phone-evidence tier can never override:
decision-maker roles (`OWNER_FOUNDER`, `PARTNER`, `DIRECTOR_MANAGER`,
`DECISION_MAKER_OTHER`, `SOLE_PRACTITIONER`) vs. staff/non-decision-maker
roles (`RECEPTION`, `SECRETARY`, `SCHEDULING`, `CALL_CENTER`,
`GENERAL_WHATSAPP`, `BUSINESS_LINE`) vs. `UNKNOWN` (not yet classified).
`scoring.decision_maker_phone_is_verified()` now HARD-REQUIRES the primary
decision-maker's `contact_role` to be in the decision-maker set — `UNKNOWN`
is treated exactly like a missing phone, never a pass. It is deliberately
biased toward false negatives over false positives, per the user's explicit
instruction: "Prefiero perder 10 leads antes que recibir 10 números de
recepción." See `role_guard.py` for the keyword-based cross-check that also
rejects a lead when the phone source/evidence text itself names reception/
secretary/scheduling/call-center/WhatsApp-general/business-line signals, even
if a sub-agent mis-tagged `contact_role` as a decision-maker role — a defense
against the tag itself being wrong, not just against it being missing.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field, fields
from typing import Optional

COLUMNS = [
    "Business Name", "Niche", "Sub-Niche", "City", "Neighborhood", "Address", "Google Maps",
    "Owner Name", "Owner Role", "Owner Authority Level", "Owner Contact Role", "Owner Is Current",
    "Owner Phone", "Owner Phone Source", "Owner Phone Evidence", "Owner Phone Confidence",
    "Owner Phone Discrepancy", "Owner Verification Status",
    "Owner LinkedIn", "Owner Instagram", "Owner Email",
    "Decision Makers JSON", "Secondary Decision Makers", "Decision Maker Count",
    "Business Phone", "Business WhatsApp", "Business Email",
    "Website", "Website Status", "Website Problem", "Website Evidence", "Instagram", "Facebook", "LinkedIn",
    "High Ticket Score", "Website Opportunity Score", "Data Quality Score",
    "Lead Quality Score", "Contact Quality Score",
    "Lead Score", "Lead Tier", "Qualification Status",
    "Research Date", "Sources", "Notes", "Angle", "Cold Call Hook",
]

REQUIRED_FOR_QUALIFIED = [
    "Business Name", "Niche", "City",
    "Owner Name", "Owner Role", "Owner Contact Role", "Owner Phone", "Owner Phone Source",
    "Owner Phone Evidence", "Owner Phone Confidence", "Owner Verification Status",
    "Website Problem", "Website Evidence",
]

PHONE_CONFIDENCE_DIRECT = "DIRECT"
PHONE_CONFIDENCE_NAMED_ATTRIBUTION = "NAMED_ATTRIBUTION"
PHONE_CONFIDENCE_VERIFIED_BUSINESS = "VERIFIED_BUSINESS"
PHONE_CONFIDENCE_GENERIC = "GENERIC"
PHONE_CONFIDENCE_UNKNOWN = "UNKNOWN"

ALL_PHONE_CONFIDENCE_LEVELS = {
    PHONE_CONFIDENCE_DIRECT, PHONE_CONFIDENCE_NAMED_ATTRIBUTION,
    PHONE_CONFIDENCE_VERIFIED_BUSINESS, PHONE_CONFIDENCE_GENERIC, PHONE_CONFIDENCE_UNKNOWN,
}
VALID_OWNER_PHONE_CONFIDENCE = {PHONE_CONFIDENCE_DIRECT, PHONE_CONFIDENCE_NAMED_ATTRIBUTION}

VERIFICATION_STATUS_VERIFIED = "VERIFIED"
VERIFICATION_STATUS_UNVERIFIED = "UNVERIFIED"
VERIFICATION_STATUS_CONTRADICTED = "CONTRADICTED"
ALL_VERIFICATION_STATUSES = {
    VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_UNVERIFIED, VERIFICATION_STATUS_CONTRADICTED,
}

AUTHORITY_FINAL = "FINAL"
AUTHORITY_INFLUENCER = "INFLUENCER"
AUTHORITY_UNKNOWN = "UNKNOWN"
ALL_AUTHORITY_LEVELS = {AUTHORITY_FINAL, AUTHORITY_INFLUENCER, AUTHORITY_UNKNOWN}

# --- v4.0 "VAULT" — Owner Contact Role taxonomy ----------------------------
# WHO actually answers this phone, as opposed to how solid the evidence is
# that a phone belongs to a named person (that's `phone_confidence`, above).
# A receptionist's own personal cell, proven with perfect evidence, is still
# a receptionist's phone — never eligible as "Owner Phone". See the v4.0 note
# at the top of this file and `role_guard.py`.
CONTACT_ROLE_OWNER_FOUNDER = "OWNER_FOUNDER"
CONTACT_ROLE_PARTNER = "PARTNER"
CONTACT_ROLE_DIRECTOR_MANAGER = "DIRECTOR_MANAGER"
CONTACT_ROLE_DECISION_MAKER_OTHER = "DECISION_MAKER_OTHER"
CONTACT_ROLE_SOLE_PRACTITIONER = "SOLE_PRACTITIONER"

CONTACT_ROLE_RECEPTION = "RECEPTION"
CONTACT_ROLE_SECRETARY = "SECRETARY"
CONTACT_ROLE_SCHEDULING = "SCHEDULING"
CONTACT_ROLE_CALL_CENTER = "CALL_CENTER"
CONTACT_ROLE_GENERAL_WHATSAPP = "GENERAL_WHATSAPP"
CONTACT_ROLE_BUSINESS_LINE = "BUSINESS_LINE"

CONTACT_ROLE_UNKNOWN = "UNKNOWN"

# Eligible as the qualifying "Owner Phone" contact.
DECISION_MAKER_CONTACT_ROLES = {
    CONTACT_ROLE_OWNER_FOUNDER, CONTACT_ROLE_PARTNER, CONTACT_ROLE_DIRECTOR_MANAGER,
    CONTACT_ROLE_DECISION_MAKER_OTHER, CONTACT_ROLE_SOLE_PRACTITIONER,
}
# Explicitly staff/generic — never eligible, no matter the phone-evidence tier.
NON_DECISION_MAKER_CONTACT_ROLES = {
    CONTACT_ROLE_RECEPTION, CONTACT_ROLE_SECRETARY, CONTACT_ROLE_SCHEDULING,
    CONTACT_ROLE_CALL_CENTER, CONTACT_ROLE_GENERAL_WHATSAPP, CONTACT_ROLE_BUSINESS_LINE,
}
ALL_CONTACT_ROLE_TYPES = DECISION_MAKER_CONTACT_ROLES | NON_DECISION_MAKER_CONTACT_ROLES | {CONTACT_ROLE_UNKNOWN}

NOT_VERIFIED = "NOT_VERIFIED"
NOT_VERIFIED_ALIASES = {
    "NOT_VERIFIED", "NO_VERIFIED", "N/A", "NA", "", "NONE", "UNKNOWN", "TBD", "NOT FOUND", "NOT_FOUND",
}

QUALIFICATION_STATUS_QUALIFIED = "QUALIFIED"
QUALIFICATION_STATUS_OWNER_PHONE_MISSING = "OWNER_PHONE_MISSING"
QUALIFICATION_STATUS_DISCARDED = "DISCARDED"
QUALIFICATION_STATUS_DUPLICATE = "DUPLICATE"

WORKSHEET_QUALIFIED = "Qualified Leads"
WORKSHEET_CANDIDATES_OWNER_MISSING = "Candidates - Decision Maker Phone Missing"
WORKSHEET_RUN_LOG = "Run Log"


@dataclass
class DecisionMaker:
    name: str = NOT_VERIFIED
    role: str = NOT_VERIFIED
    authority_level: str = AUTHORITY_UNKNOWN
    contact_role: str = CONTACT_ROLE_UNKNOWN
    is_current: bool = True
    phone: str = NOT_VERIFIED
    phone_confidence: str = PHONE_CONFIDENCE_UNKNOWN
    phone_source: str = NOT_VERIFIED
    phone_evidence: str = NOT_VERIFIED
    phone_discrepancy: str = ""
    email: str = NOT_VERIFIED
    social_profiles: str = NOT_VERIFIED
    priority: int = 1
    verification_status: str = VERIFICATION_STATUS_UNVERIFIED

    def to_dict(self) -> dict:
        return {
            "name": self.name, "role": self.role, "authority_level": self.authority_level,
            "contact_role": self.contact_role,
            "is_current": self.is_current, "phone": self.phone,
            "phone_confidence": self.phone_confidence, "phone_source": self.phone_source,
            "phone_evidence": self.phone_evidence, "phone_discrepancy": self.phone_discrepancy,
            "email": self.email, "social_profiles": self.social_profiles,
            "priority": self.priority, "verification_status": self.verification_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionMaker":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Lead:
    business_name: str = ""
    niche: str = ""
    sub_niche: str = ""
    city: str = "Bogotá"
    neighborhood: str = NOT_VERIFIED
    address: str = NOT_VERIFIED
    google_maps: str = NOT_VERIFIED

    decision_makers: list = field(default_factory=list)

    owner_name: str = NOT_VERIFIED
    owner_role: str = NOT_VERIFIED
    owner_authority_level: str = AUTHORITY_UNKNOWN
    owner_contact_role: str = CONTACT_ROLE_UNKNOWN
    owner_is_current: bool = True
    owner_phone: str = NOT_VERIFIED
    owner_phone_source: str = NOT_VERIFIED
    owner_phone_evidence: str = NOT_VERIFIED
    owner_phone_confidence: str = PHONE_CONFIDENCE_UNKNOWN
    owner_phone_discrepancy: str = ""
    owner_verification_status: str = VERIFICATION_STATUS_UNVERIFIED
    owner_linkedin: str = NOT_VERIFIED
    owner_instagram: str = NOT_VERIFIED
    owner_email: str = NOT_VERIFIED

    business_phone: str = NOT_VERIFIED
    business_whatsapp: str = NOT_VERIFIED
    business_email: str = NOT_VERIFIED

    website: str = NOT_VERIFIED
    website_status: str = NOT_VERIFIED
    website_problem: str = NOT_VERIFIED
    website_evidence: str = NOT_VERIFIED
    instagram: str = NOT_VERIFIED
    facebook: str = NOT_VERIFIED
    linkedin: str = NOT_VERIFIED

    high_ticket_score: Optional[float] = None
    website_opportunity_score: Optional[float] = None
    data_quality_score: Optional[float] = None
    lead_quality_score: Optional[float] = None
    contact_quality_score: Optional[float] = None
    lead_score: Optional[float] = None
    lead_tier: str = ""
    qualification_status: str = ""

    research_date: str = ""
    sources: str = ""
    notes: str = ""
    angle: str = ""
    cold_call_hook: str = NOT_VERIFIED

    def is_verified(self, field_name: str) -> bool:
        val = getattr(self, field_name, "")
        if isinstance(val, bool):
            return True
        return bool(val) and str(val).strip().upper() not in NOT_VERIFIED_ALIASES

    def set_decision_makers(self, people: list) -> None:
        self.decision_makers = list(people)
        if not people:
            self.owner_name = NOT_VERIFIED
            self.owner_role = NOT_VERIFIED
            self.owner_authority_level = AUTHORITY_UNKNOWN
            self.owner_contact_role = CONTACT_ROLE_UNKNOWN
            self.owner_is_current = True
            self.owner_phone = NOT_VERIFIED
            self.owner_phone_source = NOT_VERIFIED
            self.owner_phone_evidence = NOT_VERIFIED
            self.owner_phone_confidence = PHONE_CONFIDENCE_UNKNOWN
            self.owner_phone_discrepancy = ""
            self.owner_verification_status = VERIFICATION_STATUS_UNVERIFIED
            self.owner_email = NOT_VERIFIED
            return
        primary = people[0]
        self.owner_name = primary.name
        self.owner_role = primary.role
        self.owner_authority_level = primary.authority_level
        self.owner_contact_role = primary.contact_role
        self.owner_is_current = primary.is_current
        self.owner_phone = primary.phone
        self.owner_phone_source = primary.phone_source
        self.owner_phone_evidence = primary.phone_evidence
        self.owner_phone_confidence = primary.phone_confidence
        self.owner_phone_discrepancy = primary.phone_discrepancy
        self.owner_verification_status = primary.verification_status
        self.owner_email = primary.email

    @property
    def secondary_decision_makers_summary(self) -> str:
        if len(self.decision_makers) <= 1:
            return ""
        return "; ".join(f"{p.name} ({p.role})" for p in self.decision_makers[1:])

    @property
    def decision_maker_count(self) -> int:
        return len(self.decision_makers)

    def decision_makers_json(self) -> str:
        return json.dumps([p.to_dict() for p in self.decision_makers], ensure_ascii=False)

    def load_decision_makers_json(self, raw: str) -> None:
        if not raw:
            return
        try:
            people = [DecisionMaker.from_dict(d) for d in json.loads(raw)]
        except (json.JSONDecodeError, TypeError):
            return
        self.decision_makers = people

    def to_row(self, columns=COLUMNS) -> list:
        mapping = {
            "Business Name": self.business_name, "Niche": self.niche, "Sub-Niche": self.sub_niche,
            "City": self.city, "Neighborhood": self.neighborhood, "Address": self.address,
            "Google Maps": self.google_maps,
            "Owner Name": self.owner_name, "Owner Role": self.owner_role,
            "Owner Authority Level": self.owner_authority_level,
            "Owner Contact Role": self.owner_contact_role,
            "Owner Is Current": self.owner_is_current,
            "Owner Phone": self.owner_phone,
            "Owner Phone Source": self.owner_phone_source,
            "Owner Phone Evidence": self.owner_phone_evidence,
            "Owner Phone Confidence": self.owner_phone_confidence,
            "Owner Phone Discrepancy": self.owner_phone_discrepancy,
            "Owner Verification Status": self.owner_verification_status,
            "Owner LinkedIn": self.owner_linkedin,
            "Owner Instagram": self.owner_instagram,
            "Owner Email": self.owner_email,
            "Decision Makers JSON": self.decision_makers_json(),
            "Secondary Decision Makers": self.secondary_decision_makers_summary,
            "Decision Maker Count": self.decision_maker_count,
            "Business Phone": self.business_phone, "Business WhatsApp": self.business_whatsapp,
            "Business Email": self.business_email,
            "Website": self.website, "Website Status": self.website_status,
            "Website Problem": self.website_problem, "Website Evidence": self.website_evidence,
            "Instagram": self.instagram, "Facebook": self.facebook, "LinkedIn": self.linkedin,
            "High Ticket Score": self.high_ticket_score,
            "Website Opportunity Score": self.website_opportunity_score,
            "Data Quality Score": self.data_quality_score,
            "Lead Quality Score": self.lead_quality_score,
            "Contact Quality Score": self.contact_quality_score,
            "Lead Score": self.lead_score, "Lead Tier": self.lead_tier,
            "Qualification Status": self.qualification_status,
            "Research Date": self.research_date, "Sources": self.sources, "Notes": self.notes,
            "Angle": self.angle, "Cold Call Hook": self.cold_call_hook,
        }
        return [mapping.get(c, "") for c in columns]

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        key_map = {
            "Business Name": "business_name", "Niche": "niche", "Sub-Niche": "sub_niche", "City": "city",
            "Neighborhood": "neighborhood", "Address": "address", "Google Maps": "google_maps",
            "Owner Name": "owner_name", "Owner Role": "owner_role",
            "Owner Authority Level": "owner_authority_level", "Owner Contact Role": "owner_contact_role",
            "Owner Is Current": "owner_is_current",
            "Owner Phone": "owner_phone",
            "Owner Phone Source": "owner_phone_source",
            "Owner Phone Evidence": "owner_phone_evidence",
            "Owner Phone Confidence": "owner_phone_confidence",
            "Owner Phone Discrepancy": "owner_phone_discrepancy",
            "Owner Verification Status": "owner_verification_status",
            "Owner LinkedIn": "owner_linkedin",
            "Owner Instagram": "owner_instagram", "Owner Email": "owner_email",
            "Business Phone": "business_phone",
            "Business WhatsApp": "business_whatsapp", "Business Email": "business_email",
            "Website": "website", "Website Status": "website_status", "Website Problem": "website_problem",
            "Website Evidence": "website_evidence", "Instagram": "instagram", "Facebook": "facebook",
            "LinkedIn": "linkedin", "High Ticket Score": "high_ticket_score",
            "Website Opportunity Score": "website_opportunity_score",
            "Data Quality Score": "data_quality_score",
            "Lead Quality Score": "lead_quality_score", "Contact Quality Score": "contact_quality_score",
            "Lead Score": "lead_score", "Lead Tier": "lead_tier",
            "Qualification Status": "qualification_status", "Research Date": "research_date",
            "Sources": "sources", "Notes": "notes", "Angle": "angle",
            "Cold Call Hook": "cold_call_hook",
        }
        decision_makers_raw = d.get("Decision Makers JSON") or d.get("decision_makers_json")
        decision_makers_list = d.get("decision_makers")

        kwargs = {}
        valid_fields = {f.name for f in fields(cls)}
        for k, v in d.items():
            attr = key_map.get(k, k)
            if attr in valid_fields and attr != "decision_makers":
                kwargs[attr] = v
        if "owner_is_current" in kwargs and isinstance(kwargs["owner_is_current"], str):
            kwargs["owner_is_current"] = kwargs["owner_is_current"].strip().lower() not in (
                "false", "0", "no", ""
            )
        lead = cls(**kwargs)

        if decision_makers_list:
            people = [DecisionMaker.from_dict(p) if isinstance(p, dict) else p for p in decision_makers_list]
            lead.decision_makers = people
            if people and not lead.is_verified("owner_name"):
                lead.set_decision_makers(people)
        elif decision_makers_raw:
            lead.load_decision_makers_json(decision_makers_raw)
        elif lead.is_verified("owner_name"):
            lead.decision_makers = [DecisionMaker(
                name=lead.owner_name, role=lead.owner_role,
                authority_level=lead.owner_authority_level, contact_role=lead.owner_contact_role,
                is_current=lead.owner_is_current,
                phone=lead.owner_phone, phone_source=lead.owner_phone_source,
                phone_evidence=lead.owner_phone_evidence, phone_confidence=lead.owner_phone_confidence,
                phone_discrepancy=lead.owner_phone_discrepancy,
                email=lead.owner_email, verification_status=lead.owner_verification_status,
            )]
        return lead
