# Backend Local Development

This setup is for local development only. Do not use the development database password or admin key in production.

## PostgreSQL credentials

- Database: `fleet_tracker`
- User: `fleet_tracker`
- Password: ` abc` (the password begins with one space)
- Host port: `5432`
- Database URL: `postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker`

The `%20` in the URL encodes the leading space in the password. Set `POSTGRES_PASSWORD` as well as `DATABASE_URL`: Compose uses the former when initializing PostgreSQL, while the backend uses the latter to connect.

## Admin authentication settings

`APP_ENV` accepts `development` or `production`; it defaults to `production` when unset or invalid. Admin key authentication remains enabled by default. For local dashboard testing only, set `APP_ENV=development` and `DEV_DISABLE_ADMIN_AUTH=true`. The backend logs a warning when this is enabled and refuses to start if it is enabled in production. Never enable this switch in a shared or production environment.

## Start the backend on Windows PowerShell

From the repository root:

```powershell
Set-Location .\backend
$env:POSTGRES_PASSWORD = " abc"
$env:DATABASE_URL = "postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker"
$env:ADMIN_KEY = "replace-with-a-private-development-key"
docker compose up -d postgres
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m scripts.seed_default_center
..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep the backend command running in that terminal. The dashboard is at [http://localhost:8000/](http://localhost:8000/) and the API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).
