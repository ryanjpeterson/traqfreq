import { t } from '../copy/t';

/** 2026-11-05T02:00:00Z → "2026-11-05 02:00 UTC". */
export function formatUtc(iso: string): string {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]} ${t('time.utc')}` : iso;
}
