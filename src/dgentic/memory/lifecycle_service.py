"""Deterministic SQL-backed memory lifecycle policy."""

from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from dgentic.memory.models import MemoryMetadata
from dgentic.memory.schemas import MemoryLifecycleDecision, MemoryLifecycleRequest

ACTIVE_LIFECYCLE_STATES = {"active", "promoted"}
INACTIVE_LIFECYCLE_STATES = {"archived", "soft_pruned"}
PROTECTED_RETENTION_POLICIES = {"manual", "permanent"}


class MemoryLifecycleService:
    """Evaluate and apply conservative memory lifecycle decisions."""

    def __init__(self, session: Session):
        self.session = session

    def preview(self, request: MemoryLifecycleRequest) -> list[MemoryLifecycleDecision]:
        return [self._decision(metadata, request) for metadata in self._candidates(request)]

    def apply(self, request: MemoryLifecycleRequest) -> list[MemoryLifecycleDecision]:
        decisions = self.preview(request)
        now = _reference_time(request)
        for decision in decisions:
            if decision.recommended_action in {"keep", "compress_candidate"}:
                continue
            metadata = (
                self.session.query(MemoryMetadata)
                .filter(MemoryMetadata.id == str(decision.metadata_id))
                .first()
            )
            if metadata is None:
                continue
            self._apply_decision(metadata, decision, now)
        self.session.commit()
        return decisions

    def _candidates(self, request: MemoryLifecycleRequest) -> list[MemoryMetadata]:
        query = self.session.query(MemoryMetadata)
        if request.entity_types:
            query = query.filter(MemoryMetadata.entity_type.in_(request.entity_types))
        if request.category:
            query = query.filter(MemoryMetadata.category == request.category)
        if request.retention_policy:
            query = query.filter(MemoryMetadata.retention_policy == request.retention_policy)
        if request.lifecycle_state:
            query = query.filter(MemoryMetadata.lifecycle_state == request.lifecycle_state)
        elif not request.include_inactive:
            query = query.filter(
                or_(
                    MemoryMetadata.lifecycle_state.is_(None),
                    MemoryMetadata.lifecycle_state.in_(ACTIVE_LIFECYCLE_STATES),
                )
            )

        items = query.order_by(MemoryMetadata.updated_at.asc()).all()
        if request.tags:
            required_tags = set(request.tags)
            items = [item for item in items if required_tags.intersection(item.tags or [])]
        return items[: request.limit]

    def _decision(
        self,
        metadata: MemoryMetadata,
        request: MemoryLifecycleRequest,
    ) -> MemoryLifecycleDecision:
        now = _reference_time(request)
        current_state = _lifecycle_state(metadata)
        freshness_score = _freshness_score(metadata, request, now)
        action = "keep"
        reason = "Memory remains active under lifecycle policy."

        if current_state in INACTIVE_LIFECYCLE_STATES:
            reason = f"Memory is already {current_state}."
        elif (metadata.retention_policy or "").strip().lower() in PROTECTED_RETENTION_POLICIES:
            reason = "Retention policy protects this memory from automatic lifecycle changes."
        elif metadata.expires_at is not None and _as_utc(metadata.expires_at) <= now:
            action = "soft_prune"
            reason = "Memory is expired and eligible for soft pruning."
        elif (
            metadata.relevance_score >= request.promote_relevance_threshold
            or metadata.access_count >= request.promote_access_count_threshold
        ):
            action = "promote"
            reason = "Memory is high-value and eligible for promotion."
        elif (
            _age_days(metadata, now) >= request.soft_prune_after_days
            and metadata.relevance_score <= request.soft_prune_relevance_threshold
            and metadata.access_count <= 1
        ):
            action = "soft_prune"
            reason = "Memory is stale, low relevance, and eligible for soft pruning."
        elif (
            _age_days(metadata, now) >= request.archive_after_days
            and metadata.relevance_score <= request.archive_relevance_threshold
            and metadata.access_count <= 2
        ):
            action = "archive"
            reason = "Memory is stale and eligible for archival."
        elif (
            _age_days(metadata, now) >= request.compress_after_days
            and metadata.access_count >= request.compress_access_count_threshold
        ):
            action = "compress_candidate"
            reason = "Memory is frequently used and eligible for future compression."

        return MemoryLifecycleDecision(
            metadata_id=metadata.id,
            entity_type=metadata.entity_type,
            entity_id=metadata.entity_id,
            retention_policy=metadata.retention_policy or "automatic",
            current_state=current_state,
            recommended_action=action,
            reason=reason,
            freshness_score=freshness_score,
            last_accessed_at=metadata.last_accessed_at,
        )

    def _apply_decision(
        self,
        metadata: MemoryMetadata,
        decision: MemoryLifecycleDecision,
        now: datetime,
    ) -> None:
        metadata.lifecycle_reason = decision.reason
        metadata.lifecycle_updated_at = now
        metadata.freshness_score = decision.freshness_score
        metadata.updated_at = now
        if decision.recommended_action == "promote":
            metadata.lifecycle_state = "promoted"
            metadata.retention_policy = "permanent"
        elif decision.recommended_action == "archive":
            metadata.lifecycle_state = "archived"
            metadata.archived_at = metadata.archived_at or now
        elif decision.recommended_action == "soft_prune":
            metadata.lifecycle_state = "soft_pruned"
            metadata.pruned_at = metadata.pruned_at or now


def metadata_is_retrievable(metadata: MemoryMetadata) -> bool:
    return _lifecycle_state(metadata) in ACTIVE_LIFECYCLE_STATES


def _reference_time(request: MemoryLifecycleRequest) -> datetime:
    if request.reference_time is None:
        return datetime.now(UTC)
    return _as_utc(request.reference_time)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _lifecycle_state(metadata: MemoryMetadata) -> str:
    return (metadata.lifecycle_state or "active").strip().lower() or "active"


def _activity_time(metadata: MemoryMetadata) -> datetime:
    return _as_utc(metadata.last_accessed_at or metadata.updated_at or metadata.created_at)


def _age_days(metadata: MemoryMetadata, now: datetime) -> int:
    return max((now - _activity_time(metadata)).days, 0)


def _freshness_score(
    metadata: MemoryMetadata,
    request: MemoryLifecycleRequest,
    now: datetime,
) -> float:
    age_days = _age_days(metadata, now)
    horizon_days = max(request.soft_prune_after_days, 1)
    return round(max(0.0, min(1.0, 1.0 - (age_days / horizon_days))), 3)
