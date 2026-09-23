import type { Metadata } from "next";
import { LoginForm } from "./login-form";
import styles from "./login.module.css";

export const metadata: Metadata = { title: "Entrar" };

export default function LoginPage() {
  return (
    <main className={styles.screen}>
      <section className={styles.panel} aria-labelledby="login-title">
        <div className={styles.head}>
          <span className={styles.wordmark}>geniAI</span>
          <h1 id="login-title" className={styles.title}>
            Suporte: acesso da equipe
          </h1>
        </div>
        <LoginForm />
      </section>
    </main>
  );
}
