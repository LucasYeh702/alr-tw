"""Narrow display-name equivalence; never resolves or upgrades a source."""

from dataclasses import dataclass
import re

from alr_tw.contracts.sources import MaterialType, SourceRecord


@dataclass(frozen=True)
class JudgmentName:
    court: str
    year: str
    case: str
    number: str
    system: str | None
    kind: str | None

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.court, self.year, self.case, self.number


def _parse(value: str | None) -> JudgmentName | None:
    if not value or '\n' in value or '\r' in value:
        return None
    match = re.fullmatch(
        r'(?P<court>[\u3400-\u9fff]{2,30}法院(?:[\u3400-\u9fff]{1,10}分院)?)(?P<year>[0-9]{1,3})年(?:度)?'
        r'(?P<case>[\u3400-\u9fff]{1,20})字第(?P<number>[0-9]{1,12})號'
        r'(?P<system>民事|刑事|行政|懲戒)?(?P<kind>判決|裁定)?',
        re.sub(r'[^\S\r\n]', '', value),
    )
    if match is None:
        return None
    return JudgmentName(
        court=match['court'].replace('臺', '台'), year=match['year'],
        case=match['case'], number=match['number'], system=match['system'], kind=match['kind'],
    )


def judgment_name_equivalent(
    text: str, source: SourceRecord, sources: dict[str, SourceRecord],
) -> bool:
    """Use only server-owned citation/title and a unique same-run document.

    Case words, dates and document kinds are never deleted or guessed. Exact
    canonical citations retain their existing validation path in the caller.
    """
    if source.material_type != MaterialType.JUDGMENT:
        return False
    expected, supplied = _parse(source.citation), _parse(text)
    if expected is None or supplied is None or expected.identity != supplied.identity:
        return False
    identifier = source.official_identifier or ''
    parts = identifier.split(',')
    if (len(parts) != 6 or not re.fullmatch(r'[A-Z0-9]{3,12}', parts[0])
            or not re.fullmatch(r'[0-9]{8}', parts[4]) or not parts[5].isdigit()
            or tuple(parts[1:4]) != (expected.year, expected.case, expected.number)):
        return False
    # Different documents or different content snapshots under one display
    # identity are ambiguous, even if the caller bound only one evidence ID.
    candidates = {
        (item.official_identifier, item.content_hash)
        for item in sources.values()
        if item.material_type == MaterialType.JUDGMENT
        and any(name is not None and name.identity == expected.identity
                for name in (_parse(item.citation), _parse(item.title)))
    }
    if candidates != {(identifier, source.content_hash)}:
        return False
    title = _parse(source.title)
    if title is not None and title.identity != expected.identity:
        return False
    known_systems = {name.system for name in (expected, title) if name and name.system}
    known_kinds = {name.kind for name in (expected, title) if name and name.kind}
    if len(known_systems) > 1 or len(known_kinds) > 1:
        return False
    identifier_system = {"V": "民事", "M": "刑事", "A": "行政", "P": "懲戒"}.get(parts[0][-1])
    if identifier_system and known_systems and known_systems != {identifier_system}:
        return False
    # A missing suffix provides no evidence for a caller-added kind or system.
    return ((supplied.system is None or known_systems == {supplied.system})
            and (supplied.kind is None or known_kinds == {supplied.kind}))
