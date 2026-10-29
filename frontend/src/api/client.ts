const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBase = configuredApiBase ?? "http://localhost:8000";
const isRelativeApiBase = apiBase.startsWith("/");

if (
  (isRelativeApiBase && apiBase.startsWith("//"))
  || (apiBase !== "" && !isRelativeApiBase && !/^[a-z][a-z\d+.-]*:\/\//i.test(apiBase))
) {
  throw new Error("VITE_API_BASE_URL must be absolute or an origin-relative path.");
}

const parsedApiBase = new URL(apiBase || window.location.origin, window.location.origin);
if (parsedApiBase.protocol !== "http:" && parsedApiBase.protocol !== "https:") {
  throw new Error("VITE_API_BASE_URL must use HTTP or HTTPS.");
}
export const API_BASE_URL = parsedApiBase.href.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiUrl(path: string): URL {
  return new URL(path.replace(/^\/+/, ""), `${API_BASE_URL}/`);
}

function readErrorMessage(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .flatMap((item: unknown) => {
          if (typeof item !== "object" || item === null || !("msg" in item)) return [];
          return typeof item.msg === "string" ? [item.msg] : [];
        })
        .filter(Boolean);
      if (messages.length) return messages.join(" ");
    }
  }
  return `Request failed (${status}).`;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(apiUrl(path), {
    ...options,
    credentials: options.credentials ?? "include",
    headers,
  });

  if (response.status === 204) return undefined as T;

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) throw new ApiError(response.status, "The server returned an invalid response.");
    payload = null;
  }

  if (!response.ok) {
    throw new ApiError(response.status, readErrorMessage(payload, response.status));
  }
  return payload as T;
}
