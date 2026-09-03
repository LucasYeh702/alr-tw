"""Provider implementations for official sources and candidate recall."""

from alr_tw.contracts.providers import ProviderResult
from alr_tw.providers.sdk import (
    BoundedPublicLawProviderAdapter,
    GenericPublicLawProviderAdapter,
    PublicLawAdapter,
    PublicLawBackend,
    PublicLawBackendResult,
    PublicLawBackendStatus,
    PublicLawMetadataIssuer,
    PublicLawProviderAdapter,
    PublicLawSourcePromoter,
)
from alr_tw.providers.legislative_history import (
    LegislativeHistoryBackend,
    LegislativeHistoryProviderAdapter,
)
from alr_tw.providers.legislative_yuan import (
    LegislativeYuanBackend,
    LegislativeYuanConnector,
    LegislativeYuanDataBackend,
    LegislativeYuanHttpClient,
    LegislativeYuanHttpTransport,
    LegislativeYuanProviderAdapter,
)
from alr_tw.providers.receipt_adapter import (
    ProviderReceiptIssuer,
    ReceiptAwareProviderAdapter,
    ReceiptAwareProviderEnvelope,
)
from alr_tw.providers.local_portal import (
    LOCAL_PORTAL_PROVIDER_ID,
    LOCAL_PORTAL_ROOT_ENV,
    LocalPortalJudgmentProvider,
    build_local_portal_judgment_provider,
    local_portal_root_from_env,
)

__all__ = [
    "BoundedPublicLawProviderAdapter",
    "GenericPublicLawProviderAdapter",
    "ProviderResult",
    "PublicLawAdapter",
    "PublicLawBackend",
    "PublicLawBackendResult",
    "PublicLawBackendStatus",
    "PublicLawMetadataIssuer",
    "PublicLawProviderAdapter",
    "PublicLawSourcePromoter",
    "LegislativeHistoryBackend",
    "LegislativeHistoryProviderAdapter",
    "LegislativeYuanBackend",
    "LegislativeYuanConnector",
    "LegislativeYuanDataBackend",
    "LegislativeYuanHttpClient",
    "LegislativeYuanHttpTransport",
    "LegislativeYuanProviderAdapter",
    "ProviderReceiptIssuer",
    "ReceiptAwareProviderAdapter",
    "ReceiptAwareProviderEnvelope",
    "LOCAL_PORTAL_PROVIDER_ID",
    "LOCAL_PORTAL_ROOT_ENV",
    "LocalPortalJudgmentProvider",
    "build_local_portal_judgment_provider",
    "local_portal_root_from_env",
]
