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
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { ApiError, apiPost, NETWORK_ERROR } from "@/lib/api";
import { BOARD_COLUMNS, COLUMN_LABELS, triageCounter } from "@/lib/format";
import type { Board, BoardCard, BoardColumn } from "@/lib/types";
import styles from "./board.module.css";
import { columnKeyboardCoordinates } from "./column-keyboard";
import { TicketCard, type CardActions } from "./ticket-card";

const REFRESH_MS = 60_000;
/** Board width under which the columns become tabs (the container query in board.module.css). */
const NARROW_PX = 1040;

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

/** True while the board is narrow enough to show one column at a time. */
function useNarrow(ref: RefObject<HTMLElement | null>): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setNarrow(entry.contentRect.width <= NARROW_PX);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return narrow;
}

export function BoardView({ board }: { board: Board }) {
  const router = useRouter();
  const boardRef = useRef<HTMLDivElement>(null);
  const narrow = useNarrow(boardRef);
  const [loaded, setLoaded] = useState(board);
  const [columns, setColumns] = useState(board.columns);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [takeError, setTakeError] = useState<number | null>(null);
  const focusCard = useRef<number | null>(null);
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

  // After an action the focus goes back to the card, or, when the card left the column on screen,
  // to that column's heading: never to the page body.
  useEffect(() => {
    const id = focusCard.current;
    if (id === null) return;
    focusCard.current = null;
    const root = boardRef.current;
    const cardEl = root?.querySelector<HTMLElement>(`[data-card-id="${id}"]`);
    const target =
      cardEl && !(narrow && cardEl.closest('[data-shown="false"]'))
        ? cardEl
        : root?.querySelector<HTMLElement>(`#column-${shown}`);
    target?.focus();
  }, [busy, columns, shown, narrow]);

  const pointer = useSensor(PointerSensor, { activationConstraint: { distance: 6 } });
  const keyboard = useSensor(KeyboardSensor, { coordinateGetter: columnKeyboardCoordinates });
  // One column at a time: a keyboard drag has nowhere visible to go, and "Mover para" covers it.
  const sensors = useSensors(pointer, narrow ? null : keyboard);

  async function run(card: BoardCard, request: () => Promise<void>, done: string, optimistic?: BoardColumn) {
    const before = columns;
    setError(null);
    setStatus("");
    setTakeError(null);
    setBusy((s) => new Set(s).add(card.id));
    if (optimistic) {
      setColumns(withMove(columns, card.id, optimistic));
      setLanded(card.id);
    }
    try {
      await request();
      setStatus(done);
      router.refresh();
    } catch (err) {
      if (optimistic) setColumns(before);
      setLanded(null);
      setError(err instanceof ApiError ? err.detail : NETWORK_ERROR);
    } finally {
      focusCard.current = card.id;
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
        setTakeError(card.id);
        return;
      }
      const who = board.teamMembers.find((m) => m.id === responsibleId)?.name;
      void run(
        card,
        () => apiPost(`/api/board/tickets/${card.id}/take`, { responsibleId }),
        who ? `Ticket ${card.id} assumido por ${who}.` : `Ticket ${card.id} assumido.`,
        card.column === "in_progress" ? undefined : "in_progress",
      );
    },
    clearTakeError(card) {
      if (takeError === card.id) setTakeError(null);
    },
    recategorize(card, categoryId) {
      const label = board.categories.find((c) => c.id === categoryId)?.label ?? "a categoria escolhida";
      if (categoryId === card.categoryId) {
        setStatus(`O ticket ${card.id} já está em ${label}.`);
        return;
      }
      void run(
        card,
        () => apiPost(`/api/board/tickets/${card.id}/category`, { categoryId }),
        `Categoria do ticket ${card.id} corrigida para ${label}.`,
      );
    },
    move(card, to) {
      void run(
        card,
        () => apiPost(`/api/board/tickets/${card.id}/move`, { to }),
        `Ticket ${card.id} movido para ${COLUMN_LABELS[to]}.`,
        to,
      );
    },
    close(card) {
      void run(
        card,
        () => apiPost(`/api/board/tickets/${card.id}/close`),
        `Ticket ${card.id} fechado, em ${COLUMN_LABELS.resolved_by_human}.`,
        "resolved_by_human",
      );
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
    <div className={styles.board} ref={boardRef}>
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

      <p role="status" aria-label="Resultado da ação" className="visually-hidden">
        {status}
      </p>

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
                  keyboardDrag={!narrow}
                  takeError={takeError === card.id}
                  requireResponsible={board.requireResponsible}
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
      <h2 id={headingId} className={styles.columnHead} tabIndex={-1}>
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
