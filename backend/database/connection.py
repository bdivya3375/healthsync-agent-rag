"""
Database Connection -- PostgreSQL + SQLAlchemy

Provides the engine, session factory, and Base class for all models.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL connection settings (localhost running on default port 5432)
DATABASE_URL = "postgresql://postgres:sriram456@localhost:5432/healthcare_db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a database session.
    Automatically closes the session after the request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    import database.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
