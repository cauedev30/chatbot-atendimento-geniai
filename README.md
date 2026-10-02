# chatbot-atendimento-geniai

GeniAI's WhatsApp support desk: a chatbot that runs as a Chatwoot Agent Bot, a kanban board for the
support team and an indicators page.

The bot identifies the customer by phone number, opens a ticket right away, tries **one** answer from
the team's FAQ, answers a few questions about it from that entry's knowledge base, and hands the
conversation to a person the moment one is asked for. One LLM interprets each customer turn; code
decides the flow. Every ticket lands on the board with a summary, a category and the unit, and feeds
the indicators: which problems happen most, how tickets get solved, and which units suffer most from
each problem.

- **Backend:** Python 3.12 · FastAPI · Pydantic · SQLAlchemy Core on asyncpg · PostgreSQL
- **Frontend:** React · Next.js (App Router) · TypeScript
- Design spec: [docs/specs/2026-09-23-single-agent-support-bot-design.md](docs/specs/2026-09-23-single-agent-support-bot-design.md)
- Architecture: [docs/architecture.md](docs/architecture.md)

## Features

**Bot (in WhatsApp, through Chatwoot)**

- Identifies the sender by phone number only (Brazilian numbers normalized, including the 9th
  mobile digit). An unknown number goes straight to a person and never gets the FAQ.
- Never answers a group, nor a contact without a phone number: those conversations go to the team at
  once, silently. A test mode (`BOT_ONLY_PHONES`) limits the bot to a list of phones.
- Greets the attendant by registered name and unit and asks for the problem; when the first message
  already describes it, only asks to confirm who they are and then uses that message.
- Until its first reply in the ticket, groups a burst of short messages ("oi" / "bom dia") into one
  turn (4 s of silence); after it, answers at once.
- Sends at most one FAQ entry, verbatim as the team wrote it; the LLM only writes the framing
  sentence. Then asks whether it solved the problem.
- Answers up to three questions about the entry sent, only from that entry's knowledge base, and asks
  again whether it solved the problem. A question the knowledge base does not answer, or a fourth one,
  goes to a person with the question in the ticket summary.
- Asks at most two clarifying questions, then summarizes and hands over.
- Hands over immediately on any request for a person, detected by keywords in code even if the LLM
  is down, and by the LLM.
- Reads the customer's images when `LLM_READS_IMAGES=true`: a photo or screenshot, alone or with a
  caption, counts as what the customer wrote. Up to four images per turn are sent to the LLM, which
  also describes each one; later turns and the ticket summary use that description. The image goes
  to the configured LLM provider and is never stored.
- Hears the customer's audios when `TRANSCRIBE_BASE_URL`, `TRANSCRIBE_API_KEY` and `TRANSCRIBE_MODEL`
  are set: an audio of up to 2 min is transcribed, at the start of the turn, by an OpenAI-compatible
  transcription endpoint set apart from the LLM's, and what the customer said counts as text for every
  rule (the greeting, a request for a person, the LLM). Each audio is transcribed once: the text is kept
  with the message, used by later turns and the ticket summary, and posted as a private note in the
  Chatwoot conversation for the team. The audio itself is never stored, and the text never goes to the
  log.
- Cannot open videos or files, nor an audio longer than 2 min or whose transcription failed (nor any
  audio with transcription off, nor images with image reading off). With text beside them, the LLM
  knows there was an attachment it cannot open; alone, the bot asks once for the problem in text, then
  hands over. It never says an attachment did not arrive nor asks for it again.
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
    db/          SQLAlchemy schema, SQL migrations, fictitious seed, FAQ file loader, CLI
    app/         use cases: inbound messages, turns, silence sweeper, board, indicators
    llm/         LLM contract (prompt, output schema, one-retry interpretation), OpenAI-compatible adapter
    chatwoot/    webhook parsing, HTTP client (messages, private notes, status) and image and audio download
    transcription/ OpenAI-compatible audio transcription adapter
    api/         FastAPI routers: auth, board, indicators, webhook; response models
    eval/        fictitious conversations, invented screenshots and the model comparison runner
    config.py    environment configuration
    main.py      the FastAPI app and its background work
  faq/faq.json   the FAQ: categories, entries and their knowledge bases (loaded with load-faq)
  tests/         pytest suite, mirroring geniai/
  scripts/       make_eval_images.py, which draws the evaluation screenshots (needs Pillow)
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
| `python -m geniai.db.cli create` | Create the database of `DATABASE_URL` when missing (used by the e2e run) |
| `python -m geniai.db.cli migrate` | Apply `geniai/db/migrations/*.sql` to `DATABASE_URL` |
| `python -m geniai.db.cli seed` | Load **fictitious** demo data (once; a second run does nothing) |
| `python -m geniai.db.cli load-faq faq/faq.json` | Load the FAQ file (see below) into `DATABASE_URL` |
| `python -m geniai` | Run the service on `HOST` and `PORT`. It migrates on start, reschedules turns left pending by a restart and sweeps silent tickets every 5 minutes |
| `python -m geniai.eval.run` | Run the evaluation set against the models in `EVAL_CANDIDATES` |
| `python -m geniai.export_openapi` | Rewrite `openapi.json` after an API change |

The service reads only environment variables; load `.env` with your shell or process manager.

**The FAQ** is edited in `backend/faq/faq.json` and loaded with `load-faq`; there is no screen for it
yet. The file has the category list (`key`, `system`, `name`) and the entries (`category`, `title`,
`applies_when`, `answer_text`, `knowledge_base`):

- `system` and `name` make the category label on the board and in the indicators ("system / name");
- `answer_text` is sent to the customer exactly as written;
- `applies_when` tells the LLM when the entry fits;
- `knowledge_base` (a list of `- ` lines, possibly empty) is the only source for answering questions
  about the entry sent. Leave out anything not confirmed: a question it does not answer goes to a
  person.

The command checks the whole file first and loads nothing if something is wrong (an empty field, an
entry whose category is not in the file, a repeated title or key). Then, in one transaction, it creates
or updates categories by `key` and entries by category and title, and deactivates the categories and
entries the file no longer lists; nothing is deleted. The key `other` renames the existing "Outros"
category and `unidentified` is reserved. Running it again with the same file changes nothing. It
prints how many entries and categories were created, updated, left unchanged and deactivated.

Run **one process with one worker**: the order of each conversation's messages and turns, and the
burst timers, are kept in memory. The service logs each request as a JSON line with the webhook token
masked; uvicorn's own access log is off because it would print the token. If you start uvicorn
yourself (`uvicorn geniai.main:create_app --factory`), pass `--no-access-log` and no `--workers`.
Tunable conversation rules (burst window, 4 s, silence timeout, re-ask counts, how many questions about
the FAQ entry are answered (`max_faq_questions`, 3), whether "take" asks who, the card summary's
30 s deadline, the audio limits: 2 min, 5 MB, 15 s to download and 15 s to transcribe) live in
`backend/geniai/domain/rules.py`; the ones marked `OWNER-UNCONFIRMED` still await the owner's
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
| `frontend/` | `npm run e2e` | Playwright smoke across both services: starts the backend on its own `geniai_e2e` database (never the dev one) and the frontend, logs in, drags a card, opens the indicators. The database is `E2E_DATABASE_URL`, or `DATABASE_URL` from `backend/.env` pointed at `geniai_e2e` with the same credential; it is created when missing, so that role needs `CREATEDB`. First time: `npx playwright install chromium` |

A test also checks that the committed `backend/openapi.json` matches the API.

## Configuration

`.env` files are never committed; each service has a `.env.example` with placeholders.

**Backend (`backend/.env`)**

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` |
| `TEST_DATABASE_URL` | Empty, dedicated database for `pytest` |
| `PORT`, `HOST` | Where `python -m geniai` listens (default `0.0.0.0:8000`) |
| `WEBHOOK_TOKEN` | Secret path segment of the webhook URL; at least 16 characters |
| `CHATWOOT_BASE_URL` | Chatwoot address, e.g. `https://chatwoot.example.com` |
| `CHATWOOT_ACCOUNT_ID` | Chatwoot account number |
| `CHATWOOT_API_TOKEN` | Chatwoot access token for API calls |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Any OpenAI-compatible chat completions endpoint |
| `LLM_EXTRA_BODY_JSON` | Optional JSON object merged into each LLM request (e.g. to turn reasoning off) |
| `BOARD_USER`, `BOARD_PASSWORD` | The team's shared login; the password needs at least 16 characters |
| `COOKIE_SECRET` | Signs the session cookie; at least 32 characters |
| `SECURE_COOKIE` | `true` behind HTTPS (default); `false` only for local http |
| `ENABLE_API_DOCS` | `true` serves `/docs`, `/redoc` and `/openapi.json`; off by default |
| `TRUSTED_PROXY_IPS` | Addresses or networks (comma-separated) of the frontend that proxies `/api`, whose `X-Forwarded-For` is believed; default `127.0.0.1,::1` |
| `BOT_ONLY_PHONES` | Optional test mode: comma-separated phone numbers the bot serves; any other conversation is handed to the team at once. Empty serves everyone. Each entry must be a Brazilian phone number |
| `LLM_READS_IMAGES` | `true` downloads the customer's images from Chatwoot and sends them to the LLM provider with the turn (the model must accept images); `false` (default) does not |
| `TRANSCRIBE_BASE_URL`, `TRANSCRIBE_API_KEY`, `TRANSCRIBE_MODEL` | Optional: any OpenAI-compatible `/audio/transcriptions` endpoint, apart from the LLM's. With all three, the customer's audios (up to 2 min) are downloaded from Chatwoot and sent to it, in Portuguese; with none, the bot says it cannot hear audio. Only some of them is a configuration error |
| `BURST_WINDOW_MS` | Optional: silence that closes a burst of messages into one turn, until the bot's first reply in the ticket; default 4000 |
| `SILENCE_TIMEOUT_HOURS` | Optional: silence that moves a triage ticket to "No response" |
| `EVAL_CANDIDATES` | JSON list of `{label, baseUrl, model, apiKeyEnv, extraBody?}` for the evaluation |

**Frontend (`frontend/.env.local`)**

| Variable | Meaning |
|---|---|
| `BACKEND_URL` | The backend's base URL, used by server rendering and by the `/api` proxy |
| `TRUST_UPSTREAM_PROXY` | `true` only when a reverse proxy in front of the frontend sets `X-Forwarded-For`; otherwise the frontend drops the `X-Forwarded-For` and `X-Real-IP` a client sends to `/api` |

## Login attempts

The browser reaches the backend through the frontend, so the backend takes the client address from
`X-Forwarded-For`, and only when the request comes from an address in `TRUSTED_PROXY_IPS`.

- **With a client address:** after 10 failed logins from one address within 15 minutes, the login
  answers `429` until the window passes; other addresses are not affected.
- **Without one:** the logins share one count and are never refused; each attempt waits 1 s per
  recent failure, up to 5 s. So a stranger's failures slow the team down but cannot lock it out.

The frontend adds no `X-Forwarded-For` of its own, and drops the one a client sends, so **the limit
per address needs a reverse proxy** in front of the frontend that sets or appends `X-Forwarded-For`
(nginx, Caddy and Traefik do by default). With one:

- set `TRUST_UPSTREAM_PROXY=true` in the frontend, so it passes the header on;
- set `TRUSTED_PROXY_IPS` in the backend to the frontend's address as the backend sees it. When the
  services run in separate containers, that is the frontend container's address (or its network),
  not `127.0.0.1`.

Without a reverse proxy, only the progressive delay applies.

## Connecting Chatwoot

1. Create an Agent Bot whose webhook URL points to the **backend**:
   `https://<backend-host>/webhooks/chatwoot/<WEBHOOK_TOKEN>`, and attach it to the WhatsApp inbox.
   The webhook is not under `/api` and does not go through the frontend.
2. Create an access token for API calls and set `CHATWOOT_BASE_URL`, `CHATWOOT_ACCOUNT_ID` and
   `CHATWOOT_API_TOKEN`.
3. If the Agent Bot does not deliver conversation status changes, add an account webhook with the same
   URL and the `conversation_status_changed` event.

With an Agent Bot on the inbox, Chatwoot keeps each new conversation `pending`, out of the team's
"Open" list, until the bot lets it go. So a conversation the bot does not serve is opened for the team
at once, with no reply and no ticket:

- **Groups are always passed to the team**, whatever the configuration. A group is recognized by a
  contact identifier or phone ending in `@g.us`, or by a contact without a usable phone number
  (`backend/geniai/domain/audience.py`; still to be checked against the real connector).
- **Test mode:** to try the bot on a real inbox without taking over every customer, set
  `BOT_ONLY_PHONES` to the test phones. Every other conversation goes to the team as above; a ticket
  already open keeps its flow. Leave it empty to serve everyone.

## Choosing the model

`python -m geniai.eval.run` runs 30 fictitious conversations, plus 8 questions about an FAQ entry
already sent, against every candidate in `EVAL_CANDIDATES`; a candidate with `"readsImages": true`
also gets 4 invented screenshots sent alone (`backend/geniai/eval/images/`, drawn by
`backend/scripts/make_eval_images.py`). It reports, per model: human-request detection (must be
100%), category and FAQ accuracy, how many questions it read right (answered only when the entry's
knowledge base has the answer), how many screenshots it read right (category and FAQ entry from the
image, with a description), and p50/p95 latency, and saves the full result under
`backend/eval-results/`. Each candidate names the environment variable that holds its API key, so keys
never appear in files. Run it from a machine in Brazil so the latency matches production.

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

The bot, the board and the indicators are implemented and tested, with fictitious data. The FAQ
content and category list are in `backend/faq/faq.json`. Still open (spec §13):

- The model choice, by the evaluation set; reading images counts in it (audio goes through the
  transcription endpoint).
- Confirming the content type Chatwoot serves for a WhatsApp voice message (`audio/ogg` is expected)
  and the transcription on the real inbox.
- Confirming the link Chatwoot sends for a WhatsApp photo (`data_url`) and that the download works
  on the real inbox.
- Confirming that the WhatsApp connector delivers the real phone number, not an internal id, and how
  it shows a group conversation.
- Confirming which Chatwoot webhook carries conversation status changes.
- How the team loads and updates the attendant and unit base.
- Hosting and deploy.
- Known risk: a non-official WhatsApp connector can get the number banned.

## Data

The repository is public. Apart from the FAQ file, which holds the support team's instructions, it
contains only invented data: no real phone numbers, unit names, people or account ids, here or in
the FAQ. The evaluation screenshots are drawn by a script, with invented screens.
