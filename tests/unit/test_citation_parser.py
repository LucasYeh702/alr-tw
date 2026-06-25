from tw_legal_rag_mcp.legal_nlp.citation_parser import parse_citation


def test_parse_law_article_patterns():
    assert parse_citation("民法第184條") == {
        "type": "law_article",
        "law_name": "民法",
        "article_no": "184",
        "normalized": "民法 第184條",
    }
    assert parse_citation("民法184")["normalized"] == "民法 第184條"


def test_parse_interpretation_and_constitutional_judgment():
    assert parse_citation("釋字第748號")["normalized"] == "釋字第748號"
    assert parse_citation("111年憲判字第13號")["normalized"] == "111年憲判字第13號"


def test_parse_supreme_court_judgment():
    parsed = parse_citation("最高法院111年度台上字第123號")

    assert parsed["type"] == "judgment"
    assert parsed["court"] == "最高法院"
    assert parsed["normalized"] == "最高法院111年度台上字第123號"


def test_invalid_citation_does_not_hallucinate_normalized_id():
    assert parse_citation("請幫我查房東押金問題") is None
