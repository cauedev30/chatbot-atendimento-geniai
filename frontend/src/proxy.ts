import { NextResponse, type NextRequest } from "next/server";

/** Cheap first gate: no session cookie, no board. The backend stays the authority (401). */
export function proxy(request: NextRequest) {
  if (!request.cookies.has("geniai_board")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/board/:path*", "/indicators/:path*"],
};
