"""Structure-preserving parser for Judicial Yuan ordinary judgments."""

from __future__ import annotations

import html
import re
import unicodedata
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.judgment_semantics import (
    AttributionConfidence,
    DispositionRelation,
    JudgmentDisposition,
    JudgmentSpeaker,
    JudgmentStance,
    classify_disposition_text,
)

PARSER_VERSION = "judgment-parser/v3"


class JudgmentParseStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class JudgmentRole(str, Enum):
    DISPOSITION = "disposition"
    COURT_REASONING = "court_reasoning"
    COURT_HOLDING = "court_holding"
    PARTY_ARGUMENT = "party_argument"
    FACTS = "facts"
    PROCEDURE = "procedure"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ParsedJudgmentSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str = Field(min_length=1)
    heading: str | None = None
    role: JudgmentRole
    exact_text: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    eligible_for_claim_support: bool
    speaker: JudgmentSpeaker = JudgmentSpeaker.UNKNOWN
    stance: JudgmentStance = JudgmentStance.UNKNOWN
    relation_to_disposition: DispositionRelation = DispositionRelation.UNKNOWN
    attribution_confidence: AttributionConfidence = AttributionConfidence.LOW


class ParsedJudgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_jid: str = Field(min_length=1)
    full_text: str = Field(min_length=1)
    parse_status: JudgmentParseStatus
    sections: list[ParsedJudgmentSection]
    unparsed_remainder: str | None = None
    warnings: list[str] = Field(default_factory=list)
    parser_version: str = PARSER_VERSION
    disposition_codes: list[JudgmentDisposition] = Field(default_factory=list)


_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "input",
    "button",
    "select",
    "option",
    "svg",
    "nav",
}
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "dt",
    "dd",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

_HEADINGS: dict[str, JudgmentRole] = {
    "主文": JudgmentRole.DISPOSITION,
    "理由": JudgmentRole.COURT_REASONING,
    "得心證之理由": JudgmentRole.COURT_REASONING,
    "法院之判斷": JudgmentRole.COURT_HOLDING,
    "本院之判斷": JudgmentRole.COURT_HOLDING,
    "事實及理由": JudgmentRole.MIXED,
    "犯罪事實及理由": JudgmentRole.MIXED,
    "事實及法律理由": JudgmentRole.MIXED,
    "事實暨理由": JudgmentRole.MIXED,
    "事實概要": JudgmentRole.FACTS,
    "程序事項": JudgmentRole.PROCEDURE,
    "爭點": JudgmentRole.UNKNOWN,
}
_PARTY_MARKERS = (
    "上訴意旨",
    "抗告意旨",
    "聲請意旨",
    "答辯意旨",
    "原告主張",
    "被告辯稱",
    "被告抗辯",
    "被告則以",
    "上訴人主張",
    "被上訴人抗辯",
    "抗辯略以",
    "主張略以",
    "原告起訴主張",
)
_COURT_MARKERS = (
    "本院認為",
    "本院認定",
    "本院判斷",
    "本院審酌",
    "本院查",
    "法院認為",
    "法院判斷",
    "經本院審酌",
    "經查",
    "按",
)
_COURT_REBUTTAL_MARKERS = (
    "無足採",
    "不足採",
    "無可採",
    "難以採信",
    "不足為據",
    "為無理由",
)
_LOWER_COURT_MARKERS = (
    "原審",
    "原判決",
    "原裁定",
    "前審",
    "第一審",
    "第二審",
)
_LOWER_COURT_REJECTION_MARKERS = (
    "應予廢棄",
    "不足採",
    "無足採",
    "無可採",
    "難以採信",
    "尚有未洽",
    "有所違誤",
    "不無違誤",
    "非可採",
    "不可採",
    "不免率斷",
)
_CURRENT_COURT_MARKERS = _COURT_MARKERS + (
    "本院",
    "本庭",
)
_CURRENT_COURT_ADOPTION_MARKERS = (
    "並無違誤",
    "尚無違誤",
    "並無不合",
    "尚無不合",
    "並無不當",
    "尚無不當",
    "無何違誤",
)


def extract_judgment_blocks(content: Any) -> list[str]:
    """Recursively extract normalized text while preserving block boundaries."""

    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        text = _normalize_inline(" ".join(current))
        current.clear()
        if text and (not blocks or blocks[-1] != text):
            blocks.append(text)

    def walk(node: Any, *, preformatted: bool = False) -> None:
        name = str(getattr(node, "name", "") or "").lower()
        if name:
            if name in _SKIP_TAGS or _is_hidden(node):
                return
            if name == "br":
                flush()
                return
            is_block = name in _BLOCK_TAGS
            if is_block:
                flush()
            child_preformatted = preformatted or _is_preformatted_container(node)
            for child in getattr(node, "children", ()):
                walk(child, preformatted=child_preformatted)
            if is_block:
                flush()
            return

        value = str(node)
        if re.search(r"[\r\n]", value) and (
            preformatted or _has_structural_newlines(value)
        ):
            for part in re.split(r"(\r\n|\r|\n)", value):
                if part in {"\r\n", "\r", "\n"}:
                    flush()
                    continue
                normalized = _normalize_inline(part)
                if normalized:
                    current.append(normalized)
            return
        normalized = _normalize_inline(value)
        if normalized:
            current.append(normalized)

    walk(content)
    flush()
    return blocks


def parse_judgment_blocks(blocks: list[str], *, canonical_jid: str) -> ParsedJudgment:
    normalized_blocks = [_normalize_inline(item) for item in blocks]
    normalized_blocks = [item for item in normalized_blocks if item]
    normalized_blocks = _coalesce_heading_fragments(normalized_blocks)
    if not normalized_blocks:
        raise ValueError("JUDGMENT_TEXT_EMPTY")

    sections: list[ParsedJudgmentSection] = []
    current_role = JudgmentRole.UNKNOWN
    current_heading: str | None = None
    current_confidence: Literal["high", "medium", "low"] = "low"

    for block in normalized_blocks:
        heading = _heading_role(block)
        if heading is not None:
            current_heading, current_role = heading
            current_confidence = (
                "high"
                if current_role
                in {
                    JudgmentRole.DISPOSITION,
                    JudgmentRole.COURT_REASONING,
                    JudgmentRole.COURT_HOLDING,
                }
                else "medium"
            )
            continue

        role, confidence = _paragraph_role(
            block,
            current_role=current_role,
            current_confidence=current_confidence,
        )
        if role in {JudgmentRole.PARTY_ARGUMENT, JudgmentRole.COURT_REASONING}:
            current_role = role
            current_confidence = confidence
        eligible = confidence == "high" and role in {
            JudgmentRole.DISPOSITION,
            JudgmentRole.COURT_HOLDING,
            JudgmentRole.COURT_REASONING,
        }
        sections.append(
            ParsedJudgmentSection(
                section_id=f"section-{len(sections) + 1:03d}",
                heading=current_heading,
                role=role,
                exact_text=block,
                confidence=confidence,
                eligible_for_claim_support=eligible,
            )
        )

    has_disposition = any(item.role is JudgmentRole.DISPOSITION for item in sections)
    disposition_codes = _disposition_codes(sections)
    attributed_sections: list[ParsedJudgmentSection] = []
    for item in sections:
        speaker, stance, relation, attribution_confidence, semantic_eligible = (
            _paragraph_attribution(
                item,
                has_disposition=has_disposition,
                disposition_codes=disposition_codes,
            )
        )
        attributed_sections.append(
            item.model_copy(
                update={
                    "eligible_for_claim_support": item.eligible_for_claim_support
                    and semantic_eligible,
                    "speaker": speaker,
                    "stance": stance,
                    "relation_to_disposition": relation,
                    "attribution_confidence": attribution_confidence,
                }
            )
        )
    sections = attributed_sections
    has_court_reasoning = any(
        item.eligible_for_claim_support
        and item.role in {JudgmentRole.COURT_HOLDING, JudgmentRole.COURT_REASONING}
        for item in sections
    )
    unparsed = [
        item.exact_text
        for item in sections
        if item.role in {JudgmentRole.UNKNOWN, JudgmentRole.MIXED}
    ]
    warnings: list[str] = []
    parse_status = (
        JudgmentParseStatus.COMPLETE
        if has_disposition and has_court_reasoning
        else JudgmentParseStatus.PARTIAL
    )
    if parse_status is JudgmentParseStatus.PARTIAL:
        warnings.append("JUDGMENT_PARSE_PARTIAL")
    if not has_disposition:
        warnings.append("JUDGMENT_DISPOSITION_MISSING")
    if not disposition_codes or all(
        code is JudgmentDisposition.UNKNOWN for code in disposition_codes
    ):
        warnings.append("JUDGMENT_DISPOSITION_UNRESOLVED")
    if not has_court_reasoning:
        warnings.append("JUDGMENT_COURT_REASONING_MISSING")
    if any(item.speaker is JudgmentSpeaker.LOWER_COURT for item in sections):
        warnings.append("JUDGMENT_LOWER_COURT_ATTRIBUTION_PRESENT")
    if any(item.speaker is JudgmentSpeaker.UNKNOWN for item in sections):
        warnings.append("JUDGMENT_ATTRIBUTION_UNCERTAIN")
    if unparsed:
        warnings.append("JUDGMENT_UNCLASSIFIED_TEXT")

    return ParsedJudgment(
        canonical_jid=canonical_jid,
        full_text="\n".join(normalized_blocks),
        parse_status=parse_status,
        sections=sections,
        unparsed_remainder="\n".join(unparsed) or None,
        warnings=warnings,
        disposition_codes=disposition_codes,
    )


def _disposition_codes(
    sections: list[ParsedJudgmentSection],
) -> list[JudgmentDisposition]:
    values: list[JudgmentDisposition] = []
    for section in sections:
        if section.role is not JudgmentRole.DISPOSITION:
            continue
        for value in classify_disposition_text(section.exact_text):
            if value not in values:
                values.append(value)
    return values or [JudgmentDisposition.UNKNOWN]


def _paragraph_attribution(
    section: ParsedJudgmentSection,
    *,
    has_disposition: bool,
    disposition_codes: list[JudgmentDisposition],
) -> tuple[
    JudgmentSpeaker,
    JudgmentStance,
    DispositionRelation,
    AttributionConfidence,
    bool,
]:
    """Assign conservative speaker/stance metadata to a parsed paragraph."""

    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", section.exact_text))
    lower_marked = any(marker in compact for marker in _LOWER_COURT_MARKERS)
    rejection_marked = any(marker in compact for marker in _LOWER_COURT_REJECTION_MARKERS)
    court_rebuttal_marked = any(marker in compact for marker in _COURT_REBUTTAL_MARKERS)
    current_marked = any(marker in compact for marker in _CURRENT_COURT_MARKERS)
    court_adoption_marked = any(
        marker in compact for marker in _CURRENT_COURT_ADOPTION_MARKERS
    )
    explicit_current_rejection = rejection_marked or (current_marked and court_rebuttal_marked)
    relation = (
        DispositionRelation.SUPPORTS_RESULT
        if has_disposition
        else DispositionRelation.UNKNOWN
    )
    rejection_relation = (
        DispositionRelation.REASON_FOR_REMAND
        if JudgmentDisposition.VACATED_REMANDED in disposition_codes
        else relation
    )

    if section.role is JudgmentRole.DISPOSITION:
        return (
            JudgmentSpeaker.CURRENT_COURT,
            JudgmentStance.DESCRIBES,
            DispositionRelation.SUPPORTS_RESULT,
            AttributionConfidence.HIGH,
            True,
        )
    if section.role is JudgmentRole.PARTY_ARGUMENT:
        return (
            JudgmentSpeaker.PARTY,
            JudgmentStance.DESCRIBES,
            DispositionRelation.BACKGROUND_ONLY,
            AttributionConfidence.HIGH,
            False,
        )
    if lower_marked and explicit_current_rejection:
        return (
            JudgmentSpeaker.CURRENT_COURT,
            JudgmentStance.REJECTS,
            rejection_relation if has_disposition else DispositionRelation.UNKNOWN,
            AttributionConfidence.MEDIUM if not current_marked else AttributionConfidence.HIGH,
            has_disposition,
        )
    if lower_marked:
        if current_marked and court_adoption_marked:
            return (
                JudgmentSpeaker.CURRENT_COURT,
                JudgmentStance.ADOPTS,
                relation,
                AttributionConfidence.HIGH,
                has_disposition,
            )
        if current_marked:
            return (
                JudgmentSpeaker.UNKNOWN,
                JudgmentStance.UNKNOWN,
                DispositionRelation.UNKNOWN,
                AttributionConfidence.LOW,
                False,
            )
        return (
            JudgmentSpeaker.LOWER_COURT,
            JudgmentStance.DESCRIBES,
            DispositionRelation.BACKGROUND_ONLY,
            AttributionConfidence.HIGH,
            False,
        )
    if section.role in {
        JudgmentRole.COURT_HOLDING,
        JudgmentRole.COURT_REASONING,
    }:
        return (
            JudgmentSpeaker.CURRENT_COURT,
            JudgmentStance.REJECTS if court_rebuttal_marked else JudgmentStance.DESCRIBES,
            relation,
            AttributionConfidence.HIGH if current_marked else AttributionConfidence.MEDIUM,
            has_disposition,
        )
    if section.role is JudgmentRole.PROCEDURE:
        return (
            JudgmentSpeaker.CURRENT_COURT,
            JudgmentStance.PROCEDURAL_ONLY,
            DispositionRelation.BACKGROUND_ONLY,
            AttributionConfidence.MEDIUM,
            False,
        )
    return (
        JudgmentSpeaker.UNKNOWN,
        JudgmentStance.UNKNOWN,
        DispositionRelation.UNKNOWN,
        AttributionConfidence.LOW,
        False,
    )


def _heading_role(value: str) -> tuple[str, JudgmentRole] | None:
    normalized = _normalize_heading(value)
    role = _HEADINGS.get(normalized)
    return (normalized, role) if role is not None else None


def _coalesce_heading_fragments(blocks: list[str]) -> list[str]:
    """Join only adjacent fragments that together form a known heading."""

    output: list[str] = []
    index = 0
    while index < len(blocks):
        matched: str | None = None
        consumed = 0
        for width in range(min(8, len(blocks) - index), 1, -1):
            candidate = "".join(blocks[index : index + width])
            if _normalize_heading(candidate) in _HEADINGS:
                matched = candidate
                consumed = width
                break
        if matched is None:
            output.append(blocks[index])
            index += 1
        else:
            output.append(matched)
            index += consumed
    return output


def _normalize_heading(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value)).strip()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(
        r"^(?:(?:第?[一二三四五六七八九十百零〇0-9]+)[、.．]|[壹貳參肆伍陸柒捌玖拾]+[、.．])",
        "",
        normalized,
    )
    return normalized.rstrip("：:")


def _paragraph_role(
    text: str,
    *,
    current_role: JudgmentRole,
    current_confidence: Literal["high", "medium", "low"],
) -> tuple[JudgmentRole, Literal["high", "medium", "low"]]:
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    compact = re.sub(r"^(?:[一二三四五六七八九十百零〇0-9]+)[、.．]", "", compact)
    party_probe = re.sub(r"^(?:按|查)[，,：:]?", "", compact)
    party_marked = any(
        candidate.startswith(marker)
        for candidate in (compact, party_probe)
        for marker in _PARTY_MARKERS
    )
    court_prefixed = compact != party_probe
    if (
        court_prefixed
        and party_marked
        and any(marker in compact for marker in _COURT_REBUTTAL_MARKERS)
    ):
        return JudgmentRole.COURT_REASONING, "high"
    if party_marked:
        return JudgmentRole.PARTY_ARGUMENT, "high"
    if any(compact.startswith(marker) for marker in _COURT_MARKERS):
        return JudgmentRole.COURT_REASONING, "high"
    if current_role is JudgmentRole.MIXED:
        return JudgmentRole.UNKNOWN, "low"
    if current_role is JudgmentRole.UNKNOWN:
        return JudgmentRole.UNKNOWN, "low"
    return current_role, current_confidence


def _normalize_inline(value: str) -> str:
    return re.sub(r"[\s\u00a0\u3000]+", " ", html.unescape(value)).strip()


def _is_hidden(node: Any) -> bool:
    attrs = getattr(node, "attrs", {}) or {}
    if "hidden" in attrs or str(attrs.get("aria-hidden") or "").lower() == "true":
        return True
    style = re.sub(r"\s+", "", str(attrs.get("style") or "")).lower()
    return "display:none" in style or "visibility:hidden" in style


def _is_preformatted_container(node: Any) -> bool:
    name = str(getattr(node, "name", "") or "").lower()
    attrs = getattr(node, "attrs", {}) or {}
    classes = attrs.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    style = re.sub(r"\s+", "", str(attrs.get("style") or "")).lower()
    return name == "pre" or "text-pre" in classes or "white-space:pre" in style


def _has_structural_newlines(value: str) -> bool:
    lines = [_normalize_inline(item) for item in re.split(r"\r\n|\r|\n", value)]
    return any(_normalize_heading(line) in _HEADINGS for line in lines if line)
