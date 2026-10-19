import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Driver } from "../api/types";

const { leafletMocks } = vi.hoisted(() => {
  const map = {
    fitBounds: vi.fn(),
    remove: vi.fn(),
    removeLayer: vi.fn(),
    setView: vi.fn(),
  };
  map.setView.mockReturnValue(map);
  const tileLayer = { addTo: vi.fn() };
  const markerLayer = { addTo: vi.fn() };
  const marker = {
    addTo: vi.fn(),
    bindPopup: vi.fn(),
    on: vi.fn(),
    remove: vi.fn(),
    setIcon: vi.fn(),
    setLatLng: vi.fn(),
  };
  marker.addTo.mockReturnValue(marker);
  const bounds = { pad: vi.fn(() => "padded bounds") };
  return {
    leafletMocks: {
      bounds,
      map,
      marker,
      markerLayer,
      tileLayer,
    },
  };
});

vi.mock("leaflet", () => ({
  default: {
    Icon: { Default: { mergeOptions: vi.fn() } },
    divIcon: vi.fn(() => ({})),
    layerGroup: vi.fn(() => leafletMocks.markerLayer),
    latLngBounds: vi.fn(() => leafletMocks.bounds),
    map: vi.fn(() => leafletMocks.map),
    marker: vi.fn(() => leafletMocks.marker),
    tileLayer: vi.fn(() => leafletMocks.tileLayer),
  },
}));

import { MapView } from "./MapView";

const initialDriver: Driver = {
  id: "driver-1",
  name: "Nadia",
  phone: "",
  active: true,
  online: 1,
  lat: 36.8,
  lng: 10.2,
  speed: null,
  heading: null,
  accuracy: null,
  recorded_at: 1_800_000_000,
  vehicle: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  leafletMocks.map.setView.mockReturnValue(leafletMocks.map);
  leafletMocks.marker.addTo.mockReturnValue(leafletMocks.marker);
  leafletMocks.bounds.pad.mockReturnValue("padded bounds");
});

describe("MapView", () => {
  it("fits driver bounds on initial data but not on subsequent location updates", () => {
    const onMapReady = vi.fn();
    const { rerender } = render(
      <MapView
        drivers={[]}
        onSelect={vi.fn()}
        onMapReady={onMapReady}
        selectedDriverId={null}
        nowMs={1_800_000_000_000}
      />,
    );

    expect(leafletMocks.map.fitBounds).not.toHaveBeenCalled();

    rerender(
      <MapView
        drivers={[initialDriver]}
        onSelect={vi.fn()}
        onMapReady={onMapReady}
        selectedDriverId={null}
        nowMs={1_800_000_000_000}
      />,
    );

    expect(leafletMocks.map.fitBounds).toHaveBeenCalledTimes(1);

    rerender(
      <MapView
        drivers={[{ ...initialDriver, lat: 36.9, lng: 10.3 }]}
        onSelect={vi.fn()}
        onMapReady={onMapReady}
        selectedDriverId={null}
        nowMs={1_800_000_000_000}
      />,
    );

    expect(leafletMocks.map.fitBounds).toHaveBeenCalledTimes(1);
    expect(leafletMocks.marker.setLatLng).toHaveBeenCalledWith([36.9, 10.3]);
  });
});
