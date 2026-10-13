import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "./client";
import type { FleetEvent } from "./types";

const INITIAL_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

export function nextReconnectDelay(attempt: number): number {
  return Math.min(INITIAL_RECONNECT_DELAY_MS * 2 ** attempt, MAX_RECONNECT_DELAY_MS);
}

interface WebSocketHandlers {
  onEvent: (event: FleetEvent) => void;
  onConnected: () => void;
  onDisconnected: () => void;
  onInvalidMessage: () => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isOnlineValue(value: unknown): value is boolean | number {
  return typeof value === "boolean" || typeof value === "number";
}

function isFleetEvent(value: unknown): value is FleetEvent {
  if (!isRecord(value) || typeof value.driver_id !== "string") return false;
  if (value.type === "location") {
    return typeof value.lat === "number"
      && typeof value.lng === "number"
      && typeof value.recorded_at === "number"
      && (value.name === undefined || typeof value.name === "string")
      && (value.speed === undefined || value.speed === null || typeof value.speed === "number")
      && (value.heading === undefined || value.heading === null || typeof value.heading === "number");
  }
  if (value.type === "status") return isOnlineValue(value.online);
  return value.type === "driver_status"
    && typeof value.active === "boolean"
    && isOnlineValue(value.online);
}

export function useFleetWebSocket(
  enabled: boolean,
  handlers: WebSocketHandlers,
): boolean {
  const handlersRef = useRef(handlers);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let stopped = false;

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return;
      const delay = nextReconnectDelay(attempt);
      attempt += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    const connect = () => {
      if (stopped) return;
      const socketUrl = new URL("/ws", API_BASE_URL);
      socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
      try {
        socket = new WebSocket(socketUrl);
      } catch {
        handlersRef.current.onDisconnected();
        scheduleReconnect();
        return;
      }

      const currentSocket = socket;
      currentSocket.addEventListener("open", () => {
        if (stopped || socket !== currentSocket) return;
        attempt = 0;
        setConnected(true);
        handlersRef.current.onConnected();
      });
      currentSocket.addEventListener("message", (message) => {
        if (stopped || socket !== currentSocket || typeof message.data !== "string") return;
        try {
          const parsed: unknown = JSON.parse(message.data);
          if (
            isRecord(parsed)
            && (parsed.type === "location" || parsed.type === "status" || parsed.type === "driver_status")
          ) {
            if (isFleetEvent(parsed)) handlersRef.current.onEvent(parsed);
            else handlersRef.current.onInvalidMessage();
          }
        } catch {
          handlersRef.current.onInvalidMessage();
        }
      });
      currentSocket.addEventListener("close", () => {
        if (stopped || socket !== currentSocket) return;
        socket = null;
        setConnected(false);
        handlersRef.current.onDisconnected();
        scheduleReconnect();
      });
      currentSocket.addEventListener("error", () => currentSocket.close());
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      socket?.close();
      socket = null;
    };
  }, [enabled]);

  return enabled && connected;
}
