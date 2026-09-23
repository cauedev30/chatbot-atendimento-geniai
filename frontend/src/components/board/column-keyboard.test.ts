import type { ClientRect, KeyboardCoordinateGetter } from "@dnd-kit/core";
import { describe, expect, it, vi } from "vitest";
import { BOARD_COLUMNS } from "@/lib/format";
import { columnKeyboardCoordinates } from "./column-keyboard";

function rect(left: number, width: number, height = 400): ClientRect {
  return { left, width, top: 100, height, right: left + width, bottom: 100 + height };
}

function press(code: string, rects: Map<string, ClientRect>, card: ClientRect) {
  const event = { code, preventDefault: vi.fn() } as unknown as KeyboardEvent;
  const args = { context: { collisionRect: card, droppableRects: rects } } as unknown as Parameters<KeyboardCoordinateGetter>[1];
  return columnKeyboardCoordinates(event, { ...args, active: 1, currentCoordinates: { x: 0, y: 0 } });
}

describe("columnKeyboardCoordinates", () => {
  const wide = new Map(BOARD_COLUMNS.map((c, i) => [c, rect(i * 200, 180)]));

  it("jumps one whole column to the right or to the left", () => {
    const inSecond = rect(210, 160, 120);
    expect(press("ArrowRight", wide, inSecond)?.x).toBe(400 + 90 - 80);
    expect(press("ArrowLeft", wide, inSecond)?.x).toBe(90 - 80);
  });

  it("ignores columns that are not on screen (zero-size boxes)", () => {
    // Narrow window: only Aguardando humano is shown; the other columns are display: none.
    const narrow = new Map(BOARD_COLUMNS.map((c) => [c, c === "awaiting_human" ? rect(0, 600) : rect(0, 0, 0)]));
    const card = rect(10, 580, 120);
    expect(press("ArrowRight", narrow, card)).toBeUndefined();
    expect(press("ArrowLeft", narrow, card)).toBeUndefined();
  });
});
