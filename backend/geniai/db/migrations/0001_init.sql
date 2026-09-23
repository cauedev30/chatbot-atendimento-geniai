-- Spec §7. Statements end with ";" at end of line (see splitStatements).
CREATE TYPE ticket_column AS ENUM ('in_triage', 'resolved_by_bot', 'awaiting_human', 'in_progress', 'resolved_by_human', 'no_response');
CREATE TYPE handoff_reason AS ENUM ('human_requested', 'faq_not_resolved', 'no_faq_match', 'unidentified', 'registration_mismatch', 'off_topic', 'media', 'llm_failure');
CREATE TYPE move_actor AS ENUM ('bot', 'human');
CREATE TYPE message_author AS ENUM ('customer', 'bot');

CREATE TABLE unit (
  id serial PRIMARY KEY,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE attendant (
  id serial PRIMARY KEY,
  phone_e164 text NOT NULL UNIQUE,
  name text NOT NULL,
  unit_id integer NOT NULL REFERENCES unit(id),
  active boolean NOT NULL DEFAULT true
);

-- Closed list, never deleted (deactivate instead). "key" marks the system categories code needs.
CREATE TABLE category (
  id serial PRIMARY KEY,
  key text UNIQUE,
  system text NOT NULL,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE faq_item (
  id serial PRIMARY KEY,
  category_id integer NOT NULL REFERENCES category(id),
  title text NOT NULL,
  applies_when text NOT NULL,
  answer_text text NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE team_member (
  id serial PRIMARY KEY,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE ticket (
  id serial PRIMARY KEY,
  attendant_id integer REFERENCES attendant(id),
  unit_id integer REFERENCES unit(id),
  phone_e164 text,
  "column" ticket_column NOT NULL,
  category_id integer REFERENCES category(id),
  bot_category_id integer REFERENCES category(id),
  handoff_reason handoff_reason,
  faq_item_id integer REFERENCES faq_item(id),
  faq_attempted boolean NOT NULL DEFAULT false,
  clarifications_asked integer NOT NULL DEFAULT 0,
  unclear_feedback_reasks integer NOT NULL DEFAULT 0,
  media_prompts integer NOT NULL DEFAULT 0,
  summary text NOT NULL DEFAULT '',
  responsible_id integer REFERENCES team_member(id),
  chatwoot_conversation_id integer NOT NULL,
  opened_at timestamptz NOT NULL DEFAULT now(),
  handed_off_at timestamptz,
  taken_at timestamptz,
  closed_at timestamptz,
  last_customer_message_at timestamptz NOT NULL DEFAULT now(),
  last_moved_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ticket_column_idx ON ticket ("column");
CREATE INDEX ticket_opened_at_idx ON ticket (opened_at);
-- At most one open ticket per Chatwoot conversation.
CREATE UNIQUE INDEX ticket_one_open_per_conversation ON ticket (chatwoot_conversation_id) WHERE "column" IN ('in_triage', 'awaiting_human', 'in_progress');

CREATE TABLE ticket_move (
  id serial PRIMARY KEY,
  ticket_id integer NOT NULL REFERENCES ticket(id),
  from_column ticket_column,
  to_column ticket_column NOT NULL,
  at timestamptz NOT NULL DEFAULT now(),
  actor move_actor NOT NULL
);

CREATE TABLE triage_message (
  id serial PRIMARY KEY,
  ticket_id integer NOT NULL REFERENCES ticket(id),
  author message_author NOT NULL,
  text text NOT NULL,
  is_media boolean NOT NULL DEFAULT false,
  at timestamptz NOT NULL DEFAULT now(),
  chatwoot_message_id integer UNIQUE
);

CREATE INDEX triage_message_ticket_idx ON triage_message (ticket_id);

INSERT INTO category (key, system, name) VALUES ('other', 'Geral', 'Outros'), ('unidentified', 'Geral', 'Não identificado');
