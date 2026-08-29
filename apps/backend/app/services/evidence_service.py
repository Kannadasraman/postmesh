from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from html.parser import HTMLParser
import base64
import ipaddress
import json
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research_item import ResearchItem


REQUEST_TIMEOUT = 12.0
GOOGLE_NEWS_TIMEOUT = 15.0

USER_AGENT = (
    "Mozilla/5.0 "
    "(Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 "
    "PostMesh/0.3"
)
MAX_HTML_CHARS = 1_000_000
MAX_EVIDENCE_CHARS = 4_200
MAX_ARTICLE_PARAGRAPHS = 8
RELATED_EVIDENCE_THRESHOLD = 0.52
MAX_RELATED_EVIDENCE_ATTEMPTS = 4

ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "analysisnewsarticle",
    "report",
    "blogposting",
    "techarticle",
}

SKIP_TAGS = {
    "nav",
    "footer",
    "aside",
    "form",
    "noscript",
    "svg",
    "style",
}


@dataclass(frozen=True)
class EvidenceBundle:
    title: str
    summary: str
    source: str
    url: str
    enriched: bool
    extraction_method: str = "stored"
    selected_source: str = ""
    selected_url: str = ""
    evidence_title: str = ""


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = unescape(
        value,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _title_without_source(
    title: str,
) -> str:
    normalized = normalize_text(
        title,
    )

    return re.sub(
        r"\s+-\s+[^-]+$",
        "",
        normalized,
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

    if len(
        summary_normalized
    ) < 100:
        return False

    title_core = _title_without_source(
        title_normalized,
    )

    if (
        title_core
        and title_core
        in summary_normalized
    ):
        remaining = (
            summary_normalized.replace(
                title_core,
                "",
                1,
            ).strip()
        )

        if len(remaining) < 70:
            return False

    words = re.findall(
        r"[a-z0-9]+",
        summary_normalized,
    )

    if len(words) < 16:
        return False

    return True


def _safe_public_url(
    url: str,
) -> bool:
    try:
        parsed = urlparse(
            url,
        )
    except ValueError:
        return False

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    hostname = (
        parsed.hostname or ""
    ).strip().lower()

    if not hostname:
        return False

    if (
        hostname == "localhost"
        or hostname.endswith(
            ".localhost"
        )
        or hostname.endswith(
            ".local"
        )
    ):
        return False

    try:
        ip = ipaddress.ip_address(
            hostname,
        )
    except ValueError:
        return True

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )



def _is_google_news_url(
    url: str,
) -> bool:
    try:
        parsed = urlparse(
            url,
        )
    except ValueError:
        return False

    hostname = (
        parsed.hostname or ""
    ).lower()

    if hostname != "news.google.com":
        return False

    path_parts = [
        part
        for part in parsed.path.split(
            "/"
        )
        if part
    ]

    return (
        "articles" in path_parts
        or "read" in path_parts
    )


def _google_news_article_id(
    url: str,
) -> str:
    try:
        parsed = urlparse(
            url,
        )
    except ValueError:
        return ""

    path_parts = [
        part
        for part in parsed.path.split(
            "/"
        )
        if part
    ]

    if not path_parts:
        return ""

    return path_parts[-1].strip()


def _legacy_google_news_decode(
    article_id: str,
) -> str:
    if not article_id:
        return ""

    try:
        padding = (
            "="
            * (
                -len(article_id)
                % 4
            )
        )

        decoded = (
            base64.urlsafe_b64decode(
                article_id
                + padding
            )
        )
    except (
        ValueError,
        TypeError,
    ):
        return ""

    for prefix in (
        b"https://",
        b"http://",
    ):
        start = decoded.find(
            prefix,
        )

        if start == -1:
            continue

        end = start

        while (
            end < len(decoded)
            and 32
            <= decoded[end]
            < 127
        ):
            end += 1

        candidate = decoded[
            start:end
        ].decode(
            "utf-8",
            errors="ignore",
        ).strip()

        if (
            candidate
            and _safe_public_url(
                candidate,
            )
            and not _is_google_news_url(
                candidate,
            )
        ):
            return candidate

    return ""


class GoogleNewsParameterParser(
    HTMLParser,
):
    def __init__(
        self,
        article_id: str,
    ) -> None:
        super().__init__(
            convert_charrefs=True,
        )

        self.article_id = article_id
        self.signature = ""
        self.timestamp = ""

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        if tag.lower() != "div":
            return

        attributes = {
            key.lower(): value
            for key, value in attrs
            if value is not None
        }

        if (
            attributes.get(
                "data-n-a-id"
            )
            != self.article_id
        ):
            return

        self.signature = (
            attributes.get(
                "data-n-a-sg",
                "",
            )
        )

        self.timestamp = (
            attributes.get(
                "data-n-a-ts",
                "",
            )
        )


def _google_news_signature(
    url: str,
    article_id: str,
) -> tuple[
    str,
    str,
]:
    try:
        response = httpx.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml"
                ),
                "Accept-Language": (
                    "en-US,en;q=0.9"
                ),
            },
            timeout=GOOGLE_NEWS_TIMEOUT,
            follow_redirects=True,
        )

        response.raise_for_status()

    except httpx.HTTPError:
        return (
            "",
            "",
        )

    parser = GoogleNewsParameterParser(
        article_id,
    )

    try:
        parser.feed(
            response.text[
                :MAX_HTML_CHARS
            ]
        )
    except Exception:
        return (
            "",
            "",
        )

    return (
        parser.signature,
        parser.timestamp,
    )


def _decode_google_news_rpc(
    source_url: str,
    article_id: str,
) -> str:
    if not article_id:
        return ""

    (
        signature,
        timestamp,
    ) = _google_news_signature(
        source_url,
        article_id,
    )

    if (
        not signature
        or not timestamp
    ):
        return ""

    inner_request = (
        '["garturlreq",'
        '[["X","X",["X","X"],null,null,1,1,'
        '"US:en",null,1,null,null,null,null,null,0,1],'
        '"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
        f'"{article_id}",'
        f'{timestamp},'
        f'"{signature}"]'
    )

    payload = [
        "Fbv4je",
        inner_request,
    ]

    try:
        response = httpx.post(
            (
                "https://news.google.com/"
                "_/DotsSplashUi/data/"
                "batchexecute"
                "?rpcids=Fbv4je"
            ),
            headers={
                "User-Agent": USER_AGENT,
                "Referer": (
                    "https://news.google.com/"
                ),
                "Content-Type": (
                    "application/"
                    "x-www-form-urlencoded;"
                    "charset=UTF-8"
                ),
            },
            data={
                "f.req": json.dumps(
                    [
                        [
                            payload
                        ]
                    ],
                    separators=(
                        ",",
                        ":",
                    ),
                ),
            },
            timeout=GOOGLE_NEWS_TIMEOUT,
            follow_redirects=True,
        )

        response.raise_for_status()

    except httpx.HTTPError:
        return ""

    for line in reversed(
        response.text.splitlines()
    ):
        line = line.strip()

        if not line.startswith(
            "["
        ):
            continue

        try:
            outer = json.loads(
                line,
            )

            if (
                not isinstance(
                    outer,
                    list,
                )
                or not outer
                or not isinstance(
                    outer[0],
                    list,
                )
                or len(
                    outer[0]
                ) < 3
            ):
                continue

            nested = json.loads(
                outer[0][2]
            )

            candidate = (
                nested[1]
                if (
                    isinstance(
                        nested,
                        list,
                    )
                    and len(
                        nested
                    ) > 1
                )
                else ""
            )

        except (
            json.JSONDecodeError,
            TypeError,
            IndexError,
        ):
            continue

        if (
            isinstance(
                candidate,
                str,
            )
            and _safe_public_url(
                candidate,
            )
            and not _is_google_news_url(
                candidate,
            )
        ):
            return candidate

    return ""

def _resolve_source_url(
    url: str,
) -> tuple[str, bool]:
    if not _is_google_news_url(
        url,
    ):
        return (
            url,
            False,
        )

    article_id = (
        _google_news_article_id(
            url,
        )
    )

    resolved_url = (
        _legacy_google_news_decode(
            article_id,
        )
    )

    if not resolved_url:
        resolved_url = (
            _decode_google_news_rpc(
                url,
                article_id,
            )
        )

    if (
        resolved_url
        and _safe_public_url(
            resolved_url,
        )
    ):
        return (
            resolved_url,
            True,
        )

    return (
        url,
        True,
    )

def _attrs_to_dict(
    attrs: list[
        tuple[str, str | None]
    ],
) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in attrs
        if value is not None
    }


class ArticleEvidenceParser(
    HTMLParser,
):
    def __init__(
        self,
    ) -> None:
        super().__init__(
            convert_charrefs=True,
        )

        self.descriptions: list[str] = []
        self.json_ld_blocks: list[str] = []
        self.article_paragraphs: list[str] = []
        self.general_paragraphs: list[str] = []

        self._skip_depth = 0
        self._article_depth = 0
        self._main_depth = 0

        self._in_paragraph = False
        self._paragraph_parts: list[str] = []
        self._paragraph_is_article = False

        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        tag = tag.lower()
        attributes = _attrs_to_dict(
            attrs,
        )

        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "article":
            self._article_depth += 1

        if tag == "main":
            self._main_depth += 1

        if tag == "meta":
            metadata_name = (
                attributes.get(
                    "name"
                )
                or attributes.get(
                    "property"
                )
                or ""
            ).lower()

            if metadata_name in {
                "description",
                "og:description",
                "twitter:description",
            }:
                content = normalize_text(
                    attributes.get(
                        "content",
                    )
                )

                if content:
                    self.descriptions.append(
                        content,
                    )

        if tag == "script":
            script_type = (
                attributes.get(
                    "type",
                    ""
                ).lower()
            )

            if (
                "application/ld+json"
                in script_type
            ):
                self._in_json_ld = True
                self._json_ld_parts = []

        if tag == "p":
            self._in_paragraph = True
            self._paragraph_parts = []
            self._paragraph_is_article = (
                self._article_depth > 0
                or self._main_depth > 0
            )

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        tag = tag.lower()

        if tag in SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if (
            tag == "p"
            and self._in_paragraph
        ):
            paragraph = normalize_text(
                " ".join(
                    self._paragraph_parts
                )
            )

            if _useful_paragraph(
                paragraph,
            ):
                if self._paragraph_is_article:
                    self.article_paragraphs.append(
                        paragraph,
                    )
                else:
                    self.general_paragraphs.append(
                        paragraph,
                    )

            self._in_paragraph = False
            self._paragraph_parts = []
            self._paragraph_is_article = False

        if (
            tag == "script"
            and self._in_json_ld
        ):
            block = "".join(
                self._json_ld_parts
            ).strip()

            if block:
                self.json_ld_blocks.append(
                    block,
                )

            self._in_json_ld = False
            self._json_ld_parts = []

        if (
            tag == "article"
            and self._article_depth
        ):
            self._article_depth -= 1

        if (
            tag == "main"
            and self._main_depth
        ):
            self._main_depth -= 1

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self._skip_depth:
            return

        if self._in_json_ld:
            self._json_ld_parts.append(
                data,
            )

        if self._in_paragraph:
            self._paragraph_parts.append(
                data,
            )


def _is_boilerplate_text(
    text: str,
) -> bool:
    lowered = normalize_text(
        text,
    ).lower()

    if not lowered:
        return True

    boilerplate_fragments = (
        "this copy is for your personal, non-commercial use only",
        "subscriber agreement",
        "dow jones reprints",
        "copyright law",
        "for non-personal use",
        "to order multiple copies",
        "all rights reserved",
        "privacy policy",
        "terms of use",
        "cookie policy",
        "sign up for",
        "subscribe to",
        "please enable javascript",
        "disable any ad blocker",
        "advertisement",
    )

    return any(
        fragment in lowered
        for fragment in boilerplate_fragments
    )


def _useful_paragraph(
    paragraph: str,
) -> bool:
    paragraph = normalize_text(
        paragraph,
    )

    if len(paragraph) < 80:
        return False

    if len(paragraph) > 2_000:
        return False

    lowered = paragraph.lower()

    if _is_boilerplate_text(
        paragraph,
    ):
        return False

    boilerplate_starts = (
        "cookie",
        "sign up",
        "subscribe",
        "advertisement",
        "accept cookies",
        "enable javascript",
        "please enable",
        "we sincerely apologize",
    )

    if lowered.startswith(
        boilerplate_starts
    ):
        return False

    words = re.findall(
        r"[a-z0-9]+",
        lowered,
    )

    return len(words) >= 14


def _type_names(
    value: object,
) -> set[str]:
    if isinstance(
        value,
        str,
    ):
        return {
            value.lower(),
        }

    if isinstance(
        value,
        list,
    ):
        return {
            str(item).lower()
            for item in value
        }

    return set()


def _iter_json_ld_nodes(
    value: object,
):
    if isinstance(
        value,
        dict,
    ):
        yield value

        graph = value.get(
            "@graph",
        )

        if isinstance(
            graph,
            list,
        ):
            for child in graph:
                yield from _iter_json_ld_nodes(
                    child,
                )

        for key, child in value.items():
            if key == "@graph":
                continue

            if isinstance(
                child,
                (
                    dict,
                    list,
                ),
            ):
                yield from _iter_json_ld_nodes(
                    child,
                )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from _iter_json_ld_nodes(
                child,
            )


def _extract_json_ld_evidence(
    blocks: list[str],
) -> list[str]:
    evidence: list[str] = []

    for block in blocks:
        try:
            data = json.loads(
                block,
            )
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            continue

        for node in _iter_json_ld_nodes(
            data,
        ):
            node_types = _type_names(
                node.get(
                    "@type"
                )
            )

            if not (
                node_types
                & ARTICLE_TYPES
            ):
                continue

            description = normalize_text(
                node.get(
                    "description"
                )
                if isinstance(
                    node.get(
                        "description"
                    ),
                    str,
                )
                else ""
            )

            article_body = normalize_text(
                node.get(
                    "articleBody"
                )
                if isinstance(
                    node.get(
                        "articleBody"
                    ),
                    str,
                )
                else ""
            )

            if description:
                evidence.append(
                    description,
                )

            if article_body:
                evidence.append(
                    article_body,
                )

    return evidence


def _deduplicate_texts(
    values: list[str],
) -> list[str]:
    result: list[str] = []
    fingerprints: set[str] = set()

    for value in values:
        cleaned = normalize_text(
            value,
        )

        if not cleaned:
            continue

        if _is_boilerplate_text(
            cleaned,
        ):
            continue

        fingerprint = re.sub(
            r"\W+",
            " ",
            cleaned.lower(),
        ).strip()

        if not fingerprint:
            continue

        if fingerprint in fingerprints:
            continue

        duplicate = False

        for existing in result:
            existing_fp = re.sub(
                r"\W+",
                " ",
                existing.lower(),
            ).strip()

            shorter = min(
                len(fingerprint),
                len(existing_fp),
            )

            if (
                shorter >= 80
                and (
                    fingerprint
                    in existing_fp
                    or existing_fp
                    in fingerprint
                )
            ):
                duplicate = True
                break

        if duplicate:
            continue

        fingerprints.add(
            fingerprint,
        )

        result.append(
            cleaned,
        )

    return result


def _compose_evidence(
    title: str,
    stored_summary: str,
    parser: ArticleEvidenceParser,
) -> tuple[str, str]:
    json_ld = (
        _extract_json_ld_evidence(
            parser.json_ld_blocks,
        )
    )

    article_paragraphs = (
        parser.article_paragraphs[
            :MAX_ARTICLE_PARAGRAPHS
        ]
    )

    if not article_paragraphs:
        article_paragraphs = (
            parser.general_paragraphs[
                :MAX_ARTICLE_PARAGRAPHS
            ]
        )

    candidates = _deduplicate_texts(
        [
            stored_summary,
            *parser.descriptions,
            *json_ld,
            *article_paragraphs,
        ]
    )

    useful = [
        candidate
        for candidate in candidates
        if is_useful_summary(
            title,
            candidate,
        )
    ]

    if not useful:
        return (
            stored_summary,
            "stored",
        )

    parts: list[str] = []
    total_chars = 0

    for candidate in useful:
        remaining = (
            MAX_EVIDENCE_CHARS
            - total_chars
        )

        if remaining < 120:
            break

        addition = candidate[
            :remaining
        ].strip()

        if not addition:
            continue

        parts.append(
            addition,
        )

        total_chars += (
            len(addition)
            + 2
        )

    combined = "\n\n".join(
        parts,
    ).strip()

    if not combined:
        return (
            stored_summary,
            "stored",
        )

    if json_ld:
        method = "json-ld+page"
    elif article_paragraphs:
        method = "article-page"
    else:
        method = "metadata"

    return (
        combined,
        method,
    )


def _fetch_page_evidence(
    url: str,
    title: str,
    stored_summary: str,
) -> tuple[
    str,
    str,
    str,
]:
    (
        resolved_url,
        was_google_news,
    ) = _resolve_source_url(
        url,
    )

    if (
        was_google_news
        and _is_google_news_url(
            resolved_url,
        )
    ):
        return (
            stored_summary,
            "stored",
            url,
        )

    if not _safe_public_url(
        resolved_url,
    ):
        return (
            stored_summary,
            "stored",
            url,
        )

    try:
        response = httpx.get(
            resolved_url,
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml"
                ),
                "Accept-Language": (
                    "en-US,en;q=0.9"
                ),
            },
        )

        response.raise_for_status()

        final_url = str(
            response.url,
        )

        if not _safe_public_url(
            final_url,
        ):
            return (
                stored_summary,
                "stored",
                resolved_url,
            )

        if _is_google_news_url(
            final_url,
        ):
            return (
                stored_summary,
                "stored",
                url,
            )

    except httpx.HTTPError:
        return (
            stored_summary,
            "stored",
            resolved_url,
        )

    content_type = (
        response.headers.get(
            "content-type",
            "",
        ).lower()
    )

    if (
        "html" not in content_type
        and "xhtml" not in content_type
    ):
        return (
            stored_summary,
            "stored",
            final_url,
        )

    page_html = response.text[
        :MAX_HTML_CHARS
    ]

    parser = ArticleEvidenceParser()

    try:
        parser.feed(
            page_html,
        )
    except Exception:
        return (
            stored_summary,
            "stored",
            final_url,
        )

    (
        evidence_text,
        method,
    ) = _compose_evidence(
        title=title,
        stored_summary=stored_summary,
        parser=parser,
    )

    if (
        was_google_news
        and method != "stored"
    ):
        method = (
            "google-news+"
            + method
        )

    return (
        evidence_text,
        method,
        final_url,
    )


RELATED_TITLE_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "about",
    "latest",
    "news",
    "update",
    "updates",
    "report",
    "reports",
    "reported",
    "says",
    "say",
    "amid",
    "over",
    "some",
    "its",
    "new",
    "why",
    "could",
    "would",
    "after",
    "before",
    "under",
    "more",
    "than",
    "what",
    "when",
    "where",
    "who",
    "how",
    "wsj",
}


def _normalized_story_title(
    title: str,
) -> str:
    title = _title_without_source(
        title,
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        title.lower(),
    ).strip()


def _story_tokens(
    title: str,
) -> set[str]:
    return {
        token
        for token in _normalized_story_title(
            title,
        ).split()
        if (
            len(token) > 1
            and token
            not in RELATED_TITLE_STOP_WORDS
        )
    }


def _story_similarity(
    selected_title: str,
    candidate_title: str,
) -> float:
    selected_tokens = _story_tokens(
        selected_title,
    )

    candidate_tokens = _story_tokens(
        candidate_title,
    )

    if (
        not selected_tokens
        or not candidate_tokens
    ):
        return 0.0

    overlap = (
        selected_tokens
        & candidate_tokens
    )

    if len(overlap) < 3:
        return 0.0

    union = (
        selected_tokens
        | candidate_tokens
    )

    jaccard = (
        len(overlap)
        / len(union)
    )

    containment = (
        len(overlap)
        / min(
            len(selected_tokens),
            len(candidate_tokens),
        )
    )

    sequence = SequenceMatcher(
        None,
        _normalized_story_title(
            selected_title,
        ),
        _normalized_story_title(
            candidate_title,
        ),
    ).ratio()

    score = (
        containment * 0.55
        + jaccard * 0.25
        + sequence * 0.20
    )

    return round(
        min(
            1.0,
            score,
        ),
        3,
    )


def _direct_research_evidence(
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

    (
        evidence_text,
        method,
        resolved_url,
    ) = _fetch_page_evidence(
        url=research_item.url,
        title=title,
        stored_summary=stored_summary,
    )

    enriched = (
        method != "stored"
        and is_useful_summary(
            title,
            evidence_text,
        )
    )

    if not is_useful_summary(
        title,
        evidence_text,
    ):
        evidence_text = (
            stored_summary
        )

        method = "stored"
        enriched = False

    return EvidenceBundle(
        title=title,
        summary=evidence_text,
        source=source,
        url=resolved_url,
        enriched=enriched,
        extraction_method=method,
        selected_source=source,
        selected_url=resolved_url,
        evidence_title=title,
    )


def _related_research_items(
    db: Session,
    research_item: ResearchItem,
) -> list[
    tuple[
        float,
        ResearchItem,
    ]
]:
    candidates = list(
        db.scalars(
            select(
                ResearchItem
            )
            .where(
                ResearchItem.topic_id
                == research_item.topic_id,
                ResearchItem.id
                != research_item.id,
                ResearchItem.relevance_score
                > 0,
            )
            .limit(80)
        ).all()
    )

    scored: list[
        tuple[
            float,
            ResearchItem,
        ]
    ] = []

    for candidate in candidates:
        if (
            candidate.url
            == research_item.url
        ):
            continue

        similarity = (
            _story_similarity(
                research_item.title,
                candidate.title,
            )
        )

        if (
            similarity
            < RELATED_EVIDENCE_THRESHOLD
        ):
            continue

        scored.append(
            (
                similarity,
                candidate,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0],
            (
                item[1].relevance_score
                or 0.0
            ),
        ),
        reverse=True,
    )

    return scored


def get_research_evidence(
    research_item: ResearchItem,
    db: Session | None = None,
) -> EvidenceBundle:
    direct = (
        _direct_research_evidence(
            research_item,
        )
    )

    if (
        direct.enriched
        or db is None
    ):
        return direct

    related_items = (
        _related_research_items(
            db,
            research_item,
        )
    )

    evidence_options: list[
        tuple[
            float,
            float,
            EvidenceBundle,
        ]
    ] = []

    for (
        similarity,
        related_item,
    ) in related_items[
        :MAX_RELATED_EVIDENCE_ATTEMPTS
    ]:
        related_evidence = (
            _direct_research_evidence(
                related_item,
            )
        )

        if not (
            related_evidence.enriched
            and is_useful_summary(
                related_evidence.title,
                related_evidence.summary,
            )
        ):
            continue

        evidence_length_score = min(
            1.0,
            len(
                related_evidence.summary
            )
            / 2_500,
        )

        support_score = (
            similarity * 0.70
            + evidence_length_score * 0.30
        )

        evidence_options.append(
            (
                support_score,
                similarity,
                related_evidence,
            )
        )

    if not evidence_options:
        return direct

    evidence_options.sort(
        key=lambda option: (
            option[0],
            option[1],
        ),
        reverse=True,
    )

    (
        support_score,
        similarity,
        related_evidence,
    ) = evidence_options[0]

    return EvidenceBundle(
        title=normalize_text(
            research_item.title,
        ),
        summary=related_evidence.summary,
        source=related_evidence.source,
        url=related_evidence.url,
        enriched=True,
        extraction_method=(
            "cross-source+"
            + related_evidence.extraction_method
            + f"+similarity-{similarity:.3f}"
            + f"+support-{support_score:.3f}"
        ),
        selected_source=direct.source,
        selected_url=direct.url,
        evidence_title=(
            related_evidence.evidence_title
            or related_evidence.title
        ),
    )
