import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./app-shell.module.css";
import { LogoutButton } from "./logout-button";

type Section = "board" | "indicators";

const LINKS: { section: Section; href: string; label: string }[] = [
  { section: "board", href: "/board", label: "Quadro" },
  { section: "indicators", href: "/indicators", label: "Indicadores" },
];

export function AppShell({ current, children }: { current: Section; children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        <Link href="/board" className={styles.wordmark} aria-label="geniAI, suporte: ir para o quadro">
          geniAI
        </Link>
        <nav className={styles.nav} aria-label="Seções">
          {LINKS.map((link) => (
            <Link
              key={link.section}
              href={link.href}
              className={styles.link}
              aria-current={link.section === current ? "page" : undefined}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className={styles.end}>
          <LogoutButton />
        </div>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
