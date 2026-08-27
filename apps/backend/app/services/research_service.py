import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research_item import ResearchItem
from app.models.topic import Topic


USER_AGENT = (
    "Mozilla/5.0 (compatible; PostMesh/0.1; "
    "+https://localhost)"
)

REQUEST_TIMEOUT = 12.0


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None

    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def _parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _topic_keywords(topic: Topic) -> list[str]:
    keywords = []

    if topic.keywords:
        keywords = [
            item.strip()
            for item in topic.keywords.split(",")
            if item.strip()
        ]

    return [topic.name, *keywords]


def _search_query(topic: Topic) -> str:
    keywords = _topic_keywords(topic)

    return " ".join(keywords[:5])


def _search_tokens(topic: Topic) -> set[str]:
    raw = " ".join(_topic_keywords(topic)).lower()

    tokens = set(
        re.findall(
            r"[a-z0-9][a-z0-9+#.-]{1,}",
            raw,
        )
    )

    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "into",
        "about",
    }

    return tokens - stop_words


def _score_item(
    title: str,
    published_at: datetime | None,
    topic: Topic,
) -> float:
    title_lower = title.lower()
    tokens = _search_tokens(topic)

    if tokens:
        matches = sum(
            1
            for token in tokens
            if token in title_lower
        )

        relevance = min(
            1.0,
            matches / max(1, min(len(tokens), 5)),
        )
    else:
        relevance = 0.5

    freshness = 0.20

    if published_at:
        now = datetime.now(timezone.utc)

        age_hours = max(
            0,
            (now - published_at).total_seconds() / 3600,
        )

        if age_hours <= 24:
            freshness = 1.0
        elif age_hours <= 72:
            freshness = 0.85
        elif age_hours <= 168:
            freshness = 0.70
        elif age_hours <= 720:
            freshness = 0.45

    score = (relevance * 0.70) + (freshness * 0.30)

    return round(score, 3)


def _fetch_google_news(topic: Topic) -> list[dict]:
    query = quote_plus(_search_query(topic))

    url = (
        "https://news.google.com/rss/search"
        f"?q={query}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )

    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()

        root = ElementTree.fromstring(response.content)

        results = []

        for item in root.findall(".//item")[:20]:
            title = item.findtext("title")
            link = item.findtext("link")
            published = item.findtext("pubDate")
            description = item.findtext("description")

            source_element = item.find("source")

            source = (
                source_element.text.strip()
                if source_element is not None
                and source_element.text
                else "Google News"
            )

            if not title or not link:
                continue

            results.append(
                {
                    "title": title.strip(),
                    "url": link.strip(),
                    "source": source,
                    "summary": _clean_html(description),
                    "published_at": _parse_rss_date(
                        published
                    ),
                }
            )

        return results

    except (
        httpx.HTTPError,
        ElementTree.ParseError,
    ):
        return []


def _fetch_hacker_news(topic: Topic) -> list[dict]:
    query = _search_query(topic)

    try:
        response = httpx.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": query,
                "tags": "story",
                "hitsPerPage": 20,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        results = []

        for hit in data.get("hits", []):
            title = (
                hit.get("title")
                or hit.get("story_title")
            )

            object_id = hit.get("objectID")

            url = (
                hit.get("url")
                or hit.get("story_url")
                or (
                    f"https://news.ycombinator.com/item?id={object_id}"
                    if object_id
                    else None
                )
            )

            if not title or not url:
                continue

            results.append(
                {
                    "title": title.strip(),
                    "url": url.strip(),
                    "source": "Hacker News",
                    "summary": None,
                    "published_at": _parse_iso_date(
                        hit.get("created_at")
                    ),
                }
            )

        return results

    except (
        httpx.HTTPError,
        ValueError,
    ):
        return []


def _deduplicate(items: list[dict]) -> list[dict]:
    deduplicated = []
    seen_urls = set()
    seen_titles = set()

    for item in items:
        url = item["url"].strip()
        title_key = re.sub(
            r"\W+",
            " ",
            item["title"].lower(),
        ).strip()

        if url in seen_urls:
            continue

        if title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)

        deduplicated.append(item)

    return deduplicated


def run_research(
    db: Session,
    topic: Topic,
) -> list[ResearchItem]:
    candidates = [
        *_fetch_google_news(topic),
        *_fetch_hacker_news(topic),
    ]

    candidates = _deduplicate(candidates)

    for candidate in candidates:
        candidate["relevance_score"] = _score_item(
            candidate["title"],
            candidate["published_at"],
            topic,
        )

    candidates.sort(
        key=lambda item: item["relevance_score"],
        reverse=True,
    )

    candidates = candidates[:20]

    for candidate in candidates:
        existing = db.scalar(
            select(ResearchItem).where(
                ResearchItem.topic_id == topic.id,
                ResearchItem.url == candidate["url"],
            )
        )

        if existing:
            existing.title = candidate["title"]
            existing.source = candidate["source"]
            existing.summary = candidate["summary"]
            existing.published_at = candidate[
                "published_at"
            ]
            existing.relevance_score = candidate[
                "relevance_score"
            ]
            continue

        db.add(
            ResearchItem(
                topic_id=topic.id,
                title=candidate["title"],
                url=candidate["url"],
                source=candidate["source"],
                summary=candidate["summary"],
                published_at=candidate[
                    "published_at"
                ],
                relevance_score=candidate[
                    "relevance_score"
                ],
            )
        )

    db.commit()

    return list(
        db.scalars(
            select(ResearchItem)
            .where(
                ResearchItem.topic_id == topic.id
            )
            .order_by(
                ResearchItem.relevance_score.desc(),
                ResearchItem.published_at.desc(),
            )
            .limit(20)
        ).all()
    )


def get_research(
    db: Session,
    topic: Topic,
) -> list[ResearchItem]:
    return list(
        db.scalars(
            select(ResearchItem)
            .where(
                ResearchItem.topic_id == topic.id
            )
            .order_by(
                ResearchItem.relevance_score.desc(),
                ResearchItem.published_at.desc(),
            )
            .limit(20)
        ).all()
    )
