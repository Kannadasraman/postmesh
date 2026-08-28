import re

import httpx

from app.core.config import settings
from app.models.research_item import ResearchItem
from app.services.evidence_service import (
    EvidenceBundle,
    get_research_evidence,
    is_useful_summary,
)


class AIServiceError(Exception):
    pass


def _topic_hashtag(
    topic_name: str,
) -> str:
    words = re.findall(
        r"[A-Za-z0-9]+",
        topic_name,
    )

    if not words:
        return "#IndustryNews"

    hashtag = "#" + "".join(
        word[:1].upper()
        + word[1:]
        for word in words
    )

    return hashtag[:60]


def _remove_duplicate_paragraphs(
    content: str,
) -> str:
    paragraphs = re.split(
        r"\n\s*\n",
        content.strip(),
    )

    cleaned: list[str] = []
    seen: set[str] = set()

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        fingerprint = re.sub(
            r"\s+",
            " ",
            paragraph,
        ).strip().lower()

        if fingerprint in seen:
            continue

        seen.add(fingerprint)
        cleaned.append(paragraph)

    return "\n\n".join(cleaned)


def _limited_evidence_draft(
    research_item: ResearchItem,
    evidence: EvidenceBundle,
    platform: str,
    topic_name: str,
) -> str:
    hashtag = _topic_hashtag(
        topic_name,
    )

    variant = (
        research_item.id.int % 4
    )

    if platform == "x":
        variants = [
            (
                f"{evidence.title}\n\n"
                f"New from {evidence.source}. "
                f"One to watch in {topic_name}."
            ),
            (
                f"{evidence.source}: "
                f"{evidence.title}\n\n"
                f"Tracking this {topic_name} story "
                "as more details emerge."
            ),
            (
                f"{evidence.title}\n\n"
                f"A new {topic_name} item worth "
                f"watching via {evidence.source}."
            ),
            (
                f"On the radar: {evidence.title}\n\n"
                f"Source: {evidence.source}"
            ),
        ]

        return variants[
            variant
        ]

    if platform == "facebook":
        variants = [
            (
                f"{evidence.title}\n\n"
                f"{evidence.source} has a new report "
                f"related to {topic_name}.\n\n"
                "The headline is the main verified "
                "signal available right now, so this "
                "is one to follow as the story develops."
            ),
            (
                f"A new {topic_name} story is worth "
                f"keeping an eye on:\n\n"
                f"{evidence.title}\n\n"
                f"Source: {evidence.source}"
            ),
            (
                f"{evidence.source} is covering a new "
                f"development in {topic_name}:\n\n"
                f"{evidence.title}\n\n"
                "More verified context will be needed "
                "before drawing broader conclusions."
            ),
            (
                f"On the {topic_name} radar today:\n\n"
                f"{evidence.title}\n\n"
                f"Reported by {evidence.source}. "
                "Worth watching as more details emerge."
            ),
        ]

        return variants[
            variant
        ]

    if platform == "blog":
        return (
            f"{evidence.title}\n\n"
            f"{evidence.source} has surfaced a new "
            f"story related to {topic_name}.\n\n"
            "At the moment, the available source "
            "material is too limited for PostMesh to "
            "produce a detailed factual article without "
            "risking unsupported claims.\n\n"
            "This item is therefore best treated as a "
            "research lead until additional source "
            "context becomes available."
        )

    variants = [
        (
            f"{evidence.title}\n\n"
            f"A new item from {evidence.source} has "
            f"surfaced around {topic_name}.\n\n"
            "The headline is the main verified signal "
            "available right now, so this is one to "
            "watch rather than over-interpret.\n\n"
            f"{hashtag} #IndustryNews"
        ),
        (
            f"One to watch in {topic_name}:\n\n"
            f"{evidence.title}\n\n"
            f"{evidence.source} is reporting on this "
            "development. More source detail is needed "
            "before drawing broader conclusions.\n\n"
            f"{hashtag} #NewsUpdate"
        ),
        (
            f"{evidence.title}\n\n"
            f"This story from {evidence.source} is now "
            f"on the radar for anyone tracking "
            f"{topic_name}.\n\n"
            "For now, the headline is the verified "
            "information available, so the next step "
            "is to watch for fuller reporting.\n\n"
            f"{hashtag} #IndustryNews"
        ),
        (
            f"New on the {topic_name} radar:\n\n"
            f"{evidence.title}\n\n"
            f"Source: {evidence.source}\n\n"
            "Worth following as additional verified "
            "details become available.\n\n"
            f"{hashtag} #NewsUpdate"
        ),
    ]

    return variants[
        variant
    ]


def build_prompt(
    evidence: EvidenceBundle,
    platform: str,
    topic_name: str,
) -> str:
    platform_instructions = {
        "linkedin": (
            "Write a professional LinkedIn post between "
            "100 and 180 words. Use a distinct opening, "
            "short paragraphs, and 2 to 4 relevant "
            "hashtags."
        ),
        "x": (
            "Write one concise X post no longer than "
            "260 characters."
        ),
        "facebook": (
            "Write a conversational Facebook post "
            "between 80 and 150 words."
        ),
        "blog": (
            "Write a concise blog draft between "
            "300 and 500 words."
        ),
    }

    instructions = (
        platform_instructions[
            platform
        ]
    )

    return f"""
You are the content-writing assistant for PostMesh.

Create a useful, original post using ONLY the verified
evidence below.

TOPIC:
{topic_name}

PLATFORM:
{platform}

STYLE:
{instructions}

VERIFIED EVIDENCE:

Title:
{evidence.title}

Summary:
{evidence.summary}

Source:
{evidence.source}

STRICT GROUNDING RULES:

- Use only factual claims explicitly supported by the title
  or summary above.
- Do not use outside knowledge.
- Do not invent statistics, quotations, people, companies,
  product capabilities, financial results, causes, motives,
  investor behavior, or future predictions.
- Do not turn possibilities into facts.
- Do not give investment advice.
- Clearly distinguish facts from commentary.
- Do not mention PostMesh.
- Do not discuss your own writing process.
- Do not write generic filler such as "this topic is on the
  radar" or "worth following as more information becomes
  available".
- Make this post specific to the evidence supplied.
- Vary the opening and structure naturally.
- Return only the finished content.
""".strip()


def _clean_generated_content(
    content: str,
) -> str:
    content = content.strip()

    prefixes = [
        "here's a professional linkedin post",
        "here is a professional linkedin post",
        "here's a linkedin post",
        "here is a linkedin post",
        "here's the post",
        "here is the post",
    ]

    lowered = content.lower()

    for prefix in prefixes:
        if lowered.startswith(prefix):
            first_newline = (
                content.find("\n")
            )

            if first_newline != -1:
                content = content[
                    first_newline + 1 :
                ].strip()

            break

    if (
        len(content) >= 2
        and content.startswith('"')
        and content.endswith('"')
    ):
        content = content[
            1:-1
        ].strip()

    return _remove_duplicate_paragraphs(
        content,
    )


def generate_content(
    research_item: ResearchItem,
    platform: str,
    topic_name: str,
) -> tuple[str, str]:
    evidence = get_research_evidence(
        research_item,
    )

    if not is_useful_summary(
        evidence.title,
        evidence.summary,
    ):
        content = (
            _limited_evidence_draft(
                research_item=research_item,
                evidence=evidence,
                platform=platform,
                topic_name=topic_name,
            )
        )

        content = (
            _remove_duplicate_paragraphs(
                content,
            )
        )

        return (
            content,
            "grounded-template-v2",
        )

    prompt = build_prompt(
        evidence=evidence,
        platform=platform,
        topic_name=topic_name,
    )

    try:
        response = httpx.post(
            (
                f"{settings.ollama_base_url}"
                "/api/generate"
            ),
            json={
                "model": (
                    settings.ollama_model
                ),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 700,
                },
            },
            timeout=120.0,
        )

        response.raise_for_status()

    except httpx.ConnectError as exc:
        raise AIServiceError(
            "PostMesh could not connect to Ollama. "
            "Make sure Ollama is running."
        ) from exc

    except httpx.TimeoutException as exc:
        raise AIServiceError(
            "Ollama took too long to generate the draft."
        ) from exc

    except httpx.HTTPError as exc:
        raise AIServiceError(
            "Ollama returned an error while generating content."
        ) from exc

    try:
        data = response.json()

    except ValueError as exc:
        raise AIServiceError(
            "Ollama returned an invalid response."
        ) from exc

    content = _clean_generated_content(
        data.get(
            "response",
            "",
        )
    )

    if not content:
        raise AIServiceError(
            "Ollama returned an empty draft."
        )

    return (
        content,
        settings.ollama_model,
    )