"use client";

import { useEffect, useRef } from "react";
import controls from "./controls.module.css";

/**
 * An error the person has to read before going on: announced, and focused when it appears or
 * changes, so a keyboard or screen-reader user lands on it instead of on the page body.
 */
export function FocusedAlert({ children }: { children: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    ref.current?.focus();
  }, [children]);
  return (
    <p ref={ref} role="alert" tabIndex={-1} className={controls.error}>
      {children}
    </p>
  );
}
