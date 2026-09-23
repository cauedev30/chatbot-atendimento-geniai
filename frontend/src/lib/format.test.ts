import { describe, expect, it } from "vitest";
import {
  BOARD_COLUMNS,
  COLUMN_LABELS,
  HANDOFF_REASON_LABELS,
  decimal,
  formatElapsed,
  minutesLabel,
  percent,
  triageCounter,
} from "./format";

describe("formatElapsed", () => {
  it("uses minutes, hours, then days", () => {
    expect(formatElapsed(5 * 60_000)).toBe("5 min");
    expect(formatElapsed(3 * 3_600_000)).toBe("3 h");
    expect(formatElapsed(72 * 3_600_000)).toBe("3 d");
  });

  it("rounds down and never goes negative", () => {
    expect(formatElapsed(59_999)).toBe("0 min");
    expect(formatElapsed(-5_000)).toBe("0 min");
    expect(formatElapsed(47 * 3_600_000 + 59 * 60_000)).toBe("47 h");
  });
});

describe("indicator formats", () => {
  it("formats shares and durations in Portuguese", () => {
    expect(percent(0.5)).toBe("50%");
    expect(percent(null)).toBe("—");
    expect(minutesLabel(12.4)).toBe("12 min");
    expect(minutesLabel(90)).toBe("1,5 h");
    expect(minutesLabel(null)).toBe("—");
    expect(decimal(1)).toBe("1,00");
  });
});

describe("labels", () => {
  it("keeps the board column order and the Portuguese labels", () => {
    expect(BOARD_COLUMNS).toEqual(["resolved_by_bot", "awaiting_human", "in_progress", "resolved_by_human", "no_response"]);
    expect(BOARD_COLUMNS.map((c) => COLUMN_LABELS[c])).toEqual([
      "Resolvido pelo bot",
      "Aguardando humano",
      "Em atendimento",
      "Resolvido por humano",
      "Sem resposta",
    ]);
    expect(HANDOFF_REASON_LABELS.no_faq_match).toBe("Sem item no FAQ");
    expect(HANDOFF_REASON_LABELS.llm_failure).toBe("Falha da IA");
  });

  it("says conversa in the singular and conversas otherwise", () => {
    expect(triageCounter(1)).toBe("1 conversa com o bot agora");
    expect(triageCounter(0)).toBe("0 conversas com o bot agora");
    expect(triageCounter(3)).toBe("3 conversas com o bot agora");
  });
});
