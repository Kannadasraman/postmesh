import re

import httpx

from app.core.config import settings
from app.models.research_item import ResearchItem


class AIServiceError(Exception):
    pass


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def _summary_is_limited(
    research_item: ResearchItem,
) -> bool:
    summary = _normalize_text(
        research_item.summary
    ).lower()

    title = _normalize_text(
        research_item.title
    ).lower()

    if not summary:
        return True

    if summary == title:
        return True

    title_without_source = re.sub(
        r"\s+-\s+[^-]+$",
        "",
        title,
    ).strip()

    if title_without_source and title_without_source in summary:
        remaining = summary.replace(
            title_without_source,
            "",
            1,
        ).strip()

        if len(remaining) < 80:
            return True

    if len(summary) < 120:
        return True

    return False


def _limited_evidence_draft(
    research_item: ResearchItem,
    platform: str,
) -> str:
    title = _normalize_text(
        research_item.title
    )

    source = _normalize_text(
        research_item.source
    )

    if platform == "x":
        return (
            f"{source} is reporting: {title}\n\n"
            "Worth watching as the story develops."
        )

    if platform == "facebook":
        return (
            f"A recent report from {source} highlights:\n\n"
            f"{title}\n\n"
            "The available research currently contains only limited "
            "details, so this is one to follow as more information "
            "becomes available."
        )

    if platform == "blog":
        return (
            f"{title}\n\n"
            f"A recent report from {source} is drawing attention to "
            "this topic.\n\n"
            "At this stage, PostMesh has only limited source details "
            "available, so it would be premature to draw broader "
            "conclusions from the headline alone.\n\n"
            "The story is worth monitoring as additional verified "
            "information becomes available."
        )

    return (
        f"{title}\n\n"
        f"A recent report from {source} puts this topic on the radar.\n\n"
        "The source information currently available to PostMesh is "
        "limited, so it would be premature to add conclusions or "
        "details that have not been verified.\n\n"
        "Worth following as more confirmed information becomes "
        "available.\n\n"
        "#IndustryNews"
    )


def build_prompt(
    research_item: ResearchItem,
    platform: str,
) -> str:
    platform_instructions = {
        "linkedin": (
            "Write a professional LinkedIn post between 100 and "
            "180 words. Use short paragraphs and 2 to 4 relevant "
            "hashtags."
        ),
        "x": (
            "Write one concise X post no longer than "
            "260 characters."
        ),
        "facebook": (
            "Write a conversational Facebook post between "
            "80 and 150 words."
        ),
        "blog": (
            "Write a concise blog draft between 300 and "
            "500 words."
        ),
    }

    title = _normalize_text(
        research_item.title
    )

    summary = _normalize_text(
        research_item.summary
    )

    instructions = platform_instructions[
        platform
    ]

    return f"""
You are the content-writing assistant for PostMesh.

Transform the evidence below into content while remaining
strictly grounded in that evidence.

PLATFORM:
{platform}

STYLE:
{instructions}

VERIFIED EVIDENCE:

Title:
{title}

Summary:
{summary}

Source:
{research_item.source}

STRICT RULES:

- Use only facts explicitly present in VERIFIED EVIDENCE.
- Treat everything not present in VERIFIED EVIDENCE as unknown.
- Do not use outside knowledge.
- Do not infer financial performance.
- Do not infer statistics or percentages.
- Do not infer causes or future trends.
- Do not infer investor behavior.
- Do not infer product capabilities.
- Do not invent quotations.
- Do not invent people, companies, events, or details.
- Do not give investment advice.
- You may provide neutral commentary about why the verified
  topic is worth watching.
- Clearly distinguish reported facts from commentary.
- Do not write "Here's a post" or similar introductions.
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
            first_newline = content.find("\n")

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
        content = content[1:-1].strip()

    return content


def generate_content(
    research_item: ResearchItem,
    platform: str,
) -> tuple[str, str]:
    if _summary_is_limited(research_item):
        content = _limited_evidence_draft(
            research_item=research_item,
            platform=platform,
        )

        return (
            content,
            "grounded-template-v1",
        )

    prompt = build_prompt(
        research_item=research_item,
        platform=platform,
    )

    try:
        response = httpx.post(
            (
                f"{settings.ollama_base_url}"
                "/api/generate"
            ),
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 600,
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
            "Ollama took too long to generate "
            "the draft."
        ) from exc

    except httpx.HTTPError as exc:
        raise AIServiceError(
            "Ollama returned an error while "
            "generating content."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise AIServiceError(
            "Ollama returned an invalid response."
        ) from exc

    content = _clean_generated_content(
        data.get("response", "")
    )

    if not content:
        raise AIServiceError(
            "Ollama returned an empty draft."
        )

    return (
        content,
        settings.ollama_model,
    )