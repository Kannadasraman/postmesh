import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.config as config
import app.services.research_service as research_service
from app.db.database import Base
from app.models.topic import Topic


def test_repo_root_env_file_candidate_is_included(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    backend_dir = repo_root / "apps/backend"
    config_dir = backend_dir / "app/core"
    config_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / ".env").write_text("DATABASE_URL=postgresql://example\nREDIS_URL=redis://example\n")

    config_path = config_dir / "config.py"
    monkeypatch.setattr(config, "__file__", str(config_path), raising=False)

    candidates = config._env_file_candidates()

    assert str(repo_root / ".env") in candidates


def test_shorter_project_layout_does_not_crash(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    backend_dir = project_root / "app"
    config_dir = backend_dir / "core"
    config_dir.mkdir(parents=True, exist_ok=True)
    (project_root / ".env").write_text("DATABASE_URL=postgresql://example\nREDIS_URL=redis://example\n")

    config_path = config_dir / "config.py"
    monkeypatch.setattr(config, "__file__", str(config_path), raising=False)

    candidates = config._env_file_candidates()

    assert str(project_root / ".env") in candidates


def test_run_research_deduplicates_same_url_within_single_run(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    topic = Topic(
        id=uuid.uuid4(),
        name="AI Agents",
        keywords="agentic AI",
        active=True,
        research_frequency="daily",
    )

    with SessionLocal() as db:
        db.add(topic)
        db.commit()

        duplicate_url = "https://example.com/ai-agents-news"
        now = datetime.now(timezone.utc)

        monkeypatch.setattr(
            research_service,
            "_fetch_google_news",
            lambda _topic: [{
                "title": "AI Agents are changing work",
                "url": duplicate_url,
                "source": "Google News",
                "summary": "AI agents are a major trend.",
                "published_at": now,
            }],
        )
        monkeypatch.setattr(
            research_service,
            "_fetch_hacker_news",
            lambda _topic: [{
                "title": "AI agents for builders",
                "url": duplicate_url,
                "source": "Hacker News",
                "summary": "Builders are shipping AI agents.",
                "published_at": now,
            }],
        )

        items = research_service.run_research(db, topic)

        assert len(items) == 1
        assert items[0].url == duplicate_url


def test_semantic_scores_fall_back_to_heuristic_for_large_candidate_sets(monkeypatch):
    topic = Topic(
        id=uuid.uuid4(),
        name="AI Agents",
        keywords="agentic AI",
        active=True,
        research_frequency="daily",
    )

    candidates = [
        {
            "title": f"AI Agents story {index}",
            "summary": "AI agents are an active topic.",
            "source": "Example",
            "url": f"https://example.com/{index}",
            "published_at": datetime.now(timezone.utc),
        }
        for index in range(20)
    ]

    monkeypatch.setattr(
        research_service,
        "_semantic_relevance_batch",
        lambda *_args, **_kwargs: {0: 1.0},
    )

    scores = research_service._semantic_relevance_scores(topic, candidates)

    assert scores == {}
