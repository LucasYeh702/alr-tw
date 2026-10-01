"""Opt-in command adapter for a trusted operator's semantic model gateway.

The gateway consumes one JSON request on stdin and writes one protocol result
to the provided output file. It is never selected by MCP caller input. No
gateway is enabled by default; model aliases are an explicit operator contract.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.semantic_verifier import (
    SemanticVerifierRequest,
    SemanticVerifierResult,
    SemanticVerifierTarget,
    SemanticVerificationTargetKind,
    execute_semantic_verifier,
)
from alr_tw.research.draft_workspace import _registered_law_digests, review_draft
from alr_tw.storage.sqlite_store import SqliteStore
from alr_tw.contracts.sources import TrustStatus


class AdvisorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(min_length=1, max_length=32)
    model: str
    timeout_seconds: int = Field(default=90, ge=1, le=180)


class CommandSemanticVerifier:
    plugin_id = "operator_semantic_gateway"
    plugin_version = "1"

    def __init__(self, config: AdvisorConfig, evidence_packet: list[dict[str, Any]]):
        # Explicit supported baselines, not a guessed ordering of arbitrary names.
        if config.model not in {
            "gpt-5.6-luna",
            "gpt-6-astra",
            "gemini-3.8-flash",
            "gemini-3.8-flash-high",
        }:
            raise ValueError("ADVISOR_MODEL_NOT_APPROVED")
        if not Path(config.command[0]).is_absolute():
            raise ValueError("ADVISOR_EXECUTABLE_MUST_BE_ABSOLUTE")
        self.config = config
        self.evidence_packet = evidence_packet

    def verify(self, request: SemanticVerifierRequest) -> SemanticVerifierResult:
        payload = {
            "request": request.model_dump(mode="json"),
            "evidence": self.evidence_packet,
            "model": self.config.model,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "result_schema": SemanticVerifierResult.model_json_schema(),
        }
        with tempfile.TemporaryDirectory(prefix="alr-advisor-") as directory:
            output = Path(directory) / "result.json"
            try:
                process = subprocess.Popen(
                    [*self.config.command, "--output", str(output)],
                    stdin=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    process.communicate(
                        json.dumps(payload, ensure_ascii=False), timeout=self.config.timeout_seconds
                    )
                    if process.returncode:
                        raise ValueError("ADVISOR_CALL_FAILED")
                finally:
                    # A timed-out gateway must not leave model processes running.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                if output.is_symlink() or not output.is_file():
                    raise ValueError("ADVISOR_RESULT_INVALID")
                with output.open("rb") as stream:
                    raw = stream.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("ADVISOR_RESULT_TOO_LARGE")
                return SemanticVerifierResult.model_validate_json(raw)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                raise ValueError("ADVISOR_CALL_FAILED") from exc


def advise_draft(
    store: SqliteStore, run_id: str, draft: dict[str, Any], config: AdvisorConfig
) -> dict[str, Any]:
    workspace = review_draft(store, run_id, draft["answer_text"], draft["claim_bindings"])
    if workspace["draft_text"] is None:
        return {
            "advisory_only": True,
            "final_answer_authorized": False,
            "blockers": workspace["blockers"],
            "semantic_evaluation_performed": False,
        }
    source_map = {item.source_id: item for item in store.list_sources(run_id)}
    evidence_map = {item.evidence_id: item for item in store.list_evidence(run_id)}
    targets = []
    selected = set()
    for index, binding in enumerate(draft["claim_bindings"]):
        ids = binding["evidence_ids"]
        if any(item not in evidence_map for item in ids):
            raise ValueError("ADVISOR_EVIDENCE_NOT_FOUND")
        selected.update(ids)
        targets.append(
            SemanticVerifierTarget(
                target_id=f"claim-{index}",
                target_kind=SemanticVerificationTargetKind.CLAIM,
                proposition=binding["claim_text"],
                evidence_ids=ids,
                source_ids=sorted({evidence_map[item].source_id for item in ids}),
            )
        )
    if not targets:
        raise ValueError("ADVISOR_TARGET_REQUIRED")
    evidence = [evidence_map[item] for item in sorted(selected)]
    sources = [source_map[item] for item in sorted({span.source_id for span in evidence})]
    if any(
        source.expires_at <= datetime.now(UTC)
        or source.trust_status != TrustStatus.EVIDENCE_ELIGIBLE
        for source in sources
    ):
        raise ValueError("ADVISOR_SOURCE_NOT_ELIGIBLE")
    if any(not span.eligible_for_claim_support for span in evidence):
        raise ValueError("ADVISOR_EVIDENCE_NOT_ELIGIBLE")
    packet = [
        {
            "evidence_id": span.evidence_id,
            "source_id": span.source_id,
            "text": span.exact_text,
            "section_type": span.section_type.value,
        }
        for span in evidence
    ]
    # Screen the entire outbound packet, including quoted source material.
    from alr_tw.verification.output_privacy import screen_answer_output

    opaque_evidence, opaque_sources = _registered_law_digests(source_map, evidence_map)
    screened_packet = [dict(item) for item in packet]
    for item in screened_packet:
        if item["evidence_id"] in opaque_evidence:
            item["evidence_id"] = "registered-law-digest"
        if item["source_id"] in opaque_sources:
            item["source_id"] = "registered-law-digest"
    if not screen_answer_output(json.dumps(screened_packet, ensure_ascii=False)).allowed:
        raise ValueError("ADVISOR_PRIVACY_BLOCKED")
    request = SemanticVerifierRequest(
        request_id=f"advice-{uuid4().hex}",
        run_id=run_id,
        targets=targets,
        scope="Bounded draft revision advice; no final answer authorization",
    )
    result = execute_semantic_verifier(
        CommandSemanticVerifier(config, packet),
        request,
        server_run_id=run_id,
        server_targets=targets,
        server_sources=sources,
        server_evidence=evidence,
    )
    screened_result = result.model_dump(mode="json")
    # These envelope IDs are bound to the server request by the verifier.
    for key, expected in (("request_id", request.request_id), ("run_id", run_id)):
        if screened_result[key] == expected:
            screened_result[key] = "server-owned-reference"
    for finding in screened_result["findings"]:
        for key, registered in (("referenced_evidence_ids", opaque_evidence),
                                ("referenced_source_ids", opaque_sources)):
            finding[key] = ["registered-law-digest" if value in registered else value
                            for value in finding[key]]
    if not screen_answer_output(json.dumps(screened_result, ensure_ascii=False)).allowed:
        raise ValueError("ADVISOR_PRIVACY_BLOCKED")
    return {
        "advisory_only": True,
        "final_answer_authorized": False,
        "model_requested": config.model,
        "model_identity_independently_verified": False,
        "claim_mapping": {
            target.target_id: binding["claim_id"]
            for target, binding in zip(targets, draft["claim_bindings"])
        },
        "review": result.model_dump(mode="json"),
        "next_action": "依建議修正草稿與引用後，重新執行嚴格驗證；顧問結果不會自動放行。",
    }
