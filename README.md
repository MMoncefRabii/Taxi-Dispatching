# Fleet Tracker

Fleet Tracker is a real-time GPS tracking system for taxi drivers and fleet operators in Tunisia, starting with a Grand Tunis pilot. Drivers use a React Native app to share location with a FastAPI service, and an admin dashboard displays driver status and recent positions. This repository is the tracking foundation for a future dispatch and ERP system: dispatching, ERP workflows, and machine-learning features are future phases and are not built yet.

## Architecture

```text
Driver mobile app (React Native / TypeScript) ──HTTP──┐
                                                      ├──> Backend (Python / FastAPI) ──> PostgreSQL
Admin web frontend (HTML / CSS / JavaScript) ─HTTP/WS─┘
```

These are separate applications. The web frontend and driver app call the backend API; changing their UI does not require changing backend code unless the API contract also changes. The web frontend is independently served from `frontend/`, and the backend does not serve frontend files.

## What's Working

### Backend API

The FastAPI service in `backend/main.py` implements:

| Route | Purpose |
| --- | --- |
| `POST /admin/login` | Authenticate an admin with email and password; sets an eight-hour session cookie. |
| `POST /admin/logout` | Revoke the current admin session and clear its cookie. |
| `GET /admin/me` | Return the authenticated admin's email and center ID. |
| `POST /admin/drivers` | Create a driver and vehicle using the authenticated admin session; returns the driver's token once. |
| `PATCH /admin/drivers/{driver_id}` | Edit a driver and/or vehicle within the authenticated admin's center. |
| `POST /admin/drivers/{driver_id}/deactivate` | Deactivate a driver and immediately invalidate its token. |
| `POST /admin/drivers/{driver_id}/reactivate` | Reactivate a driver and return a new one-time token. |
| `POST /admin/drivers/{driver_id}/token` | Replace the token for an active driver and return it once. |
| `GET /admin/drivers/latest` | Return center-scoped drivers, active state, vehicles, and latest known positions; requires an admin session. |
| `POST /status` | Set a driver's online flag; requires the driver's `x-token`. |
| `POST /location` | Validate and store one driver's location; requires `x-token`. Validation failures return a generic 422 reason; points sent too frequently return 429. |
| `POST /location/batch` | Submit 1–50 timestamped points; requires `x-token`. The body is limited to 64 KiB; the response reports accepted, duplicate, and rejected points. |
| `WS /ws` | Stream driver status and accepted location events to authenticated dashboard clients. |

Location validation uses server time, a 60-second future allowance, a 5-minute live age limit, a 6-hour batch age limit, a 2-second minimum interval, a 200 km/h speed limit, and a 50 m accuracy limit. These limits can be configured with the `LOCATION_*` variables in `.env.example`.

The interactive API documentation is available at `/docs` when the backend is running.

### Admin Dashboard

The standalone browser dashboard lives in `frontend/`. It uses HTML, CSS, vanilla JavaScript, Leaflet, and OpenStreetMap tiles to show drivers with known coordinates, a driver list, and online, stale, or offline indicators. A driver is considered online when their stored online flag is set and their latest location is no more than 60 seconds old; a driver without a location is shown as offline. Admins can create drivers with vehicles, edit details, deactivate/reactivate drivers, and regenerate active-driver tokens. Reactivation and regeneration tokens are shown once and must be given to the driver then. The dashboard receives WebSocket updates and refreshes the driver list periodically. Dashboard access uses per-admin email/password accounts and an eight-hour HTTP-only session cookie. Its API address is configured independently in `frontend/src/config.js`.

### Driver App

`DriverApp/` contains a React Native 0.87 TypeScript app with token entry, an online/offline switch, settings for the backend URL, and Android foreground-service location tracking. The app stores the driver token and a bounded offline location queue in AsyncStorage. While online and permitted, `react-native-geolocation-service` collects fixes on a 7-second interval and the app batches queued points to the backend. The Android foreground service is intended to keep tracking active while the app is backgrounded or the screen is locked; this behavior still requires real-device verification. The app shows queued and dropped/rejected counts, the last successful sync time, and textual sync errors. iOS background tracking is out of scope and untested.

**End-to-end status:** Real phone/emulator location has been confirmed appearing live on the admin dashboard.

## What's Not Built Yet

- No role-based permissions; admins are scoped to their center.
- No dispatching, order assignment, or ERP workflows.
- PostgreSQL is used for persistence; the included Compose service is for local development only.
- The project is not containerized and has no CI/CD pipeline or cloud deployment.
- Android background tracking and offline delivery require real-device verification; iOS background tracking is not implemented or tested.

## Tech Stack

- Backend: Python, FastAPI, Pydantic Settings, SQLAlchemy 2.0 async, Alembic, PostgreSQL.
- Web frontend: HTML, CSS, vanilla JavaScript, Leaflet 1.9.4, OpenStreetMap tiles.
- Android/iOS driver app: React Native 0.87, TypeScript, React Navigation, AsyncStorage, `react-native-geolocation-service`.
- Live updates: FastAPI WebSockets.

## Project Structure

```text
.
├── backend/                 Python API, database models/migrations, scripts, and tests
├── frontend/                Standalone admin web frontend (HTML, CSS, JavaScript)
│   ├── index.html
│   └── src/                 styles.css, app.js, and API URL config.js
├── DriverApp/               React Native mobile app (TypeScript)
│   ├── android/             Android native project
│   ├── ios/                 iOS native project
│   └── src/                 Mobile screens, API client, and location tracking
├── docs/                    Repository documentation
└── README.md
```

## Run Locally

The commands below use PowerShell on Windows. PostgreSQL runs through Docker Compose; the backend runs in your Python environment.

### 1. Start the backend

From the repository root, create and activate a virtual environment, then install backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
```

Start PostgreSQL from `backend/`, configure the backend environment, apply the schema, and seed the initial center:

```powershell
Set-Location .\backend
$env:POSTGRES_PASSWORD = " abc"
$env:DATABASE_URL = "postgresql+asyncpg://fleet_tracker:%20abc@localhost:5432/fleet_tracker"
$env:APP_ENV = "development"
$env:WEB_ORIGINS = "http://localhost:5173"
docker compose up -d postgres
alembic upgrade head
python -m scripts.seed_default_center
python -m scripts.seed_admin --email admin@example.com
```

See [backend/README.md](backend/README.md) for the local PostgreSQL credentials and explanation of the URL-encoded leading space in the password.

Start the API service:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). Keep the backend running in this terminal. PostgreSQL data persists in the Compose named volume.

### 2. Run the web frontend independently

In a separate PowerShell terminal, serve the static frontend:

```powershell
Set-Location .\frontend
python -m http.server 5173 --bind localhost
```

Open [http://localhost:5173/](http://localhost:5173/). The Python command above only serves static files; the dashboard itself runs in the browser and is not Python. It calls the backend at `http://localhost:8000`, as configured in `frontend/src/config.js`. If you change the frontend origin or API address, update the API URL and set `WEB_ORIGINS` for the backend to the exact frontend origin (comma-separated if there are multiple). The backend allows only configured web origins for credentialed HTTP requests and WebSocket connections. In production, keep the frontend and API on the same site: admin sessions use `SameSite=Strict` cookies.

### 3. Create a test driver

In the backend's `/docs`, use `POST /admin/login` with the seeded admin email and password, then open `POST /admin/drivers` and submit a JSON body such as:

```json
{
  "name": "Test Driver",
  "phone": "20000000",
  "vehicle": {
    "taxi_number": "TX-1",
    "plate_number": "AB 123",
    "type": "Sedan"
  }
}
```

Copy the returned `token` into the driver app.

### 4. Run the driver app on Android

In one terminal:

```powershell
Set-Location .\DriverApp
npm install
npm start
```

In another terminal, from `DriverApp/`:

```powershell
npm run android
```

On the Android emulator, the default backend URL `http://10.0.2.2:8000` reaches port 8000 on the host machine. On a physical device, set the backend URL in app Settings to the development computer's reachable LAN address. Grant location permission when prompted, paste the driver's token, then switch Online. The app requires the backend to be running and reachable before its status request can succeed.

## Roadmap

Upcoming phases include deployment foundations (containerization, CI/CD, and Kubernetes), security hardening, operational monitoring, and later ERP, big-data, and machine-learning work. These are planned work, not current capabilities. The project roadmap document has not been added to this repository yet.

## Status and License

Work-in-progress portfolio/client project. No license has been specified.

Technical decisions are documented in [DriverApp/docs/TECHNICAL_DECISIONS.md](DriverApp/docs/TECHNICAL_DECISIONS.md).
Current branch and remote relationships are recorded in [docs/GIT_BRANCH_MAP.md](docs/GIT_BRANCH_MAP.md).