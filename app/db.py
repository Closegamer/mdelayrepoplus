from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

class Base(DeclarativeBase):
    pass

DATABASE_URL = (
    f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
