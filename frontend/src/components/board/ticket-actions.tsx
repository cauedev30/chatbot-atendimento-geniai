"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import controls from "@/components/ui/controls.module.css";
import { BOARD_COLUMNS, COLUMN_LABELS } from "@/lib/format";
import type { BoardCard, BoardColumn, IdLabel, IdName } from "@/lib/types";
import styles from "./board.module.css";

export interface CardActions {
  take(card: BoardCard, responsibleId: number | null): void;
  release(card: BoardCard): void;
  recategorize(card: BoardCard, categoryId: number): void;
  move(card: BoardCard, to: BoardColumn): void;
  close(card: BoardCard): void;
}

export interface TicketActionsProps {
  card: BoardCard;
  busy: boolean;
  requireResponsible: boolean;
  teamMembers: IdName[];
  categories: IdLabel[];
  actions: CardActions;
  /** Prefix for the ids inside; the card and the details sheet each pass their own. */
  id: string;
}

const OPEN: readonly BoardColumn[] = ["awaiting_human", "in_progress"];

type Field = "who" | "category" | "destination";

/**
 * Responsável, Categoria, Mover para and Resolver: the same controls, in the same order, on the card and
 * in its details. One rule for every button: it is always pressable, and a choice that cannot be applied
 * says why under its own field, which takes the focus.
 */
export function TicketActions(props: TicketActionsProps) {
  const { card } = props;
  // The selects start from what the server says; a new board (after an action) starts them again.
  return <Controls key={`${card.id}:${card.column}:${card.responsibleId}:${card.categoryId}`} {...props} />;
}

function Controls({ card, busy, requireResponsible, teamMembers, categories, actions, id }: TicketActionsProps) {
  const [responsibleId, setResponsibleId] = useState(card.responsibleId === null ? "" : String(card.responsibleId));
  const [categoryId, setCategoryId] = useState(card.categoryId === null ? "" : String(card.categoryId));
  const [destination, setDestination] = useState("");
  const [error, setError] = useState<{ field: Field; message: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const refs: Record<Field, RefObject<HTMLSelectElement | null>> = {
    who: useRef<HTMLSelectElement>(null),
    category: useRef<HTMLSelectElement>(null),
    destination: useRef<HTMLSelectElement>(null),
  };
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (error) refs[error.field].current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the refs are stable
  }, [error]);
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  const open = OPEN.includes(card.column);
  const current = teamMembers.find((m) => m.id === card.responsibleId)?.name;

  function refuse(field: Field, message: string) {
    setError({ field, message });
  }

  function take() {
    if (responsibleId === "") {
      if (requireResponsible) return refuse("who", "Escolha quem vai assumir o ticket.");
      return actions.take(card, null);
    }
    if (card.column === "in_progress" && Number(responsibleId) === card.responsibleId) {
      return refuse("who", `${current ?? "Essa pessoa"} já é o responsável.`);
    }
    actions.take(card, Number(responsibleId));
  }

  function recategorize() {
    if (categoryId === "") return refuse("category", "Escolha uma categoria.");
    if (Number(categoryId) === card.categoryId) return refuse("category", "O ticket já está nessa categoria.");
    actions.recategorize(card, Number(categoryId));
  }

  function move() {
    if (destination === "") return refuse("destination", "Escolha para onde mover o ticket.");
    actions.move(card, destination as BoardColumn);
  }

  function fieldProps(field: Field) {
    const invalid = error?.field === field;
    return {
      ref: refs[field],
      className: controls.select,
      disabled: busy,
      "aria-invalid": invalid || undefined,
      "aria-describedby": invalid ? `${id}-${field}-error` : undefined,
    };
  }

  function errorFor(field: Field) {
    return error?.field === field ? (
      <p id={`${id}-${field}-error`} className={`${controls.error} ${styles.fieldError}`}>
        {error.message}
      </p>
    ) : null;
  }

  return (
    <div id={id} className={styles.actionsPanel}>
      <div className={styles.actionRow}>
        <label className={controls.field}>
          <span className="label">Responsável</span>
          <select
            {...fieldProps("who")}
            value={responsibleId}
            required={requireResponsible}
            onChange={(e) => {
              setResponsibleId(e.target.value);
              setError(null);
            }}
          >
            <option value="">Escolha…</option>
            {teamMembers.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={controls.primary} disabled={busy} onClick={take}>
          {card.column === "in_progress" && card.responsibleId !== null ? "Trocar" : "Assumir"}
        </button>
        {errorFor("who")}
        {card.column === "in_progress" && card.responsibleId !== null ? (
          <button
            type="button"
            className={`${controls.quiet} ${styles.release}`}
            disabled={busy}
            onClick={() => actions.release(card)}
            aria-describedby={`${id}-release-hint`}
          >
            Tirar responsável
            <span id={`${id}-release-hint`} className={styles.releaseHint}>
              volta para {COLUMN_LABELS.awaiting_human}
            </span>
          </button>
        ) : null}
      </div>

      <div className={styles.actionRow}>
        <label className={controls.field}>
          <span className="label">Categoria</span>
          <select
            {...fieldProps("category")}
            value={categoryId}
            onChange={(e) => {
              setCategoryId(e.target.value);
              setError(null);
            }}
          >
            {card.categoryId === null ? <option value="">Sem categoria</option> : null}
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={controls.button} disabled={busy} onClick={recategorize}>
          Corrigir
        </button>
        {errorFor("category")}
      </div>

      <div className={styles.actionRow}>
        <label className={controls.field}>
          <span className="label">Mover para</span>
          <select
            {...fieldProps("destination")}
            value={destination}
            onChange={(e) => {
              setDestination(e.target.value);
              setError(null);
            }}
          >
            <option value="">Escolha…</option>
            {BOARD_COLUMNS.filter((c) => c !== card.column).map((c) => (
              <option key={c} value={c}>
                {COLUMN_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={controls.button} disabled={busy} onClick={move}>
          Mover
        </button>
        {errorFor("destination")}
      </div>

      {open ? (
        <div className={styles.resolve}>
          {confirming ? (
            <div role="group" aria-labelledby={`${id}-resolve-question`} className={styles.confirm}>
              <p id={`${id}-resolve-question`}>
                Resolver o ticket {card.id}? Ele vai para {COLUMN_LABELS.resolved_by_human} e a conversa é encerrada no
                Chatwoot.
              </p>
              <div className={styles.confirmButtons}>
                <button
                  ref={confirmRef}
                  type="button"
                  className={controls.primary}
                  disabled={busy}
                  onClick={() => actions.close(card)}
                >
                  Sim, resolver
                </button>
                <button type="button" className={controls.quiet} onClick={() => setConfirming(false)}>
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className={controls.button} disabled={busy} onClick={() => setConfirming(true)}>
              Resolver ticket
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}
