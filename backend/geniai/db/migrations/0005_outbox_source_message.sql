-- The customer message that caused an outbox row, when the row stands in for a ticket: a conversation the
-- bot does not serve is handed to the team with no ticket and no stored message, so a repeated delivery
-- of that message is recognized by this column instead.
ALTER TABLE outbox ADD COLUMN chatwoot_message_id integer UNIQUE;
