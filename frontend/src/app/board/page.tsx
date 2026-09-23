import type { Metadata } from "next";
import { BoardView } from "@/components/board/board-view";
import { AppShell } from "@/components/ui/app-shell";
import { BackendUnavailable } from "@/components/ui/backend-unavailable";
import { BackendError, backendGet } from "@/lib/backend";
import type { Board } from "@/lib/types";

export const metadata: Metadata = { title: "Quadro" };

async function load(): Promise<Board | null> {
  try {
    return await backendGet<Board>("/api/board");
  } catch (err) {
    if (err instanceof BackendError) return null;
    throw err;
  }
}

export default async function BoardPage() {
  const board = await load();
  return (
    <AppShell current="board">
      <h1 className="visually-hidden">Quadro de tickets</h1>
      {board ? <BoardView board={board} /> : <BackendUnavailable what="o quadro" retryHref="/board" />}
    </AppShell>
  );
}
