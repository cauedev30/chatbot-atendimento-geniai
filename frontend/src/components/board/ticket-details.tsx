"use client";

import { useEffect, useRef } from "react";
import { CloseIcon, ExternalIcon } from "@/components/ui/icons";
import { COLUMN_LABELS, formatDateTime, formatElapsed } from "@/lib/format";
import type { BoardCard, IdLabel, IdName } from "@/lib/types";
import styles from "./board.module.css";
import { TicketActions, type CardActions } from "./ticket-actions";

interface TicketDetailsProps {
  card: BoardCard;
  generatedAt: string;
  busy: boolean;
  requireResponsible: boolean;
  teamMembers: IdName[];
  categories: IdLabel[];
  actions: CardActions;
  onClose(): void;
}

/** Everything about one ticket, in a side sheet over the board: opened by a click on its card. */
export function TicketDetails(props: TicketDetailsProps) {
  const { card, generatedAt, onClose } = props;
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, []);

  const since = formatElapsed(Date.parse(generatedAt) - Date.parse(card.lastMovedAt));

  return (
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-labelledby="ticket-details-title"
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      // A click on the dimmed board around the sheet closes it.
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.sheetBody}>
        <header className={styles.sheetHead}>
          <h2 id="ticket-details-title" className={styles.sheetTitle} tabIndex={-1}>
            Ticket {card.id}
            <span className={styles.sheetColumn}>{COLUMN_LABELS[card.column]}</span>
          </h2>
          <button type="button" className={styles.sheetClose} onClick={onClose} title="Fechar detalhes">
            <CloseIcon />
            <span className="visually-hidden">Fechar detalhes</span>
          </button>
        </header>

        <p className={styles.sheetSummary}>{card.summary || "(sem resumo)"}</p>

        <dl className={styles.sheetFields}>
          <div>
            <dt>Aberto em</dt>
            <dd className="figure">{formatDateTime(card.openedAt)}</dd>
          </div>
          <div>
            <dt>{card.column === "awaiting_human" ? "Esperando há" : "Nesta coluna há"}</dt>
            <dd className="figure">{since}</dd>
          </div>
          <div>
            <dt>Unidade</dt>
            <dd>{card.unitName ?? "Sem unidade"}</dd>
          </div>
          <div>
            <dt>Categoria</dt>
            <dd>{card.categoryLabel ?? "Sem categoria"}</dd>
          </div>
          <div>
            <dt>Responsável</dt>
            <dd>{card.responsibleName ?? "Sem responsável"}</dd>
          </div>
        </dl>

        <a className={styles.sheetLink} href={card.conversationUrl} target="_blank" rel="noopener noreferrer">
          <ExternalIcon />
          Abrir conversa no Chatwoot
          <span className="visually-hidden"> (abre em nova aba)</span>
        </a>

        <section className={styles.sheetActions} aria-labelledby="ticket-details-actions">
          <h3 id="ticket-details-actions" className={styles.sheetSection}>
            Ações
          </h3>
          <TicketActions {...props} id="ticket-details" />
        </section>
      </div>
    </dialog>
  );
}
