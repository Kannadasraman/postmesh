from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlparse

import httpx

from app.models.research_item import ResearchItem


@dataclass(frozen=True)
class EvidenceBundle:
    title: str
    summary: str
    source: str
    url: str
    enriched: bool


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = unescape(value)

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def is_useful_summary(
    title: str,
    summary: str,
) -> bool:
    title_normalized = normalize_text(
        title,
    ).lower()

    summary_normalized = normalize_text(
        summary,
    ).lower()

    if not summary_normalized:
        return False

    if summary_normalized == title_normalized:
        return False

    if len(summary_normalized) < 100:
        return False

    title_without_source = re.sub(
        r"\s+-\s+[^-]+$",
        "",
        title_normalized,
    ).strip()

    if (
        title_without_source
        and title_without_source
        in summary_normalized
    ):
        remaining = summary_normalized.replace(
            title_without_source,
            "",
            1,
        ).strip()

        if len(remaining) < 70:
            return False

    return True


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()

        self.descriptions: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        if tag.lower() != "meta":
            return

        attributes = {
            key.lower(): value
            for key, value in attrs
            if value is not None
        }

        metadata_name = (
            attributes.get("name")
            or attributes.get("property")
            or ""
        ).lower()

        if metadata_name not in {
            "description",
            "og:description",
            "twitter:description",
        }:
            return

        content = normalize_text(
            attributes.get("content"),
        )

        if content:
            self.descriptions.append(
                content,
            )


def _safe_public_url(
    url: str,
) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    hostname = (
        parsed.hostname or ""
    ).lower()

    if not hostname:
        return False

    if hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        return False

    return True


def _fetch_metadata_description(
    url: str,
) -> str:
    if not _safe_public_url(url):
        return ""

    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=10.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36 "
                    "PostMesh/0.1"
                ),
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml"
                ),
            },
        )

        response.raise_for_status()

    except httpx.HTTPError:
        return ""

    content_type = response.headers.get(
        "content-type",
        "",
    ).lower()

    if "html" not in content_type:
        return ""

    html = response.text[
        :750_000
    ]

    parser = MetadataParser()

    try:
        parser.feed(html)
    except Exception:
        return ""

    if not parser.descriptions:
        return ""

    candidates = sorted(
        {
            normalize_text(description)
            for description
            in parser.descriptions
            if normalize_text(description)
        },
        key=len,
        reverse=True,
    )

    if not candidates:
        return ""

    return candidates[0]


def get_research_evidence(
    research_item: ResearchItem,
) -> EvidenceBundle:
    title = normalize_text(
        research_item.title,
    )

    stored_summary = normalize_text(
        research_item.summary,
    )

    source = normalize_text(
        research_item.source,
    )

    if is_useful_summary(
        title,
        stored_summary,
    ):
        return EvidenceBundle(
            title=title,
            summary=stored_summary,
            source=source,
            url=research_item.url,
            enriched=False,
        )

    enriched_summary = (
        _fetch_metadata_description(
            research_item.url,
        )
    )

    if is_useful_summary(
        title,
        enriched_summary,
    ):
        return EvidenceBundle(
            title=title,
            summary=enriched_summary,
            source=source,
            url=research_item.url,
            enriched=True,
        )

    return EvidenceBundle(
        title=title,
        summary=stored_summary,
        source=source,
        url=research_item.url,
        enriched=False,
    )