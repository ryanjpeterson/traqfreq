import { useCallback, useEffect, useState } from 'react';
import { MODULE_IDS, type ModuleId } from '../components/kit';

/** Each module's page. Its path is the module name in lower case (/library … /setup). */
export const MODULE_PATH: Record<ModuleId, string> = {
  L: '/library', H: '/history', T: '/tags', D: '/discover', M: '/mixes', F: '/fetch', S: '/setup',
};

export type Route =
  | { page: 'map' }
  | { page: 'search' }
  | { page: 'module'; module: ModuleId; sub?: 'listens' }
  | { page: 'notFound' };

/** HISTORY's rows page: the listens behind a number (query string = the filters). */
export const HISTORY_LISTENS = '/history/listens';

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/[?#].*$/, '').replace(/\/+$/, '') || '/';
  if (path === '/') return { page: 'map' };
  if (path === '/search') return { page: 'search' };
  if (path === HISTORY_LISTENS) return { page: 'module', module: 'H', sub: 'listens' };
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
