from __future__ import annotations

import html
import re
from markupsafe import Markup

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_URL_RE = re.compile(r"(?<![\"'=])(https?://[^\s<]+)")


def _inline(value: str) -> str:
    """Render a deliberately small, escaped Markdown subset."""
    escaped = html.escape(value, quote=True)
    escaped = _CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _URL_RE.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', escaped)
    return escaped


def render_assistant_text(value: object) -> Markup:
    """Safely render model output as readable headings, paragraphs and lists.

    Model and release-note text is always escaped before the limited formatting
    rules are applied. Raw HTML is never trusted.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return Markup("")

    output: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            output.append(f"<p>{'<br>'.join(_inline(line) for line in paragraph)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = min(4, len(heading.group(1)) + 2)
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if bullet or numbered:
            flush_paragraph()
            desired = "ul" if bullet else "ol"
            if list_type != desired:
                close_list()
                output.append(f"<{desired}>")
                list_type = desired
            item = bullet.group(1) if bullet else numbered.group(1)
            output.append(f"<li>{_inline(item)}</li>")
            continue

        close_list()
        paragraph.append(line)

    flush_paragraph()
    close_list()
    return Markup("".join(output))
