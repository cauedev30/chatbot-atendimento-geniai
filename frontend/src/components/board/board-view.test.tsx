import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Board, BoardCard } from "@/lib/types";
import { BoardView } from "./board-view";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const apiPost = vi.fn<(path: string, body?: unknown) => Promise<void>>();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiPost: (path: string, body?: unknown) => apiPost(path, body) };
});
const { ApiError } = await import("@/lib/api");

const NOW = "2026-09-23T15:00:00Z";

function card(overrides: Partial<BoardCard> & Pick<BoardCard, "id" | "column">): BoardCard {
  return {
    unitName: "Unidade Exemplo Centro",
    categoryId: 3,
    categoryLabel: "Painel / Não consegue entrar",
    summary: "Não consegue entrar no painel.",
    responsibleId: null,
    responsibleName: null,
    openedAt: "2026-09-23T14:40:00Z",
    lastMovedAt: "2026-09-23T14:48:00Z",
    conversationId: 100 + overrides.id,
    conversationUrl: `https://chatwoot.example/app/accounts/1/conversations/${100 + overrides.id}`,
    ...overrides,
  };
}

function board(overrides: Partial<Board> = {}): Board {
  return {
    generatedAt: NOW,
    triageCount: 3,
    columns: {
      resolved_by_bot: [card({ id: 5, column: "resolved_by_bot" })],
      awaiting_human: [
        card({ id: 1, column: "awaiting_human", summary: "<b>Painel</b> não abre", lastMovedAt: "2026-09-23T14:48:00Z" }),
        card({
          id: 2,
          column: "awaiting_human",
          unitName: null,
          categoryId: null,
          categoryLabel: null,
          lastMovedAt: "2026-09-23T14:13:00Z",
        }),
      ],
      in_progress: [card({ id: 3, column: "in_progress", responsibleId: 1, responsibleName: "Pessoa Suporte 1" })],
      resolved_by_human: [],
      no_response: [],
    },
    teamMembers: [
      { id: 1, name: "Pessoa Suporte 1" },
      { id: 2, name: "Pessoa Suporte 2" },
    ],
    categories: [
      { id: 3, label: "Painel / Não consegue entrar" },
      { id: 4, label: "Painel / Relatório não carrega" },
    ],
    requireResponsible: true,
    ...overrides,
  };
}

function column(name: RegExp) {
  return screen.getByRole("region", { name });
}

function ticket(id: number) {
  return screen.getByRole("article", { name: new RegExp(`^Ticket ${id}\\b`) });
}

async function openActions(id: number) {
  const u = userEvent.setup();
  const article = ticket(id);
  await u.click(within(article).getByRole("button", { name: "Exibir ações" }));
  return { u, article };
}

beforeEach(() => {
  apiPost.mockReset();
  refresh.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("BoardView", () => {
  it("renders the five columns in order with their counts", () => {
    render(<BoardView board={board()} />);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Resolvido pelo bot1",
      "Aguardando humano2",
      "Em atendimento1",
      "Resolvido por humano0",
      "Sem resposta0",
    ]);
    expect(within(column(/^Aguardando humano/)).getAllByRole("article")).toHaveLength(2);
  });

  it("puts the longest wait first in Aguardando humano, marked, with its wait in the name", () => {
    render(<BoardView board={board()} />);
    const [first, second] = within(column(/^Aguardando humano/)).getAllByRole("article");
    expect(first).toHaveAccessibleName(/^Ticket 2, esperando há 47 min\b/);
    expect(first).toHaveTextContent("Espera mais longa");
    expect(second).toHaveAccessibleName(/esperando há 12 min\b/);
    expect(second).not.toHaveTextContent("Espera mais longa");
  });

  it("shows when each ticket was opened, in São Paulo time", () => {
    const yesterday = card({ id: 7, column: "in_progress", openedAt: "2026-09-22T12:05:00Z" });
    const lastYear = card({ id: 8, column: "in_progress", openedAt: "2025-12-31T13:00:00Z" });
    render(<BoardView board={board({ columns: { ...board().columns, in_progress: [yesterday, lastYear] } })} />);
    expect(ticket(1)).toHaveTextContent("Aberto hoje, 11:40");
    expect(ticket(7)).toHaveTextContent("Aberto ontem, 09:05");
    expect(ticket(8)).toHaveTextContent("Aberto 31/12/2025, 10:00");
  });

  it("shows the fallbacks, keeps the summary as text and links to Chatwoot in a new tab", () => {
    render(<BoardView board={board()} />);
    const two = ticket(2);
    expect(two).toHaveTextContent("Sem unidade");
    expect(two).toHaveTextContent("Sem categoria");
    expect(two).toHaveTextContent("Sem responsável");
    const one = ticket(1);
    expect(one).toHaveTextContent("<b>Painel</b> não abre");
    const link = within(one).getByRole("link", { name: /Abrir no Chatwoot/ });
    expect(link).toHaveAttribute("href", "https://chatwoot.example/app/accounts/1/conversations/101");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("says conversa in the singular and conversas in the plural", () => {
    const { unmount } = render(<BoardView board={board({ triageCount: 1 })} />);
    expect(screen.getByText("1 conversa com o bot agora")).toBeInTheDocument();
    unmount();
    render(<BoardView board={board({ triageCount: 4 })} />);
    expect(screen.getByText("4 conversas com o bot agora")).toBeInTheDocument();
  });

  it("refuses to take without choosing a person, next to the card, and focuses the field", async () => {
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    const who = within(article).getByLabelText("Responsável");
    expect(who).toBeRequired();
    expect(who).not.toHaveAttribute("aria-invalid");
    await u.click(within(article).getByRole("button", { name: "Assumir" }));
    expect(who).toHaveAttribute("aria-invalid", "true");
    expect(who).toHaveAccessibleDescription("Escolha quem vai assumir o ticket.");
    expect(who).toHaveFocus();
    expect(within(article).getByText("Escolha quem vai assumir o ticket.")).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();
    await u.selectOptions(who, "1");
    expect(who).not.toHaveAttribute("aria-invalid");
  });

  it("shows who has the ticket, refuses the same person again and releases it back to Aguardando", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(3);
    const who = within(article).getByLabelText("Responsável");
    expect(who).toHaveDisplayValue("Pessoa Suporte 1");
    await u.click(within(article).getByRole("button", { name: "Trocar" }));
    expect(who).toHaveAccessibleDescription("Pessoa Suporte 1 já é o responsável.");
    expect(apiPost).not.toHaveBeenCalled();
    await u.click(within(article).getByRole("button", { name: /^Tirar responsável/ }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/3/release", {});
    expect(within(column(/^Aguardando humano/)).getByRole("article", { name: /^Ticket 3\b/ })).toHaveTextContent("Sem responsável");
  });

  it("says why Corrigir and Mover cannot apply, under their own field", async () => {
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    const category = within(article).getByLabelText("Categoria");
    await u.click(within(article).getByRole("button", { name: "Corrigir" }));
    expect(category).toHaveAccessibleDescription("O ticket já está nessa categoria.");
    expect(category).toHaveFocus();
    const destination = within(article).getByLabelText("Mover para");
    await u.click(within(article).getByRole("button", { name: "Mover" }));
    expect(destination).toHaveAccessibleDescription("Escolha para onde mover o ticket.");
    expect(destination).toHaveFocus();
    expect(category).not.toHaveAttribute("aria-invalid");
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("offers the same actions on a closed ticket, where Assumir reopens it", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(5);
    expect(within(article).queryByRole("button", { name: "Resolver ticket" })).toBeNull();
    await u.selectOptions(within(article).getByLabelText("Responsável"), "2");
    await u.click(within(article).getByRole("button", { name: "Assumir" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/5/take", { responsibleId: 2 });
    expect(within(column(/^Em atendimento/)).getByRole("article", { name: /^Ticket 5\b/ })).toHaveTextContent("Pessoa Suporte 2");
  });

  it("asks before resolving a ticket and does nothing when cancelled", async () => {
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(3);
    await u.click(within(article).getByRole("button", { name: "Resolver ticket" }));
    const question = within(article).getByRole("group", { name: /^Resolver o ticket 3\?/ });
    expect(within(question).getByRole("button", { name: "Sim, resolver" })).toHaveFocus();
    await u.click(within(question).getByRole("button", { name: "Cancelar" }));
    expect(apiPost).not.toHaveBeenCalled();
    expect(within(article).getByRole("button", { name: "Resolver ticket" })).toBeInTheDocument();
  });

  it("takes the ticket for the chosen person and refreshes", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Responsável"), "2");
    await u.click(within(article).getByRole("button", { name: "Assumir" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/1/take", { responsibleId: 2 });
    expect(refresh).toHaveBeenCalled();
  });

  it("keeps the card in its column and shows the backend's message when a move fails", async () => {
    apiPost.mockRejectedValue(new ApiError(400, "Esta conversa já tem outro ticket aberto."));
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Mover para"), "in_progress");
    await u.click(within(article).getByRole("button", { name: "Mover" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/1/move", { to: "in_progress" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Esta conversa já tem outro ticket aberto.");
    expect(within(column(/^Aguardando humano/)).getByRole("article", { name: /^Ticket 1\b/ })).toBeInTheDocument();
    expect(within(column(/^Em atendimento/)).queryByRole("article", { name: /^Ticket 1\b/ })).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("posts the new category, announces it and keeps Corrigir usable", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Categoria"), "4");
    const fix = within(article).getByRole("button", { name: "Corrigir" });
    await u.click(fix);
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/1/category", { categoryId: 4 });
    expect(await screen.findByRole("status", { name: "Resultado da ação" })).toHaveTextContent(
      "Categoria do ticket 1 corrigida para Painel / Relatório não carrega.",
    );
    expect(fix).toBeEnabled();
  });

  it("moves focus to the moved card and announces where it went", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Mover para"), "in_progress");
    await u.click(within(article).getByRole("button", { name: "Mover" }));
    await waitFor(() => expect(ticket(1)).toHaveFocus());
    expect(within(column(/^Em atendimento/)).getByRole("article", { name: /^Ticket 1\b/ })).toBe(ticket(1));
    expect(screen.getByRole("status", { name: "Resultado da ação" })).toHaveTextContent("Ticket 1 movido para Em atendimento.");
  });

  it("keeps focus on the card when the backend refuses", async () => {
    apiPost.mockRejectedValue(new ApiError(400, "Não foi possível mover este ticket."));
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(3);
    await u.click(within(article).getByRole("button", { name: "Resolver ticket" }));
    await u.click(within(article).getByRole("button", { name: "Sim, resolver" }));
    await waitFor(() => expect(ticket(3)).toHaveFocus());
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível mover este ticket.");
  });

  it("shows the actions at the foot of the card and hides them again", async () => {
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    expect(within(article).getByLabelText("Mover para")).toBeInTheDocument();
    await u.click(within(article).getByRole("button", { name: "Ocultar ações" }));
    expect(within(article).queryByLabelText("Mover para")).not.toBeInTheDocument();
  });

  it("opens the details of a ticket from its card, with the full summary and the actions", async () => {
    const u = userEvent.setup();
    const long = "Painel não abre desde ontem. ".repeat(12).trim();
    render(<BoardView board={board({ columns: { ...board().columns, in_progress: [card({ id: 3, column: "in_progress", summary: long, responsibleId: 1, responsibleName: "Pessoa Suporte 1" })] } })} />);
    await u.click(within(ticket(3)).getByRole("button", { name: /ver detalhes$/ }));
    const sheet = screen.getByRole("dialog", { name: /^Ticket 3/ });
    expect(sheet).toHaveTextContent(long);
    expect(sheet).toHaveTextContent("Aberto em23/09/2026 às 11:40");
    expect(sheet).toHaveTextContent("ResponsávelPessoa Suporte 1");
    expect(within(sheet).getByRole("link", { name: /Abrir conversa no Chatwoot/ })).toHaveAttribute("target", "_blank");
    expect(within(sheet).getByRole("button", { name: "Trocar" })).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Resolver ticket" })).toBeInTheDocument();
    await u.click(within(sheet).getByRole("button", { name: "Fechar detalhes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves a ticket from its details and keeps them open on the moved ticket", async () => {
    apiPost.mockResolvedValue(undefined);
    const u = userEvent.setup();
    render(<BoardView board={board()} />);
    await u.click(within(ticket(1)).getByRole("button", { name: /ver detalhes$/ }));
    const sheet = screen.getByRole("dialog", { name: /^Ticket 1/ });
    await u.selectOptions(within(sheet).getByLabelText("Mover para"), "in_progress");
    await u.click(within(sheet).getByRole("button", { name: "Mover" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/1/move", { to: "in_progress" });
    await waitFor(() => expect(screen.getByRole("heading", { name: /^Ticket 1/ })).toHaveFocus());
    expect(screen.getByRole("dialog")).toHaveTextContent("Em atendimento");
  });

  it("resolves a ticket into Resolvido por humano", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(3);
    await u.click(within(article).getByRole("button", { name: "Resolver ticket" }));
    await u.click(within(article).getByRole("button", { name: "Sim, resolver" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/3/close", undefined);
    expect(within(column(/^Resolvido por humano/)).getByRole("article", { name: /^Ticket 3\b/ })).toBeInTheDocument();
  });

  it("refreshes on its own every 60 seconds", () => {
    vi.useFakeTimers();
    render(<BoardView board={board()} />);
    vi.advanceTimersByTime(60_000);
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

describe("BoardView in a narrow window", () => {
  let report: ((width: number) => void) | undefined;

  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private readonly callback: ResizeObserverCallback) {
          report = (width) =>
            this.callback([{ contentRect: { width } } as ResizeObserverEntry], this as unknown as ResizeObserver);
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("after a move to a hidden column, focuses the heading of the column on screen", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    act(() => report?.(800));
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Mover para"), "in_progress");
    await u.click(within(article).getByRole("button", { name: "Mover" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: /^Aguardando humano/ })).toHaveFocus());
    expect(screen.getByRole("status", { name: "Resultado da ação" })).toHaveTextContent("Ticket 1 movido para Em atendimento.");
  });
});
