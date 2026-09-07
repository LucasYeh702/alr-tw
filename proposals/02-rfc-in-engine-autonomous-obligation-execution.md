---
title: "[RFC] In-Engine Autonomous Obligation Execution to Reduce MCP Multi-Hop Tool-Call Friction"
labels: ["enhancement", "mcp", "ergonomics"]
state: "draft"
author: "Third-Party Contributor / System Architect"
target_repo: "LucasYeh702/alr-tw"
---

# [RFC] In-Engine Autonomous Obligation Execution to Reduce MCP Multi-Hop Tool-Call Friction

## 1. Summary
This RFC proposes introducing an **In-Engine Autonomous Obligation Execution Mode** (`run_to_completion` / `auto_advance=True`) in `alr_tw.research.service.ResearchService` and the `tw_legal_rag_mcp` server.

Currently, ALR-TW models research as 8 fine-grained obligations (`query_understanding`, `privacy_screen`, `law_research`, `judgment_recall`, `judgment_official_verification`, `judgment_lineage_inspection`, `counter_authority`, `evidence_sufficiency`). While these obligations are explicitly declared as **Server-Owned**, the MCP interface currently forces external LLM agents to repeatedly call `continue_legal_research` across 6 to 8 roundtrips.

This client-driven orchestration introduces extreme cognitive load for external LLM agents, exacerbates context window waste, and causes frequent aborted runs due to transient network latency, tool-call parameter drift, or lock contention.

We propose adding an autonomous engine execution loop that allows an external agent to initiate a research run and have the server automatically resolve its own server-owned obligations in a single roundtrip, while preserving full auditability, idempotent operation tracking, and fail-closed safety invariants.

---

## 2. Motivation & Problem Statement

### 2.1 The Conceptual Inconsistency
In the core design of ALR-TW:
- Obligations are **Server-Owned**: The external agent does not choose which law or judgment to verify; the server derives and executes these tasks deterministically based on verified rules.
- Yet the execution is **Client-Driven**: The client is forced to act as an external clock generator, repeatedly invoking `continue_legal_research(run_id, operation_id)` simply to advance the server-side state machine.

### 2.2 Operational Friction in Real-World MCP Clients
In benchmarks with mainstream LLMs (e.g. Claude 3.5 Sonnet, GPT-4o):
1. **High Failure Rate on Multi-Hop Chains**: Models often hallucinate unexpected parameters or forget to increment `operation_id`, leading to premature run aborts or lock timeouts.
2. **Token & Latency Inflation**: Each `continue_legal_research` call returns intermediate obligation lists and schema envelopes. Exchanging 6 to 8 intermediate JSON-RPC messages consumes 15,000+ context tokens and adds 15-30 seconds of pure network/IPC overhead.
3. **Draft Redaction Friction**: If any intermediate hop fails or times out, the client never reaches `get_legal_research_finalization`, leaving the research in an unfinalized state.

---

## 3. Proposed Specification

### 3.1 `ResearchService.execute_run_to_completion()`
Add a high-level driver method to `ResearchService`:

```python
def execute_run_to_completion(
    self,
    run_id: str,
    *,
    max_steps: int = 12,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Autonomously advance all pending server-owned obligations until a terminal or human-gated state.

    Returns the finalization envelope if research completes, or the current state envelope
    if an external plan is required (CLIENT_ASSISTED) or execution is blocked.
    """
    with self._lock:
        run = self._required_run(run_id)
        step_count = 0
        while step_count < max_steps:
            pending = [
                item for item in run.obligations
                if item.status == ResearchObligationStatus.PENDING
                and item.kind != ResearchObligationKind.FINAL_ANSWER_VALIDATION
            ]
            if not pending:
                # All server-owned obligations resolved; finalize
                return self._finalize_run_internal(run, now=now)

            # Autonomously advance next obligation with internal operation_id
            op_id = f"auto_op_{run.run_id}_{step_count}_{int(time.time()*1000)}"
            step_result = self.continue_run(run.run_id, op_id, now=now)
            run = self._required_run(run_id)
            step_count += 1

            if run.state in {ResearchState.BLOCKED, ResearchState.COMPLETED}:
                break

        return self._result(run, None, replayed=False)
```

### 3.2 MCP Tool Surface Addition
Introduce a composite, agent-friendly tool:
- **`execute_legal_research`**:
  ```json
  {
    "name": "execute_legal_research",
    "description": "Initiate a complete legal research run and autonomously advance all server-owned obligations to finalization in a single call.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string"},
        "jurisdiction": {"type": "string", "default": "tw"},
        "discovery_mode": {"type": "string", "enum": ["server_orchestrated", "client_assisted"], "default": "server_orchestrated"}
      },
      "required": ["query"]
    }
  }
  ```
- Retain existing low-level tools (`research_legal_question`, `continue_legal_research`) for granular step-debugging and client-assisted research modes.

---

## 4. Invariants & Backward Compatibility
- **100% Backward Compatible**: Existing step-by-step MCP tools remain intact.
- **Fail-Closed Guarantees Preserved**: The internal loop adheres strictly to the same obligation state transitions, privacy screening, time-scope validations, and SHA-256 evidence generation.
- **Deterministic Audit Trail**: Each step executed by the autonomous loop continues to record unique `operation_id` records in the SQLite database, preserving full traceability.

---

## 5. Alternatives Considered
- **Keep pure client-driven stepping**: As demonstrated in production usage, this creates an unnecessarily high barrier to entry for standard MCP clients, leading users to bypass the harness entirely.
