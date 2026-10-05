-- The bot stays out of a conversation where the team wrote since it was last closed. This keeps when each
-- conversation was last resolved in Chatwoot, with or without a ticket open then (a conversation the team
-- handles alone has none), and adds the handoff reason of a ticket in triage the team replied to.
-- outbox.chatwoot_message_id also keeps, for a message row, the id Chatwoot gave the message the bot sent.
CREATE TABLE conversation_resolution (
  conversation_id integer PRIMARY KEY,
  resolved_at timestamptz NOT NULL
);
ALTER TYPE handoff_reason ADD VALUE 'team_replied';
