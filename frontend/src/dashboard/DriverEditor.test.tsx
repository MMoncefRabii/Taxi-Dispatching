import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Driver } from "../api/types";
import { apiRequest } from "../api/client";
import { DriverEditor } from "./DriverEditor";

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

const existingDriver: Driver = {
  id: "driver-1",
  name: "Nadia",
  phone: "20000000",
  active: true,
  online: 0,
  lat: null,
  lng: null,
  speed: null,
  heading: null,
  accuracy: null,
  recorded_at: null,
  vehicle: { taxi_number: "TX-1", plate_number: "AB 123", type: "Sedan" },
};

afterEach(() => {
  cleanup();
});

function EditorHarness() {
  const [open, setOpen] = useState(false);
  const [driver, setDriver] = useState<Driver | null>(null);
  const [instance, setInstance] = useState(0);
  const openEditor = (selectedDriver: Driver | null) => {
    setDriver(selectedDriver);
    setInstance((current) => current + 1);
    setOpen(true);
  };

  return (
    <>
      <button type="button" onClick={() => openEditor(null)}>Open create</button>
      <button type="button" onClick={() => openEditor(existingDriver)}>Open edit</button>
      <DriverEditor
        key={instance}
        open={open}
        driver={driver}
        onClose={() => setOpen(false)}
        onSaved={async () => undefined}
      />
    </>
  );
}

describe("DriverEditor", () => {
  it("resets create fields and switches titles when moving between create and edit", () => {
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Open create" }));
    expect(screen.getByRole("heading", { name: "New driver" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Temporary name" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Open edit" }));
    expect(screen.getByRole("heading", { name: "Edit driver" })).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Nadia");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Open create" }));
    expect(screen.getByRole("heading", { name: "New driver" })).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("");
  });

  it("uses POST for create and PATCH for edit", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ token: "temporary-test-token" });
    render(<EditorHarness />);

    fireEvent.click(screen.getByRole("button", { name: "Open create" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New Driver" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "20000000" } });
    fireEvent.change(screen.getByLabelText("Taxi number"), { target: { value: "TX-2" } });
    fireEvent.change(screen.getByLabelText("Plate"), { target: { value: "CD 234" } });
    fireEvent.click(screen.getByRole("button", { name: "Create driver" }));
    await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith(
      "/admin/drivers",
      expect.objectContaining({ method: "POST" }),
    ));

    fireEvent.click(screen.getByRole("button", { name: "Open edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(apiRequest).toHaveBeenLastCalledWith(
      "/admin/drivers/driver-1",
      expect.objectContaining({ method: "PATCH" }),
    ));
  });
});
