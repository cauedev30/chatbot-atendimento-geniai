import { render, screen, within } from "@testing-library/react";
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
    responsibleName: null,
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
      in_progress: [card({ id: 3, column: "in_progress", responsibleName: "Pessoa Suporte 1" })],
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
  await u.click(within(article).getByText("Ações"));
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

  it("puts the longest wait first in Aguardando humano, with its wait time", () => {
    render(<BoardView board={board()} />);
    const [first, second] = within(column(/^Aguardando humano/)).getAllByRole("article");
    expect(first).toHaveAccessibleName(/^Ticket 2\b/);
    expect(first).toHaveTextContent("47 min");
    expect(second).toHaveTextContent("12 min");
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

  it("refuses to take without choosing a person when one is required", async () => {
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.click(within(article).getByRole("button", { name: "Assumir" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escolha quem vai assumir o ticket.");
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("takes the ticket for the chosen person and refreshes", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Quem assume"), "2");
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

  it("posts the new category", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(1);
    await u.selectOptions(within(article).getByLabelText("Categoria"), "4");
    await u.click(within(article).getByRole("button", { name: "Corrigir" }));
    expect(apiPost).toHaveBeenCalledWith("/api/board/tickets/1/category", { categoryId: 4 });
  });

  it("closes a ticket into Resolvido por humano", async () => {
    apiPost.mockResolvedValue(undefined);
    render(<BoardView board={board()} />);
    const { u, article } = await openActions(3);
    await u.click(within(article).getByRole("button", { name: "Fechar" }));
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
