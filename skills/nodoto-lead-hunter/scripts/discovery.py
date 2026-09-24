"""
NODOTO LEAD HUNTER — v4.2 multi-channel discovery (Maps is optional, never a dependency).

Why: on 2026-09-15 and 2026-09-24 the Google Places quota (SearchTextRequest,
4000/day/project) was exhausted before the run started. Discovery fell back to
ad-hoc web search by 6 research agents and yielded 28 raw candidates instead of
the ~125 needed — the run delivered 4 qualified leads instead of 30-50.

Fix: discovery is its own phase, split into SHARDS (channel x zone), each run by
a dedicated discovery sub-agent that only returns real business names + source
URLs (cheap, fast). Google Maps is just one channel: probed once; if it answers
429/any error, its shards are re-assigned to the web channels and the run keeps
the same raw target. Then `merge_discovery()` dedupes every shard against memory
and against each other, and `split_into_research_batches()` produces the 15-per
batch inputs for the research sub-agents (unchanged pipeline, VAULT v4.0 intact).

One niche per run (v4.2 rule): every function here takes exactly one niche.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedupe import normalize_text, normalize_domain, normalize_phone, normalize_handle  # noqa: E402

BOGOTA_ZONES = [
    "Usaquén / Santa Bárbara / Santa Bibiana",
    "Chicó / Virrey / Parque 93 / Antiguo Country",
    "Chapinero / Rosales / Quinta Camacho / Zona G",
    "Cedritos / Colina Campestre / Suba / Niza",
    "Salitre / Teusaquillo / Modelia / Centro Internacional",
]

# Channel -> query templates. {n} = niche search phrase, {z} = zone.
# Each channel is an independent, public, free source. Order = expected yield.
DISCOVERY_CHANNELS: dict[str, list[str]] = {
    "google_maps": ["{n} {z} Bogotá"],  # only if probe_maps() is True
    "web_google": [
        "{n} {z} Bogotá", "mejores {n} en Bogotá", "{n} Bogotá sitio oficial",
        "{n} Bogotá \"agenda tu cita\" OR \"contáctanos\"",
    ],
    "directories": [
        "site:doctoralia.co {n} Bogotá", "site:paginasamarillas.com.co {n} Bogotá",
        "site:cylex.com.co {n} Bogotá", "site:houzz.com.co {n} Bogotá",
        "{n} Bogotá directorio colegio profesional",
    ],
    "instagram_social": [
        "site:instagram.com {n} Bogotá", "site:facebook.com {n} Bogotá",
        "site:linkedin.com/in {n} Bogotá fundador OR socio OR director",
    ],
    "press_rankings": [
        "top {n} Bogotá 2026", "ranking {n} Colombia", "{n} Bogotá entrevista fundador",
        "{n} Bogotá revista (Semana OR Axxis OR Diners OR La República)",
    ],
    "registries": [
        "{n} Bogotá RUES S.A.S. representante legal", "{n} Bogotá Cámara de Comercio",
    ],
}

WEB_CHANNELS = [c for c in DISCOVERY_CHANNELS if c != "google_maps"]


def probe_maps(run_composio_tool: Callable, test_query: str = "odontología Bogotá") -> bool:
    """One cheap Places call. Any error (429 quota, auth, timeout) => False.
    Never retry in a loop: a 429 on SearchTextRequest is a DAILY quota."""
    try:
        res, err = run_composio_tool("GOOGLE_MAPS_TEXT_SEARCH", {
            "textQuery": test_query, "maxResultCount": 1, "fieldMask": "places.id"})
    except Exception:
        return False
    if err:
        return False
    data = (res or {}).get("data", {})
    data = data.get("data", data)
    return bool(data.get("places"))


def build_discovery_plan(niche: str, search_phrase: str, raw_needed: int,
                         maps_available: bool, per_shard_target: int = 25,
                         zones: Optional[list[str]] = None) -> list[dict]:
    """Returns shards, each for ONE discovery sub-agent. Target sum >= raw_needed * 1.3
    (over-discover: ~30% of raw hits are dropped as dupes/chains/out-of-city)."""
    zones = zones or BOGOTA_ZONES
    goal = int(raw_needed * 1.3)
    channels = (["google_maps"] if maps_available else []) + WEB_CHANNELS
    shards: list[dict] = []
    # zone-based channels first (maps, web_google), then city-wide channels
    for ch in channels:
        zone_list = zones if ch in ("google_maps", "web_google") else ["Bogotá (toda la ciudad)"]
        for z in zone_list:
            qs = [t.format(n=search_phrase, z=z if "toda" not in z else "").replace("  ", " ").strip()
                  for t in DISCOVERY_CHANNELS[ch]]
            shards.append({"niche": niche, "channel": ch, "zone": z, "queries": qs,
                           "target": per_shard_target})
    total = sum(s["target"] for s in shards)
    if total < goal:  # scale targets up evenly
        k = goal / total
        for s in shards:
            s["target"] = int(round(s["target"] * k))
    return shards


def group_shards_for_agents(shards: list[dict], agents: int) -> list[list[dict]]:
    """Round-robin shards over N discovery agents (so each agent mixes channels)."""
    groups: list[list[dict]] = [[] for _ in range(max(1, agents))]
    for i, s in enumerate(shards):
        groups[i % len(groups)].append(s)
    return [g for g in groups if g]


def _keys(c: dict) -> set[str]:
    keys = set()
    n = normalize_text(c.get("business_name"))
    if n:
        keys.add("n:" + n)
    for f in ("website",):
        d = normalize_domain(c.get(f))
        if d and d not in ("instagram.com", "facebook.com", "linktr.ee", "wa.me", "doctoralia.co"):
            keys.add("d:" + d)
    p = normalize_phone(c.get("business_phone"))
    if p and len(p) >= 7:
        keys.add("p:" + p)
    h = normalize_handle(c.get("instagram"))
    if h:
        keys.add("i:" + h)
    return keys


def _memory_keys(repo_root: Path) -> set[str]:
    import csv
    keys: set[str] = set()
    for rel in ("data/bogota_leads.csv", "data/candidates_owner_phone_missing.csv"):
        p = repo_root / rel
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                keys |= _keys({"business_name": row.get("Business Name"), "website": row.get("Website"),
                               "business_phone": row.get("Business Phone"), "instagram": row.get("Instagram")})
    return keys


def merge_discovery(discovery_dir: Path, repo_root: Path, niche: str,
                    out_path: Optional[Path] = None) -> dict:
    """Reads every discovery shard file (*.json lists of {business_name, website,
    business_phone, instagram, address, source_url, channel}) and returns a single
    deduped pool for ONE niche, excluding anything already in memory."""
    mem = _memory_keys(repo_root)
    seen: set[str] = set()
    pool, dup_mem, dup_run, bad = [], 0, 0, 0
    for f in sorted(Path(discovery_dir).glob("*.json")):
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            bad += 1
            continue
        for c in items:
            if not normalize_text(c.get("business_name")) or not c.get("source_url"):
                bad += 1  # anti-fabrication: every discovered business needs a citable URL
                continue
            k = _keys(c)
            if k & mem:
                dup_mem += 1
                continue
            if k & seen:
                dup_run += 1
                continue
            seen |= k
            c = dict(c)
            c["niche"] = niche
            pool.append(c)
    if out_path:
        Path(out_path).write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"pool": pool, "unique": len(pool), "dup_memory": dup_mem, "dup_in_run": dup_run,
            "invalid": bad}


def split_into_research_batches(pool: list[dict], size: int = 15) -> list[list[dict]]:
    return [pool[i:i + size] for i in range(0, len(pool), size)]


def sheet_tab_name(run_date: str) -> str:
    """v4.2: every run writes its qualified leads to a NEW tab in the operative
    spreadsheet, named exactly 'NODOTO Auto Leads <YYYY-MM-DD>'."""
    return f"NODOTO Auto Leads {run_date}"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("plan")
    p1.add_argument("--niche", required=True)
    p1.add_argument("--phrase", required=True)
    p1.add_argument("--raw-needed", type=int, required=True)
    p1.add_argument("--maps", action="store_true")
    p1.add_argument("--agents", type=int, default=6)
    p2 = sub.add_parser("merge")
    p2.add_argument("--dir", required=True)
    p2.add_argument("--repo-root", required=True)
    p2.add_argument("--niche", required=True)
    p2.add_argument("--out", required=True)
    p2.add_argument("--batch-size", type=int, default=15)
    a = ap.parse_args()
    if a.cmd == "plan":
        shards = build_discovery_plan(a.niche, a.phrase, a.raw_needed, a.maps)
        groups = group_shards_for_agents(shards, a.agents)
        print(json.dumps(groups, ensure_ascii=False, indent=1))
    else:
        r = merge_discovery(Path(a.dir), Path(a.repo_root), a.niche, Path(a.out))
        batches = split_into_research_batches(r["pool"], a.batch_size)
        out_dir = Path(a.out).parent / "research_inputs"
        out_dir.mkdir(exist_ok=True)
        for i, b in enumerate(batches, 1):
            (out_dir / f"batch_{i:02d}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in r.items() if k != "pool"} | {"research_batches": len(batches)}))
