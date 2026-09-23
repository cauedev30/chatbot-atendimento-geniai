# chatbot-atendimento-geniai

GeniAI's WhatsApp support desk: a chatbot that runs as a Chatwoot Agent Bot, a kanban board for the
support team and an indicators page.

The bot identifies the customer by phone number, opens a ticket right away, tries **one** answer from
the team's FAQ and hands the conversation to a person the moment one is asked for. One LLM
interprets each customer turn; code decides the flow. Every ticket lands on the board with a summary,
a category and the unit, and feeds the indicators: which problems happen most, how tickets get
solved, and which units suffer most from each problem.

- **Backend:** Python 3.12 · FastAPI · Pydantic · SQLAlchemy Core on asyncpg · PostgreSQL
- **Frontend:** React · Next.js (App Router) · TypeScript
- Design spec: [docs/specs/2026-09-23-single-agent-support-bot-design.md](docs/specs/2026-09-23-single-agent-support-bot-design.md)
- Architecture: [docs/architecture.md](docs/architecture.md)

## Features

**Bot (in WhatsApp, through Chatwoot)**

- Identifies the sender by phone number only (Brazilian numbers normalized, including the 9th
  mobile digit). An unknown number goes straight to a person and never gets the FAQ.
- Greets the attendant by registered name and unit and asks for the problem.
- Groups a burst of short messages into one turn (about 5 s of silence).
- Sends at most one FAQ entry, verbatim as the team wrote it; the LLM only writes the framing
  sentence. Then asks whether it solved the problem.
- Asks at most two clarifying questions, then summarizes and hands over.
- Hands over immediately on any request for a person, detected by keywords in code even if the LLM
  is down, and by the LLM.
- Asks media-only messages to be typed once, then hands over.
- Closes a triage conversation that stays silent for 24 h as "No response".
- Never executes anything in customer systems: the LLM output has no action field.

**Board**

- Five columns: Resolvido pelo bot · Aguardando humano · Em atendimento · Resolvido por humano ·
  Sem resposta, plus a counter of conversations still with the bot.
- The longest wait is the first card, highlighted, with its waiting time.
- Drag and drop between columns (mouse, touch or keyboard), "Mover para", "Assumir" (choose who
  takes the ticket), category correction and "Fechar".
- Two-way sync with Chatwoot: closing a card resolves the conversation, and resolving the
  conversation in Chatwoot closes the card.
- Works in a narrow window beside Chatwoot and on a phone (one column at a time).

**Indicators**

Filtered by period and unit: volume (by week, month, unit, category), outcomes and bot resolution
rate ("no response" never counts as a success), a unit × category heatmap with an option to divide
by attendants, waiting and closing times, FAQ health and agent health. Every chart is a table.

## Architecture

```mermaid
flowchart LR
    WA["WhatsApp"] --> CW["Chatwoot"]
    CW -- "Agent Bot webhook<br/>POST /webhooks/chatwoot/&lt;token&gt;" --> BE
    BE -- "messages, conversation status" --> CW
    BE -- "one call per customer turn" --> LLM["LLM<br/>(OpenAI-compatible API)"]
    BE <--> DB[("PostgreSQL")]
    Team["Support team<br/>(browser)"] --> FE["Frontend<br/>Next.js"]
    FE -- "/api/* (proxy, same origin)" --> BE["Backend<br/>FastAPI"]
```

Two services share one database. The **backend** owns the Chatwoot webhook, the bot, the database
and a JSON API under `/api`. The **frontend** renders the login, the board and the indicators, and
proxies `/api/*` to the backend, so the browser talks to one origin and the backend's session cookie
is first-party. Chatwoot calls the backend directly. Details: [docs/architecture.md](docs/architecture.md).

## Repository layout

```
backend/
  geniai/
    domain/      pure rules: ticket transitions, turn precedence, silence, phone, texts, tunables
    db/          SQLAlchemy schema, SQL migrations, fictitious seed, CLI
    app/         use cases: inbound messages, turns, silence sweeper, board, indicators
    llm/         LLM contract (prompt, output schema, one-retry interpretation), OpenAI-compatible adapter
    chatwoot/    webhook parsing and HTTP client
    api/         FastAPI routers: auth, board, indicators, webhook; response models
    eval/        30 fictitious conversations and the model comparison runner
    config.py    environment configuration
    main.py      the FastAPI app and its background work
  tests/         pytest suite, mirroring geniai/
  openapi.json   the API schema the frontend types are generated from
frontend/
  src/app/         routes: login, board, indicators
  src/components/  board, indicators, UI primitives
  src/lib/         API client, generated API types, formatters
  e2e/             Playwright smoke test
  PRODUCT.md       product context for design work
  DESIGN.md        the visual system
docs/
  specs/           design spec
  architecture.md  how the system works
```

## Requirements

- Python 3.12 or newer
- Node.js 24 or newer
- PostgreSQL (tests need a second, empty database)

## Backend

In `backend/`:

```sh
python -m venv .venv
.venv\Scripts\activate          # Windows; on Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env             # then fill it in (see Configuration)
```

| Command | What it does |
|---|---|
| `python -m geniai.db.cli migrate` | Apply `geniai/db/migrations/*.sql` to `DATABASE_URL` |
| `python -m geniai.db.cli seed` | Load **fictitious** demo data (once; a second run does nothing) |
| `uvicorn geniai.main:create_app --factory --host 0.0.0.0 --port 8000` | Run the service. It migrates on start, reschedules turns left pending by a restart and sweeps silent tickets every 5 minutes |
| `python -m geniai.eval.run` | Run the evaluation set against the models in `EVAL_CANDIDATES` |
| `python -m geniai.export_openapi` | Rewrite `openapi.json` after an API change |

The service reads only environment variables; load `.env` with your shell or process manager.
Tunable conversation rules (burst window, silence timeout, re-ask counts, whether "take" asks who)
live in `backend/geniai/domain/rules.py`; the ones marked `OWNER-UNCONFIRMED` still await the owner's
confirmation.

## Frontend

In `frontend/`, with the backend running:

```sh
npm install
cp .env.example .env.local       # BACKEND_URL, e.g. http://127.0.0.1:8000
```

| Command | What it does |
|---|---|
| `npm run dev` | Development server on http://localhost:3000 |
| `npm run build` then `npm start` | Production build and server |
| `npm run api:types` | Regenerate `src/lib/api-schema.ts` from `../backend/openapi.json` |

Log in with `BOARD_USER` and `BOARD_PASSWORD` from the backend's environment.

## Tests

| Where | Command | What it covers |
|---|---|---|
| `backend/` | `ruff check . && ruff format --check . && mypy geniai && pytest` | Lint, format, strict types and the pytest suite (domain, database, use cases, LLM contract, Chatwoot, HTTP API). Needs `TEST_DATABASE_URL`: an empty, dedicated database that the tests truncate |
| `frontend/` | `npm run check` | ESLint, `tsc --noEmit` and the Vitest suite (API client, formatters, login, board, indicators) |
| `frontend/` | `npm run e2e` | Playwright smoke across both services: starts the backend on the dev database and the frontend, logs in, drags a card, opens the indicators. First time: `npx playwright install chromium` |

A test also checks that the committed `backend/openapi.json` matches the API.

## Configuration

`.env` files are never committed; each service has a `.env.example` with placeholders.

**Backend (`backend/.env`)**

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` |
| `TEST_DATABASE_URL` | Empty, dedicated database for `pytest` |
| `PORT`, `HOST` | Where the service listens (the `uvicorn` flags take precedence) |
| `WEBHOOK_TOKEN` | Secret path segment of the webhook URL; at least 16 characters |
| `CHATWOOT_BASE_URL` | Chatwoot address, e.g. `https://chatwoot.example.com` |
| `CHATWOOT_ACCOUNT_ID` | Chatwoot account number |
| `CHATWOOT_API_TOKEN` | Chatwoot access token for API calls |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Any OpenAI-compatible chat completions endpoint |
| `LLM_EXTRA_BODY_JSON` | Optional JSON object merged into each LLM request (e.g. to turn reasoning off) |
| `BOARD_USER`, `BOARD_PASSWORD` | The team's shared login; the password needs at least 8 characters |
| `COOKIE_SECRET` | Signs the session cookie; at least 32 characters |
| `SECURE_COOKIE` | `true` behind HTTPS (default); `false` only for local http |
| `BURST_WINDOW_MS` | Optional: silence that closes a burst of messages into one turn |
| `SILENCE_TIMEOUT_HOURS` | Optional: silence that moves a triage ticket to "No response" |
| `EVAL_CANDIDATES` | JSON list of `{label, baseUrl, model, apiKeyEnv, extraBody?}` for the evaluation |

**Frontend (`frontend/.env.local`)**

| Variable | Meaning |
|---|---|
| `BACKEND_URL` | The backend's base URL, used by server rendering and by the `/api` proxy |

## Connecting Chatwoot

1. Create an Agent Bot whose webhook URL points to the **backend**:
   `https://<backend-host>/webhooks/chatwoot/<WEBHOOK_TOKEN>`, and attach it to the WhatsApp inbox.
   The webhook is not under `/api` and does not go through the frontend.
2. Create an access token for API calls and set `CHATWOOT_BASE_URL`, `CHATWOOT_ACCOUNT_ID` and
   `CHATWOOT_API_TOKEN`.
3. If the Agent Bot does not deliver conversation status changes, add an account webhook with the same
   URL and the `conversation_status_changed` event.

## Choosing the model

`python -m geniai.eval.run` runs 30 fictitious conversations against every candidate in
`EVAL_CANDIDATES`. It reports, per model: human-request detection (must be 100%), category and FAQ
accuracy, and p50/p95 latency, and saves the full result under `backend/eval-results/`. Each candidate
names the environment variable that holds its API key, so keys never appear in files. Run it from a
machine in Brazil so the latency matches production.

## Deploy notes

- Run the backend with **one worker process**: conversations are serialized per conversation in
  memory, and burst timers live in the process. Scale up the machine, not the worker count.
- The frontend reads `BACKEND_URL` **at build time** (for the `/api` proxy) and at start. Rebuild
  when it changes.
- Serve both services over HTTPS in production and keep `SECURE_COOKIE=true`.
- The backend migrates the database on start.
- Only the backend needs to be reachable by Chatwoot; only the frontend needs to be reachable by the
  team.

## Status and open items

The bot, the board and the indicators are implemented and tested, with fictitious data. Still open
(spec §13):

- FAQ content and the initial category list, written by the support team.
- The model choice, by the evaluation set.
- Confirming that the WhatsApp connector delivers the real phone number, not an internal id.
- Confirming which Chatwoot webhook carries conversation status changes.
- How the team loads and updates the attendant and unit base.
- Hosting and deploy.
- Known risk: a non-official WhatsApp connector can get the number banned.

## Data

The repository is public. It contains only invented data: no real phone numbers, unit names, people
or account ids.
