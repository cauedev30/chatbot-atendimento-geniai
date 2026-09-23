// Browser-side calls to the backend through the same-origin /api proxy (next.config.ts).

export const NETWORK_ERROR = "Não foi possível falar com o servidor. Tente de novo.";

/** A refused call; `detail` is the backend's Portuguese message, ready to show. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return NETWORK_ERROR;
}

export async function apiPost(path: string, body: unknown = {}): Promise<void> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR);
  }
  if (!res.ok) throw new ApiError(res.status, await detailOf(res));
}
