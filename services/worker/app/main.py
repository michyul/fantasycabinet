import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import httpx


API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")
AUTO_SCORE_ENABLED = os.getenv("WORKER_AUTO_SCORE", "true").lower() == "true"
SCORING_INTERVAL_SECONDS = int(os.getenv("WORKER_SCORING_INTERVAL_SECONDS", "60"))
REAL_DATA_INGEST_ENABLED = os.getenv("WORKER_REAL_DATA_INGEST", "true").lower() == "true"

# Bootstrap feed URLs — used ONLY as a fallback when the API is not yet available.
# In normal operation the worker fetches active RSS sources from the API's data_sources table.
_FALLBACK_FEEDS = [
    "https://news.google.com/rss/search?q=canadian+politics&hl=en-CA&gl=CA&ceid=CA:en",
    "https://news.google.com/rss/search?q=ontario+politics&hl=en-CA&gl=CA&ceid=CA:en",
]


def _fetch_active_rss_feeds(client: httpx.Client) -> list[str]:
    """Fetch active RSS feed URLs from the API's data_sources table."""
    try:
        resp = client.get(
            f"{API_BASE_URL}/api/v1/internal/data-sources",
            params={"active": "true"},
            timeout=8.0,
        )
        resp.raise_for_status()
        sources = resp.json().get("items", [])
        urls = [s["url_template"] for s in sources if s.get("source_type") == "rss" and s.get("url_template")]
        if urls:
            return urls
    except Exception as exc:  # noqa: BLE001
        print(f"worker: could not fetch data-sources from API, using fallback feeds: {exc}", flush=True)
    return list(_FALLBACK_FEEDS)


def run() -> None:
    while True:
        if AUTO_SCORE_ENABLED:
            print("worker cycle: start", flush=True)
            if REAL_DATA_INGEST_ENABLED:
                inserted_ids = ingest_real_political_data()
                if inserted_ids:
                    trigger_attribution(inserted_ids)
                    trigger_story_clustering()
            trigger_scoring_for_all_scopes()
            print("worker cycle: done", flush=True)
        else:
            print("worker heartbeat: auto scoring disabled", flush=True)
        time.sleep(SCORING_INTERVAL_SECONDS)


def ingest_real_political_data() -> list[str]:
    """
    Fetch RSS feeds from DB-driven sources and ingest new events.
    Returns list of newly-inserted event IDs for attribution.
    """
    events: list[dict] = []
    with httpx.Client(timeout=12.0) as client:
        feed_urls = _fetch_active_rss_feeds(client)
        for feed_url in feed_urls:
            try:
                feed_response = client.get(feed_url)
                feed_response.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                print(f"worker ingest warning: feed fetch failed url={feed_url} err={exc}", flush=True)
                continue

            parsed = feedparser.parse(feed_response.text)
            source_name = _source_name_from_url(feed_url)
            for entry in parsed.entries[:30]:
                title = str(entry.get("title", "")).strip()
                link = str(entry.get("link", "")).strip() or None
                entry_id = str(entry.get("id") or entry.get("guid") or link or title)
                if not title or not entry_id:
                    continue

                jurisdiction = _infer_jurisdiction(title)
                event_type = _infer_event_type(title)
                occurred_at = _infer_timestamp(entry)

                events.append(
                    {
                        "source_name": source_name,
                        "source_event_id": entry_id,
                        "title": title,
                        "url": link,
                        "occurred_at": occurred_at,
                        "jurisdiction": jurisdiction,
                        "event_type": event_type,
                        "payload": {
                            "summary": str(entry.get("summary", ""))[:1000],
                            "author": str(entry.get("author", ""))[:200],
                            "feed": feed_url,
                        },
                    }
                )

    if not events:
        print("worker ingest: no events fetched", flush=True)
        return []

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{API_BASE_URL}/api/v1/internal/events/ingest",
                json={"events": events},
            )
            response.raise_for_status()
            result = response.json()
            print(
                f"worker ingest: received={result.get('received')} inserted={result.get('inserted')} duplicates={result.get('duplicates')}",
                flush=True,
            )
            # The ingest endpoint returns inserted event IDs when available
            return result.get("inserted_ids", [])
    except Exception as exc:  # noqa: BLE001
        print(f"worker warning: ingest failed: {exc}", flush=True)
        return []


def trigger_attribution(event_ids: list[str]) -> None:
    """Ask the API to run attribution for the newly-ingested event IDs."""
    if not event_ids:
        return
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{API_BASE_URL}/api/v1/internal/attribution/run",
                json={"event_ids": event_ids},
            )
            resp.raise_for_status()
            result = resp.json()
            print(
                f"worker attribution: processed={result.get('event_ids_processed')} written={result.get('attributions_written')}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"worker warning: attribution failed: {exc}", flush=True)


def trigger_story_clustering(window_hours: int = 24) -> None:
    """
    Ask the API to cluster recently-ingested articles into canonical news stories.
    Uses Ollama AI when ai_enabled=true; falls back to Jaccard heuristic.
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{API_BASE_URL}/api/v1/internal/stories/cluster",
                json={"window_hours": window_hours},
            )
            resp.raise_for_status()
            result = resp.json()
            print(
                f"worker clustering: created={result.get('stories_created')} "
                f"updated={result.get('stories_updated')} "
                f"articles={result.get('articles_assigned')} "
                f"rescore_triggers={result.get('rescore_triggers')}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"worker warning: story clustering failed: {exc}", flush=True)


def trigger_scoring_for_all_scopes() -> None:
    try:
        with httpx.Client(timeout=10.0) as client:
            scopes_response = client.get(f"{API_BASE_URL}/api/v1/cabinet-scopes")
            scopes_response.raise_for_status()
            scopes = scopes_response.json().get("items", [])

            for scope in scopes:
                scope_id = scope.get("id")
                if not scope_id:
                    continue
                score_response = client.post(
                    f"{API_BASE_URL}/api/v1/internal/scoring/run",
                    json={"league_id": scope_id},
                )
                score_response.raise_for_status()
                payload = score_response.json()
                print(
                    f"worker scoring complete scope={payload.get('league_id')} week={payload.get('week_scored')} entries={payload.get('entries_created')}",
                    flush=True,
                )
    except Exception as exc:  # noqa: BLE001
        print(f"worker warning: scoring cycle failed: {exc}", flush=True)


def _infer_timestamp(entry: dict) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed_time = entry.get(key)
        if parsed_time:
            epoch = time.mktime(parsed_time)
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _infer_jurisdiction(title: str) -> str:
    text = title.lower()
    province_map = {
        "ontario": "ON",
        "québec": "QC",
        "quebec": "QC",
        "british columbia": "BC",
        "b.c.": "BC",
        "alberta": "AB",
        "saskatchewan": "SK",
        "manitoba": "MB",
        "nova scotia": "NS",
        "new brunswick": "NB",
        "newfoundland": "NL",
        "pei": "PE",
        "prince edward island": "PE",
    }
    for token, code in province_map.items():
        if token in text:
            return code
    return "federal"


def _infer_event_type(title: str) -> str:
    text = title.lower()
    if any(word in text for word in ["confidence vote", "confidence motion", "non-confidence", "vote de confiance"]):
        return "confidence"
    if any(word in text for word in ["bill", "house", "senate", "committee", "legislation", "loi", "projet de loi"]):
        return "legislative"
    if any(word in text for word in ["policy", "platform", "program", "budget", "plan", "spending", "announce"]):
        return "policy"
    if any(word in text for word in ["premier", "prime minister", "cabinet", "minister", "ministre", "premier ministre"]):
        return "executive"
    if any(word in text for word in ["opposition", "critic", "shadow", "critique"]):
        return "opposition"
    if any(word in text for word in ["election", "campaign", "poll", "élection", "vote"]):
        return "election"
    if any(word in text for word in ["agreement", "federal-provincial", "summit", "accord", "entente", "intergovernmental"]):
        return "intergovernmental"
    if any(word in text for word in ["ethics", "scandal", "investigation", "resignation", "éthique", "scandale"]):
        return "ethics"
    return "general"


def _source_name_from_url(feed_url: str) -> str:
    try:
        host = urlparse(feed_url).netloc
        return host.replace("www.", "")
    except Exception:  # noqa: BLE001
        return "rss-source"


if __name__ == "__main__":
    run()
