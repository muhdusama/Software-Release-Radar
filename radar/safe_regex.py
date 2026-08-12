from __future__ import annotations

import regex

MAX_PATTERN_CHARS = 512
MAX_TEXT_CHARS = 100_000
MAX_RESULT_CHARS = 1_024
DEFAULT_TIMEOUT_SECONDS = 0.25


class SafeRegexError(ValueError):
    pass


class SafeRegexTimeout(SafeRegexError):
    pass


def validate_pattern(pattern: str) -> str:
    value = str(pattern or "").strip()
    if not value:
        raise SafeRegexError("A version regular expression is required.")
    if len(value) > MAX_PATTERN_CHARS:
        raise SafeRegexError(
            f"Version regular expression must not exceed {MAX_PATTERN_CHARS} characters."
        )
    try:
        regex.compile(value, regex.MULTILINE)
    except regex.error as exc:
        raise SafeRegexError(f"Version regular expression is invalid: {exc}") from exc
    return value


def search_version(
    pattern: str,
    text: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Run a user-defined expression with strict size and execution limits."""
    checked = validate_pattern(pattern)
    bounded_text = str(text or "")[:MAX_TEXT_CHARS]
    try:
        match = regex.search(
            checked,
            bounded_text,
            regex.MULTILINE,
            timeout=max(0.01, min(float(timeout), 2.0)),
        )
    except TimeoutError as exc:
        raise SafeRegexTimeout(
            "Version regular expression exceeded the execution time limit."
        ) from exc
    except regex.error as exc:
        raise SafeRegexError(f"Version regular expression failed: {exc}") from exc

    if match is None:
        return None
    value = match.group(1) if match.groups() else match.group(0)
    result = str(value or "").strip()
    if len(result) > MAX_RESULT_CHARS:
        raise SafeRegexError(
            f"Version regular expression result must not exceed {MAX_RESULT_CHARS} characters."
        )
    return result
