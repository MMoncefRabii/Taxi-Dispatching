import { afterEach, describe, expect, it, vi } from "vitest";
import { nextReconnectDelay } from "./websocket";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("WebSocket reconnect backoff", () => {
  it("grows exponentially and caps the delay at 30 seconds", () => {
    expect(nextReconnectDelay(0)).toBe(1_000);
    expect(nextReconnectDelay(1)).toBe(2_000);
    expect(nextReconnectDelay(2)).toBe(4_000);
    expect(nextReconnectDelay(20)).toBe(30_000);
  });
});

describe("WebSocket URL", () => {
  it("uses the current origin when VITE_API_BASE_URL is empty", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.resetModules();
    const { fleetWebSocketUrl: sameOriginWebSocketUrl } = await import("./websocket");

    expect(sameOriginWebSocketUrl().href).toBe(
      `${window.location.origin.replace(/^http/, "ws")}/ws`,
    );
  });

  it("uses the local-development API origin when VITE_API_BASE_URL is undefined", async () => {
    vi.stubEnv("VITE_API_BASE_URL", undefined);
    vi.resetModules();
    const { fleetWebSocketUrl: localWebSocketUrl } = await import("./websocket");

    expect(localWebSocketUrl().href).toBe("ws://localhost:8000/ws");
  });
});
