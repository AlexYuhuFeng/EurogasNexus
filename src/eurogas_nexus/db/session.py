"""Lazy SQLAlchemy session factory helpers."""

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory."""

    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
