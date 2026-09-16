import uuid
from datetime import datetime, timezone

import app.services.publishing_service as service
import pytest
from app.api.publishing import publish_draft_now
from app.api.approvals import approve_from_email
from app.db.database import Base
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from app.models.social_connection import SocialConnection
from app.services.approval_service import create_approval_token
from cryptography.fernet import Fernet
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


def test_email_approval_creates_valid_publishing_job(db, monkeypatch):
    item = ContentDraft(
        topic_id=uuid.uuid4(),
        research_item_id=uuid.uuid4(),
        platform='linkedin',
        status='draft',
        approval_channel='email',
        content='Original draft',
        model_name='test',
    )
    db.add(item)
    db.commit()

    monkeypatch.setattr('app.api.approvals.execute_publishing_job', lambda *args, **kwargs: None)

    result = approve_from_email(
        token=create_approval_token(str(item.id), 'approve'),
        content='Edited version from email approval',
        action='approve',
        db=db,
    )

    assert result['status'] == 'approved_and_published'

    job = db.scalar(select(PublishingJob).where(PublishingJob.draft_id == item.id))
    assert job is not None
    assert job.scheduled_at is not None
    assert job.status == 'queued'


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


def test_facebook_publish_uses_connected_page_feed(db, monkeypatch):
    item = ContentDraft(
        topic_id=uuid.uuid4(),
        research_item_id=uuid.uuid4(),
        platform='facebook',
        status='approved',
        content='Published to the test page',
        model_name='test',
    )
    db.add(item)
    db.commit()

    connection = SocialConnection(
        provider='facebook',
        account_name='Test Page',
        account_id='page_123',
        encrypted_access_token=Fernet('dM98AjAZ7-LP2SxZd0VIBdRh_jy36NnIyxdIDOcdq5w==').encrypt(b'page-token').decode(),
        status='connected',
    )
    db.add(connection)
    db.commit()

    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload

    def fake_post(url, data=None, files=None, timeout=None):
        captured['url'] = url
        captured['data'] = data
        captured['files'] = files
        return FakeResponse({'id': 'page_post_456'})

    monkeypatch.setattr('app.services.social_integration.SessionLocal', lambda: db)
    monkeypatch.setattr('app.services.social_integration.httpx.post', fake_post)

    result = service.publish_to_platform(item)

    assert result['status'] == 'posted'
    assert result['platform'] == 'facebook'
    assert captured['url'] == 'https://graph.facebook.com/v20.0/page_123/feed'
    assert captured['data']['message'] == 'Published to the test page'
    assert result['response']['id'] == 'page_post_456'


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
