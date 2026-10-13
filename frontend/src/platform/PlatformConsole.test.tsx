import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "../api/client";
import { PlatformConsole } from "./PlatformConsole";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, apiRequest: vi.fn() };
});

Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
  configurable: true,
  value(this: HTMLDialogElement) {
    this.open = true;
  },
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
  configurable: true,
  value(this: HTMLDialogElement) {
    this.open = false;
  },
});

const center = {
  id: "center-1",
  name: "Central",
  city: "Tunis",
  timezone: "Africa/Tunis",
  active: true,
  created_at: "2026-10-13T20:00:00Z",
  driver_count: 3,
  admin_count: 2,
};

const testTask = {
  id: "run_tests",
  label: "Run backend tests",
  description: "Run the backend test suite.",
  kind: "oneshot" as const,
  parameters: [],
};

function configureApi(devTasksAvailable: boolean) {
  vi.mocked(apiRequest).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path === "/platform/me") return { email: "owner@example.com" } as T;
    if (path === "/platform/centers?limit=200&offset=0") return [center] as T;
    if (path === "/platform/audit?limit=25&offset=0") return [] as T;
    if (path === "/platform/dev/tasks") {
      if (!devTasksAvailable) throw new ApiError(404, "Not found");
      return [testTask] as T;
    }
    if (path === "/platform/dev/runs?limit=20") return { runs: [] } as T;
    if (path === "/platform/centers/center-1/invitations?limit=200&offset=0") return [] as T;
    if (path === "/platform/centers/center-1/invitations") {
      return {
        invitation_id: "invitation-1",
        email: "new-admin@example.com",
        expires_at: "2026-10-15T20:00:00Z",
        link: "http://localhost:5173/invite.html",
        token: "one-time-invitation-token",
      } as T;
    }
    throw new Error(`Unexpected API request: ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("PlatformConsole", () => {
  it("shows development task controls only after the task endpoint returns successfully", async () => {
    configureApi(true);
    render(<PlatformConsole />);

    expect(await screen.findByText("DEV TOOLS ENABLED")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Run backend tests" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run" })).toBeTruthy();
  });

  it("keeps the development task section hidden when the task endpoint is unavailable", async () => {
    configureApi(false);
    render(<PlatformConsole />);

    await screen.findByRole("heading", { name: "Centers" });
    await waitFor(() => {
      expect(screen.queryByText("DEV TOOLS ENABLED")).toBeNull();
      expect(screen.queryByRole("heading", { name: "Run backend tests" })).toBeNull();
    });
  });

  it("shows the new invitation secret once and removes it from the DOM on close", async () => {
    configureApi(false);
    render(<PlatformConsole />);

    fireEvent.click(await screen.findByRole("button", { name: "Manage invitations" }));
    fireEvent.change(await screen.findByLabelText("Admin email"), {
      target: { value: "new-admin@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(await screen.findByText("one-time-invitation-token")).toBeTruthy();
    expect(screen.getByText("http://localhost:5173/invite.html")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(document.body.textContent).not.toContain("one-time-invitation-token");
    });
  });
});
