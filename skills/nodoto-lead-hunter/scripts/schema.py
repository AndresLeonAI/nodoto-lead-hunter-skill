"""
NODOTO LEAD HUNTER — canonical column schema.

This is the single source of truth for the shape of a lead row, used by:
  - dedupe.py        (which fields to normalize/compare)
  - scoring.py        (which fields feed the qualification gate + score)
  - sheets_io.py       (what gets written to Google Sheets / CSV)

If the target Google Sheet already has a header row, sheets_io.map_to_existing_header()
reconciles this schema against it instead of forcing a new layout (Playbook rule #15:
"Adaptarse al Sheet existente").
"""

from __future__ import annotations
from dataclasses import dataclass, field, fields
from typing import Optional

# Column order for a brand-new sheet/CSV (only used when no sheet exists yet).
COLUMNS = [
    # BUSINESS
    "Business Name", "Niche", "Sub-Niche", "City", "Neighborhood", "Address", "Google Maps",
    # OWNER
    "Owner Name", "Owner Role", "Owner Phone", "Owner Phone Source", "Owner Phone Confidence",
    "Owner LinkedIn", "Owner Instagram",
    # BUSINESS CONTACT
    "Business Phone", "Business WhatsApp", "Business Email",
    # DIGITAL
    "Website", "Website Status", "Website Problem", "Website Evidence", "Instagram", "Facebook", "LinkedIn",
    # QUALIFICATION
    "High Ticket Score", "Website Opportunity Score", "Owner Access Score", "Data Quality Score",
    "Lead Score", "Lead Tier", "Qualification Status",
    # RESEARCH
    "Research Date", "Sources", "Notes", "Angle",
]

# Fields that MUST be present and non-placeholder for a lead to ever reach "Qualified Leads".
REQUIRED_FOR_QUALIFIED = [
    "Business Name", "Niche", "City",
    "Owner Name", "Owner Role", "Owner Phone", "Owner Phone Source", "Owner Phone Confidence",
    "Website Problem", "Website Evidence",
]

# Owner Phone Confidence must be one of these — see memory repo's
# docs/owner_phone_sources.md for the definitions. Anything else (including
# empty) means the number could not be tied specifically to the decision-maker
# and must stay NOT_VERIFIED rather than be accepted as an owner phone.
VALID_OWNER_PHONE_CONFIDENCE = {"DIRECT", "NAMED_ATTRIBUTION"}

NOT_VERIFIED = "NOT_VERIFIED"
NOT_VERIFIED_ALIASES = {"NOT_VERIFIED", "NO_VERIFIED", "N/A", "NA", "", "NONE", "UNKNOWN", "TBD"}

QUALIFICATION_STATUS_QUALIFIED = "QUALIFIED"
QUALIFICATION_STATUS_OWNER_PHONE_MISSING = "OWNER_PHONE_MISSING"
QUALIFICATION_STATUS_DISCARDED = "DISCARDED"
QUALIFICATION_STATUS_DUPLICATE = "DUPLICATE"

WORKSHEET_QUALIFIED = "Qualified Leads"
WORKSHEET_CANDIDATES_OWNER_MISSING = "Candidates - Owner Phone Missing"
WORKSHEET_RUN_LOG = "Run Log"


@dataclass
class Lead:
    """One candidate/lead row. Every field defaults to NOT_VERIFIED / '' so a partially
    researched candidate can be constructed incrementally without ever silently
    fabricating a value."""

    business_name: str = ""
    niche: str = ""
    sub_niche: str = ""
    city: str = "Bogotá"
    neighborhood: str = NOT_VERIFIED
    address: str = NOT_VERIFIED
    google_maps: str = NOT_VERIFIED

    owner_name: str = NOT_VERIFIED
    owner_role: str = NOT_VERIFIED
    owner_phone: str = NOT_VERIFIED
    owner_phone_source: str = NOT_VERIFIED
    owner_phone_confidence: str = NOT_VERIFIED  # "DIRECT" | "NAMED_ATTRIBUTION" | NOT_VERIFIED
    owner_linkedin: str = NOT_VERIFIED
    owner_instagram: str = NOT_VERIFIED

    business_phone: str = NOT_VERIFIED
    business_whatsapp: str = NOT_VERIFIED
    business_email: str = NOT_VERIFIED

    website: str = NOT_VERIFIED
    website_status: str = NOT_VERIFIED  # e.g. "no_website" | "live" | "down" | "under_construction"
    website_problem: str = NOT_VERIFIED  # one primary, verifiable observation (playbook rule #17)
    website_evidence: str = NOT_VERIFIED
    instagram: str = NOT_VERIFIED
    facebook: str = NOT_VERIFIED
    linkedin: str = NOT_VERIFIED

    high_ticket_score: Optional[float] = None
    website_opportunity_score: Optional[float] = None
    owner_access_score: Optional[float] = None
    data_quality_score: Optional[float] = None
    lead_score: Optional[float] = None
    lead_tier: str = ""
    qualification_status: str = ""

    research_date: str = ""
    sources: str = ""
    notes: str = ""
    angle: str = ""

    def is_verified(self, field_name: str) -> bool:
        val = getattr(self, field_name, "")
        return bool(val) and str(val).strip().upper() not in NOT_VERIFIED_ALIASES

    def to_row(self, columns=COLUMNS) -> list:
        mapping = {
            "Business Name": self.business_name, "Niche": self.niche, "Sub-Niche": self.sub_niche,
            "City": self.city, "Neighborhood": self.neighborhood, "Address": self.address,
            "Google Maps": self.google_maps,
            "Owner Name": self.owner_name, "Owner Role": self.owner_role, "Owner Phone": self.owner_phone,
            "Owner Phone Source": self.owner_phone_source,
            "Owner Phone Confidence": self.owner_phone_confidence,
            "Owner LinkedIn": self.owner_linkedin,
            "Owner Instagram": self.owner_instagram,
            "Business Phone": self.business_phone, "Business WhatsApp": self.business_whatsapp,
            "Business Email": self.business_email,
            "Website": self.website, "Website Status": self.website_status,
            "Website Problem": self.website_problem, "Website Evidence": self.website_evidence,
            "Instagram": self.instagram, "Facebook": self.facebook, "LinkedIn": self.linkedin,
            "High Ticket Score": self.high_ticket_score, "Website Opportunity Score": self.website_opportunity_score,
            "Owner Access Score": self.owner_access_score, "Data Quality Score": self.data_quality_score,
            "Lead Score": self.lead_score, "Lead Tier": self.lead_tier,
            "Qualification Status": self.qualification_status,
            "Research Date": self.research_date, "Sources": self.sources, "Notes": self.notes,
            "Angle": self.angle,
        }
        return [mapping.get(c, "") for c in columns]

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        key_map = {
            "Business Name": "business_name", "Niche": "niche", "Sub-Niche": "sub_niche", "City": "city",
            "Neighborhood": "neighborhood", "Address": "address", "Google Maps": "google_maps",
            "Owner Name": "owner_name", "Owner Role": "owner_role", "Owner Phone": "owner_phone",
            "Owner Phone Source": "owner_phone_source",
            "Owner Phone Confidence": "owner_phone_confidence",
            "Owner LinkedIn": "owner_linkedin",
            "Owner Instagram": "owner_instagram", "Business Phone": "business_phone",
            "Business WhatsApp": "business_whatsapp", "Business Email": "business_email",
            "Website": "website", "Website Status": "website_status", "Website Problem": "website_problem",
            "Website Evidence": "website_evidence", "Instagram": "instagram", "Facebook": "facebook",
            "LinkedIn": "linkedin", "High Ticket Score": "high_ticket_score",
            "Website Opportunity Score": "website_opportunity_score", "Owner Access Score": "owner_access_score",
            "Data Quality Score": "data_quality_score", "Lead Score": "lead_score", "Lead Tier": "lead_tier",
            "Qualification Status": "qualification_status", "Research Date": "research_date",
            "Sources": "sources", "Notes": "notes", "Angle": "angle",
        }
        kwargs = {}
        for k, v in d.items():
            attr = key_map.get(k, k)
            if attr in {f.name for f in fields(cls)}:
                kwargs[attr] = v
        return cls(**kwargs)
