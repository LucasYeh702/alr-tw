"""Server-owned finalization and structured-refusal contracts.

This module is intentionally independent from the research service.  It
consumes server-produced run facts and produces a bounded posture for the
answer layer.  It never interprets a client proposal as evidence and it does
not duplicate claim/citation/privacy validation; existing verification
results can be attached as server-produced summaries.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .provider_snapshot import (
    ProviderSnapshotReceipt,
    SnapshotConsistency,
    SnapshotConsistencyResult,
    assess_snapshot_consistency,
)
from .research import (
    AnswerMode,
    ResearchObligationKind,
    ResearchRun,
    ResearchSufficiency,
    evaluate_research_sufficiency,
)


_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


def _as_list(value: object) -> list[object]:
    """Normalize a scalar or sequence without splitting a string."""

    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


class FinalizationBlocker(BaseModel):
    """Machine-readable reason that prevents an answer posture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=_ID_PATTERN)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False


class CounterAuthorityGate(BaseModel):
    """Server assessment of the bounded counter-authority obligation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    required: bool = True
    coverage_complete: bool = False
    consensus_claim_requested: bool = False
    consensus_claim_allowed: bool = False
    limitations: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("limitations", mode="before")
    @classmethod
    def normalize_limitations(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set, frozenset)):
            return [str(item) for item in value]
        raise TypeError("limitations must be a string or sequence")

    @model_validator(mode="after")
    def reject_unverifiable_consensus(self) -> CounterAuthorityGate:
        """Keep global-consensus authority disabled in the v0.8 contract.

        Counter-authority lookup is bounded and does not include a semantic
        opposition classifier.  A caller therefore cannot turn a completed
        bounded search into a global ``consensus`` assertion by setting this
        flag.  A future semantic-verifier receipt may introduce a new
        contract version; v0.8 remains fail-closed.
        """

        if self.consensus_claim_allowed:
            raise ValueError(
                "v0.8 finalization cannot authorize an unqualified consensus claim"
            )
        return self


class AbsenceClaimGate(BaseModel):
    """Whether an absence claim is actually justified within the search scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested: bool = False
    allowed: bool = False
    scope: str | None = Field(default=None, max_length=500)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("reason_codes", mode="before")
    @classmethod
    def normalize_reason_codes(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set, frozenset)):
            return [str(item) for item in value]
        raise TypeError("reason_codes must be a string or sequence")

    @model_validator(mode="after")
    def require_bounded_scope_when_allowed(self) -> AbsenceClaimGate:
        """Require a non-empty bounded scope before an absence claim is allowed."""

        if self.allowed and (self.scope is None or not self.scope.strip()):
            raise ValueError("an allowed absence claim requires a bounded scope")
        return self

class FinalizationContract(BaseModel):
    """Immutable, server-owned decision envelope for the final answer stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.finalization/v1"] = "alr-tw.finalization/v1"
    run_id: str = Field(pattern=_ID_PATTERN)
    research_schema_version: str = Field(min_length=1, max_length=100)
    trust_status: Literal["server_owned_finalization"] = "server_owned_finalization"
    workflow_complete: bool
    research_sufficiency: ResearchSufficiency
    answer_mode: AnswerMode
    allowed_source_ids: list[str] = Field(default_factory=list, max_length=256)
    allowed_evidence_ids: list[str] = Field(default_factory=list, max_length=512)
    required_qualification: list[str] = Field(default_factory=list, max_length=64)
    pending_support: list[str] = Field(default_factory=list, max_length=128)
    pending_lookups: list[str] = Field(default_factory=list, max_length=128)
    blockers: list[FinalizationBlocker] = Field(default_factory=list, max_length=64)
    safe_next_actions: list[str] = Field(default_factory=list, max_length=32)
    retryable: bool = False
    counter_authority: CounterAuthorityGate = Field(default_factory=CounterAuthorityGate)
    absence_claim: AbsenceClaimGate = Field(default_factory=AbsenceClaimGate)
    snapshot_receipts: list[ProviderSnapshotReceipt] = Field(default_factory=list, max_length=64)
    snapshot_consistency: SnapshotConsistencyResult | None = None
    answer_draft: str | None = Field(default=None, max_length=100_000)
    # These are results of existing validators.  Finalization consumes them;
    # it deliberately does not re-run or replace their citation/privacy logic.
    claim_support_summary: dict[str, object] | None = None
    privacy_allowed: bool | None = None

    @field_validator(
        "allowed_source_ids",
        "allowed_evidence_ids",
        "required_qualification",
        "pending_support",
        "pending_lookups",
        "safe_next_actions",
        mode="before",
    )
    @classmethod
    def normalize_string_sequences(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set, frozenset)):
            return [str(item) for item in value]
        raise TypeError("value must be a string or sequence")

    @field_validator("blockers", mode="before")
    @classmethod
    def normalize_blockers(cls, value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, str):
            return [{"code": value, "message": value}]
        normalized: list[object] = []
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise TypeError("blockers must be a string or sequence")
        for item in value:
            if isinstance(item, str):
                normalized.append({"code": item, "message": item})
            else:
                normalized.append(item)
        return normalized

    @field_validator("answer_draft", mode="before")
    @classmethod
    def discard_answer_body(cls, value: object) -> str | None:
        """Keep finalization as a pre-draft posture, never an answer envelope.

        ``answer_draft`` remains an input-compatible, deprecated field for
        clients that still send v0.7-shaped payloads.  It is intentionally
        discarded at the contract boundary; a caller that bypasses Pydantic
        validation with ``model_copy(update=...)`` is rejected by
        :func:`validate_finalization` below.
        """

        return None

    @model_validator(mode="after")
    def validate_ids_and_posture(self) -> FinalizationContract:
        for field_name in (
            "allowed_source_ids",
            "allowed_evidence_ids",
            "required_qualification",
            "pending_support",
            "pending_lookups",
            "safe_next_actions",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} values must be unique")
        if self.answer_mode in {AnswerMode.REFUSAL_ONLY} or self.blockers:
            if self.answer_draft is not None:
                raise ValueError("blocked/refusal finalization cannot carry an answer draft")
        if self.answer_mode is AnswerMode.CONDITIONAL and not self.required_qualification:
            raise ValueError("conditional finalization requires an explicit qualification")
        if self.answer_mode is AnswerMode.ORDINARY:
            if self.research_sufficiency is not ResearchSufficiency.SUFFICIENT:
                raise ValueError("ordinary finalization requires sufficient research")
            if not self.workflow_complete:
                raise ValueError("ordinary finalization requires workflow completion")
            if not self.allowed_source_ids or not self.allowed_evidence_ids:
                raise ValueError("ordinary finalization requires server evidence references")
            if self.pending_support or self.pending_lookups or self.blockers:
                raise ValueError("ordinary finalization cannot contain pending work or blockers")
            if (
                self.counter_authority.required
                and not self.counter_authority.coverage_complete
            ):
                raise ValueError("ordinary finalization requires counter-authority coverage")
            if (
                self.counter_authority.consensus_claim_requested
                and not self.counter_authority.consensus_claim_allowed
            ):
                raise ValueError("ordinary finalization cannot authorize an unqualified consensus claim")
            if self.absence_claim.requested and not self.absence_claim.allowed:
                raise ValueError("ordinary finalization cannot authorize an unsupported absence claim")
            if self.snapshot_consistency is None or not self.snapshot_consistency.consistent:
                raise ValueError("ordinary finalization requires a consistent snapshot receipt")
        return self

    @property
    def counter_authority_gate(self) -> CounterAuthorityGate:
        """Compatibility alias for adapters that name the nested gate explicitly."""

        return self.counter_authority

    @property
    def absence_claim_gate(self) -> AbsenceClaimGate:
        """Compatibility alias for adapters that name the nested gate explicitly."""

        return self.absence_claim

    @property
    def pending_support_ids(self) -> list[str]:
        return list(self.pending_support)

    @property
    def pending_lookup_ids(self) -> list[str]:
        return list(self.pending_lookups)


class FinalizationValidationResult(BaseModel):
    """Result of checking a finalization envelope against server-owned refs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.finalization-validation/v1"] = (
        "alr-tw.finalization-validation/v1"
    )
    run_id: str
    valid: bool
    answer_mode: AnswerMode
    # Finalization is a pre-draft gate.  Keep the legacy field for additive
    # readers, but make answer presentation impossible at this layer.
    safe_to_present: Literal[False] = False
    safe_to_draft: bool = False
    answer_draft: str | None = None
    required_qualification: list[str] = Field(default_factory=list)
    blockers: list[FinalizationBlocker] = Field(default_factory=list)
    safe_next_actions: list[str] = Field(default_factory=list)
    retryable: bool = False
    snapshot_consistency: SnapshotConsistencyResult


class StructuredRefusal(BaseModel):
    """Safe refusal payload; intentionally has no answer or client proposal field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["alr-tw.structured-refusal/v1"] = "alr-tw.structured-refusal/v1"
    run_id: str = Field(pattern=_ID_PATTERN)
    answer_mode: Literal["refusal_only"] = "refusal_only"
    reason_codes: list[str] = Field(min_length=1, max_length=64)
    safe_next_actions: list[str] = Field(default_factory=list, max_length=32)
    retryable: bool = False


def build_structured_refusal(
    result: FinalizationContract | FinalizationValidationResult,
) -> StructuredRefusal:
    """Project a blocked/refusal result into a payload safe for client output."""

    if isinstance(result, FinalizationContract):
        run_id = result.run_id
        blockers = result.blockers
        actions = result.safe_next_actions
        retryable = result.retryable
        mode = result.answer_mode
    else:
        run_id = result.run_id
        blockers = result.blockers
        actions = result.safe_next_actions
        retryable = result.retryable
        mode = result.answer_mode
    if mode is not AnswerMode.REFUSAL_ONLY and not blockers:
        raise ValueError("structured refusal requires refusal_only or blocked validation")
    reason_codes = list(dict.fromkeys(item.code for item in blockers))
    if not reason_codes:
        reason_codes = ["FINALIZATION_REFUSAL"]
    return StructuredRefusal(
        run_id=run_id,
        reason_codes=reason_codes,
        safe_next_actions=actions or ["完成必要研究後重新驗證"],
        retryable=retryable,
    )


def build_finalization_contract(
    *,
    run_id: str,
    workflow_complete: bool,
    research_sufficiency: ResearchSufficiency,
    allowed_source_ids: Sequence[str] = (),
    allowed_evidence_ids: Sequence[str] = (),
    coverage_complete: bool = False,
    time_context_complete: bool = False,
    authority_complete: bool = False,
    required_evidence_available: bool = True,
    counter_authority: CounterAuthorityGate | None = None,
    counter_authority_gate: CounterAuthorityGate | None = None,
    absence_claim: AbsenceClaimGate | None = None,
    absence_claim_gate: AbsenceClaimGate | None = None,
    required_qualification: Sequence[str] = (),
    pending_support: Sequence[str] = (),
    pending_lookups: Sequence[str] = (),
    blockers: Sequence[FinalizationBlocker | str] = (),
    safe_next_actions: Sequence[str] = (),
    retryable: bool = False,
    snapshot_receipts: Sequence[ProviderSnapshotReceipt] = (),
    server_source_ids: Sequence[str] | None = None,
    server_evidence_ids: Sequence[str] | None = None,
    server_snapshot_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
    research_schema_version: str = "alr-tw.research-run/v1",
    answer_draft: str | None = None,
    claim_support_summary: dict[str, object] | None = None,
    privacy_allowed: bool | None = None,
    now=None,
) -> FinalizationContract:
    """Build a posture from server-owned facts, never from client status flags.

    The caller should pass references read from the server's research run.  A
    later call to :func:`validate_finalization` binds those references to the
    authoritative run and rejects foreign IDs or receipts.
    """

    if counter_authority is not None and counter_authority_gate is not None:
        raise ValueError("provide only one counter-authority gate")
    if absence_claim is not None and absence_claim_gate is not None:
        raise ValueError("provide only one absence-claim gate")
    counter_value = counter_authority or counter_authority_gate
    counter = (
        counter_value
        if isinstance(counter_value, CounterAuthorityGate)
        else CounterAuthorityGate.model_validate(counter_value or {})
    )
    absence_value = absence_claim or absence_claim_gate
    absence = (
        absence_value
        if isinstance(absence_value, AbsenceClaimGate)
        else AbsenceClaimGate.model_validate(absence_value or {})
    )
    receipts = [
        item
        if isinstance(item, ProviderSnapshotReceipt)
        else ProviderSnapshotReceipt.model_validate(item)
        for item in _as_list(snapshot_receipts)
    ]
    source_values = [str(item) for item in _as_list(allowed_source_ids)]
    evidence_values = [str(item) for item in _as_list(allowed_evidence_ids)]
    qualification_values = [str(item) for item in _as_list(required_qualification)]
    pending_support_values = [str(item) for item in _as_list(pending_support)]
    pending_lookup_values = [str(item) for item in _as_list(pending_lookups)]
    action_values = [str(item) for item in _as_list(safe_next_actions)]
    blocker_inputs = _as_list(blockers)
    sufficiency = (
        research_sufficiency
        if isinstance(research_sufficiency, ResearchSufficiency)
        else ResearchSufficiency(research_sufficiency)
    )
    snapshot_result = assess_snapshot_consistency(
        receipts,
        server_receipts=server_snapshot_receipts,
        now=now,
    )

    qualification = qualification_values
    blocker_values = [
        item
        if isinstance(item, FinalizationBlocker)
        else FinalizationBlocker(code=str(item), message=str(item))
        for item in blocker_inputs
    ]

    def add_qualification(message: str) -> None:
        if message not in qualification:
            qualification.append(message)

    def add_blocker(code: str, message: str, *, is_retryable: bool = False) -> None:
        if not any(item.code == code for item in blocker_values):
            blocker_values.append(
                FinalizationBlocker(code=code, message=message, retryable=is_retryable)
            )

    if server_source_ids is not None:
        foreign_sources = sorted(set(source_values) - set(_as_list(server_source_ids)))
        if foreign_sources:
            add_blocker(
                "FINALIZATION_SOURCE_NOT_SERVER_OWNED",
                "Finalization contains source references outside the server-owned run.",
            )
    else:
        add_blocker(
            "FINALIZATION_SERVER_BINDING_REQUIRED",
            "Finalization requires an explicit server-owned source binding.",
        )
    if server_evidence_ids is not None:
        foreign_evidence = sorted(set(evidence_values) - set(_as_list(server_evidence_ids)))
        if foreign_evidence:
            add_blocker(
                "FINALIZATION_EVIDENCE_NOT_SERVER_OWNED",
                "Finalization contains evidence references outside the server-owned run.",
            )
    else:
        add_blocker(
            "FINALIZATION_SERVER_BINDING_REQUIRED",
            "Finalization requires an explicit server-owned evidence binding.",
        )

    if not workflow_complete:
        add_blocker("WORKFLOW_INCOMPLETE", "必要研究流程尚未完成。")
    if sufficiency is ResearchSufficiency.RETRY_REQUIRED:
        add_blocker("RESEARCH_RETRY_REQUIRED", "研究 provider 回報可重試錯誤。", is_retryable=True)
    elif sufficiency is ResearchSufficiency.INSUFFICIENT:
        add_blocker("RESEARCH_INSUFFICIENT", "目前研究不足以安全產生法律答案。")
    if pending_support_values:
        add_blocker("PENDING_CLAIM_SUPPORT", "仍有 claim support 尚待完成。")
    if pending_lookup_values:
        add_blocker("PENDING_SUPPORT_LOOKUP", "仍有必要的法源查詢尚待完成。")
    if not required_evidence_available or not evidence_values:
        add_blocker("SERVER_EVIDENCE_REQUIRED", "缺少可供最終答案使用的 server-owned evidence。")

    if not coverage_complete:
        add_qualification("法源涵蓋範圍未完整確認，結論僅限已驗證範圍。")
    if not time_context_complete:
        add_qualification("法律時點或版本覆蓋未完整確認。")
    if not authority_complete:
        add_qualification("法源權威層級或效力尚未完整確認。")
    if counter.required and not counter.coverage_complete:
        add_qualification("反向／相反裁判搜尋未完成，不得宣稱實務見解不存在或一致。")
    if counter.consensus_claim_requested and not counter.consensus_claim_allowed:
        add_qualification("目前不得作成實務見解一致的結論。")
    if absence.requested and not absence.allowed:
        add_qualification("目前搜尋範圍不足以支持不存在反面見解的主張。")
    if snapshot_result.status is SnapshotConsistency.LEGACY_NO_RECEIPT:
        add_qualification("此流程沒有 provider snapshot receipt，資料世代只能視為未知。")
    elif not snapshot_result.consistent:
        add_blocker(
            "SNAPSHOT_RECEIPT_MISMATCH",
            "同一研究混用不一致或非現行 provider snapshot。",
        )

    if claim_support_summary is not None and claim_support_summary.get("semantic_safe_to_present") is False:
        add_blocker("CLAIM_SUPPORT_UNSAFE", "既有 claim-support validator 未允許呈現。")
    if privacy_allowed is False:
        add_blocker("ANSWER_PRIVACY_NOT_ALLOWED", "既有 output-privacy validator 未允許呈現。")

    hard_blocked = bool(blocker_values)
    all_ordinary_gates = (
        workflow_complete
        and sufficiency is ResearchSufficiency.SUFFICIENT
        and coverage_complete
        and time_context_complete
        and authority_complete
        and required_evidence_available
        and bool(source_values)
        and bool(evidence_values)
        and not pending_support_values
        and not pending_lookup_values
        and not hard_blocked
        and (not counter.required or counter.coverage_complete)
        and (
            not counter.consensus_claim_requested
            or counter.consensus_claim_allowed
        )
        and (not absence.requested or absence.allowed)
        and snapshot_result.consistent
    )
    if all_ordinary_gates:
        mode = AnswerMode.ORDINARY
        qualification = []
    elif hard_blocked:
        mode = AnswerMode.REFUSAL_ONLY
    else:
        mode = AnswerMode.CONDITIONAL
        if not qualification:
            add_qualification("本次結論僅能以已揭露限制的條件式方式呈現。")

    if mode is AnswerMode.REFUSAL_ONLY:
        answer_draft = None
        if not action_values:
            action_values = ["完成必要研究 obligation 後重新驗證"]
    elif mode is AnswerMode.CONDITIONAL:
        if not action_values:
            action_values = ["保留限制並逐項確認缺失法源"]
    retryable = retryable or any(item.retryable for item in blocker_values)
    return FinalizationContract(
        run_id=run_id,
        research_schema_version=research_schema_version,
        workflow_complete=workflow_complete,
        research_sufficiency=research_sufficiency,
        answer_mode=mode,
        allowed_source_ids=source_values,
        allowed_evidence_ids=evidence_values,
        required_qualification=qualification,
        pending_support=pending_support_values,
        pending_lookups=pending_lookup_values,
        blockers=blocker_values,
        safe_next_actions=action_values,
        retryable=retryable,
        counter_authority=counter,
        absence_claim=absence,
        snapshot_receipts=receipts,
        snapshot_consistency=snapshot_result,
        answer_draft=answer_draft,
        claim_support_summary=claim_support_summary,
        privacy_allowed=privacy_allowed,
    )


def build_finalization_from_run(
    run: ResearchRun,
    *,
    snapshot_receipts: Sequence[ProviderSnapshotReceipt] = (),
    answer_draft: str | None = None,
    claim_support_summary: dict[str, object] | None = None,
    privacy_allowed: bool | None = None,
    now=None,
) -> FinalizationContract:
    """Build finalization from a server-owned ``ResearchRun`` snapshot.

    This helper intentionally invokes the canonical sufficiency evaluator and
    copies only run-owned IDs.  Client-provided ``workflow_complete``,
    ``research_sufficiency`` and ``answer_mode`` values are never consulted.
    """

    assessment = evaluate_research_sufficiency(run)
    coverage = run.coverage
    required_obligations = {
        item.kind
        for item in run.obligations
        if item.required and item.kind is not ResearchObligationKind.FINAL_ANSWER_VALIDATION
    }
    # The request flag is only a planning hint. A QUICK run may carry the
    # historical default ``include_counter_authority=True`` without actually
    # having a counter-authority obligation; that must not manufacture a gate.
    counter_required = ResearchObligationKind.COUNTER_AUTHORITY in required_obligations
    counter_complete = (
        not counter_required
        or (coverage.counter_authority_checked and coverage.coverage_complete)
    )
    time_required = ResearchObligationKind.LEGAL_TIME_CONTEXT in required_obligations
    time_context_complete = not time_required or coverage.time_context_checked
    counter = CounterAuthorityGate(
        required=counter_required,
        coverage_complete=counter_complete,
        # A bounded counter-authority search cannot certify a global
        # consensus.  That claim is an explicit answer request, not inferred
        # from coverage completion.
        consensus_claim_requested=False,
        consensus_claim_allowed=False,
        limitations=list(coverage.limitations),
    )
    bounded_absence_scope = coverage.bounded_query_scope
    absence_allowed = coverage.absence_claim_allowed and bool(
        bounded_absence_scope and bounded_absence_scope.strip()
    )
    absence = AbsenceClaimGate(
        requested=False,
        allowed=absence_allowed,
        scope=bounded_absence_scope,
        reason_codes=(
            []
            if absence_allowed
            else [
                (
                    "ABSENCE_CLAIM_SCOPE_MISSING"
                    if coverage.absence_claim_allowed
                    else "ABSENCE_CLAIM_NOT_ESTABLISHED"
                )
            ]
        ),
    )
    blocker_values = [
        FinalizationBlocker(
            code=item.code,
            message=item.message,
        )
        for item in run.blockers
    ]
    return build_finalization_contract(
        run_id=run.run_id,
        workflow_complete=assessment.workflow_complete,
        research_sufficiency=assessment.research_sufficiency,
        allowed_source_ids=run.source_ids,
        allowed_evidence_ids=run.evidence_ids,
        server_source_ids=run.source_ids,
        server_evidence_ids=run.evidence_ids,
        coverage_complete=coverage.coverage_complete,
        time_context_complete=time_context_complete,
        authority_complete=coverage.coverage_complete,
        required_evidence_available=bool(run.evidence_ids),
        counter_authority=counter,
        absence_claim=absence,
        required_qualification=assessment.reason_codes,
        blockers=blocker_values,
        snapshot_receipts=snapshot_receipts,
        server_snapshot_receipts=snapshot_receipts,
        answer_draft=answer_draft,
        claim_support_summary=claim_support_summary,
        privacy_allowed=privacy_allowed,
        now=now,
    )


def validate_finalization(
    contract: FinalizationContract,
    *,
    server_run_id: str,
    server_source_ids: Sequence[str],
    server_evidence_ids: Sequence[str],
    server_snapshot_receipts: Sequence[ProviderSnapshotReceipt] | None = None,
    server_run: ResearchRun | None = None,
    now=None,
) -> FinalizationValidationResult:
    """Bind a contract to one server-owned run and fail closed on foreign refs.

    ``server_run`` is an in-process, server-owned fact source.  A caller may
    still use this validator without it for non-presentable structural
    payloads, but an ordinary/conditional draft is refused unless workflow,
    sufficiency, and answer posture can be compared with that run snapshot.
    """

    blockers = list(contract.blockers)
    qualification = list(contract.required_qualification)

    def add_blocker(code: str, message: str) -> None:
        if not any(item.code == code for item in blockers):
            blockers.append(FinalizationBlocker(code=code, message=message))

    if contract.run_id != server_run_id:
        add_blocker(
            "FINALIZATION_RUN_NOT_SERVER_OWNED",
            "Finalization run_id does not match the server-owned research run.",
        )
    if contract.answer_draft is not None:
        add_blocker(
            "FINALIZATION_DRAFT_NOT_ALLOWED",
            "Finalization is a pre-draft posture and cannot carry answer content.",
        )
    source_ids = set(server_source_ids)
    evidence_ids = set(server_evidence_ids)
    foreign_sources = sorted(set(contract.allowed_source_ids) - source_ids)
    foreign_evidence = sorted(set(contract.allowed_evidence_ids) - evidence_ids)
    if foreign_sources:
        add_blocker(
            "FINALIZATION_SOURCE_NOT_SERVER_OWNED",
            "Finalization contains source references outside this run.",
        )
    if foreign_evidence:
        add_blocker(
            "FINALIZATION_EVIDENCE_NOT_SERVER_OWNED",
            "Finalization contains evidence references outside this run.",
        )

    presentable_mode = contract.answer_mode in {
        AnswerMode.ORDINARY,
        AnswerMode.CONDITIONAL,
    }
    if presentable_mode:
        if not contract.allowed_source_ids or not contract.allowed_evidence_ids:
            add_blocker(
                "FINALIZATION_SERVER_EVIDENCE_REQUIRED",
                "A presentable finalization must carry server-owned source and evidence IDs.",
            )
        if not source_ids or not evidence_ids:
            add_blocker(
                "FINALIZATION_SERVER_EVIDENCE_REQUIRED",
                "The server run must contain source and evidence IDs before presentation.",
            )

    server_contract: FinalizationContract | None = None
    if server_run is None:
        if presentable_mode:
            add_blocker(
                "FINALIZATION_SERVER_FACTS_REQUIRED",
                "Workflow and sufficiency must be checked against a server-owned run.",
            )
    else:
        if server_run.run_id != server_run_id:
            add_blocker(
                "FINALIZATION_SERVER_RUN_FACTS_MISMATCH",
                "Server run facts do not match the requested run.",
            )
        if set(server_run.source_ids) != source_ids:
            add_blocker(
                "FINALIZATION_SERVER_SOURCE_FACTS_MISMATCH",
                "Server source references do not match the server run snapshot.",
            )
        if set(server_run.evidence_ids) != evidence_ids:
            add_blocker(
                "FINALIZATION_SERVER_EVIDENCE_FACTS_MISMATCH",
                "Server evidence references do not match the server run snapshot.",
            )
        server_contract = build_finalization_from_run(
            server_run,
            snapshot_receipts=server_snapshot_receipts or (),
            now=now,
        )
        if presentable_mode:
            if contract.workflow_complete != server_contract.workflow_complete:
                add_blocker(
                    "FINALIZATION_WORKFLOW_FACTS_MISMATCH",
                    "Caller workflow status does not match the server-owned run.",
                )
            if contract.research_sufficiency is not server_contract.research_sufficiency:
                add_blocker(
                    "FINALIZATION_SUFFICIENCY_FACTS_MISMATCH",
                    "Caller sufficiency does not match the server-owned run.",
                )
            if server_contract.answer_mode is AnswerMode.REFUSAL_ONLY:
                add_blocker(
                    "FINALIZATION_SERVER_REFUSAL",
                    "The server-owned run is not eligible for a presentable answer.",
                )
            elif (
                contract.answer_mode is AnswerMode.ORDINARY
                and server_contract.answer_mode is not AnswerMode.ORDINARY
            ):
                add_blocker(
                    "FINALIZATION_SERVER_POSTURE_NOT_ORDINARY",
                    "Ordinary posture is not authorized by the server-owned run.",
                )
            missing_qualifications = set(server_contract.required_qualification) - set(
                contract.required_qualification
            )
            if missing_qualifications:
                add_blocker(
                    "FINALIZATION_SERVER_QUALIFICATION_MISSING",
                    "Caller finalization omitted a server-required qualification.",
                )
            if contract.counter_authority != server_contract.counter_authority:
                add_blocker(
                    "FINALIZATION_COUNTER_GATE_NOT_SERVER_OWNED",
                    "Counter-authority gate does not match the server-owned run.",
                )
            if contract.absence_claim != server_contract.absence_claim:
                add_blocker(
                    "FINALIZATION_ABSENCE_GATE_NOT_SERVER_OWNED",
                    "Absence-claim gate does not match the server-owned run.",
                )

    snapshot_result = assess_snapshot_consistency(
        contract.snapshot_receipts,
        server_receipts=server_snapshot_receipts,
        now=now,
    )
    if snapshot_result.status is SnapshotConsistency.FOREIGN_RECEIPT:
        add_blocker(
            "SNAPSHOT_RECEIPT_NOT_SERVER_OWNED",
            "Snapshot receipt is not issued for this server-owned run.",
        )
    elif snapshot_result.status is SnapshotConsistency.MISMATCH:
        add_blocker(
            "SNAPSHOT_RECEIPT_MISMATCH",
            "Snapshot receipts are inconsistent or stale.",
        )
    elif snapshot_result.status is SnapshotConsistency.LEGACY_NO_RECEIPT:
        if "SNAPSHOT_RECEIPT_MISSING_LEGACY" not in qualification:
            qualification.append("資料 snapshot receipt 未提供；本次結果不得視為完整世代驗證。")

    if contract.answer_mode is AnswerMode.ORDINARY:
        ordinary_fields = (
            contract.workflow_complete,
            contract.research_sufficiency is ResearchSufficiency.SUFFICIENT,
            not contract.required_qualification,
            not contract.pending_support,
            not contract.pending_lookups,
            (
                not contract.counter_authority.required
                or contract.counter_authority.coverage_complete
            ),
            (
                not contract.counter_authority.consensus_claim_requested
                or contract.counter_authority.consensus_claim_allowed
            ),
            (not contract.absence_claim.requested or contract.absence_claim.allowed),
            snapshot_result.consistent,
        )
        if not all(ordinary_fields):
            add_blocker(
                "ORDINARY_GATE_NOT_SATISFIED",
                "Ordinary answer mode does not satisfy all server finalization gates.",
            )

    # A caller cannot smuggle a draft through a blocked/refusal response.
    answer_mode = contract.answer_mode
    if blockers or answer_mode is AnswerMode.REFUSAL_ONLY:
        answer_mode = AnswerMode.REFUSAL_ONLY
        answer_draft = None
        safe_to_draft = False
    else:
        # A valid finalization permits the external client to begin drafting
        # from server-owned evidence; only validate_legal_answer can authorize
        # presentation of the resulting answer.
        answer_draft = None
        safe_to_draft = answer_mode in {AnswerMode.ORDINARY, AnswerMode.CONDITIONAL}
    unique_blockers = {item.code: item for item in blockers}
    return FinalizationValidationResult(
        run_id=server_run_id,
        valid=not unique_blockers,
        answer_mode=answer_mode,
        safe_to_draft=safe_to_draft,
        answer_draft=answer_draft,
        required_qualification=qualification,
        blockers=list(unique_blockers.values()),
        safe_next_actions=(
            list(contract.safe_next_actions)
            if not unique_blockers
            else list(contract.safe_next_actions)
            or ["完成必要研究後重新驗證"]
        ),
        retryable=contract.retryable or any(item.retryable for item in unique_blockers.values()),
        snapshot_consistency=snapshot_result,
    )
