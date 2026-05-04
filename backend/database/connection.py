import os

from sqlmodel import Session, SQLModel, create_engine

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///./telemetry.db")

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=False, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
