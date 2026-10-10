# Backend Local Development

This setup is for local development only. Do not use the development database password or admin credentials in production.

## PostgreSQL credentials

- Database: `fleet_tracker`
- User: `fleet_tracker`
- Password: ` abc` (the password begins with one space)
- Host port: `5432`
- Database URL: `postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker`

The `%20` in the URL encodes the leading space in the password. Set `POSTGRES_PASSWORD` for PostgreSQL initialization and `DATABASE_URL` for the backend connection.

## Admin authentication settings

Admins log in with the email and password entered in the dashboard; successful login sets an eight-hour HTTP-only session cookie. `APP_ENV` accepts `development` or `production`; it defaults to `production` when unset or invalid and controls whether the session cookie uses the `Secure` flag.

Platform-owner login uses a separate four-hour HTTP-only `platform_session` cookie scoped to `/platform`; it cannot authenticate center-admin routes or the driver WebSocket.

## Start the backend on Windows PowerShell

From the repository root, activate the project venv, then change into `backend/`. Set `DATABASE_URL` to the PostgreSQL database where the center and admin should be created. The seed scripts support both module invocations from `backend/` and direct script invocations.

The backend also loads settings from `backend/.env` automatically; real environment variables take precedence. Start the backend from the repository root with `.\start-backend.ps1`. To use the checked-in placeholders as a starting point, copy `.env.example` to `backend\.env` and set local values there. Password spaces inside `DATABASE_URL` must be URL-encoded; for example, a leading space is `%20`.

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location .\backend
$env:POSTGRES_PASSWORD = " abc"
$env:DATABASE_URL = "postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker"
$env:APP_ENV = "development"
$env:WEB_ORIGINS = "http://localhost:5173"
docker compose up -d postgres
python -m scripts.seed_default_center
python -m scripts.seed_admin --email admin@example.com
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The admin seed checks whether the email already exists before prompting. If it does, it prints `Admin already exists; no changes made.` and exits without requesting a password. Otherwise it asks for the password twice using hidden input and requires 12 to 128 characters. It selects the only existing center. If there are zero or multiple centers, it stops with an error unless you provide `--center-id <UUID>`.

Create a platform-owner account from `backend/` with:

```powershell
python -m scripts.seed_super_admin --email owner@example.com
```

This hidden-prompt seed command is only for creating the first platform-owner super admin. It refuses to prompt if any super admin already exists; it is not a command for adding later owner accounts.

Deactivate an admin from `backend/` with:

```powershell
python -m scripts.deactivate_admin --email admin@example.com
```

Deactivation marks the admin inactive, records the UTC deactivation time, and revokes its non-revoked sessions in one transaction. It refuses to deactivate the last active admin of a center. Re-running it for an already inactive admin makes no changes. Both admin seed and deactivation commands leave existing rows in place.

Run the fake driver simulator from `backend/` with `python fake_driver.py`. It reads `FAKE_DRIVER_TOKEN` from the environment or prompts for the token using hidden input. Do not pass the token as a command-line argument.

The default-center seed creates a center only when none exists. `WEB_ORIGINS` is a comma-separated allowlist used by the API for the separate admin frontend; for the default local frontend, set it to `http://localhost:5173`.

Keep the backend command running in that terminal. The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). The independent web frontend is served separately from the repository's `frontend/` directory; follow the frontend instructions in the root README.

The platform console can expose the allowlisted local development tasks when `DEV_TASKS_ENABLED=true` and `APP_ENV=development`. This is disabled by default, is refused in production, and starts no backend process. Use it only for local development; see the frontend README for the available console tasks.

## Real-PostgreSQL integration tests

The `backend/tests_integration/` tests are not collected unless
`INTEGRATION_DB_ENABLED=true`; they are not skipped when the flag is off. From
the repository root, activate the project venv, make sure the existing
PostgreSQL container is running, and run:

```powershell
Set-Location C:\td\backend
$env:INTEGRATION_DB_ENABLED = "true"
$env:DEV_TASKS_ENABLED = "false"
pytest tests_integration
```

The fixture requires the configured PostgreSQL URL to target `fleet_tracker`,
uses its connection settings only for the hard-coded `fleet_integration_test`
database, and refuses to run if the expected single `postgres` container is
not running. It creates that database with `docker exec`, upgrades it to head,
tests the new migration's downgrade and re-upgrade on the fresh schema, and
drops only `fleet_integration_test` after the run. If that database already
exists, setup fails rather than deleting it. The integration flag must remain
off for the regular mocked suite.
