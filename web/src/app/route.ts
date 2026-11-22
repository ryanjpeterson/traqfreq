import { useCallback, useEffect, useState } from 'react';
import { MODULE_IDS, type ModuleId } from '../components/kit';

/** Each module's page. Its path is the module name in lower case (/library … /setup). */
export const MODULE_PATH: Record<ModuleId, string> = {
  L: '/library', H: '/history', T: '/tags', D: '/discover', M: '/mixes', F: '/fetch', S: '/setup',
};

export type Route =
  | { page: 'map' }
  | { page: 'search' }
  | { page: 'module'; module: ModuleId }
  | { page: 'notFound' };

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (path === '/') return { page: 'map' };
  if (path === '/search') return { page: 'search' };
  const module = MODULE_IDS.find((m) => MODULE_PATH[m] === path);
  return module ? { page: 'module', module } : { page: 'notFound' };
}

/** A tiny History API router: the current path and a navigate function. */
export function usePath(): [string, (href: string) => void] {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const navigate = useCallback((href: string) => {
    if (href !== window.location.pathname) window.history.pushState(null, '', href);
    setPath(window.location.pathname);
    window.scrollTo?.(0, 0);
  }, []);
  return [path, navigate];
}
