import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PlatformConsole } from "./platform/PlatformConsole";
import "./platform.css";
import "./shared.css";

const root = document.getElementById("root");
if (!root) throw new Error("The platform root element is missing.");

createRoot(root).render(
  <StrictMode>
    <PlatformConsole />
  </StrictMode>,
);
