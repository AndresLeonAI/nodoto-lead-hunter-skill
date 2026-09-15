"""
Self-test for the deterministic parts of NODOTO LEAD HUNTER v3 (schema,
multi-decision-maker, dedupe, Lead Quality / Contact Quality scoring, gate,
CSV output, clean export). Does NOT touch the network or Composio.

Run:
    python3 skills/nodoto-lead-hunter/tests/test_pipeline.py
"""
from __future__ import annotations
import math
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from schema import (  # noqa: E402
    Lead, DecisionMaker, NOT_VERIFIED,
    QUALIFICATION_STATUS_OWNER_PHONE_MISSING, QUALIFICATION_STATUS_QUALIFIED,
    PHONE_CONFIDENCE_DIRECT, PHONE_CONFIDENCE_NAMED_ATTRIBUTION,
    PHONE_CONFIDENCE_VERIFIED_BUSINESS, PHONE_CONFIDENCE_GENERIC,
    VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_CONTRADICTED,
    AUTHORITY_FINAL, AUTHORITY_INFLUENCER,
)
from dedupe import (  # noqa: E402
    fingerprint_lead, find_duplicate, find_fuzzy_candidates, find_decision_maker_reuse,
    fingerprint_all_decision_makers, normalize_text, normalize_phone, normalize_domain, normalize_email,
)
from scoring import (  # noqa: E402
    run_qualification_gate, compute_lead_quality_score, compute_contact_quality_score,
    phone_format_is_plausible,
)
from sheets_io import write_csv_mirror, plan_write, verify_write  # noqa: E402
from validate import validate_evidence_quality  # noqa: E402
from report import (  # noqa: E402
    build_clean_export_table, build_clean_export_tables_by_niche,
    split_leads_by_niche, niche_slug, CLEAN_EXPORT_HEADERS,
)
from niche_priority import rank_niches, load_niche_stats_from_repo, estimate_raw_candidates_needed, NicheStats  # noqa: E402


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise AssertionError(f"Check failed: {label}")


# ---------------------------------------------------------------------------
# Helpers to build leads for the E2E scenarios below
# ---------------------------------------------------------------------------

def _base_kwargs(**overrides):
    kwargs = dict(
        business_name="Clinica Base", niche="Dermatologia laser", city="Bogotá",
        website="https://clinicabase.example",
        website_problem="Homepage has no primary CTA above the fold and the only contact path is a footer phone.",
        website_evidence="Checked 2026-09-11: hero section has no button, no WhatsApp link, no booking widget.",
        high_ticket_score=8, website_opportunity_score=8, data_quality_score=8,
    )
    kwargs.update(overrides)
    return kwargs


def _direct_person(name="Dra. Ana Gomez", role="Fundadora y Directora Medica", priority=1):
    return DecisionMaker(
        name=name, role=role, authority_level=AUTHORITY_FINAL, is_current=True,
        phone="+57 315 555 0044", phone_confidence=PHONE_CONFIDENCE_DIRECT,
        phone_source="Sitio web propio de la doctora, seccion 'Agenda tu cita'",
        phone_evidence="El boton de WhatsApp en dranagomez.com/contacto abre wa.me/573155550044, "
                       "el mismo numero aparece en su bio de Instagram personal @dra.anagomez.",
        verification_status=VERIFICATION_STATUS_VERIFIED, priority=priority,
    )


# ---------------------------------------------------------------------------
# E2E scenario 1: single decision-maker, DIRECT phone -> QUALIFIED
# ---------------------------------------------------------------------------

def test_e2e_single_decision_maker_qualifies():
    lead = Lead(**_base_kwargs(business_name="Clinica Un Decisor"))
    lead.set_decision_makers([_direct_person()])
    result = run_qualification_gate(lead)
    check("E2E-1 single decision-maker with DIRECT phone qualifies",
          result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)
    check("E2E-1 decision_maker_count is 1", lead.decision_maker_count == 1)
    check("E2E-1 lead_quality_score and contact_quality_score are both set",
          lead.lead_quality_score is not None and lead.contact_quality_score is not None)
    check("E2E-1 contact quality is high for a DIRECT, verified, evidenced phone",
          lead.contact_quality_score >= 8.0)


# ---------------------------------------------------------------------------
# E2E scenario 2: multiple decision-makers -> lead is NOT discarded, primary
# is prioritized, secondary is preserved (never silently dropped)
# ---------------------------------------------------------------------------

def test_e2e_multiple_decision_makers_preserved():
    primary = _direct_person(name="Carlos Ruiz", role="Socio Fundador", priority=1)
    secondary = DecisionMaker(
        name="Maria Torres", role="Socia Directora de Operaciones", authority_level=AUTHORITY_INFLUENCER,
        is_current=True, phone="+57 310 222 3344", phone_confidence=PHONE_CONFIDENCE_NAMED_ATTRIBUTION,
        phone_source="Perfil verificado en el directorio del Colegio de Abogados, ficha a su nombre",
        phone_evidence="El directorio del colegio profesional nombra a Maria Torres junto a este numero "
                       "como contacto de agendamiento; coincide con el numero en su LinkedIn personal.",
        verification_status=VERIFICATION_STATUS_VERIFIED, priority=2,
    )
    lead = Lead(**_base_kwargs(business_name="Bufete Multi Socio", niche="Abogados corporativos"))
    lead.set_decision_makers([primary, secondary])

    result = run_qualification_gate(lead)
    check("E2E-2 multi-decision-maker lead still qualifies via the prioritized primary",
          result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)
    check("E2E-2 decision_maker_count is 2 (secondary preserved, not dropped)", lead.decision_maker_count == 2)
    check("E2E-2 secondary decision-maker appears in the summary",
          "Maria Torres" in lead.secondary_decision_makers_summary)
    quality = validate_evidence_quality(lead)
    check("E2E-2 validator does not complain when the secondary IS recorded", quality.ok)

    # Regression: if a lead claims count > 1 but never actually records the
    # secondary, validate.py must catch that (the exact failure mode this
    # feature exists to prevent).
    broken = Lead(**_base_kwargs(business_name="Bufete Roto"))
    broken.decision_makers = [primary, secondary]
    broken.owner_name = primary.name  # simulate primary synced but summary lost
    object.__setattr__  # no-op just to keep linters quiet about unused import patterns
    broken.set_decision_makers([primary])  # this clears to 1 -> re-add second without going through setter
    broken.decision_makers.append(secondary)
    check("E2E-2b decision_maker_count reflects the real list length even if set oddly",
          broken.decision_maker_count == 2)


# ---------------------------------------------------------------------------
# E2E scenario 3: ONLY a general/business phone found -> never qualifies,
# and VERIFIED_BUSINESS must never be silently treated as an owner phone.
# ---------------------------------------------------------------------------

def test_e2e_generic_and_verified_business_phone_never_qualify():
    for confidence, label in [
        (PHONE_CONFIDENCE_GENERIC, "GENERIC (switchboard/WhatsApp Business menu)"),
        (PHONE_CONFIDENCE_VERIFIED_BUSINESS, "VERIFIED_BUSINESS (real but not the decision-maker's)"),
    ]:
        lead = Lead(**_base_kwargs(business_name=f"Negocio Solo Telefono General ({label})"))
        person = DecisionMaker(
            name="Gerente General", role="Gerente", authority_level=AUTHORITY_FINAL, is_current=True,
            phone="+57 601 555 1234", phone_confidence=confidence,
            phone_source="Ficha de Google Maps del negocio",
            phone_evidence="Numero listado como telefono principal en la ficha de Google Business.",
        )
        lead.set_decision_makers([person])
        result = run_qualification_gate(lead)
        check(f"E2E-3 {label} phone alone is rejected, never treated as an owner phone",
              result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING and not result.passed)


# ---------------------------------------------------------------------------
# E2E scenario 4: NAMED_ATTRIBUTION via a public registry -> qualifies
# ---------------------------------------------------------------------------

def test_e2e_named_attribution_qualifies():
    lead = Lead(**_base_kwargs(business_name="Consultorio Registro Publico"))
    person = DecisionMaker(
        name="Dr. Julian Vega", role="Odontologo titular", authority_level=AUTHORITY_FINAL, is_current=True,
        phone="+57 320 444 5566", phone_confidence=PHONE_CONFIDENCE_NAMED_ATTRIBUTION,
        phone_source="Perfil de Doctoralia a su nombre, seccion 'Agendar cita'",
        phone_evidence="El perfil de Doctoralia verificado con su nombre completo y matricula profesional "
                       "publica este numero como su linea directa de agendamiento.",
        verification_status=VERIFICATION_STATUS_VERIFIED,
    )
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("E2E-4 NAMED_ATTRIBUTION from a public professional directory qualifies",
          result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)


# ---------------------------------------------------------------------------
# E2E scenario 5: contradictory information across sources -> never silently
# resolved, and never qualifies while unresolved.
# ---------------------------------------------------------------------------

def test_e2e_contradictory_sources_blocks_qualification():
    lead = Lead(**_base_kwargs(business_name="Clinica Contradictoria"))
    person = DecisionMaker(
        name="Dra. Paola Rios", role="Fundadora", authority_level=AUTHORITY_FINAL, is_current=True,
        phone="+57 300 111 2222", phone_confidence=PHONE_CONFIDENCE_DIRECT,
        phone_source="Sitio web propio",
        phone_evidence="El sitio propio muestra este numero, pero Instagram personal muestra un numero "
                       "distinto (+57 300 999 8888) para la misma doctora.",
        phone_discrepancy="Sitio web dice +57 300 111 2222; Instagram personal (mas reciente, actualizado "
                           "hace 2 semanas) dice +57 300 999 8888. No se pudo confirmar cual es el actual.",
        verification_status=VERIFICATION_STATUS_CONTRADICTED,
    )
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("E2E-5 CONTRADICTED verification status blocks qualification even with DIRECT confidence",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING and not result.passed)


# ---------------------------------------------------------------------------
# E2E scenario 6: no website -> does not disqualify; opportunity score is
# still built from concrete, checkable evidence about the ABSENCE.
# ---------------------------------------------------------------------------

def test_e2e_no_website_still_qualifies_with_evidence():
    lead = Lead(**_base_kwargs(
        business_name="Consultorio Sin Web",
        website=NOT_VERIFIED,
        website_problem="No existe sitio propio; la unica presencia digital es una pagina de Facebook "
                         "sin publicaciones desde hace 8 meses y sin boton de contacto directo.",
        website_evidence="Revisado 2026-09-11: busqueda del nombre del negocio + 'Bogota' no arroja sitio "
                          "propio; la pagina de Facebook 'Consultorio Sin Web' tiene ultima publicacion "
                          "en enero 2026 y el boton de 'Enviar mensaje' no esta configurado.",
    ))
    lead.website_status = "no_website"
    lead.set_decision_makers([_direct_person(name="Dr. Felipe Soto", role="Titular")])
    result = run_qualification_gate(lead)
    check("E2E-6 missing website does not block qualification",
          result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)


# ---------------------------------------------------------------------------
# E2E scenario 7: multiple locations -> scoring still runs correctly and the
# decision-maker check is unaffected by business size/structure.
# ---------------------------------------------------------------------------

def test_e2e_multi_location_business():
    lead = Lead(**_base_kwargs(
        business_name="Cadena Multi Sede",
        notes="Cadena con 4 sedes en Bogota (Chapinero, Usaquen, Salitre, Kennedy).",
        high_ticket_score=9, website_opportunity_score=7, data_quality_score=8,
    ))
    lead.set_decision_makers([_direct_person(name="Andres Molina", role="Fundador y CEO")])
    result = run_qualification_gate(lead)
    check("E2E-7 multi-location business qualifies normally on its own merits",
          result.passed and result.status == QUALIFICATION_STATUS_QUALIFIED)
    check("E2E-7 lead_quality_score reflects the (higher) business signals independent of contact",
          lead.lead_quality_score >= 8.0)


# ---------------------------------------------------------------------------
# E2E scenario 8: founder no longer looks like the decision-maker (sold,
# retired, left) -> must NOT qualify even with an otherwise perfect phone.
# ---------------------------------------------------------------------------

def test_e2e_former_founder_is_rejected():
    lead = Lead(**_base_kwargs(business_name="Clinica Fundador Retirado"))
    person = _direct_person(name="Dr. Ricardo Nunez", role="Fundador (retirado en 2024)")
    person.is_current = False
    person.notes = "Un articulo de prensa de 2024 confirma que vendio la clinica y ya no la dirige."
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("E2E-8 a founder confirmed no longer in charge is rejected even with a DIRECT phone",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING and not result.passed)
    check("E2E-8 contact_quality_score is capped low for a non-current decision-maker",
          compute_contact_quality_score(lead) <= 1.0)


# ---------------------------------------------------------------------------
# Anti-hallucination: garbled/implausible phone formats are rejected even if
# everything else about the lead looks perfect.
# ---------------------------------------------------------------------------

def test_phone_format_sanity_check():
    check("plausible Colombian mobile passes", phone_format_is_plausible("+57 315 555 0044"))
    check("too-short garbled number is rejected", not phone_format_is_plausible("+57 55"))
    check("too-long garbled number is rejected", not phone_format_is_plausible("123456789012345"))

    lead = Lead(**_base_kwargs(business_name="Numero Invalido"))
    person = _direct_person()
    person.phone = "12"  # obviously broken
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("a DIRECT-confidence lead with an implausible phone format is still rejected",
          not result.passed)


def test_invalid_confidence_enum_is_rejected():
    lead = Lead(**_base_kwargs(business_name="Confidence Inventada"))
    person = _direct_person()
    person.phone_confidence = "TOTALLY_SURE"  # invented value, not a real tier
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("an invented confidence value is rejected outright rather than silently accepted",
          not result.passed)


# ---------------------------------------------------------------------------
# Decision-maker reuse across leads (flag, never silent auto-drop)
# ---------------------------------------------------------------------------

def test_decision_maker_reuse_is_flagged_not_dropped():
    existing_lead = Lead(**_base_kwargs(business_name="Firma Original"))
    existing_lead.set_decision_makers([_direct_person(name="Sofia Lara", role="Socia")])
    existing_records = fingerprint_all_decision_makers(existing_lead, source="bogota_leads.csv")

    new_lead = Lead(**_base_kwargs(business_name="Consultorio Propio de Sofia"))
    new_lead.set_decision_makers([_direct_person(name="Sofia Lara", role="Titular")])

    hits = find_decision_maker_reuse(new_lead, existing_records)
    check("the same person surfacing as decision-maker on a second business is flagged",
          len(hits) == 1)
    result = run_qualification_gate(new_lead)
    check("a reuse flag does not by itself block qualification (it's a review flag, not a rejection)",
          result.passed)


# ---------------------------------------------------------------------------
# Existing (v1/v2) regression coverage, kept intact
# ---------------------------------------------------------------------------

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
    lead = Lead(**_base_kwargs(business_name="Clinica Sin Telefono"))
    result = run_qualification_gate(lead)
    check("missing owner phone forces OWNER_PHONE_MISSING regardless of score",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING and not result.passed)


def test_gate_rejects_business_phone_relabeled_as_owner_phone():
    lead = Lead(**_base_kwargs(business_name="Bufete Legal X", niche="Abogados corporativos"))
    lead.business_phone = "+57 601 555 9999"
    person = DecisionMaker(
        name="Carlos Ruiz", role="Socio Director", authority_level=AUTHORITY_FINAL, is_current=True,
        phone="+57 601 555 9999", phone_confidence=PHONE_CONFIDENCE_DIRECT,
        phone_source="Google Business Profile (business listing)",
        phone_evidence="Mismo numero que aparece en la ficha de Google del negocio.",
    )
    lead.set_decision_makers([person])
    result = run_qualification_gate(lead)
    check("business phone relabeled as owner phone (no 'owner' in source) is rejected",
          result.status == QUALIFICATION_STATUS_OWNER_PHONE_MISSING)


def test_csv_output_roundtrip(tmp_dir: Path):
    qualified = Lead(**_base_kwargs(business_name="Ortodoncia Premium Bogotá", niche="Ortodoncistas"))
    qualified.set_decision_makers([_direct_person(name="Dra. Laura Niño", role="Fundadora")])
    run_qualification_gate(qualified)
    owner_missing = Lead(business_name="Estudio de Arquitectura Y", niche="Arquitectos de lujo")
    paths = write_csv_mirror([qualified], [owner_missing], tmp_dir, run_id="selftest")
    check("qualified CSV written", Path(paths["qualified_csv"]).exists())
    check("owner-missing CSV written", Path(paths["owner_missing_csv"]).exists())

    from schema import COLUMNS
    header = list(COLUMNS)
    rows = plan_write([qualified], header)
    ok, msg = verify_write(expected_new_rows=1, rows_before=5, rows_after=6,
                            expected_business_names=["Ortodoncia Premium Bogotá"],
                            actual_last_rows=rows, header=header)
    check(f"verify_write logic passes on a consistent write ({msg})", ok)

    ok_bad, _ = verify_write(expected_new_rows=1, rows_before=5, rows_after=5,
                              expected_business_names=["Ortodoncia Premium Bogotá"],
                              actual_last_rows=rows, header=header)
    check("verify_write logic catches a row-count mismatch", not ok_bad)

    exported = build_clean_export_table([qualified])
    check("clean export table has exactly one row per qualified lead", len(exported) == 1)
    check("clean export row answers 'who to contact' and 'how' directly",
          exported[0]["Decisor principal"] != "NOT FOUND" and exported[0]["Teléfono decisor"] != "NOT FOUND")


def test_unset_business_email_never_causes_false_duplicate():
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
        owner_phone_evidence="El boton de WhatsApp de esa pagina abre wa.me con este mismo numero.",
        website_problem="The contact page lists a WhatsApp link that opens to a number with no active WhatsApp Business account.",
        website_evidence="Clicked the WhatsApp icon on /contacto on 2026-09-11; wa.me link opens but the number shows 'not on WhatsApp'.",
    )
    result2 = validate_evidence_quality(strong_lead)
    check("specific, well-sourced evidence passes validation", result2.ok)


def test_niche_priority_runs_against_new_schema_csv(tmp_dir: Path):
    """Regression for the audit-found bug: load_niche_stats_from_repo used to
    expect a different, older CSV header ('Industry/Niche') than what this
    skill actually writes ('Niche'), so owner stats silently stayed at 0
    forever. Build a tiny repo fixture in the NEW schema and confirm stats
    are derived correctly from it."""
    data_dir = tmp_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    lead = Lead(**_base_kwargs(business_name="Fixture Clinic", niche="Dermatologia laser"))
    lead.set_decision_makers([_direct_person()])
    run_qualification_gate(lead)
    write_csv_mirror([lead], [], data_dir, run_id="fixture")
    import shutil
    shutil.move(str(data_dir / "qualified_leads_fixture.csv"), str(data_dir / "bogota_leads.csv"))

    stats = load_niche_stats_from_repo(tmp_dir)
    check("niche stats are derived from the new-schema bogota_leads.csv", len(stats) > 0)
    key = next(iter(stats))
    check("owner_identified_count reads real data instead of silently staying 0",
          stats[key].owner_identified_count == 1)
    check("owner_phone_count reads real data instead of silently staying 0",
          stats[key].owner_phone_count == 1)

    ranked = rank_niches(tmp_dir)
    check("niche ranking returns a sorted, non-empty list", len(ranked) > 0 and ranked[0][1] >= ranked[-1][1])


def test_cli_run_entrypoint_end_to_end(tmp_dir: Path):
    """Regression for TWO real bugs the unit tests above never caught because
    they call dedupe.py/report.py functions directly with correct arguments —
    only actually invoking `cli.py run` (as the daily automation does)
    exercised the wiring between them:
      1. cmd_run called load_bogota_leads_decision_makers(repo_root) — the
         directory — instead of repo_root/data/bogota_leads.csv, so it
         crashed with IsADirectoryError on any real repo.
      2. cmd_run called RunStats.from_qualified(qualified, qualified=len(...))
         — a positional arg literally named the same as a kwarg — so it
         crashed with 'multiple values for argument' on any run that reached
         that line (i.e. every run, always).
    Both were only caught by running the actual CLI against a real
    repo-shaped directory, per the audit directive's 'no declares producción
    sin verificarla'. This test runs cli.py as a subprocess end-to-end
    against a fixture repo containing one already-known lead, and asserts:
    the known lead dedupes correctly, a receptionist/GENERIC phone is
    rejected from Qualified, and a multi-decision-maker candidate qualifies
    on its primary while keeping the secondary."""
    import json
    import subprocess

    repo_root = tmp_dir / "repo"
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    known = Lead(**_base_kwargs(business_name="Doctora Llanos Clínica de Piel", niche="Dermatologia laser"))
    known.set_decision_makers([_direct_person(name="Lina María Llanos")])
    run_qualification_gate(known)
    write_csv_mirror([known], [], data_dir, run_id="seed")
    import shutil
    shutil.move(str(data_dir / "qualified_leads_seed.csv"), str(data_dir / "bogota_leads.csv"))
    (data_dir / "known_bad_contacts.csv").write_text("domain,email\n", encoding="utf-8")
    (data_dir / "sent_tracking.csv").write_text("recipient_email\n", encoding="utf-8")

    candidates = [
        {  # exact duplicate of the seeded lead -> must be skipped, not re-qualified
            "business_name": "Doctora Llanos Clínica de Piel", "niche": "Dermatologia laser",
            "owner_name": "Lina María Llanos", "owner_phone": "+573108633793",
            "owner_phone_source": "s", "owner_phone_evidence": "e", "owner_phone_confidence": "DIRECT",
            "website_problem": "p", "website_evidence": "e",
            "high_ticket_score": 8, "website_opportunity_score": 6, "data_quality_score": 8,
        },
        {  # receptionist/switchboard GENERIC phone -> must NOT reach Qualified
            "business_name": "Estetica Generica SAS", "niche": "Dermatologia laser",
            "owner_name": "Recepcion", "owner_phone": "+576015550199",
            "owner_phone_source": "conmutador general", "owner_phone_evidence": "linea unica de agendamiento",
            "owner_phone_confidence": "GENERIC",
            "website_problem": "p", "website_evidence": "e",
            "high_ticket_score": 7, "website_opportunity_score": 8, "data_quality_score": 6,
        },
        {  # multi-decision-maker candidate -> must qualify on primary, keep secondary
            "business_name": "Centro Odontologico Sonrisa Real", "niche": "Implantes dentales",
            "decision_makers": [
                {"name": "Dr. Andres Forero", "role": "Socio fundador", "authority_level": "FINAL",
                 "is_current": True, "phone": "+573154028871", "phone_confidence": "DIRECT",
                 "phone_source": "Doctoralia", "phone_evidence": "wa.me enlazado a su perfil",
                 "verification_status": "VERIFIED", "priority": 1},
                {"name": "Dra. Marcela Uribe", "role": "Socia administrativa", "priority": 2},
            ],
            "website_problem": "p", "website_evidence": "e",
            "high_ticket_score": 8.5, "website_opportunity_score": 7, "data_quality_score": 8.5,
        },
    ]
    candidates_path = tmp_dir / "candidates.json"
    candidates_path.write_text(json.dumps(candidates), encoding="utf-8")
    out_dir = tmp_dir / "out"
    cli_path = SCRIPTS_DIR / "cli.py"

    result = subprocess.run(
        [sys.executable, str(cli_path), "run", str(candidates_path),
         "--repo-root", str(repo_root), "--niche", "test", "--out-dir", str(out_dir)],
        capture_output=True, text=True,
    )
    check("cli.py run exits 0 against a real repo-shaped directory (not a crash)",
          result.returncode == 0)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)

    qualified_csvs = list(out_dir.glob("qualified_leads_*.csv"))
    check("a qualified CSV was written", len(qualified_csvs) == 1)
    import csv as _csv
    with open(qualified_csvs[0], newline="", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    names = {r["Business Name"] for r in rows}
    check("the exact duplicate of an already-known lead is NOT re-qualified",
          "Doctora Llanos Clínica de Piel" not in names)
    check("a receptionist/GENERIC-phone-only business never reaches Qualified",
          "Estetica Generica SAS" not in names)
    check("the multi-decision-maker business qualifies on its primary",
          "Centro Odontologico Sonrisa Real" in names)
    sonrisa = next(r for r in rows if r["Business Name"] == "Centro Odontologico Sonrisa Real")
    check("its qualified row keeps the secondary decision-maker, not just the primary",
          "Marcela Uribe" in sonrisa["Secondary Decision Makers"])
    check("'Doctora Llanos' duplicate is reported on stdout/stderr",
          "Doctora Llanos" in (result.stdout + result.stderr))


def test_estimate_raw_candidates_needed_sizes_the_funnel():
    """v3.1 efficiency addition: a niche with a strong historical owner-access
    rate should need far fewer raw candidates than one with a weak rate or no
    history at all, and the estimate must never fall below the universal 2x
    attrition floor or exceed the 12x ceiling (past which SKILL.md says to
    split across more niches instead of over-mining one)."""
    easy = NicheStats(niche="facil", existing_leads=20, owner_phone_count=16)  # 80% access rate
    hard = NicheStats(niche="dificil", existing_leads=20, owner_phone_count=2)  # 10% access rate
    unseen = NicheStats(niche="nueva", existing_leads=0, owner_phone_count=0)

    n_easy = estimate_raw_candidates_needed("facil", {"facil": easy}, target_qualified=10)
    n_hard = estimate_raw_candidates_needed("dificil", {"dificil": hard}, target_qualified=10)
    n_unseen = estimate_raw_candidates_needed("nueva", {"nueva": unseen}, target_qualified=10)

    check("an easy niche needs fewer raw candidates than a hard one", n_easy < n_hard)
    check("an easy niche still respects the 2x attrition floor", n_easy >= 20)
    check("a hard niche is capped at 12x rather than exploding unboundedly", n_hard <= 120)
    check("an unseen niche falls back to the conservative default rate, not zero/None",
          n_unseen == math.ceil(10 / 0.12))


def test_v3_2_clean_export_never_mixes_niches_and_has_a_cold_call_hook():
    """v3.2 (user directive, 2026-09-15): one clean export / one .xlsx per
    niche, never mixed — and every qualified row carries a spoken, second-
    person cold-call line, whether an agent wrote one explicitly or the
    fallback derived it from the same verified website_problem/evidence."""
    derma = Lead(
        business_name="Clinica Derma X", niche="Dermatólogos de tratamientos láser",
        owner_name="Dra. X", owner_role="Fundadora",
        owner_phone="+57 300 0000000", owner_phone_source="sitio propio",
        owner_phone_evidence="wa.me publicado en su sitio personal",
        owner_phone_confidence=PHONE_CONFIDENCE_DIRECT,
        owner_verification_status=VERIFICATION_STATUS_VERIFIED,
        website="https://dermax.example", website_status="LIVE",
        website_problem="el formulario de contacto no envia confirmacion",
        website_evidence="se probo el formulario y no llego ningun correo",
        high_ticket_score=8, website_opportunity_score=7, data_quality_score=7,
    )
    abogado = Lead(
        business_name="Bufete Y", niche="Abogados corporativos",
        owner_name="Dr. Y", owner_role="Socio Fundador",
        owner_phone="+57 300 1111111", owner_phone_source="LinkedIn personal",
        owner_phone_evidence="wa.me enlazado desde su perfil personal de LinkedIn",
        owner_phone_confidence=PHONE_CONFIDENCE_NAMED_ATTRIBUTION,
        owner_verification_status=VERIFICATION_STATUS_VERIFIED,
        website="https://bufeteY.example", website_status="LIVE",
        website_problem="el sitio corre en HTTP plano sin certificado SSL",
        website_evidence="el navegador marca la pagina como no segura",
        high_ticket_score=7, website_opportunity_score=8, data_quality_score=6,
        cold_call_hook="Cuando entre a su sitio el navegador me marco 'no seguro' porque no tiene HTTPS. ¿15 minutos esta semana?",
    )
    groups = split_leads_by_niche([derma, abogado])
    check("split_leads_by_niche produces exactly 2 groups for 2 distinct niches",
          set(groups.keys()) == {"Dermatólogos de tratamientos láser", "Abogados corporativos"})
    check("each niche group contains only its own leads",
          groups["Dermatólogos de tratamientos láser"] == [derma] and groups["Abogados corporativos"] == [abogado])

    by_niche = build_clean_export_tables_by_niche([derma, abogado])
    check("build_clean_export_tables_by_niche returns one table per niche, never combined",
          len(by_niche) == 2 and all(len(rows) == 1 for rows in by_niche.values()))
    check("CLEAN_EXPORT_HEADERS names the website-URL and cold-call-script columns explicitly",
          "Sitio Web (URL)" in CLEAN_EXPORT_HEADERS and "Qué decirle en la llamada" in CLEAN_EXPORT_HEADERS)

    derma_row = by_niche["Dermatólogos de tratamientos láser"][0]
    check("row for a lead without an explicit cold_call_hook gets a derived one, not N/A",
          derma_row["Qué decirle en la llamada"] and "N/A" not in derma_row["Qué decirle en la llamada"])
    check("the derived hook is spoken/second-person, not the raw technical sentence verbatim",
          derma_row["Qué decirle en la llamada"] != derma.website_problem
          and "15 minutos" in derma_row["Qué decirle en la llamada"])
    check("the website URL column carries the actual current site, not a placeholder",
          derma_row["Sitio Web (URL)"] == "https://dermax.example")

    abogado_row = by_niche["Abogados corporativos"][0]
    check("row for a lead WITH an explicit cold_call_hook uses it verbatim rather than the fallback",
          abogado_row["Qué decirle en la llamada"] == abogado.cold_call_hook)

    no_site = Lead(business_name="Sin Sitio Z", niche="Abogados corporativos",
                    owner_name="Dr. Z", owner_phone_confidence=PHONE_CONFIDENCE_DIRECT,
                    website_status="no_website")
    no_site_row = build_clean_export_table([no_site])[0]
    check("a lead with no website gets an explicit N/A hook, never a fabricated one",
          "N/A" in no_site_row["Qué decirle en la llamada"])
    check("niche_slug produces a stable, filesystem-safe name for filenames",
          niche_slug("Dermatólogos de tratamientos láser") == "dermatologos_de_tratamientos_laser")


if __name__ == "__main__":
    import tempfile

    # E2E scenarios (the 8 required by the audit directive)
    test_e2e_single_decision_maker_qualifies()
    test_e2e_multiple_decision_makers_preserved()
    test_e2e_generic_and_verified_business_phone_never_qualify()
    test_e2e_named_attribution_qualifies()
    test_e2e_contradictory_sources_blocks_qualification()
    test_e2e_no_website_still_qualifies_with_evidence()
    test_e2e_multi_location_business()
    test_e2e_former_founder_is_rejected()

    # Anti-hallucination + reuse
    test_phone_format_sanity_check()
    test_invalid_confidence_enum_is_rejected()
    test_decision_maker_reuse_is_flagged_not_dropped()

    # Regression coverage
    test_normalization()
    test_dedupe_same_professional_different_names()
    test_gate_rejects_missing_owner_phone()
    test_gate_rejects_business_phone_relabeled_as_owner_phone()
    test_unset_business_email_never_causes_false_duplicate()
    test_fuzzy_match_flags_without_dropping()
    test_validate_rejects_generic_source_and_vague_problem()
    test_estimate_raw_candidates_needed_sizes_the_funnel()

    with tempfile.TemporaryDirectory() as td:
        test_csv_output_roundtrip(Path(td))
    with tempfile.TemporaryDirectory() as td2:
        test_niche_priority_runs_against_new_schema_csv(Path(td2))
    with tempfile.TemporaryDirectory() as td3:
        test_cli_run_entrypoint_end_to_end(Path(td3))

    test_v3_2_clean_export_never_mixes_niches_and_has_a_cold_call_hook()

    print("\nAll self-tests passed (v3.2: multi-decision-maker + 5-tier confidence + Lead/Contact Quality split "
          "+ per-niche clean export + cold-call hook).")
