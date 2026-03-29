"""
BootstrapEngine — fetches current politicians from qualified external sources
and seeds the database. No politician names or data are hardcoded here.

Source code contains:
  - HOW to fetch from source types (adapter classes)
  - HOW to classify raw role titles into game tiers/asset_types (RoleClassifier)
  - DEFAULT source *configurations* (URLs, adapter types) — seeded once into DB
  - DEFAULT role classification *patterns* — seeded once into DB
  - DEFAULT scoring rules — seeded once into DB

Data (WHO exists, their roles, their parties) comes exclusively from the web
at runtime. All seeded rows are editable via admin API after first run.

Adapters:
  - OurCommonsAPIAdapter   — api.ourcommons.ca OData (federal ministers)
  - WikidataAdapter        — Wikidata SPARQL (provincial premiers/ministers)
  - LegislatureHTMLAdapter — generic HTML scraper (CSS selectors in config_json)

Adding a new source: insert a DataSourceModel row with bootstrap=True and
the appropriate source_type. No code change required.
"""
from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slug(name: str) -> str:
    """Stable URL-safe ID fragment derived from a human name."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Default source configurations ─────────────────────────────────────────────
# These are SOURCE CONFIGS (URLs, adapter types, field mappings) — not people.
# Seeded into data_sources on first run; editable via /admin/data-sources thereafter.

DEFAULT_BOOTSTRAP_SOURCES: list[dict] = [
    {
        "name": "Parliament of Canada — Current Members (OData)",
        "source_type": "ourcommons_api",
        "bootstrap": True,
        "url_template": (
            "https://api.ourcommons.ca/odata/Members"
            "?$filter=IsCurrent%20eq%20true"
            "&$select=PersonOfficialFirstName,PersonOfficialLastName,"
            "Province,Party,Role,PersonId"
            "&$top=350"
        ),
        "config_json": {
            "jurisdiction": "federal",
            "role_filters": [
                "minister", "ministre", "prime minister", "premier ministre",
                "house leader", "whip", "leader of", "chef de", "chef du",
                "opposition leader",
            ],
            "name_fields": ["PersonOfficialFirstName", "PersonOfficialLastName"],
            "role_field": "Role",
            "party_field": "Party",
            "province_field": "Province",
            "external_id_field": "PersonId",
        },
        "active": True,
    },
    {
        "name": "Wikidata — Canadian Provincial Premiers",
        "source_type": "wikidata_sparql",
        "bootstrap": True,
        "url_template": "https://query.wikidata.org/sparql",
        "config_json": {
            # Query: current holders of positions that are subclasses of
            # "head of government of a Canadian province" (Q1255921)
            "query": (
                "SELECT DISTINCT ?person ?personLabel ?posLabel ?partyLabel ?provinceLabel WHERE {"
                " ?person p:P39 ?ps . ?ps ps:P39 ?pos ."
                " FILTER NOT EXISTS { ?ps pq:P582 ?end }"
                " ?pos wdt:P17 wd:Q16 ."
                " { ?pos wdt:P31/wdt:P279* wd:Q30461 }"
                " UNION { ?pos wdt:P31/wdt:P279* wd:Q1255921 }"
                " OPTIONAL { ?person wdt:P102 ?party }"
                " OPTIONAL { ?pos wdt:P131 ?province }"
                " SERVICE wikibase:label { bd:serviceParam wikibase:language \"en,fr\" }"
                " } LIMIT 50"
            ),
            "jurisdiction_hint": "provincial",
            "person_field": "personLabel",
            "position_field": "posLabel",
            "party_field": "partyLabel",
            "province_field": "provinceLabel",
        },
        "active": True,
    },
    {
        "name": "Wikidata — Canadian Federal Cabinet",
        "source_type": "wikidata_sparql",
        "bootstrap": True,
        "url_template": "https://query.wikidata.org/sparql",
        "config_json": {
            # Query: current holders of positions that are subclasses of
            # "minister of the Crown of Canada" (Q83290)
            "query": (
                "SELECT DISTINCT ?person ?personLabel ?posLabel ?partyLabel WHERE {"
                " ?person p:P39 ?ps . ?ps ps:P39 ?pos ."
                " FILTER NOT EXISTS { ?ps pq:P582 ?end }"
                " ?pos wdt:P17 wd:Q16 ."
                " ?pos wdt:P31/wdt:P279* wd:Q83290 ."
                " OPTIONAL { ?person wdt:P102 ?party }"
                " SERVICE wikibase:label { bd:serviceParam wikibase:language \"en,fr\" }"
                " } LIMIT 50"
            ),
            "jurisdiction_hint": "federal",
            "person_field": "personLabel",
            "position_field": "posLabel",
            "party_field": "partyLabel",
            "province_field": None,
        },
        "active": True,
    },
    {
        "name": "Wikidata — Canadian Opposition Leaders",
        "source_type": "wikidata_sparql",
        "bootstrap": True,
        "url_template": "https://query.wikidata.org/sparql",
        "config_json": {
            # Query: current holders of "Leader of the Official Opposition" and
            # party leader positions in Canada (federal + provincial)
            "query": (
                "SELECT DISTINCT ?person ?personLabel ?posLabel ?partyLabel WHERE {"
                " ?person p:P39 ?ps . ?ps ps:P39 ?pos ."
                " FILTER NOT EXISTS { ?ps pq:P582 ?end }"
                " ?pos wdt:P17 wd:Q16 ."
                " { ?pos wdt:P31/wdt:P279* wd:Q1255921 }"
                " UNION { ?pos wdt:P31/wdt:P279* wd:Q2035432 }"
                " UNION { VALUES ?pos { wd:Q17285765 wd:Q3289596 wd:Q2035432 } }"
                " OPTIONAL { ?person wdt:P102 ?party }"
                " SERVICE wikibase:label { bd:serviceParam wikibase:language \"en,fr\" }"
                " } LIMIT 50"
            ),
            "jurisdiction_hint": "federal",
            "person_field": "personLabel",
            "position_field": "posLabel",
            "party_field": "partyLabel",
            "province_field": None,
        },
        "active": True,
    },
    # ── Canonical news RSS feeds (used by ingest worker, not bootstrap) ──────
    {
        "name": "CBC News Politics",
        "source_type": "rss",
        "bootstrap": False,
        "url_template": "https://www.cbc.ca/cmlink/rss-politics",
        "config_json": {"weight": 1.2, "trust": 0.90},
        "active": True,
    },
    {
        "name": "CTV News Politics",
        "source_type": "rss",
        "bootstrap": False,
        "url_template": "https://www.ctvnews.ca/rss/ctvnews-canada-politics-1.822032",
        "config_json": {"weight": 1.1, "trust": 0.85},
        "active": True,
    },
    {
        "name": "Globe and Mail Politics",
        "source_type": "rss",
        "bootstrap": False,
        "url_template": "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/politics/",
        "config_json": {"weight": 1.1, "trust": 0.85},
        "active": True,
    },
]


# ── Default role classification patterns ──────────────────────────────────────
# Maps substrings in role titles → (tier, asset_type). Seeded into DB once.
# Higher priority wins when multiple patterns match the same role title.

DEFAULT_ROLE_CLASSIFICATIONS: list[dict] = [
    # Tier 1 — Head of Government
    {"pattern": "prime minister",                    "tier": 1, "asset_type": "executive",    "jurisdiction_hint": "federal",    "priority": 100},
    {"pattern": "premier ministre",                  "tier": 1, "asset_type": "executive",    "jurisdiction_hint": "federal",    "priority": 100},
    {"pattern": "premier of",                        "tier": 1, "asset_type": "executive",    "jurisdiction_hint": "provincial", "priority": 100},
    {"pattern": "première ministre",                 "tier": 1, "asset_type": "executive",    "jurisdiction_hint": "provincial", "priority": 100},
    # Tier 2 — Deputy / Finance / Opposition leader
    {"pattern": "deputy prime minister",             "tier": 2, "asset_type": "executive",    "jurisdiction_hint": "federal",    "priority": 92},
    {"pattern": "vice-premier",                      "tier": 2, "asset_type": "executive",    "jurisdiction_hint": "provincial", "priority": 92},
    {"pattern": "leader of the official opposition", "tier": 2, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 91},
    {"pattern": "leader of the opposition",          "tier": 2, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 89},
    {"pattern": "chef de l'opposition",              "tier": 2, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 89},
    {"pattern": "minister of finance",               "tier": 2, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 87},
    {"pattern": "ministre des finances",             "tier": 2, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 87},
    {"pattern": "provincial leader",                 "tier": 2, "asset_type": "opposition",   "jurisdiction_hint": "provincial", "priority": 82},
    # Tier 3 — Cabinet ministers
    {"pattern": "minister of health",                "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 72},
    {"pattern": "minister of justice",               "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 72},
    {"pattern": "attorney general",                  "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 70},
    {"pattern": "solicitor general",                 "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 70},
    {"pattern": "minister of",                       "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 60},
    {"pattern": "ministre de",                       "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 60},
    {"pattern": "minister responsible",              "tier": 3, "asset_type": "cabinet",      "jurisdiction_hint": None,         "priority": 58},
    # Tier 4 — Parliamentary roles
    {"pattern": "house leader",                      "tier": 4, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 77},
    {"pattern": "chief government whip",             "tier": 4, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 75},
    {"pattern": "government whip",                   "tier": 4, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 72},
    {"pattern": "speaker",                           "tier": 4, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 70},
    {"pattern": "president of the",                  "tier": 4, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 58},
    # Tier 5 — Critics / shadow roles
    {"pattern": "opposition critic",                 "tier": 5, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 67},
    {"pattern": "shadow minister",                   "tier": 5, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 67},
    {"pattern": "critic",                            "tier": 5, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 52},
    {"pattern": "porte-parole",                      "tier": 5, "asset_type": "opposition",   "jurisdiction_hint": None,         "priority": 52},
    # Fallback — generic elected member
    {"pattern": "member of parliament",              "tier": 5, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 10},
    {"pattern": "député",                            "tier": 5, "asset_type": "parliamentary","jurisdiction_hint": None,         "priority": 10},
]


# ── Default scoring rules ──────────────────────────────────────────────────────
# (event_type, asset_type, base_points, affinity_bonus, jurisdiction_scope, description)

DEFAULT_SCORING_RULES: list[tuple[str, str, int, int, str, str]] = [
    ("legislative",       "executive",     5,  3, "own", "Executive on legislative event"),
    ("legislative",       "cabinet",       5,  2, "own", "Cabinet on legislative event"),
    ("legislative",       "opposition",    5,  2, "own", "Opposition on legislative event"),
    ("legislative",       "parliamentary", 5,  3, "own", "Parliamentary on legislative event"),
    ("executive",         "executive",     4,  3, "own", "Executive event for executive role"),
    ("executive",         "cabinet",       4,  2, "own", "Cabinet on executive event"),
    ("executive",         "opposition",    2,  0, "own", "Opposition on executive event"),
    ("executive",         "parliamentary", 3,  1, "own", "Parliamentary on executive event"),
    ("intergovernmental", "executive",     5,  3, "any", "Executive on intergovernmental"),
    ("intergovernmental", "cabinet",       4,  2, "any", "Cabinet on intergovernmental"),
    ("intergovernmental", "opposition",    3,  1, "any", "Opposition on intergovernmental"),
    ("intergovernmental", "parliamentary", 3,  1, "any", "Parliamentary on intergovernmental"),
    ("confidence",        "executive",     6,  3, "own", "Executive on confidence vote"),
    ("confidence",        "cabinet",       6,  2, "own", "Cabinet on confidence vote"),
    ("confidence",        "parliamentary", 6,  2, "own", "Parliamentary on confidence vote"),
    ("confidence",        "opposition",    5,  2, "own", "Opposition on confidence vote"),
    ("opposition",        "opposition",    3,  3, "own", "Opposition on opposition event"),
    ("opposition",        "executive",     2,  0, "own", "Executive targeted by opposition"),
    ("opposition",        "cabinet",       2,  0, "own", "Cabinet targeted by opposition"),
    ("opposition",        "parliamentary", 2,  1, "own", "Parliamentary on opposition event"),
    ("election",          "executive",     4,  2, "own", "Executive in election event"),
    ("election",          "opposition",    4,  2, "own", "Opposition in election event"),
    ("election",          "cabinet",       3,  1, "own", "Cabinet in election event"),
    ("election",          "parliamentary", 3,  1, "own", "Parliamentary in election event"),
    ("ethics",            "executive",    -6,  0, "own", "Executive in ethics/scandal"),
    ("ethics",            "cabinet",      -5,  0, "own", "Cabinet in ethics/scandal"),
    ("ethics",            "opposition",    3,  2, "own", "Opposition benefits from scandal"),
    ("ethics",            "parliamentary", 1,  0, "own", "Parliamentary in ethics context"),
    ("policy",            "executive",     4,  3, "own", "Executive on policy event"),
    ("policy",            "cabinet",       4,  2, "own", "Cabinet on policy event"),
    ("policy",            "opposition",    3,  1, "own", "Opposition on policy event"),
    ("policy",            "parliamentary", 2,  1, "own", "Parliamentary on policy event"),
    # Leadership change — deferred, applied at next cycle
    ("leadership_change", "executive",     5,  2, "any", "Executive in leadership change"),
    ("leadership_change", "cabinet",       4,  1, "any", "Cabinet in leadership change"),
    ("leadership_change", "opposition",    4,  1, "any", "Opposition in leadership change"),
    ("leadership_change", "parliamentary", 3,  1, "any", "Parliamentary in leadership change"),
    ("general",           "executive",     2,  1, "any", "General event"),
    ("general",           "cabinet",       2,  1, "any", "General event"),
    ("general",           "opposition",    2,  1, "any", "General event"),
    ("general",           "parliamentary", 2,  1, "any", "General event"),
]


# ── Default system config ──────────────────────────────────────────────────────

DEFAULT_SYSTEM_CONFIG: dict[str, object] = {
    "ai_enabled": False,
    "ai_base_url": "http://10.11.235.71:11434",
    "ai_model": "mistral",
    "ai_confidence_weight": 0.3,
    "attribution_confidence_floor": 0.65,
    "scoring_rule_version": "v1",
    "max_points_per_asset_week": 25,
    "min_points_per_asset_week": -20,
    "bootstrap_min_politicians": 10,
    "per_politician_rss_enabled": True,
}


# ── Raw intermediate representation ───────────────────────────────────────────

@dataclass
class RawPolitician:
    """Normalised intermediate record from any source adapter."""
    full_name: str
    role_title: str
    party: str
    jurisdiction: str     # "federal" or two-letter province code
    source: str           # adapter name tag
    external_id: str | None = None
    extra: dict = field(default_factory=dict)


# ── Source adapters ────────────────────────────────────────────────────────────

class SourceAdapter(ABC):
    FETCH_TIMEOUT = 25.0

    def __init__(self, name: str, url_template: str, config: dict) -> None:
        self.name = name
        self.url_template = url_template
        self.config = config

    @abstractmethod
    def fetch(self) -> list[RawPolitician]:
        """Fetch politicians from this source. Never raises — logs and returns []."""

    @staticmethod
    def _get(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 25.0) -> httpx.Response:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            return client.get(url, params=params or {}, headers=headers or {})


class OurCommonsAPIAdapter(SourceAdapter):
    """
    Fetches qualifying federal members from api.ourcommons.ca OData REST API.
    Role filtering and field mappings are fully driven by config_json.
    """

    def fetch(self) -> list[RawPolitician]:
        try:
            resp = self._get(self.url_template, headers={"Accept": "application/json"})
            resp.raise_for_status()
            members = resp.json().get("value", [])
        except Exception as exc:  # noqa: BLE001
            print(f"OurCommonsAPIAdapter: fetch failed — {exc}", flush=True)
            return []

        role_filters = [kw.lower() for kw in self.config.get("role_filters", [])]
        name_fields: list[str] = self.config.get("name_fields", ["PersonOfficialFirstName", "PersonOfficialLastName"])
        role_field: str = self.config.get("role_field", "Role")
        party_field: str = self.config.get("party_field", "Party")
        province_field: str = self.config.get("province_field", "Province")
        ext_id_field: str = self.config.get("external_id_field", "PersonId")
        default_jurisdiction: str = self.config.get("jurisdiction", "federal")

        results: list[RawPolitician] = []
        for m in members:
            role = str(m.get(role_field, "")).strip()
            if role_filters and not any(kw in role.lower() for kw in role_filters):
                continue
            name_parts = [str(m.get(f, "")).strip() for f in name_fields]
            full_name = " ".join(p for p in name_parts if p).strip()
            if not full_name or not role:
                continue
            province = str(m.get(province_field, "")).strip()
            jurisdiction = _province_to_code(province) if province else default_jurisdiction
            results.append(RawPolitician(
                full_name=full_name,
                role_title=role,
                party=str(m.get(party_field, "")).strip(),
                jurisdiction=jurisdiction,
                source="ourcommons",
                external_id=str(m.get(ext_id_field, "")) or None,
            ))

        print(f"OurCommonsAPIAdapter: {len(results)} qualifying members fetched", flush=True)
        return results


class WikidataAdapter(SourceAdapter):
    """
    Fetches politicians via Wikidata SPARQL endpoint.
    The full SPARQL query lives in config_json['query'] — editable in DB.
    """

    SPARQL_HEADERS = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "FantasyCabinet/1.0 (Canadian politics game; contact@fantasycabinet.ca)",
    }

    def fetch(self) -> list[RawPolitician]:
        query: str = self.config.get("query", "")
        if not query:
            print(f"WikidataAdapter [{self.name}]: no query in config_json, skipping", flush=True)
            return []

        try:
            with httpx.Client(timeout=self.FETCH_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(
                    self.url_template,
                    params={"query": query, "format": "json"},
                    headers=self.SPARQL_HEADERS,
                )
                resp.raise_for_status()
                bindings = resp.json().get("results", {}).get("bindings", [])
        except Exception as exc:  # noqa: BLE001
            print(f"WikidataAdapter [{self.name}]: fetch failed — {exc}", flush=True)
            return []

        person_field: str = self.config.get("person_field", "personLabel")
        position_field: str = self.config.get("position_field", "posLabel")
        party_field: str = self.config.get("party_field", "partyLabel")
        province_field: str | None = self.config.get("province_field")
        jurisdiction_hint: str = self.config.get("jurisdiction_hint", "federal")

        results: list[RawPolitician] = []
        for b in bindings:
            full_name = b.get(person_field, {}).get("value", "").strip()
            role_title = b.get(position_field, {}).get("value", "").strip()
            party = b.get(party_field, {}).get("value", "").strip()
            province_raw = b.get(province_field, {}).get("value", "").strip() if province_field else ""
            if not full_name or not role_title:
                continue
            # Skip Wikidata internal URIs (malformed labels)
            if full_name.startswith("Q") and full_name[1:].isdigit():
                continue
            jurisdiction = _province_to_code(province_raw) if province_raw else jurisdiction_hint
            results.append(RawPolitician(
                full_name=full_name,
                role_title=role_title,
                party=party,
                jurisdiction=jurisdiction,
                source="wikidata",
            ))

        print(f"WikidataAdapter [{self.name}]: {len(results)} records fetched", flush=True)
        return results


class LegislatureHTMLAdapter(SourceAdapter):
    """
    Generic HTML scraper for provincial legislature member pages.
    Uses regex patterns from config_json (no BeautifulSoup dependency).

    Required config_json keys:
      name_regex  — Python regex with one capture group for the member name
      role_regex  — regex for role (optional)
      party_regex — regex for party (optional)
      jurisdiction — two-letter province code e.g. "ON"
    """

    def fetch(self) -> list[RawPolitician]:
        name_pattern: str | None = self.config.get("name_regex")
        if not name_pattern:
            print(f"LegislatureHTMLAdapter [{self.name}]: no name_regex configured, skipping", flush=True)
            return []

        try:
            resp = self._get(self.url_template)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"LegislatureHTMLAdapter [{self.name}]: fetch failed — {exc}", flush=True)
            return []

        jurisdiction: str = self.config.get("jurisdiction", "unknown")
        role_pattern: str | None = self.config.get("role_regex")
        party_pattern: str | None = self.config.get("party_regex")

        html = resp.text
        names = re.findall(name_pattern, html)
        roles = re.findall(role_pattern, html) if role_pattern else []
        parties = re.findall(party_pattern, html) if party_pattern else []

        results: list[RawPolitician] = []
        for i, name in enumerate(names):
            results.append(RawPolitician(
                full_name=name.strip(),
                role_title=(roles[i].strip() if i < len(roles) else "Member"),
                party=(parties[i].strip() if i < len(parties) else "Unknown"),
                jurisdiction=jurisdiction,
                source="legislature_html",
            ))

        print(f"LegislatureHTMLAdapter [{self.name}]: {len(results)} records extracted", flush=True)
        return results


_ADAPTER_MAP: dict[str, type[SourceAdapter]] = {
    "ourcommons_api":   OurCommonsAPIAdapter,
    "wikidata_sparql":  WikidataAdapter,
    "legislature_html": LegislatureHTMLAdapter,
}


# ── Role classifier ────────────────────────────────────────────────────────────

class RoleClassifier:
    """
    Maps a raw role title to (tier, asset_type, jurisdiction) using DB rules.
    Rules are sorted by priority (highest first) so the first match wins.
    """

    def __init__(self, rules: list[dict]) -> None:
        self.rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)

    def classify(self, role_title: str, source_jurisdiction: str) -> dict:
        role_lower = role_title.lower()
        for rule in self.rules:
            if rule["pattern"] in role_lower:
                hint = rule.get("jurisdiction_hint")
                if hint == "provincial":
                    # Use the actual province from the source, not the hint
                    jurisdiction = source_jurisdiction if source_jurisdiction != "federal" else "provincial"
                else:
                    jurisdiction = hint or source_jurisdiction or "federal"
                return {
                    "tier": rule["tier"],
                    "asset_type": rule["asset_type"],
                    "jurisdiction": jurisdiction,
                }
        return {"tier": 5, "asset_type": "parliamentary", "jurisdiction": source_jurisdiction or "federal"}


# ── Bootstrap engine ───────────────────────────────────────────────────────────

class BootstrapEngine:
    """
    Orchestrates the full bootstrap cycle:
      1. Seed system_config, data_sources, scoring_rules, role_classifications (idempotent)
      2. For each active bootstrap DataSource: fetch → classify → upsert PoliticianModel
      3. Generate per-politician Google News RSS DataSourceModel rows for the worker
      4. Migrate legacy mp-* asset_ids in roster_slots to pol-* IDs
    """

    def run(self, session: "Session") -> int:
        """
        Run bootstrap. Returns number of new politicians written.
        Caller must commit the session after this returns.
        """
        # Lazy import to avoid circular dependency at module load
        from app.api.v1.persistent_store import (  # noqa: PLC0415
            DataSourceModel, PoliticianModel, RoleClassificationModel,
            ScoringRuleModel, SystemConfigModel,
        )
        from sqlalchemy import select  # noqa: PLC0415

        # 1. Seed config tables (idempotent — skips existing rows)
        self._seed_system_config(session, SystemConfigModel, select)
        self._seed_role_classifications(session, RoleClassificationModel, select)
        self._seed_data_sources(session, DataSourceModel, select)
        self._seed_scoring_rules(session, ScoringRuleModel, select)
        session.flush()

        # 2. Only fetch politicians if table is empty
        if session.scalar(select(PoliticianModel).limit(1)) is not None:
            return 0

        # 3. Load classifier rules from DB (just seeded)
        db_rules = [
            {
                "pattern": r.pattern,
                "tier": r.tier,
                "asset_type": r.asset_type,
                "jurisdiction_hint": r.jurisdiction_hint,
                "priority": r.priority,
            }
            for r in session.scalars(
                select(RoleClassificationModel).where(RoleClassificationModel.active.is_(True))
            )
        ]
        classifier = RoleClassifier(db_rules)

        # 4. Fetch from all active bootstrap sources
        bootstrap_sources = list(session.scalars(
            select(DataSourceModel)
            .where(DataSourceModel.bootstrap.is_(True), DataSourceModel.active.is_(True))
        ))
        if not bootstrap_sources:
            print("bootstrap: no active bootstrap sources configured", flush=True)
            return 0

        all_raw: list[RawPolitician] = []
        for ds in bootstrap_sources:
            adapter_cls = _ADAPTER_MAP.get(ds.source_type)
            if adapter_cls is None:
                print(f"bootstrap: unknown adapter source_type={ds.source_type!r} ({ds.name})", flush=True)
                continue
            adapter = adapter_cls(ds.name, ds.url_template, ds.config_json or {})
            try:
                records = adapter.fetch()
                all_raw.extend(records)
            except Exception as exc:  # noqa: BLE001
                print(f"bootstrap: adapter {ds.name!r} raised unexpectedly — {exc}", flush=True)

        # 5. Deduplicate by normalised full_name (first occurrence per name wins)
        seen: dict[str, RawPolitician] = {}
        for raw in all_raw:
            key = raw.full_name.lower().strip()
            if key and key not in seen:
                seen[key] = raw

        if not seen:
            print("bootstrap: no politicians fetched from any source", flush=True)
            return 0

        # 6. Classify and write PoliticianModel rows + per-politician RSS sources
        written = 0
        for raw in seen.values():
            cl = classifier.classify(raw.role_title, raw.jurisdiction)
            pol_id = f"pol-{_slug(raw.full_name)}"
            session.add(PoliticianModel(
                id=pol_id,
                full_name=raw.full_name,
                aliases_json=[],          # empty on bootstrap; admin enriches via API
                current_role=raw.role_title,
                role_tier=cl["tier"],
                party=raw.party or "Unknown",
                jurisdiction=cl["jurisdiction"],
                asset_type=cl["asset_type"],
                status="active",
                source=raw.source,
                last_verified_at=_utcnow(),
            ))
            # Per-politician Google News RSS feed for the ingest worker
            encoded_name = raw.full_name.replace(" ", "+")
            session.add(DataSourceModel(
                id=f"ds-{uuid4().hex[:10]}",
                name=f"Google News — {raw.full_name}",
                source_type="rss",
                bootstrap=False,
                url_template=(
                    f"https://news.google.com/rss/search"
                    f"?q=%22{encoded_name}%22&hl=en-CA&gl=CA&ceid=CA:en"
                ),
                config_json={"weight": 1.0, "trust": 0.70},
                active=True,
                politician_id=pol_id,
            ))
            written += 1

        # 7. Migrate legacy mp-* roster_slot asset IDs to pol-* equivalents
        self._migrate_legacy_asset_ids(session)

        print(f"bootstrap: seeded {written} politicians from {len(bootstrap_sources)} sources", flush=True)
        return written

    # ── private helpers ──────────────────────────────────────────────────────

    def _seed_system_config(self, session: "Session", SystemConfigModel, select) -> None:
        for key, value in DEFAULT_SYSTEM_CONFIG.items():
            if session.scalar(select(SystemConfigModel).where(SystemConfigModel.key == key)) is None:
                session.add(SystemConfigModel(key=key, value_json=value, updated_at=_utcnow(), updated_by="bootstrap"))

    def _seed_role_classifications(self, session: "Session", RoleClassificationModel, select) -> None:
        if session.scalar(select(RoleClassificationModel).limit(1)) is not None:
            return
        for rc in DEFAULT_ROLE_CLASSIFICATIONS:
            session.add(RoleClassificationModel(
                id=f"rc-{uuid4().hex[:10]}",
                pattern=rc["pattern"],
                tier=rc["tier"],
                asset_type=rc["asset_type"],
                jurisdiction_hint=rc.get("jurisdiction_hint"),
                priority=rc.get("priority", 50),
                active=True,
            ))

    def _seed_data_sources(self, session: "Session", DataSourceModel, select) -> None:
        for ds in DEFAULT_BOOTSTRAP_SOURCES:
            if session.scalar(select(DataSourceModel).where(DataSourceModel.name == ds["name"])) is None:
                session.add(DataSourceModel(
                    id=f"ds-{uuid4().hex[:10]}",
                    name=ds["name"],
                    source_type=ds["source_type"],
                    bootstrap=ds.get("bootstrap", False),
                    url_template=ds["url_template"],
                    config_json=ds.get("config_json", {}),
                    active=ds.get("active", True),
                    politician_id=None,
                ))

    def _seed_scoring_rules(self, session: "Session", ScoringRuleModel, select) -> None:
        if session.scalar(select(ScoringRuleModel).limit(1)) is not None:
            return
        for event_type, asset_type, base, affinity, jscope, desc in DEFAULT_SCORING_RULES:
            session.add(ScoringRuleModel(
                id=f"rule-{uuid4().hex[:10]}",
                rule_version="v1",
                event_type=event_type,
                asset_type=asset_type,
                base_points=base,
                affinity_bonus=affinity,
                jurisdiction_scope=jscope,
                description=desc,
                active=True,
            ))

    def _migrate_legacy_asset_ids(self, session: "Session") -> None:
        """
        Best-effort: rewrite roster_slots.asset_id rows that still use the old
        mp-* prefix to the pol-* IDs generated by bootstrap.
        The pol-* ID is derived from the same _slug() function used above,
        so it can be recomputed from the politician's full_name via the DB.
        """
        from app.api.v1.persistent_store import PoliticianModel, RosterSlotModel  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        old_slots = list(session.scalars(
            select(RosterSlotModel).where(RosterSlotModel.asset_id.like("mp-%"))
        ))
        if not old_slots:
            return

        all_politicians = {p.id: p for p in session.scalars(select(PoliticianModel))}
        for slot in old_slots:
            # Convert "mp-fed-pm" → "pol-fed-pm" as best-effort candidate
            candidate = "pol-" + slot.asset_id[3:]
            if candidate in all_politicians:
                slot.asset_id = candidate
                continue
            # No direct match — leave as-is, admin can correct via PATCH /politicians
        print(f"bootstrap: migrated legacy asset IDs in roster_slots (candidates checked: {len(old_slots)})", flush=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

_PROVINCE_CODE_MAP: dict[str, str] = {
    "ontario": "ON", "québec": "QC", "quebec": "QC",
    "british columbia": "BC", "alberta": "AB", "saskatchewan": "SK",
    "manitoba": "MB", "nova scotia": "NS", "new brunswick": "NB",
    "newfoundland": "NL", "newfoundland and labrador": "NL",
    "prince edward island": "PE", "pei": "PE",
    "northwest territories": "NT", "nunavut": "NU", "yukon": "YT",
}


def _province_to_code(province: str) -> str:
    p = province.strip().lower()
    if len(p) == 2:
        return p.upper()
    return _PROVINCE_CODE_MAP.get(p, "federal")
