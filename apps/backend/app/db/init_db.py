from app.db.database import Base, engine
from app.models import ResearchItem, Topic


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
