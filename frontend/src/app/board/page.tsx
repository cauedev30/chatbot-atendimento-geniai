import type { Metadata } from "next";
import { BoardView } from "@/components/board/board-view";
import { AppShell } from "@/components/ui/app-shell";
import { backendGet } from "@/lib/backend";
import type { Board } from "@/lib/types";

export const metadata: Metadata = { title: "Quadro" };

export default async function BoardPage() {
  const board = await backendGet<Board>("/api/board");
  return (
    <AppShell current="board">
      <h1 className="visually-hidden">Quadro de tickets</h1>
      <BoardView board={board} />
    </AppShell>
  );
}
