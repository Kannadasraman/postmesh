import uuid
from datetime import datetime, timezone

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
            now = datetime.now(
                timezone.utc,
            )

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

                job.status = "publishing"
                job.started_at = now
                job.last_error = None

                try:
                    if draft is not None:
                        result = publish_to_platform(draft, job)
                        job.last_error = None
                        if result.get("status") == "posted":
                            job.external_post_id = str(result.get("response", {}).get("id", job.id))
                            job.external_post_url = result.get("response", {}).get("url") or f"https://cloudpost.local/posts/{job.id}"
                        elif result.get("status") == "simulated":
                            job.external_post_url = result.get("message") or f"https://cloudpost.local/posts/{job.id}"
                        elif result.get("status") == "sent":
                            job.external_post_url = result.get("channel") or "approval-request"
                    else:
                        result = {"status": "simulated", "reason": "draft missing"}

                    job.status = "published"
                    job.published_at = now
                    if job.external_post_id is None:
                        job.external_post_id = str(job.id)
                    if job.external_post_url is None:
                        job.external_post_url = f"https://cloudpost.local/posts/{job.id}"

                    published_ids.append(
                        job.id,
                    )

                except Exception as exc:  # pragma: no cover - runtime integration fallback
                    job.status = "failed"
                    job.failed_at = now
                    job.last_error = str(exc)

        return published_ids

    finally:
        db.close()
