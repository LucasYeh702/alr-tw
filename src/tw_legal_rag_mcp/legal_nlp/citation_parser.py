from __future__ import annotations

import re


LAW_ARTICLE_RE = re.compile(r"(?P<law>民法|刑法|勞基法)第?(?P<article>\d+)條?")
INTERPRETATION_RE = re.compile(r"釋字第(?P<number>\d+)號")
CONSTITUTIONAL_RE = re.compile(r"(?P<year>\d{2,3})年憲判字第(?P<number>\d+)號")
JUDGMENT_RE = re.compile(
    r"(?P<court>最高法院)(?P<year>\d{2,3})年度(?P<case_type>[\u4e00-\u9fff]+字)第(?P<number>\d+)號"
)


def parse_citation(text: str) -> dict[str, str] | None:
    compact = re.sub(r"\s+", "", text)

    if match := LAW_ARTICLE_RE.fullmatch(compact):
        law_name = match.group("law")
        article_no = match.group("article")
        return {
            "type": "law_article",
            "law_name": law_name,
            "article_no": article_no,
            "normalized": f"{law_name} 第{article_no}條",
        }

    if match := INTERPRETATION_RE.fullmatch(compact):
        number = match.group("number")
        return {
            "type": "constitutional_interpretation",
            "number": number,
            "normalized": f"釋字第{number}號",
        }

    if match := CONSTITUTIONAL_RE.fullmatch(compact):
        year = match.group("year")
        number = match.group("number")
        return {
            "type": "constitutional_judgment",
            "year": year,
            "number": number,
            "normalized": f"{year}年憲判字第{number}號",
        }

    if match := JUDGMENT_RE.fullmatch(compact):
        groups = match.groupdict()
        return {
            "type": "judgment",
            "court": groups["court"],
            "year": groups["year"],
            "case_type": groups["case_type"],
            "number": groups["number"],
            "normalized": (
                f"{groups['court']}{groups['year']}年度"
                f"{groups['case_type']}第{groups['number']}號"
            ),
        }

    return None
