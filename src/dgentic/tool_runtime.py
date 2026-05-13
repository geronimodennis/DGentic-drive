import hashlib
import hmac
import json
import os
import secrets
import signal
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.database import get_db_session
from dgentic.events import event_log
from dgentic.memory.models import ToolManifest as RegistryToolManifest
from dgentic.memory.schemas import ToolUsageRequest
from dgentic.network_policy import (
    NetworkApproval,
    NetworkApprovalRequiredError,
    NetworkDomainPolicyError,
    claim_network_approval,
    get_network_approval,
    network_domain_policy,
)
from dgentic.orchestration import authorize_tool_action
from dgentic.redaction import redact_metadata, redact_sensitive_values
from dgentic.schemas import (
    LogEventType,
    OrchestrationActionDecision,
    PermissionMode,
    ToolExecutionRequest,
    ToolManifest,
    ToolStatus,
)
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection
from dgentic.tools import get_tool, save_tool_manifest
from dgentic.tools.registry_service import ToolRegistryService

DEFAULT_TOOL_TIMEOUT_SECONDS = 30
DEFAULT_TOOL_APPROVAL_TTL_MINUTES = 30
RELIABILITY_POLICY_MIN_RUNS = 5
RELIABILITY_WARNING_THRESHOLD = 0.8
RELIABILITY_DEPRECATE_MIN_RUNS = 10
RELIABILITY_DEPRECATE_THRESHOLD = 0.25
RELIABILITY_DISABLE_MIN_RUNS = 5
RELIABILITY_DISABLE_THRESHOLD = 0.6
TIMEOUT_EXIT_CODE = -1
ENTRYPOINT_FILENAMES = ("wrapper.py", "tool.py")
TOOL_APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
_TOOL_APPROVAL_DIGEST_KEY_FILE = "tool-approval-digest.key"
_TOOL_APPROVAL_DIGEST_LOCK = Lock()
GENERATED_TOOL_NETWORK_APPROVAL_SURFACE = "generated_tool"
GENERATED_TOOL_NETWORK_APPROVAL_ACTION = "socket_connect"
STANDARD_TOOL_DEPENDENCY_DIRS = ("vendor", ".dgentic-deps", ".dgentic/deps", "site-packages")
SUBPROCESS_ENV_KEYS = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "CURL_CA_BUNDLE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USERPROFILE",
        "WINDIR",
    }
)

_RUNNER_SOURCE = r"""
import contextlib
import importlib.util
import json
import os
import socket
import sys
import traceback
from pathlib import Path


def _install_network_guards():
    raw_policy = os.environ.pop("DGENTIC_TOOL_NETWORK_DOMAIN_POLICY", "").strip()
    if not raw_policy:
        return

    def normalize_mode(value):
        if not isinstance(value, str):
            raise RuntimeError("DGentic tool network policy mode is invalid.")
        normalized = value.strip().lower().replace("-", "_")
        if normalized not in {"allow", "deny", "approval_required", "audit"}:
            raise RuntimeError("DGentic tool network policy mode is invalid.")
        return normalized

    def normalize_domain(value):
        if not isinstance(value, str):
            raise RuntimeError("DGentic tool network policy domain is invalid.")
        domain = value.strip().lower().rstrip(".")
        if not domain:
            raise RuntimeError("DGentic tool network policy domain is invalid.")
        return domain

    def normalize_host(value):
        if isinstance(value, bytes):
            try:
                value = value.decode("idna")
            except UnicodeError as exc:
                raise PermissionError("Tool network host is invalid.") from exc
        return str(value).strip().lower().rstrip(".")

    def domain_matches(host, domain):
        if domain.startswith("*."):
            suffix = domain[2:]
            return host.endswith(f".{suffix}") and host != suffix
        return host == domain

    try:
        payload = json.loads(raw_policy)
    except json.JSONDecodeError as exc:
        raise RuntimeError("DGentic tool network policy must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("DGentic tool network policy must be a JSON object.")

    default_mode = normalize_mode(payload.get("default_mode", "allow"))
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        raise RuntimeError("DGentic tool network policy rules must be a list.")
    rules = []
    for rule in raw_rules:
        if not isinstance(rule, dict):
            raise RuntimeError("DGentic tool network policy rules must be objects.")
        rules.append((normalize_domain(rule.get("domain")), normalize_mode(rule.get("mode"))))
    rules = tuple(rules)

    def normalize_approved_port(value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError("DGentic tool approved network endpoint port is invalid.")
        if value < 1 or value > 65535:
            raise RuntimeError("DGentic tool approved network endpoint port is invalid.")
        return value

    raw_approved_endpoints = payload.get("approved_endpoints", [])
    if not isinstance(raw_approved_endpoints, list):
        raise RuntimeError("DGentic tool approved network endpoints must be a list.")
    approved_endpoints = {}
    for endpoint in raw_approved_endpoints:
        if not isinstance(endpoint, dict):
            raise RuntimeError("DGentic tool approved network endpoints must be objects.")
        raw_host = endpoint.get("host")
        if not isinstance(raw_host, (str, bytes)):
            raise RuntimeError("DGentic tool approved network endpoint host is invalid.")
        host = normalize_host(raw_host)
        if not host:
            raise RuntimeError("DGentic tool approved network endpoint host is invalid.")
        approved_endpoints.setdefault(host, set()).add(
            normalize_approved_port(endpoint.get("port"))
        )
    approved_endpoints = {
        host: frozenset(ports) for host, ports in approved_endpoints.items()
    }

    resolved_allowlist = set()
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyaddr = socket.gethostbyaddr
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex
    original_getnameinfo = socket.getnameinfo

    def policy_mode_for_host(host):
        normalized_host = normalize_host(host)
        for domain, mode in rules:
            if domain_matches(normalized_host, domain):
                return mode
        return default_mode

    def address_host(address):
        if isinstance(address, tuple) and address:
            return address[0]
        return address

    def normalize_address_port(value):
        if value is None:
            return None
        if isinstance(value, str):
            port = value.strip()
            if not port:
                return None
            if port.isdigit():
                return int(port)
            try:
                return socket.getservbyname(port)
            except OSError:
                return port.lower()
        return value

    def address_key(address):
        if isinstance(address, tuple) and address:
            host = normalize_host(address[0])
            port = normalize_address_port(address[1]) if len(address) > 1 else None
            return (host, port)
        return (normalize_host(address), None)

    def approved_ports_for_host(host, port=None):
        ports = approved_endpoints.get(normalize_host(host), frozenset())
        if port is None:
            return tuple(ports)
        normalized_port = normalize_address_port(port)
        if normalized_port in ports:
            return (normalized_port,)
        return ()

    def endpoint_is_approved(host, port):
        return bool(approved_ports_for_host(host, port))

    def host_has_approved_endpoint(host):
        return bool(approved_ports_for_host(host))

    def is_resolved_allowlisted(host, port=None):
        normalized_host = normalize_host(host)
        normalized_port = normalize_address_port(port)
        return (
            (normalized_host, normalized_port) in resolved_allowlist
            or (normalized_host, None) in resolved_allowlist
        )

    def authorize_host(host, port=None):
        mode = policy_mode_for_host(host)
        if mode == "deny":
            raise PermissionError(
                f"Tool network access to {host} is blocked by DGentic network policy."
            )
        if mode == "approval_required":
            if port is None and host_has_approved_endpoint(host):
                return "approved"
            if port is not None and endpoint_is_approved(host, port):
                return "approved"
            raise PermissionError(
                f"Tool network access to {host} requires DGentic network approval."
            )
        return mode

    def authorize_address(address):
        key = address_key(address)
        if key in resolved_allowlist or (key[0], None) in resolved_allowlist:
            return "allow"
        return authorize_host(address_host(address), key[1])

    def authorize_resolver_host(host, port=None):
        if is_resolved_allowlisted(host, port):
            return "allow"
        return authorize_host(host, port)

    def remember_resolved_host(host, port=None):
        resolved_allowlist.add((normalize_host(host), normalize_address_port(port)))

    def remember_approved_resolution(source_host, resolved_host, port=None):
        for approved_port in approved_ports_for_host(source_host, port):
            remember_resolved_host(resolved_host, approved_port)

    def remember_getaddrinfo_results(results):
        for result in results:
            if len(result) >= 5:
                resolved_allowlist.add(address_key(result[4]))

    def remember_approved_getaddrinfo_results(source_host, source_port, results):
        for result in results:
            if len(result) >= 5:
                sockaddr = result[4]
                if isinstance(sockaddr, tuple) and sockaddr:
                    remember_approved_resolution(source_host, sockaddr[0], source_port)

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        mode = authorize_resolver_host(host, port)
        results = original_getaddrinfo(host, port, *args, **kwargs)
        if mode in {"allow", "audit"}:
            remember_getaddrinfo_results(results)
        elif mode == "approved":
            remember_getaddrinfo_results(results)
            remember_approved_getaddrinfo_results(host, port, results)
        return results

    def guarded_gethostbyaddr(host):
        authorize_host(host)
        return original_gethostbyaddr(host)

    def guarded_gethostbyname(host):
        mode = authorize_host(host)
        address = original_gethostbyname(host)
        if mode in {"allow", "audit"}:
            remember_resolved_host(address)
        elif mode == "approved":
            remember_approved_resolution(host, address)
        return address

    def guarded_gethostbyname_ex(host):
        mode = authorize_host(host)
        result = original_gethostbyname_ex(host)
        if mode in {"allow", "audit"} and len(result) >= 3:
            for address in result[2]:
                remember_resolved_host(address)
        elif mode == "approved" and len(result) >= 3:
            for address in result[2]:
                remember_approved_resolution(host, address)
        return result

    def guarded_getnameinfo(sockaddr, flags):
        authorize_address(sockaddr)
        return original_getnameinfo(sockaddr, flags)

    def guarded_connect(self, address):
        authorize_address(address)
        return original_connect(self, address)

    def guarded_connect_ex(self, address):
        authorize_address(address)
        return original_connect_ex(self, address)

    def guarded_create_connection(address, *args, **kwargs):
        authorize_address(address)
        return original_create_connection(address, *args, **kwargs)

    def network_audit_hook(event, args):
        if event == "socket.getaddrinfo" and len(args) > 1:
            authorize_resolver_host(args[0], args[1])
        elif event in {"socket.gethostbyaddr", "socket.gethostbyname"} and args:
            authorize_host(args[0])
        elif event == "socket.getnameinfo" and args:
            authorize_address(args[0])
        elif event == "socket.connect" and len(args) > 1:
            authorize_address(args[1])

    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyaddr = guarded_gethostbyaddr
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex
    socket.getnameinfo = guarded_getnameinfo
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    sys.addaudithook(network_audit_hook)


_install_network_guards()
del _install_network_guards


def _main():
    entrypoint = Path(sys.argv[1])
    dependency_paths = [Path(item) for item in sys.argv[2:]]
    sys.path[:0] = [str(entrypoint.parent), *[str(path) for path in dependency_paths]]

    payload = json.load(sys.stdin)
    spec = importlib.util.spec_from_file_location("_dgentic_tool_entrypoint", entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load tool entrypoint: {entrypoint}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    handler = getattr(module, "invoke", None) or getattr(module, "run", None)
    if handler is None:
        raise AttributeError("Tool entrypoint must define invoke(payload) or run(payload).")

    with contextlib.redirect_stdout(sys.stderr):
        output = handler(payload)

    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


try:
    _main()
except BaseException:
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""


class ToolApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


class ToolApproval(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    tool_status: ToolStatus = ToolStatus.active
    entrypoint: str = ""
    artifact_digest: str = ""
    payload_digest: str = ""
    approval_digest: str = ""
    review_payload: Any | None = None
    timeout_seconds: int
    permission_mode: PermissionMode = PermissionMode.approval_required
    status: ToolApprovalStatus = ToolApprovalStatus.pending
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    orchestration: OrchestrationActionDecision | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: (
            datetime.now(UTC) + timedelta(minutes=DEFAULT_TOOL_APPROVAL_TTL_MINUTES)
        )
    )
    decided_at: datetime | None = None
    executed_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        self.review_payload = redact_metadata(self.review_payload)
        self.requested_by = _redact_optional_sensitive_text(self.requested_by)
        self.agent_id = _redact_optional_sensitive_text(self.agent_id)
        self.agent_role = _redact_optional_sensitive_text(self.agent_role)
        self.task_id = _redact_optional_sensitive_text(self.task_id)
        if self.orchestration is not None:
            self.orchestration = _redact_orchestration_decision(self.orchestration)
        self.decided_by = _redact_optional_sensitive_text(self.decided_by)
        self.decision_reason = _redact_optional_sensitive_text(self.decision_reason)
        self.denial_reason = _redact_optional_sensitive_text(self.denial_reason)
        self.artifact_digest = _sanitize_tool_approval_digest(self.artifact_digest)
        self.payload_digest = _sanitize_tool_approval_digest(self.payload_digest)
        self.approval_digest = _sanitize_tool_approval_digest(self.approval_digest)


class ToolApprovalReview(BaseModel):
    id: str
    status: ToolApprovalStatus
    tool_name: str
    tool_version: str
    tool_status: ToolStatus
    entrypoint: str
    artifact_digest: str = ""
    review_payload: Any | None = None
    payload_digest: str = ""
    approval_digest: str = ""
    timeout_seconds: int
    permission_mode: PermissionMode
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    orchestration: OrchestrationActionDecision | None = None
    requires_bound_execution_request: bool = True
    direct_execute_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None


_tool_approvals = JsonCollection("tool-approvals", ToolApproval)
_tool_approval_lock = Lock()


class ToolExecutionResult(BaseModel):
    tool_name: str
    approval_id: str | None = None
    network_approval_id: str | None = None
    entrypoint: Path
    cwd: Path
    dependency_paths: list[Path] = Field(default_factory=list)
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    parsed_output: Any | None = None
    orchestration: OrchestrationActionDecision | None = None
    manifest: ToolManifest = Field(
        description="The manifest after reliability counters were updated."
    )


def execute_tool(
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    approved: bool = False,
    approval_id: str | None = None,
    network_approval_id: str | None = None,
    timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
) -> ToolExecutionResult:
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1.")

    manifest = get_tool(name)
    if manifest is None:
        raise LookupError(f"Tool not found: {name}")

    _ensure_registry_allows_manifest(manifest)
    orchestration_decision = _authorize_tool_or_raise(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    bound_approval_id = _ensure_tool_can_run(
        manifest,
        payload=payload or {},
        approved=approved,
        approval_id=approval_id,
        timeout_seconds=timeout_seconds,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    root_dir = get_settings().root_dir.resolve()
    tool_dir = _tool_dir_for(manifest.name, root_dir)
    _validate_manifest_entrypoint(manifest, root_dir, tool_dir)
    entrypoint = _resolve_entrypoint(tool_dir)
    dependency_paths = _tool_dependency_paths(manifest, tool_dir)
    claimed_network_approval = _claim_tool_network_approval(
        network_approval_id,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )

    started_at = perf_counter()
    exit_code, stdout, stderr = _run_tool_subprocess(
        entrypoint=entrypoint,
        tool_dir=tool_dir,
        payload=payload or {},
        timeout_seconds=timeout_seconds,
        dependency_paths=dependency_paths,
        network_approval=claimed_network_approval,
    )

    duration_ms = round((perf_counter() - started_at) * 1000)
    parsed_output = _parse_json_output(stdout)
    redacted_output = redact_metadata(parsed_output) if parsed_output is not None else None
    stdout = _redact_stdout(stdout, redacted_output)
    stderr = redact_sensitive_values(stderr)
    updated_manifest, reliability_policy = _record_run(
        manifest,
        succeeded=exit_code == 0,
        duration_ms=duration_ms,
    )
    _record_execution_event(
        updated_manifest,
        approval_id=bound_approval_id,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        reliability_policy=reliability_policy,
        dependency_paths=dependency_paths,
        network_approval_id=claimed_network_approval.id if claimed_network_approval else None,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        orchestration=orchestration_decision,
    )

    return ToolExecutionResult(
        tool_name=manifest.name,
        approval_id=bound_approval_id,
        network_approval_id=claimed_network_approval.id if claimed_network_approval else None,
        entrypoint=entrypoint,
        cwd=tool_dir,
        dependency_paths=dependency_paths,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        parsed_output=redacted_output,
        orchestration=orchestration_decision,
        manifest=updated_manifest,
    )


def create_tool_approval(
    name: str,
    request: ToolExecutionRequest,
    *,
    requested_by: str | None = None,
) -> ToolApproval:
    if request.timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1.")
    if request.network_approval_id is not None:
        raise ValueError(
            "network_approval_id is only valid when executing a generated tool; "
            "tool approvals do not include network approval binding."
        )
    manifest = get_tool(name)
    if manifest is None:
        raise LookupError(f"Tool not found: {name}")

    _ensure_registry_allows_manifest(manifest)
    orchestration_decision = _authorize_tool_or_raise(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _ensure_tool_can_be_queued_for_approval(manifest)
    requested_by_value = requested_by or request.requested_by
    root_dir = get_settings().root_dir.resolve()
    tool_dir = _tool_dir_for(manifest.name, root_dir)
    _validate_manifest_entrypoint(manifest, root_dir, tool_dir)
    entrypoint = _resolve_entrypoint(tool_dir)
    artifact_digest = _tool_artifact_digest(tool_dir)
    payload_digest = tool_payload_digest(request.payload)
    approval_digest = tool_approval_digest(
        tool_name=manifest.name,
        tool_version=manifest.version,
        tool_status=manifest.status,
        entrypoint=str(entrypoint.relative_to(root_dir)),
        artifact_digest=artifact_digest,
        payload_digest=payload_digest,
        timeout_seconds=request.timeout_seconds,
        requested_by=requested_by_value,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        permission_mode=manifest.permission_mode,
    )
    approval = ToolApproval(
        id=f"tool-approval-{uuid4()}",
        tool_name=manifest.name,
        tool_version=manifest.version,
        tool_status=manifest.status,
        entrypoint=str(entrypoint.relative_to(root_dir)),
        artifact_digest=artifact_digest,
        payload_digest=payload_digest,
        approval_digest=approval_digest,
        review_payload=redact_metadata(request.payload),
        timeout_seconds=request.timeout_seconds,
        permission_mode=manifest.permission_mode,
        requested_by=requested_by_value,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        orchestration=orchestration_decision,
    )
    _tool_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Created generated tool approval request.",
        actor=approval.requested_by or "system",
        subject_id=approval.id,
        metadata={
            "tool_name": approval.tool_name,
            "tool_version": approval.tool_version,
            "tool_status": approval.tool_status,
            "entrypoint": approval.entrypoint,
            "artifact_digest": approval.artifact_digest,
            "permission_mode": approval.permission_mode,
            "requested_by": approval.requested_by,
            "agent_id": approval.agent_id,
            "agent_role": approval.agent_role,
            "task_id": approval.task_id,
            "orchestration": _orchestration_metadata(approval.orchestration),
            "payload_digest": approval.payload_digest,
            "approval_digest": approval.approval_digest,
            "expires_at": approval.expires_at.isoformat(),
        },
    )
    return approval


def list_tool_approvals(
    status: ToolApprovalStatus | str | None = None,
) -> list[ToolApproval]:
    approvals = _tool_approvals.list()
    if status is None:
        return approvals
    requested_status = ToolApprovalStatus(status)
    return [approval for approval in approvals if approval.status == requested_status]


def get_tool_approval_review(approval_id: str) -> ToolApprovalReview:
    approval = _get_tool_approval_or_raise(approval_id)
    warnings: list[str] = [
        "Tool approval stores a redacted payload preview; execute with a bound request "
        "that resubmits the same payload."
    ]
    if _tool_approval_is_expired(approval):
        warnings.append("Approval is expired.")
    return ToolApprovalReview(
        id=approval.id,
        status=approval.status,
        tool_name=approval.tool_name,
        tool_version=approval.tool_version,
        tool_status=approval.tool_status,
        entrypoint=approval.entrypoint,
        artifact_digest=approval.artifact_digest,
        review_payload=redact_metadata(approval.review_payload),
        payload_digest=approval.payload_digest,
        approval_digest=approval.approval_digest,
        timeout_seconds=approval.timeout_seconds,
        permission_mode=approval.permission_mode,
        requested_by=approval.requested_by,
        agent_id=approval.agent_id,
        agent_role=approval.agent_role,
        task_id=approval.task_id,
        orchestration=approval.orchestration,
        direct_execute_available=False,
        review_warnings=warnings,
        decided_by=approval.decided_by,
        decision_reason=_redact_optional_sensitive_text(approval.decision_reason),
        denial_reason=_redact_optional_sensitive_text(approval.denial_reason),
        created_at=approval.created_at,
        updated_at=approval.updated_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        executed_at=approval.executed_at,
    )


def approve_tool_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> ToolApproval:
    approval = _get_tool_approval_or_raise(approval_id)
    if approval.status != ToolApprovalStatus.pending:
        raise ValueError(
            f"Only pending tool approvals can be approved; current status is {approval.status}."
        )
    if _tool_approval_is_expired(approval):
        raise ValueError(f"Tool approval {approval_id} has expired and cannot be approved.")

    redacted_reason = _redact_optional_sensitive_text(reason)
    now = datetime.now(UTC)
    approval.status = ToolApprovalStatus.approved
    approval.decided_by = _redact_optional_sensitive_text(decided_by)
    approval.decision_reason = redacted_reason
    approval.decided_at = now
    approval.updated_at = now
    _tool_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Approved generated tool request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={"tool_name": approval.tool_name, "reason": redacted_reason}
        if redacted_reason
        else {"tool_name": approval.tool_name},
    )
    return approval


def deny_tool_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> ToolApproval:
    approval = _get_tool_approval_or_raise(approval_id)
    if approval.status != ToolApprovalStatus.pending:
        raise ValueError(
            f"Only pending tool approvals can be denied; current status is {approval.status}."
        )

    redacted_reason = _redact_optional_sensitive_text(reason)
    now = datetime.now(UTC)
    approval.status = ToolApprovalStatus.denied
    approval.decided_by = _redact_optional_sensitive_text(decided_by)
    approval.decision_reason = redacted_reason
    approval.denial_reason = redacted_reason
    approval.decided_at = now
    approval.updated_at = now
    _tool_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Denied generated tool request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={"tool_name": approval.tool_name, "reason": redacted_reason}
        if redacted_reason
        else {"tool_name": approval.tool_name},
    )
    return approval


def _ensure_tool_can_run(
    manifest: ToolManifest,
    *,
    payload: dict[str, Any],
    approved: bool,
    approval_id: str | None,
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> str | None:
    if manifest.permission_mode == PermissionMode.blocked:
        raise PermissionError(f"Tool is blocked and cannot run: {manifest.name}")
    if manifest.status == ToolStatus.disabled:
        raise PermissionError(f"Tool is disabled and cannot run: {manifest.name}")
    if manifest.status == ToolStatus.deprecated:
        reason = f": {manifest.deprecated_reason}" if manifest.deprecated_reason else "."
        raise PermissionError(f"Tool is deprecated and cannot run{reason}")
    if manifest.permission_mode == PermissionMode.approval_required:
        return _authorize_approval_required_tool_request(
            manifest,
            payload=payload,
            approved=approved,
            approval_id=approval_id,
            timeout_seconds=timeout_seconds,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )
    if approval_id is not None:
        raise ValueError("approval_id is only valid for approval-required tools.")
    return None


def _ensure_tool_can_be_queued_for_approval(manifest: ToolManifest) -> None:
    if manifest.permission_mode == PermissionMode.blocked:
        raise PermissionError(f"Tool is blocked and cannot be queued: {manifest.name}")
    if manifest.status == ToolStatus.disabled:
        raise PermissionError(f"Tool is disabled and cannot be queued: {manifest.name}")
    if manifest.status == ToolStatus.deprecated:
        reason = f": {manifest.deprecated_reason}" if manifest.deprecated_reason else "."
        raise PermissionError(f"Tool is deprecated and cannot be queued{reason}")
    if manifest.permission_mode != PermissionMode.approval_required:
        raise ValueError("Only approval-required tools can be queued for approval.")


def _authorize_approval_required_tool_request(
    manifest: ToolManifest,
    *,
    payload: dict[str, Any],
    approved: bool,
    approval_id: str | None,
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> str | None:
    if approval_id is not None:
        approval = _get_tool_approval_or_raise(approval_id)
        _claim_bound_tool_approval(
            approval,
            manifest=manifest,
            payload=payload,
            timeout_seconds=timeout_seconds,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )
        return approval.id

    if approved and _approval_boolean_bypass_allowed():
        return None
    if approved:
        raise PermissionError(
            "Tool requires an approved approval_id before execution; "
            "the approved boolean bypass is only allowed in development/test mode."
        )
    raise PermissionError("Tool requires an approved approval_id before execution.")


def _claim_bound_tool_approval(
    approval: ToolApproval,
    *,
    manifest: ToolManifest,
    payload: dict[str, Any],
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> None:
    with _tool_approval_lock:
        current = _get_tool_approval_or_raise(approval.id)
        _validate_bound_tool_approval(
            current,
            manifest=manifest,
            payload=payload,
            timeout_seconds=timeout_seconds,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
        )
        now = datetime.now(UTC)
        current.status = ToolApprovalStatus.executed
        current.executed_at = now
        current.updated_at = now
        _tool_approvals.upsert(current)
    event_log.record(
        LogEventType.approval,
        "Claimed generated tool approval for execution.",
        actor=requested_by or approval.requested_by or "system",
        subject_id=approval.id,
        metadata={"tool_name": manifest.name, "requested_by": requested_by},
    )


def _validate_bound_tool_approval(
    approval: ToolApproval,
    *,
    manifest: ToolManifest,
    payload: dict[str, Any],
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> None:
    if approval.status != ToolApprovalStatus.approved:
        raise PermissionError(
            f"Tool approval {approval.id} is not executable; current status is {approval.status}."
        )
    if _tool_approval_is_expired(approval):
        raise PermissionError(f"Tool approval {approval.id} has expired and cannot be executed.")

    root_dir = get_settings().root_dir.resolve()
    tool_dir = _tool_dir_for(manifest.name, root_dir)
    _validate_manifest_entrypoint(manifest, root_dir, tool_dir)
    entrypoint = _resolve_entrypoint(tool_dir)
    relative_entrypoint = str(entrypoint.relative_to(root_dir))
    artifact_digest = _tool_artifact_digest(tool_dir)
    payload_digest = tool_payload_digest(payload)
    expected_approval_digest = tool_approval_digest(
        tool_name=manifest.name,
        tool_version=manifest.version,
        tool_status=manifest.status,
        entrypoint=relative_entrypoint,
        artifact_digest=artifact_digest,
        payload_digest=payload_digest,
        timeout_seconds=timeout_seconds,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        permission_mode=manifest.permission_mode,
    )
    checks = [
        approval.tool_name == manifest.name,
        approval.tool_version == manifest.version,
        approval.tool_status == manifest.status,
        approval.entrypoint == relative_entrypoint,
        approval.artifact_digest == artifact_digest,
        approval.payload_digest == payload_digest,
        approval.approval_digest == expected_approval_digest,
        approval.timeout_seconds == timeout_seconds,
        approval.permission_mode == manifest.permission_mode,
        approval.requested_by == _redact_optional_sensitive_text(requested_by),
        approval.agent_id == _redact_optional_sensitive_text(agent_id),
        approval.agent_role == _redact_optional_sensitive_text(agent_role),
        approval.task_id == _redact_optional_sensitive_text(task_id),
    ]
    if not all(checks):
        raise PermissionError(
            f"Tool approval {approval.id} is not bound to this tool execution request."
        )


def _tool_approval_is_expired(approval: ToolApproval) -> bool:
    return approval.expires_at <= datetime.now(UTC)


def _get_tool_approval_or_raise(approval_id: str) -> ToolApproval:
    approval = _tool_approvals.get(approval_id)
    if approval is None:
        raise KeyError(f"Tool approval not found: {approval_id}")
    return approval


def _claim_tool_network_approval(
    network_approval_id: str | None,
    *,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> NetworkApproval | None:
    if network_approval_id is None:
        return None
    try:
        approval = get_network_approval(network_approval_id)
    except KeyError as exc:
        raise NetworkApprovalRequiredError(str(exc)) from exc
    if (
        approval.surface != GENERATED_TOOL_NETWORK_APPROVAL_SURFACE
        or approval.action != GENERATED_TOOL_NETWORK_APPROVAL_ACTION
    ):
        raise NetworkApprovalRequiredError(
            "Generated-tool network execution requires a network approval bound to "
            f"{GENERATED_TOOL_NETWORK_APPROVAL_SURFACE}/"
            f"{GENERATED_TOOL_NETWORK_APPROVAL_ACTION}."
        )
    if approval.port is None:
        raise NetworkApprovalRequiredError(
            "Generated-tool network approval must include an explicit port."
        )
    if approval.path not in {"", "/"}:
        raise NetworkApprovalRequiredError(
            "Generated-tool socket approvals must not include a URL path."
        )
    return claim_network_approval(
        network_approval_id,
        url=approval.url,
        surface=GENERATED_TOOL_NETWORK_APPROVAL_SURFACE,
        action=GENERATED_TOOL_NETWORK_APPROVAL_ACTION,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def _redact_optional_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    return redact_sensitive_values(text)


def _redact_orchestration_decision(
    decision: OrchestrationActionDecision,
) -> OrchestrationActionDecision:
    return decision.model_copy(
        update={
            "reason": redact_sensitive_values(decision.reason),
            "agent_id": _redact_optional_sensitive_text(decision.agent_id),
            "agent_role": _redact_optional_sensitive_text(decision.agent_role),
            "task_id": _redact_optional_sensitive_text(decision.task_id),
        }
    )


def _authorize_tool_or_raise(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> OrchestrationActionDecision:
    decision = authorize_tool_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    decision = _redact_orchestration_decision(decision)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    return decision


def _orchestration_metadata(
    decision: OrchestrationActionDecision | None,
) -> dict[str, Any] | None:
    if decision is None:
        return None
    return decision.model_dump(mode="json")


def _approval_boolean_bypass_allowed() -> bool:
    return get_settings().environment.strip().lower() in {"development", "test", "testing"}


def _tool_approval_digest_key() -> bytes:
    settings = get_settings()
    configured_key = settings.approval_digest_key.strip()
    if configured_key:
        return configured_key.encode("utf-8")

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    key_path = data_dir / _TOOL_APPROVAL_DIGEST_KEY_FILE
    with _TOOL_APPROVAL_DIGEST_LOCK:
        if key_path.exists():
            stored_key = key_path.read_text(encoding="utf-8").strip()
            if stored_key:
                return stored_key.encode("utf-8")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        generated_key = secrets.token_hex(32)
        key_path.write_text(generated_key + "\n", encoding="utf-8")
        return generated_key.encode("utf-8")


def _tool_hmac_digest(encoded_payload: str) -> str:
    digest = hmac.new(
        _tool_approval_digest_key(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{TOOL_APPROVAL_DIGEST_PREFIX}{digest}"


def _sanitize_tool_approval_digest(digest: str) -> str:
    if not digest:
        return ""
    if digest.startswith(TOOL_APPROVAL_DIGEST_PREFIX):
        return digest
    return REDACTED_LEGACY_DIGEST_MARKER


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def tool_payload_digest(payload: dict[str, Any]) -> str:
    return _tool_hmac_digest(_canonical_json(payload))


def _tool_artifact_digest(tool_dir: Path) -> str:
    artifacts: list[dict[str, str]] = []
    for candidate in sorted(
        tool_dir.rglob("*"),
        key=lambda path: path.relative_to(tool_dir).as_posix(),
    ):
        relative_path = candidate.relative_to(tool_dir)
        relative_parts = set(relative_path.parts)
        if "__pycache__" in relative_parts or candidate.suffix == ".pyc":
            continue
        relative = relative_path.as_posix()
        if candidate.is_symlink():
            raise PermissionError("Tool artifacts must not contain symlinks.")
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(tool_dir):
            artifacts.append(
                {
                    "path": relative,
                    "unsafe_path": str(resolved),
                }
            )
            continue
        artifacts.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
            }
        )
    return _tool_hmac_digest(_canonical_json(artifacts))


def tool_approval_digest(
    *,
    tool_name: str,
    tool_version: str,
    tool_status: ToolStatus,
    entrypoint: str,
    artifact_digest: str,
    payload_digest: str,
    timeout_seconds: int,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    permission_mode: PermissionMode,
) -> str:
    payload = {
        "tool_name": tool_name,
        "tool_version": tool_version,
        "tool_status": tool_status,
        "entrypoint": entrypoint,
        "artifact_digest": artifact_digest,
        "payload_digest": payload_digest,
        "timeout_seconds": timeout_seconds,
        "requested_by": requested_by,
        "agent_id": agent_id,
        "agent_role": agent_role,
        "task_id": task_id,
        "permission_mode": permission_mode,
    }
    return _tool_hmac_digest(_canonical_json(payload))


def _ensure_registry_allows_manifest(manifest: ToolManifest) -> None:
    session = get_db_session()
    try:
        registry_tool = (
            session.query(RegistryToolManifest)
            .filter(RegistryToolManifest.tool_name == manifest.name)
            .first()
        )
        if registry_tool is None:
            return

        if registry_tool.deprecated:
            raise PermissionError(
                f"Tool registry row is deprecated and cannot run: {manifest.name}"
            )

        try:
            registry_permission = PermissionMode(registry_tool.permission_level)
        except ValueError as exc:
            raise PermissionError(
                f"Tool registry permission_level is invalid and cannot run: {manifest.name}"
            ) from exc

        if registry_permission != manifest.permission_mode:
            raise PermissionError(
                "Tool registry permission_level conflicts with JSON manifest "
                f"permission_mode for tool: {manifest.name}"
            )
    finally:
        session.close()


def _tool_dir_for(name: str, root_dir: Path) -> Path:
    if not name or "/" in name or "\\" in name:
        raise PermissionError("Tool execution must stay inside rootDir/localmcp/[tool_name].")

    localmcp_dir = (root_dir / "localmcp").resolve()
    tool_dir = (localmcp_dir / name).resolve()
    if tool_dir.parent != localmcp_dir:
        raise PermissionError("Tool execution must stay inside rootDir/localmcp/[tool_name].")
    return tool_dir


def _validate_manifest_entrypoint(manifest: ToolManifest, root_dir: Path, tool_dir: Path) -> None:
    if not manifest.entrypoint:
        return

    entrypoint = Path(manifest.entrypoint)
    if not entrypoint.is_absolute():
        base_dir = tool_dir if entrypoint.parent == Path(".") else root_dir
        entrypoint = base_dir / entrypoint
    resolved = entrypoint.resolve()
    if resolved.parent != tool_dir:
        raise PermissionError("Tool entrypoint must stay inside rootDir/localmcp/[tool_name].")


def _resolve_entrypoint(tool_dir: Path) -> Path:
    for filename in ENTRYPOINT_FILENAMES:
        candidate = (tool_dir / filename).resolve()
        if candidate.parent != tool_dir:
            raise PermissionError("Tool entrypoint must stay inside rootDir/localmcp/[tool_name].")
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Tool entrypoint not found: expected wrapper.py or tool.py in {tool_dir}"
    )


def _tool_dependency_paths(manifest: ToolManifest, tool_dir: Path) -> list[Path]:
    dependency_paths: list[Path] = []
    seen: set[Path] = set()
    for spec in manifest.dependency_paths:
        dependency_path = _resolve_tool_dependency_path(tool_dir, spec, required=True)
        if dependency_path in seen:
            continue
        seen.add(dependency_path)
        dependency_paths.append(dependency_path)
    for spec in [*STANDARD_TOOL_DEPENDENCY_DIRS, *_tool_venv_dependency_specs()]:
        dependency_path = _resolve_tool_dependency_path(tool_dir, spec, required=False)
        if dependency_path is None or dependency_path in seen:
            continue
        seen.add(dependency_path)
        dependency_paths.append(dependency_path)
    return dependency_paths


def _tool_venv_dependency_specs() -> tuple[str, ...]:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return (
        f".venv/lib/{version}/site-packages",
        ".venv/Lib/site-packages",
    )


def _resolve_tool_dependency_path(tool_dir: Path, spec: str, *, required: bool) -> Path | None:
    dependency_spec = spec.strip()
    if not dependency_spec:
        return None
    requested = Path(dependency_spec)
    if requested.is_absolute() or requested.drive:
        raise PermissionError("Tool dependency paths must be relative to the tool directory.")
    if not requested.parts or any(part in {"", ".", ".."} for part in requested.parts):
        raise PermissionError("Tool dependency paths must stay inside the tool directory.")

    candidate = tool_dir / requested
    if not candidate.exists():
        if required:
            raise FileNotFoundError(f"Tool dependency path does not exist: {dependency_spec}")
        return None
    if _path_has_symlink_between(tool_dir, candidate):
        raise PermissionError("Tool dependency paths must not contain symlinks.")
    if not candidate.is_dir():
        raise PermissionError("Tool dependency paths must be directories.")

    resolved = candidate.resolve()
    if not resolved.is_relative_to(tool_dir):
        raise PermissionError("Tool dependency paths must stay inside the tool directory.")
    return resolved


def _tool_subprocess_args(entrypoint: Path, dependency_paths: list[Path]) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-S",
        "-X",
        "utf8",
        "-c",
        _RUNNER_SOURCE,
        str(entrypoint),
        *[str(path) for path in dependency_paths],
    ]


def _run_tool_subprocess(
    *,
    entrypoint: Path,
    tool_dir: Path,
    payload: dict[str, Any],
    timeout_seconds: int,
    dependency_paths: list[Path],
    network_approval: NetworkApproval | None = None,
) -> tuple[int, str, str]:
    process = subprocess.Popen(
        _tool_subprocess_args(entrypoint, dependency_paths),
        cwd=tool_dir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_subprocess_env(network_approval=network_approval),
        **_tool_popen_isolation_kwargs(),
    )
    try:
        stdout, stderr = process.communicate(
            json.dumps(payload),
            timeout=timeout_seconds,
        )
        exit_code = process.returncode
        if exit_code is None:
            exit_code = process.wait()
        return exit_code, stdout or "", stderr or ""
    except subprocess.TimeoutExpired as exc:
        _terminate_tool_process_tree(process)
        drained_stdout, drained_stderr = _drain_tool_process_output(process)
        stdout = _coerce_timeout_output(exc.stdout) or drained_stdout
        stderr = _coerce_timeout_output(exc.stderr) or drained_stderr
        timeout_message = f"Tool timed out after {timeout_seconds} seconds."
        stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
        return TIMEOUT_EXIT_CODE, stdout, stderr


def _drain_tool_process_output(process: subprocess.Popen) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=1)
    except (subprocess.TimeoutExpired, ValueError):
        return "", ""
    return stdout or "", stderr or ""


def _tool_popen_isolation_kwargs() -> dict[str, bool | int]:
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.name != "nt":
        return {"start_new_session": True}
    return {}


def _terminate_tool_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
        if process.pid is not None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.kill()
        return

    if process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass

    if process.pid is not None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
    else:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _path_has_symlink_between(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    current = candidate
    paths_to_check = [current]
    while current != root:
        current = current.parent
        paths_to_check.append(current)
    return any(path.exists() and path.is_symlink() for path in paths_to_check)


def _subprocess_env(*, network_approval: NetworkApproval | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in SUBPROCESS_ENV_KEYS}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["DGENTIC_TOOL_DEPENDENCY_MODE"] = "local-only"
    sanitized_network_policy = _tool_runner_network_policy(network_approval=network_approval)
    if sanitized_network_policy:
        env["DGENTIC_TOOL_NETWORK_DOMAIN_POLICY"] = sanitized_network_policy
    return env


def _tool_runner_network_policy(*, network_approval: NetworkApproval | None = None) -> str:
    if network_approval is None and not get_settings().network_domain_policy.strip():
        return ""
    try:
        policy = network_domain_policy()
    except NetworkDomainPolicyError as exc:
        raise PermissionError("Network domain policy is invalid.") from exc
    payload = {
        "default_mode": policy.default_mode,
        "rules": [
            {
                "domain": rule.domain,
                "mode": rule.mode,
            }
            for rule in policy.rules
        ],
        "approved_endpoints": (
            [
                {
                    "host": network_approval.host,
                    "port": network_approval.port,
                }
            ]
            if network_approval is not None
            else []
        ),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _parse_json_output(stdout: str) -> Any | None:
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _redact_stdout(stdout: str, parsed_output: Any | None) -> str:
    if parsed_output is not None:
        suffix = "\n" if stdout.endswith("\n") else ""
        return json.dumps(parsed_output, ensure_ascii=False) + suffix
    return redact_sensitive_values(stdout)


def _record_run(
    manifest: ToolManifest,
    *,
    succeeded: bool,
    duration_ms: int,
) -> tuple[ToolManifest, str]:
    usage_count = manifest.usage_count + 1
    success_count = manifest.success_count + (1 if succeeded else 0)
    failure_count = manifest.failure_count + (0 if succeeded else 1)
    reliability_score = success_count / usage_count if usage_count else 1.0
    reliability_policy = _reliability_policy_for(
        usage_count=usage_count,
        failure_count=failure_count,
        reliability_score=reliability_score,
    )
    governance_update = _reliability_governance_update(
        manifest,
        policy=reliability_policy,
        usage_count=usage_count,
        reliability_score=reliability_score,
    )

    updated = manifest.model_copy(
        update={
            "usage_count": usage_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "last_used_at": datetime.now(UTC),
            "reliability_score": reliability_score,
            **governance_update,
        }
    )
    saved = save_tool_manifest(updated)
    _record_sql_registry_usage(
        saved,
        succeeded=succeeded,
        duration_ms=duration_ms,
        reliability_policy=reliability_policy,
    )
    if reliability_policy != "allow":
        _record_reliability_policy_event(
            saved,
            policy=reliability_policy,
            usage_count=usage_count,
            reliability_score=reliability_score,
        )
    return saved, reliability_policy


def _reliability_policy_for(
    *,
    usage_count: int,
    failure_count: int,
    reliability_score: float,
) -> str:
    if (
        usage_count >= RELIABILITY_DEPRECATE_MIN_RUNS
        and reliability_score < RELIABILITY_DEPRECATE_THRESHOLD
    ):
        return "deprecate"
    if usage_count < RELIABILITY_POLICY_MIN_RUNS:
        return "allow"
    if failure_count >= 3 and reliability_score < RELIABILITY_DISABLE_THRESHOLD:
        return "disable"
    if reliability_score < RELIABILITY_WARNING_THRESHOLD:
        return "warn"
    return "allow"


def _reliability_governance_update(
    manifest: ToolManifest,
    *,
    policy: str,
    usage_count: int,
    reliability_score: float,
) -> dict[str, Any]:
    if manifest.status != ToolStatus.active:
        return {}
    if policy == "disable":
        return {
            "status": ToolStatus.disabled,
            "deprecated_reason": _reliability_reason(
                "Auto-disabled",
                usage_count=usage_count,
                reliability_score=reliability_score,
            ),
        }
    if policy == "deprecate":
        return {
            "status": ToolStatus.deprecated,
            "deprecated_reason": _reliability_reason(
                "Auto-deprecated",
                usage_count=usage_count,
                reliability_score=reliability_score,
            ),
        }
    return {}


def _reliability_reason(
    prefix: str,
    *,
    usage_count: int,
    reliability_score: float,
) -> str:
    return f"{prefix}: reliability score {reliability_score:.2f} after {usage_count} runs."


def _record_sql_registry_usage(
    manifest: ToolManifest,
    *,
    succeeded: bool,
    duration_ms: int,
    reliability_policy: str,
) -> None:
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        registry_tool = service.get_tool_by_name(manifest.name)
        if registry_tool is None:
            return
        updated = service.record_usage(
            registry_tool.id,
            ToolUsageRequest(
                status="success" if succeeded else "failure",
                execution_time_ms=duration_ms,
            ),
        )
        if updated is not None and reliability_policy == "deprecate":
            service.deprecate_tool(updated.id)
    finally:
        session.close()


def _record_reliability_policy_event(
    manifest: ToolManifest,
    *,
    policy: str,
    usage_count: int,
    reliability_score: float,
) -> None:
    event_log.record(
        LogEventType.tool,
        "Applied generated tool reliability policy.",
        subject_id=manifest.name,
        metadata={
            "tool_name": manifest.name,
            "policy": policy,
            "status": manifest.status,
            "usage_count": usage_count,
            "success_count": manifest.success_count,
            "failure_count": manifest.failure_count,
            "reliability_score": reliability_score,
            "deprecated_reason": manifest.deprecated_reason,
        },
    )


def _record_execution_event(
    manifest: ToolManifest,
    *,
    approval_id: str | None,
    network_approval_id: str | None,
    exit_code: int,
    duration_ms: int,
    stdout: str,
    stderr: str,
    reliability_policy: str,
    dependency_paths: list[Path],
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    orchestration: OrchestrationActionDecision | None,
) -> None:
    event_log.record(
        LogEventType.tool,
        "Executed generated tool.",
        actor=requested_by or "system",
        subject_id=manifest.name,
        metadata={
            "tool_name": manifest.name,
            "approval_id": approval_id,
            "network_approval_id": network_approval_id,
            "permission_mode": manifest.permission_mode,
            "status": manifest.status,
            "exit_code": exit_code,
            "succeeded": exit_code == 0,
            "duration_ms": duration_ms,
            "reliability_policy_action": reliability_policy,
            "reliability_policy_reason": manifest.deprecated_reason,
            "dependency_isolation": "local-only",
            "process_isolation": "process-group",
            "dependency_paths": [
                path.relative_to(
                    _tool_dir_for(manifest.name, get_settings().root_dir.resolve())
                ).as_posix()
                for path in dependency_paths
            ],
            "requested_by": requested_by,
            "agent_id": agent_id,
            "agent_role": agent_role,
            "task_id": task_id,
            "orchestration": _orchestration_metadata(orchestration),
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
        },
    )


def _coerce_timeout_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "GENERATED_TOOL_NETWORK_APPROVAL_ACTION",
    "GENERATED_TOOL_NETWORK_APPROVAL_SURFACE",
    "TIMEOUT_EXIT_CODE",
    "ToolApproval",
    "ToolApprovalReview",
    "ToolApprovalStatus",
    "ToolExecutionResult",
    "approve_tool_approval",
    "create_tool_approval",
    "deny_tool_approval",
    "execute_tool",
    "get_tool_approval_review",
    "list_tool_approvals",
]
