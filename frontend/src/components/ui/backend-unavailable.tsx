import controls from "./controls.module.css";
import { StatusPanel } from "./status-panel";

/** Shown inside the app shell when the backend cannot be reached or fails. */
export function BackendUnavailable({ what, retryHref }: { what: string; retryHref: string }) {
  return (
    <StatusPanel
      code="Sem conexão"
      title="O servidor do suporte não respondeu"
      level={2}
      actions={
        // A plain link: a full request, so the page asks the backend again.
        <a href={retryHref} className={controls.primary}>
          Tentar de novo
        </a>
      }
    >
      <p>
        Não foi possível carregar {what} agora. Os tickets continuam guardados; tente de novo em alguns instantes.
      </p>
    </StatusPanel>
  );
}
