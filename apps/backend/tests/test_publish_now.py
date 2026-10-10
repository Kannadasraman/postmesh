import uuid
from datetime import datetime, timezone

import app.services.publishing_service as service
import pytest
from app.api.publishing import publish_draft_now
from app.db.database import Base
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def draft(db, status='approved'):
    item = ContentDraft(topic_id=uuid.uuid4(), research_item_id=uuid.uuid4(),
                        platform='facebook', status=status, content='Test post', model_name='test')
    db.add(item)
    db.commit()
    return item


def test_posts_immediately_and_blocks_repeat(db, monkeypatch):
    item = draft(db)
    calls = []
    def post(draft, job):
        calls.append(job.id)
        return {'status': 'posted', 'response': {'id': 'page_123', 'url': 'https://example.com/post'}}
    monkeypatch.setattr(service, 'publish_to_platform', post)
    result = publish_draft_now(item.id, db)
    assert result.status == 'published'
    assert result.external_post_id == 'page_123'
    assert result.attempt_count == 1
    with pytest.raises(HTTPException) as exc:
        publish_draft_now(item.id, db)
    assert exc.value.status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize('status', ['scheduled', 'queued'])
def test_reuses_pending_job(db, monkeypatch, status):
    item = draft(db)
    job = PublishingJob(draft_id=item.id, platform='facebook', content_snapshot='Saved snapshot',
                        scheduled_at=datetime.now(timezone.utc), status=status, attempt_count=1 if status == 'queued' else 0)
    db.add(job)
    db.commit()
    def post(draft, job):
        assert job.content_snapshot == 'Saved snapshot'
        return {'status': 'posted', 'response': {'id': '123'}}
    monkeypatch.setattr(service, 'publish_to_platform', post)
    result = publish_draft_now(item.id, db)
    assert result.id == job.id
    assert result.status == 'published'
    assert result.attempt_count == 1
    assert len(db.scalars(select(PublishingJob)).all()) == 1


@pytest.mark.parametrize('result', [
    {'status': 'simulated', 'message': 'Configure provider endpoint.'},
    {'status': 'skipped', 'reason': 'empty content'},
    {'status': 'posted', 'response': {}},
])
def test_unconfirmed_results_are_failed(db, monkeypatch, result):
    item = draft(db)
    monkeypatch.setattr(service, 'publish_to_platform', lambda *args: result)
    job = publish_draft_now(item.id, db)
    assert job.status == 'failed'
    assert job.last_error
    assert job.published_at is None
    assert job.external_post_url is None


def test_exception_is_recorded_and_failed_draft_can_retry(db, monkeypatch):
    item = draft(db)
    def fail(*args):
        raise ValueError('No connected account')
    monkeypatch.setattr(service, 'publish_to_platform', fail)
    job = publish_draft_now(item.id, db)
    assert job.status == 'failed'
    assert job.last_error == 'No connected account'
    monkeypatch.setattr(service, 'publish_to_platform', lambda *args: {'status': 'posted', 'response': {'id': '123'}})
    assert publish_draft_now(item.id, db).status == 'published'


def test_requires_approval(db, monkeypatch):
    item = draft(db, 'draft')
    monkeypatch.setattr(service, 'publish_to_platform', lambda *args: pytest.fail('Must not post'))
    with pytest.raises(HTTPException) as exc:
        publish_draft_now(item.id, db)
    assert exc.value.status_code == 409
    assert db.scalars(select(PublishingJob)).all() == []
