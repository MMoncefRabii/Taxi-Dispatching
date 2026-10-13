import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, apiRequest } from "../api/client";
import {
  Badge,
  Button,
  ErrorBanner,
  Field,
  OneTimeSecretDialog,
  Table,
  type SecretEntry,
} from "../components/ui";

interface PlatformIdentity {
  email: string;
}

interface Center {
  id: string;
  name: string;
  city: string;
  timezone: string;
  active: boolean;
  created_at: string;
  driver_count: number;
  admin_count: number;
}

interface Invitation {
  id: string;
  email: string;
  created_at: string;
  expires_at: string;
  status: "pending" | "used" | "expired" | "revoked";
}

interface CreatedInvitation {
  invitation_id: string;
  email: string;
  expires_at: string;
  link: string;
  token: string;
}

interface AuditEvent {
  id: string;
  super_admin_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  ip: string | null;
  user_agent: string | null;
  success: boolean;
  created_at: string;
}

interface TaskParameter {
  name: string;
  description: string;
  pattern: string;
}

interface DevTask {
  id: string;
  label: string;
  description: string;
  kind: "oneshot" | "service";
  parameters: TaskParameter[];
}

interface DevRun {
  id: string;
  task_id: string;
  kind: "oneshot" | "service";
  status: "running" | "ok" | "failed" | "timeout";
  service_state: string | null;
  duration_seconds: number | null;
  output_line_count: number;
  offset: number;
  lines: string[];
}

interface RunOutput {
  run_id: string;
  offset: number;
  lines: string[];
  status: DevRun["status"];
  service_state: string | null;
  duration_seconds: number | null;
}

const AUDIT_LIMIT = 25;

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}

function displayDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function PlatformConsole() {
  const [checkingSession, setCheckingSession] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [platformEmail, setPlatformEmail] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [pageError, setPageError] = useState("");

  const [centers, setCenters] = useState<Center[]>([]);
  const [centersError, setCentersError] = useState("");
  const [centerName, setCenterName] = useState("");
  const [centerCity, setCenterCity] = useState("");
  const [centerTimezone, setCenterTimezone] = useState("");
  const [creatingCenter, setCreatingCenter] = useState(false);

  const [selectedCenterId, setSelectedCenterId] = useState<string | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [invitationEmail, setInvitationEmail] = useState("");
  const [invitationError, setInvitationError] = useState("");
  const [invitationLoading, setInvitationLoading] = useState(false);

  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditError, setAuditError] = useState("");
  const [auditLoading, setAuditLoading] = useState(false);

  const [devToolsEnabled, setDevToolsEnabled] = useState(false);
  const [devTasks, setDevTasks] = useState<DevTask[]>([]);
  const [devTasksError, setDevTasksError] = useState("");
  const [runs, setRuns] = useState<DevRun[]>([]);
  const [taskFileValues, setTaskFileValues] = useState<Record<string, string>>({});

  const [secretOpen, setSecretOpen] = useState(false);
  const [secretTitle, setSecretTitle] = useState("");
  const [secretEntries, setSecretEntries] = useState<SecretEntry[]>([]);

  const handleUnauthorized = useCallback(() => {
    setAuthenticated(false);
    setPlatformEmail("");
    setLoginError("Your platform session has expired. Please log in again.");
  }, []);

  const loadCenters = useCallback(async () => {
    setCentersError("");
    try {
      setCenters(await apiRequest<Center[]>("/platform/centers?limit=200&offset=0"));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setCentersError(errorMessage(cause, "Unable to load centers."));
    }
  }, [handleUnauthorized]);

  const loadAuditPage = useCallback(async (offset: number) => {
    setAuditLoading(true);
    setAuditError("");
    try {
      const events = await apiRequest<AuditEvent[]>(
        `/platform/audit?limit=${AUDIT_LIMIT}&offset=${offset}`,
      );
      setAuditEvents(events);
      setAuditOffset(offset);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setAuditError(errorMessage(cause, "Unable to load the audit log."));
    } finally {
      setAuditLoading(false);
    }
  }, [handleUnauthorized]);

  const loadDevTasks = useCallback(async () => {
    setDevTasksError("");
    try {
      const tasks = await apiRequest<DevTask[]>("/platform/dev/tasks");
      setDevTasks(tasks);
      setDevToolsEnabled(true);
      try {
        const result = await apiRequest<{ runs: Omit<DevRun, "offset" | "lines">[] }>(
          "/platform/dev/runs?limit=20",
        );
        setRuns(result.runs.map((run) => ({ ...run, offset: 0, lines: [] })));
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
        else setDevTasksError(errorMessage(cause, "Unable to load development task runs."));
      }
    } catch (cause) {
      setDevToolsEnabled(false);
      setDevTasks([]);
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setDevTasksError(errorMessage(cause, "Development tasks are unavailable."));
    }
  }, [handleUnauthorized]);

  const loadInvitations = useCallback(async (centerId: string) => {
    setInvitationLoading(true);
    setInvitationError("");
    try {
      setInvitations(
        await apiRequest<Invitation[]>(
          `/platform/centers/${encodeURIComponent(centerId)}/invitations?limit=200&offset=0`,
        ),
      );
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setInvitationError(errorMessage(cause, "Unable to load invitations."));
    } finally {
      setInvitationLoading(false);
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    let cancelled = false;
    async function checkSession() {
      try {
        const identity = await apiRequest<PlatformIdentity>("/platform/me");
        if (cancelled) return;
        setPlatformEmail(identity.email);
        setAuthenticated(true);
        await Promise.all([loadCenters(), loadAuditPage(0), loadDevTasks()]);
      } catch (cause) {
        if (!cancelled && !(cause instanceof ApiError && cause.status === 401)) {
          setLoginError(errorMessage(cause, "Unable to check the platform session."));
        }
      } finally {
        if (!cancelled) setCheckingSession(false);
      }
    }
    void checkSession();
    return () => {
      cancelled = true;
    };
  }, [loadAuditPage, loadCenters, loadDevTasks]);

  useEffect(() => {
    const activeRuns = runs.filter((run) => run.status === "running");
    if (!devToolsEnabled || activeRuns.length === 0) return;

    const timer = window.setInterval(() => {
      for (const run of activeRuns) {
        void apiRequest<RunOutput>(
          `/platform/dev/runs/${encodeURIComponent(run.id)}?offset=${run.offset}`,
        ).then((output) => {
          setRuns((current) =>
            current.map((item) =>
              item.id === output.run_id
                ? {
                    ...item,
                    offset: output.offset,
                    lines: [...item.lines, ...output.lines],
                    status: output.status,
                    service_state: output.service_state,
                    duration_seconds: output.duration_seconds,
                    output_line_count: Math.max(item.output_line_count, output.offset),
                  }
                : item,
            ),
          );
        }).catch((cause: unknown) => {
          if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
          else setDevTasksError(errorMessage(cause, "Unable to poll development task output."));
        });
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [devToolsEnabled, handleUnauthorized, runs]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginError("");
    try {
      await apiRequest<{ ok: boolean }>("/platform/login", {
        method: "POST",
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const identity = await apiRequest<PlatformIdentity>("/platform/me");
      setPlatformEmail(identity.email);
      setAuthenticated(true);
      setLoginEmail("");
      setLoginPassword("");
      setPageError("");
      await Promise.all([loadCenters(), loadAuditPage(0), loadDevTasks()]);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setLoginError("Invalid email or password.");
      } else {
        setLoginError(errorMessage(cause, "Unable to log in to the platform console."));
      }
    }
  }

  async function logout() {
    try {
      await apiRequest<void>("/platform/logout", { method: "POST" });
      setAuthenticated(false);
      setPlatformEmail("");
      setPageError("");
      setCenters([]);
      setInvitations([]);
      setRuns([]);
      setDevToolsEnabled(false);
      setLoginError("");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setPageError(errorMessage(cause, "Unable to log out."));
    }
  }

  async function submitCenter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingCenter(true);
    setCentersError("");
    try {
      await apiRequest<Center>("/platform/centers", {
        method: "POST",
        body: JSON.stringify({
          name: centerName,
          city: centerCity,
          timezone: centerTimezone,
        }),
      });
      setCenterName("");
      setCenterCity("");
      setCenterTimezone("");
      await loadCenters();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setCentersError(errorMessage(cause, "Unable to create the center."));
    } finally {
      setCreatingCenter(false);
    }
  }

  async function selectCenter(centerId: string) {
    if (selectedCenterId === centerId) {
      setSelectedCenterId(null);
      setInvitations([]);
      setInvitationError("");
      return;
    }
    setSelectedCenterId(centerId);
    setInvitations([]);
    setInvitationEmail("");
    await loadInvitations(centerId);
  }

  async function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCenterId) return;
    setInvitationError("");
    try {
      const created = await apiRequest<CreatedInvitation>(
        `/platform/centers/${encodeURIComponent(selectedCenterId)}/invitations`,
        {
          method: "POST",
          body: JSON.stringify({ email: invitationEmail }),
        },
      );
      setInvitationEmail("");
      setSecretTitle(`Invitation for ${created.email}`);
      setSecretEntries([
        { label: "Invitation link", value: created.link, copyLabel: "link" },
        { label: "Invitation token", value: created.token, copyLabel: "token" },
      ]);
      setSecretOpen(true);
      await loadInvitations(selectedCenterId);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setInvitationError(errorMessage(cause, "Unable to create the invitation."));
    }
  }

  async function revokeInvitation(invitation: Invitation) {
    if (!window.confirm(`Revoke the invitation for ${invitation.email}?`)) return;
    setInvitationError("");
    try {
      await apiRequest<{ ok: boolean }>(
        `/platform/invitations/${encodeURIComponent(invitation.id)}/revoke`,
        { method: "POST" },
      );
      if (selectedCenterId) await loadInvitations(selectedCenterId);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setInvitationError(errorMessage(cause, "Unable to revoke the invitation."));
    }
  }

  async function startTask(task: DevTask) {
    setDevTasksError("");
    const testFile = taskFileValues[task.id]?.trim();
    try {
      const run = await apiRequest<Omit<DevRun, "offset" | "lines">>(
        `/platform/dev/tasks/${encodeURIComponent(task.id)}/run`,
        {
          method: "POST",
          body: JSON.stringify(testFile ? { test_file: testFile } : {}),
        },
      );
      setRuns((current) => [
        { ...run, offset: 0, lines: [] },
        ...current.filter((item) => item.id !== run.id),
      ]);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setDevTasksError(errorMessage(cause, `Unable to start ${task.label}.`));
    }
  }

  async function stopRun(run: DevRun) {
    setDevTasksError("");
    try {
      const updated = await apiRequest<Omit<DevRun, "offset" | "lines">>(
        `/platform/dev/runs/${encodeURIComponent(run.id)}/stop`,
        { method: "POST" },
      );
      setRuns((current) =>
        current.map((item) =>
          item.id === run.id
            ? { ...item, ...updated, offset: item.offset, lines: item.lines }
            : item,
        ),
      );
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) handleUnauthorized();
      else setDevTasksError(errorMessage(cause, "Unable to stop the development task."));
    }
  }

  if (checkingSession) {
    return <main className="session-check" aria-live="polite">Checking platform session…</main>;
  }

  if (!authenticated) {
    return (
      <main className="login-view">
        <form className="login-card" onSubmit={(event) => void submitLogin(event)}>
          <p className="eyebrow">Fleet Tracker · Platform owner</p>
          <h1>Platform console</h1>
          <Field
            id="platform-email"
            label="Email"
            name="email"
            type="email"
            value={loginEmail}
            onChange={(event) => setLoginEmail(event.target.value)}
            maxLength={255}
            autoComplete="username"
            required
          />
          <Field
            id="platform-password"
            label="Password"
            name="password"
            type="password"
            value={loginPassword}
            onChange={(event) => setLoginPassword(event.target.value)}
            maxLength={128}
            autoComplete="current-password"
            required
          />
          <ErrorBanner>{loginError}</ErrorBanner>
          <Button type="submit">Log in</Button>
        </form>
      </main>
    );
  }

  const selectedCenter = centers.find((center) => center.id === selectedCenterId);
  const activeRunFor = (task: DevTask) =>
    runs.find((run) => run.task_id === task.id && run.status === "running");

  return (
    <div className="console-shell">
      <aside className="sidebar">
        <a className="brand" href="./platform.html">Fleet <span>Platform</span></a>
        <p className="sidebar-label">PLATFORM</p>
        <nav className="navigation" aria-label="Platform sections">
          <a className="navigation-link selected" href="#centers">Centers</a>
          <a className="navigation-link" href="#audit">Audit log</a>
          {devToolsEnabled && <a className="navigation-link" href="#dev-tasks">Dev tasks</a>}
        </nav>
        <div className="sidebar-footer">
          <span className="owner-email">{platformEmail}</span>
          <Button type="button" variant="secondary" onClick={() => void logout()}>
            Log out
          </Button>
        </div>
      </aside>

      <main className="workspace">
        <header className="page-header">
          <div>
            <p className="eyebrow">Fleet Tracker</p>
            <h1>Platform console</h1>
          </div>
          <Badge tone="self">Platform owner</Badge>
        </header>
        <ErrorBanner>{pageError}</ErrorBanner>

        <section id="centers" className="content-grid" aria-labelledby="centers-title">
          <article className="panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Platform</p><h2 id="centers-title">Centers</h2></div>
            </div>
            <ErrorBanner>{centersError}</ErrorBanner>
            <Table label="Centers">
              <thead>
                <tr>
                  <th>Name</th><th>City</th><th>Timezone</th><th>Status</th>
                  <th>Drivers</th><th>Active admins</th><th>Created</th><th>Invitations</th>
                </tr>
              </thead>
              <tbody>
                {centers.map((center) => (
                  <tr key={center.id}>
                    <td>{center.name}</td>
                    <td>{center.city}</td>
                    <td>{center.timezone}</td>
                    <td><span className={`status ${center.active ? "active" : "inactive"}`}>
                      {center.active ? "Active" : "Inactive"}
                    </span></td>
                    <td>{center.driver_count}</td>
                    <td>{center.admin_count}</td>
                    <td>{displayDate(center.created_at)}</td>
                    <td>
                      <Button
                        type="button"
                        variant="secondary"
                        aria-expanded={selectedCenterId === center.id}
                        onClick={() => void selectCenter(center.id)}
                      >
                        {selectedCenterId === center.id ? "Hide invitations" : "Manage invitations"}
                      </Button>
                    </td>
                  </tr>
                ))}
                {centers.length === 0 && (
                  <tr><td colSpan={8} className="empty-state">No centers yet.</td></tr>
                )}
              </tbody>
            </Table>

            {selectedCenter && (
              <section className="invitation-panel" aria-label={`${selectedCenter.name} invitations`}>
                <div className="panel-heading">
                  <div><p className="eyebrow">Center admins</p><h2>Invitations · {selectedCenter.name}</h2></div>
                </div>
                <form className="form-grid" onSubmit={(event) => void submitInvitation(event)}>
                  <Field
                    id={`invitation-email-${selectedCenter.id}`}
                    label="Admin email"
                    type="email"
                    value={invitationEmail}
                    onChange={(event) => setInvitationEmail(event.target.value)}
                    maxLength={254}
                    autoComplete="off"
                    required
                  />
                  <Button type="submit">Create invitation</Button>
                </form>
                <ErrorBanner>{invitationError}</ErrorBanner>
                {invitationLoading ? (
                  <p aria-live="polite">Loading invitations…</p>
                ) : (
                  <Table label={`${selectedCenter.name} invitations`}>
                    <thead><tr><th>Email</th><th>Status</th><th>Created</th><th>Expires</th><th>Action</th></tr></thead>
                    <tbody>
                      {invitations.map((invitation) => (
                        <tr key={invitation.id}>
                          <td>{invitation.email}</td>
                          <td><span className={`status ${invitation.status}`}>{invitation.status}</span></td>
                          <td>{displayDate(invitation.created_at)}</td>
                          <td>{displayDate(invitation.expires_at)}</td>
                          <td>
                            {invitation.status === "pending" && (
                              <Button
                                type="button"
                                variant="danger"
                                onClick={() => void revokeInvitation(invitation)}
                              >
                                Revoke
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {invitations.length === 0 && (
                        <tr><td colSpan={5} className="empty-state">No invitations found.</td></tr>
                      )}
                    </tbody>
                  </Table>
                )}
              </section>
            )}
          </article>

          <article className="panel">
            <div className="panel-heading">
              <div><p className="eyebrow">Create</p><h2>New center</h2></div>
            </div>
            <form className="form-grid" onSubmit={(event) => void submitCenter(event)}>
              <Field
                id="center-name"
                label="Center name"
                value={centerName}
                onChange={(event) => setCenterName(event.target.value)}
                maxLength={200}
                required
              />
              <Field
                id="center-city"
                label="City"
                value={centerCity}
                onChange={(event) => setCenterCity(event.target.value)}
                maxLength={100}
                required
              />
              <Field
                id="center-timezone"
                label="IANA timezone"
                placeholder="Africa/Tunis"
                value={centerTimezone}
                onChange={(event) => setCenterTimezone(event.target.value)}
                maxLength={50}
                required
              />
              <Button type="submit" disabled={creatingCenter}>
                {creatingCenter ? "Creating…" : "Create center"}
              </Button>
            </form>
          </article>
        </section>

        <section id="audit" className="panel audit-panel" aria-labelledby="audit-title">
          <div className="panel-heading">
            <div><p className="eyebrow">Activity</p><h2 id="audit-title">Audit log</h2></div>
          </div>
          <ErrorBanner>{auditError}</ErrorBanner>
          <Table label="Platform audit log">
            <thead>
              <tr><th>Time</th><th>Action</th><th>Target</th><th>IP</th><th>User agent</th><th>Result</th></tr>
            </thead>
            <tbody>
              {auditEvents.map((event) => (
                <tr key={event.id}>
                  <td>{displayDate(event.created_at)}</td>
                  <td>{event.action}</td>
                  <td>{event.target_type}{event.target_id ? ` · ${event.target_id}` : ""}</td>
                  <td>{event.ip ?? "—"}</td>
                  <td>{event.user_agent ?? "—"}</td>
                  <td><span className={`result ${event.success ? "success" : "failure"}`}>
                    {event.success ? "Success" : "Failure"}
                  </span></td>
                </tr>
              ))}
              {auditEvents.length === 0 && (
                <tr><td colSpan={6} className="empty-state">
                  {auditLoading ? "Loading audit events…" : "No audit events found."}
                </td></tr>
              )}
            </tbody>
          </Table>
          <div className="pagination-controls" aria-label="Audit log pagination">
            <Button
              type="button"
              variant="secondary"
              disabled={auditLoading || auditOffset === 0}
              onClick={() => void loadAuditPage(Math.max(0, auditOffset - AUDIT_LIMIT))}
            >
              Previous
            </Button>
            <span>Showing {auditOffset + 1}–{auditOffset + auditEvents.length}</span>
            <Button
              type="button"
              variant="secondary"
              disabled={auditLoading || auditEvents.length < AUDIT_LIMIT}
              onClick={() => void loadAuditPage(auditOffset + AUDIT_LIMIT)}
            >
              Next
            </Button>
          </div>
        </section>

        {devTasksError && <ErrorBanner>{devTasksError}</ErrorBanner>}
        {devToolsEnabled && (
          <section id="dev-tasks" className="dev-tools-section" aria-label="Development tasks">
            <p className="dev-tools-banner">DEV TOOLS ENABLED</p>
            <div className="dev-task-grid">
              {devTasks.map((task) => {
                const activeRun = activeRunFor(task);
                const latestRun = activeRun ?? runs.find((run) => run.task_id === task.id);
                const testFileParameter = task.parameters.find((parameter) => parameter.name === "test_file");
                return (
                  <article className="dev-task-card" key={task.id}>
                    <div className="dev-task-heading">
                      <div><h2>{task.label}</h2><p className="dev-task-description">{task.description}</p></div>
                      <span className={`dev-task-status ${latestRun?.status ?? "idle"}`}>
                        {latestRun?.service_state ?? latestRun?.status ?? "idle"}
                      </span>
                    </div>
                    {testFileParameter && (
                      <label className="dev-task-parameter">
                        {testFileParameter.description}
                        <input
                          type="text"
                          maxLength={120}
                          value={taskFileValues[task.id] ?? ""}
                          onChange={(event) => setTaskFileValues((current) => ({
                            ...current,
                            [task.id]: event.target.value,
                          }))}
                        />
                      </label>
                    )}
                    <div className="dev-task-controls">
                      <Button
                        type="button"
                        disabled={Boolean(activeRun)}
                        onClick={() => void startTask(task)}
                      >
                        {task.kind === "service" ? "Start" : "Run"}
                      </Button>
                      {activeRun && (
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() => void stopRun(activeRun)}
                        >
                          Stop
                        </Button>
                      )}
                      {latestRun && (
                        <span className="dev-task-meta">
                          Run {latestRun.id} · {latestRun.output_line_count} lines
                        </span>
                      )}
                    </div>
                    {latestRun && (
                      <pre className="dev-task-log" aria-label={`${task.label} output`}>
                        {latestRun.lines.join("\n") || "No output yet."}
                      </pre>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        )}
      </main>

      <OneTimeSecretDialog
        open={secretOpen}
        title={secretTitle}
        warning="This invitation link and token are shown only once. Save them securely before closing."
        entries={secretEntries}
        onClose={() => {
          setSecretEntries([]);
          setSecretOpen(false);
        }}
      />
    </div>
  );
}
