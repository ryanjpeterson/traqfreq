# T20–T23: TAGS, read-only (P4)

**Gate: ladders and per-track tags agree with jimbo-dj's tag rules on the real library.** On the live data, with `scripts/p4_gate.py --url http://macmini:4492` (T23; exit 0 = passed, recorded in HANDOFF as P1–P3 were):
1. **Ladders.** Every broad tag with albums under it has the same numbers in traqfreq's ladder as in jimbo-dj's families: albums under it, albums carrying it, albums missing it, and the same children with the same album counts. Checked twice: against jimbo-dj's rules run here (vendored `tags.Library.families()`) and against jimbo-dj's own stored run (`stats` row `library.tags`); a stored row that differs passes only when it is stale (built from an older data stamp), and the page says so. And every ladder from a tag ends at the broad tag jimbo-dj's rules give it.
2. **Per-track tags.** For every live track, traqfreq's tags equal jimbo-dj's per-track rule (`history._genre_tags`: the track's own Plex genres and its album's, through the rules, junk left out), and the styles the analyzer gives it equal jimbo-dj's strict test (`genres.Styles.sound_genres`, the tracks Explore's genre filter shows).
3. **The audit.** Every tag's numbers (albums, artists, tracks, MusicBrainz, sound, issues) and the album issue counts equal the stored `library.tags` (`tags`, `summary.issues`), same rule for stale rows.

TAGS only reads. Fix in Plex (album genre tags written to Plex, and with "the files too" the files' genre tags) stays in jimbo-dj until P6, with its preview, log and undo. traqfreq never writes to Plex, to jimbo-dj's database or to audio files, and never opens audio files (jimbo-dj's `file_tags` table is what it reads of them). No paid APIs: MusicBrainz is only what jimbo-dj cached.

## What jimbo-dj stores (read at jimbo-dj 1d8a7cb, `git show` only)
Source: `src/jimbodj/tags.py`, `tag_rules.json`, `genres.py`, `filetags.py`, `tagwrite.py`, `statcache.py`, `history.py` (`_genre_tags`, `_top`).

- **Plex's genres:** `albums.genres`, `artists.genres` and `tracks.plex_genres`, each a JSON list of the tag strings as Plex has them (`"Prog Rock"`, `"Pop, Rock"`, `"2010s"`). Track genres are what Plex read from the files' own tags (Plex keeps the first few). jimbo-dj's tags read **every** album and artist row, removed ones included, and live tracks only.
- **The files' genres:** `file_tags(rating_key, size, mtime, genres, read_at, error)`, every genre value in each live track's file (filetags.py, mutagen, nightly). May be missing (job never run).
- **MusicBrainz:** `mb_releases.genres` (release and release group merged) and `mb_artists.genres`, JSON `{genre: votes}`, rows with `status = 'ok'`.
- **The analyzer's styles:** `features.genres`, JSON `{"Rock---Punk": score}` (Discogs). `genres.Styles` merges them with MusicBrainz and Plex per track (noisy-or) under a strict test (a style needs metadata of its family behind it, or a sound score of 0.8 with no metadata against it); `sound_genres` = the Discogs styles each track keeps.
- **Fix in Plex's log:** `tag_edits` (per album: before, after, kinds, batch, applied, undone) and `tag_file_edits` (per file). Present only once a fix ran.
- **The stored audit:** `stats` row `library.tags` = `tags.Library.overview()`: `summary`, `fixes`, `suggestions`, `rules` (each rule with the tags and uses it changes), `families`, `tags` (every canonical tag), `kinds`. Its stamp (`tags.stamp`): `[MAX(mb_releases.fetched_at), MAX(mb_artists.fetched_at), meta last_sync, genres.version(), the rules file's mtime, filetags.stamp, tagwrite.stamp]`. `genres.version()` is a counter in jimbo-dj's process memory and the mtime is jimbo-dj's own file, so traqfreq compares the other five.

## jimbo-dj's tag rules (tags.py, tag_rules.json)
- **One tag becomes canonical tags** (`Rules.parse`), in order: split (`"Pop, Rock"`, `"Techno/Breaks"` → two), aliases and typos (`"Hip-Hop"` → `hip hop`, `"Prog Rock"` → `progressive rock`), rewrites (`"post punk"` → `post-punk`, `&` → `and`), aliases again, junk (decades, places, instruments, moods, notes, artist names, unless MusicBrainz knows the name as a genre), then Title Case with acronyms in capitals. The key is the lower-case canonical name; every spelling of one key is one tag.
- **Broad parents** (`Rules.broad`): the overrides first (`blackgaze` → Metal, `synth-pop` → Electronic, `soundtrack` → none, …), else the family `genres.family(key)` finds by regex (Metal, Punk & hardcore, Hip hop, Electronic, Jazz, Blues & soul, Folk & country, Classical, Reggae, Pop, Rock), named by `broad.families` (Punk & hardcore → Punk, Blues & soul → Soul, …). A broad tag's broad tag is itself. One broad tag per tag: jimbo-dj's hierarchy is two levels, flat (`families()`: each broad tag, its albums, those carrying it, those missing it, its children).
- **Issues per album** (Plex's album tags only): junk, split, spelling, case, broad (missing its broad tag), niche (one album or artist and unknown to MusicBrainz), untagged; each with the fix it would make (`op`: rename, remove, add).
- **Every source folded per album** (`Library._fold`): Plex album, Plex artist, track tags (share of tracks), file tags (share), MusicBrainz release and artist (votes), sound (share of analysed tracks with the style, from 0.4). Suggestions (`_recs`) are what the sources back that the album lacks (MusicBrainz votes with `genres._support`, half the tracks, or two sources agreeing), six at most.

## Reuse
Vendored unchanged at 1d8a7cb (T20), like T5's history functions:
- `vendor/jimbodj_tags.py`: tags.py from `RULES_PATH` to `tag_detail`, plus `_STAMP` and `stamp`. Not copied: `_lib`, `get` (jimbo-dj's background cache).
- `vendor/tag_rules.json`: byte for byte, beside the copy so `RULES_PATH` finds it (package data in `pyproject.toml`).
- `vendor/genres.py`: the constants, `_FAMILIES`, `_PARENTS`, `family`, `_loads`, `_votes`, `_support`. `Styles` stays a stand-in (no styles) until T21 vendors it; until then the tags carry no "sound" source.
- `vendor/filetags.py`: `by_album`, `stamp`, `status` only (they read `file_tags`). `vendor/tagwrite.py`: `stamp` only.

## The ladder (T20)
jimbo-dj gives each tag one broad tag. The ladder keeps that and adds the rungs in between, broad to specific, any depth, with shared parents: Metal → Black Metal → Atmospheric Black Metal; Death-Doom Metal under both Death Metal and Doom Metal.
- **Nodes:** every canonical tag in use (`Library.index`: album, artist or track tags), junk left out, plus each broad tag the rules name for them, in use or not.
- **Roots:** the broad tags. A tag whose rules give no broad tag (Soundtrack, Experimental) **stands alone**, said so.
- **Heads:** the shorter names inside a tag's name, as its head: drop leading words ("Atmospheric Black Metal" → "Black Metal", "Metal"), or keep one part of a hyphenated word ("Death-Doom Metal" → "Death Metal", "Doom Metal"), any number of times.
- **Parents:** the nearest heads in use **under the same broad tag** (a head that is a head of another candidate is not nearest); with none, the broad tag. A head under another broad tag is no rung (Post-Punk is Rock, so Punk is listed as "a name inside it under another broad tag", not its parent). So every ladder ends at jimbo-dj's broad tag, and the ladder never contradicts the rules: a broad tag's descendants are exactly jimbo-dj's family.
- **Rung:** 0 for a broad tag, else one more than its highest parent.
- **Numbers**, each opening its rows (W3): albums carrying a tag, artists carrying it, albums under it (carrying it or any tag below it); for a broad tag, albums missing it. Summary: tags in use, broad tags, deepest rung, tags with several parents, tags standing alone, junk tags; each opens its list.
- API: `GET /api/tags/ladder` (nodes, roots, alone, summary, rules, `check`; cached as `tags.ladder`, key = `LADDER_VERSION` + the five comparable parts of jimbo-dj's stamp), `GET /api/tags/albums?tag=&set=carries|under|missing&limit=&offset=`, `GET /api/tags/artists?tag=`. `check` = gate check 1, per broad tag: the ladder's numbers, jimbo-dj's (run here), jimbo-dj's stored, `matches`, and whether the stored row is fresh.
- Page `/tags` (module T, green): the summary, the agreement card, the ladder as nested station rows by broad tag (shared children appear under each parent, marked), tags standing alone. Rows pages `/tags/albums?tag=&set=` (each album opens LIBRARY's album page, with its Plex tags and the tags below that put it there) and `/tags/artists?tag=`, and `/tags/list?show=` (the tags behind a summary number).

## Sessions
### T20: the ladder
Spec (this file), vendoring, `src/traqfreq/tags.py`, the API and the TAGS page above. Fixture (`make_fixture.py` TAGS): invented Plex album, artist and track genres and MusicBrainz votes on the existing rows (no earlier count changes) covering three rungs, two parents, a missing broad tag, a misspelling, an alias, junk, a tag standing alone, a head under another broad tag, a track-only tag and the removed album; and a fresh stored `library.tags` trimmed to its families, worked out by hand.
### T21: albums tagged track by track
- Vendor `genres.Styles` (and what it needs) unchanged; the P2 gate's `genres` bars then come from it (check that P2 still passes: they stay not compared).
- Per track: its tags by source (its own Plex genres, its file's genres from `file_tags`, its album's and artist's Plex genres, MusicBrainz release and artist votes, the analyzer's styles kept by the strict test, with their scores), and jimbo-dj's per-track rule (`_genre_tags`) as the track's tags. Each tag on its rung of the ladder.
- An album page lists its tracks with their tags, so a track that differs from its album shows (an ambient intro on a black metal album: the fixture's Westkreuz). Album tags from its tracks: a tag carried by at least `TRACK_SHARE` (0.5) of its tracks speaks for the album, as jimbo-dj's `_recs` reads it.
- API `GET /api/tags/album/{key}`, `GET /api/tags/track/{key}`; LIBRARY's album and track pages link to them. Gate check 2's comparison in the API.
### T22: the proposals inbox (shown, not written)
- Every album's proposed change, from jimbo-dj's audit (`Library.albums`: issues with their fix, suggestions with their sources and votes, `proposed`), before and after, the way Fix in Plex's preview shows it (`tagwrite.proposal`, vendored unchanged: pure). Grouped like jimbo-dj's `fixes()` and `suggestions()`, each count opening its albums.
- Ladder proposals, traqfreq's own and labelled as such: an album carrying a tag but not its parents (Atmospheric Black Metal without Black Metal).
- Nothing is applied: the inbox says Fix in Plex is in jimbo-dj until P6, and links there. No accept buttons that write; any choice made here is kept only in traqfreq's own database, if at all, and never sent.
- Gate check 3's comparison (tags rows, issue counts, fixes, suggestions) against the stored row.
### T23: genre pages, the genre map, the gate
- A page per tag (`/tags/tag/<key>`): its ladders up to the broad tag, its children, its spellings and the rules that made it, its albums, artists and tracks, its plays (HISTORY's counted plays of the tracks carrying it, jimbo-dj's Top genres rule), its sound.
- The genre map: the whole ladder drawn as lines like the map home (CSS from `LineBullet`s, a visually hidden summary, L6), one line per broad tag.
- Movements defined: a movement is a named set of tags across broad tags (Blackgaze with Shoegaze, say), read from a data file in traqfreq's repo (`src/traqfreq/movements.json`), shown on the map and on each tag's page; it changes no ladder and no count.
- `scripts/p4_gate.py --url` (GET only, `--json`; exit 0 passed, 1 not passed, 2 can't run), `GET /api/tags/compare`, the gate card on SETUP and TAGS. Run on the deployed app.

## Not in P4
Writing tags anywhere (Fix in Plex, file tags, MusicBrainz): P6. Editing tag_rules.json from the page: P6, with the rules then owned by traqfreq. Playlists from tags: P5.
