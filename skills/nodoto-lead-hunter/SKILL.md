---
name: nodoto-lead-hunter
description: High-ticket sales opportunity engine for NODOTO AGENCY. Discovers Bogotá businesses in one niche at a time with weak digital presence, identifies EVERY plausible decision-maker (not just one), verifies the DECISION-MAKER'S OWN phone (never the receptionist's) at one of 5 confidence tiers, audits the real website, scores Lead Quality and Contact Quality separately, dedupes against persistent GitHub memory, and writes only fully-qualified leads to CSV/Sheets. Use when asked to find leads, prospect, hunt for clients, or run lead generation for NODOTO.
---

> ## ACTUALIZACIÓN v3 (2026-09-11) — leer esto primero
>
> Esta skill fue auditada de forma adversarial (buscando activamente números de
> recepcionista mal etiquetados como del dueño, decisores desactualizados,
> negocios con varios socios tratados como si solo tuvieran uno, y alucinación
> de datos) y reescrita para cerrar cada hueco encontrado. Lo que sigue debajo
> de esta nota es la v2 original y sigue siendo válido en su mayoría (fuentes
> públicas legítimas, principio de "nunca inventar"), pero estas reglas v3 lo
> **reemplazan** donde haya conflicto:
>
> 1. **Nunca asumas un solo decisor.** Toda investigación debe intentar
>    encontrar TODOS los decisores plausibles (socios, codirectores, gerente
>    administrativo con poder de compra) y registrarlos en
>    `decision_makers` (lista completa, ordenada por prioridad). El primero
>    (`priority=1`) es el que se prioriza para contacto — los demás NUNCA se
>    descartan, quedan en `Secondary Decision Makers`.
> 2. **Confianza del teléfono: 5 niveles, no 2** — `schema.py`:
>    `DIRECT` (el propio decisor lo publica) · `NAMED_ATTRIBUTION` (fuente
>    pública nombra explícitamente a esa persona con ese número — directorio
>    profesional, prensa, Doctoralia) · `VERIFIED_BUSINESS` (número real y
>    correcto del NEGOCIO, pero explícitamente NO del decisor — nunca lo
>    tratable como owner phone) · `GENERIC` (conmutador/recepción/menú de
>    WhatsApp Business) · `UNKNOWN` (no encontrado). Solo `DIRECT` y
>    `NAMED_ATTRIBUTION` pueden calificar un lead.
> 3. **Pipeline de descubrimiento, en este orden exacto — nunca puntuar antes
>    de tener el contacto:**
>    `DESCUBRIR → IDENTIFICAR NEGOCIO → IDENTIFICAR DECISORES → PRIORIZAR
>    DECISOR → BUSCAR TELÉFONO → VERIFICAR → CROSS-CHECK → SCORE →
>    DEDUPLICAR → MEMORIA → EXPORTAR`.
> 4. **Verificación de cada teléfono candidato:** identificar la persona →
>    su rol/autoridad → el número → probar el vínculo persona↔número con
>    evidencia citable → cross-check contra otra fuente si es posible →
>    registrar la evidencia en `phone_evidence` → asignar el tier de
>    confianza. Si dos fuentes se contradicen, NUNCA elegir arbitrariamente:
>    compara autoridad/antigüedad de cada fuente, registra el desacuerdo en
>    `phone_discrepancy`, y usa `verification_status=CONTRADICTED` — eso
>    bloquea la calificación hasta resolverlo, no importa qué tan alta sea
>    la confianza declarada.
> 5. **Un decisor que ya no es el decisor** (vendió, se retiró, ya no
>    aparece activo) se marca `is_current=False` — bloquea la calificación
>    aunque su teléfono sea DIRECT y esté perfectamente verificado.
> 6. **Lead Quality ≠ Contact Quality.** Lead Quality = qué tan buen negocio
>    es esta oportunidad (ticket, necesidad, gap digital) — nunca usa
>    señales de contacto. Contact Quality = qué tan alcanzable es el decisor
>    real — un teléfono GENERIC nunca puede puntuar igual que uno DIRECT
>    verificado, sin importar cuán bueno sea el negocio. Ver `scoring.py`.
> 7. **Fuentes públicas legítimas únicamente** (ampliando la lista v2 de
>    abajo): sitio oficial, perfil profesional propio, Instagram/Facebook/
>    LinkedIn PERSONAL (no solo la página del negocio), WhatsApp/wa.me
>    publicado públicamente, RUES/Cámara de Comercio de Bogotá (representante
>    legal), RETHUS/Tribunal Nacional de Ética Médica y colegios
>    profesionales (abogados, contadores), Doctoralia, prensa/entrevistas/
>    podcasts/eventos públicos. **Nunca** datos privados, comprados, o
>    inferidos/adivinados.
> 8. **Formato de salida limpio** (una fila = respuesta completa): `Empresa |
>    Decisor principal | Otros decisores | Teléfono decisor | Confidence |
>    Sitio Web (URL) | Qué decirle en la llamada | Redes | Ángulo | Notas` —
>    generado automáticamente por `report.build_clean_export_table()`, nunca a
>    mano. **v3.2: siempre un archivo por nicho** — ver
>    `build_clean_export_tables_by_niche()` — y la columna "Qué decirle en la
>    llamada" es el gancho de llamada en frío (`cold_call_hook`), no el
>    hallazgo técnico crudo — ver `references/cold_call_style_guide.md`.
> 9. **Meta operativa: 30-50 leads extremadamente calificados/día — pero
>    calidad sobre cantidad.** Si un día solo hay 12 que de verdad califican,
>    se entregan 12. Nunca se rellena con leads débiles ni teléfonos
>    inventados/estimados para llegar al número.
> 10. **Memoria persistente en GitHub** (`AndresLeonAI/nodoto-lead-hunter-memory`,
>    repo `data/` y `docs/`) es la fuente de verdad entre corridas — leer
>    ANTES de investigar (para no repetir trabajo ni re-contactar leads
>    descartados/enviados) y escribir DESPUÉS (append-only, nunca sobrescribir
>    filas existentes) cada lead, descarte, teléfono rechazado, fuente mala,
>    decisor, nicho trabajado, error y aprendizaje de la corrida.
>
> Ejecución mecánica (dedupe, gate, scoring, export) vive en
> `scripts/cli.py run` — ver `scripts/schema.py` para el modelo de datos
> completo (`DecisionMaker`, `Lead`) y `tests/test_pipeline.py` para los 8
> escenarios E2E obligatorios que este diseño debe pasar siempre.

> ## ACTUALIZACIÓN v3.1 (2026-09-11) — auditoría de eficiencia, BigQuery + Clay
>
> Segunda pasada de auditoría, esta vez enfocada en **eficiencia** (llegar a
> 30-50 leads extremadamente calificados/día de forma consistente, no solo
> correcta). Se investigó si Google BigQuery y Clay (ambos conectados vía
> Composio) debían incorporarse al pipeline. Resultado y cambios reales:
>
> 1. **BigQuery: investigado, NO adoptado como dependencia.** La cuenta
>    conectada solo tiene proyectos genéricos sin relación con NODOTO ("My
>    First Project", "PRUEBA", etc.) — no existe ningún warehouse de leads que
>    aprovechar. Al volumen actual (cientos de filas en `bogota_leads.csv`),
>    parsear CSVs es instantáneo; añadir BigQuery ahora solo introduciría una
>    segunda fuente de verdad que puede desincronizarse de GitHub, exactamente
>    el tipo de riesgo que esta auditoría existe para eliminar, sin mejorar en
>    nada la calidad real de un lead (BigQuery no investiga negocios ni
>    verifica teléfonos). **No usar BigQuery en este pipeline hasta que
>    `bogota_leads.csv` supere ~5,000-10,000 filas y el dedupe fuzzy
>    (`difflib`, O(n²) por corrida) sea un cuello de botella medible** — y aun
>    entonces, como un índice espejo de solo lectura, nunca como reemplazo de
>    GitHub como fuente de verdad append-only.
> 2. **El verdadero apalancamiento de eficiencia era el dimensionamiento del
>    embudo, no infraestructura nueva.** Se implementó
>    `niche_priority.estimate_raw_candidates_needed()`: usa el
>    `owner_access_rate` histórico real de cada nicho (ya calculado desde
>    `bogota_leads.csv`) para decir cuántos candidatos crudos descubrir hoy
>    para tener una oportunidad real de alcanzar el target de calificados —
>    nichos donde el teléfono del decisor históricamente es difícil de
>    encontrar necesitan un embudo más grande, no el mismo 20-40 fijo de
>    siempre. Ver `python3 scripts/cli.py rank-niches --target-qualified <n>`.
> 3. **Escalamiento en paralelo, formalizado en la skill (antes solo vivía en
>    el prompt de la tarea programada).** Ver la nueva sección "Escalamiento
>    en paralelo" más abajo — descubrir en 2-4 nichos a la vez, investigar en
>    lotes paralelos de 15-20 vía sub-agentes, consolidar en un solo JSON,
>    UNA sola llamada a `cli.py run` al final.
> 4. **Clay: disponible, nunca dependencia — solo cuando de verdad se
>    requiere.** Ver "Enriquecimiento opcional con Clay" más abajo. Se usa
>    ÚNICAMENTE como respaldo puntual de descubrimiento de teléfono/email tras
>    agotar las fuentes públicas gratuitas de `owner_phone_sources_v3.md`, y
>    solo para negocios que ya pasarían el filtro de Lead Quality por sí
>    solos. Cualquier dato que devuelva Clay pasa por la MISMA verificación de
>    evidencia que cualquier otra fuente — nunca se eleva automáticamente a
>    DIRECT/NAMED_ATTRIBUTION solo porque vino de Clay. Si Clay no está
>    disponible, la corrida sigue exactamente igual sin él.

> ## ACTUALIZACIÓN v3.2 (2026-09-15) — un archivo por nicho, y un gancho de llamada en frío
>
> Directiva explícita del usuario tras revisar el primer Excel entregado. Dos
> cambios, ambos obligatorios de aquí en adelante:
>
> 1. **El export limpio / el .xlsx final NUNCA mezcla nichos — uno por
>    archivo, siempre.** Un run puede seguir descubriendo/investigando 2-4
>    nichos en paralelo por eficiencia (eso no cambia), pero el momento de
>    entregar es distinto del momento de investigar: `report.py` ahora expone
>    `split_leads_by_niche()` / `build_clean_export_tables_by_niche()`, y
>    `cli.py run` escribe automáticamente `clean_export_<nicho>_<run>.csv` —
>    uno por cada nicho presente en los leads calificados, nunca un solo CSV
>    combinado. **Quien construya el .xlsx final a partir de esos CSV debe
>    generar un archivo de Excel por nicho** (mismo nombre de nicho en el
>    archivo), y entregarlos como archivos separados — nunca un único libro
>    con pestañas por nicho ni una sola hoja con la columna "Niche" mezclada.
>    Si un mismo run produce leads calificados en, por ejemplo, "Dermatólogos"
>    y "Abogados corporativos", eso son DOS archivos entregables, no uno.
> 2. **Nuevo campo `cold_call_hook` (columna "Qué decirle en la llamada" en
>    el export limpio), pensado para maximizar la tasa de reuniones
>    agendadas.** `website_problem`/`website_evidence` siguen existiendo sin
>    cambios (evidencia técnica verificable, exigida por el gate) — pero
>    ahora cada lead calificado también lleva una frase corta (2-3 oraciones),
>    en segunda persona, dirigida al dueño del negocio, redactada como si se
>    fuera a decir casi textual en una llamada en frío: abre con curiosidad
>    genuina (no acusación), traduce el hallazgo técnico a impacto de negocio
>    (clientes/citas que se pierden, no jerga como "404" o "sin SSL"), y
>    cierra con un puente suave hacia agendar una llamada corta. **Nunca
>    inventa nada que no esté ya en `website_problem`/`website_evidence`** —
>    es un cambio de voz, no de contenido. Ver la guía completa con ejemplos
>    y tabla de traducción hallazgo→impacto en
>    `references/cold_call_style_guide.md` — LÉELA antes de escribir el
>    primer `cold_call_hook` de una corrida. Si un lead no califica (sin
>    decisor con teléfono DIRECT/NAMED_ATTRIBUTION), no se genera gancho de
>    venta para él. `report.py` incluye un `_fallback_cold_call_hook()`
>    puramente mecánico como red de seguridad para datos investigados antes
>    de este cambio — produce frases correctas pero mecánicas; el sub-agente
>    que investiga cada lead debe escribir el suyo a mano siguiendo la guía,
>    nunca depender del fallback a propósito.

# NODOTO LEAD HUNTER

A high-ticket sales opportunity engine, not a generic scraper. It exists to answer
one question per business: **can NODOTO actually reach the person who decides,
with a real reason to talk to them?**

```
BUSINESS → OWNER/DECISION MAKER → PHONE → WEBSITE/SOCIALS → DIGITAL OPPORTUNITY
```

This skill is **additive** to the existing repo. It does not touch
`docs/outreach_playbook.md`'s cold-email sending policy, `data/sent_tracking.csv`,
follow-up logic, or the blacklist mechanics — it only discovers and qualifies new
leads and writes them somewhere new (a fresh Google Sheet / worksheet, or CSV).
Read `docs/outreach_playbook.md` and `docs/methodology_and_status.md` first, every
run — they are still the operative source of truth for niches, anti-fabrication
rules, and Bogotá-only scope, which this skill inherits rather than redefines.

## The one rule that overrides every other rule

**A lead is never "Qualified" without a publicly verifiable, professional phone
number belonging to the OWNER/decision-maker — not the business's generic line.**
No score, no amount of polish on the website audit, no urgency in the niche
buys past this. If it's missing: `Owner Phone = NOT_VERIFIED`,
`Qualification Status = OWNER_PHONE_MISSING`, and the lead goes to the
`Candidates - Owner Phone Missing` list, never to `Qualified Leads`.

Owner phone priority (highest to lowest):
1. Phone the professional publishes themselves (own website, own booking page).
2. Professional WhatsApp of the owner specifically.
3. Phone/WhatsApp publicly associated with the owner by name (news, interview, directory).
4. Phone on the owner's personal/professional website.
5. Phone in the owner's own professional social profiles (Instagram bio, LinkedIn).
6. Reliable public professional directories (medical boards, bar associations, etc.).
7. Public business registries where legally available.

Never: guess, infer, autocomplete, pad digits, use leaked/private databases, or
silently relabel the business's generic phone as the owner's. If the same digits
as the business line are the only thing found, that is **not** an owner phone
unless there's explicit evidence the owner personally publishes that same number.

## Pipeline

```
READ REPO → READ GOOGLE SHEET → SELECT NICHE(S) (opportunity score,
sized per niche via estimate_raw_candidates_needed) →
DISCOVER (2-4 niches in parallel if targeting 30-50/day) → RESEARCH
(parallel sub-agent batches of 15-20) → IDENTIFY DECISION-MAKER(S) →
FIND DECISION-MAKER PHONE (Clay only as last-resort fallback) →
AUDIT WEBSITE → FIND SOCIALS → SCORE + GATE → DEDUPE (repo + sheet) →
WRITE (append-only, one consolidated cli.py run) → READ BACK → VERIFY
```

### 0. Read repo + read Sheet

- Read `docs/outreach_playbook.md` and `docs/methodology_and_status.md`.
- Load existing dedupe fingerprints: `python3 skills/nodoto-lead-hunter/scripts -c` isn't
  a thing — import and call `dedupe.load_all_repo_sources(repo_root)` (covers
  `bogota_leads.csv`, `known_bad_contacts.csv`, `sent_tracking.csv`).
- Identify the correct Composio-connected NODOTO Google account and the
  operative spreadsheet. Follow `references/composio_tools.md` step by step.
  **If the account can't be determined with certainty, stop before writing
  anything and say so in the final report** — proceed with discovery/research
  regardless, output goes to CSV only for that run.
- Read the target worksheet's header + existing rows; fold them into the same
  dedupe fingerprint set via `dedupe.load_sheet_rows()`.

### 1. Select the niche (dynamic, not random)

Pick ONE niche from the 50 in `docs/outreach_playbook.md` for the entire run.
Rank candidates by a **Niche Opportunity Score** combining:
economic potential, urgency, existing lead count for that niche (fewer = more
room), % with a bad/missing website, % with an identified owner, % with an
owner phone, competition, and ease of reaching a decision-maker. Favor
HIGH TICKET + WEBSITE GAP + LOW COVERAGE + OWNER ACCESS. Cross-reference
against `bogota_leads.csv`'s `Niche` column and the Sheet's `Niche`
column to see what's already saturated. Do not mix niches within a run.

Size the raw discovery batch to the niche instead of guessing 20-40 every
time:

```bash
python3 skills/nodoto-lead-hunter/scripts/cli.py rank-niches --repo-root . --target-qualified 10
```

The `Raw needed` column comes from `niche_priority.estimate_raw_candidates_needed()`
— it uses the niche's real historical `owner_access_rate` (how often a
decision-maker phone was actually found there before) to say how many
candidates to discover today for a realistic shot at the target. A niche
with no history yet defaults to a conservative 12% assumed qualify rate
(over-discover rather than run short); the number is floored at 2x the
target and capped at 12x (past that, work a second niche in parallel instead
of over-mining one — see "Escalamiento en paralelo" below).

### 1.5 Escalamiento en paralelo (para llegar a 30-50/día de forma confiable)

Un solo nicho de 20-40 candidatos rara vez produce 30-50 calificados —
la meta operativa se alcanza combinando varios nichos por día:

1. Elegir 2-4 nichos del ranking (paso 1), priorizando los de mayor Niche
   Opportunity Score primero.
2. Descubrir el volumen crudo recomendado por nicho (paso 1) — típicamente
   100-150 candidatos totales entre todos los nichos elegidos.
3. Dividir la investigación (pasos 3-6: decisores, teléfono, sitio, redes) en
   lotes de 15-20 candidatos y correrlos en **sub-agentes en paralelo** (uno
   por lote) — cada sub-agente entrega su lote como una lista de objetos con
   el mismo shape que `Lead`/`DecisionMaker` (ver `tests/candidates_sample.json`).
4. Consolidar TODOS los lotes de TODOS los nichos en un solo archivo JSON
   antes de tocar `cli.py`. Nunca correr `cli.py run` una vez por lote —
   fragmenta el dedupe (dos lotes distintos no se ven entre sí hasta que
   comparten una sola llamada) y produce múltiples reportes en vez de uno.
5. Una sola llamada final: `cli.py run candidatos_consolidados.json --niche
   "<nichos trabajados hoy, separados por coma>" ...`.

Esto es exactamente lo que ya hace la tarea programada diaria (ver el prompt
del scheduled task) — esta sección lo deja disponible también para
corridas manuales de la skill, no solo para la automatización.

### 2. Discover (20-40 candidates)

Search Google/Maps/directories for real businesses in that niche, in Bogotá,
matching the high-ticket profile in `docs/outreach_playbook.md` section 1 and
respecting its exclusions (section 2). Real businesses only — no invented
names, no invented addresses.

### 3. Research + decision-maker discovery engine (v3: find ALL of them)

For each candidate, go beyond the Maps listing. Search:
`"<business>" owner`, `"<business>" fundador`, `"<business>" socio`,
`"<business>" director`, `"<business>" Dr.`, `"<business>" LinkedIn`,
`site:linkedin.com "<business>"`, `site:instagram.com "<business>"`.
Objective: business → EVERY plausible decision-maker, not just the first name
found. Roles to look for: Owner, Founder, Co-Founder, Partner, Managing
Partner, Director, lead Doctor/Professional, CEO, Principal,
Administrador/propietario. Record each as a `DecisionMaker` in
`decision_makers`, then rank by `priority` (see the v3 note above) — never
collapse a multi-partner business into a single name.

### 4. Decision-maker phone discovery

Once a decision-maker is named, search specifically:
`"<name>" Bogotá teléfono`, `"<name>" WhatsApp`,
`"<name>" Instagram`, `"<name>" LinkedIn`, `"<name>" website`,
`"<name>" clínica/despacho/estudio`, plus relevant professional
directories (Doctoralia, colegios profesionales). Only public,
professionally-published numbers count — never private or leaked data.
Record `Owner Phone Source` with enough specificity to audit later (e.g.
"Instagram oficial @drname, bio", not just "Instagram"), and
`Owner Phone Evidence` describing HOW the person↔number link was proven, not
just where it was seen. See `docs/owner_phone_sources_v3.md` in the memory
repo for the full 5-tier hierarchy and contradiction-handling protocol.

#### 4b. Enriquecimiento opcional con Clay (respaldo, nunca dependencia)

Clay (`clay_mcp` en Composio) está conectado y disponible, pero el pipeline
**nunca depende de él** — si no está conectado o falla, la corrida sigue
exactamente igual usando solo fuentes públicas. Se invoca únicamente cuando
las TRES condiciones se cumplen:

1. Se agotaron las fuentes públicas gratuitas de `owner_phone_sources_v3.md`
   para el decisor de mayor prioridad (`priority=1`) — Clay nunca reemplaza
   la búsqueda pública, solo la sigue.
2. El negocio ya calificaría por Lead Quality (ticket alto + gap de sitio
   real) independientemente del contacto — nunca gastar créditos de Clay en
   un negocio que de todas formas no calificaría.
3. Existe un dominio propio o página de LinkedIn de la empresa identificable
   (las herramientas de Clay buscan contactos por dominio/URL de LinkedIn de
   la empresa, no por nombre de negocio suelto — muchos consultorios/estudios
   pequeños en Bogotá no tienen esto, y ahí Clay simplemente no aplica).

Herramientas a usar, en este orden: `CLAY_MCP_FIND_AND_ENRICH_LIST_OF_CONTACTS`
si ya se conoce el nombre del decisor (busca su teléfono/email directo), o
`CLAY_MCP_RUN_SUBROUTINE_DIRECT` con la subrutina "Enrich Person and Find
Contact Details" / "Work Email" si solo se conoce el negocio. **Regla que no
se negocia:** cualquier teléfono/email que devuelva Clay entra al pipeline
como un CANDIDATO a verificar, no como un hecho verificado — pasa por el
mismo paso 6 (verificación con evidencia citable) y el mismo cross-check que
cualquier otra fuente. Clay nunca produce por sí solo `phone_confidence =
DIRECT` o `NAMED_ATTRIBUTION`; el tier final depende de si la evidencia
recolectada (idealmente cruzada contra una fuente pública independiente)
sostiene ese nivel. Registrar `phone_source` como algo auditable, ej.
"Clay (Enrich Person) — cruzado contra perfil de LinkedIn personal
verificado", nunca solo "Clay".

### 5. Website audit (visit it for real)

Actually open the site (or confirm it doesn't exist / is down). Judge it
against: missing/dead site, outdated design, generic template, weak
hierarchy, poor mobile experience, weak/absent CTA, no WhatsApp link, no
booking, no social proof, weak value prop, poor photography, weak branding,
stale content, broken links/errors, poor local SEO, positioning below the
business's real market level. Record exactly ONE primary `Website Problem`
with concrete, checkable `Website Evidence` — never a vague adjective.

Bad: `Website is bad.`
Good: `The homepage has no clear primary CTA above the fold and the only
contact path is a generic phone number in the footer.`

Record `Website` as the actual, current, live URL you audited (following any
redirect to the real domain in use today — e.g. an old domain that 302s to a
new one is NOT the value to record, the destination is). If there is no
website, `Website Status = "no_website"` and leave `Website` as `NOT_VERIFIED`
— never a placeholder URL.

**v3.2 — also write `cold_call_hook` here, same step, while the evidence is
fresh** (only for leads that will end up qualifying — DIRECT/NAMED_ATTRIBUTION
decision-maker phone). This is the SAME `website_problem`/`website_evidence`
finding, rewritten as 2-3 spoken sentences in second person, addressed to the
business owner, built to be read almost verbatim on a cold call and to
maximize the booked-meeting rate — never a new fact beyond what's already in
`website_problem`/`website_evidence`. Read
`references/cold_call_style_guide.md` before writing the first one of a run —
it has the full structure (curiosity opener → business-impact translation →
soft bridge to a short call), tone guidance, and a translation table from
common technical findings to business-impact phrasing.

### 6. Social discovery

Find and verify (don't guess) official Instagram, Facebook, LinkedIn, TikTok
(if relevant), and each decision-maker's own professional profile. A profile
only counts as "official" if there's real evidence it belongs to this
business/person (bio matches, linked from the real site, tagged posts, etc.)
— never assume from a similar-looking username.

### 7. Score, validate, and gate (v3: Lead Quality + Contact Quality, separately)

Populate `high_ticket_score`, `website_opportunity_score`,
`data_quality_score` (0-10 each, based on what was actually found) on a
`schema.Lead`, then run it through the gate AND the evidence-quality check
(a lead can satisfy the gate's "field is non-empty" test while still being
too vague to trust — `validate.py` catches that):

```python
import sys; sys.path.insert(0, "skills/nodoto-lead-hunter/scripts")
from schema import Lead, DecisionMaker
from scoring import run_qualification_gate
from validate import validate_evidence_quality

lead = Lead(business_name=..., niche=..., website_problem=..., website_evidence=...,
            high_ticket_score=..., website_opportunity_score=..., data_quality_score=...)
lead.set_decision_makers([
    DecisionMaker(name=..., role=..., authority_level=..., is_current=True,
                  phone=..., phone_confidence=..., phone_source=..., phone_evidence=...,
                  verification_status=..., priority=1),
    # ...additional decision-makers, never dropped, priority=2, 3, ...
])
result = run_qualification_gate(lead)
# result.passed, result.status, result.reasons
# lead.lead_score, lead.lead_tier, lead.lead_quality_score, lead.contact_quality_score now set
quality = validate_evidence_quality(lead)
# quality.ok must also be True
```

Lead Quality weights: High Ticket 45%, Website Opportunity 40%, Data Quality
15% (no contact signal). Contact Quality is built entirely from decision-maker
reachability (name/role/authority + phone confidence tier + evidence +
verification status) — see `scoring.py`. Combined `lead_score` blends them
60/40 for VIP/A/B tier ranking, but **the gate itself never qualifies a lead
without DIRECT or NAMED_ATTRIBUTION on the primary decision-maker**,
regardless of either score. Tiers: 9.0-10 VIP, 8.0-8.9 A, 7.0-7.9 B, below 7
discard. `OWNER_PHONE_MISSING` always overrides tier/score.

### 8. Dedupe (v3: also checks decision-maker reuse across leads)

```python
from dedupe import (load_all_repo_sources, load_sheet_rows, find_duplicate,
                     find_fuzzy_candidates, load_bogota_leads_decision_makers,
                     find_decision_maker_reuse)
existing = load_all_repo_sources(repo_root) + load_sheet_rows(sheet_rows_as_dicts)
existing_dms = load_bogota_leads_decision_makers(repo_root / "data" / "bogota_leads.csv")
dup = find_duplicate(lead, existing)                    # exact-signal match -> auto-drop
fuzzy = find_fuzzy_candidates(lead, existing)             # near-miss names -> flag, don't auto-drop
reuse = find_decision_maker_reuse(lead, existing_dms)     # same person, different business -> flag, don't auto-drop
```

Matches on normalized owner phone, domain, email, Instagram handle, or
normalized business/owner name (order- and stopword-insensitive, catches
"Dr. Juan Pérez Dermatología" == "Juan Pérez Laser Center" when other signals
agree). A match means the candidate is dropped, not silently merged.

### 9. Write (append-only, Sheets + CSV mirror)

Follow `references/composio_tools.md` for the exact Composio call sequence.
Then, always — the CLI does this automatically (see "Running it end-to-end"
below), or call it directly:

```python
from sheets_io import write_csv_mirror
paths = write_csv_mirror(qualified_leads, owner_missing_leads,
                          output_dir=Path("skills/nodoto-lead-hunter/output"))
```

Never clear, overwrite, or replace a worksheet. Append only. If the user has
asked for CSV instead of Sheets for a given run (or the correct Composio
account/spreadsheet can't be verified — see step 0), **this CSV mirror is the
entire output for that run**: say so plainly, hand over the two file paths, and
skip the Sheets write rather than guessing at a connection.

## Running it end-to-end (CLI)

Everything from dedupe through CSV writing and the final report is one
deterministic command once research is done. The agent still has to do the
actual discovery/decision-maker-research/website-audit work (that needs live
browsing and judgment) and produce a JSON file of candidates —
`tests/candidates_sample.json` shows the shape (a `decision_makers` list is
accepted directly) — but from there:

```bash
python3 skills/nodoto-lead-hunter/scripts/cli.py run candidates.json \
    --repo-root . \
    --niche "Dermatólogos de tratamientos láser" \
    --out-dir skills/nodoto-lead-hunter/output
    # optional: --sheet-rows sheet_export.json  (a Composio read of the live Sheet, as JSON)
```

This validates each candidate, dedupes against the repo's CSVs (+ the Sheet
export if provided, + decision-maker reuse across the whole memory) AND
against other candidates in the same batch, runs the qualification gate and
evidence-quality check, writes `qualified_leads_<run>.csv` and
`candidates_owner_phone_missing_<run>.csv`, prints the fixed-format run
report, and — **v3.2, one file per niche, never combined** — writes
`clean_export_<nicho_slug>_<run>.csv` once per distinct niche present in the
qualified leads (e.g. `clean_export_dermatologos_de_tratamientos_laser_<run>.csv`
and `clean_export_abogados_corporativos_<run>.csv` from the same run, as two
separate files, if that run qualified leads in both niches). Whoever builds
the final `.xlsx` deliverable from these must produce one workbook per niche
CSV — never merge them into one file or one multi-tab workbook. With
discard/duplicate/reuse-flag reasons on stderr for auditing. To rank niches
before picking one:

```bash
python3 skills/nodoto-lead-hunter/scripts/cli.py rank-niches --repo-root .
```

### 10. Verify

Re-read the worksheet (if written) and run `sheets_io.verify_write(...)`. If
it fails, stop and report — do not retry blindly. For CSV-only runs, verify by
re-reading the written CSV row count against the in-memory qualified list.
**Before ever calling a run "production-ready", actually execute
`tests/test_pipeline.py` AND run `cli.py run` against a real repo-shaped
directory** — unit tests alone did not catch two real wiring bugs in this
skill's own CLI entrypoint; only an actual `cli.py run` invocation did.

### 11. Report

Render with `scripts/report.py` (`render_report` for the fixed-format summary;
`build_clean_export_tables_by_niche` for the one-row-per-lead answer table,
pre-split by niche — v3.2, use this instead of the single-table
`build_clean_export_table` whenever the output will be delivered as a file,
so a multi-niche run can never accidentally produce one mixed file). See
`report.py`'s `RunStats.from_qualified()` for deriving the v3 quality-breakdown
fields automatically from the qualified leads.

## Batching target

Size the raw batch per niche with `cli.py rank-niches --target-qualified <n>`
(see "Escalamiento en paralelo" above) instead of a fixed 20-40 — typically
2-4 niches, 100-150 raw candidates combined, researched in parallel batches.
Target **30-50 truly qualified leads per day** — but quality over quantity
always: if only 12 are genuinely good, deliver 12, never pad the batch with
weak leads or estimated/invented phone numbers to hit a round number.

## Anti-fabrication (inherited, non-negotiable)

Never invent: decision-maker name, phone, website, socials, score,
observations, pricing, or revenue. Anything unverifiable is `NOT_VERIFIED`,
not a guess. This mirrors `docs/outreach_playbook.md`'s existing
anti-fabrication rule for emails — this skill extends the same discipline to
decision-makers and phones, now enforced additionally by
`scoring.phone_format_is_plausible()` and `scoring._validate_enum_fields()`,
which reject garbled numbers and invented confidence/status/authority values
outright rather than silently accepting them.

## What this skill does NOT do

It does not send emails, does not touch `sent_tracking.csv` or
`known_bad_contacts.csv` write paths, does not modify follow-up sequencing,
and does not change the existing 3-account Gmail round-robin. It only
discovers, qualifies, and writes new leads. Log the run in the memory repo's
`docs/run_log.md` following the existing entry format — as its own dated
entry, not mixed into the cold-email run log.

## Files in this skill

- `scripts/schema.py` — canonical `Lead` + `DecisionMaker` dataclasses, 5-tier
  phone confidence, verification status, authority levels.
- `scripts/dedupe.py` — normalization + exact and fuzzy duplicate detection,
  plus cross-lead decision-maker reuse detection.
- `scripts/scoring.py` — the qualification gate (decision-maker phone tier +
  is_current + contradiction checks) + separate Lead Quality / Contact
  Quality scoring + anti-hallucination phone-format and enum validation.
- `scripts/validate.py` — evidence-quality checks (rejects generic phone
  sources/evidence, vague website-problem text, unrecorded secondary
  decision-makers).
- `scripts/niche_priority.py` — Niche Opportunity Score ranking from real
  repo/Sheet coverage data, plus `estimate_raw_candidates_needed()` (v3.1) for
  sizing the raw discovery batch per niche from its real historical
  owner-access rate.
- `scripts/sheets_io.py` — Sheets write-plan/verify contract + CSV fallback writer.
- `scripts/report.py` — fixed-format run report + the exact one-row-per-lead
  clean export table, split by niche (v3.2 — `split_leads_by_niche`,
  `build_clean_export_tables_by_niche`, `niche_slug`), plus `cold_call_hook`
  handling (`_fallback_cold_call_hook` for older data).
- `scripts/cli.py` — single entrypoint running dedupe → gate → validate →
  score → write → report over a JSON candidates file; writes one
  `clean_export_<nicho>_<run>.csv` per niche (v3.2).
- `references/composio_tools.md` — exact Composio call sequence + account-verification steps.
- `references/cold_call_style_guide.md` — v3.2: how to write `cold_call_hook`
  (structure, tone, a technical-finding → business-impact translation table,
  worked examples) so the clean export reads as a call-ready script, not a
  technical audit note.
- `tests/test_pipeline.py` — the 8 mandated E2E scenarios (single/multi
  decision-maker, generic/verified-business-only phone rejection,
  named-attribution, contradictory sources, no-website, multi-location,
  former-founder), anti-hallucination checks, decision-maker-reuse, the
  funnel-sizing helper (v3.1), and a subprocess-level test of `cli.py run`
  itself (the only thing that caught two real production bugs in this
  skill's own wiring). Run after any change:
  `python3 skills/nodoto-lead-hunter/tests/test_pipeline.py`.
- `tests/candidates_sample.json` — example input shape for `cli.py run`.
