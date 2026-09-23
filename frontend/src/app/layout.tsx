import type { Metadata, Viewport } from "next";
import { Red_Hat_Mono, Red_Hat_Text } from "next/font/google";
import "./globals.css";

const mono = Red_Hat_Mono({ subsets: ["latin"], variable: "--font-red-hat-mono", display: "swap" });
const text = Red_Hat_Text({ subsets: ["latin"], variable: "--font-red-hat-text", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Suporte geniAI", template: "%s · Suporte geniAI" },
  description: "Quadro de tickets e indicadores do suporte da geniAI.",
};

export const viewport: Viewport = {
  themeColor: "#030606",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${mono.variable} ${text.variable}`}>
      <body>{children}</body>
    </html>
  );
}
