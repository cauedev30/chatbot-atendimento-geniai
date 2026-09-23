"use client";

import Link from "next/link";
import controls from "@/components/ui/controls.module.css";
import { StatusScreen } from "@/components/ui/status-panel";

export default function ErrorPage({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <StatusScreen
      code="Erro"
      title="Não foi possível mostrar esta página"
      actions={
        <>
          <button type="button" className={controls.primary} onClick={() => retry()}>
            Tentar de novo
          </button>
          <Link href="/board" className={controls.button}>
            Ir para o quadro
          </Link>
        </>
      }
    >
      <p>Algo falhou ao montar a página. Os tickets continuam guardados; tente de novo em alguns instantes.</p>
      {error.digest ? (
        <p>
          Se o erro continuar, passe este código para quem cuida do sistema: <span className="figure">{error.digest}</span>
        </p>
      ) : null}
    </StatusScreen>
  );
}
