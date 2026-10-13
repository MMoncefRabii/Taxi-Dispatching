import { useState, type FormEvent } from "react";
import { apiRequest, ApiError } from "../api/client";
import type { Driver, DriverFormData } from "../api/types";
import { Button, Dialog, ErrorBanner, Field } from "../components/ui";

interface SaveResult {
  name?: string;
  token?: string;
}

export function DriverEditor({
  open,
  driver,
  onClose,
  onSaved,
}: {
  open: boolean;
  driver: Driver | null;
  onClose: () => void;
  onSaved: (name: string, token: string | null) => Promise<void>;
}) {
  const [name, setName] = useState(driver?.name ?? "");
  const [phone, setPhone] = useState(driver?.phone ?? "");
  const [taxiNumber, setTaxiNumber] = useState(driver?.vehicle?.taxi_number ?? "");
  const [plateNumber, setPlateNumber] = useState(driver?.vehicle?.plate_number ?? "");
  const [model, setModel] = useState(driver?.vehicle?.type ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const editing = driver !== null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const normalizedPlate = plateNumber.trim().toUpperCase();
    if (!/^[A-Z0-9](?:[A-Z0-9 -]{0,48}[A-Z0-9])?$/.test(normalizedPlate)) {
      setError("Use letters, numbers, spaces, and hyphens; the plate must start and end with a letter or number.");
      return;
    }

    const body: DriverFormData = {
      name: name.trim(),
      phone: phone.trim(),
      vehicle: {
        taxi_number: taxiNumber.trim(),
        plate_number: normalizedPlate,
        type: model.trim() || null,
      },
    };
    setSaving(true);
    try {
      const path = editing ? `/admin/drivers/${encodeURIComponent(driver.id)}` : "/admin/drivers";
      const result = await apiRequest<SaveResult>(path, {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      const token = typeof result?.token === "string" ? result.token : null;
      if (result && "token" in result) result.token = "";
      await onSaved(result?.name || body.name, token);
      onClose();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setError("Your admin session is no longer valid. Log in again.");
      } else if (cause instanceof ApiError && cause.status === 409) {
        setError("That taxi number is already assigned. Check the vehicle details and try again.");
      } else if (cause instanceof ApiError && cause.status === 422) {
        setError("Check the driver and vehicle fields and try again.");
      } else if (cause instanceof Error) {
        setError(cause.message);
      } else {
        setError("Unable to save the driver. Check your connection and try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={editing ? "Edit driver" : "New driver"}
      onClose={onClose}
      className="driver-editor-dialog"
    >
      <form onSubmit={(event) => void submit(event)}>
        <Field
          id="driver-name"
          label="Name"
          name="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          minLength={1}
          maxLength={100}
          autoComplete="name"
          required
        />
        <Field
          id="driver-phone"
          label="Phone"
          name="phone"
          type="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          minLength={5}
          maxLength={20}
          autoComplete="tel"
          required
        />
        <fieldset className="vehicle-fields">
          <legend>Vehicle</legend>
          <Field
            id="driver-taxi-number"
            label="Taxi number"
            name="taxi_number"
            value={taxiNumber}
            onChange={(event) => setTaxiNumber(event.target.value)}
            minLength={1}
            maxLength={50}
            required
          />
          <Field
            id="driver-plate"
            label="Plate"
            name="plate_number"
            value={plateNumber}
            onChange={(event) => setPlateNumber(event.target.value)}
            minLength={1}
            maxLength={50}
            required
          />
          <Field
            id="driver-model"
            label="Model"
            name="type"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            maxLength={50}
          />
        </fieldset>
        <ErrorBanner>{error}</ErrorBanner>
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>
            {editing ? "Save changes" : "Create driver"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
