-- The files sent with a customer message, as a JSON list of {"kind", "url"?, "outcome"?, "description"?}:
-- kind is image, audio, video or file; url is Chatwoot's link; for an image, once an LLM turn read the
-- message, outcome (seen, failed, over_limit) and, when seen, the LLM's short description of it. A message
-- stored before this column has none (a media-only one keeps is_media and the "[mídia]" text).
ALTER TABLE triage_message ADD COLUMN attachments jsonb NOT NULL DEFAULT '[]'::jsonb;
