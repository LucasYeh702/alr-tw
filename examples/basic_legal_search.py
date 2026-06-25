from __future__ import annotations

import json

from tw_legal_rag_mcp.retrieval.search_coordinator import demo_search
from tw_legal_rag_mcp.verification.answer_validation import answer_with_validation


def main() -> int:
    result = demo_search("房東不退押金怎麼辦？")
    wrapped = answer_with_validation("以下結果僅為 synthetic demo，不能作為法律意見。", result["results"])
    print(json.dumps({"search": result, "answer": wrapped}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
