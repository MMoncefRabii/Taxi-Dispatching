import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../api/client";
import {
  InvitationAcceptance,
  validateInvitationPassword,
} from "./InvitationAcceptance";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, apiRequest: vi.fn() };
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("invitation password validation", () => {
  it("enforces the 12–128 character bounds and matching confirmation", () => {
    expect(validateInvitationPassword("short-pass", "short-pass")).toContain("12 and 128");
    expect(validateInvitationPassword("a".repeat(129), "a".repeat(129))).toContain("12 and 128");
    expect(validateInvitationPassword("long-enough-password", "different-password"))
      .toBe("Passwords do not match.");
    expect(validateInvitationPassword("long-enough-password", "long-enough-password"))
      .toBeNull();
  });

  it("omits browser credentials and clears the token and passwords after submission", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ ok: true });
    render(<InvitationAcceptance />);

    fireEvent.change(screen.getByLabelText("Invitation token"), {
      target: { value: "one-time-input-token" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "valid-password-123" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "valid-password-123" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Accept invitation" }).closest("form")!);

    expect((await screen.findByRole("status")).textContent).toContain("account is ready");
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith(
      "/invitations/accept",
      expect.objectContaining({
        method: "POST",
        credentials: "omit",
        body: JSON.stringify({
          token: "one-time-input-token",
          password: "valid-password-123",
        }),
      }),
    ));
    expect(document.body.textContent).not.toContain("one-time-input-token");
    expect(document.body.textContent).not.toContain("valid-password-123");
  });

  it("rejects mismatched passwords without sending the token", async () => {
    const request = vi.mocked(apiRequest);
    request.mockResolvedValue({ ok: true });
    render(<InvitationAcceptance />);

    fireEvent.change(screen.getByLabelText("Invitation token"), {
      target: { value: "temporary-token" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "valid-password-123" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "not-the-same-password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Accept invitation" }).closest("form")!);

    expect((await screen.findByRole("alert")).textContent).toBe("Passwords do not match.");
    expect(request).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("temporary-token");
  });
});
