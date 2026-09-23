"use client";

import { useDraggable } from "@dnd-kit/core";
import { useEffect, useId, useRef, useState } from "react";
import controls from "@/components/ui/controls.module.css";
import { ExternalIcon, GripIcon } from "@/components/ui/icons";
import { BOARD_COLUMNS, COLUMN_LABELS, formatElapsed } from "@/lib/format";
import type { BoardCard, BoardColumn, IdLabel, IdName } from "@/lib/types";
import styles from "./board.module.css";

export interface CardActions {
  take(card: BoardCard, responsibleId: number | null): void;
  clearTakeError(card: BoardCard): void;
  recategorize(card: BoardCard, categoryId: number): void;
  move(card: BoardCard, to: BoardColumn): void;
  close(card: BoardCard): void;
}

interface TicketCardProps {
  card: BoardCard;
  /** Server "now" of the loaded board; waits are measured from it. */
  generatedAt: string;
  longestWait: boolean;
  landed: boolean;
  busy: boolean;
  /** False in the one-column layout: the handle then serves only mouse and touch. */
  keyboardDrag: boolean;
  /** "Assumir" was pressed without choosing who takes the ticket. */
  takeError: boolean;
  requireResponsible: boolean;
  teamMembers: IdName[];
  categories: IdLabel[];
  actions: CardActions;
}

const OPEN: readonly BoardColumn[] = ["awaiting_human", "in_progress"];
const TAKE_NEEDS_PERSON = "Escolha quem vai assumir o ticket.";

export function TicketCard(props: TicketCardProps) {
  const { card, generatedAt, longestWait, landed, busy, keyboardDrag, takeError, requireResponsible } = props;
  const { teamMembers, categories, actions } = props;
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, isDragging } = useDraggable({
    id: card.id,
    data: { column: card.column },
    disabled: busy,
    attributes: { roleDescription: "ticket arrastável" },
  });
  const ids = useId();
  const whoRef = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (takeError) whoRef.current?.focus();
  }, [takeError]);
  const [responsibleId, setResponsibleId] = useState("");
  const [categoryId, setCategoryId] = useState(card.categoryId === null ? "" : String(card.categoryId));
  const [destination, setDestination] = useState("");

  const elapsed = formatElapsed(Date.parse(generatedAt) - Date.parse(card.lastMovedAt));
  const waiting = card.column === "awaiting_human";
  const open = OPEN.includes(card.column);
  const unit = card.unitName ?? "Sem unidade";
  const category = card.categoryLabel ?? "Sem categoria";
  const responsible = card.responsibleName ? `Responsável: ${card.responsibleName}` : "Sem responsável";
  const name = waiting
    ? `Ticket ${card.id}, esperando há ${elapsed}, ${unit}`
    : `Ticket ${card.id}, ${COLUMN_LABELS[card.column]}, ${unit}`;

  const className = [
    styles.card,
    longestWait ? styles.longest : "",
    landed ? styles.landed : "",
    isDragging ? styles.dragging : "",
  ].join(" ");

  return (
    <article
      ref={setNodeRef}
      className={className}
      aria-label={name}
      aria-busy={busy || undefined}
      data-card-id={card.id}
      tabIndex={-1}
      style={transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined}
    >
      <div className={styles.cardTop}>
        {waiting ? (
          <p className={styles.wait}>
            <span className="label">{longestWait ? "Espera mais longa" : "Esperando"}</span>
            <span className={`figure ${styles.waitFigure}`}>{elapsed}</span>
          </p>
        ) : (
          <p className={`label ${styles.since}`}>há {elapsed}</p>
        )}
        <button
          type="button"
          ref={setActivatorNodeRef}
          className={styles.handle}
          aria-label={`Arrastar ticket ${card.id}`}
          {...attributes}
          {...listeners}
          {...(keyboardDrag ? {} : { tabIndex: -1, "aria-hidden": true })}
        >
          <GripIcon />
        </button>
      </div>

      <p className={styles.where}>
        <span>{unit}</span>
        <span className={styles.category}>{category}</span>
      </p>
      <p className={styles.summary}>{card.summary || "(sem resumo)"}</p>
      <p className={styles.responsible}>{responsible}</p>

      <div className={styles.cardFoot}>
        <a className={styles.chatwoot} href={card.conversationUrl} target="_blank" rel="noopener noreferrer">
          Abrir no Chatwoot
          <ExternalIcon />
          <span className="visually-hidden"> (abre em nova aba)</span>
        </a>
        <details className={styles.actions}>
          <summary className={styles.actionsToggle}>Ações</summary>
          <div className={styles.actionsPanel}>
            {open ? (
              <div className={styles.actionRow}>
                <label className={controls.field}>
                  <span className="label">Quem assume</span>
                  <select
                    ref={whoRef}
                    className={controls.select}
                    value={responsibleId}
                    onChange={(e) => {
                      setResponsibleId(e.target.value);
                      actions.clearTakeError(card);
                    }}
                    disabled={busy}
                    required={requireResponsible}
                    aria-invalid={takeError || undefined}
                    aria-describedby={takeError ? `${ids}-take-error` : undefined}
                  >
                    <option value="">Escolha…</option>
                    {teamMembers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className={controls.primary}
                  disabled={busy}
                  onClick={() => actions.take(card, responsibleId === "" ? null : Number(responsibleId))}
                >
                  Assumir
                </button>
                {takeError ? (
                  <p id={`${ids}-take-error`} className={`${controls.error} ${styles.fieldError}`}>
                    {TAKE_NEEDS_PERSON}
                  </p>
                ) : null}
              </div>
            ) : null}

            <div className={styles.actionRow}>
              <label className={controls.field}>
                <span className="label" id={`${ids}-category`}>
                  Categoria
                </span>
                <select
                  className={controls.select}
                  aria-labelledby={`${ids}-category`}
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  disabled={busy}
                >
                  {card.categoryId === null ? <option value="">Sem categoria</option> : null}
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={controls.button}
                disabled={busy || categoryId === ""}
                onClick={() => actions.recategorize(card, Number(categoryId))}
              >
                Corrigir
              </button>
            </div>

            <div className={styles.actionRow}>
              <label className={controls.field}>
                <span className="label">Mover para</span>
                <select
                  className={controls.select}
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  disabled={busy}
                >
                  <option value="">Escolha…</option>
                  {BOARD_COLUMNS.filter((c) => c !== card.column).map((c) => (
                    <option key={c} value={c}>
                      {COLUMN_LABELS[c]}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={controls.button}
                disabled={busy || destination === ""}
                onClick={() => actions.move(card, destination as BoardColumn)}
              >
                Mover
              </button>
            </div>

            {open ? (
              <button type="button" className={`${controls.button} ${styles.close}`} disabled={busy} onClick={() => actions.close(card)}>
                Fechar
              </button>
            ) : null}
          </div>
        </details>
      </div>
    </article>
  );
}
