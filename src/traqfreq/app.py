"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from datetime import datetime
from zoneinfo import ZoneInfo

from . import __version__, counted, entities, history, legacy, library, library_gate, periods, store
from .settings import CORE, MODULES, Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="traqfreq", version=__version__)
    app.state.settings = settings

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
