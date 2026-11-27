import { Button, Card, Status, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import {
  PLAYLISTS_GATE_API, PLAYLISTS_PATH, count, junctionHref, playlistHref, sourceRowsHref,
  type GateFeature, type GateTree, type PlaylistsGate,
} from '../app/playlists';
import { Num } from './Playlists';

/** T28: the P5 gate card, "Same tracks as jimbo-dj", on LIBRARY and SETUP. traqfreq's side: the ten trees with
 *  what each picks now (every number opens its rows), the kinds of condition they use between them, and the saved
 *  list check 3 compares. jimbo-dj's side is asked only by scripts/p5_gate.py, so the card says how to run it. */

type Nav = { navigate: (href: string) => void };

export function PlaylistsGateCard({ navigate }: Nav) {
  const load = useGet<PlaylistsGate>(PLAYLISTS_GATE_API);
  return (
    <Card label={t('p5gate.card')}>
      <div className="stack">
        {load.state === 'loading' && <Text>{t('p5gate.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('p5gate.failed')} />}
        {load.state === 'ok' && <GateBody g={load.data} navigate={navigate} />}
      </div>
    </Card>
  );
}

const featureName = (f: GateFeature) => t(`p5gate.feature.${f}` as StringKey);
const CHECK_NAMES: Record<string, StringKey> = { lines: 'p5gate.check.lines', tracks: 'p5gate.check.tracks', saved: 'p5gate.check.saved' };

function GateBody({ g, navigate }: { g: PlaylistsGate } & Nav) {
  const cov = g.coverage;
  const trees = count(cov.trees, 'tree');
  return (
    <>
      <Status state="needs" label={t('p5gate.status')} />
      <Text variant="note">{`${t('p5gate.statusWhy')} ${g.script}`}</Text>
      <ul className="rows" aria-label={t('p5gate.checks')}>
        {g.checks.map((c) => (
          <li key={c.check} className="gate-field">
            <span><strong>{t(CHECK_NAMES[c.check])}</strong><span className="sub">{c.rule}</span></span>
          </li>
        ))}
        <li className="gate-field">
          <span>
            <strong>{cov.ok ? tf('p5gate.coverage', { n: trees }) : tf('p5gate.coverageMissing', { n: trees, list: cov.missing.map(featureName).join(', ') })}</strong>
            <span className="sub">{cov.rule}</span>
          </span>
          <Status state={cov.ok ? 'ready' : 'needs'} label={t(cov.ok ? 'p5gate.coverageOk' : 'p5gate.coverageNot')} />
        </li>
      </ul>
      <Text variant="label">{t('p5gate.trees')}</Text>
      <ul className="rows pl-list" aria-label={t('p5gate.trees')}>
        {g.trees.map((x) => <TreeRow key={x.i} x={x} navigate={navigate} />)}
      </ul>
      <Text>
        {tf('p5gate.saved', { n: count(g.saved.count, 'playlist') })}{' '}
        <Button variant="quiet" href={PLAYLISTS_PATH} onClick={() => navigate(PLAYLISTS_PATH)}>{t('playlists.open')}</Button>
      </Text>
      <Text variant="note">{g.read_only}</Text>
    </>
  );
}

function TreeRow({ x, navigate }: { x: GateTree } & Nav) {
  const s = x.source;
  const href = s.kind === 'saved' ? playlistHref(s.slug ?? s.id) : junctionHref(x.query);
  const src = { tree: x.query };
  return (
    <li>
      <span className="pl-name">
        <Button variant="quiet" href={href} onClick={() => navigate(href)}>{s.name}</Button>
        <span className="sub">{[t(s.kind === 'saved' ? 'p5gate.tree.saved' : 'p5gate.tree.fixed'),
          x.lines ? count(x.lines.length, 'line') : null].filter(Boolean).join(' · ')}</span>
        <span className="sub">{tf('p5gate.tree.uses', { list: x.features.map(featureName).join(', ') })}</span>
        {x.error && <span className="sub">{tf('p5gate.tree.error', { why: x.error })}</span>}
      </span>
      {x.total !== undefined && x.picked !== undefined && (
        <span className="pl-switches">
          <Num href={sourceRowsHref(src, '', 'total')} label={tf('p5gate.tree.total', { n: count(x.total, 'track') })} of={s.name} navigate={navigate} />
          <Num href={sourceRowsHref(src, '', 'picked')} label={tf('p5gate.tree.picked', { n: count(x.picked, 'track') })} of={s.name} navigate={navigate} />
        </span>
      )}
    </li>
  );
}
