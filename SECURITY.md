# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's **[Report a vulnerability](https://github.com/mos26613/SE-2026/security/advisories/new)** feature (Security tab → Advisories), or contact the maintainers directly.

Please include:

- A description of the issue and its impact.
- Steps to reproduce it.
- Any suggested fix, if you have one.

## Secrets

- Never commit passwords, API keys, connection strings or certificates.
- Use environment variables or a secret store (for example Azure Key Vault or GitHub Actions secrets).
- If a secret is committed by accident, treat it as leaked: **rotate it immediately**, then remove it from the history.
