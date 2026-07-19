# Security Policy

## Supported versions

Security review focuses on the default branch and latest public-preview release. `0.x` versions are not stable interfaces.

## Report privately

Do not publish vulnerabilities, secrets, private paths, real case facts, or personal data in an issue. Use GitHub private vulnerability reporting or a Security Advisory when available. Otherwise open a minimal issue asking for a private contact, without exploit details.

## v0.6 trust boundary

- MCP caller input is untrusted, including `source_tier`, URLs, hashes, timestamps, answer text, and identifiers.
- Caller-attested `official` or `verified_cache` metadata cannot establish final eligibility.
- Only server-fetched official snapshots or resolver-backed matching hashes may enter final evidence.
- TLR and other external recall results are candidate-only.
- Official HTTP uses HTTPS host allowlists, redirect validation, timeouts, response-size limits, and schema guards.
- Secrets are read from process configuration, redacted from diagnostics, and excluded from managed storage.
- Expired evidence, official content conflicts, ambiguous citations, role errors, and unsupported claims fail closed.
- A blocked validation response must not include the answer body.

## Sensitive data

Do not place production legal data, official full-text caches, user queries, TLR responses, SQLite or vector shards, private eval sets, API keys, screenshots containing case facts, or local sensitive paths in the repository.

`hybrid_verified` may transmit a privacy-screened query to TLR. The rule-based gate reduces risk but is not a confidentiality guarantee. Never send privileged, confidential, personal, or unpublished case material to an external provider.

## Operational requirements

- Keep `synthetic` as the implicit default; live modes require explicit selection.
- Use short-lived Judicial Yuan credentials and avoid shell history or committed env files.
- Limit retention, use `ephemeral` for sensitive-but-permitted local workflows, and purge after use.
- Treat official removal responses as deletion obligations.
- Review third-party dependency and service policy changes before release.
- Do not add browser automation that bypasses CAPTCHA or official access controls.

## Release checks

Run at least:

```bash
git status --short --branch
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run ruff check .
uv run mypy src
uv run pytest -q
uv build
```

Also review tracked files and Git history for secrets, databases, archives, logs, real-shaped identifiers, personal data, and generated caches. A clean worktree alone does not prove history is safe.

## Out of scope

Legal correctness questions, third-party service availability, and risks introduced by an operator's own private adapters or deployment are not vulnerabilities in this reference repository. Security defects that let those inputs cross the documented trust boundary are in scope.

This project has no paid bug bounty program.
