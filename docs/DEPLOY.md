# Production Compose deployment

The production Compose stack serves the dashboard and API through one Caddy
origin. The API container and database are not published to the host.

## Local proxy setup

Copy `.env.prod.example` to `.env.prod`, replace the database password and
matching `DATABASE_URL` password with a unique value, then start the stack:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml -p fleet-proxy up -d --build
```

Open `http://localhost:8080/`. The platform console and invitation page are
available at `/platform.html` and `/invite.html`. Caddy proxies API paths
directly without a prefix: `/admin/*`, `/platform/*`, `/invitations/*`,
`/location`, `/location/*`, `/status`, `/ws`, `/health`, and `/ready`.
Extensionless `/platform` and `/invite` paths and other unknown paths return
404. The production guard permits the exact localhost HTTP origin with a
warning.

The image build sets `VITE_API_BASE_URL` to an empty string, meaning the
dashboard uses same-origin API requests and derives its WebSocket URL from the
page origin. If the variable is undefined, local development retains the
`http://localhost:8000` API default. Production session cookies include
`Secure`; browsers treat `localhost` as an exception and allow Secure cookies
over HTTP there. Do not rely on that exception for LAN addresses or public HTTP.

Set the mobile app backend base URL to `http://10.0.2.2:8080` on the Android
emulator, `http://<PC-LAN-IP>:8080` on a physical device, or
`https://<domain>` in production. Do not append `/api`.
The default Compose binding is loopback-only; for a physical device, change the
proxy's published host address to the PC's LAN interface and set `CADDY_SITE`
to `http://<PC-LAN-IP>:8080`. Restrict LAN access to a trusted network.

Check the proxy and API through the published origin:

```powershell
curl.exe -i http://localhost:8080/health
curl.exe -i http://localhost:8080/ready
curl.exe -i http://localhost:8080/platform.html
curl.exe -i http://localhost:8080/invite.html
curl.exe -i http://localhost:8080/platform
curl.exe -i http://localhost:8080/invite
```

Remove this isolated project and its database volume when finished:

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml -p fleet-proxy down --volumes
```

## Public HTTPS deployment

Set `CADDY_SITE` to the actual HTTPS origin and set `WEB_ORIGINS` and
`FRONTEND_BASE_URL` to that same bare origin, without a path or trailing slash.
The example value `https://your-domain.example` is only a placeholder. Configure
DNS to point to the host, allow inbound ports 80 and 443, and replace the
localhost port mapping in `docker-compose.prod.yml` with the commented `80:80`
and `443:443` mappings. Caddy then obtains and renews the certificate
automatically. Do not publish the API or database ports.

The proxy adds `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`,
and a Content-Security-Policy-Report-Only policy. The policy allows self-hosted
scripts, same-origin WebSockets, OpenStreetMap tile images and data images.
Inline scripts are not present in the HTML entry points. HSTS is sent only for
HTTPS requests. The CSP remains report-only so violations can be reviewed
without breaking the initial deployment.

## Platform session cookie path

The backend sets the platform session cookie with `Path=/platform`. Direct
proxying of `/platform/*` preserves the cookie path, so browsers send the
platform session on authenticated platform API requests without rewriting
cookies or changing backend authentication behavior.
