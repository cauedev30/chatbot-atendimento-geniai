"use client";

import { Red_Hat_Display, Red_Hat_Text } from "next/font/google";
import controls from "@/components/ui/controls.module.css";
import { StatusScreen } from "@/components/ui/status-panel";
import "./globals.css";

// This page replaces the root layout, so it brings the fonts and the global styles itself.
const display = Red_Hat_Display({ subsets: ["latin"], variable: "--font-red-hat-display", display: "swap" });
const text = Red_Hat_Text({ subsets: ["latin"], variable: "--font-red-hat-text", display: "swap" });

export default function GlobalError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${text.variable}`}>
      <body>
        <title>Erro · Suporte geniAI</title>
        <StatusScreen
          code="Erro"
          title="O suporte não conseguiu abrir"
          actions={
            <button type="button" className={controls.primary} onClick={() => retry()}>
              Tentar de novo
            </button>
          }
        >
          <p>Algo falhou antes de a página carregar. Os tickets continuam guardados; tente de novo em alguns instantes.</p>
          {error.digest ? (
            <p>
              Se o erro continuar, passe este código para quem cuida do sistema:{" "}
              <span className="figure">{error.digest}</span>
            </p>
          ) : null}
        </StatusScreen>
      </body>
    </html>
  );
}
