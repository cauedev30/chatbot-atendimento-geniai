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
  team_replied: "A equipe respondeu",
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

const TIME_ZONE = "America/Sao_Paulo";
const DAY = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const HOUR = new Intl.DateTimeFormat("pt-BR", { timeZone: TIME_ZONE, hour: "2-digit", minute: "2-digit" });
const DAY_MONTH = new Intl.DateTimeFormat("pt-BR", { timeZone: TIME_ZONE, day: "2-digit", month: "2-digit" });
const FULL_DATE = new Intl.DateTimeFormat("pt-BR", { timeZone: TIME_ZONE, day: "2-digit", month: "2-digit", year: "numeric" });

/** "23/09/2026 às 14:32", in São Paulo time. */
export function formatDateTime(iso: string): string {
  const at = new Date(iso);
  return `${FULL_DATE.format(at)} às ${HOUR.format(at)}`;
}

/**
 * "hoje, 14:32", "ontem, 09:05", "23/09, 14:32" or "23/09/2025, 14:32": when a ticket was opened,
 * in São Paulo time, relative to the server "now" so the server and the browser print the same.
 */
export function formatOpened(openedAt: string, now: string): string {
  const opened = new Date(openedAt);
  const today = new Date(now);
  const yesterday = new Date(today.getTime() - 86_400_000);
  const day = DAY.format(opened);
  const time = HOUR.format(opened);
  if (day === DAY.format(today)) return `hoje, ${time}`;
  if (day === DAY.format(yesterday)) return `ontem, ${time}`;
  const sameYear = day.slice(0, 4) === DAY.format(today).slice(0, 4);
  return `${(sameYear ? DAY_MONTH : FULL_DATE).format(opened)}, ${time}`;
}
