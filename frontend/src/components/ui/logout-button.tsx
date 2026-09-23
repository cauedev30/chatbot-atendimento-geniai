"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import controls from "./controls.module.css";

export function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    try {
      await apiPost("/api/auth/logout");
    } catch {
      // The session may already be gone; the login page is the right place either way.
    }
    router.push("/login");
    router.refresh();
  }

  return (
    <button type="button" className={controls.quiet} onClick={logout} disabled={busy}>
      Sair
    </button>
  );
}
