from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]

ACTIVE_RECEIPT_DOCS = (
    "README.md",
    "README.zh-TW.md",
    "README.en.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "CHANGELOG.md",
    "docs/AGENTIC_HARNESS_ACCEPTANCE.md",
    "docs/AGENTIC_WORKFLOW.md",
    "docs/AGENT_CLIENT_GUIDE.md",
    "docs/ARCHITECTURE_CONTRACT.md",
    "docs/INTEROPERABILITY_CONTRACT.md",
    "docs/OFFICIAL_PROVIDERS.md",
    "docs/RELEASE_NOTES.md",
    "docs/STORAGE_AND_PURGE.md",
    "docs/TLR_PROVIDER.md",
    "DATA_POLICY.md",
)

PREDRAFT_DOCS = (
    "README.md",
    "README.zh-TW.md",
    "README.en.md",
    "ARCHITECTURE.md",
    "docs/AGENTIC_HARNESS_ACCEPTANCE.md",
    "docs/AGENTIC_WORKFLOW.md",
    "docs/AGENT_CLIENT_GUIDE.md",
    "docs/ARCHITECTURE_CONTRACT.md",
    "docs/INTEROPERABILITY_CONTRACT.md",
    "docs/RELEASE_NOTES.md",
    "docs/TRACE_SCHEMA.md",
)


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_active_docs_disclose_receipt_aware_runtime_boundary():
    for relative in ACTIVE_RECEIPT_DOCS:
        text = _read(relative).casefold()
        assert "provider-neutral" in text or "provider neutral" in text, relative
        assert "receipt-aware" in text, relative
        assert "conditional" in text and "qualified" in text, relative


def test_finalization_docs_describe_pre_draft_only():
    for relative in PREDRAFT_DOCS:
        text = _read(relative).casefold()
        assert "safe_to_draft" in text, relative
        assert "validate_legal_answer" in text, relative


def test_active_readmes_do_not_restate_an_archived_release_number():
    for relative in (
        "README.md",
        "README.zh-TW.md",
        "README.en.md",
        "ROADMAP.md",
        "docs/AGENTIC_HARNESS_ACCEPTANCE.md",
    ):
        assert "v0.7.1" not in _read(relative), relative


def test_release_notes_contain_changes_not_audit_results():
    text = _read("docs/RELEASE_NOTES.md").casefold()
    for forbidden in ("pytest", "ruff check", "mypy", "audit result", "passed"):
        assert forbidden not in text, forbidden
