"""Bounded local search suggestions, never evidence or a legal-time decision."""
from __future__ import annotations

from datetime import date
import re
from typing import Any
import unicodedata

from alr_tw.providers.official.law_aliases import ALIAS_VERSION

PREPARATION_VERSION = "alr-tw.query-preparation/v1"
LEXICON_VERSION = "alr-tw.search-terms/v1"
MAX_QUERY_CODE_POINTS = 16_384
MAX_QUERY_BYTES = 65_536
MAX_EXPANSIONS = 6  # Includes the unmodified original query.
MAX_EXPANDED_LENGTH = 2_048
MAX_DATE_MENTIONS = 16

# Reviewed search vocabulary, not legal equivalence. Context-dependent terms
# are approximate or related; never rewrite a party role or a factual claim.
# Law abbreviations remain exclusively in the official law-alias policy.
TERMS = (
    ("違建", "違章建築", "equivalent"),
    ("房東", "出租人", "approximate"),
    ("房客", "承租人", "approximate"),
    ("押金", "押租金", "approximate"),
    ("加班費", "延長工時工資", "approximate"),
    ("監護權", "親權", "approximate"),
    ("探視", "會面交往", "approximate"),
    ("押金", "押租金返還", "related"),
    ("退租", "終止租賃契約", "related"),
    ("漏水", "修繕義務", "related"),
    ("違約金", "違約金酌減", "related"),
    ("監護權", "未成年子女最佳利益", "related"),
    ("監護權", "會面交往", "related"),
    ("罰單", "行政救濟", "related"),
)
_WEIGHTS = {"equivalent": 0.9, "approximate": 0.6, "related": 0.3}
_NUM = r"[0-9〇零一二兩三四五六七八九十百千]{1,8}"
_LAW = re.compile(rf"[\u3400-\u9fff]{{1,30}}(?:法|條例|規則|辦法)第\s*{_NUM}(?:之{_NUM})?\s*條")
_EXACT = re.compile(
    rf"{_LAW.pattern}|[A-Z0-9]{{3,12}},[^,\r\n]{{1,80}},[^,\r\n]{{1,80}},\d+,\d{{8}},\d+"
    rf"|法院(?:[\u3400-\u9fff]{{1,10}}分院)?\s*{_NUM}年(?:度)?.{{1,20}}字第\s*{_NUM}號"
)
_DATE = re.compile(
    rf"(?<![0-9])(?P<calendar>民國|西元)?\s*(?P<year>{_NUM})年"
    rf"(?:(?P<month>{_NUM})月(?:(?P<day>{_NUM})日)?)?"
    r"|(?<![0-9])(?P<iso_year>[0-9]{4})(?P<sep>[-/])(?P<iso_month>[0-9]{1,2})"
    r"(?P=sep)(?P<iso_day>[0-9]{1,2})(?![0-9])"
)
_ACT = ("行為時", "修法前", "修法後", "當時", "歷史法", "舊法")
_WEAK_ACT = ("發生", "事故", "簽約", "契約成立")


def validate_query(query: str) -> str:
    if type(query) is not str or not query.strip() or len(query) > MAX_QUERY_CODE_POINTS:
        raise ValueError("RESEARCH_QUERY_INVALID")
    if any(unicodedata.category(ch) in {"Cs", "Cf"} or
           (unicodedata.category(ch) == "Cc" and ch not in '\n\r\t') for ch in query):
        raise ValueError("RESEARCH_QUERY_INVALID")
    if len(query.encode('utf-8')) > MAX_QUERY_BYTES:
        raise ValueError("RESEARCH_QUERY_INVALID")
    return query


def _number(value: str) -> int:
    if value.isascii() and value.isdigit():
        return int(value)
    digits = dict(zip('〇零一二兩三四五六七八九', (0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9), strict=True))
    if all(ch in digits for ch in value):
        return int(''.join(str(digits[ch]) for ch in value))
    total, current, last_unit = 0, 0, 10000
    for ch in value:
        if ch in digits:
            current = digits[ch]
        else:
            unit = {'十': 10, '百': 100, '千': 1000}[ch]
            if unit >= last_unit:
                raise ValueError('invalid numeral')
            total += (current or 1) * unit
            current, last_unit = 0, unit
    return total + current


def time_hints(query: str, as_of_date: date | None = None) -> dict[str, Any]:
    text = unicodedata.normalize('NFKC', query)
    mentions: list[dict[str, Any]] = []
    warnings: list[str] = []
    for match in _DATE.finditer(text):
        # A case year or article number is not an event date.
        if re.search(r'第\s*$', text[:match.start()]) or re.match(r'\s*(?:度|字第|條)', text[match.end():]):
            continue
        if re.match(r'\s*[^\s\d，。；]{1,20}字\s*第', text[match.end():]):
            continue
        # Bare small numbers are durations unless a calendar/month establishes
        # a date. Duration syntax also wins for larger numbers (e.g. 100年以下).
        if match['iso_year'] is None and match['calendar'] is None:
            try:
                year_number = _number(match['year'])
            except (ValueError, KeyError):
                year_number = 10000  # Preserve malformed numerals for validation below.
            if (match['month'] is None and (year_number < 100 or re.search(
                r'(?:租期|期限|期間|時效|刑期)(?:為|是|共)?\s*$', text[:match.start()]
            ))) or re.match(
                r'\s*(?:內|間|以下|以上|以內|以外|之內|期限|期間)', text[match.end():]
            ):
                continue
        if len(mentions) == MAX_DATE_MENTIONS:
            warnings.append('DATE_MENTION_LIMIT')
            break
        iso = match['iso_year'] is not None
        raw_year = match['iso_year'] if iso else match['year']
        raw_month = match['iso_month'] if iso else match['month']
        raw_day = match['iso_day'] if iso else match['day']
        precision = 'day' if raw_day else 'month' if raw_month else 'year'
        calendar = 'ce'
        value = None
        try:
            year = _number(raw_year)
            if not iso and match['calendar'] != '西元' and year <= 300:
                calendar = 'roc'
                year += 1911
            elif match['calendar'] == '民國':
                raise ValueError('invalid roc year')
            month = _number(raw_month) if raw_month else 1
            day = _number(raw_day) if raw_day else 1
            checked = date(year, month, day)
            if year < 1912 or year > 2200:
                raise ValueError('outside supported years')
            value = checked.isoformat()[:{'day': 10, 'month': 7, 'year': 4}[precision]]
        except (ValueError, KeyError):
            warnings.append('INVALID_DATE_MENTION')
        mentions.append({'surface': match.group(0).strip(), 'calendar': calendar,
                         'precision': precision, 'value': value})
    distinct = {(m['value'], m['precision']) for m in mentions if m['value'] is not None}
    if len(distinct) > 1:
        warnings.append('MULTIPLE_DATE_MENTIONS')
    if any(m['precision'] != 'day' for m in mentions):
        warnings.append('INCOMPLETE_DATE_PRECISION')
    suggestion = (next(iter(distinct))[0] if len(distinct) == 1
                  and next(iter(distinct))[1] == 'day' and not warnings else None)
    act = any(word in text for word in _ACT)
    weak_act = any(word in text for word in _WEAK_ACT)
    if act and not mentions and as_of_date is None:
        warnings.append('EVENT_DATE_MISSING')
    if as_of_date and distinct and distinct != {(as_of_date.isoformat(), 'day')}:
        warnings.append('EXPLICIT_DATE_REQUIRES_RECONCILIATION')
    return {'date_mentions': mentions, 'suggested_as_of_date': suggestion,
            'explicit_as_of_date': as_of_date.isoformat() if as_of_date else None,
            'act_time_language': act or weak_act, 'needs_time_context': act or bool(mentions),
            'requires_clarification': bool(warnings) or bool((act or mentions) and as_of_date is None),
            'warnings': sorted(set(warnings)), 'automatically_applied': False}


def prepare_query(query: str, *, as_of_date: date | None = None) -> dict[str, Any]:
    original = validate_query(query)
    exact = _EXACT.search(unicodedata.normalize('NFKC', original)) is not None
    terms: list[dict[str, Any]] = [{'surface': surface, 'term': term, 'relation': relation, 'weight': _WEIGHTS[relation]}
             for surface, term, relation in TERMS if surface in original]
    queries = [{'query': original, 'relation': 'original', 'weight': 1.0}]
    warnings = []
    if exact:
        warnings.append('EXACT_CITATION_EXPANSION_SKIPPED')
    else:
        seen = {original}
        for item in terms:
            # Append search vocabulary. Never replace facts, negation or roles.
            expanded = original + ' ' + item['term']
            if expanded in seen or item['term'] in original:
                continue
            if len(expanded) > MAX_EXPANDED_LENGTH or len(queries) == MAX_EXPANSIONS:
                warnings.append('EXPANSION_LIMIT')
                continue
            seen.add(expanded)
            queries.append({'query': expanded, 'relation': item['relation'], 'weight': item['weight']})
    law_queries = [queries[0]]
    for item in terms:
        if exact or len(original) > MAX_EXPANDED_LENGTH:
            break
        if len(law_queries) == MAX_EXPANSIONS:
            break
        if item['term'] not in {row['query'] for row in law_queries}:
            law_queries.append({'query': item['term'], 'surface': item['surface'],
                                'relation': item['relation'], 'weight': item['weight']})
    ambiguous = (any(item['relation'] != 'equivalent' for item in terms)
                 or any(word in original for word in ('兩種', '多種', '歧義', '不確定')))
    temporal = time_hints(original, as_of_date)
    return {'schema_version': PREPARATION_VERSION, 'lexicon_version': LEXICON_VERSION,
            'law_alias_version': ALIAS_VERSION, 'original_query': original,
            'exact_citation': exact, 'term_candidates': terms, 'search_queries': queries,
            'law_search_queries': law_queries,
            'requires_clarification': ambiguous or temporal['requires_clarification'],
            'clarification_guidance': '近似與相關詞不是同義詞；確認詞義、研究範圍與事件時點後再採用。',
            'time_hints': temporal, 'warnings': sorted(set(warnings)),
            'candidate_only': True, 'answer_authorized': False,
            'execution_policy': 'original-first; official-only fallback; stop on results or error; shared run budget'}
