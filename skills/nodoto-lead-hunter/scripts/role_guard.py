"""
NODOTO LEAD HUNTER — v4.0 "VAULT": contact-role cross-check.

Added 2026-09-15 in direct response to a critical failure the user reported:
the pipeline was delivering "Owner Phone" numbers that turned out to belong to
receptionists, secretaries, appointment/scheduling lines, call centers,
general customer-service WhatsApp, or generic business lines — never the
actual owner/decision-maker. See `docs/owner_phone_vault_v4.md` in the memory
repo for the full root-cause writeup and `schema.py`'s v4.0 docstring note for
the short version.

`schema.py` adds a mandatory `contact_role` classification (per decision-maker)
that a phone-evidence tier can never override. This module is the SECOND,
independent line of defense: even when a sub-agent correctly fills in
`contact_role` as some decision-maker role, this scans the free-text fields
that describe the phone (`Owner Role`, `Owner Phone Source`, `Owner Phone
Evidence`, `Owner Phone Discrepancy`) for bilingual signals that the number
actually belongs to reception, a secretary, scheduling, a call center,
general WhatsApp, or a generic business line — and rejects the lead if so,
regardless of what `contact_role` claims. A mis-tagged or overly generous
classification should never be trusted blindly; the evidence text itself is
cross-examined every time.

This is deliberately biased toward false negatives over false positives —
the user's own words: "Prefiero perder 10 leads antes que recibir 10 números
de recepción." A borderline case is a REJECTED case.
"""

from __future__ import annotations
import re
import unicodedata

from schema import DECISION_MAKER_CONTACT_ROLES

# Each entry: (category label, list of bilingual substrings to match against
# accent-stripped, lowercased text). Substrings are deliberately multi-word /
# specific — never a single generic word like "business" or "atencion" alone,
# which would false-positive on completely legitimate evidence text.
_NON_DECISION_MAKER_SIGNALS: list[tuple[str, list[str]]] = [
    ("RECEPTION", [
        "recepcion", "recepcionista", "receptionist", "front desk", "mostrador de entrada",
    ]),
    ("SECRETARY", [
        "secretaria", "secretario", "secretary", "asistente personal", "personal assistant",
        "executive assistant", "asistente ejecutiv",
    ]),
    ("SCHEDULING", [
        "agenda de citas", "linea de citas", "agendamiento general", "appointment line",
        "scheduling line", "booking line", "centro de citas", "linea de reservas",
        "encargada de agenda", "encargado de agenda",
    ]),
    ("CALL_CENTER", [
        "call center", "centro de llamadas", "conmutador", "central telefonica",
        "central de llamadas",
    ]),
    ("GENERAL_WHATSAPP", [
        "whatsapp de atencion", "whatsapp general", "whatsapp de atencion al cliente",
        "customer service whatsapp", "linea de whatsapp para clientes",
        "whatsapp business del negocio", "whatsapp corporativo",
    ]),
    ("BUSINESS_LINE", [
        "atencion al cliente", "customer service", "servicio al cliente",
        "linea de atencion", "informacion general", "general inquiries",
        "linea empresarial", "business line", "linea principal del negocio",
        "main line", "linea de la empresa", "pbx",
    ]),
]


def _strip_accents_lower(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    return normalized.lower()


def detect_non_decision_maker_signals(text: str) -> list[tuple[str, str]]:
    """Returns a list of (category, matched phrase) for every staff/generic
    signal found in `text`. Empty list means no signal found — NOT the same
    as confirmation the contact is a real decision-maker, just that this
    particular text didn't contradict it."""
    if not text:
        return []
    normalized = _strip_accents_lower(text)
    hits = []
    for category, phrases in _NON_DECISION_MAKER_SIGNALS:
        for phrase in phrases:
            if re.search(re.escape(phrase), normalized):
                hits.append((category, phrase))
    return hits


def role_contradicts_evidence(contact_role: str, *texts: str) -> list[str]:
    """The core v4.0 vault cross-check. If `contact_role` claims a
    decision-maker role, but any of `texts` (Owner Role, Owner Phone Source,
    Owner Phone Evidence, Owner Phone Discrepancy, ...) names a reception/
    secretary/scheduling/call-center/general-WhatsApp/business-line signal,
    returns one human-readable contradiction message per distinct category
    found. Returns [] when `contact_role` is not a decision-maker role in the
    first place — that case is rejected upstream by the "role not classified
    as decision-maker" check, not by this contradiction check, so this
    function only has something to say when a decision-maker tag needs to be
    second-guessed against its own supporting text."""
    role = (contact_role or "").strip().upper()
    if role not in DECISION_MAKER_CONTACT_ROLES:
        return []
    seen_categories: set[str] = set()
    messages: list[str] = []
    for text in texts:
        for category, phrase in detect_non_decision_maker_signals(text):
            if category in seen_categories:
                continue
            seen_categories.add(category)
            messages.append(
                f"Owner Contact Role is tagged '{role}' (decision-maker), but the evidence text "
                f"contains a {category} signal ('{phrase}') — vault rule v4.0 does not trust the tag "
                f"when the phone's own source/evidence describes it as a staff/generic line. Rejected."
            )
    return messages
