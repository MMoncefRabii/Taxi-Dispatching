# Fleet Tracker Web Frontend

The standalone web frontend is a multi-page React, TypeScript, and Vite application. It is served separately from the FastAPI backend and the React Native driver app.

## Install

```powershell
Set-Location .\frontend
npm ci
```

## Run locally

Start the backend as described in the repository root README. In another PowerShell terminal:

```powershell
Set-Location .\frontend
npm run dev
```

Vite binds to `localhost:5173` and exits if that port is already occupied. Open <http://localhost:5173/> for the center dashboard. Add the exact frontend origin to the backend's comma-separated `WEB_ORIGINS` setting and restart the backend. Admin and platform sessions use HTTP-only `SameSite=Strict` cookies; in production, serve the frontend and API from the same site.

## Configuration

Copy `.env.example` to `.env` when a non-default API URL is needed:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

The default is `http://localhost:8000`. Vite exposes only variables prefixed with `VITE_`; do not put secrets in frontend environment variables.

## Pages

- `/` (`index.html`): center admin dashboard, ported in Part B.
- `/platform.html`: platform-owner console for center creation, center-admin invitations, audit log pagination, and development tasks when the API enables them.
- `/invite.html`: public invitation acceptance page. Enter the one-time token in the form; it is never read from the URL or stored in browser storage.

All pages are independent HTML entry points in Vite's multi-page build. Shared API, UI components, and stylesheet code are separated from the dashboard.

The three entry points are separate Vite bundles. The platform console imports shared UI/API code but does not import dashboard code. Invitation acceptance sends its request without browser credentials and clears its form fields after submission.

## Build and checks

```powershell
npm run lint
npx tsc --noEmit
npm test
npm run build
npm audit
```

## Reverse-proxy Content Security Policy

Set a production CSP at the reverse proxy and replace `https://api.example.com` with the API origin. OpenStreetMap tiles require the listed image origin. Leaflet updates map layout styles dynamically, hence the style directive permits inline styles; scripts remain self-hosted.

```text
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.tile.openstreetmap.org; font-src 'self'; connect-src 'self' https://api.example.com wss://api.example.com
```

## Platform owner setup

The platform console is at <http://localhost:5173/platform.html>. Bootstrap the first platform owner from `backend/` with `python -m scripts.seed_super_admin --email owner@example.com`; see the backend README for the hidden password prompts.

`FRONTEND_BASE_URL` in the backend defaults to `http://localhost:5173` and is used to construct `/invite.html` links. Keep it an HTTP(S) origin without a trailing slash.

## Development tasks

The platform console's Dev tasks section is available only when `GET /platform/dev/tasks` succeeds with HTTP 200. The task runner is disabled by default and refuses to start in production. It exposes only fixed, allowlisted local-development tasks and does not accept arbitrary commands. Audit events use limit/offset pagination.

The `frontend_serve` service runs this project's Vite dev server at <http://localhost:5173/>. Task output remains in memory only for the current backend process.
