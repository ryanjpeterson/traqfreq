# Decisions

## Log

### 2026-11-24 — Playlists live under LIBRARY, and the P5 gate asks jimbo-dj's preview

- **Decision:** the Junction (jimbo-dj's branch builder, Library → Tracks) and the saved playlists are pages under LIBRARY, not a module of their own. The P5 gate compares traqfreq's tracks with jimbo-dj's `POST /api/rules/preview` for the same tree. That endpoint builds a playlist and saves nothing. Only `scripts/p5_gate.py` calls it.
- **Why:** in jimbo-dj the builder is part of Library, and its conditions are Library's chart bars. A playlist's tracks depend on plays that change every day, so jimbo-dj's stored tracks can't be the answer; its own builder, asked now, can.
- **Consequences:** the three switches (Plex, Jellyfin, Navidrome) are read-only until P6. Jellyfin and Navidrome show as off because jimbo-dj has nowhere to keep them.

### 2026-11-24 — Movements live in a data file and change nothing

- **Decision:** a movement is a named set of tags across broad tags, kept in `src/traqfreq/movements.json` in traqfreq's repo (five to start). Each tag runs through jimbo-dj's rules. Movements are shown on the genre map and on each tag's page, and they change no ladder and no count: every tag keeps its own broad tag and its own numbers.
- **Why:** jimbo-dj's hierarchy is one broad tag per tag, and the P4 gate is agreement with it. A scene that crosses broad tags (Blackgaze: black metal and shoegaze) can only sit beside the ladder, not in it.
- **Alternatives:** movements as extra parents on the ladder (this would break check 1); movements in traqfreq's database, edited from a page (a write path in a read-only phase).
- **Consequences:** a change to the file needs a commit and a version bump. A movement's tags not in use are shown as such.

### 2026-11-24 — The P4 gate script reads the three checks' own endpoints

- **Decision:** `scripts/p4_gate.py` GETs `/api/tags/ladder`, `/api/tags/tracks/check` and `/api/tags/proposals` and judges them with `tags_gate.py`, which imports nothing else of traqfreq. `GET /api/tags/compare` runs the same code on the same answers for the gate card.
- **Why:** each check already has an endpoint and a page. Reading those endpoints means the gate runs against a traqfreq from before T23, and the gate can't disagree with the pages.
- **Alternatives:** one compare endpoint only, as in P3 (it can't run before the deploy).
- **Consequences:** check 3 stays strict (Ryan, 2026-11-24): a fresh stored row that differs fails, even when jimbo-dj's own background cache is the cause.

### 2026-11-24 — The proposals inbox shows jimbo-dj's proposals as jimbo-dj makes them, and labels traqfreq's own

- **Decision:** the inbox lists jimbo-dj's audit (issues with their fixes, suggestions, `proposed`) and Fix in Plex's preview through jimbo-dj's own code, vendored unchanged (`tagwrite.proposal`, `plan`, `Library.fixes`, `suggestions`), and adds traqfreq's own proposals beside them, labelled: a tag's missing ladder parents (below the broad tag, which is jimbo-dj's fix), and rule questions (a broad tag that rests on a word before the tag's last one). Nothing is applied, kept or sent; the inbox links to Fix in Plex in jimbo-dj.
- **Why:** P4 only reads, and the gate is agreement with jimbo-dj: showing its proposals through its own code keeps "before and after" exactly what Fix in Plex would do. traqfreq's ladder adds rungs jimbo-dj doesn't know, so their proposals are new, and must not pass as jimbo-dj's.
- **Alternatives:** accept buttons that queue changes for P6 (a store nobody reads yet, and a write path in a read-only phase); flag every tag whose name holds another broad tag's name (44 live, mostly jimbo-dj's deliberate choices like Punk Rock → Punk).
- **Consequences:** rule questions are narrow on purpose (live candidate: "Drill and Bass"); a ladder proposal can repeat one of jimbo-dj's suggestions (Death Metal on the fixture's Low Tide Radio), shown under both, labelled.

### 2026-11-24 — A track's tags are built from its sources, then checked against jimbo-dj's rule

- **Decision:** vendor jimbo-dj's `history._genre_tags` and `genres.Styles` unchanged, but build each track's tags in traqfreq from its own per-source breakdown (the album's Plex genres, then the track's, through the rules), and compare that with the vendored rule for every live track (gate check 2). The styles shown as kept are `Styles.sound_genres`, checked track by track.
- **Why:** the page has to show where each tag comes from, which jimbo-dj's rule doesn't say; building the tags from that breakdown and comparing keeps the page and jimbo-dj's rule from drifting apart.
- **Alternatives:** show only the vendored rule's answer (no sources); reimplement the strict test for styles (a second copy of jimbo-dj's code to keep in step).
- **Consequences:** the styles half of the check proves the plumbing (same tracks, same styles, same order), not an independent strict test; the P2 gate's `sound.genres` bars now come from the real styles and stay not compared.

### 2026-11-24 — The ladder adds rungs inside jimbo-dj's broad tags, never across them

- **Decision:** keep jimbo-dj's tag rules (tags.py, tag_rules.json, `genres.family`) vendored unchanged and build the ladder on them: a tag's parents are the nearest tags in use whose name is its head (leading words dropped, or one part of a hyphenated word kept), only under the same broad tag; with none, the broad tag. A head under another broad tag is shown, not made a rung.
- **Why:** P4's gate is agreement with jimbo-dj's tag rules: a broad tag's descendants must be exactly jimbo-dj's family, so the ladder can add depth (Metal → Black Metal → Atmospheric Black Metal) and shared parents (Death-Doom Metal under Death Metal and Doom Metal) without moving any tag to another family.
- **Alternatives:** a hand-written genre tree (a second set of rules to keep in step); MusicBrainz's genre relations (lookups traqfreq doesn't make); several broad tags per tag (contradicts jimbo-dj's Fix in Plex).
- **Consequences:** a few name heads are refused (Post-Punk isn't under Punk: it is Rock in jimbo-dj); tags whose names don't share words (Shoegaze, Blackgaze) meet only at the broad tag, until movements (T23) name them together.

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
