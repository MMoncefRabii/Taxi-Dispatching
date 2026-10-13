import { useState, type FormEvent } from "react";
import { apiRequest } from "../api/client";
import { Button, ErrorBanner, Field } from "../components/ui";

export function validateInvitationPassword(
  password: string,
  confirmation: string,
): string | null {
  if (password.length < 12 || password.length > 128) {
    return "Password must be between 12 and 128 characters.";
  }
  if (password !== confirmation) return "Passwords do not match.";
  return null;
}

export function InvitationAcceptance() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess(false);

    const validationError = validateInvitationPassword(password, confirmation);
    if (validationError) {
      setError(validationError);
      setToken("");
      setPassword("");
      setConfirmation("");
      return;
    }

    const submission = { token, password };
    setSubmitting(true);
    try {
      await apiRequest<{ ok: boolean }>("/invitations/accept", {
        method: "POST",
        credentials: "omit",
        body: JSON.stringify(submission),
      });
      setSuccess(true);
    } catch {
      setError("Unable to accept this invitation. Check the token and try again.");
    } finally {
      setToken("");
      setPassword("");
      setConfirmation("");
      setSubmitting(false);
    }
  }

  return (
    <main className="login-view">
      <section className="login-card invite-card" aria-labelledby="invite-title">
        <p className="eyebrow">Fleet Tracker · Center admin</p>
        <h1 id="invite-title">Accept invitation</h1>
        {success ? (
          <>
            <p className="message success" role="status">
              Your admin account is ready. You can now sign in to the dashboard.
            </p>
            <a className="login-link" href="./index.html">Go to dashboard</a>
          </>
        ) : (
          <form onSubmit={(event) => void submitInvitation(event)}>
            <Field
              id="invitation-token"
              label="Invitation token"
              name="token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              maxLength={128}
              autoComplete="off"
              required
            />
            <Field
              id="invitation-password"
              label="Password"
              name="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />
            <Field
              id="invitation-password-confirmation"
              label="Confirm password"
              name="password_confirmation"
              type="password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />
            <ErrorBanner>{error}</ErrorBanner>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Submitting…" : "Accept invitation"}
            </Button>
          </form>
        )}
      </section>
    </main>
  );
}
