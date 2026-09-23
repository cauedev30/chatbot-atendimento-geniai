# chatbot-atendimento-geniai

Support chatbot for WhatsApp, running as a Chatwoot Agent Bot. One LLM agent identifies the customer
by phone number, opens a ticket, tries a single FAQ answer and hands over to a human whenever asked.
Every ticket lands on a kanban board with a summary, a category and the unit, and feeds an
indicators page (top problems, how tickets were solved, which units suffer most from each problem).

## Status

Design phase. No code yet.

- Design spec: [docs/specs/2026-09-23-single-agent-support-bot-design.md](docs/specs/2026-09-23-single-agent-support-bot-design.md)
