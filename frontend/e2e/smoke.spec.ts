import { expect, test, type Page } from "@playwright/test";

// Fictitious data only: an unknown number (+5511988887777) goes straight to "Aguardando humano".
const backend = process.env.E2E_BACKEND_URL!;
const user = process.env.BOARD_USER ?? "suporte";
const password = process.env.BOARD_PASSWORD!;
const token = process.env.WEBHOOK_TOKEN!;
const stamp = Date.now();
const summary = `Teste de ponta a ponta ${stamp}`;

test.beforeAll(async ({ request }) => {
  const res = await request.post(`${backend}/webhooks/chatwoot/${token}`, {
    data: {
      event: "message_created",
      id: stamp % 2_000_000_000,
      content: summary,
      message_type: "incoming",
      conversation: { id: (stamp % 1_000_000_000) + 1 },
      sender: { phone_number: "+5511988887777" },
    },
  });
  expect(await res.json()).toEqual({ outcome: "unidentified_ticket" });
});

async function login(page: Page) {
  await page.goto("/board");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Usuário").fill(user);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/board$/);
}

test("login, board, drag a card to Em atendimento, indicators", async ({ page }) => {
  await login(page);

  for (const label of ["Resolvido pelo bot", "Aguardando humano", "Em atendimento", "Resolvido por humano", "Sem resposta"]) {
    await expect(page.getByRole("heading", { level: 2, name: new RegExp(`^${label}`) })).toBeVisible();
  }

  const waiting = page.getByRole("region", { name: /^Aguardando humano/ });
  const inProgress = page.getByRole("region", { name: /^Em atendimento/ });
  const card = waiting.getByRole("article").filter({ hasText: summary });
  await expect(card).toBeVisible();

  // Drag by the handle and drop on Em atendimento, level with the card (every column is full height).
  const handle = card.getByRole("button", { name: /^Arrastar ticket/ });
  await handle.scrollIntoViewIfNeeded();
  const from = (await handle.boundingBox())!;
  const to = (await inProgress.boundingBox())!;
  const y = from.y + from.height / 2;
  await page.mouse.move(from.x + from.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(from.x + 40, y + 10, { steps: 5 });
  await page.mouse.move(to.x + to.width / 2, y, { steps: 12 });
  await page.mouse.up();

  await expect(inProgress.getByRole("article").filter({ hasText: summary })).toBeVisible();
  await expect(waiting.getByRole("article").filter({ hasText: summary })).toHaveCount(0);
  await expect(page.locator("main [role=alert]")).toHaveCount(0);

  // The move is the server's truth, not only the screen's.
  await page.reload();
  await expect(
    page.getByRole("region", { name: /^Em atendimento/ }).getByRole("article").filter({ hasText: summary }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Indicadores" }).click();
  await expect(page).toHaveURL(/\/indicators/);
  await expect(page.getByRole("heading", { level: 2, name: "1. Volume" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "6. Saúde do agente" })).toBeVisible();
});
