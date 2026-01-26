import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def _get_database_url() -> str:
    """
    Railway às vezes fornece POSTGRES_URL / DATABASE_URL.
    Se vier postgres://, normaliza para postgresql:// (SQLAlchemy 2).
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRESQL_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurado no ambiente. "
            "No Railway: Service -> Variables -> adicionar DATABASE_URL (ou POSTGRES_URL)."
        )

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


DATABASE_URL = _get_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
