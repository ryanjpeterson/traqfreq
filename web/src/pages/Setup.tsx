import { Band, Card, LineBullet, Status, Text, type ModuleId } from '../components/kit';
import { t, tMaybe, type StringKey } from '../copy/t';
import { useGet, type Activity, type Measure, type ModuleSwitch, type Summary } from '../app/api';
import { formatUtc } from '../app/time';
import type { Compare } from '../app/periods';
import { CompareCard } from './HistoryCompare';

/** SETUP, read-only: what traqfreq can read from jimbo-dj's database, and which modules are on. */
export function Setup({ modules, navigate }: { modules: ModuleSwitch[]; navigate: (href: string) => void }) {
  const historyOn = modules.find((m) => m.id === 'H')?.on ?? false;
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
                {(summary.data.measures ?? []).length > 0 && (
                  <ul className="rows" aria-label={t('setup.measures')}>
                    {(summary.data.measures ?? []).map((m) => <MeasureRow key={m.id} m={m} />)}
                  </ul>
                )}
                <Text variant="label">{t('setup.db.raw')}</Text>
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

          {historyOn && <SetupCompare navigate={navigate} />}

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

/** One of jimbo-dj's numbers with the rule it uses (W3) and how it compares with jimbo-dj's stored copy. */
function MeasureRow({ m }: { m: Measure }) {
  const compare = m.jimbodj == null ? t('setup.measure.unstored')
    : m.matches ? t('setup.measure.same')
      : `${t('setup.measure.differs')}: ${m.jimbodj.value.toLocaleString('en')}`;
  return (
    <li>
      <span>
        <strong>{t(`setup.measure.${m.id}` as StringKey)}</strong>
        <span className="sub">{`${t(`setup.measure.${m.id}.rule` as StringKey)} ${compare}`}</span>
      </span>
      <span>{m.value.toLocaleString('en')}</span>
    </li>
  );
}

/** The P1 gate (T8): HISTORY's numbers next to jimbo-dj's stored ones. Only when HISTORY is on (L2). */
function SetupCompare({ navigate }: { navigate: (href: string) => void }) {
  const load = useGet<Compare>('/api/history/compare');
  return <CompareCard load={load} navigate={navigate} />;
}
