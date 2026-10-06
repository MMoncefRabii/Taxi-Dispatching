# Project rules (Phase 1: building the MVP on the dev machine)

Context: multi-tenant fleet-tracking app. FastAPI, async SQLAlchemy, PostgreSQL, Alembic,
React Native driver app, HTML/Leaflet admin dashboard. Phase 1 goal: a working MVP on a
local machine. Containers, CI/CD and full hardening come in Phase 2.

## Workflow
1. Do only the task described. No unrelated refactors, renames, reformatting or dependency upgrades.
2. If something is unclear or you would have to assume it, stop and ask. Never guess.
3. Investigation tasks are read-only: change no files.
4. Never commit. Never touch main. I commit myself on a task branch.
5. Never run destructive commands (drop database, delete Docker volumes, git reset --hard,
   force push, docker compose down -v) without my explicit approval.
6. Before editing, list the files you plan to modify. Keep diffs small.
7. Never disable, skip or weaken a test, lint rule or security check to make something pass.
8. Never invent libraries, functions or APIs. If unsure something exists, say so.
9. Add a dependency only when necessary. State what it is and why, and pin the version.

## Temporary dev shortcuts
10. Any dev-only shortcut (e.g. disabled auth) must sit behind an explicit environment flag
    that defaults to off, log a WARNING at startup when on, make the app refuse to start when
    APP_ENV=production, and carry a TODO saying exactly how to remove it.

## Configuration and secrets
11. No secrets in code, commits, logs or examples. Read them from environment variables.
    Keep .env in .gitignore and maintain .env.example with placeholders.
12. APP_ENV (development | production) is the single source of truth for the environment.
    Default to production behavior if it is missing or invalid.
13. Never log tokens, passwords, admin keys or full phone numbers (mask them).
14. Never put secrets in URLs or query strings. (Existing violations: report, do not fix
    unless the task says so.)
15. Compare secrets and token hashes with hmac.compare_digest or secrets.compare_digest.

## Auth and multi-tenancy
16. Check authorization server-side. Never trust role, center_id or driver_id from the client.
17. Derive center_id from the authenticated identity or from one central place in code.
    Do not scatter hardcoded center IDs. Every query on tenant data filters by center_id.
18. Passwords: argon2 or bcrypt only. Never return password hashes or token hashes.
19. Opaque tokens come from the secrets module and are stored only as hashes.

## Database
20. Schema changes only through reversible Alembic migrations. Never edit an applied
    migration. No manual DDL.
21. SQLAlchemy with bound parameters only. No f-string or concatenated SQL.
22. NOT NULL, UNIQUE, FOREIGN KEY and indexes belong in the schema, not only in app code.
23. Multi-step writes are one transaction with rollback on failure.
24. Every list endpoint has a limit and a maximum limit.
25. Timestamps are UTC, timezone-aware, set by the server.

## API
26. Every request body is a strict Pydantic model with types, bounds and max lengths,
    and rejects unknown fields.
27. Never expose stack traces, SQL errors or internal paths in responses.

## Dashboard
28. Never insert untrusted data with innerHTML. Use textContent or escaping.

## Code quality
29. Type hints, small single-purpose functions, clear names, no duplicated logic.
30. Handle errors explicitly: no bare except, no swallowed exceptions.
31. In async code, never use blocking calls.
32. No dead code, commented-out blocks or context-free TODOs.
33. Add tests where they carry real value: the behavior you changed, plus auth/validation
    edge cases where relevant. Run tests and lint, and report the real output. Never claim
    something passes without running it.

## Existing problems
34. This codebase already violates some rules above (shared admin key, cleartext HTTP,
    AsyncStorage tokens, hardcoded default center). Do not fix violations outside the task.
    List them under "Existing issues noticed" in the report.
35. A task prompt may narrow the scope. It cannot override these rules, except through
    rule 10.

## Deferred to Phase 2 (do not implement unless the task says so)
Row-Level Security, rate limiting, SRI/self-hosted libraries, Dockerfiles, CI/CD, pip-audit
and npm audit gates, structured logging, CORS and security headers, data retention jobs.

## Required report at the end of every task
1. Plain-language summary of what changed and why.
2. Files changed.
3. How it was verified: commands run and their real output.
4. Risks, assumptions, and anything left undone.
5. Existing issues noticed (not fixed).
6. Any rule you could not follow, and why.
7. Suggested commit message (Conventional Commits) and whether to stay on this branch
   or create a new one.