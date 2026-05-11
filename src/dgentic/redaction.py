import json
import re
from typing import Any

REDACTED_SECRET_MARKER = "[REDACTED]"
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:(?:`[\s\S])|\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:(?:`[\s\S])|\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PREFIX_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))",
    re.IGNORECASE,
)
_SENSITIVE_KEY_MARKER_PATTERN = (
    r"[A-Za-z0-9_.-]*(?:api[-_]?key|access[-_]?key|token|password|secret|"
    r"authorization|credential)[A-Za-z0-9_.-]*"
)
_SENSITIVE_LABEL_KEY_MARKER_PATTERN = (
    r"[A-Za-z0-9_.-]*(?:api[-_]?key|access[-_]?key|token|password|secret|"
    r"credential)[A-Za-z0-9_.-]*"
)
_SENSITIVE_JSON_FIELD_RE = re.compile(
    r"(?P<prefix>(?P<quote>[\"'])" + _SENSITIVE_KEY_MARKER_PATTERN + r"(?P=quote)\s*:\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^,\r\n}\]]+)",
    re.IGNORECASE,
)
_SENSITIVE_AUTHORIZATION_HEADER_RE = re.compile(
    r"(?<![\"'A-Za-z0-9_])(?P<prefix>[A-Za-z0-9_.-]*authorization[A-Za-z0-9_.-]*\s*:\s*)"
    r"(?P<value>[^\r\n]+)",
    re.IGNORECASE,
)
_SENSITIVE_LABEL_RE = re.compile(
    r"(?<![\"'A-Za-z0-9_])(?P<prefix>" + _SENSITIVE_LABEL_KEY_MARKER_PATTERN + r"\s*:\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;&|]+)",
    re.IGNORECASE,
)
_SENSITIVE_METADATA_KEY_MARKERS = {
    "accesstoken",
    "accesstokens",
    "refreshtoken",
    "refreshtokens",
    "apitoken",
    "apitokens",
    "authtoken",
    "authtokens",
    "bearertoken",
    "bearertokens",
    "token",
    "tokens",
    "password",
    "passwords",
    "passwordhash",
    "passwordhashes",
    "secret",
    "secrets",
    "secretvalue",
    "secretvalues",
    "apikey",
    "apikeys",
    "accesskey",
    "accesskeys",
    "privatekey",
    "privatekeys",
    "authorization",
    "credential",
    "credentials",
}
_SAFE_NUMERIC_METADATA_KEYS = {
    "completiontokens",
    "evalcount",
    "prompttokens",
    "totaltokens",
}


def redact_sensitive_values(text: str) -> str:
    """Redact common secret assignments, labels, headers, flags, and substitutions."""

    result = _redact_substitution_secret_values(text)
    result = _redact_json_lines(result)
    result = _SENSITIVE_JSON_FIELD_RE.sub(_redact_key_value_match, result)
    result = _SENSITIVE_AUTHORIZATION_HEADER_RE.sub(
        _redact_authorization_header_match,
        result,
    )
    result = _SENSITIVE_LABEL_RE.sub(_redact_key_value_match, result)
    result = _SENSITIVE_FLAG_RE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED_SECRET_MARKER}",
        result,
    )
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}={REDACTED_SECRET_MARKER}",
        result,
    )


def redact_metadata(value: Any, *, key: str | None = None) -> Any:
    if key is not None and is_sensitive_metadata_key(key):
        if _is_safe_numeric_metadata_value(key, value):
            return value
        return REDACTED_SECRET_MARKER
    if isinstance(value, str):
        return redact_sensitive_values(value)
    if isinstance(value, list):
        return [redact_metadata(item) for item in value]
    if isinstance(value, dict):
        return {
            item_key: redact_metadata(item, key=str(item_key)) for item_key, item in value.items()
        }
    return value


def is_sensitive_metadata_key(key: str) -> bool:
    compact_key = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(marker in compact_key for marker in _SENSITIVE_METADATA_KEY_MARKERS)


def _is_safe_numeric_metadata_value(key: str, value: Any) -> bool:
    compact_key = re.sub(r"[^a-z0-9]", "", key.lower())
    return (
        compact_key in _SAFE_NUMERIC_METADATA_KEYS
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    )


def _redact_substitution_secret_values(text: str) -> str:
    result = text
    for match in list(_SENSITIVE_ASSIGNMENT_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), "")
    for match in list(_SENSITIVE_FLAG_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), match.group("prefix"))
    return result


def _redact_json_lines(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text

    redacted_lines: list[str] = []
    changed = False
    for line in lines:
        line_body = line.rstrip("\r\n")
        newline = line[len(line_body) :]
        leading = line_body[: len(line_body) - len(line_body.lstrip())]
        trailing = line_body[len(line_body.rstrip()) :]
        candidate = line_body.strip()
        if not candidate:
            redacted_lines.append(line)
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            redacted_lines.append(line)
            continue
        redacted_lines.append(
            f"{leading}{json.dumps(redact_metadata(parsed), ensure_ascii=False)}{trailing}{newline}"
        )
        changed = True

    return "".join(redacted_lines) if changed else text


def _redact_key_value_match(match: re.Match[str]) -> str:
    value = match.group("value")
    if value.startswith('"'):
        redacted_value = f'"{REDACTED_SECRET_MARKER}"'
    elif value.startswith("'"):
        redacted_value = f"'{REDACTED_SECRET_MARKER}'"
    else:
        redacted_value = REDACTED_SECRET_MARKER
    return f"{match.group('prefix')}{redacted_value}"


def _redact_authorization_header_match(match: re.Match[str]) -> str:
    value = match.group("value")
    value_body = value.rstrip()
    trailing = value[len(value_body) :]
    scheme_match = re.match(
        r"(?P<scheme>[A-Za-z][A-Za-z0-9._-]*)(?P<space>\s+).+",
        value_body,
    )
    if scheme_match is not None:
        redacted_value = (
            f"{scheme_match.group('scheme')}{scheme_match.group('space')}{REDACTED_SECRET_MARKER}"
        )
    else:
        redacted_value = REDACTED_SECRET_MARKER
    return f"{match.group('prefix')}{redacted_value}{trailing}"


def _redact_balanced_substitution_value(text: str, value_start: int, prefix: str) -> str:
    if not text.startswith("$(", value_start):
        return text
    end_index = _find_balanced_substitution_end(text, value_start + 2)
    if end_index == -1:
        return text
    redacted = f"{prefix}{REDACTED_SECRET_MARKER}"
    return text[: value_start - len(prefix)] + redacted + text[end_index:]


def _find_balanced_substitution_end(text: str, start_index: int) -> int:
    depth = 1
    quote: str | None = None
    escaped = False
    index = start_index
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if text.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if char == ")":
            depth -= 1
            index += 1
            if depth == 0:
                return index
            continue
        index += 1
    return -1
