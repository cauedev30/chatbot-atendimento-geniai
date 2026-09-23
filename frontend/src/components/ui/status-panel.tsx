import type { ReactNode } from "react";
import styles from "./status-panel.module.css";

interface StatusPanelProps {
  /** Short machine-ish state, set as a terminal label: "404", "Sem conexão". */
  code: string;
  title: string;
  /** h1 on a page of its own; h2 inside the app shell, whose h1 names the page. */
  level?: 1 | 2;
  children: ReactNode;
  actions: ReactNode;
}

/** What the page shows instead of its content when something is missing or broken. */
export function StatusPanel({ code, title, level = 1, children, actions }: StatusPanelProps) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <section className={styles.panel} aria-labelledby="status-title">
      <p className={styles.code}>{code}</p>
      <Heading id="status-title" className={styles.title}>
        {title}
      </Heading>
      <div className={styles.text}>{children}</div>
      <div className={styles.actions}>{actions}</div>
    </section>
  );
}

/** A page of its own (not found, broken layout): the status panel centered under the wordmark. */
export function StatusScreen(props: StatusPanelProps) {
  return (
    <main className={styles.screen}>
      <div className={styles.stack}>
        <span className={styles.wordmark}>geniAI</span>
        <StatusPanel {...props} />
      </div>
    </main>
  );
}
