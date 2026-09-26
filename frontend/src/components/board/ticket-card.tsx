"use client";

import { useDraggable } from "@dnd-kit/core";
import { useEffect, useId, useRef, useState, type PointerEvent } from "react";
import { ExternalIcon, MoreIcon } from "@/components/ui/icons";
import { COLUMN_LABELS, formatElapsed, formatOpened } from "@/lib/format";
import type { BoardCard, IdLabel, IdName } from "@/lib/types";
import styles from "./board.module.css";
import { TicketActions, type CardActions } from "./ticket-actions";

interface TicketCardProps {
  card: BoardCard;
  /** Server "now" of the loaded board; waits and "hoje"/"ontem" are measured from it. */
  generatedAt: string;
  longestWait: boolean;
  landed: boolean;
  busy: boolean;
  requireResponsible: boolean;
  teamMembers: IdName[];
  categories: IdLabel[];
  actions: CardActions;
  onOpen(card: BoardCard): void;
}

/** Controls inside the card (links, the actions toggle, the actions) never start a drag. */
function fromControl(event: PointerEvent): boolean {
  return event.target instanceof Element && event.target.closest("[data-no-drag]") !== null;
}

export function TicketCard(props: TicketCardProps) {
  const { card, generatedAt, longestWait, landed, busy, onOpen } = props;
  const { listeners, setNodeRef, isDragging } = useDraggable({
    id: card.id,
    data: { column: card.column },
    disabled: busy,
  });
  const ids = useId();
  const [showActions, setShowActions] = useState(false);
  const footRef = useRef<HTMLDivElement>(null);
  // The actions open under the card, often below the column's fold: bring them into view.
  useEffect(() => {
    if (!showActions) return;
    const smooth = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    footRef.current?.scrollIntoView?.({ block: "nearest", behavior: smooth ? "smooth" : "auto" });
  }, [showActions]);

  const elapsed = formatElapsed(Date.parse(generatedAt) - Date.parse(card.lastMovedAt));
  const opened = formatOpened(card.openedAt, generatedAt);
  const unit = card.unitName ?? "Sem unidade";
  const category = card.categoryLabel ?? "Sem categoria";
  const name =
    card.column === "awaiting_human"
      ? `Ticket ${card.id}, esperando há ${elapsed}, ${unit}`
      : `Ticket ${card.id}, ${COLUMN_LABELS[card.column]}, ${unit}`;

  const className = [
    styles.card,
    longestWait ? styles.longest : "",
    landed ? styles.landed : "",
    isDragging ? styles.lifted : "",
  ].join(" ");

  return (
    <article
      ref={setNodeRef}
      className={className}
      aria-label={name}
      aria-busy={busy || undefined}
      data-card-id={card.id}
      tabIndex={-1}
      onPointerDown={(event) => {
        if (!fromControl(event)) listeners?.onPointerDown?.(event);
      }}
    >
      <div className={styles.cardTop}>
        <p className={styles.opened}>
          <span className={styles.date}>Aberto {opened}</span>
          {longestWait ? <span className={styles.oldest}>Espera mais longa</span> : null}
        </p>
        <a
          className={styles.tool}
          href={card.conversationUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="Abrir no Chatwoot"
          data-no-drag
        >
          <ExternalIcon />
          <span className="visually-hidden">Abrir no Chatwoot (abre em nova aba)</span>
        </a>
      </div>

      {/* The summary is the card's one link to its details; its hit area stretches over the whole card. */}
      <button type="button" className={styles.openDetails} onClick={() => onOpen(card)}>
        <span className={styles.summary}>{card.summary || "(sem resumo)"}</span>
        <span className="visually-hidden">, ver detalhes</span>
      </button>

      <dl className={styles.fields}>
        <div>
          <dt>Unidade</dt>
          <dd>{unit}</dd>
        </div>
        <div>
          <dt>Categoria</dt>
          <dd>{category}</dd>
        </div>
        <div>
          <dt>Responsável</dt>
          <dd className={card.responsibleName ? undefined : styles.nobody}>{card.responsibleName ?? "Sem responsável"}</dd>
        </div>
      </dl>

      <div ref={footRef} className={styles.cardFoot} data-no-drag>
        <button
          type="button"
          className={styles.actionsToggle}
          aria-expanded={showActions}
          aria-controls={showActions ? `${ids}-actions` : undefined}
          onClick={() => setShowActions((shown) => !shown)}
        >
          <MoreIcon />
          {showActions ? "Ocultar ações" : "Exibir ações"}
        </button>
        {showActions ? <TicketActions {...props} id={`${ids}-actions`} /> : null}
      </div>
    </article>
  );
}

/** What follows the pointer during a drag: the card's face, without its controls. */
export function CardPreview({ card, generatedAt }: { card: BoardCard; generatedAt: string }) {
  return (
    <div className={`${styles.card} ${styles.dragging}`} aria-hidden="true">
      <p className={styles.opened}>
        <span className={styles.date}>Aberto {formatOpened(card.openedAt, generatedAt)}</span>
      </p>
      <p className={styles.summary}>{card.summary || "(sem resumo)"}</p>
      <p className={styles.fields}>
        {card.unitName ?? "Sem unidade"} · {card.categoryLabel ?? "Sem categoria"}
      </p>
    </div>
  );
}
