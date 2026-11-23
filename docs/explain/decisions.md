# Decisions

## Log

### 2026-11-23 — The file is the anchor for one song across servers

- **Decision:** match a Plex copy to Jellyfin and Navidrome by its path below the music folder, then MusicBrainz ID, then tags; no fingerprints.
- **Why:** all three servers read the same music folder on the Mac mini; paths are exact and need no audio.
- **Alternatives:** fingerprints (open the files), fuzzy title matching (wrong matches).
- **Consequences:** Navidrome must report real paths; files outside the folders need the tag tier.

### 2026-11-22 — Count every source in LIBRARY, beside jimbo-dj's Plex-only numbers

- **Decision:** LIBRARY's play history counts Last.fm, Spotify and Apple Music too (`plays_of`, never the sum), and keeps jimbo-dj's Plex-only fields labelled for the gate.
- **Why:** Plex alone misses most listening.
- **Alternatives:** match jimbo-dj exactly and nothing more.
- **Consequences:** two sets of numbers on one page, each saying whose it is.

### 2026-11-22 — Vendor jimbo-dj's counting code unchanged

- **Decision:** copy jimbo-dj's pure functions into `src/traqfreq/vendor/` with `VENDORED_FROM`, never edit them, give stand-ins for its config.
- **Why:** numbers must equal jimbo-dj's until each cut-over; jimbo-dj's repo is private, so no git dependency.
- **Alternatives:** rewrite the counting; depend on jimbo-dj's package.
- **Consequences:** re-copy when jimbo-dj changes; the gates catch drift.

### 2026-11-22 — Sessions run in the server checkout over SMB

- **Decision:** work on the laptop in `/Volumes/jimbos-sloppydrive/traqfreq`, with node_modules and venvs in a scratch copy.
- **Why:** gates and deploys use the same checkout; cloud containers can't reach the Mac mini.
- **Consequences:** SMB quirks (renames sometimes fail, no `sed -i`).

### 2026-11-22 — Build beside jimbo-dj, read-only, one module at a time

- **Decision:** a new app on :4492 that reads jimbo-dj's database read-only, proves each module equal (a gate), then takes over its writes (P6).
- **Why:** jimbo-dj is in daily use and its database holds about 11 hours of analysis.
- **Alternatives:** redesign jimbo-dj in place.
- **Consequences:** one writer at a time; two apps running until P8.

### 2026-11-22 — Berlin · Gelb, eleven components

- **Decision:** the Berlin · Gelb direction (yellow chrome, square module badges, Fira Sans), only eleven kit components, tokens and copy in one file each.
- **Why:** chosen from ten directions; a small kit keeps pages consistent.
- **Alternatives:** jimbo-ui; the nine other directions (to ship as skins in P8).
- **Consequences:** traqfreq doesn't follow jimbo-ui; brand rules are checked in CI.
