# Brand (summary)

Short form of the Brand guidelines page in the build prompt doc (version 2026.11.16). That page is the full text and wins on conflict. The Product rules outrank the brand rules (B1–B3).

**Idea:** the library is a city and the app is its transit map. Modules are lines, tracks are stations, and colour tells you which line you're on.

## Principles
1. Ink and paper: no gradients, shadows, glows or textures.
2. Colour means module, used as a splash only.
3. Status is shape: filled = ready, outlined = needs something, dashed = off, always with a word.
4. One system, many looks: a direction is a token file.
5. Show the network, and every drawing has a list view.
6. Touch first: 44 px targets, keyboard-operable.
7. Transparent by default: rows behind numbers, logged changes, preview before write.
8. Plain, stark words.

## Direction: Berlin · Gelb
Chrome `#F0D722`, chromeInk black. Square badges. Fira Sans, self-hosted. Nav top · fill, dense (page padding 24 px). Radius 2 / card 0.

| Module | Badge | Colour |
|---|---|---|
| LIBRARY (core) | L1 | `#E60012` |
| HISTORY | H2 | `#0079C2` |
| TAGS | T3 | `#00843A` |
| DISCOVER | D4 | `#7354C2` |
| MIXES | M5 | `#B0006E` |
| FETCH | F6 | `#6D4C2F` |
| SETUP | S0 | ink (paper text) |

Language loop: grey `#6B6A67` row in SETUP, no nav item.

**Dark mode marks (decided 2026-11-22):** MIXES (`#B0006E`) and FETCH (`#6D4C2F`) marks on dark grounds get a 1 px paper-coloured outline so they pass 3:1. The module colours don't change (C2). Filled bands and bullets with white text are unaffected.

## Rules (30; script-checked except K2, W3)
- **C Colour:** C1 only tokens, no literal colours/fonts/radii. C2 exactly seven module colours. C3 line colours mark modules only (never success/error/links). C4 text on a line colour is white, ≥ 4.5:1. C5 errors are ink + shape + sentence + next step (red is LIBRARY). C6 status = the Status component. C7 nav uses chrome/chromeInk; the current item may fill with its module colour.
- **T Type:** T1 at most two free typefaces. T2 module names one word in CAPITALS. T3 everything else sentence case. T4 labels 12 px, ink2. T5 body 14–15 px, nothing under 12 px.
- **L Layout:** L1 nav order LIBRARY, switched-on modules (HISTORY, TAGS, DISCOVER, MIXES, FETCH), SETUP, plus search. L2 an off module leaves no trace (dashed on the map). L3 phone: 76 px bottom bar of five. L4 tablet: compact top bar or 96 px rail. L5 desktop: one main column + at most one 320 px side column. L6 every drawing has a list view and a screen-reader summary.
- **K Components:** K1 only the eleven kit components: LineBullet, NavItem, Status, Band, Button, ConditionChip, LineLever, StationRow, Text, Card, ArtTile. K2 one ink button per view. K3 44 × 44 px targets. K4 real controls, aria-current, no clickable divs.
- **W Words:** W1 all copy from the strings file. W2 what happened, why, next step; no "!", emoji, "magic", "smart", "AI-powered", "oops". W3 numbers carry units and can show their source.
- **D Data:** D1 sample data never ships; empty states point to SETUP. D2 charts use their module's colour; two line colours only when comparing.
- **B Behaviour:** B1 every automatic change is in SETUP's activity log with reason and undo. B2 nothing writes to Plex, Jellyfin, Navidrome, files or slskd without a preview and confirm. B3 every playlist track shows which line brought it in and why.
