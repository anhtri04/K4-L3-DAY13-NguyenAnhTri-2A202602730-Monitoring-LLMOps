from __future__ import annotations

import hashlib
import re

PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "cccd": r"\b\d{12}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    # NOTE (future): extra identifiers are intentionally deferred until they can be
    # matched with context, because bare patterns cause heavy false positives and
    # lossy redaction:
    #   - Vietnamese passport (~8 chars, e.g. B1234567): a bare r"\b[A-Z]\d{7,8}\b"
    #     also matches order IDs / product codes. Prefer a context-anchored rule such
    #     as r"(?i)(?:hộ chiếu|passport)\s*[:#]?\s*([A-Z]\d{7}|\d{8})" and redact only
    #     the captured group; this requires scrub_text() to support group replacement.
    #   - Vietnamese addresses (số nhà/đường/phường/quận/tỉnh...): not fixed-format and
    #     keyword redaction leaves the street/house number visible. Prefer data
    #     minimization (never log raw addresses) over regex detection.
    # Add such patterns only together with positive AND negative tests in tests/test_pii.py.
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
