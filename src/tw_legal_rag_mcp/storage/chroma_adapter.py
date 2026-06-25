from __future__ import annotations


class ChromaAdapterUnavailable(RuntimeError):
    pass


def connect_chroma() -> None:
    raise ChromaAdapterUnavailable("v0.1 demo does not connect to vector databases")
