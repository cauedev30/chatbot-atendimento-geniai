-- The last customer message a turn has read. A message stored while a turn is running comes after it,
-- so it stays pending for the next turn even when the turn's reply is stored later.
ALTER TABLE ticket ADD COLUMN last_consumed_message_id integer;
-- Existing tickets: every customer message before the last bot message was already answered.
UPDATE ticket SET last_consumed_message_id = (SELECT max(m.id) FROM triage_message m WHERE m.ticket_id = ticket.id AND m.author = 'customer' AND m.id < (SELECT max(b.id) FROM triage_message b WHERE b.ticket_id = ticket.id AND b.author = 'bot'));
