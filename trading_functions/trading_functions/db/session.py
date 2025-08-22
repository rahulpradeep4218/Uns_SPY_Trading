import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


def get_env(primary: str, fallback: str, default: str) -> str:
    """Get env var, preferring `primary` over `fallback`."""
    return os.getenv(primary) or os.getenv(fallback, default)


POSTGRES_USER = get_env("POSTGRES_USER", "DAGSTER_POSTGRES_USER", "user")
POSTGRES_PASSWORD = get_env("POSTGRES_PASSWORD", "DAGSTER_POSTGRES_PASSWORD", "password")
POSTGRES_HOST = get_env("POSTGRES_HOST", "DAGSTER_POSTGRES_HOST", "localhost")
POSTGRES_PORT = get_env("POSTGRES_PORT", "DAGSTER_POSTGRES_PORT", "5432")
INF_POSTGRES_DB = get_env("INF_POSTGRES_DB", "DAGSTER_INF_POSTGRES_DB", "dbname")

INF_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{INF_POSTGRES_DB}"

engine = create_engine(
    INF_DATABASE_URL, 
    echo=False,
    pool_size=20,
    max_overflow=40,
    pool_timeout=60,
    pool_recycle=21600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
