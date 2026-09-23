import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "./login-form";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

function mockFetch(response: Response) {
  const fn = vi.fn<typeof fetch>(async () => response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function submit(user: string, password: string) {
  const u = userEvent.setup();
  await u.type(screen.getByLabelText("Usuário"), user);
  await u.type(screen.getByLabelText("Senha"), password);
  await u.click(screen.getByRole("button", { name: "Entrar" }));
}

beforeEach(() => {
  push.mockReset();
  refresh.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LoginForm", () => {
  it("shows the backend's message on a 401 and stays on the page", async () => {
    mockFetch(Response.json({ detail: "Usuário ou senha incorretos." }, { status: 401 }));
    render(<LoginForm />);
    await submit("suporte", "errada");
    expect(await screen.findByRole("alert")).toHaveTextContent("Usuário ou senha incorretos.");
    expect(push).not.toHaveBeenCalled();
  });

  it("moves the focus to the error message", async () => {
    mockFetch(Response.json({ detail: "Muitas tentativas de login. Aguarde alguns minutos e tente de novo." }, { status: 429 }));
    render(<LoginForm />);
    await submit("suporte", "errada");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Muitas tentativas de login.");
    expect(alert).toHaveFocus();
  });

  it("posts the credentials and goes to the board on success", async () => {
    const fetchFn = mockFetch(new Response(null, { status: 204 }));
    render(<LoginForm />);
    await submit("suporte", "senha-certa");
    expect(push).toHaveBeenCalledWith("/board");
    const [url, init] = fetchFn.mock.calls[0]!;
    expect(url).toBe("/api/auth/login");
    expect(init?.body).toBe(JSON.stringify({ user: "suporte", password: "senha-certa" }));
  });
});
