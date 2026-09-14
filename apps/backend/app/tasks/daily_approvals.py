from celery import shared_task


@shared_task(name="app.tasks.daily_approvals.send_daily_approval_options")
def send_daily_approval_options() -> dict[str, str]:
    """Daily approval digest entry point (9:00 AM Asia/Kolkata / 03:30 UTC)."""
    return {"status": "pending-approval-digest-implementation"}
