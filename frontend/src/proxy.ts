import { NextResponse, type NextRequest } from "next/server";

/** Headers a client could send to pose as another address before the backend's login limit. */
const CLIENT_ADDRESS_HEADERS = ["x-forwarded-for", "x-real-ip"] as const;

/**
 * /api/*: forwarded to the backend by the rewrite in next.config.ts. Next adds no X-Forwarded-For of its
 * own and passes on what the client sent, so those headers are dropped unless TRUST_UPSTREAM_PROXY=true
 * says a reverse proxy in front of this app sets them. Without one, the backend sees no client address and
 * slows failed logins down instead of refusing them.
 *
 * Pages: cheap first gate, no session cookie, no board. The backend stays the authority (401).
 */
export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    if (process.env.TRUST_UPSTREAM_PROXY === "true") return NextResponse.next();
    const headers = new Headers(request.headers);
    for (const name of CLIENT_ADDRESS_HEADERS) headers.delete(name);
    return NextResponse.next({ request: { headers } });
  }
  if (!request.cookies.has("geniai_board")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/board/:path*", "/indicators/:path*", "/api/:path*"],
};
