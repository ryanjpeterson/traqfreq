import { lazy, Suspense, useEffect } from 'react';
import { t, type StringKey } from './copy/t';
import { useModules } from './app/api';
import { BottomBar, TopBar } from './app/Nav';
import { parseRoute, usePath, type Route } from './app/route';
import { History } from './pages/History';
import { HistoryCompare } from './pages/HistoryCompare';
import { HistoryCounted } from './pages/HistoryCounted';
import { HistoryRows } from './pages/HistoryRows';
import { HistoryTop } from './pages/HistoryTop';
import { HistoryWrapped } from './pages/HistoryWrapped';
import { HistoryYears } from './pages/HistoryYears';
import { MapHome } from './pages/MapHome';
import { ModulePage } from './pages/ModulePage';
import { NotFound } from './pages/NotFound';
import { Search } from './pages/Search';
import { Setup } from './pages/Setup';
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
        {r.page === 'module' && r.module === 'S' && <Setup modules={modules} navigate={navigate} />}
        {r.page === 'module' && r.module === 'H' && !waiting && <HistoryPage sub={r.sub} query={path.replace(/^[^?]*/, '')} navigate={navigate} />}
        {r.page === 'module' && r.module !== 'S' && r.module !== 'H' && !waiting && <ModulePage module={r.module} navigate={navigate} />}
        {r.page === 'notFound' && <NotFound navigate={navigate} />}
      </main>
      <BottomBar modules={modules} route={r} navigate={navigate} />
    </>
  );
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
