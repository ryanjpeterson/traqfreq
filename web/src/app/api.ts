import { useEffect, useState } from 'react';
import type { ModuleId } from '../components/kit';

export type ModuleSwitch = { id: ModuleId; on: boolean; core: boolean };
export type MeasureId = 'tracks' | 'albums' | 'artists' | 'plays';
/** A number jimbo-dj shows, counted its way (rule = the SQL), next to the copy jimbo-dj last stored. */
export type Measure = {
  id: MeasureId; value: number; rule: string;
  jimbodj: { value: number; built_at: string | null; source: string } | null; matches: boolean | null;
};
export type Summary = {
  measures?: Measure[]; counts: Record<string, number>; missing_tables: string[]; times: Record<string, string>;
};
export type Job = {
  id: number; kind: string; source: string; at: string | null; rows: number | null; added: number | null; note: string | null;
};
export type Activity = { last_scan: { at: string; source: string } | null; jobs: Job[]; jobs_source: string | null };

/** Until /api/modules answers (or if it fails), only the core modules are on. */
export const CORE_ONLY: ModuleSwitch[] = (['L', 'H', 'T', 'D', 'M', 'F', 'S'] as ModuleId[])
  .map((id) => ({ id, on: id === 'L' || id === 'S', core: id === 'L' || id === 'S' }));

export type Load<T> = { state: 'loading' } | { state: 'ok'; data: T } | { state: 'failed' };

/** GET a JSON endpoint once. */
export function useGet<T>(url: string): Load<T> {
  const [load, setLoad] = useState<Load<T>>({ state: 'loading' });
  useEffect(() => {
    let live = true;
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((data: T) => live && setLoad({ state: 'ok', data }))
      .catch(() => live && setLoad({ state: 'failed' }));
    return () => { live = false; };
  }, [url]);
  return load;
}

/** The module switches, and whether the answer is in (false while loading). */
export function useModules(): [ModuleSwitch[], boolean] {
  const load = useGet<{ modules: ModuleSwitch[] }>('/api/modules');
  return [load.state === 'ok' ? load.data.modules : CORE_ONLY, load.state !== 'loading'];
}
