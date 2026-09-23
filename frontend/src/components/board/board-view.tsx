"use client";

import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  pointerWithin,
  type Announcements,
  type CollisionDetection,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError, apiPost, NETWORK_ERROR } from "@/lib/api";
import { BOARD_COLUMNS, COLUMN_LABELS, triageCounter } from "@/lib/format";
import type { Board, BoardCard, BoardColumn } from "@/lib/types";
import styles from "./board.module.css";
import { columnKeyboardCoordinates } from "./column-keyboard";
import { TicketCard, type CardActions } from "./ticket-card";

const REFRESH_MS = 60_000;
const TAKE_NEEDS_PERSON = "Escolha quem vai assumir o ticket.";

type Columns = Board["columns"];

/** Aguardando humano shows the longest wait first; the other columns keep the server's order. */
function ordered(column: BoardColumn, cards: BoardCard[]): BoardCard[] {
  if (column !== "awaiting_human") return cards;
  return [...cards].sort((a, b) => Date.parse(a.lastMovedAt) - Date.parse(b.lastMovedAt));
}

function withMove(columns: Columns, cardId: number, to: BoardColumn): Columns {
  const next = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, columns[c].filter((x) => x.id !== cardId)])) as Columns;
  const card = BOARD_COLUMNS.flatMap((c) => columns[c]).find((x) => x.id === cardId);
  if (card) next[to] = [{ ...card, column: to }, ...next[to]];
  return next;
}

function findCard(columns: Columns, cardId: number): BoardCard | undefined {
  return BOARD_COLUMNS.flatMap((c) => columns[c]).find((x) => x.id === cardId);
}

const ANNOUNCEMENTS: Announcements = {
  onDragStart: ({ active }) => `Ticket ${active.id} selecionado. Use as setas para trocar de coluna.`,
  onDragOver: ({ active, over }) =>
    over ? `Ticket ${active.id} sobre ${COLUMN_LABELS[over.id as BoardColumn]}.` : `Ticket ${active.id} fora das colunas.`,
  onDragEnd: ({ active, over }) =>
    over ? `Ticket ${active.id} solto em ${COLUMN_LABELS[over.id as BoardColumn]}.` : `Ticket ${active.id} voltou ao lugar.`,
  onDragCancel: ({ active }) => `Movimento do ticket ${active.id} cancelado.`,
};

/** A pointer drops where the pointer is (cards are wider than the narrow columns); the keyboard, by center. */
const collision: CollisionDetection = (args) => (args.pointerCoordinates ? pointerWithin(args) : closestCenter(args));

const INSTRUCTIONS =
  "Para mover um ticket: foque o botão de arrastar, aperte espaço, use as setas para a esquerda e para a direita e aperte espaço de novo para soltar. Esc cancela.";

export function BoardView({ board }: { board: Board }) {
  const router = useRouter();
  const [loaded, setLoaded] = useState(board);
  const [columns, setColumns] = useState(board.columns);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlySet<number>>(new Set());
  const [landed, setLanded] = useState<number | null>(null);
  const [shown, setShown] = useState<BoardColumn>("awaiting_human");

  // A router.refresh() brings a new board from the server: it replaces local state.
  if (loaded !== board) {
    setLoaded(board);
    setColumns(board.columns);
  }

  useEffect(() => {
    const timer = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [router]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: columnKeyboardCoordinates }),
  );

  async function run(card: BoardCard, request: () => Promise<void>, optimistic?: BoardColumn) {
    const before = columns;
    setError(null);
    setBusy((s) => new Set(s).add(card.id));
    if (optimistic) {
      setColumns(withMove(columns, card.id, optimistic));
      setLanded(card.id);
    }
    try {
      await request();
      router.refresh();
    } catch (err) {
      if (optimistic) setColumns(before);
      setLanded(null);
      setError(err instanceof ApiError ? err.detail : NETWORK_ERROR);
    } finally {
      setBusy((s) => {
        const next = new Set(s);
        next.delete(card.id);
        return next;
      });
    }
  }

  const actions: CardActions = {
    take(card, responsibleId) {
      if (responsibleId === null && board.requireResponsible) {
        setError(TAKE_NEEDS_PERSON);
        return;
      }
      void run(
        card,
        () => apiPost(`/api/board/tickets/${card.id}/take`, { responsibleId }),
        card.column === "in_progress" ? undefined : "in_progress",
      );
    },
    recategorize(card, categoryId) {
      void run(card, () => apiPost(`/api/board/tickets/${card.id}/category`, { categoryId }));
    },
    move(card, to) {
      void run(card, () => apiPost(`/api/board/tickets/${card.id}/move`, { to }), to);
    },
    close(card) {
      void run(card, () => apiPost(`/api/board/tickets/${card.id}/close`), "resolved_by_human");
    },
  };

  function onDragEnd({ active, over }: DragEndEvent) {
    if (!over) return;
    const card = findCard(columns, Number(active.id));
    const to = over.id as BoardColumn;
    if (card && card.column !== to) actions.move(card, to);
  }

  const waitingIds = ordered("awaiting_human", columns.awaiting_human).map((c) => c.id);
  const longestWait = waitingIds[0];

  return (
    <div className={styles.board}>
      <div className={styles.status}>
        <p className={styles.counter}>
          <span aria-hidden="true" className={`figure ${styles.counterFigure}`}>
            {board.triageCount}
          </span>
          <span aria-hidden="true" className={styles.counterText}>
            {triageCounter(board.triageCount).replace(/^\d+ /, "")}
          </span>
          <span className="visually-hidden">{triageCounter(board.triageCount)}</span>
        </p>
        <p className={styles.hint}>Atualiza sozinho a cada minuto.</p>
      </div>

      {error ? (
        <div role="alert" className={styles.alert}>
          <span>{error}</span>
          <button type="button" className={styles.dismiss} onClick={() => setError(null)}>
            Dispensar
          </button>
        </div>
      ) : null}

      <nav className={styles.switcher} aria-label="Coluna exibida">
        {BOARD_COLUMNS.map((column) => (
          <button
            key={column}
            type="button"
            className={styles.switch}
            aria-pressed={shown === column}
            onClick={() => setShown(column)}
          >
            <span>{COLUMN_LABELS[column]}</span>
            <span className="figure">{columns[column].length}</span>
          </button>
        ))}
      </nav>

      <DndContext
        id="board-dnd"
        sensors={sensors}
        collisionDetection={collision}
        onDragEnd={onDragEnd}
        accessibility={{ announcements: ANNOUNCEMENTS, screenReaderInstructions: { draggable: INSTRUCTIONS } }}
      >
        <div className={styles.columns}>
          {BOARD_COLUMNS.map((column) => (
            <Column key={column} column={column} count={columns[column].length} shown={shown === column}>
              {ordered(column, columns[column]).map((card) => (
                <TicketCard
                  key={card.id}
                  card={card}
                  generatedAt={board.generatedAt}
                  longestWait={card.id === longestWait}
                  landed={card.id === landed}
                  busy={busy.has(card.id)}
                  teamMembers={board.teamMembers}
                  categories={board.categories}
                  actions={actions}
                />
              ))}
            </Column>
          ))}
        </div>
      </DndContext>
    </div>
  );
}

function Column(props: { column: BoardColumn; count: number; shown: boolean; children: ReactNode }) {
  const { column, count, shown, children } = props;
  const { setNodeRef, isOver } = useDroppable({ id: column });
  const headingId = `column-${column}`;
  return (
    <section
      ref={setNodeRef}
      className={`${styles.column} ${column === "awaiting_human" ? styles.lead : ""} ${isOver ? styles.over : ""}`}
      aria-labelledby={headingId}
      data-shown={shown}
    >
      <h2 id={headingId} className={styles.columnHead}>
        <span>{COLUMN_LABELS[column]}</span>
        <span className={`figure ${styles.columnCount}`}>{count}</span>
      </h2>
      <div className={styles.cards}>
        {children}
        {count === 0 ? <p className={styles.empty}>Nenhum ticket.</p> : null}
      </div>
    </section>
  );
}
