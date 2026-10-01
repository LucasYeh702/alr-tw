"""Search-only Unicode projection with conservative authority-text offsets.

Authority text and existing hash definitions never change. A projected match
must map uniquely to a complete normalization cluster, or no quote is issued.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteLocation:
    start: int
    end: int
    exact_text: str
    authority_sha256: str


def _hangul(char: str) -> bool:
    return (
        "\u1100" <= char <= "\u11ff" or "\ua960" <= char <= "\ua97f" or "\ud7b0" <= char <= "\ud7ff"
    )


def search_projection(text: str) -> tuple[str, list[tuple[int, int]]]:
    if len(text) > 100000:
        raise ValueError("QUOTE_INPUT_TOO_LARGE")
    projected: list[str] = []
    offsets: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text) and (
            unicodedata.category(text[end]).startswith("M")
            or (_hangul(text[start]) and _hangul(text[end]))
        ):
            end += 1
        cluster = unicodedata.normalize("NFKC", text[start:end])
        for char in cluster:
            if char.isspace():
                if projected and projected[-1] == " ":
                    offsets[-1] = (offsets[-1][0], end)
                    continue
                char = " "
            projected.append(char)
            offsets.append((start, end))
        start = end
    return "".join(projected), offsets


def locate_quote(authority_text: str, query: str) -> QuoteLocation | None:
    if not query.strip() or len(query) > 10000:
        raise ValueError("QUOTE_QUERY_INVALID")
    projected, offsets = search_projection(authority_text)
    target, _ = search_projection(query)
    matches: set[tuple[int, int]] = set()
    index = projected.find(target)
    attempts = 0
    while index >= 0:
        attempts += 1
        if attempts > 64:
            return None
        start, end = offsets[index][0], offsets[index + len(target) - 1][1]
        # Reject a partial ligature/combining cluster and whitespace ambiguity.
        if search_projection(authority_text[start:end])[0] == target:
            matches.add((start, end))
        if len(matches) > 1:
            return None
        index = projected.find(target, index + 1)
    if not matches:
        return None
    start, end = next(iter(matches))
    return QuoteLocation(
        start, end, authority_text[start:end], hashlib.sha256(authority_text.encode()).hexdigest()
    )


def assemble_pages(pages: list[dict[str, object]], *, version: str, digest: str) -> str:
    """Validate overlapping authority pages without retaining a second text store."""
    if not pages or len(pages) > 256:
        raise ValueError("QUOTE_PAGES_INVALID")
    text = ""
    seen: set[int] = set()
    for page in pages:
        start, part = page.get("start"), page.get("text")
        if (
            page.get("version") != version
            or page.get("sha256") != digest
            or type(start) is not int
            or not isinstance(part, str)
            or not part
            or start < 0
            or start in seen
            or start > len(text)
        ):
            raise ValueError("QUOTE_PAGE_BINDING_INVALID")
        seen.add(start)
        overlap = len(text) - start
        if overlap > len(part) or text[start:] != part[:overlap]:
            raise ValueError("QUOTE_PAGE_OVERLAP_INVALID")
        text += part[overlap:]
        if len(text) > 100000:
            raise ValueError("QUOTE_INPUT_TOO_LARGE")
    if hashlib.sha256(text.encode()).hexdigest() != digest:
        raise ValueError("QUOTE_TEXT_INCOMPLETE")
    return text
