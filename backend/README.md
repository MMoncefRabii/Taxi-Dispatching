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

The default-center seed creates a center only when none exists. `WEB_ORIGINS` is a comma-separated allowlist used by the API for the separate admin frontend; for the default local frontend, set it to `http://localhost:5173`.

Keep the backend command running in that terminal. The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). The independent web frontend is served separately from the repository's `frontend/` directory; follow the frontend instructions in the root README.

The platform console can expose the allowlisted local development tasks when `DEV_TASKS_ENABLED=true` and `APP_ENV=development`. This is disabled by default, is refused in production, and starts no backend process. Use it only for local development; see the frontend README for the available console tasks.

## PostgreSQL backups and restore checks

The PowerShell scripts in `C:\td\scripts\backup` create PostgreSQL custom-format dumps from the `postgres` service in `backend\docker-compose.yml`. They run `pg_dump` and `pg_restore` inside the PostgreSQL container; no local PostgreSQL installation is needed. The scripts use the database user, database name, and password already set in the container environment. They do not print the password.

Run these commands from the repository root in Windows PowerShell:

```powershell
.\scripts\backup\backup-db.ps1
.\scripts\backup\restore-test.ps1
```

Backups default to `C:\td-backups`. To select another backup folder, pass `-BackupDir 'D:\fleet-backups'` to either script. Backup names are `fleet_YYYYMMDD_HHmmss.dump`; each dump has a neighboring `.sha256` checksum. The backup script checks that the dump is nonempty and readable by `pg_restore --list`. It retains the newest 14 dumps overall and the newest 8 dumps dated on Sundays. These sets are combined, so recent Sunday dumps may overlap. To preview retention deletions while creating a new verified backup, run:

```powershell
.\scripts\backup\backup-db.ps1 -WhatIf
```

`-WhatIf` previews only retention deletions; it still creates and verifies a backup. Retention only removes matching `fleet_*.dump` files and their corresponding `fleet_*.sha256` files from the selected backup folder. The script refuses to use a folder inside this Git repository.

To tolerate concurrent writes to `driver_locations` while the restore test runs, specify a nonnegative row-count tolerance. No other table has a tolerance:

```powershell
.\scripts\backup\restore-test.ps1 -DriverLocationsTolerance 5
```

The restore test defaults to the newest dump in `C:\td-backups`. It recreates only the hard-coded `fleet_restore_test` database, restores the dump there, compares row counts for `drivers`, `driver_locations`, `admins`, `centers`, and `vehicles`, then drops `fleet_restore_test`. Do not use that database for other data; it is intentionally disposable. This test never restores to the live database.

### Scheduling

Register a daily Windows Scheduled Task, defaulting to 02:00:

```powershell
.\scripts\backup\register-backup-task.ps1
```

Set another local time using `-Time HH:mm`, for example `-Time '03:30'`. The scheduled task is named `FleetBackup` and is configured to start when available if a scheduled run was missed while the PC was off. Remove it with:

```powershell
.\scripts\backup\register-backup-task.ps1 -Unregister
```

The task uses the registering user's interactive Windows session. It can run only when that user is logged in, the PC is on, Docker Desktop and the PostgreSQL container are running, and the user can access Docker.

### Manually restoring into a new database

Choose a new database name that does not already exist. The following example restores a selected dump into `fleet_manual_restore`, not the live `fleet_tracker` database. Run from the repository root:

```powershell
$container = (docker compose -f .\backend\docker-compose.yml ps -q postgres).Trim()
if (-not $container) { throw 'The postgres container is not running.' }
$dump = 'C:\td-backups\fleet_YYYYMMDD_HHmmss.dump'
docker cp $dump "${container}:/tmp/fleet_manual_restore.dump"
if ($LASTEXITCODE -ne 0) { throw 'Could not copy the dump into the container.' }
docker exec $container createdb -U fleet_tracker --owner=fleet_tracker fleet_manual_restore
if ($LASTEXITCODE -ne 0) { throw 'Could not create the new restore database.' }
docker exec $container pg_restore -U fleet_tracker --no-owner --no-privileges -d fleet_manual_restore /tmp/fleet_manual_restore.dump
if ($LASTEXITCODE -ne 0) { throw 'Restore into fleet_manual_restore failed.' }
docker exec $container rm -f /tmp/fleet_manual_restore.dump
```

Replace the example dump filename with an existing dump. This manual procedure assumes the container's configured user is `fleet_tracker`. Verify the new database before using it. Remove it only after confirming its contents are no longer needed.

### Warning: restoring over the live database

The scripts never restore over the live database. Restoring over `fleet_tracker` is a separate, manual and destructive operation; do not point the restore-test script at it. Before any deliberate live restore:

1. Stop the backend process (for example, press `Ctrl+C` in the terminal running Uvicorn).
2. While PostgreSQL is running, create a fresh backup and verify both its dump and checksum:

   ```powershell
   .\scripts\backup\backup-db.ps1
   $dump = (Get-ChildItem C:\td-backups\fleet_*.dump | Sort-Object Name -Descending | Select-Object -First 1).FullName
   if (-not $dump) { throw 'No backup dump was created.' }
   $expectedHash = (Get-Content "$dump.sha256").Split()[0]
   $actualHash = (Get-FileHash $dump -Algorithm SHA256).Hash.ToLowerInvariant()
   if ($actualHash -ne $expectedHash) { throw 'Backup checksum does not match.' }
   $container = (docker compose -f .\backend\docker-compose.yml ps -q postgres).Trim()
   if (-not $container) { throw 'The postgres container is not running.' }
   docker cp $dump "${container}:/tmp/fleet_fresh_before_live_restore.dump"
   if ($LASTEXITCODE -ne 0) { throw 'Could not copy the fresh backup into the container.' }
   docker exec $container pg_restore --list /tmp/fleet_fresh_before_live_restore.dump | Out-Null
   if ($LASTEXITCODE -ne 0) { throw 'The fresh backup is not readable.' }
   docker exec $container rm -f /tmp/fleet_fresh_before_live_restore.dump
   ```

3. Proceed only if the checksum matches and `pg_restore --list` succeeds. The backup script also performs the readability check before copying the dump out.
4. Only after verifying the recovery point and confirming the target is `fleet_tracker`, deliberately run the separately chosen live-restore procedure. This step can replace live data; the backup and restore-test scripts do not automate it.
5. Confirm the restored database before restarting the backend.

Backups stored on the same disk do not protect against disk failure. Keep an encrypted copy on a separate machine or other off-machine storage.
