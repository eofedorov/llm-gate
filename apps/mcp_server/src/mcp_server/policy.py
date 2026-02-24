"""Политики валидации аргументов и SQL sandbox для MCP tools."""
import re
from typing import Any

from audit import audit_event

MAX_QUERY_LEN = 1000
K_MIN, K_MAX = 1, 10
ALLOWED_FILTER_KEYS = frozenset({"doc_type", "language"})
SQL_MAX_ROWS = 200
FORBIDDEN_SQL_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|COPY|TRUNCATE)\b",
    re.IGNORECASE,
)
SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
FORBIDDEN_SQL_PATTERNS = [
    re.compile(r";", re.IGNORECASE),
    re.compile(r"pg_catalog\.", re.IGNORECASE),
    re.compile(r"information_schema\.", re.IGNORECASE),
    re.compile(r"pg_\w+\s*\(", re.IGNORECASE),
]
MAX_TOOL_CALLS_PER_REQUEST = 6
MAX_TOTAL_TOOL_PAYLOAD_BYTES = 200 * 1024


class PolicyError(Exception):
    """Нарушение политики (аргументы или SQL)."""


def validate_k(k: int) -> None:
    if not (K_MIN <= k <= K_MAX):
        audit_event("policy.blocked", reason=f"k must be between {K_MIN} and {K_MAX}, got {k}", validator="validate_k")
        raise PolicyError(f"k must be between {K_MIN} and {K_MAX}, got {k}")


def validate_query(query: str) -> None:
    if not query or not isinstance(query, str):
        audit_event("policy.blocked", reason="query is required and must be non-empty string", validator="validate_query")
        raise PolicyError("query is required and must be non-empty string")
    if len(query) > MAX_QUERY_LEN:
        audit_event("policy.blocked", reason=f"query must be at most {MAX_QUERY_LEN} characters", validator="validate_query")
        raise PolicyError(f"query must be at most {MAX_QUERY_LEN} characters")


def validate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        audit_event("policy.blocked", reason="filters must be a dict or null", validator="validate_filters")
        raise PolicyError("filters must be a dict or null")
    out = {}
    for key, value in filters.items():
        if key not in ALLOWED_FILTER_KEYS:
            audit_event("policy.blocked", reason=f"filters allowlist: {sorted(ALLOWED_FILTER_KEYS)}, got {key!r}", validator="validate_filters")
            raise PolicyError(f"filters allowlist: {sorted(ALLOWED_FILTER_KEYS)}, got {key!r}")
        if value is not None and value != "":
            out[key] = str(value)
    return out


def validate_sql(query: str) -> None:
    if not query or not isinstance(query, str):
        audit_event("policy.blocked", reason="query is required and must be non-empty string", validator="validate_sql")
        raise PolicyError("query is required and must be non-empty string")
    q = query.strip()
    if not SELECT_ONLY.search(q):
        audit_event("policy.blocked", reason="Only SELECT is allowed", validator="validate_sql")
        raise PolicyError("Only SELECT is allowed")
    if FORBIDDEN_SQL_KEYWORDS.search(q):
        audit_event("policy.blocked", reason="Forbidden SQL keyword (INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/COPY/TRUNCATE)", validator="validate_sql")
        raise PolicyError("Forbidden SQL keyword (INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/COPY/TRUNCATE)")
    if ";" in q:
        audit_event("policy.blocked", reason="Semicolon (batch) not allowed", validator="validate_sql")
        raise PolicyError("Semicolon (batch) not allowed")
    for pat in FORBIDDEN_SQL_PATTERNS[1:]:
        if pat.search(q):
            audit_event("policy.blocked", reason="Access to pg_catalog/information_schema/pg_* functions not allowed", validator="validate_sql")
            raise PolicyError("Access to pg_catalog/information_schema/pg_* functions not allowed")
