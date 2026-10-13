import type { Driver, DriverStatus } from "../api/types";

export function getDriverStatus(
  driver: Driver,
  nowMs: number = Date.now(),
): DriverStatus {
  if (
    !driver
    || driver.active === false
    || driver.lat === null
    || driver.lng === null
    || driver.online !== 1
  ) {
    return "offline";
  }
  const recordedAt = Number(driver.recorded_at ?? 0);
  return nowMs / 1000 - recordedAt <= 60 ? "online" : "stale";
}

export function filterDrivers(
  drivers: Driver[],
  query: string,
  filter: "all" | "active" | "inactive",
  nowMs: number,
): Driver[] {
  const normalizedQuery = query.trim().toLowerCase();
  return drivers
    .filter((driver) => {
      if (filter === "active" && driver.active === false) return false;
      if (filter === "inactive" && driver.active !== false) return false;
      if (!normalizedQuery) return true;
      const vehicle = driver.vehicle;
      return [
        driver.name,
        driver.phone,
        vehicle?.plate_number,
        vehicle?.taxi_number,
        vehicle?.type,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    })
    .sort((first, second) => {
      const order: Record<DriverStatus, number> = {
        online: 0,
        stale: 1,
        offline: 2,
      };
      const statusOrder = order[getDriverStatus(first, nowMs)] - order[getDriverStatus(second, nowMs)];
      return statusOrder || first.name.localeCompare(second.name);
    });
}
