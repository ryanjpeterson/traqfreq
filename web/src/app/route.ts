import { useCallback, useEffect, useState } from 'react';
import { MODULE_IDS, type ModuleId } from '../components/kit';

/** Each module's page. Its path is the module name in lower case (/library … /setup). */
export const MODULE_PATH: Record<ModuleId, string> = {
  L: '/library', H: '/history', T: '/tags', D: '/discover', M: '/mixes', F: '/fetch', S: '/setup',
};

export type Route =
  | { page: 'map' }
  | { page: 'search' }
  | { page: 'module'; module: ModuleId; sub?: HistorySub | LibrarySub | SetupSub | TagsSub; key?: number; tag?: string; ref?: string }
  | { page: 'notFound' };

/** HISTORY's rows page: the listens behind a number (query string = the filters). */
export const HISTORY_LISTENS = '/history/listens';
/** HISTORY's Counted once page (T7): why each listen that isn't a play isn't one, and the read-only checks. */
export const HISTORY_COUNTED = '/history/counted';

/** T8: Years and On this day; Wrapped for a period (?period=YYYY, YYYY-MM or YYYY-MM-DD); Top (?period=&kind=&sort=);
 *  the P1 gate's comparison with jimbo-dj's stored numbers. */
export const HISTORY_YEARS = '/history/years';
export const HISTORY_WRAPPED = '/history/wrapped';
export const HISTORY_TOP = '/history/top';
export const HISTORY_COMPARE = '/history/compare';
export type HistorySub = 'listens' | 'counted' | 'years' | 'wrapped' | 'top' | 'compare';
const HISTORY_SUBS: Record<string, HistorySub> = {
  [HISTORY_LISTENS]: 'listens', [HISTORY_COUNTED]: 'counted', [HISTORY_YEARS]: 'years',
  [HISTORY_WRAPPED]: 'wrapped', [HISTORY_TOP]: 'top', [HISTORY_COMPARE]: 'compare',
};

/** LIBRARY's rows page (T10): the tracks behind a number (query string = the filters of /api/library/tracks). */
export const LIBRARY_TRACKS = '/library/tracks';
/** T11: the album and artist lists, the listens behind a page's history numbers, and /library/album|artist|track/<key>. */
export const LIBRARY_ALBUMS = '/library/albums';
export const LIBRARY_ARTISTS = '/library/artists';
export const LIBRARY_PLAYS = '/library/plays';
/** T12: the P2 gate's comparison with jimbo-dj's stored library numbers. */
export const LIBRARY_COMPARE = '/library/compare';
/** T24: PLAYLISTS (P5): the saved playlists, one playlist (/library/playlists/<slug>), the rows behind its counts.
 *  T25: the Junction (any tree, /library/junction?b=…), the rows behind its numbers, the copies behind a switch. */
export type LibrarySub = 'tracks' | 'albums' | 'artists' | 'plays' | 'album' | 'artist' | 'track' | 'compare'
  | 'playlists' | 'playlist' | 'playlistRows' | 'playlistCopies' | 'junction' | 'junctionRows';
const LIBRARY_SUBS: Record<string, LibrarySub> = {
  [LIBRARY_TRACKS]: 'tracks', [LIBRARY_ALBUMS]: 'albums', [LIBRARY_ARTISTS]: 'artists', [LIBRARY_PLAYS]: 'plays',
  [LIBRARY_COMPARE]: 'compare', '/library/playlists': 'playlists', '/library/playlists/rows': 'playlistRows',
  '/library/playlists/copies': 'playlistCopies', '/library/junction': 'junction', '/library/junction/rows': 'junctionRows',
};

/** T15: SETUP → SERVERS and the rows behind its counts (identity copies; match rows). SERVERS is not a module. */
export type SetupSub = 'servers' | 'serverCopies' | 'serverMatches';
const SETUP_SUBS: Record<string, SetupSub> = {
  '/setup/servers': 'servers', '/setup/servers/copies': 'serverCopies', '/setup/servers/matches': 'serverMatches',
};

/** T20: TAGS' rows pages: the albums and artists behind a tag's numbers, the tags behind a summary number. */
export type TagsSub = 'albums' | 'artists' | 'list' | 'album' | 'track' | 'proposals' | 'proposalAlbums'
  | 'tag' | 'map' | 'tracks';
/** T22: the proposals inbox and the albums behind its numbers. T23: the genre map and the tracks behind a tag. */
const TAGS_SUBS: Record<string, TagsSub> = { '/tags/albums': 'albums', '/tags/artists': 'artists', '/tags/list': 'list',
  '/tags/proposals': 'proposals', '/tags/proposals/albums': 'proposalAlbums', '/tags/map': 'map', '/tags/tracks': 'tracks' };

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/[?#].*$/, '').replace(/\/+$/, '') || '/';
  if (path === '/') return { page: 'map' };
  if (path === '/search') return { page: 'search' };
  if (LIBRARY_SUBS[path]) return { page: 'module', module: 'L', sub: LIBRARY_SUBS[path] };
  const entity = /^\/library\/(album|artist|track)\/(\d+)$/.exec(path);
  if (entity) return { page: 'module', module: 'L', sub: entity[1] as LibrarySub, key: Number(entity[2]) };
  const pl = /^\/library\/playlists\/([^/]+)$/.exec(path);
  if (pl) {
    try {
      return { page: 'module', module: 'L', sub: 'playlist', ref: decodeURIComponent(pl[1]) };
    } catch {
      return { page: 'notFound' };
    }
  }
  if (HISTORY_SUBS[path]) return { page: 'module', module: 'H', sub: HISTORY_SUBS[path] };
  if (SETUP_SUBS[path]) return { page: 'module', module: 'S', sub: SETUP_SUBS[path] };
  if (TAGS_SUBS[path]) return { page: 'module', module: 'T', sub: TAGS_SUBS[path] };
  /** T21: an album tagged track by track, a track's tags by source. */
  const tagged = /^\/tags\/(album|track)\/(\d+)$/.exec(path);
  if (tagged) return { page: 'module', module: 'T', sub: tagged[1] as TagsSub, key: Number(tagged[2]) };
  /** T23: a page per tag, /tags/tag/<key> (the key URL-encoded). */
  const tagPage = /^\/tags\/tag\/(.+)$/.exec(path);
  if (tagPage) {
    try {
      return { page: 'module', module: 'T', sub: 'tag', tag: decodeURIComponent(tagPage[1]) };
    } catch {
      return { page: 'notFound' };
    }
  }
  const module = MODULE_IDS.find((m) => MODULE_PATH[m] === path);
  return module ? { page: 'module', module } : { page: 'notFound' };
}

const here = () => window.location.pathname + window.location.search;

/** A tiny History API router: the current path (with its query string) and a navigate function. */
export function usePath(): [string, (href: string) => void] {
  const [path, setPath] = useState(here);
  useEffect(() => {
    const onPop = () => setPath(here());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const navigate = useCallback((href: string) => {
    if (href !== here()) window.history.pushState(null, '', href);
    setPath(here());
    window.scrollTo?.(0, 0);
  }, []);
  return [path, navigate];
}
