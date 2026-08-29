from celery import shared_task

from app.services.publishing_service import (
    queue_due_publishing_jobs,
)


@shared_task(
    name=(
        "app.tasks.publishing."
        "process_due_publishing_jobs"
    ),
)
def process_due_publishing_jobs() -> dict[
    str,
    object,
]:
    queued_ids = queue_due_publishing_jobs()

    return {
        "queued_count": len(
            queued_ids,
        ),
        "job_ids": [
            str(job_id)
            for job_id
            in queued_ids
        ],
    }
