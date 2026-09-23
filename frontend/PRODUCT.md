# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Two services against one PostgreSQL database (owner decision, 2026-09-23):

- **Backend:** Python + FastAPI (`../backend/`). Owns the Chatwoot webhook, the bot, the database and the JSON API under `/api`.
- **Frontend:** React + Next.js (App Router) + TypeScript (this folder). Renders login, board and indicators; proxies `/api/*` to the backend so the browser sees one origin.

## Users

The GeniAI support team: about two people sharing one login. They answer customers inside Chatwoot and use this app to see and move tickets and to read indicators. The board stays open the whole working day, side by side with Chatwoot on the same screen, so it often lives in a narrow window. It must still work on a phone.

## Product Purpose

Every WhatsApp support conversation becomes a ticket. The bot resolves known problems with a single FAQ answer, or hands the conversation to a human. The board shows where every ticket is. The indicators show the most frequent problems, how tickets get solved, and which units suffer most from each problem.

Success: the team always knows which tickets wait for a person, takes them quickly, and can see where the FAQ and the bot fall short.

## Positioning

A support desk built around one bot rule: the bot tries one FAQ answer at most and hands over the moment a person is asked for; the code, not the model, decides the flow. The board and indicators are the team's view of that loop, not a generic helpdesk.

## Operating Context

- Customers are staff at client units, identified by phone number; unknown numbers go straight to a person.
- The team works inside Chatwoot; each card links to its Chatwoot conversation ("Abrir no Chatwoot").
- Board columns: Resolvido pelo bot, Aguardando humano, Em atendimento, Resolvido por humano, Sem resposta; plus a counter of conversations still with the bot.
- Actions on a card: drag between columns, Assumir (choose who takes it), Categoria (correct the category), Fechar.
- Indicators: six blocks — volume, resultados, unidade × categoria, tempo, saúde do FAQ, saúde do agente — filtered by period and unit.

## Capabilities and Constraints

- Surfaces: login, board, indicators. All three are task surfaces (Operate).
- All UI copy is Brazilian Portuguese.
- Desktop-first, but the board shares the screen with Chatwoot most of the day: layouts must hold up in a narrow window, and work on a phone.
- One shared login (session cookie from the backend).

## Brand Commitments

Binding, from the owner's brand image (hex values approximate, sampled by eye):

- Near-black background (~`#030606`).
- Deep teal shadows (~`#0a2f2c`).
- Luminous teal/aqua as the signature accent (~`#14c8b4`, highlights ~`#3ff0da`).
- A teal → cyan → blue gradient (~`#1fd1a8` → `#1fb8e0` → `#2a8cf0`) for emphasis.
- White type.
- No logo. The wordmark is written "geniAI".

## Evidence on Hand

Only the fictitious seed data (`../backend/geniai/db/fixtures.py`): units "Unidade Exemplo …", people "… Exemplo", phones `+55119000000xx`. No real customers, units or people may appear in the UI, screenshots or docs. No testimonials, metrics or client names exist, and none may be invented.

## Product Principles

1. The ticket waiting for a person is the most important thing on screen.
2. The board reflects the server's truth; a refused action says why, in the backend's words.
3. Indicators are honest: "no response" is never counted as a bot success, and every chart has a readable table or text equivalent.
4. Nothing on screen may expose real customer data.

## Accessibility & Inclusion

No specific need known in the team. Standard: WCAG 2.2 AA — contrast, full keyboard use (including moving cards), screen-reader labels.
