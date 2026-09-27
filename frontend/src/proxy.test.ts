// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy } from "./proxy";

function forwarded(response: Response): { overridden: string[]; forwardedFor: string | null; realIp: string | null } {
  return {
    overridden: (response.headers.get("x-middleware-override-headers") ?? "").split(",").filter(Boolean),
    forwardedFor: response.headers.get("x-middleware-request-x-forwarded-for"),
    realIp: response.headers.get("x-middleware-request-x-real-ip"),
  };
}

const spoofed = () =>
  new NextRequest("http://127.0.0.1:3100/api/auth/login", {
    method: "POST",
    headers: { "x-forwarded-for": "203.0.113.9", "x-real-ip": "203.0.113.9", "content-type": "application/json" },
  });

describe("proxy", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("drops the client address headers a client sent to /api", () => {
    const sent = forwarded(proxy(spoofed()));
    // The request headers are overridden with a set that no longer has them.
    expect(sent.overridden).toContain("content-type");
    expect(sent.overridden).not.toContain("x-forwarded-for");
    expect(sent.overridden).not.toContain("x-real-ip");
    expect(sent.forwardedFor).toBeNull();
    expect(sent.realIp).toBeNull();
  });

  it("keeps them when a trusted reverse proxy in front sets them", () => {
    vi.stubEnv("TRUST_UPSTREAM_PROXY", "true");
    const response = proxy(spoofed());
    expect(response.headers.get("x-middleware-override-headers")).toBeNull();
  });

  it("sends a page request without the session cookie to the login", () => {
    const response = proxy(new NextRequest("http://127.0.0.1:3100/board"));
    expect(new URL(response.headers.get("location") ?? "").pathname).toBe("/login");
  });
});
