"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import __version__, ask, counted, entities, history, identity, junction, legacy, library, library_gate, matching, periods, playlists, playlists_compare, proposals, reach, reading, servers, servers_gate, store, tagpages, tags, tags_gate
from .settings import CORE, MODULES, Settings


def create_app(settings: Settings | None = None, server_transport=None, ask_transport=None) -> FastAPI:
    """``server_transport``: an ``httpx`` transport for the server readers (tests: ``httpx.MockTransport``)."""
    settings = settings or Settings.from_env()
    app = FastAPI(title="traqfreq", version=__version__)
    app.state.settings = settings
    app.state.server_transport = server_transport
    app.state.ask_transport = ask_transport  # T28: jimbodj-text and Ollama (tests: httpx.MockTransport)
    app.state.readers = None  # None = reading.READERS; tests put their own here

    @app.get("/api/health")
    def health() -> dict:
        db = settings.legacy_db
        return {
            "status": "ok",
            "version": __version__,
            "legacy_db_configured": db is not None,
            "legacy_db_present": bool(db and db.is_file()),
        }

    def read_legacy(fn):
        if settings.legacy_db is None:
            raise HTTPException(503, "TRAQFREQ_LEGACY_DB is not set")
        try:
            conn = legacy.connect(settings.legacy_db)
        except legacy.LegacyDBMissing:
            raise HTTPException(503, "legacy DB not found")
        try:
            return fn(conn)
        finally:
            conn.close()

    @app.get("/api/legacy/summary")
    def legacy_summary() -> dict:
        return read_legacy(legacy.summary)

    @app.get("/api/legacy/activity")
    def legacy_activity() -> dict:
        """Last scan and recent jobs, read from jimbo-dj's DB (read-only)."""
        return read_legacy(legacy.activity)

    def read_history(fn):
        def run(conn):
            try:
                return fn(conn)
            except history.NoHistory:
                raise HTTPException(404, "jimbo-dj's database has no listens table")
            except ValueError as e:
                raise HTTPException(400, str(e))
        return read_legacy(run)

    def history_summary(conn) -> tuple[dict, dict]:
        """The built summary, from traqfreq's stats cache (its own database), rebuilt when jimbo-dj's data or
        the time zone changes."""
        return store.cached(settings.data_dir, "history.summary", history.cache_key(conn, settings.tz),
                            lambda: history.summary(conn, settings.tz))

    @app.get("/api/history/overview")
    def history_overview() -> dict:
        """Plays and the listens that aren't plays, by source and year, top artists, counted the way jimbo-dj
        counts them. Read from the stats cache."""
        def run(conn):
            value, info = history_summary(conn)
            return {**value["overview"], "cache": info}
        return read_history(run)

    @app.get("/api/history/heatmap")
    def history_heatmap(year: int | None = None) -> dict:
        """Plays per day for a year of days (the last 53 weeks, or one calendar year), with five levels."""
        def run(conn):
            value, info = history_summary(conn)
            tz = history.listen_tz(conn, settings.tz)
            return {**history.heatmap(value["days"], tz, year, datetime.now(tz).date()), "cache": info}
        return read_history(run)

    @app.get("/api/history/counted")
    def history_counted() -> dict:
        """Counted once: how far each repeat and duplicate was from the listen it repeats or duplicates, and the
        read-only checks (bursts, loops, steady rhythms). Read from the stats cache, same key as the summary."""
        def run(conn):
            tz = history.listen_tz(conn, settings.tz)
            value, info = store.cached(settings.data_dir, "history.counted", history.cache_key(conn, settings.tz),
                                       lambda: counted.counted(conn, tz))
            return {**value, "cache": info}
        return read_history(run)

    @app.get("/api/history/listens")
    def history_listens(status: str = "play", source: str | None = None, year: int | None = None,
                        period: str | None = None, artist: str | None = None, matched: bool | None = None,
                        of: str | None = None, gap: str | None = None, start: int | None = None,
                        end: int | None = None, song: str | None = None, album: str | None = None,
                        hour: int | None = None, weekday: int | None = None, limit: int = 50, offset: int = 0) -> dict:
        """The rows behind each HISTORY number (status play, too_short, repeat or duplicate; optional source,
        year, period YYYY / YYYY-MM / YYYY-MM-DD, artist key, matched, of = dup_of, gap a-b / none, start and
        end in UTC epoch seconds; T8: song = match_key, album = Top's album key, hour 0-23, weekday 0-6)."""
        return read_history(lambda c: history.listens(c, status, source or None, year, limit, offset, settings.tz,
                                                      period or None, artist or None, matched, of or None,
                                                      gap or None, start, end, song or None, album or None,
                                                      hour, weekday))

    # --- T8: Years, On this day, Wrapped, Top, and the P1 gate ---------------------------------------------

    def period_ctx(conn):
        """(time zone, cache key, Names) for jimbo-dj's data as it is now."""
        tz = history.listen_tz(conn, settings.tz)
        key = f"{history.cache_key(conn, settings.tz)}|p{periods.PERIOD_VERSION}"
        return tz, key, periods.names(conn, key)

    def jd_today() -> str:
        """Today in jimbo-dj's TZ (schedule.tz: TZ, else America/Denver): its daily rows' stamps end with it."""
        try:
            zone = ZoneInfo(settings.tz or history.DEFAULT_TZ)
        except Exception:  # noqa: BLE001
            zone = ZoneInfo("UTC")
        return datetime.now(zone).date().isoformat()

    def daily_build(conn):
        tz, key, nm = period_ctx(conn)
        today = datetime.now(tz).date()
        return store.cached(settings.data_dir, "history.daily", f"{key}|{today.isoformat()}",
                            lambda: periods.daily(conn, tz, nm, today))

    def wrapped_build(conn, period: str):
        y, m, d = periods.parse_wrapped(period)
        p = periods.wrapped_key(y, m, d)
        tz, key, nm = period_ctx(conn)
        return store.cached(settings.data_dir, f"history.wrapped:{p}", key, lambda: periods.wrapped(conn, tz, nm, y, m, d))

    @app.get("/api/history/years")
    def history_years() -> dict:
        """Every year's plays and hours, on this day in earlier years, and jimbo-dj's overview highlights,
        worked out the way jimbo-dj's overview works them out. Rebuilt daily and when the data changes."""
        def run(conn):
            value, info = daily_build(conn)
            return {**value, "cache": info}
        return read_history(run)

    @app.get("/api/history/on-this-day")
    def history_on_this_day() -> dict:
        """Today's date in earlier years: plays and the top three songs of each year."""
        def run(conn):
            value, info = daily_build(conn)
            return {"today": value.get("today"), "on_this_day": value.get("on_this_day", []),
                    "timezone": value.get("timezone"), "cache": info}
        return read_history(run)

    @app.get("/api/history/wrapped")
    def history_wrapped(period: str) -> dict:
        """Wrapped for a year (YYYY), a month (YYYY-MM) or a day (YYYY-MM-DD), number for number as jimbo-dj's."""
        def run(conn):
            value, info = wrapped_build(conn, period)
            return {**value, "cache": info}
        return read_history(run)

    @app.get("/api/history/top")
    def history_top(period: str = "all", kind: str = "artists", sort: str = "plays", source: str | None = None,
                    page: int = 1, per: int = 48) -> dict:
        """Top artists, songs or albums for a period (all, 30d, 12m, YYYY, YYYY-MM) by plays or minutes."""
        def run(conn):
            if kind not in periods.TOP_KINDS:
                raise ValueError(f"kind is one of {', '.join(periods.TOP_KINDS)}")
            if sort not in periods.TOP_SORTS:
                raise ValueError("sort is plays or minutes")
            tz, key, nm = period_ctx(conn)
            if period in ("30d", "12m"):
                key = f"{key}|{datetime.now(tz).date().isoformat()}"
            periods.top_range(conn, tz, period)  # a bad period is a 400 before anything is built
            value, info = store.cached(settings.data_dir, f"history.top:{period}:{source or ''}", key,
                                       lambda: periods.top(conn, tz, nm, period, source or None))
            return {**periods.top_page(value, kind, sort, page, per), "cache": info}
        return read_history(run)

    @app.get("/api/history/compare")
    def history_compare() -> dict:
        """The P1 gate: every HISTORY number jimbo-dj stored (stats history.overview and every history.wrapped)
        next to traqfreq's for the same period, with matches; a stale stored row is said to be stale."""
        def run(conn):
            tz, key, nm = period_ctx(conn)
            today = jd_today()
            value, info = store.cached(
                settings.data_dir, "history.compare", f"{key}|{today}|{datetime.now(tz).date()}|{periods.gate_key(conn)}",
                lambda: periods.compare(conn, tz, nm, today, overview_of=lambda: daily_build(conn)[0],
                                        wrapped_of=lambda p: wrapped_build(conn, p)[0]))
            return {**value, "cache": info}
        return read_history(run)

    # --- T9: LIBRARY numbers and their rows -------------------------------------------------------------

    def read_library(fn):
        def run(conn):
            try:
                return fn(conn)
            except library.NoLibrary:
                raise HTTPException(404, "jimbo-dj's database has no tracks table")
            except ValueError as e:
                raise HTTPException(400, str(e))
        return read_legacy(run)

    @app.get("/api/library/stats")
    def library_stats() -> dict:
        """jimbo-dj's library numbers (its library.stats, counted its way), each with its rule and the query for
        its rows; folders as jimbo-dj stored them. Read from the stats cache (key: last sync, history version,
        analyzer version and results)."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "library.stats", library.cache_key(conn),
                                       lambda: library.stats(conn, settings.tz))
            return {**value, "cache": info}
        return read_library(run)

    @app.get("/api/library/tracks")
    def library_tracks(codec: str | None = None, container: str | None = None, bitrate: str | None = None,
                       played: bool | None = None, rated: bool | None = None, sonic: bool | None = None,
                       analysis: str | None = None, mapped: bool | None = None, multi_part: bool | None = None,
                       removed: bool = False, artist_key: int | None = None, album_key: int | None = None,
                       sort: str = "artist", limit: int = 50, offset: int = 0, facet: str | None = None,
                       value: str | None = None, heard: bool | None = None, source: str | None = None) -> dict:
        """The rows behind each LIBRARY number: live tracks (or removed ones) by codec, container, bitrate
        bucket, played, rated, Plex sonic analysis, jimbo-dj's analyzer (ok, error, older, none), mapped,
        multi-part, artist or album, or (T12) one bar of jimbo-dj's Library charts (facet and value, e.g.
        facet=format&value=FLAC); each with its plays (jimbo-dj's plays_of)."""
        return read_library(lambda c: library.tracks(
            c, codec, container, bitrate or None, played, rated, sonic, analysis or None, mapped, multi_part,
            removed, artist_key, album_key, sort, limit, offset, settings.tz, facet or None,
            value if facet else None, heard, source or None))

    @app.get("/api/library/compare")
    def library_compare() -> dict:
        """The P2 gate: every LIBRARY number jimbo-dj stored (stats library.stats and library.charts) next to
        traqfreq's, with matches and whether the stored row is fresh. Folders, genres and styles aren't
        compared (shown as stored). Read from the stats cache."""
        def run(conn):
            tz = library_gate.zone(conn, settings.tz)
            stats_of = lambda: store.cached(settings.data_dir, "library.stats", library.cache_key(conn),  # noqa: E731
                                            lambda: library.stats(conn))[0]
            value, info = store.cached(settings.data_dir, "library.compare", library_gate.cache_key(conn, tz),
                                       lambda: library_gate.compare(conn, tz, stats_of=stats_of))
            return {**value, "cache": info}
        return read_library(run)

    # --- T11: albums, artists, a track ---------------------------------------------------------------------

    def read_entity(fn):
        def run(conn):
            try:
                return fn(conn)
            except entities.NotFound as e:
                raise HTTPException(404, str(e))
        return read_library(run)

    @app.get("/api/library/albums")
    def library_albums(sort: str = "plays", limit: int = 50, offset: int = 0) -> dict:
        """jimbo-dj's Library → Albums: every live album with its tracks, plays (SUM of plays_of), newest added
        and year; sort plays, added (jimbo-dj's), name or year."""
        return read_entity(lambda c: entities.entity_list(c, "albums", sort, limit, offset, settings.tz))

    @app.get("/api/library/artists")
    def library_artists(sort: str = "plays", limit: int = 50, offset: int = 0) -> dict:
        """jimbo-dj's Library → Artists, the same way."""
        return read_entity(lambda c: entities.entity_list(c, "artists", sort, limit, offset, settings.tz))

    @app.get("/api/library/album/{key}")
    def library_album(key: int) -> dict:
        """An album: its tracks in disc and track order with plays and other copies, and their listens."""
        return read_entity(lambda c: entities.album(c, key, settings.tz))

    @app.get("/api/library/artist/{key}")
    def library_artist(key: int) -> dict:
        """An artist: its albums, top songs, plays and listens."""
        return read_entity(lambda c: entities.artist(c, key, settings.tz))

    @app.get("/api/library/track/{key}")
    def library_track(key: int) -> dict:
        """A track: file facts, jimbo-dj's analysis, plays (plays_of), listens by source, and its song's copies."""
        return read_entity(lambda c: entities.track(c, key, settings.tz))

    @app.get("/api/library/plays")
    def library_plays(track: int | None = None, album: int | None = None, artist: int | None = None,
                      song: bool = False, source: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        """The counted listens behind an album's, artist's or track's history numbers, newest first."""
        return read_entity(lambda c: entities.plays(c, track, album, artist, song, source or None, limit, offset,
                                                    settings.tz))

    # --- T13: SERVERS, track identity (the Plex side) ------------------------------------------------------

    @app.get("/api/servers")
    def servers_status() -> dict:
        """Plex (through jimbo-dj's database), Jellyfin and Navidrome: set up or not, with which settings
        (secrets only as set or not set). traqfreq never writes to any server."""
        conn = None
        if settings.legacy_db is not None:
            try:
                conn = legacy.connect(settings.legacy_db)
            except legacy.LegacyDBMissing:
                conn = None
        try:
            out = servers.status(conn, settings)
        finally:
            if conn is not None:
                conn.close()
        for s in out["servers"]:
            if s["server"] in reading.READERS:
                s["refresh"] = reading.state(settings, s["server"], limit=1)
        return out

    def read_identity(fn):
        def run(conn):
            try:
                return fn(conn)
            except identity.NoLibrary as e:
                raise HTTPException(404, str(e))
            except ValueError as e:
                raise HTTPException(400, str(e))
        return read_legacy(run)

    @app.get("/api/servers/identity")
    def servers_identity() -> dict:
        """Every live Plex copy's identity: file key, song, match key; Plex's music folders and where they come
        from; each count with its rule and its rows. Read from the stats cache (servers.identity)."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "servers.identity",
                                       identity.cache_key(conn, settings.plex_roots),
                                       lambda: identity.summary(conn, settings.plex_roots))
            return {**value, "cache": info}
        return read_identity(run)

    @app.get("/api/servers/copies")
    def servers_copies(issue: str | None = None, song: str | None = None, file: str | None = None,
                       has_file: bool | None = None, versions: bool | None = None, rating_key: int | None = None,
                       sort: str = "file", limit: int = 50, offset: int = 0) -> dict:
        """The copies behind each identity count: by issue, song key, file key, with or without a file key,
        songs with more than one copy, or one rating key."""
        return read_identity(lambda c: identity.copies(c, settings.plex_roots, issue or None, song or None,
                                                       file or None, has_file, versions, rating_key, sort,
                                                       limit, offset))

    # --- T14: SERVERS, matching on snapshots -----------------------------------------------------------

    @app.get("/api/servers/matches")
    def servers_matches(server: str | None = None, tier: str | None = None, reason: str | None = None,
                        rating_key: int | None = None, limit: int = 50, offset: int = 0) -> dict:
        """Every Plex copy matched to the Jellyfin and Navidrome items in their stored snapshots (file, then
        MusicBrainz IDs, then tags; one to one), and Jellyfin to Navidrome; every unmatched copy and item with
        its reason. Each count with its rule and its rows: ``server`` (jellyfin, navidrome,
        jellyfin-navidrome), ``tier`` or ``reason``; ``rating_key`` = one Plex copy's rows (the track page's
        "On servers", T15). Nothing is sent to any server."""
        return read_identity(lambda c: matching.report(c, settings.data_dir, settings.plex_roots, server or None,
                                                       tier or None, reason or None, limit, offset, rating_key))

    # --- T19: the P3 gate --------------------------------------------------------------------------------

    @app.get("/api/servers/compare")
    def servers_compare(seed: int | None = None) -> dict:
        """The P3 gate: (1) one to one per server, (2) every unmatched copy and item has a reason and they add up,
        (3) a spot check of every case plus 20 copies at random (``seed``; default today's date), each asked of
        Jellyfin and Navidrome by ID now (GET only): file and duration within 2 s of Plex's. Not cached: the
        spot check asks the servers each time. Writes nothing anywhere."""
        return read_identity(lambda c: servers_gate.compare(c, settings, seed, app.state.server_transport))

    # --- T16: SERVERS, reading servers (GET only) ---------------------------------------------------------

    def known_server(server: str) -> None:
        if server == "plex":
            raise HTTPException(400, {"error": "plex", "message": "Plex is read through jimbo-dj's database (its last "
                                      "sync), not by traqfreq: there is nothing to refresh here."})
        if server not in reading.READERS:
            raise HTTPException(404, {"error": "unknown", "message": f"No server called {server!r}."})

    @app.post("/api/servers/{server}/refresh")
    def servers_refresh(server: str) -> dict:
        """Read one server whole (GET requests only) and store its snapshot in traqfreq's own database, replacing
        the one before. One refresh at a time per server; each is logged with its counts or its error. Writes
        nothing to the server, to jimbo-dj's database or to any file but traqfreq's database."""
        known_server(server)
        try:
            entry = reading.refresh(server, settings, app.state.server_transport, app.state.readers)
        except reading.NotSetUp as e:
            raise HTTPException(409, {"error": "not_set_up", "message": str(e),
                                      "missing": reading.missing_settings(server, settings)})
        except reading.Busy as e:
            raise HTTPException(409, {"error": "busy", "message": str(e)})
        except reading.ReaderMissing as e:
            raise HTTPException(501, {"error": "no_reader", "message": str(e)})
        except reading.ServerError as e:
            raise HTTPException(502, {"error": "server", "message": e.message, "status": e.status})
        return {"refresh": entry, **reading.state(settings, server)}

    @app.get("/api/servers/{server}/refreshes")
    def servers_refreshes(server: str, limit: int = 10) -> dict:
        """A server's refresh log, newest first: when, done or failed, its counts or the server's message."""
        known_server(server)
        return reading.state(settings, server, limit)

    # --- T20: TAGS, the ladder (read-only) -----------------------------------------------------------------

    def read_tags(fn):
        def run(conn):
            try:
                return fn(conn)
            except tags.NoTags as e:
                raise HTTPException(404, f"jimbo-dj's database has no tag tables ({e})")
            except tags.NotFound as e:
                raise HTTPException(404, str(e))
            except ValueError as e:
                raise HTTPException(400, str(e))
        return read_legacy(run)

    @app.get("/api/tags/ladder")
    def tags_ladder() -> dict:
        """Every genre tag in use on its rungs, broad to specific (jimbo-dj's tag rules, vendored), with the
        numbers behind each and the agreement with jimbo-dj's families (run here and as it stored them). Read
        from the stats cache (key: jimbo-dj's tag data stamp)."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "tags.ladder", tags.cache_key(conn),
                                       lambda: tags.overview(conn))
            return {**value, "cache": info}
        return read_tags(run)

    @app.get("/api/tags/albums")
    def tags_albums(tag: str, set: str = "carries", limit: int = 50, offset: int = 0) -> dict:  # noqa: A002
        """The albums behind a tag's number: carrying it, under it (it or a tag below it), or missing it (a
        broad tag)."""
        return read_tags(lambda c: tags.albums(c, tag, set, limit, offset))

    @app.get("/api/tags/artists")
    def tags_artists(tag: str, limit: int = 50, offset: int = 0) -> dict:
        """The artists whose Plex artist genres name a tag."""
        return read_tags(lambda c: tags.artists(c, tag, limit, offset))

    # --- T21: tracks tagged one by one (read-only) ----------------------------------------------------------

    @app.get("/api/tags/album/{key}")
    def tags_album(key: int) -> dict:
        """An album's live tracks with their tags (jimbo-dj's per-track rule), the tracks that differ from the
        album, and the tags its tracks and files carry that speak for it."""
        return read_tags(lambda c: tags.album(c, key))

    @app.get("/api/tags/track/{key}")
    def tags_track(key: int) -> dict:
        """A live track's tags by source (its own and its file's, its album's and artist's Plex genres,
        MusicBrainz votes, the analyzer's styles with their scores), each on its rung of the ladder, and its tags."""
        return read_tags(lambda c: tags.track(c, key))

    @app.get("/api/tags/tracks/check")
    def tags_tracks_check() -> dict:
        """Gate check 2: every live track's tags against jimbo-dj's _genre_tags, and its kept styles against
        genres.Styles.sound_genres (both vendored, run here). Cached (key: the tag and styles data stamps)."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "tags.tracks", tags.track_check_key(conn),
                                       lambda: tags.track_check(conn))
            return {**value, "cache": info}
        return read_tags(run)

    # --- T22: the proposals inbox (shown, never applied) and gate check 3 ------------------------------------

    @app.get("/api/tags/proposals")
    def tags_proposals() -> dict:
        """Every album's proposed change, grouped as jimbo-dj's audit groups them (kinds of issue, fixes,
        suggestions), traqfreq's own ladder proposals and rule questions, Fix in Plex's preview counts, and gate
        check 3 against jimbo-dj's stored library.tags. Nothing is applied: Fix in Plex stays in jimbo-dj until
        P6. Cached (key: jimbo-dj's tag data stamp)."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "tags.proposals", proposals.cache_key(conn),
                                       lambda: proposals.inbox(conn))
            return {**value, "cache": info}
        return read_tags(run)

    @app.get("/api/tags/proposals/albums")
    def tags_proposals_albums(group: str = "all", value: str | None = None, limit: int = 50, offset: int = 0) -> dict:
        """The albums behind one of the inbox's numbers (group all, kind, fix, suggest, ladder or rule), each
        before and after Fix in Plex's preview, with its issues, suggestions and traqfreq's ladder proposals."""
        return read_tags(lambda c: proposals.albums(c, group, value, limit, offset))

    # --- T23: a page per tag, the genre map, movements, and the P4 gate ---------------------------------------

    def ladder_value(conn) -> dict:
        return store.cached(settings.data_dir, "tags.ladder", tags.cache_key(conn), lambda: tags.overview(conn))[0]

    def tracks_value(conn) -> dict:
        return store.cached(settings.data_dir, "tags.tracks", tags.track_check_key(conn),
                            lambda: tags.track_check(conn))[0]

    def proposals_value(conn) -> dict:
        return store.cached(settings.data_dir, "tags.proposals", proposals.cache_key(conn),
                            lambda: proposals.inbox(conn))[0]

    @app.get("/api/tags/map")
    def tags_map() -> dict:
        """The whole ladder as lines, one per broad tag, its tags as stations on their rungs; the tags with no
        broad tag; and the movements (movements.json), which change no ladder and no count. Cached."""
        def run(conn):
            value, info = store.cached(settings.data_dir, "tags.map", tagpages.map_key(conn),
                                       lambda: tagpages.overview(conn))
            return {**value, "cache": info}
        return read_tags(run)

    @app.get("/api/tags/tag/{key:path}")
    def tags_tag(key: str) -> dict:
        """One tag: its ladders up to the broad tag, its children, its spellings and the rules that made it, its
        numbers (albums, artists, tracks, plays, sound) and the movements naming it."""
        def run(conn):
            lib, lad = tags._ready(conn)
            return tagpages.tag(conn, key, settings.tz, tagpages.movements(lib, lad))
        return read_tags(run)

    @app.get("/api/tags/tracks")
    def tags_tracks(tag: str, sort: str = "plays", limit: int = 50, offset: int = 0) -> dict:
        """The live tracks carrying a tag (jimbo-dj's per-track rule), each with its counted plays."""
        return read_tags(lambda c: tagpages.tag_tracks(c, tag, sort, limit, offset, settings.tz))

    @app.get("/api/tags/compare")
    def tags_compare() -> dict:
        """The P4 gate: check 1 (the ladder's check), check 2 (the per-track check) and check 3 (the inbox's
        check), each as its own endpoint answers it, and whether all three passed."""
        def run(conn):
            lad, trk, prop = ladder_value(conn), tracks_value(conn), proposals_value(conn)
            return tags_gate.compare(lad["check"], trk, prop["check"])
        return read_tags(run)

    # --- T24: PLAYLISTS, the Junction preview (P5), read-only -----------------------------------------------

    def read_playlists(fn):
        def run(conn):
            try:
                return fn(conn)
            except playlists.NoPlaylists:
                raise HTTPException(404, "jimbo-dj's database has no saved_playlists table")
            except playlists.NotFound as e:
                raise HTTPException(404, str(e))
            except (ValueError, TypeError) as e:
                raise HTTPException(400, str(e))
        return read_legacy(run)

    def tree_query(request: Request) -> str:
        """The tree's URL form, as jimbo-dj writes it (b=…&n=…&per=…&shuffle=…), without traqfreq's own params."""
        return urlencode([(k, v) for k, v in request.query_params.multi_items() if k in ("b", "n", "per", "shuffle")])

    @app.get("/api/playlists")
    def playlists_list() -> dict:
        """Every playlist jimbo-dj saved (saved_playlists), by kind, each with its three switches (Plex is
        jimbo-dj's in_plex; Jellyfin and Navidrome are off until P6), each with how many of the stored tracks have a
        copy on that server (P3's matches, T25). Read-only: nothing is pushed anywhere."""
        return read_playlists(lambda c: playlists.listing(c, settings.data_dir, settings.plex_roots))

    @app.get("/api/playlists/lines")
    def playlists_lines(request: Request) -> dict:
        """Any tree in jimbo-dj's URL form (``b=style:punk,!mood:sad~20&n=60``): its lines, each condition's and
        each line's count of live tracks, counted with jimbo-dj's rules, and the total. Nothing is saved."""
        return read_playlists(lambda c: playlists.lines_from_query(c, tree_query(request), settings.tz))

    @app.get("/api/playlists/lines/rows")
    def playlists_lines_rows(request: Request, line: str, path: str = "", limit: int = 50, offset: int = 0) -> dict:
        """The tracks behind a line's count, or one condition's (``path``: all.0, all.1.any.0), for a URL tree."""
        return read_playlists(lambda c: playlists.line_rows(c, playlists.rules.from_query(tree_query(request)), line, path,
                                                            limit, offset, settings.tz))

    # --- T28: the P5 gate, traqfreq's side (jimbo-dj's is asked only by scripts/p5_gate.py) ------------------

    @app.get("/api/playlists/compare")
    def playlists_compare_all() -> dict:
        """The P5 gate card: the ten trees (saved ones with a tree, then p5_trees.json), each with its lines'
        numbers and what it picks now, which kinds of condition they use between them, and the saved list check 3
        compares. jimbo-dj's side is asked by scripts/p5_gate.py only."""
        return read_playlists(lambda c: playlists_compare.compare(c, settings.tz))

    @app.get("/api/playlists/compare/stamp")
    def playlists_compare_stamp() -> dict:
        """The data stamp both sides' answers depend on; the gate script asks a tree again once if it moves."""
        return read_playlists(lambda c: {"stamp": playlists_compare.stamp(c)})

    @app.get("/api/playlists/compare/trees/{i}")
    def playlists_compare_tree(i: int) -> dict:
        """traqfreq's answer for gate tree i, in the shape of jimbo-dj's POST /api/rules/preview, with its tree."""
        return read_playlists(lambda c: playlists_compare.tree(c, i, settings.tz))

    @app.get("/api/playlists/{ref}")
    def playlists_one(ref: str, limit: int = 50, offset: int = 0) -> dict:
        """One saved playlist (slug or id): its switches, the tracks jimbo-dj stored (play order) and, when it has
        a tree, its lines with their counts."""
        return read_playlists(lambda c: playlists.playlist(c, ref, limit, offset, settings.tz, settings.data_dir,
                                                           settings.plex_roots))

    @app.get("/api/playlists/{ref}/copies")
    def playlists_one_copies(ref: str, server: str, missing: bool | None = None, limit: int = 50,
                             offset: int = 0) -> dict:
        """The stored tracks behind a switch's copies (T25): each with whether that server has a copy and, if not,
        why (removed, no snapshot, or P3's reason). ``missing=true``: only those without one."""
        return read_playlists(lambda c: playlists.copy_rows(c, ref, server, missing, limit, offset, settings.data_dir,
                                                            settings.plex_roots))

    @app.get("/api/playlists/{ref}/rows")
    def playlists_one_rows(ref: str, line: str = "", path: str = "", which: str = "count", limit: int = 50,
                           offset: int = 0) -> dict:
        """The tracks behind one of a saved playlist's numbers: a line's matches or one condition's (``path``), or
        (``which``, T25) what the line got, its pool (available), what Never in mixes left out, or every pick."""
        def run(c):
            if which == "count":
                return playlists.playlist_rows(c, ref, line, path, limit, offset, settings.tz)
            tree = playlists.tree_of(playlists._get(c, ref))
            if not tree:
                raise playlists.NotFound("this playlist has no lines")
            return junction.rows(c, tree, line, which, path, limit, offset, settings.tz)
        return read_playlists(run)

    # --- T25: the Junction, any tree in jimbo-dj's URL form ------------------------------------------------

    @app.get("/api/junction")
    def junction_preview(request: Request) -> dict:
        """What a tree (``b=…&n=…&per=…&shuffle=…``) picks now, with jimbo-dj's rules.build: per line its count,
        share, got and available, the union's total, and every picked track with the line that took it (pick
        order until T27's flow). Nothing is saved or pushed."""
        return read_playlists(lambda c: junction.build_from_query(c, tree_query(request), settings.tz))

    @app.get("/api/junction/rows")
    def junction_rows(request: Request, line: str = "", which: str = "count", path: str = "", limit: int = 50,
                      offset: int = 0) -> dict:
        """The tracks behind one of the Junction's numbers (``which``: count, got, available, banned, picked)."""
        return read_playlists(lambda c: junction.rows(c, playlists.rules.from_query(tree_query(request)), line, which,
                                                      path, limit, offset, settings.tz))

    # --- T26: movements, rooted to roaming (new in traqfreq; a preview, not part of the gate) ---------------

    @app.get("/api/junction/reach")
    def junction_reach(request: Request) -> dict:
        """How far each line of a tree could reach if it followed its tag: the style conditions it follows and four
        stops (rooted, ladder, movement, roaming), each with its count of live tracks and the tags it takes in. A
        preview only: the Junction's numbers don't move, nothing is picked or saved."""
        return read_playlists(lambda c: reach.reach_from_query(c, tree_query(request), settings.tz))

    @app.get("/api/junction/reach/rows")
    def junction_reach_rows(request: Request, line: str, stop: str, which: str = "count", limit: int = 50,
                            offset: int = 0) -> dict:
        """The tracks behind a stop's number: all it matches (count) or only those the rooted line doesn't (added)."""
        return read_playlists(lambda c: reach.rows(c, playlists.rules.from_query(tree_query(request)), line, stop, which,
                                                   limit, offset, settings.tz))

    # --- T28: the Ask box, words to a line (jimbodj-text, and Ollama when it's on) -------------------------

    @app.get("/api/junction/ask")
    def junction_ask(q: str = "") -> dict:
        """A few words to lines for the Junction: typed facet:value parts, the words by sound (jimbodj-text's CLAP
        vector against every track's) and, when it's on, by Ollama. Each line has its count and URL form."""
        return read_playlists(lambda c: ask.ask(c, q, settings.text_url, settings.ollama_url, settings.ollama_model,
                                                app.state.ask_transport, settings.tz))

    @app.get("/api/junction/ask/rows")
    def junction_ask_rows(q: str, limit: int = 50, offset: int = 0) -> dict:
        """The rows behind the sound line: the tracks nearest the words, closest first, each with its score."""
        def run(c):
            try:
                return ask.near_rows(c, q, settings.text_url, app.state.ask_transport, limit, offset)
            except ask.prompt.Unavailable as e:
                raise HTTPException(503, str(e))
            except LookupError as e:
                raise HTTPException(404, str(e))
        return read_playlists(run)

    @app.get("/api/modules")
    def modules() -> dict:
        """Each module, in nav order, with whether it is switched on (TRAQFREQ_MODULES)."""
        return {"modules": [{"id": m, "on": m in settings.modules, "core": m in CORE} for m in MODULES]}

    if (settings.web_dir / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=settings.web_dir, html=True), name="web")

    return app


class SPAStaticFiles(StaticFiles):
    """Serves the built web app; unknown non-API paths fall back to index.html (client routes)."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/") or path == "api":
                raise
            return await super().get_response("index.html", scope)
