import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { IndicatorsResponse } from "@/lib/types";
import { IndicatorsView, heatFill } from "./indicators-view";

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
        cells: [{ unitId: 1, categoryId: 3, count: 2 }],
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
  it("shows the six blocks in order", () => {
    render(<IndicatorsView response={response()} />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "1. Volume",
      "2. Resultados",
      "3. Unidade × categoria",
      "4. Tempo",
      "5. Saúde do FAQ",
      "6. Saúde do agente",
    ]);
  });

  it("shows the bot rate over identified tickets and a dash for missing shares", () => {
    render(<IndicatorsView response={response()} />);
    const results = screen.getByRole("region", { name: "2. Resultados" });
    expect(results).toHaveTextContent("Taxa de resolução pelo bot50%");
    expect(results).toHaveTextContent("de 2 tickets identificados que saíram da triagem");
    expect(results).toHaveTextContent("Sem resposta—");
    expect(within(results).getByRole("row", { name: /Sem item no FAQ/ })).toHaveTextContent("1");
    const faq = screen.getByRole("region", { name: "5. Saúde do FAQ" });
    expect(within(faq).getByRole("row", { name: /Redefinir senha do painel/ })).toHaveTextContent("—");
    const time = screen.getByRole("region", { name: "4. Tempo" });
    expect(within(time).getByRole("row", { name: /Da abertura ao fechamento/ })).toHaveTextContent("1,5 h");
    expect(within(time).getByRole("row", { name: /Da abertura ao fechamento/ })).toHaveTextContent("12 min");
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
    const heatmap = screen.getByRole("region", { name: "3. Unidade × categoria" });
    expect(within(heatmap).getByRole("row", { name: /Unidade Exemplo Centro/ })).toHaveTextContent("1,00");
    expect(within(heatmap).getByRole("row", { name: /Unidade Exemplo Norte/ })).toHaveTextContent("—");
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

  it("names the missing unit and category rows", () => {
    render(<IndicatorsView response={response()} />);
    const volume = screen.getByRole("region", { name: "1. Volume" });
    expect(within(volume).getByRole("row", { name: /Sem unidade/ })).toHaveTextContent("1");
    expect(volume).toHaveTextContent("Total de tickets no período3");
  });
});

describe("IndicatorsView context lines", () => {
  it("says how many tickets the unit × category table leaves out", () => {
    render(<IndicatorsView response={response()} />);
    const heatmap = screen.getByRole("region", { name: "3. Unidade × categoria" });
    expect(heatmap).toHaveTextContent("1 ticket sem unidade ou sem categoria fica fora desta tabela.");
  });

  it("shows the empty message instead of a grid of zeros", () => {
    const r = response();
    r.data.heatmap.cells = [];
    render(<IndicatorsView response={r} />);
    const heatmap = screen.getByRole("region", { name: "3. Unidade × categoria" });
    expect(within(heatmap).queryByRole("table")).toBeNull();
    expect(heatmap).toHaveTextContent("Nenhum ticket com unidade e categoria no período.");
    expect(heatmap).toHaveTextContent("3 tickets sem unidade ou sem categoria ficam fora desta tabela.");
  });

  it("states which tickets the time figures cover", () => {
    render(<IndicatorsView response={response()} />);
    expect(screen.getByRole("region", { name: "4. Tempo" })).toHaveTextContent("só os tickets que alguém já assumiu");
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
