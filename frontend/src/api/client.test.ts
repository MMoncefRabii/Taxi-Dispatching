import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("apiRequest", () => {
  it("includes credentials and sends JSON for requests with a body", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000");
    const { apiRequest } = await import("./client");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest<{ ok: boolean }>("/admin/login", {
      method: "POST",
      body: JSON.stringify({ email: "admin@example.invalid" }),
    });

    const [, options] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).get("Content-Type")).toBe("application/json");
  });

  it("uses a readable server detail in a typed error without logging the body", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000");
    const { apiRequest } = await import("./client");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "That taxi number is already assigned." }), {
        status: 409,
      }),
    ));

    await expect(apiRequest("/admin/drivers", { method: "POST", body: "{}" }))
      .rejects.toMatchObject({ status: 409, message: "That taxi number is already assigned." });
  });

  it("uses the current origin when VITE_API_BASE_URL is empty", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const { apiUrl } = await import("./client");

    expect(apiUrl("/platform/me").href).toBe(`${window.location.origin}/platform/me`);
  });

  it("keeps the localhost API default when VITE_API_BASE_URL is undefined", async () => {
    vi.stubEnv("VITE_API_BASE_URL", undefined);
    const { apiUrl } = await import("./client");

    expect(apiUrl("/platform/me").href).toBe("http://localhost:8000/platform/me");
  });
});
