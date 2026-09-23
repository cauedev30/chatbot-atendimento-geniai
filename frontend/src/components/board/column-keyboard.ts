import type { KeyboardCoordinateGetter } from "@dnd-kit/core";
import { BOARD_COLUMNS } from "@/lib/format";

/**
 * Keyboard drag between columns: Space picks a card up, ←/→ jump one whole column (no glide),
 * Space drops it, Esc cancels. ↑/↓ are ignored: a column has no manual order.
 */
export const columnKeyboardCoordinates: KeyboardCoordinateGetter = (event, { context }) => {
  if (event.code !== "ArrowLeft" && event.code !== "ArrowRight") return undefined;
  event.preventDefault();
  const { collisionRect, droppableRects } = context;
  if (!collisionRect) return undefined;

  const rects = BOARD_COLUMNS.map((column) => droppableRects.get(column)).filter((r) => r !== undefined);
  if (rects.length === 0) return undefined;
  const centerX = collisionRect.left + collisionRect.width / 2;
  let index = rects.findIndex((r) => centerX >= r.left && centerX < r.left + r.width);
  if (index === -1) index = 0;
  const next = rects[index + (event.code === "ArrowRight" ? 1 : -1)];
  if (!next) return undefined;
  return {
    x: next.left + next.width / 2 - collisionRect.width / 2,
    y: Math.max(next.top + 48, collisionRect.top),
  };
};
