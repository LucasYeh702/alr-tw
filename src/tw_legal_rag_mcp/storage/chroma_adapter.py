from __future__ import annotations


class ChromaAdapterUnavailable(RuntimeError):
    pass


def connect_chroma() -> None:
    raise ChromaAdapterUnavailable("public demo does not connect to vector databases")
