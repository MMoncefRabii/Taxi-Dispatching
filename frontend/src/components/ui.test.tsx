import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { OneTimeSecretDialog } from "./ui";

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

const secretEntries = [
  { label: "Driver token", value: "temporary-secret-value", copyLabel: "token" },
];

function SecretHarness() {
  const [open, setOpen] = useState(true);
  const [entries, setEntries] = useState(secretEntries);
  return (
    <OneTimeSecretDialog
      open={open}
      title="One-time token"
      warning="Shown only once."
      entries={entries}
      onClose={() => {
        setEntries([]);
        setOpen(false);
      }}
    />
  );
}

describe("OneTimeSecretDialog", () => {
  it("clears the secret from component state and the DOM on close", () => {
    render(<SecretHarness />);
    expect(screen.getByText("temporary-secret-value")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByText("temporary-secret-value")).toBeNull();
    expect(document.body.textContent).not.toContain("temporary-secret-value");
  });
});
