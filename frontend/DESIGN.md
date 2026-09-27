---
name: Suporte geniAI
description: Support desk board and indicators, built as a calm handover sheet on a near-black ground.
colors:
  bg: "#030606"
  surface: "#0b1413"
  surface-2: "#111d1c"
  line: "#182725"
  line-strong: "#557470"
  track: "#162422"
  teal: "#14c8b4"
  teal-hi: "#3ff0da"
  teal-soft: "rgb(20 200 180 / 0.1)"
  on-teal: "#021a18"
  text: "#eef4f3"
  text-2: "#a9bcb9"
  text-3: "#86a09c"
  danger: "#ff8a7a"
  danger-soft: "rgb(255 138 122 / 0.1)"
  gradient-teal: "#1fd1a8"
  gradient-cyan: "#1fb8e0"
  gradient-blue: "#2a8cf0"
  data-bot: "#199e70"
  data-waiting: "#c98500"
  data-progress: "#3987e5"
  data-human: "#d55181"
  data-silent: "#9085e9"
typography:
  figure:
    fontFamily: "Red Hat Display, Red Hat Text, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.15
    fontFeature: "tnum"
  headline:
    fontFamily: "Red Hat Display, Red Hat Text, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    letterSpacing: "0.01em"
  wordmark:
    fontFamily: "Red Hat Display, Red Hat Text, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
  wordmark-login:
    fontFamily: "Red Hat Display, Red Hat Text, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
  title:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
  summary:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  table:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  label:
    fontFamily: "Red Hat Text, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
rounded:
  mark: "4px"
  small: "6px"
  control: "8px"
  card: "10px"
  group: "12px"
  panel: "14px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "48px"
components:
  button:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "36px"
  button-primary:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-teal}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.teal-hi}"
    textColor: "{colors.on-teal}"
  button-quiet:
    textColor: "{colors.text-2}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "36px"
  button-quiet-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "36px"
  nav-link:
    textColor: "{colors.text-2}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "34px"
  nav-link-active:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
  ticket-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "12px 12px 12px 16px"
  details-sheet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    padding: "24px"
    width: "460px"
  segment:
    textColor: "{colors.text-2}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "34px"
  segment-active:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "32px"
  alert:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  state-tag:
    backgroundColor: "{colors.teal-soft}"
    textColor: "{colors.teal}"
    typography: "{typography.label}"
    rounded: "{rounded.small}"
    padding: "2px 8px"
---

# Design System: Suporte geniAI

## Overview

**Creative North Star: "The Calm Handover Sheet"**

The support desk reads like a sheet handed from one shift to the next: a near-black ground, loose cards one tonal step up with a hairline edge, and the same facts in the same place on every card. Nothing is boxed that does not need to be. Board columns are headings over a hairline, not panels; indicator sections are headings over their content, not cards. Teal is spent on what the person should act on or read first: the primary action, the queue that needs a person, counts and chart marks.

The system is dense but quiet. It stays open all day next to Chatwoot in a narrow window, so it ranks legibility and predictable placement over expression. One proportional family carries everything: Red Hat Text for the interface and prose, its Display cut for the wordmark, section headings and big figures. Corners are gently rounded (8px controls, 10px cards). Depth is tonal; shadows exist only on things that float above the page (the dragged card and the details sheet).

Confirmed rejections: neon, glow and bloom (owner, 2026-09-23).

**Key Characteristics:**
- Near-black ground, two surface steps, 1px hairlines in `line`, control borders in `line-strong`.
- Soft corners: 8px controls, 10px cards, 12px segmented groups, 14px standalone panels.
- One proportional family (Red Hat Text and Red Hat Display), sentence case, tabular figures for numbers.
- Teal marks the primary action, the lead queue, counts and single-hue charts; a five-hue palette is reserved for the board-column split.
- The brand gradient appears once per screen, as the 2px rule under the wordmark.
- Two authored motions: the details sheet slides in, and a card that lands in a new column is outlined in teal that fades.

## Colors

Teal on near-black with white type in three tones, one warm coral for errors, and a five-hue data palette that only ever paints chart marks.

### Primary
- **Signal Teal** (`teal`): the primary button, the lead column's rule and count, the selected tab's count, links, the "Espera mais longa" tag, single-hue chart marks (count bars, volume columns, median bars, FAQ progress, agent rings) and the heatmap fill.
- **Lit Teal** (`teal-hi`): primary hover, link hover, the focus ring, the caret, and the landing outline of a moved card.
- **Teal Wash** (`teal-soft`): a column's card area while a card is dragged over it, and the state tag on status pages.
- **Plate Ink** (`on-teal`): ink on a solid teal fill (primary buttons, text selection, strong heatmap cells).

### Secondary (data palette)
Five hues for the board's five columns in the "Onde os tickets estão" split bar and its legend swatches, in this order: **Bot Green** (`data-bot`, Resolvido pelo bot), **Queue Amber** (`data-waiting`, Aguardando humano), **Work Blue** (`data-progress`, Em atendimento), **Human Rose** (`data-human`, Resolvido por humano), **Silent Violet** (`data-silent`, Sem resposta). The set was validated as a dataviz palette on the dark ground. Work Blue is reused as the mean bar beside teal medians in the time chart.

### Neutral
- **Terminal Black** (`bg`): the page ground, the top bar (at 92% opacity), input fields, and the 2px gaps between heatmap cells.
- **Card Surface** (`surface`): ticket cards, the details sheet, the login and status panels, the segmented group and the category switcher.
- **Raised Surface** (`surface-2`): default buttons, the active nav link, the selected segment or tab, hover on quiet controls.
- **Hairline** (`line`): column-head rules, card and panel borders, table row dividers, stat dividers.
- **Control Edge** (`line-strong`): borders of buttons, selects and inputs (at least 3:1 on the ground and every surface), the volume chart baseline, the scrollbar thumb on hover.
- **Track** (`track`): the empty track of count bars, FAQ progress bars and agent rings. Set as a literal in the indicators stylesheet.
- **Paper White** (`text`): summaries, table values, figures.
- **Soft Grey** (`text-2`): column heads, nav links at rest, secondary facts, table captions.
- **Faint Grey** (`text-3`): labels, table heads, dates, notes, placeholders, empty-state lines.

### Error
- **Warning Coral** (`danger`) on **Coral Wash** (`danger-soft`), with a 1px coral border at 45%: refused actions and inline field errors, always with the backend's or the field's own message.

### Named Rules
**The Marks Carry the Color Rule.** Hue lives on chart marks, swatches and fills. Text stays in `text`, `text-2` and `text-3` (plus `teal` for links and counts), so no reading depends on a data hue.

**The Gradient Spent Once Rule.** The teal-cyan-blue brand gradient (`gradient-teal` to `gradient-cyan` to `gradient-blue`) appears once per screen, as the 2px rule under the "geniAI" wordmark. It never fills a surface, a button or text.

**The No Glow Rule.** Teal is matte. No text-shadow, bloom or blurred colored shadow. The landing outline is a zero-blur 2px ring that fades out, not a glow.

## Typography

**Display Font:** Red Hat Display (falls back to Red Hat Text, system-ui, sans-serif)
**Body Font:** Red Hat Text (with system-ui, sans-serif)

**Character:** One family in two cuts. Text does the work at small sizes; Display gives the wordmark, section headings and figures a slightly firmer shape without introducing a second voice.

### Hierarchy
- **Figure** (Display 600, 2rem, line-height 1.15, tabular): the four summary numbers on the indicators page. Agent-ring values use 1.75rem. Under 520px the summary figures drop to 1.625rem.
- **Headline** (Display 600, 1.375rem, 0.01em, teal): indicator section headings. 1.1875rem under 520px.
- **Wordmark** (Display 700, 1.125rem in the top bar, 1.5rem on login and status pages): "geniAI" only.
- **Title** (Text 600, 0.9375rem): board column heads; the details sheet's column name at 1rem; status page titles at 1.125rem 700.
- **Summary** (Text 500, 0.9375rem, line-height 1.45): card summaries, clamped to three lines. The details sheet shows it whole at 1.0625rem.
- **Body** (Text 400, 0.9375rem, line-height 1.5): prose and explanations (max 70 to 80ch).
- **Control** (Text 600, 0.875rem): buttons. Segments and tabs use 500.
- **Table** (Text 400, 0.875rem): indicator tables and the sheet's field list.
- **Label** (Text 500, 0.8125rem, `text-3`): field names, table heads, dates, notes.

### Named Rules
**The Sentence Case Rule.** Labels, buttons, nav and headings are written in sentence case with normal tracking. No uppercase, no monospace.

**The Type Holds Rule.** Narrow windows swap the board to one column and hide magnitude bars; body, label and table sizes never shrink. Only the indicator headline and summary figures step down under 520px.

## Layout

Spacing runs on a 4px base (4, 8, 12, 16, 24, 32, 48px). The top bar is sticky and 56px tall with a 1px bottom hairline; page padding is 24px, dropping to 16px by 12px under 520px.

**Board.** Five columns in a fixed order, 24px apart: Resolvido pelo bot, Aguardando humano, Em atendimento, Resolvido por humano, Sem resposta. Aguardando humano is 1.35 times the width of the others. The board fills the viewport under the top bar (minimum 420px) and each column scrolls on its own; cards sit 12px apart. Under 1040px of board width (a container query) the grid becomes one column and a category switcher appears above it; the page then scrolls instead of the columns. Under 1088px of viewport width the board drops its fixed height. Cards are containers too: under 320px of card width, unit, category and person each take their own line; wider, unit and category share a line joined by a middle dot.

**Details sheet.** A right-side dialog, `min(460px, 100vw)` wide and full height, over the dimmed board. 24px padding, 24px between its parts.

**Indicators.** One subject per row, always open, capped at 1200px and centered, 48px between subjects and 24px between a subject's heading block and its content. The summary strip auto-fits four stats (200px minimum), divided by hairlines; two per row under 520px. Wide tables scroll inside their subject.

Every control reaches 44px on coarse pointers.

## Elevation & Depth

Flat at rest. Depth comes from tonal steps (`bg`, `surface`, `surface-2`) and 1px hairlines. Shadows belong only to elements that float above the page.

### Shadow Vocabulary
- **Drag lift** (`box-shadow: 0 16px 32px rgb(0 0 0 / 0.5)`): the card preview that follows the pointer during a drag. The card left in place drops to 35% opacity.
- **Sheet cast** (`box-shadow: -24px 0 48px rgb(0 0 0 / 0.45)`): the details sheet, with a backdrop of `rgb(0 0 0 / 0.55)`.

### Named Rules
**The Only Floaters Cast Rule.** A shadow means the element floats over the page: the dragged card and the details sheet. Cards, columns, panels and tables never cast one at rest.

## Shapes

Gently rounded everywhere. Controls, nav links, inputs, segments and alerts use 8px; ticket cards 10px; segmented groups and the category switcher 12px (their inner segments 8px, inset by 4px); login and status panels 14px; small icon tools and tags 6px. Chart marks use 4px on their outer ends (split bar ends, volume column caps, time bar ends, legend swatches at 3px). Count bars, progress bars and ring strokes are fully rounded. The live indicator is an 8px dot. Icons are drawn on a 16px grid with a 1.5px stroke and round caps; the select chevron is an inline SVG in `text-3`.

## Components

### Buttons
Soft, bordered, sentence case.
- **Shape:** 8px radius, 1px `line-strong` border, 36px min height (44px on touch), 12px horizontal padding.
- **Default:** `surface-2` fill, `text` ink. Hover turns the border teal.
- **Primary:** teal fill and border, `on-teal` ink; hover moves to `teal-hi`. One primary per group (Assumir or Trocar, Sim, resolver, Entrar, recovery actions).
- **Quiet:** transparent, `text-2` ink; hover fills `surface-2` with `text` ink (Sair, Cancelar, Tirar responsável, the sheet's close button).
- **Disabled:** 0.55 opacity, not-allowed cursor.
- **Motion:** 140ms color, background and border transitions on the ease-out curve (`cubic-bezier(0.16, 1, 0.3, 1)`). None under reduced motion.

### Inputs / Fields
- **Style:** `bg` fill, 1px `line-strong` border, 8px radius, 36px min height. The label sits 6px above in Label type.
- **Hover:** border turns teal. **Focus:** the global 2px `teal-hi` outline with 2px offset.
- **Error:** inline under its own field: a coral alert box, `aria-invalid` on the field, and focus moves to the field. A refused choice always says why.

### Navigation
The sticky top bar holds the wordmark over its gradient rule, then text links in `text-2` at 0.9375rem 500, 34px tall with 8px radius. Hover fills `surface`; the current page fills `surface-2` with `text` ink. "Sair" is a quiet button pushed to the far end.

### Board Column
Not a box: a head row over a 1px `line` rule (name in Title type, count in `text-3`), then the column's cards. The lead column (Aguardando humano) has a teal rule, `text` name and a teal count. While a card is dragged over a column, its card area fills with `teal-soft`. Empty columns show one faint sentence.

### Ticket Card (signature)
A `surface` block with a 1px `line` border, 10px radius and 12px padding (16px on the left). Top to bottom: "Aberto …" date in Label type with, on the longest wait only, a teal 600 "Espera mais longa" tag; a 28px "Abrir no Chatwoot" icon tool at the top right; the summary; unit, category and responsible person in `text-2` (category in `text-3`, a missing person in italic); an "Exibir ações" toggle at the foot. Hover lifts the border a step.
- **Whole-card behavior:** the summary is a button whose hit area stretches over the card, so a click anywhere opens the details sheet; the focus ring draws around the whole card. Pointer dragging starts from anywhere on the card except its controls; a preview of the card's face follows the pointer. There is no grip handle and no keyboard drag: keyboard users move tickets with "Mover para".
- **Longest wait:** first in its column, with a teal border at 45% (70% on hover) and its tag. No fill change.
- **Landed:** a card that lands in a new column starts with a `teal-hi` border and a 2px zero-blur ring that fade over 1200ms. Reduced motion keeps the teal edge and drops the fade.

### Ticket Actions
One component, the same options in the same order on the card (under "Exibir ações") and in the details sheet, separated from the card body by a hairline: Responsável (select plus Assumir or Trocar, and "Tirar responsável", which returns the ticket to Aguardando humano), Categoria (select plus Corrigir), Mover para (select plus Mover). Each row is a select beside its button. On open tickets, "Resolver ticket" sits apart below a hairline and asks for inline confirmation (a sentence, then "Sim, resolver" as primary and "Cancelar" as quiet, focus on the confirm button).

### Details Sheet
A modal `<dialog>` docked to the right: `surface` fill, a 1px `line` left edge, the sheet cast shadow, and a 200ms slide-in from 24px (none under reduced motion). Head: ticket number in Label type over the column name; a quiet 36px close button. Then the full summary, a field list (9rem label column, hairlines between rows, tabular dates), a teal "Abrir no Chatwoot" link, and the Ticket Actions under a small "Ações" section title.

### Category Switcher (narrow board only)
A `surface` group with a 1px hairline and 12px radius, holding one button per column (36px, 500 weight, `text-2`). The selected one fills `surface-2` with `text` ink and a teal count.

### Indicator Section
No box and no rule: a teal Headline, a grey note under it (`text-3`, max 80ch), then the content 24px below. Each section has its own chart form, and every value is also readable as text:
- **Split bar** (Onde os tickets estão): one 24px bar split into the five columns with 2px gaps, colored by the data palette, over a legend table with swatches, counts and shares.
- **Count tables** (handoffs and other rankings): ranked rows whose count cell carries a 6px rounded teal bar on a `track` track, scaled to the table's largest count. Bars hide under 520px, and multi-value rows stack with labeled values.
- **Volume:** a segmented filter (week, month, unit, category). Week and month show a column chart (220px tall, 24px columns with rounded caps, count on the cap, period under a `line-strong` baseline); unit and category show count tables.
- **Heatmap** (Unidade × categoria): cells filled with teal by value; strong fills switch the ink to `on-teal` 600 so contrast holds. A link toggles absolute and per-agent values.
- **Paired bars** (time): per measure, a teal median bar and a blue mean bar, 12px tall, on one shared scale, with a key above.
- **FAQ progress:** an 8px rounded bar per item (track = every send, fill = sends that solved it) with its text below.
- **Agent rings:** 88px rings with an 8px stroke, teal arc on a `track` circle, value in Display 1.75rem beside the label and note.
- **Empty data** shows one faint sentence, never a table of zeros.

### Segmented Filter
A `surface` group with a 1px hairline, 12px radius and 4px padding; segments are 34px, 16px padding, 8px radius, `text-2` at rest, `surface-2` with `text` ink when pressed.

### Summary Stat
A Label in `text-2`, a Figure in `text`, and a note in `text-3` that says what the number counts. Stats are divided by hairlines, not boxed.

### Status Panel
Login, not-found, error and backend-down pages: a centered `surface` panel (14px radius, 1px hairline, 32px padding) under the 1.5rem wordmark. Status pages open with a small state tag (`teal-soft` fill, teal ink, 6px radius: "404", "Sem conexão", "Erro"), a bold title, a short `text-2` explanation, and one primary recovery action.

## Do's and Don'ts

### Do:
- **Do** keep controls at 8px and cards at 10px radius, with 1px `line` hairlines and `line-strong` control borders.
- **Do** reserve solid teal for the primary action and for single-hue chart marks; mark the lead queue with its teal rule and count.
- **Do** keep the five data hues on chart marks and swatches only, in column order.
- **Do** give every chart a table or text equivalent, and every count a note of what it counts.
- **Do** keep the same card fields in the same order on every card, and the same actions in the same order on the card and in the sheet.
- **Do** show field errors inline under the field, with `aria-invalid`, and move focus there.
- **Do** keep "Mover para" on every ticket, so no move depends on dragging.
- **Do** switch the board to one column with the category switcher under 1040px, and keep type sizes unchanged.
- **Do** give every control a 44px target on coarse pointers and a 2px `teal-hi` focus outline.

### Don't:
- **Don't** add glow, bloom, neon text-shadow or blurred colored shadows to teal.
- **Don't** use the brand gradient anywhere except the wordmark rule, once per screen.
- **Don't** box board columns or indicator sections; headings and hairlines mark where they start.
- **Don't** cast shadows at rest. Only the dragged card and the details sheet float.
- **Don't** set text in a data hue, or use a data hue outside a chart.
- **Don't** use uppercase labels or monospace type.
- **Don't** invent time thresholds or color bands for waits.
- **Don't** show real customer phones, unit names or people; only the fictitious seed data.
