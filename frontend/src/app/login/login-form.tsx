"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import controls from "@/components/ui/controls.module.css";
import { ApiError, apiPost } from "@/lib/api";
import styles from "./login.module.css";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/auth/login", { user: String(data.get("user")), password: String(data.get("password")) });
      router.push("/board");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Não foi possível entrar. Tente de novo.");
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} noValidate={false}>
      {error ? (
        <p role="alert" className={controls.error}>
          {error}
        </p>
      ) : null}
      <label className={controls.field}>
        <span className="label">Usuário</span>
        <input className={controls.input} name="user" autoComplete="username" required autoFocus />
      </label>
      <label className={controls.field}>
        <span className="label">Senha</span>
        <input className={controls.input} name="password" type="password" autoComplete="current-password" required />
      </label>
      <button type="submit" className={`${controls.primary} ${styles.submit}`} disabled={busy}>
        {busy ? "Entrando…" : "Entrar"}
      </button>
    </form>
  );
}
