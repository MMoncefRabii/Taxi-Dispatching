import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CenterDashboard } from "./dashboard/CenterDashboard";
import "./styles.css";
import "./shared.css";

const root = document.getElementById("root");
if (!root) throw new Error("The dashboard root element is missing.");

createRoot(root).render(
  <StrictMode>
    <CenterDashboard />
  </StrictMode>,
);
