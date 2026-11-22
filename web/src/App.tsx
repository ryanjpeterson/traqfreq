import { useEffect, useState } from 'react';
import { t } from './copy/t';

type Summary = { counts: Record<string, number>; missing_tables: string[]; times: Record<string, string> };

/** The shell: chrome bar and the read-only legacy summary. Kit components arrive in T3. */
export function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch('/api/legacy/summary')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setSummary)
      .catch(() => setFailed(true));
  }, []);

  return (
    <>
      <header className="topbar">
        <span className="wordmark">{t('app.name')}</span>
      </header>
      <main>
        <h1>{t('shell.title')}</h1>
        <p>{t('shell.lede')}</p>
        {failed && <p>{t('shell.unavailable')}</p>}
        {!failed && !summary && <p>{t('shell.loading')}</p>}
        {summary && (
          <section aria-labelledby="counts-label">
            <p id="counts-label" className="label">{t('shell.countsLabel')}</p>
            <ul className="counts">
              {Object.entries(summary.counts).map(([table, n]) => (
                <li key={table}>
                  <span>{table}</span>
                  <span>{n.toLocaleString()} {t('shell.rows')}</span>
                </li>
              ))}
            </ul>
            {summary.missing_tables.length > 0 && (
              <p className="label">{t('shell.missingTables')}: {summary.missing_tables.join(', ')}</p>
            )}
          </section>
        )}
      </main>
    </>
  );
}
