# Fleet Tracker

Fleet Tracker is a real-time GPS tracking system for taxi drivers and fleet operators in Tunisia, starting with a Grand Tunis pilot. Drivers use a React Native app to share their foreground location with a FastAPI service, and an admin dashboard displays driver status and recent positions. This repository is the tracking foundation for a future dispatch and ERP system: dispatching, ERP workflows, and machine-learning features are future phases and are not built yet.

## Architecture

```text
+-------------------+       HTTP/JSON         +------------------+       persist/query       +-------------+
| Driver mobile app | ----------------------> | FastAPI backend  | ----------------------> |   SQLite    |
| React Native      |                         |                  |                          +-------------+
+-------------------+                         |                  |
                                              | WebSocket events |-------------------------------+
                                              +------------------+                               |
                                                                                                  v
                                                                                         +------------------+
                                                                                         | Admin dashboard  |
                                                                                         | Browser + Leaflet|
                                                                                         +------------------+
```

## What's Working

### Backend API

The FastAPI service in `backend/main.py` implements:

| Route | Purpose |
| --- | --- |
| `POST /admin/drivers` | Create a driver using the shared `x-admin-key`; returns the driver's token. |
| `GET /admin/drivers/latest` | Return drivers and their latest known position; requires `x-admin-key`. |
| `POST /status` | Set a driver's online flag; requires the driver's `x-token`. |
| `POST /location` | Validate and store a driver's location; requires `x-token`. Locations with accuracy over 50 m are ignored with `{"ok": false, "ignored": "low accuracy"}`. |
| `WS /ws?key=...` | Stream driver status and accepted location events to authorized dashboard clients. |

The interactive API documentation is available at `/docs` when the backend is running.

### Admin Dashboard

The browser dashboard is served from `backend/static/` at `/`. It uses Leaflet and OpenStreetMap tiles to show drivers with known coordinates, a driver list, and online, stale, or offline indicators. A driver is considered online when their stored online flag is set and their latest location is no more than 60 seconds old; a driver without a location is shown as offline. The dashboard receives WebSocket updates and refreshes the driver list periodically. Dashboard access uses the shared admin key.

### Driver App

`DriverApp/` contains a React Native 0.87 TypeScript app with token entry, an online/offline switch, settings for the backend URL, and foreground location tracking. The app stores the driver token locally and sends it in `x-token` headers. While online and permitted, it posts location updates through `react-native-geolocation-service` (watch interval 7 seconds, fastest interval 5 seconds) and displays the last accepted coordinates and send time. Location tracking stops when the driver goes offline or leaves the main screen; it does not run in the background.

**End-to-end status:** Real phone/emulator location has been confirmed appearing live on the admin dashboard.

## What's Not Built Yet

- No background location tracking; the driver app must remain foregrounded.
- No individual admin accounts or roles; the dashboard and admin API use one shared admin key.
- No dispatching, order assignment, or ERP workflows.
- SQLite is used for persistence; production PostgreSQL is not configured.
- The project is not containerized and has no CI/CD pipeline or cloud deployment.
- Automated backend/API/location-flow tests are not present. The mobile app currently has only a basic Jest render smoke test.

## Tech Stack

- Backend: Python, FastAPI, Pydantic, SQLite.
- Dashboard: vanilla JavaScript, Leaflet 1.9.4, OpenStreetMap tiles.
- Driver app: React Native 0.87, TypeScript, React Navigation, AsyncStorage, `react-native-geolocation-service`.
- Live updates: FastAPI WebSockets.

## Project Structure

```text
.
├── backend/                 FastAPI service, SQLite database, test-driver helper, dashboard assets
├── DriverApp/               React Native driver app, Android/iOS projects, and technical decisions
│   └── docs/
│       └── TECHNICAL_DECISIONS.md
├── docs/                    Repository-level contribution and branch documentation
│   └── GIT_BRANCH_MAP.md
└── README.md                Project overview and local setup
```

## Run Locally

The commands below use PowerShell on Windows. Python dependencies are installed directly because this repository does not currently include a backend requirements or project dependency file.

### 1. Start the backend

From the repository root, create and activate a virtual environment, then install the backend and test-helper dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi uvicorn requests
```

Start the service with a private admin key:

```powershell
$env:ADMIN_KEY = "replace-with-a-private-development-key"
Set-Location .\backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

The dashboard is served at [http://localhost:8000/](http://localhost:8000/) and the interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs). Keep the backend running in this terminal. SQLite data is stored in `backend/tracking.db`.

### 2. Create a test driver

In `/docs`, open `POST /admin/drivers`, provide `x-admin-key` using the exact value configured for the running backend, and submit a JSON body such as:

```json
{
  "name": "Test Driver",
  "phone": "20000000"
}
```

Copy the returned `token` into the driver app. The backend also includes `backend/get_test_token.py`, which creates a `TestDriver` using `ADMIN_KEY` from the helper process environment. If running it in a separate PowerShell terminal, set the same key in that terminal first.

### 3. Run the driver app on Android

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