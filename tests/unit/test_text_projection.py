import hashlib
import pytest
from alr_tw.verification.text_projection import locate_quote, assemble_pages


@pytest.mark.parametrize(
    "text,query",
    [
        ("前綴第１條：ＡＢＣ。尾段", "第1條:ABC。"),
        ("前綴 e\u0301 文本", "é"),
        ("前綴\uf900文本", "豈"),
        ("前綴甲\r\n\t乙尾段", "甲 乙"),
        ("前綴\ufb00尾段", "ff"),
    ],
)
def test_maps_to_unchanged_authority(text, query):
    result = locate_quote(text, query)
    assert result is not None
    assert text[result.start : result.end] == result.exact_text
    assert result.authority_sha256 == hashlib.sha256(text.encode()).hexdigest()


def test_ambiguous_and_partial_cluster_do_not_invent_quote():
    assert locate_quote("甲乙甲", "甲") is None
    assert locate_quote("\ufb00", "f") is None
    assert locate_quote("abc", "absent") is None


def test_pagination_requires_complete_same_version_and_valid_overlap():
    text = "甲乙丙丁戊"
    digest = hashlib.sha256(text.encode()).hexdigest()
    pages = [
        dict(start=0, text="甲乙丙", version="v1", sha256=digest),
        dict(start=2, text="丙丁戊", version="v1", sha256=digest),
    ]
    assert assemble_pages(pages, version="v1", digest=digest) == text
    for bad in [
        pages[:1],
        pages + pages[1:],
        [pages[0], {**pages[1], "version": "v2"}],
        [pages[0], {**pages[1], "text": "錯丁戊"}],
        [pages[1]],
    ]:
        with pytest.raises(ValueError):
            assemble_pages(bad, version="v1", digest=digest)
