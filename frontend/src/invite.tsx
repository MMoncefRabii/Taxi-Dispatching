import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Button } from "./components/ui";
import "./platform.css";
import "./invite.css";
import "./shared.css";

function InvitationEntryShell() {
  return (
    <main className="login-view">
      <section className="login-card invite-card">
        <p className="eyebrow">Fleet Tracker · Center admin</p>
        <h1>Accept invitation</h1>
        <p className="message">Invitation acceptance migration is scheduled for Part D.</p>
        <Button type="button" onClick={() => window.location.assign("./index.html")}>
          Go to dashboard
        </Button>
      </section>
    </main>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("The invitation root element is missing.");

createRoot(root).render(
  <StrictMode>
    <InvitationEntryShell />
  </StrictMode>,
);
