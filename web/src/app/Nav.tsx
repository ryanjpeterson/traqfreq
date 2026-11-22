import { NavItem, type ModuleId } from '../components/kit';
import { t } from '../copy/t';
import type { ModuleSwitch } from './api';
import { MODULE_PATH, type Route } from './route';

type Props = { modules: ModuleSwitch[]; route: Route; navigate: (href: string) => void };

/** L1: LIBRARY, the switched-on modules in order, SETUP. Off modules leave no trace (L2). */
export function navModules(modules: ModuleSwitch[]): ModuleId[] {
  const on = new Set(modules.filter((m) => m.on).map((m) => m.id));
  const middle = (['H', 'T', 'D', 'M', 'F'] as ModuleId[]).filter((m) => on.has(m));
  return ['L', ...middle, 'S'];
}

/** L3: the phone bar holds five at most: LIBRARY, up to two modules, the map (the way to every line), SETUP. */
export function phoneModules(modules: ModuleSwitch[]): ModuleId[] {
  const middle = navModules(modules).slice(1, -1);
  return ['L', ...middle.slice(0, 2), 'S'];
}

const isCurrent = (route: Route, m: ModuleId) => route.page === 'module' && route.module === m;

/** The chrome: wordmark, the lines, search. Compact on tablets (L4); on phones the lines move to the bottom bar. */
export function TopBar({ modules, route, navigate }: Props) {
  return (
    <header className="topbar">
      <NavItem label={t('app.name')} href="/" wordmark current={route.page === 'map'} onNavigate={navigate} />
      <nav className="topbar-lines" aria-label={t('nav.label')}>
        {navModules(modules).map((m) => (
          <NavItem key={m} module={m} href={MODULE_PATH[m]} current={isCurrent(route, m)} onNavigate={navigate} />
        ))}
      </nav>
      <div className="topbar-search">
        <NavItem label={t('nav.search')} href="/search" current={route.page === 'search'} onNavigate={navigate} />
      </div>
    </header>
  );
}

/** Phone only (CSS shows it under 600 px): a 76 px bar of at most five. */
export function BottomBar({ modules, route, navigate }: Props) {
  const ms = phoneModules(modules);
  const items = ms.slice(0, -1).map((m) => (
    <NavItem key={m} module={m} href={MODULE_PATH[m]} current={isCurrent(route, m)} onNavigate={navigate} />
  ));
  return (
    <nav className="bottombar" aria-label={t('nav.label')}>
      {items}
      <NavItem label={t('nav.map')} href="/" current={route.page === 'map'} onNavigate={navigate} />
      <NavItem module="S" href={MODULE_PATH.S} current={isCurrent(route, 'S')} onNavigate={navigate} />
    </nav>
  );
}
