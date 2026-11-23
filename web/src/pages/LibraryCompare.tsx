import { useState } from 'react';
import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet, type Load } from '../app/api';
import { LIBRARY_COMPARE, MODULE_PATH } from '../app/route';
import { count, dayLabel, fmt } from '../app/history';
import { tracksHref, valueLabel, type GateField, type GateRow, type LibraryGate } from '../app/library';
import { CompareCard, summary } from './HistoryCompare';

type Nav = { navigate: (href: string) => void };

const short = (v: unknown) => {
  const s = JSON.stringify(v);
  return s && s.length > 120 ? `${s.slice(0, 117)}...` : String(s);
};

/** The P2 gate in one card, for SETUP and the LIBRARY page (T12). */
export function LibraryCompareCard({ load, navigate }: { load: Load<LibraryGate> } & Nav) {
  return <CompareCard load={load} navigate={navigate} label={t('libcompare.card')} href={LIBRARY_COMPARE} />;
}

/** Every LIBRARY number jimbo-dj stored (library.stats, library.charts) next to traqfreq's (P2 gate, T12). */
export function LibraryCompare({ navigate }: Nav) {
  const load = useGet<LibraryGate>('/api/library/compare');
  return (
    <>
      <Band module="L">{t('libcompare.sub')}</Band>
      <div className="page stack history library">
        <div><Button variant="quiet" href={MODULE_PATH.L} onClick={() => navigate(MODULE_PATH.L)}>{t('library.rows.back')}</Button></div>
        <Text variant="title">{t('libcompare.title')}</Text>
        <Text>{t('libcompare.intro')}</Text>
        {load.state === 'loading' && <Text>{t('libcompare.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('libcompare.failed')} />}
        {load.state === 'ok' && <GateBody g={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function GateBody({ g, navigate }: { g: LibraryGate } & Nav) {
  return (
    <>
      <Status state={g.passed ? 'ready' : 'needs'} label={t(g.passed ? 'compare.passed' : 'compare.notPassed')} />
      <Text>{summary(g)}</Text>
      <Text variant="note">{`${g.rules.fresh}. ${g.rules.passed}.`}</Text>
      {g.stored === 0 && <Text>{t('libcompare.none')}</Text>}
      {g.rows.map((r) => <GateSection key={r.name} r={r} navigate={navigate} />)}
      <Card label={t('libcompare.rules')}>
        <ul className="rows" aria-label={t('libcompare.rules')}>
          {Object.entries(g.chart_rules).map(([k, v]) => (
            <li key={k}><span><span className="mono">{k}</span><span className="sub">{v}</span></span></li>
          ))}
        </ul>
        <Text variant="note">{tf('libcompare.zone', { tz: g.timezone })}</Text>
      </Card>
      <Text variant="note">{tf('libcompare.notInP2', { what: Object.entries(g.not_in_p2).map(([k, v]) => `${k} (${v})`).join('; ') })}</Text>
    </>
  );
}

function GateSection({ r, navigate }: { r: GateRow } & Nav) {
  const title = t(`libcompare.${r.name}` as StringKey);
  const state = r.matches ? t('compare.match') : r.fresh ? t('compare.differs') : t('compare.differsStale');
  const id = `gate-${r.name.replace('.', '-')}`;
  return (
    <section aria-labelledby={id} className="stack">
      <div className="gate-head">
        <Text variant="heading" id={id}>{`${title} · ${r.name}`}</Text>
        <Status state={r.matches ? 'ready' : r.fresh ? 'needs' : 'off'} label={state} />
      </div>
      <Text variant="note">
        {[tf('compare.fields', { m: fmt(r.matching), n: count(r.compared, 'field') }),
          tf('libcompare.stamp', { built: r.built_at ? dayLabel(r.built_at.slice(0, 10)) : '?', fresh: r.fresh ? t('compare.fresh') : t('compare.stale') })].join(' · ')}
      </Text>
      <ul className="rows" aria-label={title}>
        {r.fields.map((f) => <FieldLine key={f.field} f={f} navigate={navigate} />)}
      </ul>
    </section>
  );
}

type Bar = { label: string; jd: unknown; tq: unknown; rows?: string };

/** A distribution's bars (a list of {label, value} or a {value: count} dict), jimbo-dj's next to traqfreq's. */
function bars(f: GateField): Bar[] | null {
  const rows = typeof f.rows === 'object' ? f.rows : undefined;
  const asMap = (v: unknown): Map<string, unknown> | null => {
    if (Array.isArray(v)) {
      if (!v.every((b) => b && typeof b === 'object' && 'label' in b && 'value' in b)) return null;
      return new Map(v.map((b) => [String((b as { label: unknown }).label), (b as { value: unknown }).value]));
    }
    if (v && typeof v === 'object' && Object.values(v).every((x) => typeof x === 'number')) return new Map(Object.entries(v));
    return null;
  };
  const jd = asMap(f.jimbodj);
  const tq = asMap(f.traqfreq) ?? new Map();
  if (!jd) return null;
  const labels = [...jd.keys(), ...[...tq.keys()].filter((k) => !jd.has(k))];
  return labels.map((label) => ({ label, jd: jd.get(label), tq: tq.get(label), rows: rows?.[label] }));
}

function FieldLine({ f, navigate }: { f: GateField } & Nav) {
  const [open, setOpen] = useState(false);
  const list = f.matches === null ? null : bars(f);
  const scalar = f.size === undefined;
  let detail: string;
  if (f.matches === null) detail = tf('libcompare.skipped', { why: f.skipped ?? '' });
  else if (scalar) detail = f.matches ? tf('libcompare.same', { v: short(f.jimbodj) }) : tf('libcompare.value', { jd: short(f.jimbodj), tq: short(f.traqfreq) });
  else {
    const n = count(list ? list.length : f.size ?? 0, list ? 'bar' : 'entry');
    detail = f.matches ? tf('libcompare.entries', { n }) : tf('libcompare.entriesDiffer', { n, diff: short(f.first_diff) });
  }
  const status = f.matches === null ? <Status state="off" label={t('libcompare.notCompared')} />
    : <Status state={f.matches ? 'ready' : 'needs'} label={t(f.matches ? 'compare.match' : 'compare.differs')} />;
  const rowsHref = typeof f.rows === 'string' ? tracksHref(f.rows) : null;
  return (
    <li className="gate-field">
      <span>
        <span className="mono">{f.field}</span>
        <span className="sub">{detail}</span>
        {rowsHref && (
          <span>
            <Button variant="quiet" href={rowsHref} onClick={() => navigate(rowsHref)}>
              {t('libcompare.showRows')}<span className="visually-hidden">{`, ${f.field}`}</span>
            </Button>
          </span>
        )}
        {list && list.length > 0 && (
          <span>
            <Button variant="quiet" onClick={() => setOpen(!open)}>
              {t(open ? 'libcompare.hideBars' : 'libcompare.showBars')}<span className="visually-hidden">{`, ${f.field}`}</span>
            </Button>
          </span>
        )}
        {open && list && (
          <ul className="rows gate-bars" aria-label={tf('libcompare.barsOf', { field: f.field })}>
            {list.map((b) => (
              <li key={b.label}>
                <span>
                  {b.rows != null ? (
                    <Button variant="quiet" href={tracksHref(b.rows)} onClick={() => navigate(tracksHref(b.rows!))}>{valueLabel(b.label)}</Button>
                  ) : <strong>{valueLabel(b.label)}</strong>}
                  <span className="sub">{tf('libcompare.bar', { jd: short(b.jd), tq: short(b.tq) })}</span>
                </span>
                {JSON.stringify(b.jd) !== JSON.stringify(b.tq) && <Status state="needs" label={t('compare.differs')} />}
              </li>
            ))}
          </ul>
        )}
      </span>
      {status}
    </li>
  );
}
