import { Band, Card, LineBullet, Status, Text, type ModuleId } from '../components/kit';
import { t, tMaybe, type StringKey } from '../copy/t';
import { useGet, type Activity, type ModuleSwitch, type Summary } from '../app/api';
import { formatUtc } from '../app/time';

/** SETUP, read-only: what traqfreq can read from jimbo-dj's database, and which modules are on. */
export function Setup({ modules }: { modules: ModuleSwitch[] }) {
  const summary = useGet<Summary>('/api/legacy/summary');
  const activity = useGet<Activity>('/api/legacy/activity');
  return (
    <>
      <Band module="S">{t('setup.sub')}</Band>
      <div className="page stack">
        <Text>{t('setup.lede')}</Text>
        <div className="setup-grid">
          <Card label={t('setup.db')}>
            {summary.state === 'loading' && <Text>{t('setup.db.loading')}</Text>}
            {summary.state === 'failed' && (
              <div className="stack">
                <Status state="needs" label={t('setup.db.failed')} />
                <Text>{t('setup.db.failedBody')}</Text>
              </div>
            )}
            {summary.state === 'ok' && (
              <div className="stack">
                <Status state="ready" label={t('setup.db.ok')} />
                <ul className="rows" aria-label={t('setup.db')}>
                  {Object.entries(summary.data.counts).map(([table, n]) => (
                    <li key={table}>
                      <span className="mono">{table}</span>
                      <span>{`${n.toLocaleString('en')} ${t('setup.db.rows')}`}</span>
                    </li>
                  ))}
                </ul>
                {summary.data.missing_tables.length > 0 && (
                  <Text>{`${t('setup.db.missing')}: ${summary.data.missing_tables.join(', ')}`}</Text>
                )}
                <Text variant="note">{t('setup.db.source')}</Text>
              </div>
            )}
          </Card>

          <Card label={t('setup.scan')}>
            {activity.state === 'loading' && <Text>{t('setup.db.loading')}</Text>}
            {activity.state === 'failed' && <Status state="needs" label={t('setup.db.failed')} />}
            {activity.state === 'ok' && (
              <div className="stack">
                {activity.data.last_scan
                  ? <Text variant="heading">{formatUtc(activity.data.last_scan.at)}</Text>
                  : <Text>{t('setup.scan.none')}</Text>}
                <Text variant="note">{t('setup.scan.source')}</Text>
              </div>
            )}
          </Card>

          <Card label={t('setup.jobs')}>
            {activity.state === 'loading' && <Text>{t('setup.db.loading')}</Text>}
            {activity.state === 'failed' && <Status state="needs" label={t('setup.db.failed')} />}
            {activity.state === 'ok' && (
              <div className="stack">
                {activity.data.jobs.length === 0 ? <Text>{t('setup.jobs.none')}</Text> : (
                  <ul className="rows" aria-label={t('setup.jobs')}>
                    {activity.data.jobs.map((j) => (
                      <li key={j.id}>
                        <span>
                          <strong>{`${tMaybe(`source.${j.source}`) ?? j.source} ${t('setup.jobs.import')}`}</strong>
                          <span className="sub">
                            {[j.at && formatUtc(j.at), j.rows != null && `${j.rows.toLocaleString('en')} ${t('setup.jobs.rows')}`,
                              j.added != null && `${j.added.toLocaleString('en')} ${t('setup.jobs.added')}`, j.note]
                              .filter(Boolean).join(' · ')}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <Text variant="note">{t('setup.jobs.source')}</Text>
              </div>
            )}
          </Card>

          <Card label={t('setup.modules')}>
            <div className="stack">
              <ul className="rows" aria-label={t('setup.modules')}>
                {modules.map((m) => (
                  <li key={m.id}>
                    <span className="module-name">
                      <LineBullet module={m.id} size={24} decorative />
                      {t(`module.${m.id as ModuleId}` as StringKey)}
                    </span>
                    <Status state={m.on ? 'ready' : 'off'} label={t(m.on ? 'status.on' : 'status.off')} />
                  </li>
                ))}
              </ul>
              <Text variant="note">{t('setup.modules.source')}</Text>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
