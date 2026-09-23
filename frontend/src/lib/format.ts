import type { BoardColumn, HandoffReason } from "./types";

/** Kanban columns in display order. "in_triage" is shown as a counter, not a column. */
export const BOARD_COLUMNS: readonly BoardColumn[] = [
  "resolved_by_bot",
  "awaiting_human",
  "in_progress",
  "resolved_by_human",
  "no_response",
];

export const COLUMN_LABELS: Record<BoardColumn, string> = {
  resolved_by_bot: "Resolvido pelo bot",
  awaiting_human: "Aguardando humano",
  in_progress: "Em atendimento",
  resolved_by_human: "Resolvido por humano",
  no_response: "Sem resposta",
};

export const HANDOFF_REASON_LABELS: Record<HandoffReason, string> = {
  human_requested: "Pediu atendente",
  faq_not_resolved: "FAQ não resolveu",
  no_faq_match: "Sem item no FAQ",
  unidentified: "Número não identificado",
  registration_mismatch: "Cadastro não confere",
  off_topic: "Fora do assunto",
  media: "Mídia",
  llm_failure: "Falha da IA",
};

/** "12 min", "3 h", "3 d": the time since a card last moved. */
export function formatElapsed(ms: number): string {
  const minutes = Math.max(0, Math.floor(ms / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
}

export function triageCounter(count: number): string {
  return `${count} ${count === 1 ? "conversa" : "conversas"} com o bot agora`;
}

export function percent(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

export function minutesLabel(n: number | null): string {
  if (n === null) return "—";
  if (n < 60) return `${Math.round(n)} min`;
  return `${(n / 60).toFixed(1).replace(".", ",")} h`;
}

export function decimal(n: number): string {
  return n.toFixed(2).replace(".", ",");
}
