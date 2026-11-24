import { useState, type ReactNode } from 'react';
import { Button, Card, Status, Text } from '../components/kit';
import { t, tf, tMaybe } from '../copy/t';
import { useGet } from '../app/api';
import { fmt } from '../app/history';
import {
  GATE_API, matchesHref, pairName, reasonName, serverName, tierIn,
  type GateOneToOne, type GateReasons, type ServersGate, type SpotAnswer, type SpotRow,
} from '../app/servers';

type Nav = { navigate: (href: string) => void };

const reasonsLine = (r: Record<string, number>) =>
  Object.entries(r).map(([k, n]) => `${reasonName(k)} ${fmt(n)}`).join(', ') || t('servers.none');

/** The P3 gate in one card on SETUP (T19): its three checks, each with its rows (W3). */
export function ServersGateCard({ navigate }: Nav) {
  const load = useGet<ServersGate>(GATE_API);
  return (
    <Card label={t('p3gate.card')}>
      <div className="stack">
        {load.state === 'loading' && <Text>{t('p3gate.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('p3gate.failed')} />}
        {load.state === 'ok' && <GateBody g={load.data} navigate={navigate} />}
      </div>
    </Card>
  );
}

function GateBody({ g, navigate }: { g: ServersGate } & Nav) {
  const [one, why, spot] = g.checks;
  return (
    <>
      <Status state={g.passed ? 'ready' : 'needs'} label={t(g.passed ? 'p3gate.passed' : 'p3gate.notPassed')} />
      <Text>{tf('p3gate.summary', { n: fmt(g.copies) })}</Text>
      <ul className="rows" aria-label={t('p3gate.checks')}>
        <CheckLine name={t('p3gate.one')} passed={one.passed} rule={one.rule}>
          {one.pairs.map((p) => <OneLine key={p.pair} p={p} navigate={navigate} />)}
        </CheckLine>
        <CheckLine name={t('p3gate.reasons')} passed={why.passed} rule={why.rule}>
          {why.pairs.map((p) => <ReasonLine key={p.pair} p={p} navigate={navigate} />)}
        </CheckLine>
        <CheckLine name={t('p3gate.spot')} passed={spot.passed} rule={spot.rule}>
          <span className="sub">
            {tf('p3gate.spot.summary', {
              n: fmt(spot.sample), cases: fmt(spot.cases), random: fmt(spot.random), seed: String(spot.seed),
              failed: fmt(spot.failed),
              asked: Object.entries(spot.asked).map(([s, n]) => `${serverName(s)} ${fmt(n)}`).join(', '),
            })}
          </span>
          {Object.keys(spot.problems).length > 0 && (
            <span className="sub">
              {tf('p3gate.spot.problems', {
                p: Object.entries(spot.problems).map(([k, n]) => `${problemName(k)} ${fmt(n)}`).join(', '),
              })}
            </span>
          )}
          <SpotRows rows={spot.rows} />
        </CheckLine>
      </ul>
      {g.notes.map((n) => <Text key={n}>{n}</Text>)}
      <Text variant="note">{`${g.rules.passed} ${g.read_only}`}</Text>
    </>
  );
}

function CheckLine({ name, passed, rule, children }: { name: string; passed: boolean; rule: string; children: ReactNode }) {
  return (
    <li className="gate-field">
      <span>
        <strong>{name}</strong>
        <span className="sub">{rule}</span>
        {children}
      </span>
      <Status state={passed ? 'ready' : 'needs'} label={t(passed ? 'p3gate.check.passed' : 'p3gate.check.notPassed')} />
    </li>
  );
}

function RowsLink({ q, what, navigate }: { q: string; what: string } & Nav) {
  const href = matchesHref(q);
  return (
    <span>
      <Button variant="quiet" href={href} onClick={() => navigate(href)}>
        {t('p3gate.rows')}<span className="visually-hidden">{`, ${what}`}</span>
      </Button>
    </span>
  );
}

function OneLine({ p, navigate }: { p: GateOneToOne } & Nav) {
  const name = pairName(p.pair);
  let line: string;
  if (p.missing) line = tf('p3gate.one.missing', { p: name });
  else if (p.server) {
    line = tf('p3gate.one.server', {
      p: name, m: fmt(p.visible_matched ?? 0), n: fmt(p.visible ?? 0), all: fmt(p.matched ?? 0), hidden: fmt(p.hidden_paths ?? 0),
    });
    const f = Object.entries(p.failures ?? {}).filter(([, n]) => n > 0);
    if (f.length) line += ` ${tf('p3gate.one.failures', { f: f.map(([k, n]) => `${problemName(k)} ${fmt(n)}`).join(', ') })}`;
  } else line = tf('p3gate.one.between', { p: name, all: fmt(p.matched ?? 0), twice: fmt(p.failures?.item_twice ?? 0) });
  return (
    <>
      <span className="sub">{`${p.passed ? '' : `${t('p3gate.check.notPassed')}: `}${line}`}</span>
      {!p.missing && <RowsLink q={`server=${p.pair}`} what={name} navigate={navigate} />}
    </>
  );
}

function ReasonLine({ p, navigate }: { p: GateReasons } & Nav) {
  const name = pairName(p.pair);
  if (p.missing || !p.sides) return <span className="sub">{tf('p3gate.one.missing', { p: name })}</span>;
  const side = (s: 'left' | 'right') => {
    const x = p.sides![s];
    return tf('p3gate.reasons.side', {
      s: serverName(p[s]!), u: fmt(x.unmatched), r: reasonsLine(x.reasons), m: fmt(x.matched), n: fmt(x.total),
    });
  };
  return (
    <>
      <span className="sub">{`${name}: ${side('left')}; ${side('right')}.${p.passed ? '' : ` ${t('p3gate.reasons.off')}`}`}</span>
      <RowsLink q={`server=${p.pair}`} what={name} navigate={navigate} />
    </>
  );
}

const problemName = (k: string) => tMaybe(`p3gate.problem.${k}`) ?? reasonName(k);

function answerLine(s: string, a: SpotAnswer): string {
  const head = serverName(s);
  if (a.status === 'unmatched') return tf('p3gate.answer.unmatched', { s: head, r: reasonName(a.reason ?? '') });
  if (a.status === 'error') return tf('p3gate.answer.error', { s: head, m: a.message ?? '' });
  const how = a.tier ? ` (${tierIn(a.tier)})` : a.reason ? ` (${reasonName(a.reason)})` : '';
  if (a.status === 'ok') {
    return a.diff_ms != null ? tf('p3gate.answer.ok', { s: head, how, d: (a.diff_ms / 1000).toFixed(1) })
      : tf('p3gate.answer.okItem', { s: head, how });
  }
  return tf('p3gate.answer.differs', { s: head, how, p: (a.problems ?? []).map(problemName).join(', ') });
}

function rowTitle(r: SpotRow): string {
  if (r.kind === 'copy') return [r.artist, r.title].filter(Boolean).join(' – ') || tf('servers.rows.copy', { k: String(r.rating_key) });
  if (r.kind === 'item') return tf('p3gate.row.item', { s: serverName(r.server ?? ''), id: r.id ?? '' });
  return tf('p3gate.row.pair', { p: pairName(r.pair!) });
}

function SpotRows({ rows }: { rows: SpotRow[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <span>
        <Button variant="quiet" onClick={() => setOpen(!open)}>
          {tf(open ? 'p3gate.spot.hide' : 'p3gate.spot.show', { n: fmt(rows.length) })}
        </Button>
      </span>
      {open && (
        <ul className="rows gate-bars gate-spot" aria-label={t('p3gate.spot.rows')}>
          {rows.map((r, i) => (
            <li key={`${r.kind}-${r.rating_key ?? r.id}-${i}`}>
              <span>
                <strong>{rowTitle(r)}</strong>
                <span className="sub">{r.why.map((w) => (w === 'random' ? t('p3gate.why.random') : w)).join(' · ')}</span>
                {Object.entries(r.servers).map(([s, a]) => <span key={s} className="sub">{answerLine(s, a!)}</span>)}
              </span>
              <Status state={r.passed ? 'ready' : 'needs'} label={t(r.passed ? 'p3gate.row.ok' : 'p3gate.row.off')} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
