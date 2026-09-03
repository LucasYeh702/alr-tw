"""TLR semantic-recall provider (candidate-only)."""

from .privacy import PrivacyScreenResult, screen_external_query
from .provider import (
    TlrAdministrativeSourceKind,
    TlrCandidateFulltextRecord,
    TlrCaseHistoryEntry,
    TlrCaseHistoryRecord,
    TlrFulltextPage,
    TlrSemanticRecallProvider,
)

__all__ = [
    "PrivacyScreenResult",
    "TlrAdministrativeSourceKind",
    "TlrCandidateFulltextRecord",
    "TlrCaseHistoryEntry",
    "TlrCaseHistoryRecord",
    "TlrFulltextPage",
    "TlrSemanticRecallProvider",
    "screen_external_query",
]
