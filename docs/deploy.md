# Deploy with Docker Compose

`deploy/compose.yaml` runs the whole system on one Linux host with Docker:

| Service | What it is | Port on the host |
|---|---|---|
| `db` | PostgreSQL 16, data in the named volume `db-data` | none |
| `backend` | `python -m geniai` (bot, webhook, API); migrates the database on start | `127.0.0.1:${BACKEND_HOST_PORT:-8010}` |
| `board` | the board (`next start`); `/api` goes to `backend` | `127.0.0.1:${BOARD_HOST_PORT:-3110}` |
| `tunnel-bot` | Cloudflare quick tunnel to `backend` (Chatwoot reaches the webhook through it) | none |
| `tunnel-board` | Cloudflare quick tunnel to `board` (the team opens the board through it) | none |

The two host ports listen on `127.0.0.1` only, for debugging over SSH
(`ssh -L 8010:127.0.0.1:8010 <host>`, then `http://127.0.0.1:8010/api/health`). The services talk to each
other over the project's own network; the tunnels only open outbound connections, so no port is opened
to the internet.

## Sharing the host

The compose file is written to live next to other projects without touching them:

- the project name is fixed (`name: geniai-atendimento`, and `-p geniai-atendimento` in every command),
  so every container, network and volume is prefixed with it; there is no `container_name`;
- no network or volume is `external`: the database, its volume and the network belong to this project;
- only the two ports above are published, on `127.0.0.1`. Before the first start, check they are free
  (`ss -ltnp | grep -E ':(8010|3110)\b'` prints nothing); if not, pick free ones in
  `BACKEND_HOST_PORT` and `BOARD_HOST_PORT`. Never reuse a port another project publishes.

## First start

Run every command from the repository root.

```sh
git clone <repository-url> geniai-atendimento && cd geniai-atendimento
cp deploy/.env.example deploy/.env && chmod 600 deploy/.env    # then fill it in
docker compose -p geniai-atendimento -f deploy/compose.yaml up -d --build
docker compose -p geniai-atendimento -f deploy/compose.yaml ps
```

`deploy/.env` holds the database credentials, the host ports, the board's `TRUST_UPSTREAM_PROXY` and every
backend variable (see the README, "Configuration"). Compose sets `DATABASE_URL`, `HOST` and `PORT` for the
backend itself. In that file, put a value that contains `$` between single quotes.

**Tunnel addresses.** A quick tunnel gets a new random `https://<words>.trycloudflare.com` address on every
start of its container:

```sh
docker compose -p geniai-atendimento -f deploy/compose.yaml logs tunnel-bot | grep trycloudflare.com
docker compose -p geniai-atendimento -f deploy/compose.yaml logs tunnel-board | grep trycloudflare.com
```

- Chatwoot's Agent Bot webhook: `https://<tunnel-bot address>/webhooks/chatwoot/<WEBHOOK_TOKEN>`.
  Update it whenever `tunnel-bot` restarts.
- The board: `https://<tunnel-board address>/login`.

With a domain on Cloudflare, a named tunnel (fixed address, token from the Cloudflare dashboard) replaces
the quick ones: `command: ["tunnel", "--no-autoupdate", "run", "--token", "${TUNNEL_TOKEN}"]`.

**The FAQ** is not loaded on start. After the first start, and after every change to
`backend/faq/faq.json` (which needs a rebuild of `backend`, since the file is in the image):

```sh
docker compose -p geniai-atendimento -f deploy/compose.yaml exec backend python -m geniai.db.cli load-faq faq/faq.json
```

## Login attempts

The backend limits failed logins per visitor address (README, "Login attempts"). Behind the tunnels:

- Cloudflare sets `X-Forwarded-For` on every request, appending the visitor's address as the rightmost
  entry (and `CF-Connecting-IP`, which the backend does not read). The backend takes the rightmost entry
  that is not a trusted proxy, so what a visitor writes in the header is never believed.
- `TRUST_UPSTREAM_PROXY=true` (board): the board passes that header on to the backend instead of dropping
  it.
- `TRUSTED_PROXY_IPS` (backend): the addresses of this project's containers, which are the peers the
  backend sees (the board for the board's logins, `tunnel-bot` for requests to the backend's address).
  The default in `deploy/.env.example`, `172.16.0.0/12,192.168.0.0/16`, covers Docker's private ranges.
  To trust only this project's network, use its subnet:
  `docker network inspect geniai-atendimento_default --format '{{(index .IPAM.Config 0).Subnet}}'`
  (it can change when the network is removed by `down`, so check it again after one).

A request through an SSH tunnel to a host port arrives from the Docker gateway with no forwarded address:
its failed logins are slowed down, never refused.

## Update

```sh
git pull
docker compose -p geniai-atendimento -f deploy/compose.yaml up -d --build
```

Only the rebuilt services restart; the backend applies new migrations on start. If `board` or `backend`
restart, the tunnels keep their addresses; if a tunnel container restarts, its address changes.

## Logs

```sh
docker compose -p geniai-atendimento -f deploy/compose.yaml logs -f --tail=200 backend
docker compose -p geniai-atendimento -f deploy/compose.yaml logs -f --tail=200 board
```

The backend writes one JSON line per request, with the webhook token masked.

## Database backup and restore

```sh
docker compose -p geniai-atendimento -f deploy/compose.yaml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > geniai-$(date +%F).dump

docker compose -p geniai-atendimento -f deploy/compose.yaml exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < geniai-YYYY-MM-DD.dump
```

The dump has customer data: keep it out of the repository and off shared folders.

## Stop

```sh
docker compose -p geniai-atendimento -f deploy/compose.yaml stop     # keeps everything
docker compose -p geniai-atendimento -f deploy/compose.yaml down     # removes containers and network, keeps the volume
```

Never `down -v` unless the database should be deleted. Before stopping the backend for long, take the bot
out of the Chatwoot inbox, or new conversations wait for it.
