# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are CalVer (`YYYY.MM.N`).

## [Unreleased]
### Added
- T15: SETUP → SERVERS (`/setup/servers`; not a module of its own): the three servers with status and snapshot age (each server's column says when it has no snapshot), Plex's identity counts and issues, each pair's matches by tier and by reason (lists with SETUP-ink bars and a one-line summary, L6), and a song's three IDs (pick a copy: its Plex rating key, Jellyfin item and Navidrome song, with the tier or the reason). Every count opens its rows: `/setup/servers/copies` and `/setup/servers/matches`, each row saying why. SETUP gets a servers card.
- T15: LIBRARY's track page gains "On servers": the copy's item on each server, its tier, and each server's own play count, labelled; shown beside, never added to traqfreq's plays.
- T15: `GET /api/servers/matches?rating_key=`: one Plex copy's rows (its match or reason on each pair, and Jellyfin ↔ Navidrome matched through it), with `copy.live`.
- T14: server snapshots (`src/traqfreq/snapshots.py`): Jellyfin's `/Library/VirtualFolders` and `/Items` pages and Navidrome's `getScanStatus`, `getAlbumList2` and `search3` pages turned into one item shape (server, ID, path, hidden path, file key, title, artist, album artist, album, disc, track, duration, MusicBrainz recording and release, size, play count); a `snapshots` table in traqfreq's database (server, read at, stamp, folders, items; one row per server).
- T14: matching (`src/traqfreq/matching.py`, `GET /api/servers/matches?server=&tier=&reason=`): Plex ↔ Jellyfin, Plex ↔ Navidrome and Jellyfin ↔ Navidrome by file (then loose key, only when unique), MusicBrainz recording and release (a Plex copy borrows its file match's IDs on the other server) and tags (match key, album, disc and track, within 2 s, one candidate); one to one per server, two copies of one file sharing its item; every unmatched copy and item with one reason (`no_path`, `outside_roots`, `not_on_server`, `ambiguous`, `hidden_path`, `not_in_plex`, `multi_part`). Each count with its rule and its rows. Nothing is sent to any server.
- T14: fixture: invented Jellyfin and Navidrome answers (`scripts/fixture_jellyfin.json`, `fixture_navidrome.json`), loaded with `python scripts/make_fixture.py --snapshots <data dir>`; with T13's scratch problem copies they cover every tier and every reason. The legacy fixture is unchanged.
- `.env.example`: every setting by phase, the ones read now (P0–P3) and the ones later phases will need (P6–P8, with jimbo-dj's equivalents), secrets marked.
- T13: P3 spec (`docs/specs/t13-servers.md`): one song on Plex, Jellyfin and Navidrome; how jimbo-dj identifies a track; file key and match tiers; sessions T13–T19.
- T13: track identity, the Plex side (`GET /api/servers/identity`, `/api/servers/copies`): Plex's music folders and where they come from, every live copy's file key (path below the folder, NFC), loose key, song and match key, and its issues (no path, outside the folders, shared file, case clash, multi-part, no duration), each count with its rule and its rows.
- T13: `GET /api/servers`: Plex (through jimbo-dj's database), Jellyfin and Navidrome set up or not; new optional settings `TRAQFREQ_PLEX_ROOTS`, `TRAQFREQ_JELLYFIN_URL|KEY|USER`, `TRAQFREQ_NAVIDROME_URL|USER|PASSWORD` (secrets never shown), passed through by `docker-compose.yml`.
- P2 gate passed on live data: both stored LIBRARY rows (`library.stats` 23 fields, `library.charts` 37), 60 of 60 fields, equal jimbo-dj's.
- LIBRARY's play history counts every source, not Plex alone: played tracks and plays by `plays_of` (Plex's count or the history's per track, the larger, never both), plays by source (Last.fm, Plex, Spotify, Apple Music; a list with bars and a summary, each opening its tracks) and top artists from every source. jimbo-dj's Plex-only numbers stay beside them, labelled, for the P2 gate. `GET /api/library/stats` adds `plays_all`; `/api/library/tracks` adds `heard`, `source` and the order `plays`.
- T12: P2 gate: `scripts/p2_gate.py` (read-only, `--url` or `--db`; exit 0 = passed) and `GET /api/library/compare` put every field jimbo-dj stored in `library.stats` and the non-genre parts of `library.charts` (keys, files, time, place, sound) next to traqfreq's, with matches and whether the stored row is fresh. Folders, genres and styles are shown as stored, not compared.
- T12: `/library/compare`: every stored field, counts opening their rows, chart fields with their bars (jimbo-dj's next to traqfreq's), each bar opening its tracks; the gate card on LIBRARY and SETUP.
- T12: `/api/library/tracks` takes `facet` and `value`: the tracks behind one bar of jimbo-dj's Files, Time or Place charts, by its own `facets.members`; the rows page shows them ("Tracks · format FLAC").
- T12: vendored unchanged from jimbo-dj 1d8a7cb: insights.py's keys, files, time, place and `_all_views`, live.py's `distributions` (`vendor/jimbodj_insights.py`), facets.py's `members` (`vendor/jimbodj_facets.py`), with marked stand-ins (`schedule.tz`, `genre_view`, `vendor/genres.py`).
- T12: fixture: bit depth, sample rate, channels, stream size, artist places (`mb_artists`) and a stale stored `library.charts` row with one explained difference. T5–T11 counts unchanged.
- T11: album and artist lists (`/library/albums`, `/library/artists`; LIBRARY's album and artist counts open them): jimbo-dj's Library → Albums and Artists (`browse._grouped`) with tracks, plays (SUM of `plays_of`), newest added and year; ordered by plays or added (jimbo-dj's) or by name or year (traqfreq's). Each number opens its tracks.
- T11: album page (`/library/album/<key>`): tracks in disc and track order with plays, key and moods and how many copies of each song the library has; jimbo-dj's year (MusicBrainz's first release, else Plex's), Plex's year, release date and label, MusicBrainz as jimbo-dj cached it; its listens by source and year (lists with a summary, L6).
- T11: artist page (`/library/artist/<key>`; Plex top artists on LIBRARY open it): tracks, plays, albums oldest first (and ones it appears on), top songs (every copy's plays added up, jimbo-dj's `_top_songs`), listens by source and year.
- T11: track page (`/library/track/<key>`; every rows-page title opens it): plays (`plays_of`, with Plex's and the history's beside it), this copy's listens by source and year, the song's other copies and every copy's listens, file facts, jimbo-dj's analysis (status, version, key, BPM, loudness, moods).
- T11: listens page `/library/plays?track=|album=|artist=` (and `song`, `source`): the counted listens each history number above counts, newest first.
- T11: `GET /api/library/albums`, `/artists`, `/album/{key}`, `/artist/{key}`, `/track/{key}`, `/plays`, read-only.
- T11: vendored unchanged from jimbo-dj 1d8a7cb: `songs.py` (all but its background-cache `index`) into `vendor/jimbodj_songs.py`; from `pages.py` the track columns, `_track`, `_listens`, `_artist_where`, `_keys_where`, `summarise`, `resolve_artist`, `_library_of`, `_top_songs`, `resolve_album`, `_recent`, `insights._release_years` and `browse.GROUP_SORTS`/`_grouped` into `vendor/jimbodj_pages.py`, with marked stand-ins.
- T11: the kit's `StationRow` takes an optional `href` (the title becomes a link). The copy lint knows LUFS and EP.
- T11: fixture: disc numbers, Plex release dates and labels, a cached MusicBrainz release (`mb_releases`), key, scale and moods. T5–T10 counts unchanged.
- T10: LIBRARY page (`/library`, always on): tracks, albums, artists, playing time and size; codecs, containers and bitrate buckets as lists with LIBRARY-red share bars and a one-line summary (L6); Plex play history (played %, Plex plays, rated) and Plex top artists by key; Plex sonic analysis next to jimbo-dj's analyzer, each saying which it is; paths (mapped, not mapped with the first five, multi-part, removed) and music folders as jimbo-dj stored them, marked not compared. Every number shows its rule and opens its rows.
- T10: rows page `/library/tracks?…`: 50 tracks a page as `StationRow`s with key and BPM where jimbo-dj's analyzer finished, the rule and the plays rule, order by artist, Plex plays or newest added; the "why" line gives the file facts, analysis and plays (`plays_of`: Plex, history, the larger counts).
- T9 deployed: on live data all 48 compared fields of `/api/library/stats` equal jimbo-dj's `/api/stats`.
- T9: `GET /api/library/stats`: jimbo-dj's library numbers (its `library.stats`, vendored unchanged and run on the read-only connection): tracks, albums, artists, hours, size, codecs, containers, bitrate buckets, Plex play history and top artists, Plex sonic analysis, mapped and multi-part tracks, removed since the first sync. Each number carries its rule and the query that lists its rows; jimbo-dj's analyzer (ok at version 2, errors) beside Plex's sonic analysis; folders shown as jimbo-dj stored them, not compared. Cached in traqfreq's store (key: last sync, history version, analyzer version and results).
- T9: `GET /api/library/tracks?…`: the rows behind each library number (codec, container, bitrate, played, rated, sonic, analysis ok/error/older/none, mapped, multi-part, removed, artist, album; sort by artist, Plex plays or added), paged, each with its plays (jimbo-dj's `plays_of`: the larger of Plex's and the history's, never the sum) and last played (`last_of`).
- T9: `src/traqfreq/vendor/jimbodj_library.py`: `_pct`, `stats`, `_track_stats`, `plays_of`, `last_of`, `ANALYZER_VERSION` from jimbo-dj 1d8a7cb, unchanged, with marked stand-ins for its connection and settings.
- T9: fixture: library columns on the six invented tracks (lossless, 128k, 256k, 320k two-part, no bitrate and unmapped; played, rated, sonic; the removed track played 50 times), analyzer versions 1 and 2, Plex server meta, and jimbo-dj's stored `library.stats` in full shape. T5–T8 counts unchanged.
- P1 gate passed on live data: all 41 stored HISTORY rows (overview and every Wrapped), 862 of 862 fields, equal jimbo-dj's.
- T8: Years (`/history/years`: every year's plays and hours, on this day in earlier years, jimbo-dj's highlights), Wrapped for a year, month or day (`/history/wrapped?period=`), Top artists, songs and albums for all time, 30 days, 12 months, a year or a month by plays or minutes (`/history/top`). The same numbers as jimbo-dj's (its `_overview`, `_wrapped`, `_top`), each opening its rows.
- T8: P1 gate: `scripts/p1_gate.py` (read-only, `--url` or `--db`) and `GET /api/history/compare` put every number jimbo-dj stored for HISTORY next to traqfreq's, with matches and whether the stored row is stale; shown at `/history/compare`, on the overview and on SETUP.
- T8: `GET /api/history/years`, `/on-this-day`, `/wrapped`, `/top`, `/compare`; `/api/history/listens` adds `song`, `album`, `hour`, `weekday`.
- T8: vendored unchanged from jimbo-dj: `_range`, `_minutes`, `TOP_PERIODS`, `top_range`.
- T7 deployed: gap buckets equal the overview's repeats and duplicates for every source pair on live data, none unfound.
- `docs/specs/t9-library.md`: plan for T9–T12 (LIBRARY read-only).
- T7: Counted once page (`/history/counted`, linked from the overview's "Every listen, counted once"): for each repeat and duplicate, the listen it repeats or duplicates, found again with jimbo-dj's own conditions (`window_sql` vendored unchanged), and how far apart, in gap buckets per source pair; "no listen in the window" is shown, not hidden.
- T7: read-only checks over the plays: bursts (plays starting under 30 s apart, all but the first held), one song looped, steady rhythm (scrobbler-bot shape). Report only; plays stay jimbo-dj's `counted = 1`.
- T7: `GET /api/history/counted` (stats cache `history.counted`); `/api/history/listens` adds `of`, `gap` (`a-b` seconds or `none`), `start`/`end` (UTC epoch seconds), and each repeat or duplicate row carries `of` (its listen, gap, window). The rows' "why" line says which play and how far apart.
- T7: `scripts/make_fixture.py --checks` adds invented bursts, a loop, a steady rhythm, an Apple Music daily-summary duplicate and a flag with no play in its window.
- T6: HISTORY page (when `TRAQFREQ_MODULES` has H): plays, every listen counted once, matched %, the year heatmap (HISTORY blue at five levels, with a summary, legend and list by month), top artists (one name per artist, jimbo-dj's `Names`), sources and years. Every number links to its rows at `/history/listens` (paged, with the rule and why each listen is there).
- T6: stats cache in traqfreq's own database (`TRAQFREQ_DATA_DIR/traqfreq.sqlite`), keyed by jimbo-dj's history, match and library versions and the time zone.
- T6: `GET /api/history/heatmap?year=`; `/api/history/overview` adds top artists and reads the cache; `/api/history/listens` adds `period`, `artist`, `matched`.
- T6: heat tokens (`heat` in `berlin.json` → `--heat-0…4`).
- T5 deployed: on live data SETUP's four counts and the history overview (every year, every source) equal jimbo-dj's.
- T5: `GET /api/history/overview` (plays, listens, too short / repeats / duplicates, by source and by year in jimbo-dj's listening time zone, matched plays, songs, jimbo-dj's stored plays) and `GET /api/history/listens` (the rows behind each number). Plays are jimbo-dj's `counted = 1`; every listen is in exactly one bucket, checked on each read (`adds_up`).
- `/api/legacy/summary` adds `measures`: tracks, albums, artists and plays counted jimbo-dj's way (live tracks, distinct album and artist keys of live tracks, counted listens), each with its SQL rule and jimbo-dj's stored value (`stats` table) to compare. `counts` (raw rows) unchanged.
- SETUP shows those four numbers with their rules and whether they match jimbo-dj's stored counts (W3), then raw rows per table.
- `src/traqfreq/vendor/jimbodj_history.py`: jimbo-dj's pure history functions, copied unchanged (jimbo-dj is private, so no git dependency).
- `TZ` setting (jimbo-dj's listening time zone when its `history_tz` isn't set).
- `docs/specs/t5-history.md`: plan for T5–T8.
### Fixed
- T7: `test_api_tz_from_env` wrote its cache into `./data` (in the server checkout, the deployed app's data folder); it now uses a temp folder.
- Fixture and `legacy.KEY_TABLES` now match jimbo-dj's real schema (`tracks` by `rating_key` with `removed_at`, `albums`/`artists` by key, `analysis`, `features`, `listens`, `listen_matches`, `history_imports`, `stats`). The guessed `track_analysis` and `track_tags` are gone, so SETUP no longer lists them as not found.
- P0 gate passed: deployed on the Mac mini at :4492 from `main`, reading jimbo-dj's live database read-only.
- T4 shell: chrome top bar from `NavItem` (LIBRARY, switched-on modules, SETUP, search; L1/L2), compact top bar on tablets (L4), 76 px phone bottom bar of five (L3), client-side routing.
- Map home: the modules drawn as lines (off lines dashed), a screen-reader summary and a list view (L6).
- Read-only SETUP: legacy DB row counts, last scan (`meta.last_sync`), recent jobs (`history_imports`), each module's on/off `Status`. Empty module pages and search point to SETUP (D1).
- `GET /api/legacy/activity` and `GET /api/modules`; `TRAQFREQ_MODULES` switches modules on (LIBRARY and SETUP always on).
- `Dockerfile`, `docker-compose.yml` (service `web`, port 4492, jimbo-dj's data folder mounted `:ro`), `.dockerignore`.
- Kit: `NavItem` plain items (no module) and wordmark; `Button` links route client-side with `onClick`; `Text` variant `note`.
- Fixture: jimbo-dj's real `meta.last_sync` key and `history_imports` table.
- T3 kit: the eleven components in `web/src/components/kit` (LineBullet, NavItem, Status, Band, Button, ConditionChip, LineLever, StationRow, Text, Card, ArtTile), every state, styled from tokens only.
- Vitest + Testing Library component tests (51), in CI.
- Brand checks K1 (kit-only UI) and W1 (no copy literals in JSX); C7 covers the kit's `--line` indirection; copy lint covers every `*strings.json`.
- Dev-only kit board at `/kit`; its sample copy never ships.
### Changed
- Port 4491 → **4492** (4491 is jimbo-dj's `jimbodj-text` analyzer on the Mac mini): settings default, Vite proxy, docs, tests.
- GitHub repo was made private, then public again; default branch is `main` (at the T3 commit). Forgejo is live as a pull mirror of GitHub (10-minute sync).
### Added
- jimbo-deploy: `deploy.json`, README deploy snippet, Forgejo mirrors GitHub (pull mirror); `origin` pushes to GitHub only.

## [2026.11.1] - 2026-11-22
### Added
- T2 web shell: `web/` with Vite, React and TypeScript, served by FastAPI at `/` (SPA fallback; `TRAQFREQ_WEB_DIR`).
- `tokens/berlin.json` (Berlin · Gelb, light and dark) and `scripts/build-tokens.mjs` generating CSS custom properties.
- Self-hosted Fira Sans (bundled woff2, no CDN).
- `scripts/check.mjs` brand fast checks (C1, C2, C4, C7, T2, T3, W2) with self-tests; CI `web` job.
- Dark mode: 1 px paper outline on MIXES and FETCH marks.
### Changed
- Session protocol: code is produced on the Mac mini, driven from the laptop; pushed to GitHub and Forgejo.

## [2026.11.0] - 2026-11-22
### Added
- T1 scaffold: `traqfreq` package, FastAPI app, env settings, uvicorn entry point on :4491.
- Read-only legacy DB access to jimbo-dj's SQLite; `GET /api/health`, `GET /api/legacy/summary`.
- Fixture generator `scripts/make_fixture.py` (invented rows, provisional schema).
- pytest suite and GitHub Actions workflow.
- CLAUDE.md, HANDOFF.md, docs/specs (phases, brand summary).
