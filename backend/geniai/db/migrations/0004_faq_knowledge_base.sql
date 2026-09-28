-- What the bot may use to answer questions about the FAQ entry it sent (spec §5.1 step 5), and how
-- many of those questions a ticket already had answered.
ALTER TABLE faq_item ADD COLUMN knowledge_base text NOT NULL DEFAULT '';
ALTER TABLE ticket ADD COLUMN faq_questions_answered integer NOT NULL DEFAULT 0;
