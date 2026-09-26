---
version: 1
slug: "src-app-board-page-tsx"
primary_target: "src/app/board/page.tsx"
related_targets: ["src/app/login/page.tsx","src/app/indicators/page.tsx","src/app/layout.tsx"]
---

# Support desk surfaces: login, board, indicators

Mode: Operate (all three surfaces).

Audience and job: the GeniAI support team (about two people, one shared login), board open all day beside Chatwoot in a narrow window. First glance: which tickets wait for a person. Then move, take, recategorize and close cards; read indicators by period and unit.

Owner constraints: brand colors stay (near-black + teal). Redesign 2026-09-24: the "terminal" look read as ugly and gamified. Wanted: simple, modern, pleasant to look at, useful, not over-worked. Board keeps five categories side by side, but no boxed column panels: cards sit loose under each category heading. The card shows, without clicking: summary, unit and category, responsible person, and when the ticket was opened (date and time, small), not the big wait figure. Indicators: a summary on top (3 to 4 key numbers, one main chart) and details below, collapsible.

## Direction contract

THESIS: The board is a shift-handover sheet: every ticket is a small filled-in record with the same fields in the same place, read at a glance. It refuses both the boxed terminal it replaces and the rounded, tag-colored kanban default.

OWN-WORLD: Near-black ground, cards one tonal step lighter with a hairline edge and a small radius (6px), no panels around columns. One proportional UI face for everything, tabular figures for numbers, sentence case, no tracked caps. Three text tones plus teal; teal only for the primary action, active nav, counts and the "Aguardando humano" marker. Raised from the depot blind: one change is one step, no gliding. Raised from the oscilloscope: one 8px grid. Raised from the modular identity: card, key number and table are the only three building blocks. Raised from the reference page: three text tones, one accent. Raised from the sneaker boxes: fields keep the same position on every card.

STORY: The agent sees who waits for a person, takes the ticket, answers in Chatwoot, closes it; later reads four key numbers and opens a detail only when needed.

FIRST VIEWPORT: Slim top bar (geniAI, Quadro, Indicadores, Sair). One quiet line: "N conversas com o bot agora". Five category headings in a row, each a label and a count, Aguardando humano first and widest with a teal marker. Loose cards below each heading; each column scrolls on its own. Card: "Aberto 23/09, 14:32" small on top, summary as the lead text, then Unidade, Categoria, Responsável on fixed rows; actions behind a small menu button. Narrow: category tabs.

FORM: shift-handover sheet, position 7 of 7 on the ordered list, seed key ca6689bb; code-led (no image generation). Signature interaction: a card moved by drag, menu or keyboard lands in its new column in one step and is briefly outlined in teal.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Refresh cadence stays 60 s; live push is out of scope.
