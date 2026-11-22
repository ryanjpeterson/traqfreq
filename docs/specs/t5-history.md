# T5–T8: HISTORY, read-only (P1)

**Gate:** counts match jimbo-dj. Every HISTORY number traqfreq shows equals the number jimbo-dj shows for the same data, and each says which rule it uses (W3) and can show its rows.

traqfreq only reads. jimbo-dj keeps every history write (imports, dedupe, rematch, time zone setting) until HISTORY's cut-over in P6.

## How jimbo-dj counts (read at jimbo-dj 1d8a7cb)
Source: `src/jimbodj/history.py` (module doc, `dedupe`, `_overview`, `_plays`, `Names`), `statcache.py`, `schedule.py`.

- **Listens** (`listens`): one row per imported listen from Last.fm, Plex, Spotify, Apple Music. Unique on `(source, started_at, match_key)`. `started_at` is UTC epoch seconds.
- **Play** = `counted = 1`. jimbo-dj sets the flag after each import (`dedupe`); traqfreq reads it and never recomputes it. A listen that isn't a play is exactly one of:
  - too short: under 30 s (`counted = 0`, `dup_of IS NULL`);
  - repeat: the same source logged it twice within 30 s (`dup_of = source`);
  - duplicate: a source ahead in `PRIORITY` (Last.fm, Plex, Spotify, Apple Music) has the same play within its window (`dup_of` = that source).
  So plays + too short + repeats + duplicates = listens. `overview.adds_up` checks it on every read. **Nothing counts twice.**
- **Library track of a play:** `COALESCE(listens.rating_key, listen_matches.rating_key)`; NULL means not in the library. "Matched %" is plays with a track / plays.
- **Songs:** rows of `listen_matches` (distinct normalised artist|title heard); matched = those with a `rating_key`.
- **Time zone:** years, months, days, hours are in meta `history_tz`, else `TZ`, else America/Denver. traqfreq does the same (`Settings.tz` from `TZ`; compose sets `TZ`).
- **Names:** one name per artist, song and album however each source spelled it (`history.Names`: library spelling first, else the most played). Top lists count by these names.
- **Minutes:** `ms_played`, except Last.fm (track length) and Apple Music's daily summary (capped at the track length); no length at all: 225 s (`_minutes`).
- **A track's plays** elsewhere (Library, mixes): `max(Plex view_count, history plays)`, never the sum (`plays_of`).
- **jimbo-dj's own numbers** are stored as JSON in its `stats` table (`statcache.py`): `history.overview` (params `''`), `history.wrapped` (params `2025`, `2025-06`, `2025-06-14`), `library.stats`. They are rebuilt hourly and after imports, so they can lag the listens by up to an hour. traqfreq reads them as the comparison for the gate (`jimbodj` fields); when they differ, compare after jimbo-dj's next rebuild (`stats.stamp` = meta `history_version` when fresh).

## Reuse: vendored
jimbo-dj's repo is private, so a pinned git dependency would need credentials in CI and in the image. The pure functions are copied unchanged into `src/traqfreq/vendor/jimbodj_history.py` (constants, `band_of`, `norm_artist`, `norm_title`, `match_key`), with the commit they came from. `tests/test_vendor.py` checks them against the match keys jimbo-dj stored. Anything else T6–T8 need (`Names`, `_minutes`, period ranges) is vendored the same way, never rewritten.

## Sessions
### T5 (done): schema, counting rules, first read API
- Fixture and `legacy.KEY_TABLES` match jimbo-dj's real schema (`tracks` by `rating_key` with `removed_at`, `albums`/`artists` by key, `analysis`, `features`, `listens`, `listen_matches`, `history_imports`, `stats`). Invented rows chosen so each rule differs from a raw count.
- `/api/legacy/summary` adds `measures`: tracks, albums, artists, plays, each with its SQL rule, jimbo-dj's stored value and `matches`. `counts` (raw rows) stays. SETUP shows both.
- `GET /api/history/overview`: plays, listens, the three non-play reasons, `adds_up`, matched plays, songs, per source (in PRIORITY order) and per year (in the listening time zone), rules, jimbo-dj's stored plays.
- `GET /api/history/listens?status=play|too_short|repeat|duplicate&source=&year=&limit=&offset=`: the rows behind each number, newest first, with the rule and its parameters.

### T6: the HISTORY page
- Module H page (shown when `TRAQFREQ_MODULES` has H): plays headline, sources table (listens, plays, too short, repeats, duplicates of whom), years list with plays per source, matched %, time zone. Every number has a note with its rule and opens its rows (`/api/history/listens`, paged).
- A "Compared with jimbo-dj" line: same / differs (jimbo-dj's stored value and when it was built).
- Kit only (K1), copy in `strings.json` (W1); phone and tablet layouts; Vitest.
- If the overview is slow on 350,953 listens (Python loop over plays for years), cache it in memory keyed by meta `history_version` and the time zone.

### T7: top lists and hours
- Vendor `Names` and `_minutes`. Hours per year and total, top artists all-time (jimbo-dj: 15), on this day.
- `GET /api/history/top?kind=artists|songs|albums&period=all|30d|12m|YYYY|YYYY-MM`, matching jimbo-dj's `top_page` for plays (minutes sort after).
- Compare with `stats.history.overview` (`hours`, `top_artists`, `years[].hours`).

### T8: Wrapped and the gate
- A year, month or day of listening, matching `stats.history.wrapped` for every stored period.
- `GET /api/history/compare`: every stored jimbo-dj history number next to traqfreq's, with `matches`. The HISTORY page and SETUP show a one-line gate result.
- Gate run on the Mac mini (live data): all `matches` true, or each difference explained by a stale stored row. Record it in HANDOFF.

## Not in P1
Imports, dedupe, rematch, the time zone setting, Last.fm sync: all writes, P6. Library counts (P2) beyond SETUP's four measures.
