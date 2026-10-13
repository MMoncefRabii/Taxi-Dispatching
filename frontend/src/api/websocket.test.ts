import { describe, expect, it } from "vitest";
import { nextReconnectDelay } from "./websocket";

describe("WebSocket reconnect backoff", () => {
  it("grows exponentially and caps the delay at 30 seconds", () => {
    expect(nextReconnectDelay(0)).toBe(1_000);
    expect(nextReconnectDelay(1)).toBe(2_000);
    expect(nextReconnectDelay(2)).toBe(4_000);
    expect(nextReconnectDelay(20)).toBe(30_000);
  });
});
