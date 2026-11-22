"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, legacy
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
