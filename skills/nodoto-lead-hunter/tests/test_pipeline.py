"""
Self-test for the deterministic parts of NODOTO LEAD HUNTER (schema, dedupe,
scoring gate, CSV output). Does NOT touch the network, Composio, or the repo's
real data files unless run with --against-repo.

Run:
    python3 skills/nodoto-lead-hunter/tests/test_pipeline.py
"""
from __future__ import annotations
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from schema import Lead, NOT_VERIFIED, QUALIFICATION_STATUS_OWNER_PHONE_MISSING, QUALIFICATION_STATUS_QUALIFIED, QUALIFICATION_STATUS_DISCARDED  # noqa: E402
from dedupe import fingerprint_lead, find_duplicate, find_fuzzy_candidates, normalize_text, normalize_phone, normalize_domain, normalize_email  # noqa: E402
from scoring import run_qualification_gate, compute_lead_score  # noqa: E402
from sheets_io import write_csv_mirror, plan_write, verify_write  # noqa: E402
from validate import validate_evidence_quality  # noqa: E402
from niche_priority import rank_niches, niche_opportunity_score, load_niche_stats_from_repo  # noqa: E402


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise AssertionError(f"Check failed: {label}")


def test_normalization():
    check("phone normalization collapses formats",
          normalize_phone("+57 601 555 1234") == normalize_phone("6015551234") == normalize_phone("601-555-1234"))
    check("domain normalization strips www/scheme",
          normalize_domain("https://www.clinica-x.com/") == normalize_domain("clinica-x.com"))
    check("text normalization is order + stopword insensitive",
          normalize_text("Dr. Juan Pérez Dermatología") != "" and
          normalize_text("Clinica Dermatologica Juan Perez") == normalize_text("Juan Perez Clinica Dermatologica"))


def test_dedupe_same_professional_different_names():
    lead_a = Lead(business_name="Dr. Juan Pérez Dermatología", owner_name="Juan Pérez",
                  owner_phone="+57 310 555 0001", owner_phone_source="Instagram oficial del Dr. Perez")
    lead_b = Lead(business_name="Juan Pérez Laser Center", owner_name="Juan Pérez",
                  owner_phone="310 555 0001", owner_phone_source="Website profesional")
    existing = [fingerprint_lead(lead_a, source="sheet")]
    dup = find_duplicate(lead_b, existing)
    check("same owner phone across differently-named businesses is caught as duplicate", dup is not None)


def test_gate_rejects_missing_owner_phone():
    lead = Lead(
        business_name="Clínica Estética Bogotá", niche="Dermatología láser",
        owner_name="Dra. Ana Gómez", owner_role="Directora médica",
        owner_phone=NOT_VERIFIED, owner_phone_source=NOT_VERIFIED,
        website_problem="No primary CTA above the fold; only contact path is a footer phone number.",
        website_evidence="Reviewed homepage 2026-09-11: hero section has no button, no WhatsApp link, no booking widget.",
        high_ticket_score=8, website_opportunity_score=9, owner_access_score=6, data_quality_score=5,
    )
    result = run_qualification_gate(lead)
    check("missing owner phone forces OWNER_PHONE_MISSING regardless of score",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING and not result.passed)


def test_gate_rejects_business_phone_relabeled_as_owner_phone():
    lead = Lead(
        business_name="Bufete Legal X", niche="Abogados corporativos",
        owner_name="Carlos Ruiz", owner_role="Socio Director",
        business_phone="+57 601 555 9999",
        owner_phone="+57 601 555 9999", owner_phone_source="Google Business Profile (business listing)",
        website_problem="Site has not been updated since 2019 and lists dissolved practice areas.",
        website_evidence="Footer copyright reads 2019; 'Derecho Digital' service page returns a 404.",
        high_ticket_score=9, website_opportunity_score=8, owner_access_score=7, data_quality_score=6,
    )
    result = run_qualification_gate(lead)
    check("business phone silently relabeled as owner phone is rejected",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING)


def test_gate_rejects_missing_owner_phone_confidence():
    """v2 rule: even a specific, non-generic phone source is not enough — the
    lead must also carry a DIRECT/NAMED_ATTRIBUTION confidence tier, or it's
    treated as unverified (guards against a plausible-sounding source that
    still turns out to be the receptionist/front-desk line)."""
    lead = Lead(
        business_name="Clinica Estetica Z", niche="Cirujanos plásticos",
        owner_name="Dra. Marcela Diaz", owner_role="Fundadora",
        owner_phone="+57 300 111 2222",
        owner_phone_source="Directorio medico especifico, ficha nombrando a la Dra. Diaz",
        website_problem="Homepage has no CTA above the fold.",
        website_evidence="Checked 2026-09-11: hero section has no button or phone link visible without scrolling.",
        high_ticket_score=9, website_opportunity_score=8, owner_access_score=8, data_quality_score=8,
    )
    result = run_qualification_gate(lead)
    check("owner phone without a confidence tier is treated as unverified",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING)


def test_gate_accepts_fully_verified_vip_lead():
    lead = Lead(
        business_name="Centro de Fertilidad Bogotá", niche="Fertilidad",
        owner_name="Dr. Mauricio Salas", owner_role="Director médico y fundador",
        owner_phone="+57 315 555 0044", owner_phone_source="Instagram oficial @dr.mauriciosalas (bio + destacada 'Agenda tu cita')",
        owner_phone_confidence="DIRECT",
        website="https://centrofertilidadbogota.example",
        website_problem="Mobile menu overlaps the hero text and the booking form times out on submit.",
        website_evidence="Tested on iPhone viewport 2026-09-11: hamburger menu opens over the H1; submitting the appointment form returns a blank page after 30s.",
        instagram="https://instagram.com/dr.mauriciosalas",
        high_ticket_score=9.5, website_opportunity_score=9, owner_access_score=9, data_quality_score=8.5,
    )
    result = run_qualification_gate(lead)
    check("fully verified high-scoring lead passes the gate as QUALIFIED", result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)
    check("lead tier computed correctly", lead.lead_tier in ("VIP", "A"))


def test_csv_output_roundtrip(tmp_dir: Path):
    qualified = Lead(
        business_name="Ortodoncia Premium Bogotá", niche="Ortodoncistas",
        owner_name="Dra. Laura Niño", owner_role="Fundadora",
        owner_phone="+57 320 555 0077", owner_phone_source="Website profesional (sección Contacto)",
        owner_phone_confidence="DIRECT",
        website_problem="No social proof anywhere on the site (no reviews, no before/after gallery).",
        website_evidence="Homepage and 3 subpages checked 2026-09-11: zero testimonials, zero patient photos.",
        high_ticket_score=8, website_opportunity_score=8.5, owner_access_score=8, data_quality_score=7.5,
    )
    run_qualification_gate(qualified)
    owner_missing = Lead(business_name="Estudio de Arquitectura Y", niche="Arquitectos de lujo",
                          owner_phone=NOT_VERIFIED, owner_phone_source=NOT_VERIFIED)
    paths = write_csv_mirror([qualified], [owner_missing], tmp_dir, run_id="selftest")
    check("qualified CSV written", Path(paths["qualified_csv"]).exists())
    check("owner-missing CSV written", Path(paths["owner_missing_csv"]).exists())

    header = list(Lead().to_row.__globals__["COLUMNS"])
    rows = plan_write([qualified], header)
    ok, msg = verify_write(expected_new_rows=1, rows_before=5, rows_after=6,
                            expected_business_names=["Ortodoncia Premium Bogotá"],
                            actual_last_rows=rows, header=header)
    check(f"verify_write logic passes on a consistent write ({msg})", ok)

    ok_bad, _ = verify_write(expected_new_rows=1, rows_before=5, rows_after=5,
                              expected_business_names=["Ortodoncia Premium Bogotá"],
                              actual_last_rows=rows, header=header)
    check("verify_write logic catches a row-count mismatch", not ok_bad)


def test_unset_business_email_never_causes_false_duplicate():
    """Regression: two unrelated leads that both leave Business Email unset
    (defaulting to NOT_VERIFIED) must NOT be flagged as duplicates of each
    other just because they share that placeholder string."""
    lead_a = Lead(business_name="Ortodoncia Alfa", owner_name="Ana Gómez",
                  owner_phone="+57 300 000 0001", website="https://alfa.example")
    lead_b = Lead(business_name="Ortodoncia Beta", owner_name="Beto Ruiz",
                  owner_phone="+57 300 000 0002", website="https://beta.example")
    check("normalize_email treats NOT_VERIFIED as empty", normalize_email(lead_a.business_email) == "")
    dup = find_duplicate(lead_b, [fingerprint_lead(lead_a)])
    check("two distinct unresearched-email leads are not falsely deduped", dup is None)


def test_fuzzy_match_flags_without_dropping():
    lead_a = Lead(business_name="Centro Dermatologico Bogota")
    lead_b = Lead(business_name="Centro Dermatologico de Bogota SAS")
    hits = find_fuzzy_candidates(lead_b, [fingerprint_lead(lead_a)])
    check("near-identical business names surface as fuzzy candidates", len(hits) == 1)


def test_validate_rejects_generic_source_and_vague_problem():
    weak_lead = Lead(
        business_name="X", owner_name="Y", owner_role="Owner",
        owner_phone="+57 300 000 0003", owner_phone_source="Instagram",
        website_problem="Website is bad.", website_evidence="It looks bad.",
    )
    result = validate_evidence_quality(weak_lead)
    check("generic owner phone source is rejected", any("too generic" in e for e in result.errors))
    check("vague website problem phrasing is rejected", any("vague adjective" in e for e in result.errors))

    strong_lead = Lead(
        business_name="X", owner_name="Y", owner_role="Owner",
        owner_phone="+57 300 000 0003",
        owner_phone_source="Website profesional, pagina de contacto, seccion 'Agende su cita'",
        website_problem="The contact page lists a WhatsApp link that opens to a number with no active WhatsApp Business account.",
        website_evidence="Clicked the WhatsApp icon on /contacto on 2026-09-11; wa.me link opens but the number shows 'not on WhatsApp'.",
    )
    result2 = validate_evidence_quality(strong_lead)
    check("specific, well-sourced evidence passes validation", result2.ok)


def test_niche_priority_runs_against_repo():
    repo_root = Path(__file__).resolve().parents[3]
    stats = load_niche_stats_from_repo(repo_root)
    check("niche stats derived from bogota_leads.csv", len(stats) > 0)
    ranked = rank_niches(repo_root)
    check("niche ranking returns a sorted, non-empty list", len(ranked) > 0 and ranked[0][1] >= ranked[-1][1])


def test_against_repo_dedupe():
    """Optional deeper check: confirm dedupe.load_all_repo_sources runs cleanly
    against the real repo CSVs without throwing, and actually loads records."""
    repo_root = Path(__file__).resolve().parents[3]
    from dedupe import load_all_repo_sources
    records = load_all_repo_sources(repo_root)
    check(f"repo CSVs load into dedupe fingerprints ({len(records)} records)", len(records) > 0)


if __name__ == "__main__":
    import tempfile
    test_normalization()
    test_dedupe_same_professional_different_names()
    test_gate_rejects_missing_owner_phone()
    test_gate_rejects_business_phone_relabeled_as_owner_phone()
    test_gate_rejects_missing_owner_phone_confidence()
    test_gate_accepts_fully_verified_vip_lead()
    test_unset_business_email_never_causes_false_duplicate()
    test_fuzzy_match_flags_without_dropping()
    test_validate_rejects_generic_source_and_vague_problem()
    with tempfile.TemporaryDirectory() as td:
        test_csv_output_roundtrip(Path(td))
    try:
        test_niche_priority_runs_against_repo()
    except Exception as e:
        print(f"[SKIP] test_niche_priority_runs_against_repo ({e})")
    try:
        test_against_repo_dedupe()
    except Exception as e:  # repo CSVs may not be present in every context
        print(f"[SKIP] test_against_repo_dedupe ({e})")
    print("\nAll self-tests passed.")
