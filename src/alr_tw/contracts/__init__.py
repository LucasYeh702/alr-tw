"""Provider-neutral contracts for the ALR-TW governance core."""

from .providers import (
    DataMode,
    LegalSourceProvider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)
from .research import (
    CoverageState,
    PrivacyStatus,
    ResearchBlocker,
    ResearchDepth,
    ResearchObligation,
    ResearchObligationKind,
    ResearchObligationStatus,
    ResearchRun,
    ResearchState,
)
from .sources import (
    EvidenceSpan,
    EvidenceSectionType,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from .storage import (
    CleanupResult,
    OperationRecordResult,
    PurgeResult,
    StorageMode,
    StoragePolicy,
)

__all__ = [
    "CoverageState",
    "CleanupResult",
    "DataMode",
    "EvidenceSectionType",
    "EvidenceSpan",
    "MaterialType",
    "LegalSourceProvider",
    "PrivacyStatus",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderHealthStatus",
    "OperationRecordResult",
    "PurgeResult",
    "ResearchBlocker",
    "ResearchDepth",
    "ResearchObligation",
    "ResearchObligationKind",
    "ResearchObligationStatus",
    "ResearchRun",
    "ResearchState",
    "SourceRecord",
    "SourceTier",
    "StorageMode",
    "StoragePolicy",
    "TrustStatus",
]
