# Security Policy

## Scope

This repository is a public reference framework that uses synthetic demo data only.

Please report security issues involving:

- accidental inclusion of credentials, tokens, private endpoints, logs, local paths, or production manifests
- bypasses in the forbidden file checker or CI release checks
- unsafe defaults in privacy masking, source trust policy, citation validation, or trust gates
- vulnerabilities in the demo MCP tools, examples, or validation scripts
- documentation that could cause users to expose production legal data, caches, or sensitive queries

## Supported Versions

Security review is focused on the current default branch and the latest tagged release, if any.
Older commits and experimental branches are not supported as stable release artifacts.

## Reporting a Vulnerability

Do not open a public issue for vulnerabilities, leaked secrets, private data, or sensitive legal facts.

Preferred reporting path:

1. Use GitHub's private vulnerability reporting or Security Advisories for this repository, if available.
2. If private reporting is not available, open a minimal public issue asking for a security contact, without including exploit details, secrets, private paths, or real case facts.

When reporting, include only the minimum safe details needed to reproduce the issue. Use synthetic examples whenever possible.

## Sensitive Data

Do not include any of the following in issues, pull requests, examples, screenshots, or reproduction files:

- production SQLite shards
- official full-text caches
- user query logs
- TLR or external service response caches
- Hugging Face verified full datasets
- Chroma or other vector database files
- private evaluation holdouts
- credentials, API keys, tokens, private endpoints, or local sensitive paths
- real personal data, real case facts, or confidential legal materials

## Release Checks

The full, repeatable audit procedure is defined in
[docs/RELEASE_AUDIT_PROCEDURE.md](docs/RELEASE_AUDIT_PROCEDURE.md). Before
publishing releases, changing visibility, or accepting data-related pull
requests, run at least:

```bash
git status --short --branch
git ls-files | sort
python scripts/check_no_forbidden_files.py
```

Recommended additional checks:

- GitHub secret scanning
- the CI history secret-scan job, currently backed by gitleaks
- trufflehog
- a tracked-file scan for database files, logs, archives, local paths, and generated caches
- a git-history review when changing repository visibility or importing large changes

The repository guard scripts also check common Taiwan legal-data leak shapes,
including real-shaped judgment identifiers outside the synthetic namespace and
Taiwan national ID number patterns.

A clean current working tree does not prove that older commits are safe to publish.

## Out Of Scope

The following are not handled as security vulnerabilities in this reference repository:

- requests for legal advice or legal correctness review
- availability or accuracy of third-party services such as TLR, Legal Detective, Dr.Lawbot, or government APIs
- risks introduced by a user's own production adapters, private datasets, model providers, or deployment environment
- disclosure of data that was never present in this repository

## No Bug Bounty

This project does not currently operate a paid bug bounty program.
