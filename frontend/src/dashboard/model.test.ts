import { describe, expect, it } from "vitest";
import type { Driver } from "../api/types";
import { filterDrivers, getDriverStatus } from "./model";

function driver(overrides: Partial<Driver> = {}): Driver {
  return {
    id: "driver-1",
    name: "Nadia",
    phone: "20000000",
    active: true,
    online: 1,
    lat: 36.8,
    lng: 10.1,
    speed: 0,
    heading: 0,
    accuracy: null,
    recorded_at: 1_000,
    vehicle: { taxi_number: "TX-1", plate_number: "AB 123", type: "Sedan" },
    ...overrides,
  };
}

describe("getDriverStatus", () => {
  it("classifies no-fix and inactive drivers as offline", () => {
    expect(getDriverStatus(driver({ lat: null }), 1_000_000)).toBe("offline");
    expect(getDriverStatus(driver({ active: false }), 1_000_000)).toBe("offline");
    expect(getDriverStatus(driver({ online: 0 }), 1_000_000)).toBe("offline");
  });

  it("distinguishes online from stale at the 60-second boundary", () => {
    expect(getDriverStatus(driver(), 1_060_000)).toBe("online");
    expect(getDriverStatus(driver(), 1_061_000)).toBe("stale");
  });
});

describe("filterDrivers", () => {
  const rows = [
    driver({ id: "1", name: "Nadia" }),
    driver({ id: "2", name: "Amir", active: false }),
    driver({
      id: "3",
      name: "Salma",
      online: 0,
      vehicle: { taxi_number: "TX-9", plate_number: "ZX 900", type: "Van" },
    }),
  ];

  it("matches search across driver and vehicle details and applies activity filters", () => {
    expect(filterDrivers(rows, "zx 900", "all", 1_000_000).map((row) => row.id)).toEqual(["3"]);
    expect(filterDrivers(rows, "", "active", 1_000_000).map((row) => row.id)).toEqual(["1", "3"]);
    expect(filterDrivers(rows, "", "inactive", 1_000_000).map((row) => row.id)).toEqual(["2"]);
  });
});
