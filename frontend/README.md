# Admin Web Frontend

The admin dashboard is a standalone static web app built with HTML, CSS, and vanilla JavaScript. It runs in the browser; Python is only used below as a local static file server. The frontend is separate from the Python backend and the React Native driver app.

## Run locally

Start the backend as described in the repository root README. In another PowerShell terminal:

```powershell
Set-Location .\frontend
python -m http.server 5173 --bind localhost
```

Open <http://localhost:5173/>. The API base URL is set in `src/config.js`; the default is `http://localhost:8000`. If the frontend is served from a different origin, add that exact origin to the backend's comma-separated `WEB_ORIGINS` setting and restart the backend. For production, serve the frontend and API from the same site because admin sessions use `SameSite=Strict` cookies.

## Files

- `index.html`: dashboard document and UI markup.
- `src/styles.css`: dashboard styling.
- `src/app.js`: browser behavior and HTTP/WebSocket API client.
- `src/config.js`: backend API base URL.
