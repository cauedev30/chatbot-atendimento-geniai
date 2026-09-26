import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { IndicatorsResponse } from "@/lib/types";
import { monthColumns, weekColumns } from "./charts";
import { IndicatorsView, InvalidPeriod, heatFill, unitIdOf } from "./indicators-view";

function response(overrides: Partial<IndicatorsResponse["query"]> = {}): IndicatorsResponse {
  return {
    query: { fromDate: "2026-09-01", toDate: "2026-09-30", unitId: null, normalize: false, ...overrides },
    units: [
      { id: 1, name: "Unidade Exemplo Centro" },
      { id: 2, name: "Unidade Exemplo Norte" },
    ],
    data: {
      volume: {
        total: 3,
        byWeek: [{ period: "2026-09-07", count: 3 }],
        byMonth: [{ period: "2026-09", count: 3 }],
        byUnit: [
          { unitId: 1, unitName: "Unidade Exemplo Centro", count: 2 },
          { unitId: null, unitName: null, count: 1 },
        ],
        byCategory: [{ categoryId: 3, label: "Painel / Não consegue entrar", count: 3 }],
      },
      outcomes: {
        byColumn: { resolved_by_bot: 1, awaiting_human: 1, in_progress: 0, resolved_by_human: 0, no_response: 0 },
        byHandoffReason: [{ reason: "no_faq_match", count: 1 }],
        identifiedReached: 2,
        botResolutionRate: 0.5,
        noResponseShare: null,
      },
      heatmap: {
        units: [
          { id: 1, name: "Unidade Exemplo Centro", attendants: 2 },
          { id: 2, name: "Unidade Exemplo Norte", attendants: 0 },
        ],
        categories: [{ id: 3, label: "Painel / Não consegue entrar" }],
        cells: [
          { unitId: 1, categoryId: 3, count: 2 },
          { unitId: null, categoryId: 3, count: 1 },
        ],
        uncategorized: 0,
      },
      time: {
        waitToTakeMedianMin: null,
        waitToTakeAvgMin: null,
        timeToCloseMedianMin: 90,
        timeToCloseAvgMin: 12.4,
      },
      faqHealth: [{ faqItemId: 1, title: "Redefinir senha do painel", used: 0, resolved: 0, resolvedShare: null }],
      agentHealth: { classified: 2, corrected: 0, correctedShare: 0, otherShare: null },
    },
  };
}

describe("IndicatorsView", () => {
  it("shows every block, always open, in order", () => {
    render(<IndicatorsView response={response()} />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Resumo de 01/09 a 30/09/2026",
      "Onde os tickets estão",
      "Por que passaram para humano",
      "Volume",
      "Unidade × categoria",
      "Tempo",
      "Saúde do FAQ",
      "Saúde do agente",
    ]);
    expect(document.querySelector("details")).toBeNull();
  });

  it("shows the bot rate over identified tickets and a dash for missing shares", () => {
    render(<IndicatorsView response={response()} />);
    const summary = screen.getByRole("region", { name: /^Resumo/ });
    expect(summary).toHaveTextContent("Resolvidos pelo bot50%");
    expect(summary).toHaveTextContent("de 2 identificados que saíram da triagem; — ficaram sem resposta");
    const handoffs = screen.getByRole("region", { name: "Por que passaram para humano" });
    expect(within(handoffs).getByRole("row", { name: /Sem item no FAQ/ })).toHaveTextContent("1");
    const faq = screen.getByRole("region", { name: "Saúde do FAQ" });
    expect(within(faq).getByRole("row", { name: /Redefinir senha do painel/ })).toHaveTextContent("não foi enviado—");
    const time = screen.getByRole("region", { name: "Tempo" });
    expect(within(time).getByRole("row", { name: /Da abertura ao fechamento/ })).toHaveTextContent("1,5 h");
    expect(within(time).getByRole("row", { name: /Da abertura ao fechamento/ })).toHaveTextContent("12 min");
  });

  it("splits the board columns into parts of the whole, with a legend of counts and shares", () => {
    render(<IndicatorsView response={response()} />);
    const outcomes = screen.getByRole("region", { name: "Onde os tickets estão" });
    expect(within(outcomes).getByRole("row", { name: /Resolvido pelo bot/ })).toHaveTextContent("150%");
    expect(within(outcomes).getByRole("row", { name: /Em atendimento/ })).toHaveTextContent("00%");
    // Only columns with tickets get a part of the bar.
    expect(outcomes.querySelectorAll("[data-column]:not(th *)").length).toBe(2);
  });

  it("shows each agent share as a ring with its value", () => {
    render(<IndicatorsView response={response()} />);
    const agent = screen.getByRole("region", { name: "Saúde do agente" });
    expect(agent).toHaveTextContent("Categorias corrigidas por humanos0%de 2 tickets classificados pelo bot");
    expect(agent).toHaveTextContent('Classificados como "Outros"—');
  });

  it("builds the normalize toggle URL, keeping the period and unit", () => {
    const { unmount } = render(<IndicatorsView response={response({ unitId: 1 })} />);
    const toggle = screen.getByRole("link", { name: "Dividir pelo número de atendentes da unidade" });
    expect(toggle).toHaveAttribute("href", "/indicators?from=2026-09-01&to=2026-09-30&unit=1&norm=1");
    unmount();
    render(<IndicatorsView response={response({ normalize: true })} />);
    const back = screen.getByRole("link", { name: "Mostrar números absolutos" });
    expect(back).toHaveAttribute("href", "/indicators?from=2026-09-01&to=2026-09-30&unit=&norm=0");
  });

  it("divides the heatmap by attendants, with a dash where a unit has none", () => {
    render(<IndicatorsView response={response({ normalize: true })} />);
    const heatmap = screen.getByRole("region", { name: "Unidade × categoria" });
    expect(within(heatmap).getByRole("row", { name: /Unidade Exemplo Centro/ })).toHaveTextContent("1,00");
    expect(within(heatmap).getByRole("row", { name: /Unidade Exemplo Norte/ })).toHaveTextContent("—");
    // Unknown numbers have no attendants to divide by.
    expect(within(heatmap).getByRole("row", { name: /Sem unidade/ })).toHaveTextContent("—");
    expect(heatmap).toHaveTextContent("A linha Sem unidade não tem atendentes para dividir.");
  });

  it("gives tickets from unknown numbers their own heatmap row, last", () => {
    render(<IndicatorsView response={response()} />);
    const heatmap = screen.getByRole("region", { name: "Unidade × categoria" });
    const rows = within(heatmap).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.firstChild?.textContent)).toEqual([
      "Unidade Exemplo Centro",
      "Unidade Exemplo Norte",
      "Sem unidade",
    ]);
    expect(rows[2]).toHaveTextContent("1");
  });

  it("keeps the chosen unit, period and normalization in the filter form", () => {
    render(<IndicatorsView response={response({ unitId: 2, normalize: true })} />);
    const form = screen.getByRole("search", { name: "Filtros" });
    expect(within(form).getByLabelText("Unidade")).toHaveValue("2");
    expect(within(form).getByLabelText("De")).toHaveValue("2026-09-01");
    expect(within(form).getByLabelText("Até")).toHaveValue("2026-09-30");
    expect(form.querySelector('input[name="norm"]')).toHaveValue("1");
    expect(form).toHaveAttribute("action", "/indicators");
    expect(form).toHaveAttribute("method", "get");
  });

  it("shows the volume one view at a time, by week first, and names the missing unit", async () => {
    const u = userEvent.setup();
    render(<IndicatorsView response={response()} />);
    const volume = screen.getByRole("region", { name: "Volume" });
    expect(within(volume).getByRole("button", { name: "Por semana" })).toHaveAttribute("aria-pressed", "true");
    expect(within(volume).getByText("Semana de 07/09: 3 tickets")).toBeInTheDocument();
    await u.click(within(volume).getByRole("button", { name: "Por unidade" }));
    expect(within(volume).getByRole("button", { name: "Por semana" })).toHaveAttribute("aria-pressed", "false");
    expect(within(volume).queryByText(/^Semana de/)).toBeNull();
    expect(within(volume).getByRole("row", { name: /Sem unidade/ })).toHaveTextContent("1");
    expect(screen.getByRole("region", { name: /^Resumo/ })).toHaveTextContent("Tickets no período3");
  });
});

describe("IndicatorsView context lines", () => {
  it("counts only the tickets without a category as left out of the unit × category table", () => {
    const r = response();
    r.data.heatmap.uncategorized = 1;
    const { unmount } = render(<IndicatorsView response={r} />);
    const heatmap = screen.getByRole("region", { name: "Unidade × categoria" });
    expect(heatmap).toHaveTextContent("1 ticket sem categoria fica fora desta tabela.");
    unmount();
    render(<IndicatorsView response={response()} />);
    expect(screen.getByRole("region", { name: "Unidade × categoria" })).not.toHaveTextContent("fora desta tabela");
  });

  it("shows the empty message instead of a grid of zeros", () => {
    const r = response();
    r.data.heatmap.cells = [];
    r.data.heatmap.uncategorized = 3;
    render(<IndicatorsView response={r} />);
    const heatmap = screen.getByRole("region", { name: "Unidade × categoria" });
    expect(within(heatmap).queryByRole("table")).toBeNull();
    expect(heatmap).toHaveTextContent("Nenhum ticket com categoria no período.");
    expect(heatmap).toHaveTextContent("3 tickets sem categoria ficam fora desta tabela.");
  });

  it("states which tickets the time figures cover", () => {
    render(<IndicatorsView response={response()} />);
    expect(screen.getByRole("region", { name: "Tempo" })).toHaveTextContent("só os tickets que alguém já assumiu");
  });
});

describe("InvalidPeriod", () => {
  it("keeps the chosen unit and dates, and announces and focuses the error", () => {
    render(
      <InvalidPeriod
        units={response().units}
        query={{ fromDate: "2026-09-30", toDate: "2026-09-01", unitId: 2, normalize: false }}
        detail="Período inválido."
      />,
    );
    const form = screen.getByRole("search", { name: "Filtros" });
    expect(within(form).getByLabelText("Unidade")).toHaveValue("2");
    expect(within(form).getByLabelText("De")).toHaveValue("2026-09-30");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Período inválido.");
    expect(alert).toHaveFocus();
  });

  it("reads the unit from the address only when it is a unit id", () => {
    expect(unitIdOf("2")).toBe(2);
    expect(unitIdOf("")).toBeNull();
    expect(unitIdOf(undefined)).toBeNull();
    expect(unitIdOf("abc")).toBeNull();
    expect(unitIdOf("0")).toBeNull();
  });
});

describe("heatFill", () => {
  it("never lands in the band where neither white nor dark ink keeps 4.5:1", () => {
    for (let i = 0; i <= 100; i++) {
      const { alpha, dark } = heatFill(i / 100);
      expect(dark ? alpha >= 0.75 : alpha <= 0.6).toBe(true);
    }
    expect(heatFill(0)).toEqual({ alpha: 0, dark: false });
    expect(heatFill(1).alpha).toBeCloseTo(0.85);
  });
});

describe("volume periods", () => {
  it("lists every week of the period from its Monday, with zero where nothing was opened", () => {
    expect(weekColumns("2026-09-01", "2026-09-30", [{ period: "2026-09-07", count: 3 }]).map((c) => [c.label, c.count])).toEqual([
      ["31/08", 0],
      ["07/09", 3],
      ["14/09", 0],
      ["21/09", 0],
      ["28/09", 0],
    ]);
  });

  it("lists every month of the period, across a year", () => {
    const months = monthColumns("2025-11-15", "2026-02-10", [{ period: "2026-01", count: 4 }]);
    expect(months.map((m) => [m.label, m.count])).toEqual([
      ["nov/25", 0],
      ["dez/25", 0],
      ["jan/26", 4],
      ["fev/26", 0],
    ]);
    expect(months[2]?.spoken).toBe("jan de 2026");
  });
});
