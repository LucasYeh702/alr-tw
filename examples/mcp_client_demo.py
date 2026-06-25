from __future__ import annotations

from tw_legal_rag_mcp.mcp_server.tools import legal_search


def main() -> int:
    print(legal_search("房東不退押金怎麼辦？"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
