import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from app.schemas.publishing_job import (
    PublishingJobResponse,
    PublishingScheduleRequest,
    PublishingStatus,
)


router = APIRouter(
    tags=["Publishing"],
)


BLOCKING_JOB_STATUSES = (
    "scheduled",
    "queued",
    "publishing",
    "published",
)


def _get_draft_or_404(
    draft_id: uuid.UUID,
    db: Session,
) -> ContentDraft:
    draft = db.get(
        ContentDraft,
        draft_id,
    )

    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )

    return draft


def _get_job_or_404(
    job_id: uuid.UUID,
    db: Session,
) -> PublishingJob:
    job = db.get(
        PublishingJob,
        job_id,
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publishing job not found",
        )

    return job


@router.post(
    "/api/v1/drafts/{draft_id}/schedule",
    response_model=PublishingJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_draft(
    draft_id: uuid.UUID,
    payload: PublishingScheduleRequest,
    db: Session = Depends(get_db),
):
    draft = _get_draft_or_404(
        draft_id,
        db,
    )

    if draft.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only approved drafts can be scheduled "
                "for publishing"
            ),
        )

    scheduled_at = (
        payload.scheduled_at.astimezone(
            timezone.utc,
        )
    )

    if scheduled_at <= datetime.now(
        timezone.utc,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "scheduled_at must be in the future"
            ),
        )

    existing_job = db.scalar(
        select(PublishingJob)
        .where(
            PublishingJob.draft_id
            == draft.id,
            PublishingJob.status.in_(
                BLOCKING_JOB_STATUSES,
            ),
        )
        .order_by(
            PublishingJob.created_at.desc(),
        )
    )

    if existing_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This draft already has an active "
                "or published publishing job"
            ),
        )

    job = PublishingJob(
        draft_id=draft.id,
        platform=draft.platform,
        status="scheduled",
        content_snapshot=draft.content,
        scheduled_at=scheduled_at,
        max_attempts=payload.max_attempts,
    )

    db.add(
        job,
    )
    db.commit()
    db.refresh(
        job,
    )

    return job


@router.get(
    "/api/v1/publishing/jobs",
    response_model=list[
        PublishingJobResponse
    ],
)
def list_publishing_jobs(
    job_status: PublishingStatus | None = Query(
        default=None,
        alias="status",
    ),
    db: Session = Depends(get_db),
):
    statement = select(
        PublishingJob,
    )

    if job_status is not None:
        statement = statement.where(
            PublishingJob.status
            == job_status,
        )

    jobs = db.scalars(
        statement.order_by(
            PublishingJob.scheduled_at.asc(),
            PublishingJob.created_at.asc(),
        )
    ).all()

    return list(
        jobs,
    )


@router.get(
    "/api/v1/drafts/{draft_id}/publishing-jobs",
    response_model=list[
        PublishingJobResponse
    ],
)
def list_draft_publishing_jobs(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_draft_or_404(
        draft_id,
        db,
    )

    jobs = db.scalars(
        select(PublishingJob)
        .where(
            PublishingJob.draft_id
            == draft_id,
        )
        .order_by(
            PublishingJob.created_at.desc(),
        )
    ).all()

    return list(
        jobs,
    )


@router.patch(
    "/api/v1/publishing/jobs/{job_id}/cancel",
    response_model=PublishingJobResponse,
)
def cancel_publishing_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    job = _get_job_or_404(
        job_id,
        db,
    )

    if job.status == "cancelled":
        return job

    if job.status not in {
        "scheduled",
        "queued",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only scheduled or queued publishing "
                "jobs can be cancelled"
            ),
        )

    job.status = "cancelled"
    job.cancelled_at = datetime.now(
        timezone.utc,
    )

    db.commit()
    db.refresh(
        job,
    )

    return job
