import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BackendUnavailable } from "./backend-unavailable";

describe("BackendUnavailable", () => {
  it("says what failed, that nothing was lost, and offers to try again on the same page", () => {
    render(<BackendUnavailable what="o quadro" retryHref="/board" />);
    expect(screen.getByRole("heading", { level: 2, name: "O servidor do suporte não respondeu" })).toBeInTheDocument();
    expect(screen.getByText(/Não foi possível carregar o quadro agora./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tentar de novo" })).toHaveAttribute("href", "/board");
  });
});
