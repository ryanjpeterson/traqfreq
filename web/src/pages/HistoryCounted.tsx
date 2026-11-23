import { Band, Button, Card, Status, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { formatUtc } from '../app/time';
import {
  count, duration, fmt, localTime, sourceName,
  type CheckReport, type Counted, type Finding, type GapBucket, type GapPair,
} from '../app/history';
import { RowsLink } from './History';

type Nav = { navigate: (href: string) => void };
type CheckId = 'burst' | 'loop' | 'rhythm';
const CHECKS: CheckId[] = ['burst', 'loop', 'rhythm'];

/** "Up to 10 s", "Over 30 s, up to 1 min". */
export function bucketLabel(b: GapBucket, i: number, all: GapBucket[]): string {
  return i === 0 ? tf('counted.bucket.first', { b: duration(b.max) })
    : tf('counted.bucket.range', { a: duration(all[i - 1].max), b: duration(b.max) });
}

/** Counted once (T7): the listen each repeat and duplicate is of and how far apart, then the read-only checks. */
export function HistoryCounted({ navigate }: Nav) {
  const load = useGet<Counted>('/api/history/counted');
  return (
    <>
      <Band module="H">{t('counted.sub')}</Band>
      <div className="page stack history">
        <div><Button variant="quiet" href={MODULE_PATH.H} onClick={() => navigate(MODULE_PATH.H)}>{t('counted.back')}</Button></div>
        <Text variant="title">{t('counted.title')}</Text>
        <Text>{t('counted.intro')}</Text>
        {load.state === 'loading' && <Text>{t('counted.loading')}</Text>}
        {load.state === 'failed' && (
          <Card>
            <div className="stack">
              <Status state="needs" label={t('history.failed')} />
              <Text>{t('history.failedBody')}</Text>
            </div>
          </Card>
        )}
        {load.state === 'ok' && <CountedBody c={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function CountedBody({ c, navigate }: { c: Counted } & Nav) {
  const g = c.gaps;
  const tz = c.timezone ?? 'UTC';
  return (
    <>
      <section aria-labelledby="c-gaps" className="stack">
        <Text variant="label" id="c-gaps">{t('counted.gaps')}</Text>
        <Text>
          {tf('counted.gaps.summary', {
            repeats: count(g.repeats, 'listen'),
            duplicates: count(g.duplicates, 'listen'),
            found: g.not_found ? tf('counted.gaps.someMissing', { n: count(g.not_found, 'listen') }) : t('counted.gaps.allFound'),
          })}
        </Text>
        <Text variant="note">{t('counted.gaps.rule')}</Text>
        <div className="hist-sources">
          {g.pairs.map((p) => <PairCard key={`${p.source}-${p.of}`} p={p} navigate={navigate} />)}
        </div>
      </section>

      <section aria-labelledby="c-checks" className="stack">
        <Text variant="label" id="c-checks">{t('counted.checks')}</Text>
        <Text variant="note">{tf('counted.checks.rule', { n: count(c.checks.plays_checked, 'play') })}</Text>
        <div className="hist-sources">
          {CHECKS.map((k) => <CheckCard key={k} id={k} r={c.checks[k]} tz={tz} navigate={navigate} />)}
        </div>
      </section>

      {c.cache && (
        <Text variant="note">
          {tf('history.cache', { at: formatUtc(new Date(c.cache.built_at * 1000).toISOString()), s: c.cache.seconds })}
        </Text>
      )}
    </>
  );
}

function PairCard({ p, navigate }: { p: GapPair } & Nav) {
  const label = p.kind === 'repeat'
    ? tf('counted.pair.repeat', { source: sourceName(p.source) })
    : tf('counted.pair.duplicate', { source: sourceName(p.source), of: sourceName(p.of) });
  const window = p.windows.length > 1
    ? tf('counted.pair.windows', { a: duration(p.windows[0]), b: duration(p.windows[p.windows.length - 1]) })
    : tf('counted.pair.window', { w: duration(p.windows[0]) });
  const most = Math.max(1, ...p.buckets.map((b) => b.listens), p.not_found);
  const base = { status: p.kind, source: p.source, of: p.of } as const;
  // Only the buckets inside this pair's window (a repeat's window is 30 s), so the list isn't padded with zeros.
  const widest = p.windows[p.windows.length - 1];
  const shown = p.buckets.filter((b) => b.min <= widest);
  return (
    <Card label={label}>
      <div className="stack">
        <Text variant="note">
          {`${count(p.listens, 'listen')}. ${window}`}
        </Text>
        <ul className="rows hist-top" aria-label={label}>
          {shown.map((b, i) => (
            <li key={b.min}>
              <span className="hist-top-text">
                <strong>{bucketLabel(b, i, p.buckets)}</strong>
                <span className="hist-bar" aria-hidden="true"><span style={{ width: `${(100 * b.listens) / most}%` }} /></span>
              </span>
              <RowsLink n={b.listens} unit="listen" filter={{ ...base, gap: `${b.min}-${b.max}` }} navigate={navigate} />
            </li>
          ))}
          <li>
            <span className="hist-top-text">
              <strong>{t('counted.bucket.none')}</strong>
              <span className="hist-bar" aria-hidden="true"><span style={{ width: `${(100 * p.not_found) / most}%` }} /></span>
            </span>
            <RowsLink n={p.not_found} unit="listen" filter={{ ...base, gap: 'none' }} navigate={navigate} />
          </li>
          {p.beyond > 0 && (
            <li>
              <span><strong>{t('counted.bucket.beyond')}</strong></span>
              <span className="hist-num">{count(p.beyond, 'listen')}</span>
            </li>
          )}
        </ul>
      </div>
    </Card>
  );
}

function CheckCard({ id, r, tz, navigate }: { id: CheckId; r: CheckReport; tz: string } & Nav) {
  const name = t(`counted.${id}` as StringKey);
  const found = id === 'burst'
    ? tf('counted.burst.found', { n: count(r.findings, 'finding'), held: count(r.plays, 'play') })
    : tf('counted.found', { n: count(r.findings, 'finding'), plays: count(r.plays, 'play') });
  return (
    <Card label={name}>
      <div className="stack">
        <Status state="off" label={t('counted.report')} />
        <Text>{t(`counted.${id}.body` as StringKey)}</Text>
        <Text variant="heading">{found}</Text>
        {r.findings === 0 ? <Text>{t('counted.none')}</Text> : (
          <>
            <Text variant="label">{tf('counted.newest', { n: fmt(r.newest.length) })}</Text>
            <ul className="rows" aria-label={name}>
              {r.newest.map((f) => <FindingRow key={f.start} f={f} tz={tz} navigate={navigate} />)}
            </ul>
          </>
        )}
        <Text variant="note">{tf('counted.rule', { rule: r.rule })}</Text>
      </div>
    </Card>
  );
}

function FindingRow({ f, tz, navigate }: { f: Finding; tz: string } & Nav) {
  const what = f.songs === 1 ? [f.artist, f.title].filter(Boolean).join(' · ') : '';
  return (
    <li>
      <span>
        <strong>{tf('counted.finding', { when: localTime(f.first, tz), tz, plays: count(f.plays, 'play'), songs: count(f.songs, 'song') })}</strong>
        <span className="sub">
          {[what, f.gap_s != null && tf('counted.finding.gap', { gap: duration(f.gap_s) }),
            Object.entries(f.sources).map(([s, n]) => `${sourceName(s)} ${fmt(n)}`).join(' · ')].filter(Boolean).join(' · ')}
        </span>
      </span>
      <RowsLink n={f.plays} unit="play" filter={{ status: 'play', start: f.start, end: f.end }} navigate={navigate} />
    </li>
  );
}
