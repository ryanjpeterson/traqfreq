import { Card, Status, Text } from '../components/kit';
import { t, tf } from '../copy/t';
import { useGet } from '../app/api';
import { CUTOVERS_API, rowText, unixUtc, type Cutover, type Cutovers, type Run, type SwitchOff } from '../app/cutovers';

/** T30: P6's cut-overs on SETUP. Each cut-over's state; once traqfreq owns it, the switch-off check (jimbo-dj's side
 *  now against the copy's stamp, naming every row new on jimbo-dj's side); traqfreq's Plex sync (settings, watcher,
 *  the newest runs). Read-only: copies, rollbacks and syncs run with traqfreq-cutover. */
export function CutoversCard() {
  const load = useGet<Cutovers>(CUTOVERS_API);
  return (
    <Card label={t('cutover.card')}>
      <div className="stack">
        {load.state === 'loading' && <Text>{t('cutover.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('cutover.failed')} />}
        {load.state === 'ok' && <Body c={load.data} />}
      </div>
    </Card>
  );
}

const utc = (at: number | string | null | undefined) => unixUtc(at, t('time.utc'));

function Body({ c }: { c: Cutovers }) {
  return (
    <>
      {c.cutovers.map((x) => <CutoverPart key={x.name} x={x} />)}
      <Text variant="label">{t('cutover.sync')}</Text>
      <ul className="rows" aria-label={t('cutover.sync')}>
        <li><span>{t('cutover.plexUrl')}</span><span className="mono">{c.plex.url ?? t('cutover.notSet')}</span></li>
        <li><span>{t('cutover.plexToken')}</span><span>{t(c.plex.token_set ? 'cutover.set' : 'cutover.notSet')}</span></li>
        <li><span>{t('cutover.plexSection')}</span><span>{c.plex.section ?? t('cutover.onlyLibrary')}</span></li>
        <li><span>{t('cutover.pathMap')}</span><span className="mono">{c.plex.path_map ?? t('cutover.notSet')}</span></li>
        <li>
          <span>
            {t('cutover.watcher')}
            <span className="sub">
              {c.watcher.enabled ? [tf('cutover.watcherEvery', { n: c.watcher.interval }),
                c.watcher.checked_at && tf('cutover.watcherChecked', { at: utc(c.watcher.checked_at) }),
                c.watcher.scanning && t('cutover.watcherScanning'), c.watcher.error].filter(Boolean).join(' · ')
                : t('cutover.watcherOffWhy')}
            </span>
          </span>
          <Status state={c.watcher.enabled ? 'ready' : 'off'} label={t(c.watcher.enabled ? 'status.on' : 'status.off')} />
        </li>
      </ul>
      <Text variant="note">{`${t('cutover.settingsSource')} ${c.plex.env.join(', ')}`}</Text>
      <Text variant="label">{t('cutover.runs')}</Text>
      {c.runs.length === 0 ? <Text>{t('cutover.runsNone')}</Text> : (
        <ul className="rows" aria-label={t('cutover.runs')}>
          {c.runs.map((r) => <RunRow key={r.id} r={r} />)}
        </ul>
      )}
      <Text variant="note">{t('cutover.runsSource')}</Text>
    </>
  );
}

const STATE = {
  not_copied: { state: 'off', label: 'cutover.state.not_copied', why: 'cutover.why.not_copied' },
  owned: { state: 'ready', label: 'cutover.state.owned', why: 'cutover.why.owned' },
  rolled_back: { state: 'needs', label: 'cutover.state.rolled_back', why: 'cutover.why.rolled_back' },
} as const;

function CutoverPart({ x }: { x: Cutover }) {
  const s = STATE[x.state] ?? STATE.not_copied;
  return (
    <section className="stack" aria-label={x.title}>
      <ul className="rows">
        <li>
          <span><strong>{x.title}</strong><span className="sub">{x.tables.join(', ')}</span></span>
          <Status state={s.state} label={t(s.label)} />
        </li>
      </ul>
      <Text>{x.copied_at ? `${t(s.why)} ${tf('cutover.copiedAt', { at: utc(x.copied_at) })}` : t(s.why)}</Text>
      {x.switch_off && <SwitchOffPart s={x.switch_off} />}
    </section>
  );
}

function SwitchOffPart({ s }: { s: SwitchOff }) {
  if ('error' in s) {
    return <><Status state="needs" label={t('cutover.check.failed')} /><Text variant="note">{s.error}</Text></>;
  }
  const moved = s.tables.filter((x) => x.moved);
  const marks = Object.entries(s.marks).filter(([, m]) => m.moved);
  return (
    <>
      <Text variant="label">{t('cutover.check')}</Text>
      <Status state={s.clean ? 'ready' : 'needs'} label={t(s.clean ? 'cutover.check.clean' : 'cutover.check.moved')} />
      {s.clean ? <Text>{t('cutover.check.cleanWhy')}</Text> : (
        <>
          <Text>{tf('cutover.check.movedWhy', { n: s.missed.toLocaleString('en') })}</Text>
          <ul className="rows" aria-label={t('cutover.check')}>
            {moved.map((x) => (
              <li key={x.table} className="gate-field">
                <span>
                  <strong className="mono">{x.table}</strong>
                  <span className="sub">
                    {[tf('cutover.check.counts', { copied: (x.copied ?? 0).toLocaleString('en'), now: (x.now ?? 0).toLocaleString('en') }),
                      x.new != null && x.rule && tf('cutover.check.new', { n: x.new.toLocaleString('en'), rule: x.rule.where, since: String(x.rule.since ?? '–') })]
                      .filter(Boolean).join(' · ')}
                  </span>
                  {x.examples.map((r, i) => <span key={i} className="sub mono">{rowText(r)}</span>)}
                </span>
              </li>
            ))}
            {marks.map(([k, m]) => (
              <li key={k} className="gate-field">
                <span>
                  <strong className="mono">{k}</strong>
                  <span className="sub">{tf('cutover.check.mark', { copied: String(m.copied ?? '–'), now: String(m.now ?? '–') })}</span>
                </span>
              </li>
            ))}
          </ul>
          <Text variant="note">{t('cutover.check.fix')}</Text>
        </>
      )}
      <Text variant="note">{tf('cutover.check.source', { at: utc(s.checked_at) })}</Text>
    </>
  );
}

function RunRow({ r }: { r: Run }) {
  return (
    <li>
      <span>
        <strong>{`${utc(r.started_at)} · ${tf('unit.sec', { n: r.seconds })}`}</strong>
        <span className="sub">{r.note}</span>
        <span className="sub">{`${t('cutover.run.reason')}: ${r.reason} · ${t('cutover.run.undo')}: ${r.undo}`}</span>
      </span>
      <Status state={r.ok ? 'ready' : 'needs'} label={t(r.ok ? 'cutover.run.ok' : 'cutover.run.failed')} />
    </li>
  );
}
