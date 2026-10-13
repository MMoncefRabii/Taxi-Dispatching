import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type L from "leaflet";
import { apiRequest, apiUrl, ApiError } from "../api/client";
import type { Admin, Driver, FleetEvent } from "../api/types";
import { useFleetWebSocket } from "../api/websocket";
import { Badge, Button, ErrorBanner, Field, OneTimeSecretDialog } from "../components/ui";
import type { SecretEntry } from "../components/ui";
import { DriverEditor } from "./DriverEditor";
import { fitDrivers, MapView } from "./MapView";
import { filterDrivers, getDriverStatus } from "./model";

const ADMIN_PAGE_SIZE = 200;

function speedLabel(speedMps: number | null): string {
  return speedMps === null || Number.isNaN(Number(speedMps))
    ? "—"
    : `${(Number(speedMps) * 3.6).toFixed(1)} km/h`;
}

function lastSeenLabel(driver: Driver, nowMs: number): string {
  if (driver.recorded_at === null) return "never";
  const seconds = Math.max(0, Math.floor(nowMs / 1000 - driver.recorded_at));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}

function mapEventToDriver(event: FleetEvent, current: Driver | undefined): Driver {
  if (event.type === "location") {
    const driver: Driver = current ?? {
      id: event.driver_id,
      name: event.name ?? "",
      phone: "",
      active: true,
      online: 0,
      lat: null,
      lng: null,
      speed: null,
      heading: null,
      accuracy: null,
      recorded_at: null,
      vehicle: null,
    };
    return {
      ...driver,
      name: event.name || driver.name || "Unknown driver",
      lat: Number(event.lat),
      lng: Number(event.lng),
      speed: event.speed ?? driver.speed,
      heading: event.heading ?? driver.heading ?? 0,
      recorded_at: Number(event.recorded_at),
      online: driver.active ? 1 : 0,
    };
  }
  if (event.type === "status") {
    const driver = current ?? emptyDriver(event.driver_id);
    return { ...driver, online: driver.active && event.online ? 1 : 0 };
  }
  const driver = current ?? emptyDriver(event.driver_id);
  return {
    ...driver,
    active: Boolean(event.active),
    online: event.active && event.online ? 1 : 0,
  };
}

function emptyDriver(id: string): Driver {
  return {
    id,
    name: "Unknown driver",
    phone: "",
    active: true,
    online: 0,
    lat: null,
    lng: null,
    speed: null,
    heading: null,
    accuracy: null,
    recorded_at: null,
    vehicle: null,
  };
}

export function CenterDashboard() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [adminOffset, setAdminOffset] = useState(0);
  const [adminsHaveMore, setAdminsHaveMore] = useState(false);
  const [adminsError, setAdminsError] = useState("");
  const [dataError, setDataError] = useState("");
  const [view, setView] = useState<"drivers" | "admins">("drivers");
  const [search, setSearch] = useState("");
  const [driverFilter, setDriverFilter] = useState<"all" | "active" | "inactive">("all");
  const [selectedDriverId, setSelectedDriverId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorDriver, setEditorDriver] = useState<Driver | null>(null);
  const [secretOpen, setSecretOpen] = useState(false);
  const [secretTitle, setSecretTitle] = useState("");
  const [secretEntries, setSecretEntries] = useState<SecretEntry[]>([]);
  const [nowMs, setNowMs] = useState<number | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null);

  const handleUnauthorized = useCallback(() => {
    setAuthenticated(false);
    setDrivers([]);
    setAdmins([]);
    setLoginPassword("");
    setLoginError("Your admin session has expired. Please log in again.");
  }, []);

  const loadLatestDrivers = useCallback(async () => {
    try {
      const rows = await apiRequest<Driver[]>("/admin/drivers/latest");
      setDrivers(rows);
      setDataError("");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        handleUnauthorized();
        return;
      }
      setDataError(cause instanceof Error ? cause.message : "Unable to load drivers.");
      throw cause;
    }
  }, [handleUnauthorized]);

  const loadAdmins = useCallback(async (append: boolean) => {
    if (!append) {
      setAdmins([]);
      setAdminOffset(0);
      setAdminsHaveMore(false);
    }
    setAdminsError("");
    try {
      const url = apiUrl("/admin/admins");
      url.searchParams.set("limit", String(ADMIN_PAGE_SIZE));
      url.searchParams.set("offset", String(append ? adminOffset : 0));
      const rows = await apiRequest<Admin[]>(url.toString());
      setAdmins((current) => append ? [...current, ...rows] : rows);
      setAdminOffset((append ? adminOffset : 0) + rows.length);
      setAdminsHaveMore(rows.length === ADMIN_PAGE_SIZE);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        handleUnauthorized();
      } else {
        setAdminsError(cause instanceof Error ? cause.message : "Unable to load admins.");
      }
    }
  }, [adminOffset, handleUnauthorized]);

  useEffect(() => {
    let mounted = true;
    apiRequest<{ email: string }>("/admin/me")
      .then(async () => {
        if (!mounted) return;
        setAuthenticated(true);
        setCheckingSession(false);
        try {
          await loadLatestDrivers();
        } catch {
          return;
        }
      })
      .catch((cause: unknown) => {
        if (!mounted) return;
        if (cause instanceof ApiError && cause.status !== 401) {
          setLoginError(cause.message);
        }
        setAuthenticated(false);
        setCheckingSession(false);
      });
    return () => {
      mounted = false;
    };
  }, [loadLatestDrivers]);

  useEffect(() => {
    const firstTick = setTimeout(() => setNowMs(Date.now()), 0);
    const timer = setInterval(() => setNowMs(Date.now()), 5_000);
    return () => {
      clearTimeout(firstTick);
      clearInterval(timer);
    };
  }, []);

  const selectDriver = useCallback((driver: Driver) => {
    setSelectedDriverId(String(driver.id));
  }, []);

  const onMapReady = useCallback((map: L.Map) => {
    setMapInstance(map);
  }, []);

  const handleFleetEvent = useCallback((event: FleetEvent) => {
    setDrivers((current) => {
      const byId = new Map(current.map((driver) => [String(driver.id), driver]));
      const id = String(event.driver_id);
      byId.set(id, mapEventToDriver(event, byId.get(id)));
      return [...byId.values()];
    });
  }, []);

  const connected = useFleetWebSocket(authenticated, {
    onEvent: handleFleetEvent,
    onConnected: () => {
      void loadLatestDrivers().catch(() => undefined);
    },
    onDisconnected: () => undefined,
    onInvalidMessage: () => {
      setDataError("Received an invalid live update. Waiting for the next update.");
    },
  });

  const visibleDrivers = useMemo(
    () => filterDrivers(drivers, search, driverFilter, nowMs ?? 0),
    [drivers, driverFilter, nowMs, search],
  );
  const counts = useMemo(() => drivers.reduce(
    (result, driver) => {
      result[getDriverStatus(driver, nowMs ?? 0)] += 1;
      return result;
    },
    { online: 0, stale: 0, offline: 0 },
  ), [drivers, nowMs]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError("");
    try {
      await apiRequest("/admin/login", {
        method: "POST",
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      setLoginPassword("");
      setAuthenticated(true);
      try {
        await loadLatestDrivers();
      } catch {
        return;
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setLoginError("Invalid email or password.");
      } else {
        setLoginError(cause instanceof Error ? cause.message : "Unable to connect to the server.");
      }
    }
  }

  async function logout() {
    let failed = false;
    try {
      await apiRequest("/admin/logout", { method: "POST" });
    } catch (cause) {
      failed = true;
      setLoginError(cause instanceof Error ? cause.message : "Unable to confirm logout with the server.");
    }
    setAuthenticated(false);
    setDrivers([]);
    setAdmins([]);
    setAdminOffset(0);
    setAdminsHaveMore(false);
    setSelectedDriverId(null);
    setLoginPassword("");
    setView("drivers");
    if (!failed) setLoginError("");
  }

  async function saveDriver(name: string, token: string | null) {
    if (token) {
      setSecretTitle(`${name} — one-time driver token`);
      setSecretEntries([{ label: "Driver token", value: token, copyLabel: "token" }]);
      setSecretOpen(true);
    }
    try {
      await loadLatestDrivers();
    } catch {
      setDataError(
        token
          ? "The driver was saved, but the list could not be refreshed. Refresh the page to see the changes."
          : "The driver was saved, but the list could not be refreshed. Refresh the page.",
      );
    }
  }

  function showSecret(name: string, token: string) {
    setSecretTitle(`${name} — one-time driver token`);
    setSecretEntries([{ label: "Driver token", value: token, copyLabel: "token" }]);
    setSecretOpen(true);
  }

  async function driverAction(driver: Driver, action: "deactivate" | "reactivate" | "token") {
    if (action === "deactivate" && !window.confirm(
      `Deactivate ${driver.name}? The driver will be signed out immediately.`,
    )) return;
    if (action === "token" && !window.confirm(
      `Generate a new token for ${driver.name}? The old token will stop working immediately.`,
    )) return;

    try {
      const result = await apiRequest<{ token?: string }>(
        `/admin/drivers/${encodeURIComponent(driver.id)}/${action}`,
        { method: "POST" },
      );
      if (action !== "deactivate") {
        const token = typeof result?.token === "string" ? result.token : "";
        if (result && "token" in result) result.token = "";
        if (!token) {
          setDataError(
            action === "reactivate"
              ? "The driver was reactivated, but no token was returned. Contact support."
              : "No new token was returned. Contact support.",
          );
        } else {
          showSecret(driver.name || "Driver", token);
        }
      }
      await loadLatestDrivers();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        handleUnauthorized();
      } else {
        setDataError(cause instanceof Error ? cause.message : `Unable to ${action} the driver.`);
      }
    }
  }

  async function deactivateAdmin(admin: Admin) {
    if (!window.confirm(`Deactivate ${admin.email}?`)) return;
    setAdminsError("");
    try {
      await apiRequest(`/admin/admins/${encodeURIComponent(admin.id)}/deactivate`, {
        method: "POST",
      });
      await loadAdmins(false);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        handleUnauthorized();
      } else if (cause instanceof ApiError && cause.status === 409) {
        setAdminsError("This admin cannot be deactivated. The last active admin in a center must remain active.");
      } else if (cause instanceof ApiError && cause.status === 404) {
        setAdminsError("Admin not found in your center.");
      } else {
        setAdminsError(cause instanceof Error ? cause.message : "Unable to deactivate this admin.");
      }
    }
  }

  function openCreateDriver() {
    setEditorDriver(null);
    setEditorOpen(true);
  }

  function openEditDriver(driver: Driver) {
    setEditorDriver(driver);
    setEditorOpen(true);
  }

  function closeEditor() {
    setEditorOpen(false);
    setEditorDriver(null);
  }

  if (checkingSession || nowMs === null) {
    return <main className="session-check" aria-live="polite">Checking admin session…</main>;
  }

  return (
    <div id="app">
      {authenticated && (
        <>
          <MapView
            drivers={drivers}
            onSelect={selectDriver}
            onMapReady={onMapReady}
            selectedDriverId={selectedDriverId}
            nowMs={nowMs}
          />
          <header className="topbar">
            <div className="topbar-inner" aria-label="Driver status counts">
              <div className="counter online"><span className="dot" /><strong>{counts.online}</strong><span>Online</span></div>
              <div className="counter stale"><span className="dot" /><strong>{counts.stale}</strong><span>Stale</span></div>
              <div className="counter offline"><span className="dot" /><strong>{counts.offline}</strong><span>Offline</span></div>
              <div className="live-indicator" role="status">
                <span className={`live-dot ${connected ? "live" : "reconnect"}`} />
                {connected ? "Live" : "Reconnecting"}
              </div>
            </div>
          </header>
          <aside className={`sidebar${sidebarCollapsed ? " collapsed" : ""}`}>
            <div className="sidebar-header">
              <strong>Fleet</strong>
              <div className="sidebar-header-actions">
                <Button
                  type="button"
                  variant="secondary"
                  className="sidebar-toggle"
                  aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                  onClick={() => setSidebarCollapsed((current) => !current)}
                >
                  ☰
                </Button>
                <Button type="button" variant="secondary" onClick={() => void logout()}>Log out</Button>
              </div>
            </div>
            <nav className="view-tabs" aria-label="Dashboard views">
              <Button
                type="button"
                variant="secondary"
                className={`view-tab${view === "drivers" ? " selected" : ""}`}
                aria-selected={view === "drivers"}
                onClick={() => setView("drivers")}
              >
                Drivers
              </Button>
              <Button
                type="button"
                variant="secondary"
                className={`view-tab${view === "admins" ? " selected" : ""}`}
                aria-selected={view === "admins"}
                onClick={() => {
                  setView("admins");
                  void loadAdmins(false);
                }}
              >
                Admins
              </Button>
            </nav>
            {view === "drivers" ? (
              <section id="driversView">
                <div className="toolbar">
                  <div className="search-wrap">
                    <label className="sr-only" htmlFor="driver-search">Search driver</label>
                    <input
                      id="driver-search"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search driver"
                    />
                  </div>
                  <label className="sr-only" htmlFor="driver-filter">Filter drivers</label>
                  <select
                    id="driver-filter"
                    value={driverFilter}
                    onChange={(event) => setDriverFilter(event.target.value as typeof driverFilter)}
                  >
                    <option value="all">All</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                  <Button type="button" onClick={openCreateDriver}>New driver</Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      if (mapInstance) fitDrivers(mapInstance, drivers);
                    }}
                  >
                    Fit all
                  </Button>
                </div>
                <ErrorBanner>{dataError}</ErrorBanner>
                <div className="list" aria-label="Drivers">
                  {visibleDrivers.length === 0
                    ? <div className="driver-empty">No drivers found.</div>
                    : visibleDrivers.map((driver) => {
                        const status = getDriverStatus(driver, nowMs);
                        const active = selectedDriverId === String(driver.id);
                        return (
                          <article
                            className={`driver-item${active ? " active" : ""}${driver.active ? "" : " inactive"}`}
                            key={driver.id}
                          >
                            <button
                              className="driver-select"
                              type="button"
                              onClick={() => {
                                selectDriver(driver);
                              }}
                            >
                              <span className={`driver-dot status-${status}`} />
                              <span className="driver-main">
                                <span className="driver-name">{driver.name || "Unknown driver"}</span>
                                <span className="driver-meta">
                                  <span>{driver.phone || "—"}</span>
                                  <Badge tone={status}>{status}</Badge>
                                  {!driver.active && <Badge tone="inactive">Inactive</Badge>}
                                </span>
                                <span className="driver-vehicle">
                                  {[driver.vehicle?.plate_number, driver.vehicle?.type]
                                    .filter(Boolean)
                                    .join(" · ") || "No vehicle"}
                                </span>
                              </span>
                              <span className="driver-speed">
                                {speedLabel(driver.speed)}<br />{lastSeenLabel(driver, nowMs)}
                              </span>
                            </button>
                            <div className="driver-actions">
                              <Button type="button" variant="secondary" onClick={() => openEditDriver(driver)}>Edit</Button>
                              {driver.active ? (
                                <>
                                  <Button
                                    type="button"
                                    variant="danger"
                                    onClick={() => void driverAction(driver, "deactivate")}
                                  >
                                    Deactivate
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="secondary"
                                    onClick={() => void driverAction(driver, "token")}
                                  >
                                    New token
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  type="button"
                                  variant="secondary"
                                  onClick={() => void driverAction(driver, "reactivate")}
                                >
                                  Reactivate
                                </Button>
                              )}
                            </div>
                          </article>
                        );
                      })}
                </div>
              </section>
            ) : (
              <section className="admins-view" aria-label="Center admins">
                <ErrorBanner>{adminsError}</ErrorBanner>
                <div className="admin-list">
                  {admins.length === 0
                    ? <p className="admin-empty">No admins found.</p>
                    : admins.map((admin) => (
                        <article className="admin-item" key={admin.id}>
                          <div className="admin-details">
                            <strong className="admin-email">{admin.email}</strong>
                            <div className="admin-badges">
                              <Badge tone={admin.active ? "active" : "inactive"}>
                                {admin.active ? "Active" : "Inactive"}
                              </Badge>
                              {admin.is_self && <Badge tone="self">You</Badge>}
                            </div>
                            <span className="admin-meta">
                              {admin.created_at && `Created ${new Date(admin.created_at).toLocaleDateString()}`}
                            </span>
                          </div>
                          {admin.active && !admin.is_self && (
                            <Button
                              type="button"
                              variant="danger"
                              onClick={() => void deactivateAdmin(admin)}
                            >
                              Deactivate
                            </Button>
                          )}
                        </article>
                      ))}
                </div>
                {adminsHaveMore && (
                  <Button
                    id="loadMoreAdminsBtn"
                    type="button"
                    variant="secondary"
                    onClick={() => void loadAdmins(true)}
                  >
                    Load more admins
                  </Button>
                )}
              </section>
            )}
          </aside>
          <DriverEditor
            key={`${editorDriver?.id ?? "create"}-${editorOpen ? "open" : "closed"}`}
            open={editorOpen}
            driver={editorDriver}
            onClose={closeEditor}
            onSaved={saveDriver}
          />
          <OneTimeSecretDialog
            open={secretOpen}
            title={secretTitle}
            warning="This token is shown only once. Give it to the driver now."
            entries={secretEntries}
            onClose={() => {
              setSecretEntries([]);
              setSecretOpen(false);
            }}
          />
        </>
      )}
      {!authenticated && (
        <div className="login-overlay">
          <form className="login-box" onSubmit={(event) => void submitLogin(event)}>
            <h2>Fleet Tracker</h2>
            <Field
              id="adminEmailInput"
              label="Email"
              type="email"
              name="email"
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
              maxLength={255}
              autoComplete="username"
              required
            />
            <Field
              id="adminPasswordInput"
              label="Password"
              type="password"
              name="password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              maxLength={128}
              autoComplete="current-password"
              required
            />
            <ErrorBanner>{loginError}</ErrorBanner>
            <Button type="submit" disabled={checkingSession}>Log in</Button>
          </form>
        </div>
      )}
    </div>
  );
}
