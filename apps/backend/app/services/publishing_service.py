import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from app.services.social_integration import publish_to_platform

DEFAULT_DUE_JOB_BATCH_SIZE = 50
MAX_DUE_JOB_BATCH_SIZE = 500


def queue_due_publishing_jobs(
    limit: int = DEFAULT_DUE_JOB_BATCH_SIZE,
) -> list[uuid.UUID]:
    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    limit = min(
        limit,
        MAX_DUE_JOB_BATCH_SIZE,
    )

    db = SessionLocal()

    try:
        with db.begin():
            now = datetime.now(
                timezone.utc,
            )

            jobs = db.scalars(
                select(PublishingJob)
                .where(
                    PublishingJob.status
                    == "scheduled",
                    PublishingJob.scheduled_at
                    <= now,
                )
                .order_by(
                    PublishingJob.scheduled_at.asc(),
                    PublishingJob.created_at.asc(),
                )
                .limit(
                    limit,
                )
                .with_for_update(
                    skip_locked=True,
                )
            ).all()

            queued_ids: list[
                uuid.UUID
            ] = []

            for job in jobs:
                job.status = "queued"
                job.queued_at = now
                job.attempt_count = max(
                    job.attempt_count + 1,
                    1,
                )
                job.last_error = None

                queued_ids.append(
                    job.id,
                )

        return queued_ids

    finally:
        db.close()


def publish_queued_jobs(
    limit: int = DEFAULT_DUE_JOB_BATCH_SIZE,
) -> list[uuid.UUID]:
    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    limit = min(
        limit,
        MAX_DUE_JOB_BATCH_SIZE,
    )

    db = SessionLocal()

    try:
        with db.begin():
            jobs = db.scalars(
                select(PublishingJob)
                .where(
                    PublishingJob.status
                    == "queued",
                )
                .order_by(
                    PublishingJob.queued_at.asc(),
                    PublishingJob.created_at.asc(),
                )
                .limit(
                    limit,
                )
                .with_for_update(
                    skip_locked=True,
                )
            ).all()

            published_ids: list[
                uuid.UUID
            ] = []

            for job in jobs:
                draft = db.get(
                    ContentDraft,
                    job.draft_id,
                )

                execute_publishing_job(draft, job)
                if job.status == "published":
                    published_ids.append(job.id)

        return published_ids

    finally:
        db.close()


def execute_publishing_job(draft: ContentDraft | None, job: PublishingJob) -> None:
    """Run one attempt; only a confirmed provider result counts as published."""
    job.status = "publishing"
    job.started_at = datetime.now(timezone.utc)
    job.last_error = None
    try:
        if draft is None:
            raise ValueError("Draft no longer exists.")
        result = publish_to_platform(draft, job)
        if result.get("status") not in {"posted", "sent"}:
            raise ValueError(result.get("message") or result.get("reason") or "Provider did not confirm publication.")
        response = result.get("response") or {}
        post_id = response.get("id") or (response.get("data") or {}).get("id")
        if result.get("status") == "posted" and not post_id:
            raise ValueError("Provider returned no post ID. Check the destination before retrying.")
        job.external_post_id = str(post_id) if post_id else None
        job.external_post_url = response.get("url")
        job.status = "published"
        job.published_at = datetime.now(timezone.utc)
    except Exception as exc:
        job.status = "failed"
        job.failed_at = datetime.now(timezone.utc)
        # HTTP exception strings can include credential-bearing provider URLs.
        if isinstance(exc, httpx.HTTPError):
            job.last_error = "The publishing provider request failed. Check the destination before retrying."
        else:
            job.last_error = str(exc)
