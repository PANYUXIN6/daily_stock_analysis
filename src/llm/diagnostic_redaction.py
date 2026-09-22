"""Redact credentials and personal paths from model diagnostics."""
from __future__ import annotations

from functools import lru_cache
import os
import re
from typing import Any, Iterable, Set, Callable, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlsplit

_PREVIEW_LIMIT = 800


_URL_PATTERN = re.compile(r"https?://[^\s,;)\]}]+", re.IGNORECASE)


_ANSI_ESCAPE_PATTERN = re.compile(
    r"""
    \x1B
    (?:
        \[[0-?]*[ -/]*[@-~]
        |
        \][^\x07\x1B]*(?:\x07|\x1B\\)
        |
        [@-_]
    )
    """,
    re.VERBOSE,
)


_SENSITIVE_URL_KEY_PARTS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "sendkey",
    "token",
    "webhook",
}


_SENSITIVE_ENV_PATTERNS = (
    "ACCESS_TOKEN",
    "API_KEY",
    "API_KEYS",
    "AUTHORIZATION",
    "AUTH_TOKEN",
    "AWS_",
    "AZURE_",
    "BASE_URL",
    "CLAUDE_",
    "COOKIE",
    "DATABASE_URL",
    "DB_URL",
    "FEISHU",
    "GEMINI",
    "GITHUB_TOKEN",
    "OPENAI",
    "ANTHROPIC",
    "OPENCODE_",
    "DEEPSEEK",
    "GOOGLE_",
    "MODEL",
    "SECRET",
    "SESSION",
    "TOKEN",
    "TUSHARE",
    "VERTEX_",
    "WEBHOOK",
)


_SENSITIVE_ENV_EXACT_NAMES = frozenset({
    "AIHUBMIX_KEY",
    "DINGTALK_APP_KEY",
    "PUSHOVER_USER_KEY",
    "WECOM_ENCODING_AES_KEY",
})


_SENSITIVE_DIAGNOSTIC_FIELDS = frozenset({
    "access_token",
    "access_key",
    "access_key_id",
    "api_key",
    "api_keys",
    "apikey",
    "api_secret",
    "app_secret",
    "auth_token",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "csrf_token",
    "database_url",
    "db_url",
    "github_token",
    "id_token",
    "encryption_key",
    "password",
    "passwd",
    "private_key",
    "proxy_authorization",
    "refresh_token",
    "secret",
    "secret_access_key",
    "secret_key",
    "sendkey",
    "set_cookie",
    "session_secret",
    "signing_key",
    "token",
    "tushare_token",
    "verification_token",
    "webhook",
    "webhook_url",
})


_SENSITIVE_DIAGNOSTIC_FIELD_SUFFIXES = (
    "_access_key",
    "_access_key_id",
    "_access_token",
    "_api_key",
    "_api_keys",
    "_api_secret",
    "_app_secret",
    "_auth_token",
    "_client_secret",
    "_credential",
    "_credentials",
    "_database_url",
    "_db_url",
    "_encryption_key",
    "_password",
    "_passwd",
    "_private_key",
    "_secret",
    "_secret_access_key",
    "_secret_key",
    "_sendkey",
    "_session_secret",
    "_signing_key",
    "_token",
    "_webhook",
    "_webhook_url",
)


_DIAGNOSTIC_ASSIGNMENT_VALUE_PATTERN = r"""
    (?P<value>
        (?:
            "(?:\\.|[^"\\])*"
            |
            '(?:''|\\.|[^'\\])*'
            |
            \\\r?\n[ \t]*
            |
            \\[^\r\n]
            |
            [^\s,;}\]"']
        )+
    )
"""


@lru_cache(maxsize=1)
def _diagnostic_field_name_pattern() -> str:
    """Build field syntax after the lazy config registry can be imported safely."""

    sensitive_names = (
        {name.upper() for name in _SENSITIVE_DIAGNOSTIC_FIELDS}
        | _SENSITIVE_ENV_EXACT_NAMES
        | _registered_sensitive_env_exact_names()
    )
    title_patterns = sorted(
        (re.escape(title) for title in _registered_sensitive_field_titles()),
        key=len,
        reverse=True,
    )
    spaced_sensitive_names = sorted(
        (
            re.escape(name).replace("_", r"[ \t]+")
            for name in sensitive_names
            if "_" in name
        ),
        key=len,
        reverse=True,
    )
    explicit_sensitive_names = "|".join(title_patterns + spaced_sensitive_names)
    return (
        rf"(?:(?i:{explicit_sensitive_names})|"
        r"[A-Za-z][A-Za-z0-9_-]*)"
    )


@lru_cache(maxsize=1)
def _diagnostic_field_assignment_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"""
        (?<![A-Za-z0-9_-])
        (?P<name_quote>'?)
        (?P<name>{_diagnostic_field_name_pattern()})
        (?P=name_quote)
        (?P<separator>[ \t]*(?:=|:)[ \t]*)
        {_DIAGNOSTIC_ASSIGNMENT_VALUE_PATTERN}
        """,
        re.VERBOSE,
    )


@lru_cache(maxsize=1)
def _diagnostic_json_assignment_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"""
        "
        (?P<name>(?:\\.|[^"\\])*)
        "
        (?P<separator>[ \t\r\n]*:[ \t\r\n]*)
        {_DIAGNOSTIC_ASSIGNMENT_VALUE_PATTERN}
        """,
        re.VERBOSE,
    )


@lru_cache(maxsize=1)
def _diagnostic_line_field_pattern() -> re.Pattern[str]:
    field_name_pattern = _diagnostic_field_name_pattern()
    return re.compile(
        rf"""
        (?<![A-Za-z0-9_-])
        (?P<name_quote>'?)
        (?P<name>{field_name_pattern})
        (?P=name_quote)
        (?P<separator>[ \t]*(?:=|:)[ \t]*)
        (?P<value>[^\r\n]*?)
        (?=
            (?:(?:[,;][ \t]*)|[ \t]+)'?{field_name_pattern}'?[ \t]*(?:=|:)[ \t]*
            |
            \r?\n?
            $
        )
        """,
        re.VERBOSE,
    )


@lru_cache(maxsize=1)
def _diagnostic_double_quoted_yaml_line_pattern() -> re.Pattern[str]:
    return re.compile(
        r"""
        ^
        (?P<indent>[ ]*)
        (?P<sequence_prefix>-[ \t]+)?
        (?P<node_properties>(?:(?:!(?:<[^>\r\n]+>|[^ \t\r\n]*)?|&[^ \t\r\n]+)[ \t]+)*)
        "
        (?P<name>(?:\\.|[^"\\])*)
        "
        (?P<separator>[ \t]*:[ \t]*)
        (?P<value>[^\r\n]*)
        (?P<newline>\r?\n?)
        $
        """,
        re.VERBOSE,
    )


@lru_cache(maxsize=1)
def _diagnostic_yaml_explicit_key_pattern() -> re.Pattern[str]:
    return re.compile(
        rf"""
        ^
        (?P<indent>[ ]*)
        (?P<sequence_prefix>-[ \t]+)?
        \?[ \t]+
        (?P<node_properties>(?:(?:!(?:<[^>\r\n]+>|[^ \t\r\n]*)?|&[^ \t\r\n]+)[ \t]+)*)
        (?P<name_token>
            "(?:\\.|[^"\\])*"
            |
            '(?:''|[^'])*'
            |
            [^\r\n#]+?
        )
        [ \t]*(?:\#.*)?
        \r?\n?
        $
        """,
        re.VERBOSE,
    )


_DIAGNOSTIC_ENV_ASSIGNMENT_PATTERN = re.compile(
    rf"""
    (?<![A-Za-z0-9_])
    (?P<prefix>(?:export[ \t]+)?)
    (?P<name>[A-Z][A-Z0-9_]*)
    (?P<separator>[ \t]*\+?=[ \t]*)
    {_DIAGNOSTIC_ASSIGNMENT_VALUE_PATTERN}
    """,
    re.VERBOSE,
)


_DIAGNOSTIC_ENV_ASSIGNMENT_PREFIX_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    (?P<prefix>(?:export[ \t]+)?)
    (?P<name>[A-Z][A-Z0-9_]*)
    (?P<separator>[ \t]*\+?=[ \t]*)
    """,
    re.VERBOSE,
)


_AUTHORIZATION_FIELD_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9_-])
    (?P<prefix>
        (?:
            (?P<quote>["'])
            (?:(?:proxy[-_ \t]?)?authorization)
            (?P=quote)
            |
            (?:proxy[-_ \t]?)?authorization
        )
        [ \t]*(?:=|:)[ \t]*
    )
    (?P<value>[^\r\n]*?)
    (?=
        [ \t]+["']?(?:proxy[-_ \t]?)?authorization["']?[ \t]*(?:=|:)
        |
        \r?\n
        |
        $
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


_YAML_BLOCK_SCALAR_PATTERN = re.compile(r"^[|>][0-9+-]*$")


def _redact_assignment_value(match: re.Match[str]) -> str:
    """Replace one parsed assignment value while preserving its surrounding syntax."""

    original = match.group(0)
    value = match.group("value")
    replacement = "<redacted>"
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        replacement = f"{value[0]}<redacted>{value[0]}"
    value_start = match.start("value") - match.start()
    value_end = match.end("value") - match.start()
    return f"{original[:value_start]}{replacement}{original[value_end:]}"


def _is_field_specific_sensitive_redaction_target(name: str) -> bool:
    normalized_name = _normalize_diagnostic_field_name(name)
    return (
        _is_sensitive_structured_assignment_name(name)
        and normalized_name not in {"authorization", "proxy_authorization"}
    )


def _is_multiline_sensitive_redaction_target(name: str) -> bool:
    return _is_sensitive_structured_assignment_name(name)


def _normalize_diagnostic_field_name(name: str) -> str:
    normalized = re.sub(r"[- \t]+", "_", str(name or ""))
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", normalized)
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
    return normalized.lower()


def _decode_diagnostic_double_quoted_field_name(name: str) -> str:
    """Decode YAML/JSON double-quoted escapes before applying name matching."""

    if "\\" not in name:
        return name

    simple_escapes = {
        "0": "\0",
        "a": "\a",
        "b": "\b",
        "t": "\t",
        "\t": "\t",
        "n": "\n",
        "v": "\v",
        "f": "\f",
        "r": "\r",
        "e": "\x1b",
        " ": " ",
        '"': '"',
        "/": "/",
        "\\": "\\",
        "N": "\x85",
        "_": "\xa0",
        "L": "\u2028",
        "P": "\u2029",
    }
    decoded = []
    index = 0
    while index < len(name):
        char = name[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        if index + 1 >= len(name):
            return name
        escape = name[index + 1]
        if escape in simple_escapes:
            decoded.append(simple_escapes[escape])
            index += 2
            continue
        if escape in {"x", "u", "U"}:
            widths = {"x": 2, "u": 4, "U": 8}
            width = widths[escape]
            digits = name[index + 2:index + 2 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                return name
            try:
                decoded.append(chr(int(digits, 16)))
            except ValueError:
                return name
            index += 2 + width
            continue
        if escape in {"\n", "\r"}:
            index += 2
            if escape == "\r" and index < len(name) and name[index] == "\n":
                index += 1
            while index < len(name) and name[index] in {" ", "\t"}:
                index += 1
            continue
        return name
    return "".join(decoded)


def _decode_diagnostic_yaml_field_name(name_token: str) -> str:
    """Decode a YAML key token to its logical field name."""

    token = str(name_token or "")
    if len(token) >= 2 and token[0] == token[-1] == '"':
        return _decode_diagnostic_double_quoted_field_name(token[1:-1])
    if len(token) >= 2 and token[0] == token[-1] == "'":
        return token[1:-1].replace("''", "'")
    return token.strip()


def _is_sensitive_diagnostic_field_name(name: str) -> bool:
    normalized = _normalize_diagnostic_field_name(name)
    return (
        normalized in _SENSITIVE_DIAGNOSTIC_FIELDS
        or any(normalized.endswith(suffix) for suffix in _SENSITIVE_DIAGNOSTIC_FIELD_SUFFIXES)
    )


@lru_cache(maxsize=1)
def _sensitive_exact_diagnostic_field_names() -> frozenset[str]:
    return _SENSITIVE_ENV_EXACT_NAMES | _registered_sensitive_env_exact_names()


@lru_cache(maxsize=1)
def _registered_sensitive_field_titles() -> frozenset[str]:
    try:
        from src.core.config_registry import _FIELD_DEFINITIONS
    except Exception:
        return frozenset()

    return frozenset(
        str(metadata.get("title"))
        for metadata in _FIELD_DEFINITIONS.values()
        if isinstance(metadata, Mapping)
        and metadata.get("is_sensitive")
        and isinstance(metadata.get("title"), str)
        and metadata.get("title")
    )


def _compact_diagnostic_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(name or "")).upper()


@lru_cache(maxsize=1)
def _compact_sensitive_exact_diagnostic_field_names() -> frozenset[str]:
    return frozenset(
        _compact_diagnostic_name(name)
        for name in _sensitive_exact_diagnostic_field_names()
    )


@lru_cache(maxsize=1)
def _sensitive_registered_diagnostic_field_titles() -> frozenset[str]:
    return frozenset(title.upper() for title in _registered_sensitive_field_titles())


@lru_cache(maxsize=1)
def _compact_sensitive_registered_diagnostic_field_titles() -> frozenset[str]:
    return frozenset(
        _compact_diagnostic_name(title) for title in _registered_sensitive_field_titles()
    )


def _is_sensitive_structured_assignment_name(name: str) -> bool:
    exact_name = _normalize_diagnostic_field_name(name).upper()
    upper_name = str(name or "").upper()
    compact_name = _compact_diagnostic_name(name)
    return (
        _is_sensitive_diagnostic_field_name(name)
        or exact_name in _sensitive_exact_diagnostic_field_names()
        or upper_name in _sensitive_registered_diagnostic_field_titles()
        or compact_name in _compact_sensitive_exact_diagnostic_field_names()
        or compact_name in _compact_sensitive_registered_diagnostic_field_titles()
    )


def _is_registered_sensitive_field_title(name: str) -> bool:
    return str(name or "").upper() in _sensitive_registered_diagnostic_field_titles()


def _leading_space_count(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _yaml_value_without_node_properties(value: str) -> str:
    """Return a YAML value with leading tags and anchors removed."""

    remaining = value.strip()
    while remaining.startswith(("!", "&")):
        if remaining.startswith("&"):
            property_match = re.match(r"&[^ \t]+(?:[ \t]+|$)", remaining)
        else:
            property_match = re.match(r"!(?:<[^>]+>|[^ \t]*)?(?:[ \t]+|$)", remaining)
        if property_match is None:
            break
        remaining = remaining[property_match.end():].lstrip()
    return remaining


def _is_yaml_block_value(value: str) -> bool:
    """Return whether a YAML value introduces content on following lines."""

    stripped = _yaml_value_without_node_properties(value)
    if not stripped or stripped.startswith("#"):
        return True

    tokens = stripped.split()
    if not tokens or tokens[0].startswith("#"):
        return True
    if not _YAML_BLOCK_SCALAR_PATTERN.match(tokens[0]):
        return False
    return len(tokens) == 1 or tokens[1].startswith("#")


def _yaml_value_allows_indentless_sequence(value: str) -> bool:
    """Return whether a following same-indent sequence belongs to this value."""

    stripped = _yaml_value_without_node_properties(value)
    return not stripped or stripped.startswith("#")


def _replace_spans(text: str, replacements: Sequence[Tuple[int, int, str]]) -> str:
    updated = text
    for start, end, replacement in sorted(replacements, reverse=True):
        updated = f"{updated[:start]}{replacement}{updated[end:]}"
    return updated


def _consume_redacted_yaml_block_lines(
    lines: Sequence[str],
    *,
    start_index: int,
    base_indent: int,
    allows_indentless_sequence: bool,
) -> tuple[list[str], int]:
    kept_lines: list[str] = []
    index = start_index
    while index < len(lines):
        next_line = lines[index]
        stripped_next_line = next_line.strip()
        next_indent = _leading_space_count(next_line)
        if stripped_next_line and next_indent <= base_indent:
            is_same_indent_comment = (
                next_indent == base_indent and stripped_next_line.startswith("#")
            )
            is_indentless_sequence = (
                allows_indentless_sequence
                and next_indent == base_indent
                and (
                    stripped_next_line == "-"
                    or stripped_next_line.startswith("- ")
                )
            )
            if not is_same_indent_comment and not is_indentless_sequence:
                break
        if not stripped_next_line:
            kept_lines.append(next_line)
        index += 1
    return kept_lines, index


def _consume_redacted_multiline_quote_lines(
    lines: Sequence[str],
    *,
    start_index: int,
    multiline_quote: str,
) -> tuple[list[str], int]:
    kept_lines: list[str] = []
    index = start_index
    while index < len(lines):
        next_line = lines[index]
        close_index = _diagnostic_quote_close_index(next_line, multiline_quote, start=0)
        if close_index is None:
            index += 1
            continue
        trailing = next_line[close_index:]
        if trailing.strip():
            kept_lines.append(trailing)
        index += 1
        break
    return kept_lines, index


def _is_inside_diagnostic_flow_collection(text: str) -> bool:
    closing_by_opening = {"{": "}", "[": "]"}
    stack: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in {"'", '"'}:
            index = _consume_diagnostic_scalar(text, index)
            continue
        if char in closing_by_opening:
            stack.append(closing_by_opening[char])
            index += 1
            continue
        if stack and char == stack[-1]:
            stack.pop()
        index += 1
    return bool(stack)


def _redact_double_quoted_yaml_sensitive_field(
    lines: Sequence[str],
    index: int,
) -> Optional[tuple[list[str], int]]:
    line = lines[index]
    match = _diagnostic_double_quoted_yaml_line_pattern().match(line)
    if match is None:
        return None

    decoded_name = _decode_diagnostic_double_quoted_field_name(match.group("name"))
    if not _is_multiline_sensitive_redaction_target(decoded_name):
        return None
    if _is_inside_diagnostic_flow_collection("".join(lines[:index])):
        return None

    value = match.group("value")
    normalized_name = _normalize_diagnostic_field_name(decoded_name)
    if (
        normalized_name in {"authorization", "proxy_authorization"}
        and value.lstrip(" \t").startswith("<redacted>")
    ):
        return None
    stripped_value = value.strip()
    yaml_scalar_value = _yaml_value_without_node_properties(value)
    base_indent = _leading_space_count(line)
    value_span = (match.start("value"), match.end("value"))

    if _is_yaml_block_value(value):
        replacement = "<redacted>"
        if not match.group("separator")[-1:].isspace():
            replacement = f" {replacement}"
        kept_lines, next_index = _consume_redacted_yaml_block_lines(
            lines,
            start_index=index + 1,
            base_indent=base_indent,
            allows_indentless_sequence=_yaml_value_allows_indentless_sequence(value),
        )
        return (
            [_replace_spans(line, [(value_span[0], value_span[1], replacement)]), *kept_lines],
            next_index,
        )

    yaml_quote = yaml_scalar_value[:1]
    yaml_quote_is_closed = bool(
        yaml_quote and _has_closed_diagnostic_quote(yaml_scalar_value, yaml_quote)
    )
    if yaml_quote in {"'", '"'} and (
        yaml_scalar_value != stripped_value or not yaml_quote_is_closed
    ):
        kept_lines = [_replace_spans(line, [(value_span[0], value_span[1], "<redacted>")])]
        next_index = index + 1
        if not yaml_quote_is_closed:
            trailing_lines, next_index = _consume_redacted_multiline_quote_lines(
                lines,
                start_index=next_index,
                multiline_quote=yaml_quote,
            )
            kept_lines.extend(trailing_lines)
        return kept_lines, next_index

    if stripped_value and stripped_value[0] not in {"'", '"', "{", "["}:
        redacted_line = _replace_spans(line, [(value_span[0], value_span[1], "<redacted>")])
        kept_lines = [redacted_line]
        continuation_index = index + 1
        while continuation_index < len(lines):
            next_line = lines[continuation_index]
            if not next_line.strip():
                kept_lines.append(next_line)
                continuation_index += 1
                continue
            if _leading_space_count(next_line) <= base_indent:
                break
            continuation_index += 1
        return kept_lines, continuation_index

    return None


def _redact_sensitive_collection_assignments(text: str) -> str:
    def replace_matches(
        source: str,
        pattern: re.Pattern[str],
        is_sensitive_name: Callable[[str], bool],
    ) -> str:
        replacements = []
        last_end = -1
        for match in pattern.finditer(source):
            name = match.group("name")
            value = match.group("value")
            if not is_sensitive_name(name) or not value or value[0] not in "{[":
                continue
            value_start = match.start("value")
            if value_start < last_end:
                continue
            value_end = _consume_diagnostic_collection(source, value_start)
            replacements.append((value_start, value_end, "<redacted>"))
            last_end = value_end
        return _replace_spans(source, replacements)

    redacted = replace_matches(text, _DIAGNOSTIC_ENV_ASSIGNMENT_PATTERN, _is_sensitive_env_name)
    redacted = replace_matches(
        redacted,
        _diagnostic_json_assignment_pattern(),
        lambda name: _is_sensitive_structured_assignment_name(
            _decode_diagnostic_double_quoted_field_name(name)
        ),
    )
    return replace_matches(
        redacted,
        _diagnostic_field_assignment_pattern(),
        _is_field_specific_sensitive_redaction_target,
    )


def _redact_multiline_sensitive_fields(text: str) -> str:
    """Redact YAML/log scalar fields that span spaces or indented block lines."""

    lines = text.splitlines(keepends=True)
    if not lines:
        return text

    redacted_lines = []
    index = 0
    while index < len(lines):
        line = lines[index]
        quoted_yaml_redaction = _redact_double_quoted_yaml_sensitive_field(lines, index)
        if quoted_yaml_redaction is not None:
            kept_lines, index = quoted_yaml_redaction
            redacted_lines.extend(kept_lines)
            continue

        matches = list(_diagnostic_line_field_pattern().finditer(line))
        if not matches:
            redacted_lines.append(line)
            index += 1
            continue

        replacements = []
        block_match: Optional[re.Match[str]] = None
        block_allows_indentless_sequence = False
        multiline_quote: Optional[str] = None
        for match in matches:
            name = match.group("name")
            value = match.group("value")
            normalized_name = _normalize_diagnostic_field_name(name)
            is_redacted_authorization = (
                normalized_name in {"authorization", "proxy_authorization"}
                and value.strip() == "<redacted>"
            )
            is_authorization_yaml_block = (
                normalized_name in {"authorization", "proxy_authorization"}
                and ":" in match.group("separator")
                and _is_yaml_block_value(value)
            )
            if (
                not _is_field_specific_sensitive_redaction_target(name)
                and not is_redacted_authorization
                and not is_authorization_yaml_block
            ):
                continue

            stripped_value = value.strip()
            yaml_scalar_value = _yaml_value_without_node_properties(value)
            if ":" in match.group("separator") and _is_yaml_block_value(value):
                replacement = "<redacted>"
                if not match.group("separator")[-1:].isspace():
                    replacement = f" {replacement}"
                replacements.append((match.start("value"), match.end("value"), replacement))
                block_match = block_match or match
                block_allows_indentless_sequence = (
                    block_allows_indentless_sequence
                    or _yaml_value_allows_indentless_sequence(value)
                )
                continue

            yaml_quote = yaml_scalar_value[:1]
            yaml_quote_is_closed = bool(
                yaml_quote
                and _has_closed_diagnostic_quote(yaml_scalar_value, yaml_quote)
            )
            if yaml_quote in {"'", '"'} and (
                yaml_scalar_value != stripped_value or not yaml_quote_is_closed
            ):
                replacements.append((match.start("value"), match.end("value"), "<redacted>"))
                if not yaml_quote_is_closed:
                    multiline_quote = multiline_quote or yaml_quote
                continue

            if stripped_value and stripped_value[0] not in {"'", '"', "{", "["}:
                value_end = match.end("value")
                if (
                    ":" in match.group("separator")
                    and stripped_value != "<redacted>"
                    and not _is_registered_sensitive_field_title(name)
                ):
                    flow_value_end = _find_diagnostic_flow_scalar_end(line, match.start("value"))
                    if flow_value_end is not None:
                        value_end = flow_value_end
                    else:
                        # Outside YAML flow collections, an unquoted scalar has
                        # no reliable same-line boundary. Fail closed instead
                        # of treating assignment-like text inside the
                        # credential as a separate diagnostic field.
                        value_end = len(line.rstrip("\r\n"))
                replacements.append((match.start("value"), value_end, "<redacted>"))
                if ":" in match.group("separator") and value_end == len(line.rstrip("\r\n")):
                    block_match = block_match or match
                if value_end == len(line.rstrip("\r\n")):
                    break

        if not replacements:
            redacted_lines.append(line)
            index += 1
            continue

        redacted_lines.append(_replace_spans(line, replacements))
        index += 1

        if block_match is not None:
            base_indent = _leading_space_count(line)
            kept_lines, index = _consume_redacted_yaml_block_lines(
                lines,
                start_index=index,
                base_indent=base_indent,
                allows_indentless_sequence=block_allows_indentless_sequence,
            )
            redacted_lines.extend(kept_lines)
            continue

        if multiline_quote is None:
            continue

        kept_lines, index = _consume_redacted_multiline_quote_lines(
            lines,
            start_index=index,
            multiline_quote=multiline_quote,
        )
        redacted_lines.extend(kept_lines)

    return "".join(redacted_lines)


def _redact_yaml_explicit_sensitive_fields(text: str) -> str:
    """Redact YAML ``? key`` / ``: value`` entries and their continuations."""

    lines = text.splitlines(keepends=True)
    redacted_lines = []
    index = 0
    while index < len(lines):
        key_line = lines[index]
        key_match = _diagnostic_yaml_explicit_key_pattern().match(key_line)
        key_name = (
            _decode_diagnostic_yaml_field_name(key_match.group("name_token"))
            if key_match is not None
            else ""
        )
        if (
            key_match is None
            or not _is_multiline_sensitive_redaction_target(key_name)
        ):
            redacted_lines.append(key_line)
            index += 1
            continue

        base_indent = len(key_match.group("indent")) + len(key_match.group("sequence_prefix") or "")
        value_index = index + 1
        while value_index < len(lines):
            candidate_line = lines[value_index]
            candidate_stripped = candidate_line.strip()
            if not candidate_stripped:
                value_index += 1
                continue
            if candidate_line[_leading_space_count(candidate_line):].startswith("#"):
                value_index += 1
                continue
            break
        if value_index >= len(lines):
            redacted_lines.append(key_line)
            index += 1
            continue

        value_line = lines[value_index]
        value_indent = _leading_space_count(value_line)
        value_content = value_line[value_indent:].rstrip("\r\n")
        if (
            value_indent != base_indent
            or not value_content.startswith(":")
            or (
                len(value_content) > 1
                and value_content[1] not in {" ", "\t"}
            )
        ):
            redacted_lines.append(key_line)
            index += 1
            continue

        newline = (
            "\r\n"
            if value_line.endswith("\r\n")
            else "\n"
            if value_line.endswith("\n")
            else ""
        )
        value = value_content[1:].lstrip(" \t")
        redacted_lines.append(key_line)
        for skipped_line in lines[index + 1:value_index]:
            if not skipped_line.strip():
                redacted_lines.append(skipped_line)
        redacted_lines.append(f"{' ' * value_indent}: <redacted>{newline}")
        index = value_index + 1
        allows_indentless_sequence = _yaml_value_allows_indentless_sequence(value)

        while index < len(lines):
            next_line = lines[index]
            stripped_next_line = next_line.strip()
            next_indent = _leading_space_count(next_line)
            if stripped_next_line and next_indent <= base_indent:
                is_same_indent_comment = (
                    next_indent == base_indent and stripped_next_line.startswith("#")
                )
                is_indentless_sequence = (
                    allows_indentless_sequence
                    and next_indent == base_indent
                    and (
                        stripped_next_line == "-"
                        or stripped_next_line.startswith("- ")
                    )
                )
                if not is_same_indent_comment and not is_indentless_sequence:
                    break
            if not stripped_next_line:
                redacted_lines.append(next_line)
            index += 1

    return "".join(redacted_lines)


def _redact_sensitive_diagnostic_assignments(text: str) -> str:
    """Redact parsed env and structured-field assignments under separate contracts."""

    def redact_env(match: re.Match[str]) -> str:
        name = match.group("name")
        return _redact_assignment_value(match) if _is_sensitive_env_name(name) else match.group(0)

    def redact_structured_field(match: re.Match[str]) -> str:
        return (
            _redact_assignment_value(match)
            if _is_field_specific_sensitive_redaction_target(match.group("name"))
            else match.group(0)
        )

    def redact_sensitive_env_command_substitutions(source: str) -> str:
        replacements = []
        last_end = -1
        # Collect all sensitive-env-assignment spans from the first pass
        # so the second pass can skip any ``$(...)`` that sits inside one
        # of those already-redacted regions. Without this overlap guard
        # the second pass re-adds the same span and ``_replace_spans``
        # silently drops trailing diagnostics such as ``session_id``
        # (regression OR-COR-7c0a5d41).
        first_pass_spans: list[tuple[int, int]] = []
        for match in _DIAGNOSTIC_ENV_ASSIGNMENT_PREFIX_PATTERN.finditer(source):
            value_start = match.end()
            if value_start < last_end or source[value_start:value_start + 2] != "$(":
                continue
            if not _is_sensitive_env_name(match.group("name")):
                continue
            value_end = _consume_shell_command_substitution(source, value_start)
            if value_end <= value_start:
                continue
            replacements.append((value_start, value_end, "<redacted>"))
            first_pass_spans.append((value_start, value_end))
            last_end = value_end
        # Scan remaining $(...) command substitutions not bound to any env
        # assignment, so multi-segment diagnostics like
        # A=$(echo X);B=ok; tail $(printenv SECRET_TOKEN)
        # redact every sensitive reference regardless of how it is invoked.
        tail_start = 0
        while True:
            sub = source.find("$(", tail_start)
            if sub == -1:
                break
            if sub > 0 and source[sub - 1] == "$":
                tail_start = sub + 1
                continue
            # Skip $( that is the direct value of a sensitive env assignment
            # already handled above, so we don't double-rewrite it. A leading
            # non-sensitive token like A=$(echo SECRET) must still be scanned
            # because the inner token triggers the redaction. We use the
            # collected spans rather than re-deriving the leading prefix
            # so that the ``export SENSITIVE=$(...)`` shape is recognised
            # the same way as ``SENSITIVE=$(...)`` (both share the same
            # leading match in ``_DIAGNOSTIC_ENV_ASSIGNMENT_PREFIX_PATTERN``
            # which already accepts an optional ``export`` prefix).
            skip_due_to_first_pass = any(
                start <= sub < end for start, end in first_pass_spans
            )
            if skip_due_to_first_pass:
                tail_start = sub + 1
                continue
            prior_semi = source.rfind(";", 0, sub)
            if prior_semi == -1:
                prior_nl = source.rfind("\n", 0, sub)
            else:
                prior_nl = -1
            skip_due_to_prior = False
            if prior_semi != -1:
                candidate = source[prior_semi + 1:sub].strip(" \t")
                if candidate:
                    prior_match = re.match(
                        r"(?:export[ \t]+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*$",
                        candidate,
                    )
                    if prior_match and _is_sensitive_env_name(prior_match.group("name")):
                        skip_due_to_prior = True
            if not skip_due_to_prior and prior_nl != -1:
                candidate = source[prior_nl + 1:sub].strip(" \t")
                if candidate:
                    prior_match = re.match(
                        r"(?:export[ \t]+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*$",
                        candidate,
                    )
                    if prior_match and _is_sensitive_env_name(prior_match.group("name")):
                        skip_due_to_prior = True
            if not skip_due_to_prior and prior_semi == -1 and prior_nl == -1:
                head = source[:sub].lstrip(" \t")
                if head:
                    prior_match = re.match(
                        r"(?:export[ \t]+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*$",
                        head,
                    )
                    if prior_match and _is_sensitive_env_name(prior_match.group("name")):
                        skip_due_to_prior = True
            if skip_due_to_prior:
                tail_start = sub + 1
                continue
            value_end = _consume_shell_command_substitution(source, sub)
            if value_end <= sub:
                tail_start = sub + 1
                continue
            snippet = source[sub + 2:value_end - 1] if value_end > sub + 2 else source[sub + 2:]
            # Scan every uppercase token inside the command substitution so
            # that printenv SECRET_TOKEN, echo API_KEY=..., ${TOKEN:+x}, and
            # similar forms each trigger redaction even when the leading word
            # is a generic command name like "echo" or "printenv".
            sensitive_hit = any(
                _is_sensitive_env_name(token)
                for token in re.findall(r"[A-Z][A-Z0-9_]*", snippet)
            )
            if sensitive_hit:
                replacements.append((sub, value_end, "<redacted>"))
                last_end = value_end
                tail_start = value_end
            else:
                tail_start = sub + 1
        return _replace_spans(source, replacements)

    redacted = _redact_yaml_explicit_sensitive_fields(text)
    redacted = redact_sensitive_env_command_substitutions(redacted)
    redacted = _DIAGNOSTIC_ENV_ASSIGNMENT_PATTERN.sub(redact_env, redacted)
    redacted = _redact_sensitive_collection_assignments(redacted)
    redacted = _redact_multiline_sensitive_fields(redacted)
    redacted = _diagnostic_json_assignment_pattern().sub(
        lambda match: (
            _redact_assignment_value(match)
            if _is_sensitive_structured_assignment_name(
                _decode_diagnostic_double_quoted_field_name(match.group("name"))
            )
            else match.group(0)
        ),
        redacted,
    )
    redacted = _diagnostic_field_assignment_pattern().sub(redact_structured_field, redacted)
    return _redact_partially_redacted_flow_scalars(redacted)


def _redact_partially_redacted_flow_scalars(text: str) -> str:
    """Collapse any flow-style sensitive scalar tail left after token-level redaction."""

    field_name_pattern = _diagnostic_field_name_pattern()
    pattern = re.compile(
        r"""
        (?P<prefix>
            "
            (?P<json_name>(?:\\.|[^"\\])*)
            "
            (?P<json_separator>[ \t\r\n]*:[ \t\r\n]*)
            |
            (?<![A-Za-z0-9_-])
            (?P<field_name_quote>')
            (?P<field_name>"""
        + field_name_pattern
        + r""")
            (?P=field_name_quote)
            (?P<field_separator>[ \t]*(?:=|:)[ \t]*)
        )
        <redacted>
        (?P<tail>[ \t]+[^\r\n,}\]]+?)
        (?=[ \t]*[,}\]]|\r?\n?$)
        """,
        re.VERBOSE,
    )

    def replace(match: re.Match[str]) -> str:
        json_name = match.group("json_name")
        normalized_name: Optional[str]
        if json_name is not None:
            normalized_name = _normalize_diagnostic_field_name(
                _decode_diagnostic_double_quoted_field_name(json_name)
            )
            sensitive = _is_sensitive_structured_assignment_name(normalized_name)
        else:
            normalized_name = _normalize_diagnostic_field_name(match.group("field_name"))
            sensitive = _is_field_specific_sensitive_redaction_target(match.group("field_name"))
        if not sensitive:
            return match.group(0)
        if normalized_name in {"authorization", "proxy_authorization"}:
            trailing_field = match.group("tail").lstrip(" \t")
            if _diagnostic_field_assignment_pattern().match(trailing_field):
                return match.group(0)
        return f"{match.group('prefix')}<redacted>"

    return pattern.sub(replace, text)


def _has_closed_diagnostic_quote(value: str, quote: str) -> bool:
    return _diagnostic_quote_close_index(value, quote, start=1) is not None


def _diagnostic_quote_close_index(value: str, quote: str, *, start: int) -> Optional[int]:
    index = start
    while index < len(value):
        char = value[index]
        if quote == "'" and char == "'" and index + 1 < len(value) and value[index + 1] == "'":
            index += 2
            continue
        if char == "\\" and index + 1 < len(value):
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return None


def _consume_diagnostic_scalar(
    value: str,
    start: int,
    *,
    stop_chars: str = " \t,;",
) -> int:
    if start >= len(value):
        return start
    quote = value[start]
    if quote in {"'", '"'}:
        index = start + 1
        while index < len(value):
            char = value[index]
            if quote == "'" and char == "'" and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            if char == "\\" and index + 1 < len(value):
                index += 2
                continue
            if char == quote:
                return index + 1
            index += 1
        return len(value)

    index = start
    while index < len(value) and value[index] not in stop_chars:
        index += 1
    return index


def _consume_diagnostic_collection(value: str, start: int) -> int:
    if start >= len(value) or value[start] not in "{[":
        return start

    closing_by_opening = {"{": "}", "[": "]"}
    stack = [closing_by_opening[value[start]]]
    index = start + 1
    while index < len(value):
        char = value[index]
        if char in {"'", '"'}:
            index = _consume_diagnostic_scalar(value, index)
            continue
        if char in closing_by_opening:
            stack.append(closing_by_opening[char])
            index += 1
            continue
        if stack and char == stack[-1]:
            stack.pop()
            index += 1
            if not stack:
                return index
            continue
        index += 1
    return len(value)


def _consume_shell_command_substitution(value: str, start: int) -> int:
    if start + 1 >= len(value) or value[start:start + 2] != "$(":
        return start

    depth = 1
    index = start + 2
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            index += 2
            continue
        if char in {"'", '"'}:
            index = _consume_diagnostic_scalar(value, index)
            continue
        if value.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            index += 1
            if depth == 0:
                return index
            continue
        index += 1
    return len(value)


def _find_diagnostic_flow_scalar_end(value: str, start: int) -> Optional[int]:
    """Return the end of an unquoted YAML flow scalar when delimiters are reliable."""

    closing_by_opening = {"{": "}", "[": "]"}
    stack: list[str] = []
    index = 0
    while index < start:
        char = value[index]
        if char in {"'", '"'}:
            index = _consume_diagnostic_scalar(value, index)
            continue
        if char in closing_by_opening:
            stack.append(closing_by_opening[char])
            index += 1
            continue
        if stack and char == stack[-1]:
            stack.pop()
        index += 1

    if not stack:
        return None

    index = start
    while index < len(value):
        char = value[index]
        if char in {"'", '"'}:
            index = _consume_diagnostic_scalar(value, index)
            continue
        if char in closing_by_opening:
            stack.append(closing_by_opening[char])
            index += 1
            continue
        if len(stack) == 1 and char in {",", stack[-1]}:
            return index
        if stack and char == stack[-1]:
            stack.pop()
            index += 1
            continue
        index += 1

    return None


def _authorization_value_end(value: str) -> int:
    scheme_match = re.match(r"[A-Za-z][A-Za-z0-9_-]*", value)
    if scheme_match is None:
        return len(value)

    index = scheme_match.end()
    while index < len(value) and value[index].isspace():
        index += 1

    auth_end = _consume_authorization_param_list(value, index)
    if auth_end > index:
        return auth_end

    simple_value_end = _consume_diagnostic_scalar(value, index)
    return simple_value_end if simple_value_end > index else len(value)


def _consume_authorization_param_list(
    value: str,
    start: int,
    *,
    allowed_names: Optional[frozenset[str]] = None,
) -> int:
    index = start
    auth_end = start
    consumed_any = False
    first_param = True
    while index < len(value):
        while index < len(value) and value[index].isspace():
            index += 1
        if not first_param:
            if index >= len(value) or value[index] != ",":
                break
            index += 1
            while index < len(value) and value[index].isspace():
                index += 1
        name_match = re.match(r"[A-Za-z][A-Za-z0-9_-]*", value[index:])
        if name_match is None:
            break
        name = _normalize_diagnostic_field_name(name_match.group(0))
        if allowed_names is not None and name not in allowed_names:
            break
        index += name_match.end()
        while index < len(value) and value[index].isspace():
            index += 1
        if index >= len(value) or value[index] != "=":
            break
        index += 1
        saw_whitespace_after_equals = False
        while index < len(value) and value[index].isspace():
            saw_whitespace_after_equals = True
            index += 1
        if saw_whitespace_after_equals and re.match(r"[A-Za-z][A-Za-z0-9_-]*\s*=", value[index:]):
            break
        scalar_end = _consume_diagnostic_scalar(value, index, stop_chars=" \t,")
        if scalar_end <= index:
            break
        consumed_any = True
        auth_end = scalar_end
        index = scalar_end
        first_param = False

    return auth_end if consumed_any else start


def _redact_authorization_fields(text: str) -> str:
    def redact(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        value = match.group("value") or ""
        if match.group("quote") is not None and value.lstrip(" \t")[:1] in {'"', "'", "{", "["}:
            return match.group(0)
        if not value.strip():
            return f"{prefix}<redacted>"
        auth_end = _authorization_value_end(value)
        if auth_end <= 0:
            return f"{prefix}<redacted>"
        return f"{prefix}<redacted>{value[auth_end:]}"

    return _AUTHORIZATION_FIELD_PATTERN.sub(redact, text)


def redact_diagnostic_text(text: str, *, home: Optional[str] = None, limit: int = _PREVIEW_LIMIT) -> str:
    """Redact sensitive diagnostics and return a bounded preview.

    Uppercase environment assignments intentionally reuse the fail-closed child
    environment contract. Scalar YAML/JSON/log fields use a narrower allowlist
    so ordinary fields such as ``token_budget`` and ``session_id`` remain useful
    for troubleshooting.
    """

    redacted = _ANSI_ESCAPE_PATTERN.sub("", text or "")
    home_path = home or os.path.expanduser("~")
    if home_path:
        redacted = redacted.replace(home_path, "~")
    redacted = re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@]+:[^@\s/]+@", r"\1<redacted>@", redacted)
    redacted = _URL_PATTERN.sub(_redact_sensitive_diagnostic_url, redacted)
    redacted = _redact_authorization_fields(redacted)
    redacted = re.sub(r"(?i)(cookie[ \t]*[:=][ \t]*)[^\n\r]+", r"\1<redacted>", redacted)
    redacted = _redact_sensitive_diagnostic_assignments(redacted)
    redacted = re.sub(r"(?i)(session[_-]?secret\s*[:=]\s*)[^\s]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"\b(sk-[A-Za-z0-9_-]{12,})\b", "<redacted-api-key>", redacted)
    redacted = re.sub(r"\b(AIza[A-Za-z0-9_-]{16,})\b", "<redacted-api-key>", redacted)
    redacted = re.sub(r"\b(gh[pousr]_[A-Za-z0-9_]{16,})\b", "<redacted-token>", redacted)
    # Conservative by design: model diagnostics may contain opaque long-lived credentials.
    redacted = re.sub(r"\b([A-Za-z0-9_-]{32,})\b", "<redacted-token>", redacted)
    if len(redacted) > limit:
        return redacted[:limit] + "...<truncated>"
    return redacted


def _redact_sensitive_diagnostic_url(match: re.Match[str]) -> str:
    url = match.group(0)
    return "<redacted-url>" if _is_sensitive_diagnostic_url(url) else url


def _is_sensitive_diagnostic_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return True
    if parsed.username or parsed.password:
        return True
    if _is_webhook_diagnostic_url(parsed.hostname or "", parsed.path):
        return True
    return (
        _has_sensitive_url_params(parsed.query)
        or _has_sensitive_url_params(parsed.fragment)
    )


def _is_webhook_diagnostic_url(hostname: str, path: str) -> bool:
    hostname = str(hostname or "").lower().strip(".")
    normalized_path = f"/{path.lstrip('/').lower()}"
    path_segments = {segment for segment in normalized_path.split("/") if segment}

    if hostname == "hooks.slack.com" and normalized_path.startswith("/services/"):
        return True
    if hostname == "oapi.dingtalk.com" and normalized_path.startswith("/robot/send"):
        return True
    if hostname in {"discord.com", "discordapp.com"} and "/api/webhooks/" in normalized_path:
        return True
    if hostname == "open.feishu.cn" and "/open-apis/bot/" in normalized_path and "/hook/" in normalized_path:
        return True
    if hostname == "qyapi.weixin.qq.com" and normalized_path.startswith("/cgi-bin/webhook/send"):
        return True
    if hostname.startswith("hooks."):
        return True
    return bool({"hook", "webhook", "webhooks"} & path_segments)


def _has_sensitive_url_params(params_text: str) -> bool:
    if not params_text:
        return False
    try:
        params = parse_qsl(params_text, keep_blank_values=True)
    except ValueError:
        return True
    for key, value in params:
        key_text = str(key or "").strip().lower().replace("-", "_")
        if key_text in _SENSITIVE_URL_KEY_PARTS or any(part in key_text for part in _SENSITIVE_URL_KEY_PARTS):
            return True
        if re.search(r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,}|[A-Za-z0-9_-]{32,})\b", str(value or "")):
            return True
    return False


@lru_cache(maxsize=1)
def _registered_sensitive_env_exact_names() -> frozenset[str]:
    """Reuse the config registry's secret-field contract without creating an import cycle."""

    try:
        from src.core.config_registry import _FIELD_DEFINITIONS
    except Exception:
        return frozenset()

    return frozenset(
        str(name).upper()
        for name, metadata in _FIELD_DEFINITIONS.items()
        if isinstance(metadata, Mapping) and metadata.get("is_sensitive")
    )


def _is_sensitive_env_name(upper_name: str) -> bool:
    return (
        upper_name in _SENSITIVE_ENV_EXACT_NAMES
        or upper_name in _registered_sensitive_env_exact_names()
    ) or any(
        pattern in upper_name for pattern in _SENSITIVE_ENV_PATTERNS
    )



def build_redaction_values(*values: Any) -> Set[str]:
    redactions: Set[str] = set()
    for value in values:
        if value is None:
            continue
        raw_value = str(value).strip()
        if raw_value:
            redactions.add(raw_value)
            redactions.add(f"Bearer {raw_value}")
            redactions.add(f"Authorization: Bearer {raw_value}")
        for segment in str(value).split(","):
            token = segment.strip()
            if token:
                redactions.add(token)
                redactions.add(f"Bearer {token}")
                redactions.add(f"Authorization: Bearer {token}")
    return redactions


def _comma_flexible_secret_pattern(secret: str) -> Optional[re.Pattern[str]]:
    normalized = re.sub(r"(?i)^\s*authorization\s*[:=]\s*", "", str(secret or "").strip())
    normalized = re.sub(r"(?i)^\s*bearer\s+", "", normalized)
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if len(parts) <= 1:
        return None
    return re.compile(
        r"(?i)(?:authorization\s*[:=]\s*)?(?:bearer\s+)?"
        + r"\s*,\s*".join(re.escape(part) for part in parts)
    )


def sanitize_error_text(
    text: Any,
    *,
    redaction_values: Optional[Iterable[str]] = None,
) -> str:
    if text is None:
        return ""
    sanitized = str(text).strip()
    if not sanitized:
        return ""
    values = set(redaction_values or set())
    for secret in sorted(values, key=len, reverse=True):
        pattern = _comma_flexible_secret_pattern(secret)
        if pattern is not None:
            sanitized = pattern.sub("[REDACTED]", sanitized)
    for secret in sorted(values, key=len, reverse=True):
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    patterns = [
        (r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)", r"\1[REDACTED]"),
        (r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
        (r"(?i)(cookie\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
        (r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTED]"),
        (r"(?i)sk-[a-z0-9_\-]+", "[REDACTED]"),
    ]
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    return " ".join(sanitized.split())[:300]
