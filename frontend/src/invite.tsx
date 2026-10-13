import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { InvitationAcceptance } from "./invite/InvitationAcceptance";
import "./platform.css";
import "./invite.css";
import "./shared.css";

const root = document.getElementById("root");
if (!root) throw new Error("The invitation root element is missing.");

createRoot(root).render(
  <StrictMode>
    <InvitationAcceptance />
  </StrictMode>,
);
