# Admin Web Frontend

The admin dashboard is a standalone static web app built with HTML, CSS, and vanilla JavaScript. It runs in the browser; Python is only used below as a local static file server. The frontend is separate from the Python backend and the React Native driver app.

## Run locally

Start the backend as described in the repository root README. In another PowerShell terminal:

```powershell
Set-Location .\frontend
python -m http.server 5173 --bind localhost
```

Open <http://localhost:5173/>. The API base URL is set in `src/config.js`; the default is `http://localhost:8000`. If the frontend is served from a different origin, add that exact origin to the backend's comma-separated `WEB_ORIGINS` setting and restart the backend. For production, serve the frontend and API from the same site because admin and platform sessions use `SameSite=Strict` cookies.

The platform-owner console is available at <http://localhost:5173/platform.html>. It uses the same configured API base URL and credentialed, HTTP-only platform session cookie. Bootstrap the first platform owner from `backend/` with `python -m scripts.seed_super_admin --email owner@example.com`; see the backend README for the hidden password prompts.

## Development tasks in the platform console

The platform console's **Dev tasks** section is available only when the backend is started with `DEV_TASKS_ENABLED=true` and `APP_ENV=development`. The task runner is disabled by default and refuses to start in production. It exposes only the fixed, allowlisted local-development tasks shown in the console; it does not accept arbitrary commands. Run the console on the same machine as the backend, and sign in as a platform owner.

Use `start-backend.ps1` from the repository root to start the backend with the root `.venv` and load settings from `backend/.env`. Enable the task runner only for local development. The console can start the backend's PostgreSQL container, show running containers, inspect or upgrade the Alembic revision, run the backend test suite (optionally selecting a `tests/test_*.py` module), and start or stop the frontend static server.

Output is kept in memory for the current backend process and is discarded when it stops. The `frontend_serve` task serves this directory at <http://localhost:5173/>.

## Files

- `index.html`: dashboard document and UI markup.
- `src/styles.css`: dashboard styling.
- `src/app.js`: browser behavior and HTTP/WebSocket API client.
- `src/config.js`: backend API base URL.
- `platform.html`: platform-owner login and console document.
- `src/platform.css`: platform console styling.
- `src/platform.js`: platform console API client and UI behavior.
