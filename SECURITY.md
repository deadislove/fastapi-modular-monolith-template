# Security Policy

## Supported versions

This is a template, not a versioned library — there are no release tags, only
`main`. Security fixes land on `main`; if you forked or scaffolded a project
from this template, you're responsible for pulling in fixes yourself. There's
no backport policy because there's nothing to backport to.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.** Email
**daweilin7689@gmail.com** (Da-Wei Lin) instead, with:

- What the vulnerability is and where in the codebase it lives.
- Steps to reproduce it, or a proof of concept if you have one.
- What you think the impact is (e.g., "authentication bypass," "SQL
  injection," "one module can read another module's data it shouldn't be
  able to").

This is a personal project, not a company with an SLA — expect an
acknowledgment within a few days, not a guaranteed response time. You'll be
credited in the fix's changelog/commit message unless you ask not to be.

## Scope

In scope: anything in `app/`, `alembic/`, `.github/workflows/`, or the
`Dockerfile`/`docker-compose.yml` that could let an attacker bypass
authentication, escalate privileges, read or write data they shouldn't have
access to, or compromise the CI pipeline.

Out of scope: vulnerabilities in third-party dependencies themselves (report
those upstream — `pip-audit`/`safety` against `requirements.txt` is a
reasonable way to check what's pinned) and anything that only reproduces on a
`.env` configured against the documented advice in
[`docs/quality-and-tooling.md`](docs/quality-and-tooling.md#production-readiness-guards)
— e.g. running with `APP_ENV=production` and the default `JWT_SECRET_KEY` is
already refused at startup (`app/shared/config.py`); running with it changed
to something equally guessable is a configuration problem, not a bug in this
template.

## A note on what's already handled by design, not by patching

A few things worth knowing before filing a report, since they're intentional
and documented, not oversights:

- **`JWT_SECRET_KEY` cannot be the shipped default when `APP_ENV=production`**
  — the process refuses to start. See
  [`docs/quality-and-tooling.md`](docs/quality-and-tooling.md#jwt_secret_key-cant-stay-the-default-in-production).
- **Rate limiting is per-process, in-memory** — this is a known, documented
  limitation for multi-worker deployments, not a silent gap. See the same
  doc's [rate limiter section](docs/quality-and-tooling.md#the-rate-limiter-doesnt-survive-more-than-one-process)
  before reporting it as a bypass.
- **Module boundaries are enforced by `.importlinter` and tested in CI** — a
  cross-module data leak that's only possible by directly importing a
  module's private `service.py`/`repository.py` isn't a runtime
  vulnerability; it's exactly what `.importlinter`'s contracts already block
  at commit time (see [`docs/architecture.md`](docs/architecture.md#enforcing-boundaries)).

If you've read the relevant doc and still think there's a real issue, please
do report it — the above is context, not a way to wave off a report.
