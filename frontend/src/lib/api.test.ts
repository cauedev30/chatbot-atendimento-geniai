import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiPost } from "./api";

function mockFetch(response: Response) {
  const fn = vi.fn<typeof fetch>(async () => response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiPost", () => {
  it("sends JSON to the same origin and resolves on 204", async () => {
    const fetchFn = mockFetch(new Response(null, { status: 204 }));
    await expect(apiPost("/api/board/tickets/7/move", { to: "in_progress" })).resolves.toBeUndefined();
    const [url, init] = fetchFn.mock.calls[0]!;
    expect(url).toBe("/api/board/tickets/7/move");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).get("content-type")).toBe("application/json");
    expect(init?.body).toBe('{"to":"in_progress"}');
  });

  it("sends an empty JSON object when there is no body", async () => {
    const fetchFn = mockFetch(new Response(null, { status: 204 }));
    await apiPost("/api/board/tickets/7/close");
    expect(fetchFn.mock.calls[0]![1]?.body).toBe("{}");
  });

  it("throws ApiError with the backend's Portuguese detail on 400", async () => {
    mockFetch(Response.json({ detail: "Esta conversa já tem outro ticket aberto." }, { status: 400 }));
    const error = await apiPost("/api/board/tickets/7/move", { to: "awaiting_human" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(400);
    expect((error as ApiError).detail).toBe("Esta conversa já tem outro ticket aberto.");
    expect((error as ApiError).message).toBe("Esta conversa já tem outro ticket aberto.");
  });

  it("falls back to a generic message when the body has no detail", async () => {
    mockFetch(new Response("Bad Gateway", { status: 502 }));
    const error = (await apiPost("/api/board").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.detail).toBe("Não foi possível falar com o servidor. Tente de novo.");
  });

  it("turns a network failure into an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const error = (await apiPost("/api/board").catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
  });
});
