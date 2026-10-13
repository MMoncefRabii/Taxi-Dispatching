import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("includes credentials and sends JSON for requests with a body", async () => {
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
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "That taxi number is already assigned." }), {
        status: 409,
      }),
    ));

    await expect(apiRequest("/admin/drivers", { method: "POST", body: "{}" }))
      .rejects.toMatchObject({ status: 409, message: "That taxi number is already assigned." });
  });
});
