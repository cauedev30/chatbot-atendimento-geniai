import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: async () => ({ toString: () => "" }) }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
const { BACKEND_UNAVAILABLE, BackendError, backendGet } = await import("./backend");

beforeEach(() => {
  vi.stubEnv("BACKEND_URL", "http://127.0.0.1:8999");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("backendGet", () => {
  it("turns an unreachable backend into a BackendError with a message for people", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    const err = await backendGet("/api/board").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(BackendError);
    expect(err).toMatchObject({ status: 503, detail: BACKEND_UNAVAILABLE });
  });

  it("keeps the backend's own message on a refusal", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ detail: "Período inválido." }, { status: 400 })));
    await expect(backendGet("/api/indicators")).rejects.toMatchObject({ status: 400, detail: "Período inválido." });
  });
});
