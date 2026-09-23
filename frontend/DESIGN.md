---
name: Suporte geniAI
description: Support desk board and indicators, built as a matte service-counter terminal.
colors:
  ink-0: "#030606"
  ink-1: "#061110"
  ink-2: "#0a2f2c"
  rule: "#173a36"
  rule-strong: "#2f6a63"
  teal: "#14c8b4"
  teal-hi: "#3ff0da"
  on-teal: "#021a18"
  text: "#f3f8f7"
  text-2: "#b3ccc8"
  text-3: "#7f9f9a"
  danger: "#ff8a7a"
  danger-ground: "#2a0f0c"
  gradient-teal: "#1fd1a8"
  gradient-cyan: "#1fb8e0"
  gradient-blue: "#2a8cf0"
typography:
  figure:
    fontFamily: "Red Hat Mono, ui-monospace, monospace"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.05
    fontFeature: "tnum"
  wordmark:
    fontFamily: "Red Hat Mono, ui-monospace, monospace"
    fontSize: "1rem"
    fontWeight: 700
    letterSpacing: "0.02em"
  wordmark-login:
    fontFamily: "Red Hat Mono, ui-monospace, monospace"
    fontSize: "1.5rem"
    fontWeight: 700
    letterSpacing: "0.02em"
  section-heading:
    fontFamily: "Red Hat Mono, ui-monospace, monospace"
    fontSize: "0.875rem"
    fontWeight: 700
    letterSpacing: "0.06em"
  body:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  table:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  meta:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
  label:
    fontFamily: "Red Hat Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    letterSpacing: "0.06em"
rounded:
  none: "0px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
components:
  button:
    backgroundColor: "{colors.ink-1}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "36px"
  button-hover:
    textColor: "{colors.teal-hi}"
  button-primary:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-teal}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.teal-hi}"
    textColor: "{colors.on-teal}"
  button-quiet:
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "36px"
  input:
    backgroundColor: "{colors.ink-0}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "36px"
  nav-link:
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    padding: "0 12px"
  nav-link-active:
    textColor: "{colors.teal}"
  column:
    backgroundColor: "{colors.ink-1}"
    rounded: "{rounded.none}"
  column-head-lead:
    backgroundColor: "{colors.ink-2}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    padding: "8px 12px"
  card:
    backgroundColor: "{colors.ink-0}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    padding: "12px"
  card-longest:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-teal}"
    rounded: "{rounded.none}"
    padding: "12px"
  column-switch-active:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-teal}"
    typography: "{typography.label}"
    height: "40px"
  alert:
    backgroundColor: "{colors.danger-ground}"
    textColor: "{colors.danger}"
    padding: "8px 12px"
---

# Design System: Suporte geniAI

## Overview

**Creative North Star: "The Service-Counter Terminal (matte phosphor)"**

The support desk reads like a terminal at a service counter: a character grid on a near-black ground, deep-teal panels, teal and white type with no glow or bloom. Chrome is limited to 1px rules. Corners are square throughout. Emphasis comes from inverse video, a solid teal plate with dark ink, and never from a new hue, a shadow or a bigger radius. Time and counts are the loudest things on screen, set in tabular monospace figures.

The system is dense but not cramped. It is built to stay open all day next to Chatwoot in a narrow window, so it ranks function and legibility over expression. The monospace carries every label, count, time and state name in small uppercase with wide tracking. A proportional face carries summaries, names and explanations. Indicators render as terminal printouts: tables are the primary view, thin teal bars show magnitude, and the heatmap runs from ground to teal in one hue.

Confirmed rejections: neon, glow and bloom (owner, 2026-09-23); equal-weight columns of rounded, glowing cards.

**Key Characteristics:**
- Near-black ground, two deep-teal panel steps, 1px teal-grey rules as the only chrome.
- Square corners everywhere (0px).
- Inverse video (teal plate, dark ink) is the single emphasis device.
- Monospace uppercase labels plus tabular figures for data; a proportional face for prose.
- The brand gradient appears once per screen, as the rule under the wordmark.
- One authored motion: a one-step settle when a card lands in a new column.

## Colors

A single-hue world: teal on near-black, with white for content and one warm red kept for errors.

### Primary
- **Signal Teal** (`teal`): the accent. Used for active nav, column counts, wait figures, links, primary buttons, magnitude bars, heatmap fill, and as the plate behind inverse-video emphasis.
- **Lit Teal** (`teal-hi`): hover state for teal elements, the focus ring, the caret, and the landing edge of a settled card. Never used as a resting fill for large areas.
- **Plate Ink** (`on-teal`): dark ink printed on any teal plate (the longest-wait card, the primary button, the active column tab, strong heatmap cells).

### Neutral
- **Terminal Black** (`ink-0`): the page ground, the top bar, card bodies and input fields.
- **Panel Teal-Black** (`ink-1`): columns, filter bar, login panel, action panels, default buttons, table-row hover.
- **Deep Teal Shadow** (`ink-2`): the lead column's header strip and the empty track of magnitude bars.
- **Rule** (`rule`): every 1px divider and panel border.
- **Strong Rule** (`rule-strong`): control borders (at least 3:1 on the ground and on the panels, so a field is findable), the lead column's border, section-heading underlines, the scrollbar thumb.
- **Paper White** (`text`): content: summaries, table values, figures in indicators.
- **Dim Teal-Grey** (`text-2`): secondary text: nav links at rest, column heads, notes.
- **Faint Teal-Grey** (`text-3`): labels, placeholders, empty-state lines, table column heads.

### Error
- **Warning Coral** (`danger`) on **Oxide Ground** (`danger-ground`): refused actions and login errors only, always as a bordered box with the backend's message.

### Named Rules
**The Inverse Video Rule.** Emphasis is a solid teal plate with dark ink. On the board exactly one card is inverted: the longest wait. Primary buttons and the active narrow-window tab use the same plate.

**The Gradient Spent Once Rule.** The teal-cyan-blue brand gradient (`#1fd1a8` to `#1fb8e0` to `#2a8cf0`) appears once per screen, as the 2px rule under the "geniAI" wordmark. It never fills a surface, a button or text.

**The No Glow Rule.** Teal is matte. No text-shadow, bloom or colored box-shadow on any teal element.

## Typography

**Display / Label Font:** Red Hat Mono (with ui-monospace, monospace)
**Body Font:** Red Hat Text (with system-ui, sans-serif)

**Character:** A monospace built for reading, paired with its proportional sibling. The mono makes the character grid; the text face keeps customer summaries readable at length.

### Hierarchy
- **Figure** (Mono 600, 1.75rem, line-height 1.05, tabular numbers): wait times, the bot-conversation counter, indicator totals. The largest type in the app.
- **Wordmark** (Mono 700, 1rem in the top bar, 1.5rem on login, 0.02em tracking): "geniAI" only.
- **Section heading** (Mono 700, 0.875rem, 0.06em tracking, uppercase, teal): indicator block headings, numbered to match the six indicator blocks.
- **Body** (Text 400, 0.9375rem, line-height 1.5): card summaries, explanations (max 70ch).
- **Table** (Text 400, 0.875rem): indicator table cells.
- **Meta** (Text 400, 0.8125rem): unit, responsible person, stat notes.
- **Label** (Mono 500 to 600, 0.75rem, 0.06em tracking, uppercase): field labels, column heads, buttons, nav, state names, "há 9 min" times.

### Named Rules
**The Rank Without Size Rule.** Rank comes from weight, case, color and inversion. The app has one large size (figure); everything else sits between 0.75rem and 1rem.

**The Type Never Shrinks Rule.** Narrow windows and phones drop columns into tabs and hide magnitude bars. They never reduce type size.

## Layout

Spacing runs on a 4px base (4, 8, 12, 16, 24, 32px). Page padding is 16px, 12px under 520px. The top bar is sticky, 48px tall, with a 1px bottom rule.

The board is a five-column grid in a fixed order. The "Aguardando humano" column is 1.5 times the width of the others and sorts its oldest wait first. Columns sit 12px apart, cards 8px apart inside 8px column padding. Under 1040px of board width (a container query), the grid collapses to one column and a row of column tabs appears, with "Aguardando" selected by default.

Indicators stack six blocks 32px apart, capped at 1280px wide. Tables inside a block auto-fit in a grid with a 340px minimum column. Under 520px of container width, magnitude bars are hidden, multi-value table rows stack (name on one line, labeled values below), and wide tables scroll inside their block.

Every control reaches 44px on coarse pointers.

## Elevation & Depth

The system is flat. Depth comes from tonal steps (ink-0 ground, ink-1 panels, ink-2 lead header) and 1px rules, never from shadows at rest.

### Shadow Vocabulary
- **Lift while dragging** (`box-shadow: 0 12px 28px rgb(0 0 0 / 0.55)`): only on a card while it is being dragged. It goes away when the card drops.

### Named Rules
**The Rules Are the Chrome Rule.** Panels, cards, tables and controls are separated by 1px borders in `rule` or `rule-strong`, never by shadows or background blur.

## Shapes

All corners are square (0px): buttons, inputs, selects, cards, columns, panels, alerts, bars and tabs. Icons are drawn on a 16px grid with a 1.5px stroke and square caps, so they match the 1px rules. The select arrow is a small CSS-drawn teal chevron. The details toggle is a rotated two-stroke caret.

## Components

### Buttons
Square, bordered, labeled in mono caps.
- **Shape:** square (0px), 1px `rule-strong` border, 36px min height (44px on touch), 12px horizontal padding.
- **Default:** `ink-1` fill, `text` ink. Hover turns the border teal and the ink `teal-hi`.
- **Primary:** inverse video: teal plate, `on-teal` ink. Hover goes to `teal-hi`. One primary action per group (Filtrar, Assumir, Entrar).
- **Quiet:** transparent fill and border, `text-2` ink (Sair).
- **Disabled:** 0.55 opacity, not-allowed cursor.
- **Motion:** 120ms color and border transitions on the settle curve. None under reduced motion.

### Inputs / Fields
- **Style:** `ink-0` fill, 1px `rule-strong` border, square, 36px min height. The label sits above as a mono caps label, 4px gap.
- **Hover:** the border turns teal. **Focus:** the global 2px `teal-hi` outline with 2px offset.
- **Error:** a coral bordered box on the oxide ground below the form. Fields do not turn red.

### Navigation
The sticky top bar holds the wordmark with its gradient rule, then mono caps links in `text-2`. The active link is teal with a 2px teal bottom border that sits flush with the bar's rule. "Sair" is a quiet button pushed to the far end.

### Board Column
A panel in `ink-1` with a 1px rule border and a header row: mono caps name on the left, teal count on the right. The lead column (Aguardando humano) has a `rule-strong` border and an `ink-2` header with white ink. While a card is dragged over a column, its border turns teal.

### Ticket Card (signature)
A square `ink-0` block with a 1px rule border and 12px padding. From top to bottom: a mono caps state label and the wait in large tabular teal figures (waiting cards) or a single "há N min" label (other cards); unit, then category in faint mono; the summary in body text; the responsible person in meta text; a ruled footer with "Abrir no Chatwoot" and an "Ações" disclosure. A 32px grip button (44px on touch) handles dragging. Every card also has "Mover para" in its actions, so no move depends on dragging.
- **Longest wait:** the one inverse card: teal plate, every inner text in `on-teal`, focus outline in `on-teal`.
- **Landed:** when a card lands in a new column it settles in one step (240ms, 6px drop, teal-hi edge). Under reduced motion the edge stays and the movement is dropped.

### Column Tabs (narrow only)
A strip of mono caps tabs joined by 1px rule gaps, 40px tall, each showing its count. The selected tab is inverse video.

### Indicator Table
Mono caps caption, faint mono column heads over a `rule-strong` line, 1px rule row dividers, right-aligned tabular numbers. Count cells carry a 6px bar: teal fill on an `ink-2` track. The heatmap fills cells with teal at an alpha set by the value. Strong fills switch the cell ink to `on-teal` so contrast holds. Empty data shows a faint mono sentence, never a table of zeros.

### Stat
A mono caps label, a figure in white, and a meta note that states what the number counts (for example, "de N tickets identificados…").

## Do's and Don'ts

### Do:
- **Do** keep every corner square (0px) and every separator a 1px rule in `rule` or `rule-strong`.
- **Do** mark emphasis with inverse video (teal plate, `on-teal` ink), and invert only the longest wait on the board.
- **Do** set times, counts and state names in Red Hat Mono, with tabular figures for numbers.
- **Do** give every state a text label. Color never carries meaning alone.
- **Do** make every count state what it counts, and show an honest empty message instead of zeros.
- **Do** switch to one column with tabs when the board is under 1040px wide, and keep type sizes unchanged.
- **Do** give every control a 44px target on coarse pointers and a 2px `teal-hi` focus outline.

### Don't:
- **Don't** add glow, bloom, neon text-shadow or colored shadows to teal.
- **Don't** use the brand gradient anywhere except the wordmark rule, once per screen.
- **Don't** round corners on cards, controls or panels.
- **Don't** use shadows at rest. The only shadow belongs to a card being dragged.
- **Don't** invent time thresholds or color bands for waits. Each card shows its own number.
- **Don't** add a second accent hue. Coral is for errors only.
- **Don't** show real customer phones, unit names or people; only the fictitious seed data.
