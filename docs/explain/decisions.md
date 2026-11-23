# Decisions

## Log

### 2026-11-23 — A Navidrome read counts only when no scan ran during it

- **Decision:** read every song through `search3` page by page, with `getScanStatus` before and after; store the read only when no scan ran (not scanning, the same `lastScan` and `count`), no song came twice and the distinct songs are the scan's own `count`. Otherwise the refresh fails, says why, and keeps the snapshot before.
- **Why:** Subsonic's `search3` has no sort order to ask for, so a scan can shift the pages under the read (T17 found a torn read live on Jellyfin); a snapshot with songs twice or missing would match wrongly.
- **Alternatives:** one `getAlbum` per album (thousands of requests); store the torn read with a warning.
- **Consequences:** a refresh during a scan has to be pressed again; live, the scan's count equals the songs listed (52,985).

### 2026-11-23 — Jellyfin's items don't depend on a user; play counts come from one named user

- **Decision:** the reader lists every audio item through `/Items` with the API key, and reads play counts separately from one user (`TRAQFREQ_JELLYFIN_USER`, by name or ID) through `/Users/{id}/Items?Filters=IsPlayed`; without a user there are no play counts.
- **Why:** an API key belongs to no user, so its play counts would be nobody's; reading the items through a user would drop the libraries that user can't see.
- **Alternatives:** read everything through `/Users/{id}/Items`; require a user.
- **Consequences:** one more paged request when a user is set; SERVERS says whose plays they are, shown beside traqfreq's, never added.

### 2026-11-23 — Servers are read with GET only, never retried, refreshed by hand

- **Decision:** one `httpx` client whose only verb is GET, with a timeout, no retries and no redirects; a snapshot is refreshed only when someone presses Refresh on SETUP, one at a time per server, and every refresh is logged with its counts or the server's own message.
- **Why:** traqfreq must never write to a server (B2), a failed read should be seen rather than hidden by retries, and a redirect could carry the key elsewhere.
- **Alternatives:** a scheduled refresh (a job to watch before P6); retries with backoff.
- **Consequences:** snapshots age until someone refreshes them (the page shows the age); a flaky server needs a second press.

### 2026-11-23 — Matching never guesses, and Plex borrows MusicBrainz IDs

- **Decision:** a tier that finds two candidates, or one candidate two copies want, stops with `ambiguous`; every unmatched copy and item gets exactly one reason. Plex copies have no track MusicBrainz ID, so for the `mbid` tier a copy uses the IDs of the item its file matched on the other server. Navidrome's music folder is the folder its real paths share (Subsonic names none).
- **Why:** a wrong match is worse than a missing one (transparent, W3), and the reasons must add up to the unmatched count.
- **Alternatives:** best-of-several by score; asking MusicBrainz (no lookups in P3).
- **Consequences:** some songs stay unmatched until their tags are fixed; a Navidrome library in one artist folder needs its folder set (`TRAQFREQ_NAVIDROME_ROOTS`, T18).

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
