import { defineConfig, devices } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

// End-to-end smoke across both services: the FastAPI backend on its own e2e database (fictitious seed)
// and this Next.js app. The backend reads backend/.env (never committed; see backend/.env.example).
const backendDir = path.resolve(__dirname, "../backend");
const envFile = path.join(backendDir, ".env");
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const match = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (match && process.env[match[1]!] === undefined) process.env[match[1]!] = match[2];
  }
}

/**
 * The e2e run writes tickets, so it never uses the dev database: E2E_DATABASE_URL, or else DATABASE_URL
 * from backend/.env pointed at a `geniai_e2e` database on the same server, with the same credential. The
 * backend creates it when missing (python -m geniai.db.cli create).
 */
function e2eDatabaseUrl(): string {
  if (process.env.E2E_DATABASE_URL) return process.env.E2E_DATABASE_URL;
  const dev = process.env.DATABASE_URL;
  if (!dev) throw new Error("Set E2E_DATABASE_URL, or DATABASE_URL in backend/.env.");
  const url = new URL(dev);
  url.pathname = "/geniai_e2e";
  return url.toString();
}

const BACKEND_PORT = 8010;
const FRONTEND_PORT = 3100;
const python = path.join(backendDir, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
process.env.E2E_BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    locale: "pt-BR",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `"${python}" -m geniai.db.cli create && "${python}" -m geniai.db.cli seed && "${python}" -m geniai`,
      cwd: backendDir,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { DATABASE_URL: e2eDatabaseUrl(), SECURE_COOKIE: "false", HOST: "127.0.0.1", PORT: String(BACKEND_PORT) },
    },
    {
      command: `npx next build && npx next start -p ${FRONTEND_PORT} -H 127.0.0.1`,
      url: `http://127.0.0.1:${FRONTEND_PORT}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: { BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
  ],
});
