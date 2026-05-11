"""Minimal database migration ledger for SQLAlchemy-managed metadata tables."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, inspect, select, text
from sqlalchemy.engine import Engine

from dgentic.memory.models import Base

BASELINE_MIGRATION_ID = "0001_metadata_tool_registry_baseline"
MEMORY_LIFECYCLE_MIGRATION_ID = "0002_memory_lifecycle_metadata"

_ledger_metadata = MetaData()

schema_migrations = Table(
    "schema_migrations",
    _ledger_metadata,
    Column("migration_id", String(255), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def initialize_database(engine: Engine) -> None:
    """Create current metadata tables and apply ordered additive migrations."""

    Base.metadata.create_all(bind=engine)
    _ledger_metadata.create_all(bind=engine)

    with engine.begin() as connection:
        _record_migration_if_missing(connection, BASELINE_MIGRATION_ID)
        if not _migration_applied(connection, MEMORY_LIFECYCLE_MIGRATION_ID):
            _apply_memory_lifecycle_migration(connection)
            _record_migration_if_missing(connection, MEMORY_LIFECYCLE_MIGRATION_ID)


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


def _migration_applied(connection, migration_id: str) -> bool:
    return (
        connection.execute(
            select(schema_migrations.c.migration_id).where(
                schema_migrations.c.migration_id == migration_id
            )
        ).scalar_one_or_none()
        is not None
    )


def _record_migration_if_missing(connection, migration_id: str) -> None:
    if _migration_applied(connection, migration_id):
        return
    connection.execute(
        insert(schema_migrations).values(
            migration_id=migration_id,
            applied_at=datetime.now(UTC),
        )
    )


def _apply_memory_lifecycle_migration(connection) -> None:
    timestamp_type = _timestamp_column_type(connection)
    float_type = _float_column_type(connection)
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "lifecycle_state",
        "lifecycle_state VARCHAR(50) DEFAULT 'active'",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "lifecycle_reason",
        "lifecycle_reason TEXT",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "lifecycle_updated_at",
        f"lifecycle_updated_at {timestamp_type}",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "archived_at",
        f"archived_at {timestamp_type}",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "pruned_at",
        f"pruned_at {timestamp_type}",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "expires_at",
        f"expires_at {timestamp_type}",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "freshness_score",
        f"freshness_score {float_type} DEFAULT 1.0",
    )
    _add_column_if_missing(
        connection,
        "memory_metadata",
        "last_compacted_at",
        f"last_compacted_at {timestamp_type}",
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_metadata_lifecycle_state "
            "ON memory_metadata (lifecycle_state)"
        )
    )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS idx_metadata_expires_at ON memory_metadata (expires_at)")
    )


def _add_column_if_missing(connection, table_name: str, column_name: str, column_ddl: str) -> None:
    column_names = {column["name"] for column in inspect(connection).get_columns(table_name)}
    if column_name not in column_names:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}"))


def _timestamp_column_type(connection) -> str:
    if connection.dialect.name == "postgresql":
        return "TIMESTAMP WITH TIME ZONE"
    if connection.dialect.name == "mysql":
        return "DATETIME"
    return "DATETIME"


def _float_column_type(connection) -> str:
    if connection.dialect.name == "postgresql":
        return "DOUBLE PRECISION"
    return "FLOAT"
