from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "postmesh",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.publishing",
    ],
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=[
        "json",
    ],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "queue-due-publishing-jobs": {
            "task": (
                "app.tasks.publishing."
                "process_due_publishing_jobs"
            ),
            "schedule": 30.0,
        },
    },
)
