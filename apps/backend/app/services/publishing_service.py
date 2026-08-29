import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.publishing_job import PublishingJob


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

                queued_ids.append(
                    job.id,
                )

        return queued_ids

    finally:
        db.close()
