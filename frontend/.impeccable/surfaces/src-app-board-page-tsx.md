---
version: 1
slug: "src-app-board-page-tsx"
primary_target: "src/app/board/page.tsx"
related_targets: ["src/app/login/page.tsx","src/app/indicators/page.tsx","src/app/layout.tsx"]
---

# Support desk surfaces: login, board, indicators

Mode: Operate (all three surfaces).

Audience and job: the GeniAI support team (about two people, one shared login), board open all day beside Chatwoot in a narrow window. First glance must answer "who is waiting for a person, and for how long". Then move, take, recategorize and close cards; read indicators by period and unit.

Owner constraints (2026-09-23): no tiring neon or glow; not cramped; "appearance is the least of it, it just has to work" — function and legibility outrank expression. Brand colors from PRODUCT.md are binding; no logo, wordmark "geniAI".

## Direction contract

THESIS: The board is a service-counter terminal, not a kanban toy: one character grid, the waiting queue in front, time as the loudest number. It refuses the category default of equal-weight glowing columns of rounded cards.

OWN-WORLD: Near-black ground, deep-teal panels, matte teal type with no glow or bloom, white for content, 1px rules as the only chrome, square corners. One monospace for labels, times and counts (tabular figures); a proportional face for summaries. Emphasis is inverse video (solid teal plate, dark text): the longest wait is the one inverse card; every wait shows its own number, no invented time thresholds. Raised from the timetable rack: one type size per role family, rank by weight, case and inversion. Raised from the instrument six-pack: every count states its reference. Raised from the cyclorama: every state carries a text label, color never alone. Raised from the civic prospectus: the brand gradient is spent once, on the wordmark rule. Raised from the depot blind: narrow windows drop columns into tabs, type never shrinks.

STORY: The agent sees the longest wait first, takes it, answers in Chatwoot, closes it; later reads which problems and units hurt most.

FIRST VIEWPORT: Top bar: "geniAI" wordmark, Quadro / Indicadores, Sair. Under it one status line: "N conversas com o bot agora". Then the five columns in their fixed order; "Aguardando humano" is the widest and sorts its oldest wait first, inverse, the wait in large tabular digits; the other columns are narrower and quieter. Narrow: column tabs, Aguardando selected by default; each card also offers "Mover para" so moves work without dragging.

FORM: service-counter terminal (matte phosphor), position 7 of 7 on the ordered list, seed key 105ca8b5; build path code-led (no image generation). Signature interaction: keyboard-first card moves (arrow keys between columns) with a one-step settle, no glide.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Refresh cadence stays 60 s; live push is out of scope.
