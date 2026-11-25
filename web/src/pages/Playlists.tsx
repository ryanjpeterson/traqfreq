import { Band, Button, Card, ConditionChip, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { trackHref } from '../app/entities';
import { formatUtc } from '../app/time';
import {
  PLAYLISTS_PATH, count, kindName, playlistApi, playlistHref, rowsApi, rowsHref, serverName,
  type Condition, type Group, type Line, type LineRows, type Lines, type Node, type PlaylistList, type PlaylistPage,
  type PlaylistRow, type Switch, type TrackRow,
} from '../app/playlists';

/** T24: PLAYLISTS (P5), the Junction preview: jimbo-dj's saved playlists, their three switches and their lines,
 *  read-only. Every count opens its rows (W3). */

type Nav = { navigate: (href: string) => void };
type Operator = 'AND' | 'OR' | 'NOT';

function Num({ href, label, of, navigate }: { href: string; label: string; of?: string } & Nav) {
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Failed({ why }: { why?: StringKey }) {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('playlists.failed')} />
        <Text>{t(why ?? 'playlists.failedWhy')}</Text>
      </div>
    </Card>
  );
}

function Back({ href, label, navigate }: { href: string; label: string } & Nav) {
  return <div><Button variant="quiet" href={href} onClick={() => navigate(href)}>{label}</Button></div>;
}

// --- the switches -------------------------------------------------------------------------------------------

function switchState(s: Switch): { state: 'ready' | 'needs' | 'off'; label: string } {
  if (s.from === 'P6') return { state: 'off', label: t('playlists.switch.p6') };
  if (s.on && s.error) return { state: 'needs', label: t('playlists.switch.error') };
  return s.on ? { state: 'ready', label: t('playlists.switch.on') } : { state: 'off', label: t('playlists.switch.off') };
}

/** The three switches in one line (the list): each server with its state in words (C6). */
function SwitchLine({ switches }: { switches: Switch[] }) {
  return (
    <span className="pl-switches">
      {switches.map((s) => (
        <span key={s.server} className="pl-switch">
          <Status state={switchState(s).state} label={tf('playlists.switch.summary', { name: serverName(s.server), state: switchState(s).label })} />
        </span>
      ))}
    </span>
  );
}

/** The three switches with where each comes from (a playlist's page). */
function SwitchCard({ switches }: { switches: Switch[] }) {
  return (
    <Card label={t('playlists.switches')}>
      <div className="stack">
        <ul className="rows">
          {switches.map((s) => {
            const st = switchState(s);
            const sub = s.from === 'P6' ? s.rule
              : [t('playlists.switch.jimbodj'), s.pushed_at ? tf('playlists.switch.pushed', { at: formatUtc(new Date(s.pushed_at * 1000).toISOString()) })
                : t('playlists.switch.notPushed'), s.error].filter(Boolean).join(' · ');
            return (
              <li key={s.server}>
                <span><strong>{serverName(s.server)}</strong><span className="sub">{sub}</span></span>
                <Status state={st.state} label={st.label} />
              </li>
            );
          })}
        </ul>
        <Text variant="note">{t('playlists.switchesNote')}</Text>
      </div>
    </Card>
  );
}

// --- the list -----------------------------------------------------------------------------------------------

export function Playlists({ navigate }: Nav) {
  const load = useGet<PlaylistList>('/api/playlists');
  return (
    <>
      <Band module="L">{t('playlists.sub')}</Band>
      <div className="page stack history playlists">
        <Back href="/library" label={t('library.rows.back')} navigate={navigate} />
        <Text variant="title">{t('playlists.title')}</Text>
        <Text>{t('playlists.intro')}</Text>
        {load.state === 'loading' && <Text>{t('playlists.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.none' : undefined} />}
        {load.state === 'ok' && <ListBody p={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function ListBody({ p, navigate }: { p: PlaylistList } & Nav) {
  const head = [
    { k: 'count', label: t('playlists.saved'), text: count(p.count, 'playlist') },
    { k: 'with_lines', label: t('playlists.withLines'), text: count(p.with_lines, 'playlist') },
    { k: 'on', label: t('playlists.onPlex'), text: count(p.on.plex, 'playlist') },
    { k: 'stale', label: t('playlists.stale'), text: count(p.stale, 'playlist') },
  ];
  return (
    <>
      <ul className="rows" aria-label={t('playlists.saved')}>
        {head.map((h) => (
          <li key={h.k}>
            <span><strong>{h.label}</strong><span className="sub">{`${t('playlists.rule')}: ${p.rules[h.k] ?? ''}`}</span></span>
            <span className="hist-num">{h.text}</span>
          </li>
        ))}
      </ul>
      {p.kinds.map((k) => (
        <section key={k.kind} aria-labelledby={`pl-${k.kind}`}>
          <Text variant="label" id={`pl-${k.kind}`}>{`${kindName(k.kind)} · ${count(k.count, 'playlist')}`}</Text>
          <ul className="rows pl-list">
            {k.rows.map((r) => <ListRow key={r.id} r={r} navigate={navigate} />)}
          </ul>
        </section>
      ))}
    </>
  );
}

function ListRow({ r, navigate }: { r: PlaylistRow } & Nav) {
  const sub = [tf('playlists.tracksIn', { n: count(r.tracks, 'track') }), r.lines ? count(r.lines, 'line') : t('playlists.noLines'),
    r.stale && t('playlists.staleNote')].filter(Boolean).join(' · ');
  return (
    <li>
      <span className="pl-name">
        <Num href={playlistHref(r.slug)} label={r.name} navigate={navigate} />
        <span className="sub">{sub}</span>
      </span>
      <SwitchLine switches={r.switches} />
    </li>
  );
}

/** The card on LIBRARY's overview. */
export function PlaylistsCard({ navigate }: Nav) {
  const load = useGet<PlaylistList>('/api/playlists');
  if (load.state !== 'ok') return null;
  return (
    <Card label={t('playlists.card')}>
      <div className="stack">
        <Text>{tf('playlists.cardBody', { n: count(load.data.count, 'playlist'), m: load.data.with_lines })}</Text>
        <div><Button variant="secondary" href={PLAYLISTS_PATH} onClick={() => navigate(PLAYLISTS_PATH)}>{t('playlists.open')}</Button></div>
      </div>
    </Card>
  );
}

// --- one playlist -------------------------------------------------------------------------------------------

export function Playlist({ slug, navigate }: { slug: string } & Nav) {
  const load = useGet<PlaylistPage>(playlistApi(slug));
  return (
    <>
      <Band module="L">{t('playlists.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={PLAYLISTS_PATH} label={t('playlists.back')} navigate={navigate} />
        {load.state === 'loading' && <Text>{t('playlists.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && <PlaylistBody p={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

const madeBy = (m: string | null) => t(`playlists.madeBy.${m && ['rules', 'filter', 'mix', 'cluster', 'radio'].includes(m) ? m : 'other'}` as StringKey);

function PlaylistBody({ p, navigate }: { p: PlaylistPage } & Nav) {
  const r = p.playlist;
  return (
    <>
      <Text variant="title">{r.name}</Text>
      <Text variant="note">{[kindName(r.kind), `${t('playlists.from')}: ${madeBy(r.made_by)}`, r.stale && t('playlists.staleNote')].filter(Boolean).join(' · ')}</Text>
      {r.summary && <Text>{r.summary}</Text>}
      <div className="hist-grid">
        <SwitchCard switches={r.switches} />
      </div>
      {p.lines_error && <Card><Status state="needs" label={tf('playlists.linesError', { e: p.lines_error })} /></Card>}
      {p.lines && <LinesView l={p.lines} slug={r.slug} navigate={navigate} />}
      <Stored p={p} navigate={navigate} />
    </>
  );
}

function LinesView({ l, slug, navigate }: { l: Lines; slug: string } & Nav) {
  return (
    <section aria-labelledby="pl-lines" className="stack">
      <Text variant="label" id="pl-lines">{t('playlists.lines')}</Text>
      <Text>{tf('playlists.linesSummary', { lines: count(l.lines.length, 'line'), n: l.n, total: count(l.total, 'track'), library: count(l.library, 'track') })}</Text>
      <Text variant="note">{`${t('playlists.rule')}: ${l.rules.count}. ${t('playlists.linesNote')}`}</Text>
      <div className="hist-grid">
        {l.lines.map((x) => <LineCard key={x.id} x={x} n={l.n} slug={slug} navigate={navigate} />)}
      </div>
    </section>
  );
}

function LineCard({ x, n, slug, navigate }: { x: Line; n: number; slug: string } & Nav) {
  return (
    <Card label={x.label ? `${tf('playlists.line', { id: x.id })} · ${x.label}` : tf('playlists.line', { id: x.id })}>
      <div className="stack">
        <Text>{x.words}</Text>
        <ul className="rows">
          <li>
            <span><strong>{t('playlists.lineMatches')}</strong><span className="sub">{tf('playlists.lineShare', { n: x.share, of: n })}</span></span>
            {x.count > 0 ? <Num href={rowsHref(slug, x.id)} label={count(x.count, 'track')} of={x.words} navigate={navigate} />
              : <span className="hist-num">{count(0, 'track')}</span>}
          </li>
        </ul>
        <Text variant="label">{t('playlists.conditions')}</Text>
        <Tree node={x.match} slug={slug} line={x.id} navigate={navigate} />
      </div>
    </Card>
  );
}

const OPS: { part: 'all' | 'any' | 'not'; op: Operator; label: StringKey }[] = [
  { part: 'all', op: 'AND', label: 'playlists.op.all' }, { part: 'any', op: 'OR', label: 'playlists.op.any' },
  { part: 'not', op: 'NOT', label: 'playlists.op.not' },
];

/** A line's conditions: each group's AND, OR and NOT parts, each condition a chip with its count (nesting shown by
 *  indent; a screen reader hears each part's operator in words). */
function Tree({ node, slug, line, navigate }: { node: Node; slug: string; line: string } & Nav) {
  if (node.type === 'condition') return <ul className="pl-tree"><Leaf c={node} op="AND" slug={slug} line={line} navigate={navigate} /></ul>;
  return <GroupView g={node} slug={slug} line={line} navigate={navigate} />;
}

function GroupView({ g, slug, line, navigate }: { g: Group; slug: string; line: string } & Nav) {
  return (
    <ul className="pl-tree">
      {OPS.filter((o) => g[o.part]?.length).map((o) => (
        <li key={o.part} className="pl-part">
          <span className="visually-hidden">{t(o.label)}</span>
          <ul className="pl-tree">
            {g[o.part]!.map((x) => x.type === 'condition'
              ? <Leaf key={x.path} c={x} op={o.op} slug={slug} line={line} navigate={navigate} />
              : (
                <li key={x.path} className="pl-group">
                  <span className="pl-row">
                    <ConditionChip op={o.op}>{`${t('playlists.group')}: ${x.words}`}</ConditionChip>
                    <CountLink n={x.count} slug={slug} line={line} path={x.path} of={x.words} navigate={navigate} />
                  </span>
                  <GroupView g={x} slug={slug} line={line} navigate={navigate} />
                </li>
              ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function Leaf({ c, op, slug, line, navigate }: { c: Condition; op: Operator; slug: string; line: string } & Nav) {
  return (
    <li className="pl-row">
      <ConditionChip op={op}>{c.text}</ConditionChip>
      <CountLink n={c.count} slug={slug} line={line} path={c.path} of={c.text} navigate={navigate} />
    </li>
  );
}

function CountLink({ n, slug, line, path, of, navigate }: { n: number; slug: string; line: string; path: string; of: string } & Nav) {
  if (n === 0) return <span className="hist-num">{count(0, 'track')}</span>;
  return <Num href={rowsHref(slug, line, path)} label={count(n, 'track')} of={of} navigate={navigate} />;
}

function Stored({ p, navigate }: { p: PlaylistPage } & Nav) {
  const s = p.stored;
  return (
    <section aria-labelledby="pl-stored" className="stack">
      <Text variant="label" id="pl-stored">{`${t('playlists.stored')} · ${count(s.count, 'track')}`}</Text>
      <Text variant="note">{`${tf('playlists.storedNote', { live: count(s.live, 'track') })}${s.count > s.rows.length ? ` ${tf('playlists.storedMore', { n: s.rows.length })}` : ''}`}</Text>
      <TrackList rows={s.rows} why={(i) => tf('playlists.storedWhy', { n: s.offset + i + 1 })} navigate={navigate} />
    </section>
  );
}

function TrackList({ rows, why, navigate }: { rows: TrackRow[]; why: (i: number) => string } & Nav) {
  return (
    <div className="pl-tracks">
      {rows.map((r, i) => (
        <StationRow key={`${r.rating_key}-${i}`} position={i + 1} module="L" title={r.title} artist={r.artist}
          why={r.live ? why(i) : `${why(i)} ${t('playlists.removed')}.`}
          href={r.live ? trackHref(r.rating_key) : undefined} onNavigate={navigate} />
      ))}
    </div>
  );
}

// --- the rows behind a count --------------------------------------------------------------------------------

export function PlaylistRows({ query, navigate }: { query: string } & Nav) {
  const load = useGet<LineRows>(rowsApi(query));
  const ref = new URLSearchParams(query).get('ref') ?? '';
  return (
    <>
      <Band module="L">{t('playlists.rows.sub')}</Band>
      <div className="page stack history playlists">
        <Back href={playlistHref(ref)} label={t('playlists.rows.back')} navigate={navigate} />
        <Text variant="title">{t('playlists.rows.title')}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed why={load.status === 404 ? 'playlists.notFound' : undefined} />}
        {load.state === 'ok' && (
          <>
            <Text>{`${load.data.words} · ${count(load.data.count, 'track')}`}</Text>
            <Text variant="note">{t('playlists.rows.note')}</Text>
            <TrackList rows={load.data.rows} why={() => tf('playlists.rows.why', { words: load.data.words })} navigate={navigate} />
          </>
        )}
      </div>
    </>
  );
}
