import { lazy, Suspense, useEffect } from 'react';
import { t, type StringKey } from './copy/t';
import { useModules, type ModuleSwitch } from './app/api';
import { BottomBar, TopBar } from './app/Nav';
import { parseRoute, usePath, type Route } from './app/route';
import { History } from './pages/History';
import { HistoryCompare } from './pages/HistoryCompare';
import { HistoryCounted } from './pages/HistoryCounted';
import { HistoryRows } from './pages/HistoryRows';
import { HistoryTop } from './pages/HistoryTop';
import { HistoryWrapped } from './pages/HistoryWrapped';
import { HistoryYears } from './pages/HistoryYears';
import { Library } from './pages/Library';
import { LibraryRows } from './pages/LibraryRows';
import { LibraryCompare } from './pages/LibraryCompare';
import { Junction, Playlist, PlaylistCopies, PlaylistRows, Playlists, ReachRows } from './pages/Playlists';
import { LibraryAlbum, LibraryArtist, LibraryList, LibraryPlays, LibraryTrack } from './pages/LibraryEntities';
import { MapHome } from './pages/MapHome';
import { ModulePage } from './pages/ModulePage';
import { NotFound } from './pages/NotFound';
import { Search } from './pages/Search';
import { Setup } from './pages/Setup';
import { TagAlbumRows, TagArtistRows, TagList, Tags } from './pages/Tags';
import { TagAlbum, TagTrack } from './pages/TagsTracks';
import { ProposalAlbums, Proposals } from './pages/TagsProposals';
import { GenreMap, TagPage, TagTrackRows } from './pages/TagsGenre';
import { ServerCopies, ServerMatches, SetupServers } from './pages/Servers';
import './app/app.css';

// The kit board is dev only: import.meta.env.DEV is false in production, so Vite drops it from the build (D1).
const KitBoard = import.meta.env.DEV ? lazy(() => import('./dev/KitBoard').then((m) => ({ default: m.KitBoard }))) : null;

export function App() {
  if (KitBoard && window.location.pathname === '/kit') {
    return <Suspense><KitBoard /></Suspense>;
  }
  return <Shell />;
}

function pageTitle(route: Route): string {
  if (route.page === 'map') return t('map.title');
  if (route.page === 'search') return t('search.title');
  if (route.page === 'module') return t(`module.${route.module}` as StringKey);
  return t('notFound.title');
}

/** The shell: chrome top bar, the page, and the phone bottom bar. */
export function Shell() {
  const [path, navigate] = usePath();
  const [modules, known] = useModules();
  let route = parseRoute(path);
  // An off module leaves no trace (L2): its page doesn't exist. Wait for the switches before saying so.
  const waiting = route.page === 'module' && !known && !['L', 'S'].includes(route.module);
  if (route.page === 'module') {
    const id = route.module;
    if (known && !modules.find((m) => m.id === id)?.on) route = { page: 'notFound' };
  }

  useEffect(() => {
    document.title = `${pageTitle(route)} · ${t('title.suffix')}`;
  });

  const r = route;
  return (
    <>
      <TopBar modules={modules} route={r} navigate={navigate} />
      <main className={r.page === 'module' ? 'is-banded' : undefined} aria-busy={waiting || undefined}>
        {r.page === 'map' && <MapHome modules={modules} navigate={navigate} />}
        {r.page === 'search' && <Search navigate={navigate} />}
        {r.page === 'module' && r.module === 'S' && <SetupPage sub={r.sub} modules={modules} query={path.replace(/^[^?]*/, '')} navigate={navigate} />}
        {r.page === 'module' && r.module === 'H' && !waiting && <HistoryPage sub={r.sub} query={path.replace(/^[^?]*/, '')} navigate={navigate} />}
        {r.page === 'module' && r.module === 'L' && <LibraryPage sub={r.sub} entityKey={r.key} playlistRef={r.ref} query={path.replace(/^[^?]*/, '')} navigate={navigate} />}
        {r.page === 'module' && r.module === 'T' && !waiting && <TagsPage sub={r.sub} entityKey={r.key} tag={r.tag} query={path.replace(/^[^?]*/, '')} navigate={navigate} />}
        {r.page === 'module' && !['S', 'H', 'L', 'T'].includes(r.module) && !waiting && <ModulePage module={r.module as 'D' | 'M' | 'F'} navigate={navigate} />}
        {r.page === 'notFound' && <NotFound navigate={navigate} />}
      </main>
      <BottomBar modules={modules} route={r} navigate={navigate} />
    </>
  );
}

/** SETUP's pages: the overview, and SERVERS with the rows behind its counts (T15). */
function SetupPage({ sub, modules, query, navigate }: { sub?: string; modules: ModuleSwitch[]; query: string; navigate: (href: string) => void }) {
  if (sub === 'servers') return <SetupServers query={query} navigate={navigate} />;
  if (sub === 'serverCopies') return <ServerCopies query={query} navigate={navigate} />;
  if (sub === 'serverMatches') return <ServerMatches query={query} navigate={navigate} />;
  return <Setup modules={modules} navigate={navigate} />;
}

/** TAGS' pages (T20): the ladder, the albums and artists behind a tag's numbers, the tags behind a summary number;
 *  T21: an album tagged track by track, a track's tags by source; T22: the proposals inbox and its albums. */
function TagsPage({ sub, entityKey, tag, query, navigate }: { sub?: string; entityKey?: number; tag?: string; query: string; navigate: (href: string) => void }) {
  if (sub === 'tag' && tag != null) return <TagPage tagKey={tag} navigate={navigate} />;
  if (sub === 'map') return <GenreMap navigate={navigate} />;
  if (sub === 'tracks') return <TagTrackRows query={query} navigate={navigate} />;
  if (sub === 'album' && entityKey != null) return <TagAlbum entityKey={entityKey} query={query} navigate={navigate} />;
  if (sub === 'track' && entityKey != null) return <TagTrack entityKey={entityKey} navigate={navigate} />;
  if (sub === 'albums') return <TagAlbumRows query={query} navigate={navigate} />;
  if (sub === 'artists') return <TagArtistRows query={query} navigate={navigate} />;
  if (sub === 'list') return <TagList query={query} navigate={navigate} />;
  if (sub === 'proposals') return <Proposals navigate={navigate} />;
  if (sub === 'proposalAlbums') return <ProposalAlbums query={query} navigate={navigate} />;
  return <Tags navigate={navigate} />;
}

/** HISTORY's pages: the overview and its subpages (rows, Counted once, Years, Wrapped, Top, the P1 comparison). */
function HistoryPage({ sub, query, navigate }: { sub?: string; query: string; navigate: (href: string) => void }) {
  if (sub === 'listens') return <HistoryRows query={query} navigate={navigate} />;
  if (sub === 'counted') return <HistoryCounted navigate={navigate} />;
  if (sub === 'years') return <HistoryYears navigate={navigate} />;
  if (sub === 'wrapped') return <HistoryWrapped query={query} navigate={navigate} />;
  if (sub === 'top') return <HistoryTop query={query} navigate={navigate} />;
  if (sub === 'compare') return <HistoryCompare navigate={navigate} />;
  return <History navigate={navigate} />;
}

/** LIBRARY's pages: the overview, the rows behind a number, the album and artist lists, an album, an artist, a
 *  track, and the listens behind their history numbers (T11), the P2 comparison (T12), PLAYLISTS (T24) and the
 *  Junction (T25), rooted to roaming (T26). */
function LibraryPage({ sub, entityKey, playlistRef, query, navigate }: { sub?: string; entityKey?: number; playlistRef?: string; query: string; navigate: (href: string) => void }) {
  if (sub === 'playlists') return <Playlists navigate={navigate} />;
  if (sub === 'playlist' && playlistRef) return <Playlist key={playlistRef} slug={playlistRef} navigate={navigate} />;
  if (sub === 'playlistRows' || sub === 'junctionRows') return <PlaylistRows query={query} navigate={navigate} />;
  if (sub === 'playlistCopies') return <PlaylistCopies query={query} navigate={navigate} />;
  if (sub === 'junction') return <Junction query={query} navigate={navigate} />;
  if (sub === 'reachRows') return <ReachRows query={query} navigate={navigate} />;
  if (sub === 'tracks') return <LibraryRows query={query} navigate={navigate} />;
  if (sub === 'albums' || sub === 'artists') return <LibraryList kind={sub} query={query} navigate={navigate} />;
  if (sub === 'plays') return <LibraryPlays query={query} navigate={navigate} />;
  if (sub === 'album' && entityKey != null) return <LibraryAlbum entityKey={entityKey} navigate={navigate} />;
  if (sub === 'artist' && entityKey != null) return <LibraryArtist entityKey={entityKey} navigate={navigate} />;
  if (sub === 'track' && entityKey != null) return <LibraryTrack entityKey={entityKey} navigate={navigate} />;
  if (sub === 'compare') return <LibraryCompare navigate={navigate} />;
  return <Library navigate={navigate} />;
}
