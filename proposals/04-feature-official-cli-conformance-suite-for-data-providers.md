---
title: "[Feature] Provide Official CLI Conformance Test Suite for External Data Providers"
labels: ["enhancement", "tooling", "data-layer"]
state: "draft"
author: "Third-Party Contributor / System Architect"
target_repo: "LucasYeh702/alr-tw"
---

# [Feature] Provide Official CLI Conformance Test Suite for External Data Providers

## 1. Summary
This RFC proposes creating an official CLI command: **`alr-tw verify-provider`** (or `alr-tw check-conformance`).

In ALR-TW v0.11.0, the architecture officially opened the boundary for deployer-supplied data layers (via `ALR_TW_LOCAL_PORTAL_ROOT`, `ProviderSnapshotReceipt`, and pluggable local cache providers). However, the repository currently provides **no public automated tool or test suite** for third parties to audit whether their local judicial databases, FTS index shards, or graph tables conform to the expected ALR-TW contracts.

Adding an official conformance verification CLI will enable third-party law firms, enterprises, and open-source contributors to independently validate their local data assets against the harness's strict standards.

---

## 2. Motivation & Problem Statement

### 2.1 The Black-Box Integration Problem
When a third-party developer attempts to prepare a local database for ALR-TW:
1. They must read raw Python code to infer the expected table schemas (e.g. `judgment_registry`, `*_main-reasoning.sqlite`, `appellate_edges`).
2. Schema mismatches (e.g., missing columns, unindexed fields, unescaped WAL logs, or unnormalized JIDs) fail silently or produce obscure runtime tracebacks.
3. There is no official way to pre-verify `ProviderSnapshotReceipt` SHA-256 digests before starting an MCP service.

### 2.2 Preserving the Integrity of the Harness
If an external provider supplies corrupted or malformed data, it compromises the user's trust in ALR-TW. A formal conformance gate ensures that only structurally verified databases are recognized as `verified_cache`.

---

## 3. Proposed Specification

### 3.1 CLI Command Syntax
```bash
alr-tw verify-provider --path /path/to/judicial/data [options]
```

### 3.2 Audit Checklist & Conformance Matrix
The verification command runs 5 automated audit phases:

1. **Phase 1: Filesystem & Shard Topology**
   - Validates monthly shard naming convention (`YYYYMM_main-reasoning.sqlite`).
   - Verifies SQLite integrity (`PRAGMA integrity_check`).
   - Checks WAL status (fails closed if uncommitted WAL exists in read-only portable distributions).
2. **Phase 2: Full-Text Search (FTS) Conformance**
   - Validates existence and schema of FTS5 virtual tables (`fts_judgments` or `main_reasoning`).
   - Verifies query latency and tokenizer settings.
3. **Phase 3: JID Canonical Normalization**
   - Samples 1,000 random entries to ensure JID format conforms to `OfficialJudgmentProvider.normalize_jid()`.
   - Checks date format (`YYYYMMDD`) and court hierarchy prefixes.
4. **Phase 4: Snapshot Receipt & Hash Digest Validation**
   - Recalculates file SHA-256 digests and compares them against `manifest.json` or declared snapshot metadata.
5. **Phase 5: Graph Schema Verification (Optional)**
   - If `appellate_edges` table exists, verifies foreign keys, self-loop absence, and domain isolation.

### 3.3 Sample CLI Output
```text
$ alr-tw verify-provider --path /Volumes/Data/ALR-TW-handoff

=== ALR-TW Data Provider Conformance Audit ===
Target Path: /Volumes/Data/ALR-TW-handoff
Snapshot ID: ALR-TW-handoff-20260830

[✓] Phase 1: Shard Topology (413 shards verified, PRAGMA integrity OK)
[✓] Phase 2: FTS Index Conformance (FTS5 enabled, syntax query OK)
[✓] Phase 3: JID Normalization (1,000 samples conform to 6-part JID standard)
[✓] Phase 4: Snapshot Receipts (SHA-256 manifests match declared hashes)
[!] Phase 5: Appellate Graph (41,173 edges found, 0 self-loops, 0.3% domain warnings)

Result: CONFORMANCE PASSED (Grade: A)
Receipt Hash: 9b12101d33190fc6c253457a41285223...
Status: ELIGIBLE FOR ALR_TW_DATA_MODE=hybrid_verified
```

---

## 4. Safety & Invariant Analysis
- Purely read-only diagnostic command; does not mutate the target databases.
- Prevents deployment errors before the MCP server boots up.
- Empowers the open-source community to build diverse, compliant local datasets.
