# -*- coding: utf-8 -*-
"""Parse user-facing stock lists for the A-share-only runtime."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "AnalysisTarget",
    "IndexRegistry",
    "IndexEntry",
    "ParseStatus",
    "parse_analysis_target",
    "parse_stock_list",
    "serialize_stock_list",
    "split_stock_list",
    "default_index_registry",
]


_STOCK_LIST_SEPARATOR_RE = re.compile(r"[\s,;\uFF0C\u3001\uFF1B]+")
_EXPLICIT_INDEX_ALIAS_RE = re.compile(r"^(?:(?:sh|sz|csi)\d{6}|\d{6}\.(?:sh|sz|csi))$")
_EXPLICIT_CSI_FORM_RE = re.compile(r"^(?:csi\d+|\d+\.csi)$")
_EXCHANGE_PREFIX_TO_CODE = {"sh": "SH", "sz": "SZ", "bj": "BJ"}


def _normalize_index_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    prefix_match = re.fullmatch(r"(sh|sz)(\d{6})", normalized)
    if prefix_match:
        return f"{prefix_match.group(1)}{prefix_match.group(2)}"
    suffix_match = re.fullmatch(r"(\d{6})\.(sh|sz)", normalized)
    if suffix_match:
        return f"{suffix_match.group(2)}{suffix_match.group(1)}"
    return normalized


def _normalize_display_name(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def split_stock_list(value: str) -> List[str]:
    return [item.strip() for item in _STOCK_LIST_SEPARATOR_RE.split(value or "") if item.strip()]


def serialize_stock_list(value: str) -> str:
    return ",".join(split_stock_list(value))


class ParseStatus:
    STOCK = "stock"
    INDEX = "index"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class IndexEntry:
    bare_code: str
    exchange: str
    canonical_id: str
    display_name: str
    aliases: Tuple[str, ...] = ()

    def matches_code(self, code: str) -> bool:
        return code == self.bare_code or code in self.aliases


@dataclass(frozen=True)
class AnalysisTarget:
    raw_input: str
    asset_type: str
    canonical_id: str
    display_code: str
    exchange: str
    unsupported_reason: Optional[str] = None
    normalized_prefix: Optional[str] = None
    normalized_code: Optional[str] = None
    matched_index: Optional[IndexEntry] = field(default=None, hash=False, compare=False)


class IndexRegistry:
    """Validated registry for explicit A-share index identities."""

    def __init__(self, entries: Iterable[IndexEntry] = ()):
        self._entries = list(entries)
        self._by_canonical: Dict[str, IndexEntry] = {}
        self._by_resolver_key: Dict[str, IndexEntry] = {}
        self._by_bare_conflict: Dict[str, IndexEntry] = {}

        for entry in self._entries:
            canonical = _normalize_index_key(entry.canonical_id)
            if canonical in self._by_canonical:
                raise ValueError(f"duplicate index canonical: {entry.canonical_id!r}")
            self._by_canonical[canonical] = entry
            for key in [entry.canonical_id, *entry.aliases]:
                normalized = _normalize_index_key(key)
                if normalized.isdigit() or not _EXPLICIT_INDEX_ALIAS_RE.fullmatch(normalized):
                    raise ValueError(f"index identities must use an explicit A-share form: {key!r}")
                existing = self._by_resolver_key.get(normalized)
                if existing is not None and existing is not entry:
                    raise ValueError(f"index resolver key {key!r} maps to multiple canonicals")
                self._by_resolver_key[normalized] = entry
                digits = "".join(character for character in normalized if character.isdigit())
                if len(digits) == 6:
                    self._by_bare_conflict.setdefault(digits, entry)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def find_by_prefixed_code(self, prefix: str, bare_code: str) -> Optional[IndexEntry]:
        if prefix not in {"sh", "sz"}:
            return None
        key = _normalize_index_key(f"{prefix}{bare_code}")
        entry = self._by_canonical.get(key) or self._by_resolver_key.get(key)
        if entry is not None:
            return entry
        exchange = _EXCHANGE_PREFIX_TO_CODE[prefix]
        return next(
            (candidate for candidate in self._entries if candidate.exchange == exchange and candidate.matches_code(bare_code)),
            None,
        )

    def find_by_bare_code(self, bare_code: str) -> Optional[IndexEntry]:
        return next((entry for entry in self._entries if entry.matches_code(bare_code)), None)

    def find_by_explicit_key(self, key: str) -> Optional[IndexEntry]:
        return self._by_resolver_key.get(_normalize_index_key(key))

    def find_by_display_name(self, name: str) -> Optional[IndexEntry]:
        key = _normalize_display_name(name)
        matches = [entry for entry in self._entries if _normalize_display_name(entry.display_name) == key]
        return matches[0] if len(matches) == 1 else None

    def is_ambiguous_display_name(self, name: str) -> bool:
        key = _normalize_display_name(name)
        return sum(_normalize_display_name(entry.display_name) == key for entry in self._entries) > 1

    def find_by_bare_conflict(self, bare_code: str) -> Optional[IndexEntry]:
        return self._by_bare_conflict.get(_normalize_index_key(bare_code))


def _index_entry_from_row(row) -> Optional[IndexEntry]:
    if not isinstance(row, list) or len(row) < 10:
        return None
    canonical = str(row[0] or "").strip()
    display = str(row[1] or "").strip()
    name = str(row[2] or "").strip()
    if not canonical or not name:
        return None
    if canonical.startswith("csi"):
        exchange, bare_code = "CSI", canonical[3:]
    elif canonical.startswith(("sh", "sz")):
        exchange, bare_code = _EXCHANGE_PREFIX_TO_CODE[canonical[:2]], canonical[2:]
    else:
        return None
    aliases = [str(alias) for alias in (row[5] if isinstance(row[5], list) else []) if str(alias).strip()]
    if display and display != canonical and display not in aliases:
        aliases.append(display)
    return IndexEntry(bare_code, exchange, canonical, name, tuple(aliases))


def default_index_registry() -> IndexRegistry:
    from src.data.stock_index_loader import _load_active_index_rows

    entries = [entry for row in _load_active_index_rows() if (entry := _index_entry_from_row(row)) is not None]
    return IndexRegistry(entries)


def _unsupported(raw_input: str, reason: str, exchange: str = "UNKNOWN") -> AnalysisTarget:
    raw = str(raw_input or "").strip()
    return AnalysisTarget(
        raw_input=raw_input or "",
        asset_type=ParseStatus.UNSUPPORTED,
        canonical_id=raw,
        display_code=raw,
        exchange=exchange,
        unsupported_reason=reason,
        normalized_code=raw or None,
    )


def parse_analysis_target(raw_input: str, registry: Optional[IndexRegistry] = None) -> AnalysisTarget:
    """Parse one explicit A-share index or Shanghai/Shenzhen/Beijing security."""
    raw = str(raw_input or "").strip()
    if not raw:
        return _unsupported(raw_input, "empty input")
    registry = default_index_registry() if registry is None else registry

    lookup = re.sub(r"^(SH|SZ|SS|BJ)\.", r"\1", raw, flags=re.IGNORECASE)
    if lookup.upper().startswith("SS"):
        lookup = "SH" + lookup[2:]
    explicit_entry = registry.find_by_explicit_key(lookup)
    if explicit_entry is not None:
        prefix = raw[:2].lower() if raw[:2].lower() in {"sh", "sz"} else None
        return AnalysisTarget(
            raw_input=raw_input,
            asset_type=ParseStatus.INDEX,
            canonical_id=explicit_entry.canonical_id,
            display_code=explicit_entry.display_name,
            exchange=explicit_entry.exchange,
            normalized_prefix=prefix,
            normalized_code=explicit_entry.bare_code,
            matched_index=explicit_entry,
        )

    normalized_key = _normalize_index_key(raw)
    if _EXPLICIT_CSI_FORM_RE.fullmatch(normalized_key):
        return _unsupported(raw_input, f"unregistered CSI index: {raw!r}")

    from .stock_code_utils import _infer_cn_exchange, _normalize_code_and_exchange

    normalized_code, explicit_exchange = _normalize_code_and_exchange(raw)
    if normalized_code is None:
        return _unsupported(raw_input, "仅支持六位 A 股代码及已登记的 A 股指数", explicit_exchange or "UNKNOWN")

    prefix = None
    upper = unicodedata.normalize("NFKC", raw).strip().upper()
    for candidate in ("SH", "SZ", "BJ", "SS"):
        if upper.startswith(candidate):
            prefix = "sh" if candidate == "SS" else candidate.lower()
            break
        if upper.endswith(f".{candidate}"):
            prefix = "sh" if candidate == "SS" else candidate.lower()
            break

    if prefix in {"sh", "sz"}:
        entry = registry.find_by_prefixed_code(prefix, normalized_code)
        if entry is not None:
            return AnalysisTarget(
                raw_input=raw_input,
                asset_type=ParseStatus.INDEX,
                canonical_id=entry.canonical_id,
                display_code=entry.display_name,
                exchange=entry.exchange,
                normalized_prefix=prefix,
                normalized_code=normalized_code,
                matched_index=entry,
            )

    exchange = "SH" if explicit_exchange == "SS" else (explicit_exchange or _infer_cn_exchange(normalized_code))
    canonical_prefix = "sh" if exchange == "SH" else exchange.lower()
    matched_index = registry.find_by_bare_code(normalized_code) or registry.find_by_bare_conflict(normalized_code)
    return AnalysisTarget(
        raw_input=raw_input,
        asset_type=ParseStatus.STOCK,
        canonical_id=f"{canonical_prefix}{normalized_code}" if prefix else normalized_code,
        display_code=normalized_code,
        exchange=exchange,
        normalized_prefix=prefix,
        normalized_code=normalized_code,
        matched_index=matched_index if prefix is None else None,
    )


def parse_stock_list(value: str, registry: Optional[IndexRegistry] = None) -> List[AnalysisTarget]:
    return [parse_analysis_target(token, registry=registry) for token in split_stock_list(value)]
