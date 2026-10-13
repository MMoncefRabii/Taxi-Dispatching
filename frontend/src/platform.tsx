import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Button } from "./components/ui";
import "./platform.css";
import "./shared.css";

function PlatformEntryShell() {
  return (
    <main className="login-view">
      <section className="login-card">
        <p className="eyebrow">Fleet Tracker · Platform owner</p>
        <h1>Platform console</h1>
        <p className="message">Platform console migration is scheduled for Part C.</p>
        <Button type="button" onClick={() => window.location.assign("./index.html")}>
          Go to dashboard
        </Button>
      </section>
    </main>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("The platform root element is missing.");

createRoot(root).render(
  <StrictMode>
    <PlatformEntryShell />
  </StrictMode>,
);
