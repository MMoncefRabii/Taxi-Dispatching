# Backend Local Development

This setup is for local development only. Do not use the development database password or admin credentials in production.

## PostgreSQL credentials

- Database: `fleet_tracker`
- User: `fleet_tracker`
- Password: ` abc` (the password begins with one space)
- Host port: `5432`
- Database URL: `postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker`

The `%20` in the URL encodes the leading space in the password. Set `POSTGRES_PASSWORD` as well as `DATABASE_URL`: Compose uses the former when initializing PostgreSQL, while the backend uses the latter to connect.

## Admin authentication settings

Admins log in with the email and password entered in the dashboard; successful login sets an eight-hour HTTP-only session cookie. `APP_ENV` accepts `development` or `production`; it defaults to `production` when unset or invalid and controls whether the session cookie uses the `Secure` flag.

## Start the backend on Windows PowerShell

From the repository root, activate the project venv, then change into `backend/`. Set `DATABASE_URL` to the PostgreSQL database where the center and admin should be created. The seed scripts support both module invocations from `backend/` and direct script invocations.

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location .\backend
$env:POSTGRES_PASSWORD = " abc"
$env:DATABASE_URL = "postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker"
$env:APP_ENV = "development"
docker compose up -d postgres
python -m scripts.seed_default_center
python -m scripts.seed_admin --email admin@example.com
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The admin seed asks for the password twice using hidden input and requires 12 to 128 characters. It selects the only existing center. If there are zero or multiple centers, it stops with an error unless you provide `--center-id <UUID>`. The default-center seed creates a center only when none exists. Both seed commands are idempotent for already-existing data.

Keep the backend command running in that terminal. The dashboard is at [http://localhost:8000/](http://localhost:8000/) and the API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).
