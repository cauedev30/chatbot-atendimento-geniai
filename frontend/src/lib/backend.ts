import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export function backendUrl(): string {
  const url = process.env.BACKEND_URL;
  if (!url) throw new Error("BACKEND_URL is not set (see .env.example)");
  return url.replace(/\/+$/, "");
}

export class BackendError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "BackendError";
  }
}

/** Server-only GET that forwards the visitor's cookies; a 401 sends them to the login page. */
export async function backendGet<T>(path: string): Promise<T> {
  const cookieHeader = (await cookies()).toString();
  const res = await fetch(`${backendUrl()}${path}`, {
    headers: cookieHeader ? { cookie: cookieHeader } : {},
    cache: "no-store",
  });
  if (res.status === 401) redirect("/login");
  if (!res.ok) {
    let detail = `Erro ${res.status} do servidor.`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new BackendError(res.status, detail);
  }
  return (await res.json()) as T;
}
