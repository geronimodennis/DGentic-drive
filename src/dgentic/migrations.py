"""Minimal database migration ledger for SQLAlchemy-managed metadata tables."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select
from sqlalchemy.engine import Engine

from dgentic.memory.models import Base

BASELINE_MIGRATION_ID = "0001_metadata_tool_registry_baseline"

_ledger_metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    _ledger_metadata,
    Column("migration_id", String(255), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def initialize_database(engine: Engine) -> None:
    """Create current metadata tables and record the baseline migration once."""

    Base.metadata.create_all(bind=engine)
    _ledger_metadata.create_all(bind=engine)

    with engine.begin() as connection:
        existing = connection.execute(
            select(schema_migrations.c.migration_id).where(
                schema_migrations.c.migration_id == BASELINE_MIGRATION_ID
            )
        ).scalar_one_or_none()

        if existing is None:
            connection.execute(
                insert(schema_migrations).values(
                    migration_id=BASELINE_MIGRATION_ID,
                    applied_at=datetime.now(UTC),
                )
            )


def list_applied_migrations(engine: Engine) -> list[str]:
    """Return applied migration ids in deterministic order."""

    _ledger_metadata.create_all(bind=engine)

    with engine.begin() as connection:
        return list(
            connection.execute(
                select(schema_migrations.c.migration_id).order_by(
                    schema_migrations.c.migration_id.asc()
                )
            ).scalars()
        )
