import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import type { Driver } from "../api/types";
import { getDriverStatus } from "./model";

const TUNIS_CENTER: L.LatLngExpression = [36.8065, 10.1815];

export function fitDrivers(map: L.Map, drivers: Driver[]) {
  const locatedDrivers = drivers.filter(
    (driver): driver is Driver & { lat: number; lng: number } =>
      driver.lat !== null && driver.lng !== null,
  );
  if (!locatedDrivers.length) {
    map.setView(TUNIS_CENTER, 11);
    return;
  }
  const bounds = L.latLngBounds(
    locatedDrivers.map((driver) => [driver.lat as number, driver.lng as number]),
  );
  map.fitBounds(bounds.pad(0.22), { animate: true });
}

function makeDriverIcon(driver: Driver, nowMs: number): L.DivIcon {
  const marker = document.createElement("div");
  marker.className = `driver-marker ${getDriverStatus(driver, nowMs)}`;
  const arrow = document.createElement("span");
  arrow.textContent = "→";
  const heading = Number(driver.heading);
  arrow.style.transform = `rotate(${Number.isFinite(heading) ? heading : 0}deg)`;
  marker.appendChild(arrow);
  return L.divIcon({
    className: "custom-driver-icon",
    html: marker,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -14],
  });
}

function makePopup(driver: Driver, nowMs: number): HTMLElement {
  const content = document.createElement("div");
  content.className = "driver-card";
  const title = document.createElement("h3");
  title.textContent = driver.name || "Unknown driver";
  content.appendChild(title);

  const badge = document.createElement("div");
  badge.className = `status-chip ${getDriverStatus(driver, nowMs)}`;
  badge.textContent = getDriverStatus(driver, nowMs);
  content.appendChild(badge);

  const phoneRow = document.createElement("div");
  phoneRow.className = "row";
  const phoneLabel = document.createElement("span");
  phoneLabel.textContent = "Phone";
  const phoneLink = document.createElement("a");
  phoneLink.href = `tel:${encodeURIComponent(driver.phone || "")}`;
  phoneLink.textContent = driver.phone || "—";
  phoneRow.append(phoneLabel, phoneLink);
  content.appendChild(phoneRow);

  const speedRow = document.createElement("div");
  speedRow.className = "row";
  const speedLabel = document.createElement("span");
  speedLabel.textContent = "Speed";
  const speed = document.createElement("span");
  speed.textContent = formatSpeed(driver.speed);
  speedRow.append(speedLabel, speed);
  content.appendChild(speedRow);

  const seenRow = document.createElement("div");
  seenRow.className = "row";
  const seenLabel = document.createElement("span");
  seenLabel.textContent = "Last seen";
  const seen = document.createElement("span");
  seen.textContent = formatLastSeen(driver, nowMs);
  seenRow.append(seenLabel, seen);
  content.appendChild(seenRow);
  return content;
}

function formatSpeed(speedMps: number | null): string {
  return speedMps === null || Number.isNaN(Number(speedMps))
    ? "—"
    : `${(Number(speedMps) * 3.6).toFixed(1)} km/h`;
}

function formatLastSeen(driver: Driver, nowMs: number): string {
  if (driver.recorded_at === null) return "never";
  const seconds = Math.max(0, Math.floor(nowMs / 1000 - driver.recorded_at));
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}

export function MapView({
  drivers,
  onSelect,
  onMapReady,
  selectedDriverId,
  nowMs,
}: {
  drivers: Driver[];
  onSelect: (driver: Driver) => void;
  onMapReady: (map: L.Map) => void;
  selectedDriverId: string | null;
  nowMs: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());
  const onSelectRef = useRef(onSelect);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    L.Icon.Default.mergeOptions({
      iconRetinaUrl: markerIcon2x,
      iconUrl: markerIcon,
      shadowUrl: markerShadow,
    });
    const map = L.map(container, { zoomControl: true }).setView(TUNIS_CENTER, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    const markerLayer = L.layerGroup().addTo(map);
    const markers = markersRef.current;
    mapRef.current = map;
    onMapReady(map);

    return () => {
      markers.clear();
      map.removeLayer(markerLayer);
      map.remove();
      mapRef.current = null;
    };
  }, [onMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const currentIds = new Set(drivers.map((driver) => String(driver.id)));
    for (const [id, marker] of markersRef.current) {
      if (!currentIds.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    }

    for (const driver of drivers) {
      const id = String(driver.id);
      let marker = markersRef.current.get(id);
      if (driver.lat === null || driver.lng === null) {
        marker?.remove();
        markersRef.current.delete(id);
        continue;
      }
      if (!marker) {
        marker = L.marker([driver.lat, driver.lng], {
          icon: makeDriverIcon(driver, nowMs),
          keyboard: false,
        }).addTo(map);
        marker.on("click", () => onSelectRef.current(driver));
        markersRef.current.set(id, marker);
      } else {
        marker.setLatLng([driver.lat, driver.lng]);
        marker.setIcon(makeDriverIcon(driver, nowMs));
      }
      marker.bindPopup(makePopup(driver, nowMs));
    }
  }, [drivers, nowMs]);

  useEffect(() => {
    const map = mapRef.current;
    if (map) fitDrivers(map, drivers);
  }, [drivers]);

  useEffect(() => {
    if (!selectedDriverId) return;
    markersRef.current.get(selectedDriverId)?.openPopup();
  }, [selectedDriverId]);

  return <div id="map" ref={containerRef} aria-label="Live driver map" />;
}
