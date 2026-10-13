export interface Vehicle {
  taxi_number: string;
  plate_number: string;
  type: string | null;
}

export interface Driver {
  id: string;
  name: string;
  phone: string;
  active: boolean;
  online: number;
  lat: number | null;
  lng: number | null;
  speed: number | null;
  heading: number | null;
  accuracy: number | null;
  recorded_at: number | null;
  vehicle: Vehicle | null;
}

export interface DriverFormData {
  name: string;
  phone: string;
  vehicle: Vehicle;
}

export interface Admin {
  id: string;
  email: string;
  active: boolean;
  is_self: boolean;
  created_at: string | null;
}

export type DriverStatus = "online" | "stale" | "offline";

export type FleetEvent =
  | {
      type: "location";
      driver_id: string;
      name?: string;
      lat: number;
      lng: number;
      speed?: number | null;
      heading?: number | null;
      recorded_at: number;
    }
  | {
      type: "status";
      driver_id: string;
      online: boolean | number;
    }
  | {
      type: "driver_status";
      driver_id: string;
      active: boolean;
      online: boolean | number;
    };
