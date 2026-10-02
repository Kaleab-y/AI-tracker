import os

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

import config  # noqa: F401

sqlite_url = os.getenv("DATABASE_URL", "sqlite:///./telemetry.db")

connect_args = {"check_same_thread": False} if sqlite_url.startswith("sqlite") else {}
engine = create_engine(sqlite_url, echo=False, connect_args=connect_args)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # Additive migration preserves telemetry collected by earlier releases.
    columns = {column["name"] for column in inspect(engine).get_columns("request_logs")}
    additions = {
        "status": "VARCHAR NOT NULL DEFAULT 'success'",
        "usage_available": "BOOLEAN NOT NULL DEFAULT TRUE",
        "error_code": "VARCHAR",
        "request_id": "VARCHAR",
        "is_demo": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE request_logs ADD COLUMN {name} {definition}")
                )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_logs_timestamp ON request_logs (timestamp)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_request_logs_status ON request_logs (status)"
            )
        )


def get_session():
    with Session(engine) as session:
        yield session
