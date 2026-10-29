# Production Compose deployment

The production Compose stack serves the dashboard and API through one Caddy
origin. The API container and database are not published to the host.

## Local proxy setup

Copy `.env.prod.example` to `.env.prod`, replace the database password and
matching `DATABASE_URL` password with a unique value, then start the stack:

`PROXY_PORT` controls the host-side proxy port and defaults to `8080`; the
proxy still listens on `8080` inside its container. Set `WEB_ORIGINS` and
`FRONTEND_BASE_URL` to the browser origin using the same host port. For example,
with `PROXY_PORT=18080`, set both to `http://localhost:18080` and open
`http://localhost:18080/`. Keep `CADDY_SITE` on the container's port 8080.

```powershell
docker compose --env-file .env.prod -f docker-compose.prod.yml -p fleet-proxy up -d --build
```

The platform console and invitation page are available at `/platform.html` and
`/invite.html`. Caddy proxies API paths
directly without a prefix: `/admin/*`, `/platform/*`, `/invitations/*`,
`/location`, `/location/*`, `/status`, `/ws`, `/health`, and `/ready`.
Extensionless `/platform` and `/invite` paths and other unknown paths return
404. The production guard permits the exact localhost HTTP origin with a
warning.

The image build sets `VITE_API_BASE_URL` to an empty string, meaning the
dashboard uses same-origin API requests and derives its WebSocket URL from the
page origin. If the variable is undefined, local development retains the
`http://localhost:8000` API default. Admin and platform session cookies are
`Secure` in production. Open the dashboard on the PC at
`http://localhost:<PROXY_PORT>` (browsers treat `localhost` as secure) or over
HTTPS; do not rely on the localhost exception for LAN addresses or public HTTP.
Driver apps send the `x-token` header and are not affected by the cookie
restriction.

Set the mobile app backend base URL to `http://10.0.2.2:<PROXY_PORT>` on the
Android emulator, `http://<PC-LAN-IP>:<PROXY_PORT>` on a physical device, or
`https://<domain>` in production. Do not append `/api`.
The default Compose binding is loopback-only; for a physical device, change the
proxy's published host address to the PC's LAN interface and set `CADDY_SITE`
to `http://<PC-LAN-IP>:8080`. Restrict LAN access to a trusted network. On
Windows, if Docker cannot bind the selected host port, inspect reserved TCP
port ranges with:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

Choose another available `PROXY_PORT` if the selected port is excluded.

Check the proxy and API through the published origin. The examples below use
the default port; replace `8080` with `PROXY_PORT` when using a different host
port.

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
