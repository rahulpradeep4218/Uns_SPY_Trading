import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import logging

logger = logging.getLogger(__name__)

POSTGRES_USER = os.getenv("DAGSTER_POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("DAGSTER_POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("DAGSTER_POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("DAGSTER_POSTGRES_PORT", "5432")
INF_POSTGRES_DB = os.getenv("INF_POSTGRES_DB", "dbname")

INF_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{INF_POSTGRES_DB}"
logger.info(f"Connecting to database at {INF_DATABASE_URL}")
engine = create_engine(INF_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
