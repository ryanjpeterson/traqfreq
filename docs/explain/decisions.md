# Decisions

## Log

### 2026-11-27 — P6: tables move whole into library.sqlite, read through views

- **Decision:** each cut-over owns whole jimbo-dj tables (and some `meta` keys), copied once into `TRAQFREQ_DATA_DIR/library.sqlite` with jimbo-dj's own `CREATE` statements and checked in the same transaction: row counts, no row different either way, jimbo-dj's numbers, the owned `meta` keys. Pages read through one connection, jimbo-dj's database read-only with `library.sqlite` attached read-only and a TEMP VIEW per owned table. The order is Ryan's: Plex scan and play log, history imports, analyzer, playlists, Fix in Plex, jobs and log, backups. jimbodj-text and the native analyzer stay as they are.
- **Why:** jimbo-dj writes one table from several places (its nightly sync also imports Plex plays and Last.fm and starts the MusicBrainz lookups; `listens` is one deduped table for every source), so only whole tables keep one writer. The same schema keeps every vendored reader working unchanged; a view in `temp` shadows jimbo-dj's table without touching the 45 places that check `sqlite_master`. In jimbo-dj, switching off comes before the copy, so no write falls between them.
- **Alternatives:** a new schema of traqfreq's own (every reader rewritten at once); splitting `listens` by source (dedupe crosses sources); moving the analyzer and text server into traqfreq (about two more sessions, nothing gained).
- **Consequences:** a second file to back up (cut-over 7). Until the analyzer and playlists cut-overs, jimbo-dj's frozen library means new music isn't analysed or in its mixes. A rollback renames the tables aside and reads go back to jimbo-dj's copy at once.

### 2026-11-26 — The Ask box makes a line from the nearest tracks' styles

- **Decision:** words become a line three ways (`src/traqfreq/ask.py`). Typed `facet:value` parts are used as they are. The other words go to jimbo-dj's CLAP text server and are compared with every analysed track's CLAP vector, as jimbo-dj's prompt Radio does; up to three styles that cover the 100 nearest tracks become the line, an OR. A local Ollama, only when set, reads the words into the library's own styles, moods and decades and drops the rest.
- **Why:** jimbo-dj at 1d8a7cb sends a prompt to Radio (a ranked list), not to a line, and has no Ollama code yet (its Ollama spec is "on spec, not built"). A line made of styles is something the Junction, the gate's rules and every count already understand, so the words end in something counted, explained and opened like any other line. Ollama never decides on its own: its line is checked against the library and shown like the others.
- **Consequences:** numpy is a dependency. jimbodj-text's `/embed` and Ollama's `/api/chat` are POSTs from traqfreq that read nothing; the only POST to jimbo-dj is still the gate script's preview. The Ask box's field is LineLever's new `field` mode, since K1 allows no twelfth component.

### 2026-11-26 — The P5 gate: only the script asks jimbo-dj

- **Decision:** `scripts/p5_gate.py` is the only caller of jimbo-dj's `POST /api/rules/preview` and `GET /api/saved`. `GET /api/playlists/compare` and the gate card show traqfreq's side: the ten trees with their numbers, the kinds of condition they use, the saved list. The fixed trees in `p5_trees.json` are written as jimbo-dj's builder writes them, so their URL form gives the same tree. The script also runs against a traqfreq from before T28.
- **Why:** the spec keeps every non-GET call to jimbo-dj in one place that runs only when asked. A tree with a top-level OR came back from the URL form wrapped in an AND; the same tracks, but not the same tree, so it is stored the way the builder makes it.
- **Consequences:** the card can't say "passed" on its own; HANDOFF records each run. The first live run (2026-11-26) used the before-T28 path against the deployed T27, whose Junction is the same code, and passed.

### 2026-11-25 — The in:mix: scope keeps what jimbo-dj's index knows

- **Decision:** `mixes.latest` is vendored unchanged at T27, replacing T24's stand-in. A mix's tracks count toward `in:mix:` only when jimbo-dj's vectors index knows them: analysed at the current analyzer version, status ok, with features.
- **Why:** the stand-in kept every live track with an ok analysis at any version, so a track analysed at an old version counted in traqfreq and not in jimbo-dj. The gate compares the two, and only jimbo-dj's rule can pass it.
- **Consequences:** the fixture's daily mix gives the same tracks either way (its unanalysed track was already left out); a scratch copy with an old-version track in the mix tests the difference. On live data, `in:mix:` lines can shrink by the tracks waiting for re-analysis.

### 2026-11-25 — Why this track: every condition of its line, met or not

- **Decision:** each picked track carries, per condition and group of the line that brought it in, whether it meets it (`met`), counted as the line's count is. The page shows them as true or false ConditionChips under the line's AND, OR and NOT parts, with the transition from the track before (jimbo-dj's `flow.describe`). StationRow's why now takes chips as well as a sentence.
- **Why:** B3 asks every row to say why it is there. A NOT condition is shown as false, which is why the track is in, so the part's words (NOT: none of these) are shown beside the chips.
- **Consequences:** no new kit component. The transition has no score of its own: jimbo-dj's describe gives Camelot steps and the tempo gap only, and traqfreq shows just those.

### 2026-11-25 — Rooted to roaming widens only style conditions, and only as a preview

- **Decision:** a line follows the tag of each `style` condition it needs (in its `all` or `any` parts, not under a `not`). Four stops widen that condition: rooted (the tag alone, the line as it is), ladder (the tags under it), movement (the tags of each movement naming one of those) and roaming (their neighbours on the genre map, one rung up or down, broad tags left out). Each tag is counted the way jimbo-dj counts a `style` condition. The slider is read-only and every line sits at rooted.
- **Why:** style names and TAGS' tag keys are the same words, so the widened line is still counted by jimbo-dj's own rule, and nothing vendored changes. A broad tag would take its whole line. Widening a NOT would shrink the line. `genre` conditions are Discogs genres, which aren't on the ladder.
- **Consequences:** the Junction's answers and the P5 gate don't move (`reach.py` only reads). Following a tag for real would need jimbo-dj's lines to change, so it waits for P6 or later.

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

### 2026-11-27 — Sessions run in a laptop clone; push to GitHub and Forgejo together

- **Decision:** edit and commit in `~/Development/traqfreq`; push with jimbo-deploy's `push.sh` to GitHub and Forgejo at once; Forgejo is a normal repo, not a pull mirror; the server checkout only pulls and deploys.
- **Why:** the jimbo-deploy standard (one rule for every app); the mini has no Forgejo credentials, so commits from the server checkout couldn't reach both; no SMB quirks.
- **Alternatives:** keep working in the server checkout with Forgejo as a pull mirror.
- **Consequences:** a push fails if either side is down (see jimbo-deploy Failover); supersedes the 2026-11-22 decision below.

### 2026-11-22 — Sessions run in the server checkout over SMB (superseded 2026-11-27)

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
