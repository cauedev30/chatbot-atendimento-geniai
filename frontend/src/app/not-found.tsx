import type { Metadata } from "next";
import Link from "next/link";
import controls from "@/components/ui/controls.module.css";
import { StatusScreen } from "@/components/ui/status-panel";

export const metadata: Metadata = { title: "Página não encontrada" };

export default function NotFound() {
  return (
    <StatusScreen
      code="404"
      title="Página não encontrada"
      actions={
        <Link href="/board" className={controls.primary}>
          Ir para o quadro
        </Link>
      }
    >
      <p>Este endereço não existe no suporte. Confira o link ou volte ao quadro de tickets.</p>
    </StatusScreen>
  );
}
