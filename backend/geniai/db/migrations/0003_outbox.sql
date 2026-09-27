-- Chatwoot calls to make (spec §10). Written in the same transaction as the ticket change that causes
-- them, then sent by the outbox worker in order per conversation; pending rows survive a restart.
CREATE TYPE outbox_kind AS ENUM ('message', 'status');
CREATE TYPE outbox_state AS ENUM ('pending', 'sent', 'failed');
CREATE TABLE outbox (
  id serial PRIMARY KEY,
  conversation_id integer NOT NULL,
  kind outbox_kind NOT NULL,
  payload text NOT NULL,
  state outbox_state NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  done_at timestamptz,
  error text
);
CREATE INDEX outbox_pending_idx ON outbox (id) WHERE state = 'pending';
