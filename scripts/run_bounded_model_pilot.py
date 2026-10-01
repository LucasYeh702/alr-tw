"""Small model-in-the-loop synthetic research pilot; expert scores remain unreviewed."""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    ("S01", "請查示範責任法第7條，回答條文規定的責任，僅依查得資料。"),
    ("S02", "請查示範責任法第8條，回答管理機關的義務，僅依查得資料。"),
]
ARMS = ["direct", "standard", "quick"]
MODEL = "gpt-5.6-luna"
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "article": {"type": "string", "enum": ["7", "8"]},
        "answer_text": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    }, "required": ["article", "answer_text", "evidence_ids"],
}


def dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def unexpected_actions(events: list[dict]) -> list[dict]:
    unexpected = []
    for event in events:
        item = event.get("item")
        if item is None or item.get("type") in {"agent_message", "reasoning"}:
            continue
        # This CLI startup warning is not a model tool invocation or a failed API call.
        if item.get("type") == "error" and str(item.get("message", "")).startswith(
            "Skill descriptions were shortened to fit the 2% skills context budget."
        ):
            continue
        unexpected.append(event)
    return unexpected


def model_turn(prompt: str, directory: Path, phase: str) -> tuple[dict, dict]:
    schema = directory / "schema.json"
    dump(schema, SCHEMA)
    last = directory / f"{phase}-answer.json"
    started = perf_counter()
    result = subprocess.run(
        ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
         "--sandbox", "read-only", "--model", MODEL,
         "-c", 'model_reasoning_effort="low"', "--json", "--output-schema", str(schema),
         "--output-last-message", str(last), "--cd", str(directory), "-"],
        input=prompt, text=True, capture_output=True, timeout=180,
    )
    (directory / f"{phase}-events.jsonl").write_text(result.stdout)
    (directory / f"{phase}-stderr.txt").write_text(result.stderr)
    events = []
    for line in result.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    # Only final text/reasoning is allowed; research tools belong to this runner.
    unexpected = unexpected_actions(events)
    if result.returncode or not last.exists() or unexpected:
        raise RuntimeError(f"MODEL_PROTOCOL_FAILED:{phase}:exit={result.returncode}")
    payload = json.loads(last.read_text())
    if set(payload) != set(SCHEMA["required"]) or payload["article"] not in {"7", "8"}:
        raise ValueError("MODEL_SCHEMA_INVALID")
    usage = [e.get("usage") for e in events if e.get("type") == "turn.completed"]
    diagnostics = [e for e in events if e.get("item", {}).get("type") == "error"]
    return payload, {"elapsed_seconds": perf_counter() - started, "usage": usage,
                     "diagnostics": diagnostics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = runpy.run_path(str(ROOT / "tests/integration/test_v012_release_gates.py"))
    archive = fixture["_law_archive"]()
    fixture["_LawTransport"].get.__globals__["_law_archive"] = lambda: archive
    source_manifest = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for top in ("src", "scripts", "tests") for p in sorted((ROOT / top).rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    dump(output / "source-manifest.json", source_manifest)
    protocol = {
        "date": datetime.now(UTC).isoformat(), "model_alias": MODEL,
        "immutable_model_revision": None, "reasoning": "low", "tasks": TASKS, "arms": ARMS,
        "source_manifest_sha256": hashlib.sha256(
            (output / "source-manifest.json").read_bytes()).hexdigest(),
        "answer_max_characters": 200,
        "model_calls_per_run": 2, "research_calls_per_run": 1, "max_internal_steps": 12,
        "source_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "source_kind": "synthetic", "expert_status": "unreviewed",
        "quality_thresholds": None, "fees": "unavailable",
        "limitations": ["two synthetic tasks", "no live provider measurement",
                        "model alias is not immutable revision", "no expert accuracy scores",
                        "runner dispatches one model-selected lookup; no autonomous retry"],
    }
    dump(output / "protocol.json", protocol)
    rows = []
    for task_id, question in TASKS:
        # Rotate arm order to reduce always-first cache/order bias; no causal estimate from N=2.
        offset = len(rows) // len(ARMS)
        for arm in ARMS[offset:] + ARMS[:offset]:
            started = perf_counter()
            row = {"task_id": task_id, "arm": arm, "status": "started", "expert_status": "unreviewed"}
            directory = output / f"{task_id}-{arm}"
            directory.mkdir()
            try:
                instruction = (
                    "這是合成研究試測，不是真實法律意見。只輸出符合 schema 的 JSON，"
                    "不要呼叫任何 shell、web 或 MCP 工具。實驗工具由外部執行器代為呼叫。"
                )
                selected, first_usage = model_turn(
                    instruction + question + "\n請選擇查詢條號 article，answer_text 留空，evidence_ids 留空。",
                    directory, "select",
                )
                article = selected["article"]
                expected_article = "7" if task_id == "S01" else "8"
                row["selection_matches_task"] = article == expected_article
                row["task_outcome"] = "unreviewed" if article == expected_article else "selection_error"
                if selected["answer_text"] or selected["evidence_ids"]:
                    raise ValueError("PRE_RETRIEVAL_ANSWER_NOT_ALLOWED")
                session = fixture["_mcp_session"](directory / "state")
                query = f"示範責任法第{article}條"
                retrieval_started = perf_counter()
                if arm == "direct":
                    provider = fixture["OfficialLawProvider"](fixture["_LawTransport"](), verify_webpage=False)
                    _, source, evidence = asyncio.run(provider.exact_lookup("示範責任法", article))
                    assert source is not None and evidence is not None
                    packet = [{"evidence_id": evidence.evidence_id, "text": evidence.exact_text}]
                    run_id = None
                else:
                    result = fixture["_call"](session, "execute_legal_research", {
                        "query": query, "constraints": {"research_depth": arm,
                        "include_counter_authority": False}, "max_steps": 12,
                    })
                    run_id = result["run_id"]
                    packet = [{"evidence_id": e["evidence_id"], "text": e["exact_text"]}
                              for item in result.get("evidence_bundle", {}).get("items", [])
                              for e in item["evidence"]]
                    dump(directory / "research.json", result)
                row["retrieval_seconds"] = perf_counter() - retrieval_started
                dump(directory / "packet.json", packet)
                response, second_usage = model_turn(
                    instruction + question + "\n已查得資料：" + json.dumps(packet, ensure_ascii=False)
                    + "\n以簡短原文或忠實意譯回答，evidence_ids 填入直接支持答案的段落 ID。",
                    directory, "draft",
                )
                if len(response["answer_text"]) > 200 or response["article"] != article:
                    raise ValueError("MODEL_ANSWER_PROTOCOL_VIOLATION")
                row.update({"model_turns": [first_usage, second_usage], "answer": response})
                if arm != "direct":
                    validation = fixture["_call"](session, "validate_legal_answer", {
                        "run_id": run_id, "operation_id": "pilot-draft",
                        "answer_text": response["answer_text"], "claim_bindings": [{
                            "claim_id": "model-claim", "claim_text": response["answer_text"],
                            "claim_type": "law_rule", "evidence_ids": response["evidence_ids"],
                        }],
                    })
                    dump(directory / "validation.json", validation)
                    row["safe_to_present"] = validation["safe_to_present"]
                    row["decision"] = validation["decision"]
                else:
                    row["safe_to_present"] = None
                    row["decision"] = "not_gated_experimental_output"
                row["status"] = "collected"
            except Exception as exc:
                row["status"] = "failed"
                row["error_type"] = type(exc).__name__
                row["error"] = str(exc)
            row["elapsed_seconds"] = perf_counter() - started
            rows.append(row)
            dump(output / "runs.json", rows)
            print(task_id, arm, row["status"], flush=True)
    changed = [name for name, digest in source_manifest.items()
               if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    protocol["source_unchanged_at_end"] = not changed
    protocol["changed_source_paths"] = changed
    dump(output / "protocol.json", protocol)
    dump(output / "expert-review-template.json", [
        {"task_id": r["task_id"], "arm": r["arm"], "status": "unreviewed",
         "answer_sha256": hashlib.sha256(json.dumps(r.get("answer"), sort_keys=True).encode()).hexdigest(),
         "correct": None, "citation_supported": None, "useful": None, "review_seconds": None}
        for r in rows
    ])
    failed = sum(row["status"] != "collected" for row in rows)
    print(f"Pilot collection: {len(rows) - failed}/{len(rows)} collected; "
          "expert review remains unreviewed.")
    if failed or changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
