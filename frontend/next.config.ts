import type { NextConfig } from "next";

const backend = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  // The browser only talks to this origin: /api/* is proxied to the FastAPI backend, so its
  // session cookie (SameSite=Lax, httpOnly) is first-party. The Chatwoot webhook is not proxied.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
