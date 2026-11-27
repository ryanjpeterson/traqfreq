"""traqfreq's stand-in for the part of plexapi's ``PlexServer`` that jimbo-dj's Plex sync and watcher use, not
vendored: ``friendlyName``, ``version``, ``machineIdentifier``, ``myPlexSubscription``, ``library.sections()`` (each
with ``type``, ``title``, ``key``) and ``query(path)`` (the answer's XML root element).

**GET only.** It is built on ``httpx`` and has no method that sends anything else; the client underneath is never
handed out. The token goes in the ``X-Plex-Token`` header (never in a URL, so never in a log line), and every error
message has it taken out. Redirects aren't followed. Tests hand in an ``httpx.MockTransport``."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)


class PlexUnavailable(RuntimeError):
    """Plex didn't answer, or answered with an error. The message never holds the token."""


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    type: str


class _Library:
    def __init__(self, server: "PlexServer"):
        self._server = server

    def sections(self) -> list[Section]:
        return [Section(key=str(el.get("key")), title=el.get("title") or "", type=el.get("type") or "")
                for el in self._server.query("/library/sections").findall("Directory")]


class PlexServer:
    def __init__(self, baseurl: str, token: str, timeout: float = 60, transport: httpx.BaseTransport | None = None):
        self._token = token
        self.requests = 0
        self._http = httpx.Client(
            base_url=baseurl.rstrip("/"), timeout=httpx.Timeout(timeout, connect=5.0), follow_redirects=False,
            headers={"X-Plex-Token": token, "Accept": "application/xml", "X-Plex-Product": "traqfreq"},
            transport=transport if transport is not None else httpx.HTTPTransport(retries=0))
        root = self.query("/")
        self.friendlyName = root.get("friendlyName")
        self.version = root.get("version")
        self.machineIdentifier = root.get("machineIdentifier")
        self.myPlexSubscription = (root.get("myPlexSubscription") or "").lower() in ("1", "true")
        self.library = _Library(self)

    def _clean(self, text: str) -> str:
        return text.replace(self._token, "…") if self._token else text

    def query(self, path: str) -> Element:
        where = f"GET {path.split('?')[0]}"
        self.requests += 1
        try:
            r = self._http.get(path)
        except httpx.TimeoutException:
            raise PlexUnavailable(f"Plex didn't answer in time ({where}).") from None
        except httpx.HTTPError as e:
            raise PlexUnavailable(self._clean(f"Couldn't reach Plex ({where}): {type(e).__name__}.")) from None
        if r.status_code >= 300:
            raise PlexUnavailable(f"Plex answered {r.status_code} {r.reason_phrase} ({where}).")
        try:
            return ElementTree.fromstring(r.content)
        except ElementTree.ParseError:
            raise PlexUnavailable(f"Plex answered {where} with something that isn't XML.") from None

    def close(self) -> None:
        self._http.close()
