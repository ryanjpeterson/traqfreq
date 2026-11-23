import type { ReactNode } from 'react';
import { Band, Button, Card, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, tMaybe, type StringKey } from '../copy/t';
import { useGet, type Load } from '../app/api';
import { MODULE_PATH } from '../app/route';
import { duration, fmt } from '../app/history';
import { trackHref } from '../app/entities';
import { formatUtc } from '../app/time';
import {
  OTHER_SERVERS, SERVERS_PATH, ageLabel, copiesApi, matchesApi, copiesHref, copiesTitle, copyQuery, matchQuery, matchesHref, matchesTitle,
  pairName, reasonName, serverName, tierIn, tierName,
  type Copies, type Copy, type Identity, type Item, type MatchRow, type Matches, type Pair, type PairId, type ServerId,
  type ServerStatus, type Servers, type Snapshot,
} from '../app/servers';

type Nav = { navigate: (href: string) => void };

const PAIRS: PairId[] = ['jellyfin', 'navidrome', 'jellyfin-navidrome'];
const rule = (text: string | undefined) => `${t('library.rule')}: ${text ?? ''}`;
const unixUtc = (s: number) => formatUtc(new Date(s * 1000).toISOString());
type Unit = 'copy' | 'item' | 'file' | 'song' | 'key';
/** "1 copy", "14 items" (W3: numbers carry units). */
export const n = (v: number, unit: Unit) => `${fmt(v)} ${t(`servers.unit.${unit}.${v === 1 ? 'one' : 'other'}` as StringKey)}`;

function Back({ href, label, navigate }: { href: string; label: string } & Nav) {
  return <div><Button variant="quiet" href={href} onClick={() => navigate(href)}>{label}</Button></div>;
}

/** A number that opens its rows (W3), or plain text at zero. */
function RowsLink({ text, href, what, navigate }: { text: string; href: string | null; what: string } & Nav) {
  if (!href) return <span className="hist-num">{text}</span>;
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {text}<span className="visually-hidden">{`, ${tf('servers.showRows', { what })}`}</span>
    </Button>
  );
}

function Failed({ load }: { load: { state: 'failed'; status?: number } }) {
  return (
    <div className="stack">
      <Status state="needs" label={t('servers.failed')} />
      <Text>{t(load.status === 404 ? 'servers.failed.noLibrary' : 'servers.failed.body')}</Text>
    </div>
  );
}

// --- SETUP's SERVERS page --------------------------------------------------------------------------------

/** SETUP → SERVERS (T15): the three servers, Plex's side of each copy, the matches by tier and reason, a song's three IDs. */
export function SetupServers({ query, navigate }: { query: string } & Nav) {
  const servers = useGet<Servers>('/api/servers');
  const identity = useGet<Identity>('/api/servers/identity');
  const matches = useGet<Matches>('/api/servers/matches');
  return (
    <>
      <Band module="S">{t('servers.sub')}</Band>
      <div className="page stack servers">
        <Back href={MODULE_PATH.S} label={t('servers.back')} navigate={navigate} />
        <Text variant="title">{t('servers.title')}</Text>
        <Text>{t('servers.intro')}</Text>
        <Text variant="note">{t('servers.readOnly')}</Text>
        <section className="stack" aria-labelledby="srv-three">
          <Text variant="heading" id="srv-three">{t('servers.three')}</Text>
          {servers.state === 'loading' && <Text>{t('servers.loading')}</Text>}
          {servers.state === 'failed' && <Card><Failed load={servers} /></Card>}
          {servers.state === 'ok' && (
            <div className="setup-grid">
              {servers.data.servers.map((s) => (
                <ServerCard key={s.server} s={s} snap={matches.state === 'ok' ? matches.data.snapshots.find((x) => x.server === s.server) : undefined} />
              ))}
            </div>
          )}
        </section>
        <IdentityCard load={identity} navigate={navigate} />
        <section className="stack" aria-labelledby="srv-matches">
          <Text variant="heading" id="srv-matches">{t('servers.matches')}</Text>
          {matches.state === 'loading' && <Text>{t('servers.loading')}</Text>}
          {matches.state === 'failed' && <Card><Failed load={matches} /></Card>}
          {matches.state === 'ok' && (
            <>
              <Text variant="note">{t('servers.matches.how')}</Text>
              <div className="hist-grid">
                {PAIRS.map((p) => {
                  const pair = matches.data.pairs.find((x) => x.pair === p);
                  return pair ? <PairCard key={p} p={pair} navigate={navigate} /> : <MissingPair key={p} p={p} snaps={matches.data.snapshots} />;
                })}
              </div>
            </>
          )}
        </section>
        <ThreeIdsCard query={query} navigate={navigate} />
      </div>
    </>
  );
}

/** One server's column: set up or not (secrets only as set), and how old its snapshot is; Plex is jimbo-dj's sync. */
function ServerCard({ s, snap }: { s: ServerStatus; snap?: Snapshot }) {
  const plex = s.server === 'plex';
  return (
    <Card label={serverName(s.server)}>
      <div className="stack">
        {plex
          ? <Status state={s.read ? 'ready' : 'needs'} label={t(s.read ? 'servers.plex.read' : 'servers.plex.unread')} />
          : <Status state={s.set_up ? 'ready' : 'off'} label={t(s.set_up ? 'servers.setUp' : 'servers.notSetUp')} />}
        <ul className="rows lib-paths" aria-label={tf('servers.facts', { s: serverName(s.server) })}>
          {plex && s.server_name && <Fact label={t('servers.plex.name')}>{s.server_name}</Fact>}
          {plex && s.version && <Fact label={t('servers.plex.version')}>{s.version}</Fact>}
          {plex && s.last_sync != null && <Fact label={t('servers.plex.sync')}>{unixUtc(s.last_sync)}</Fact>}
          {plex && s.tracks != null && <Fact label={t('servers.plex.tracks')}>{n(s.tracks, 'copy')}</Fact>}
          {!plex && s.url && <Fact label={t('servers.url')} mono>{s.url}</Fact>}
          {s.settings.map((x) => (
            <Fact key={x.env} label={x.env} mono>
              {!x.set ? t('servers.setting.unset') : x.secret ? t('servers.setting.secret') : (x.value ?? t('servers.setting.set'))}
            </Fact>
          ))}
        </ul>
        {plex ? <Text variant="note">{t('servers.plex.snapshot')}</Text> : <SnapshotLine snap={snap} s={s.server} />}
        {s.note && <Text variant="note">{s.note}</Text>}
      </div>
    </Card>
  );
}

function SnapshotLine({ snap, s }: { snap?: Snapshot; s: ServerId }) {
  if (!snap) return null;
  if (!snap.snapshot) {
    return (
      <div className="stack">
        <Status state="needs" label={t('servers.snapshot.none')} />
        <Text variant="note">{tf('servers.snapshot.noneWhy', { s: serverName(s) })}</Text>
      </div>
    );
  }
  return (
    <div className="stack">
      <Text>{tf('servers.snapshot.age', { age: ageLabel(snap.age_s), n: n(snap.items, 'item') })}</Text>
      <Text variant="note">
        {[tf('servers.snapshot.read', { at: unixUtc(snap.read_at) }),
          tf('servers.snapshot.folders', { f: snap.folders.join(', ') || t('servers.none'), why: snap.folder_rule }),
          snap.hidden_paths > 0 ? tf('servers.snapshot.hidden', { n: n(snap.hidden_paths, 'item') }) : ''].filter(Boolean).join(' · ')}
      </Text>
    </div>
  );
}

function Fact({ label, sub, children, mono = false }: { label: string; sub?: string; children: ReactNode; mono?: boolean }) {
  return (
    <li>
      <span><strong className={mono ? 'mono' : undefined}>{label}</strong>{sub && <span className="sub">{sub}</span>}</span>
      <span className={mono ? 'mono lib-fact' : 'hist-num'}>{children}</span>
    </li>
  );
}

const COUNTS: { key: string; unit: Unit }[] = [
  { key: 'copies', unit: 'copy' }, { key: 'with_file', unit: 'copy' }, { key: 'files', unit: 'file' },
  { key: 'songs', unit: 'song' }, { key: 'songs_with_versions', unit: 'song' }, { key: 'match_keys', unit: 'key' },
];

/** Plex's side (T13): every live copy's file key, song and match key, and its issues; each count opens its copies. */
function IdentityCard({ load, navigate }: { load: Load<Identity> } & Nav) {
  return (
    <Card label={t('servers.identity')}>
      {load.state === 'loading' && <Text>{t('servers.loading')}</Text>}
      {load.state === 'failed' && <Failed load={load} />}
      {load.state === 'ok' && (() => {
        const d = load.data;
        const issues = Object.entries(d.issues);
        const most = Math.max(1, ...issues.map(([, v]) => v));
        return (
          <div className="stack">
            <Text>{tf('servers.identity.summary', {
              copies: n(d.counts.copies, 'copy'), files: n(d.counts.files, 'file'), songs: n(d.counts.songs, 'song'), clean: fmt(d.clean),
            })}</Text>
            <ul className="rows" aria-label={t('servers.identity')}>
              {COUNTS.map(({ key, unit }) => (
                <Fact key={key} label={t(`servers.count.${key}` as StringKey)} sub={d.rules[key]}>
                  <RowsLink text={n(d.counts[key], unit)} href={d.counts[key] ? copiesHref(d.rows[key] ?? '') : null}
                    what={t(`servers.count.${key}` as StringKey)} navigate={navigate} />
                </Fact>
              ))}
            </ul>
            <Text variant="label">{t('servers.issues')}</Text>
            <ul className="rows hist-top" aria-label={t('servers.issues')}>
              {issues.map(([k, v]) => (
                <li key={k}>
                  <span className="hist-top-text">
                    <strong>{t(`servers.issue.${k}` as StringKey)}</strong>
                    <span className="hist-bar srv-bar" aria-hidden="true"><span style={{ width: `${(100 * v) / most}%` }} /></span>
                    <span className="sub">{d.rules[k]}</span>
                  </span>
                  <RowsLink text={n(v, 'copy')} href={v ? copiesHref(d.rows[k]) : null} what={t(`servers.issue.${k}` as StringKey)} navigate={navigate} />
                </li>
              ))}
            </ul>
            <Text variant="note">{tf('servers.identity.folders', {
              f: d.roots.map((r) => `${r.folder} (${n(r.tracks, 'copy')})`).join(', ') || t('servers.none'), why: d.root_rule,
            })}</Text>
          </div>
        );
      })()}
    </Card>
  );
}

/** A pair's side names: "Plex copies" / "Jellyfin items". */
const sideName = (v: number, s: ServerId) => tf(`servers.side.${s === 'plex' ? 'plex' : 'items'}.${v === 1 ? 'one' : 'other'}` as StringKey, { n: fmt(v), s: serverName(s) });

/** One pair: the summary (L6), the matches by tier as bars in a list, and the misses by reason; each count opens its rows. */
function PairCard({ p, navigate }: { p: Pair } & Nav) {
  const c = p.counts;
  const lname = p.left === 'plex' ? 'copies' : 'left';
  const tiers = Object.entries(p.tiers);
  const most = Math.max(1, ...tiers.map(([, v]) => v));
  const reasons = [...new Set([...Object.keys(p.unmatched_left), ...Object.keys(p.unmatched_items)])];
  const notes = Object.entries(p.notes).filter(([, v]) => v > 0);
  const id = `pair-${p.pair}`;
  return (
    <Card label={pairName(p.pair)}>
      <div className="stack">
        <Text id={id}>{tf('servers.pair.summary', {
          matched: fmt(c.matched), left: sideName(c[lname], p.left), im: fmt(c.items_matched), items: sideName(c.items, p.right),
          lu: sideName(c[`${lname}_unmatched`], p.left), iu: sideName(c.items_unmatched, p.right),
        })}</Text>
        <Text variant="label">{t('servers.byTier')}</Text>
        <ul className="rows hist-top" aria-label={tf('servers.byTierOf', { p: pairName(p.pair) })}>
          {tiers.map(([k, v]) => (
            <li key={k}>
              <span className="hist-top-text">
                <strong>{tierName(k)}</strong>
                <span className="hist-bar srv-bar" aria-hidden="true"><span style={{ width: `${(100 * v) / most}%` }} /></span>
                <span className="sub">{p.rules[k]}</span>
              </span>
              <RowsLink text={fmt(v)} href={v ? matchesHref(p.rows[k]) : null} what={`${pairName(p.pair)}, ${tierName(k)}`} navigate={navigate} />
            </li>
          ))}
        </ul>
        {notes.length > 0 && (
          <Text variant="note">{notes.map(([k, v]) => `${t(`servers.note.${k}` as StringKey)}: ${fmt(v)} (${p.rules[k]})`).join(' · ')}</Text>
        )}
        <Text variant="label">{t('servers.notMatched')}</Text>
        {reasons.length === 0 ? <Text>{t('servers.notMatched.none')}</Text> : (
          <ul className="rows" aria-label={tf('servers.notMatchedOf', { p: pairName(p.pair) })}>
            {reasons.map((r) => {
              const l = p.unmatched_left[r] ?? 0;
              const i = p.unmatched_items[r] ?? 0;
              const split = [l ? sideName(l, p.left) : '', i ? sideName(i, p.right) : ''].filter(Boolean).join(', ');
              return (
                <Fact key={r} label={reasonName(r)} sub={split}>
                  <RowsLink text={fmt(l + i)} href={matchesHref(p.rows[r])} what={`${pairName(p.pair)}, ${reasonName(r)}`} navigate={navigate} />
                </Fact>
              );
            })}
          </ul>
        )}
        <div><Button variant="quiet" href={matchesHref(p.rows.all)} onClick={() => navigate(matchesHref(p.rows.all))}>
          {t('servers.pair.all')}<span className="visually-hidden">{`, ${pairName(p.pair)}`}</span>
        </Button></div>
      </div>
    </Card>
  );
}

/** A pair with no snapshot on one side: its column says so. */
function MissingPair({ p, snaps }: { p: PairId; snaps: Snapshot[] }) {
  const without = snaps.filter((s) => !s.snapshot && (p === 'jellyfin-navidrome' || s.server === p)).map((s) => serverName(s.server));
  return (
    <Card label={pairName(p)}>
      <div className="stack">
        <Status state="off" label={t('servers.snapshot.none')} />
        <Text>{tf('servers.pair.missing', { s: without.join(', ') })}</Text>
      </div>
    </Card>
  );
}

// --- A song's three IDs (SETUP) and On servers (LIBRARY's track page) -----------------------------------------

const PICK = 5;

/** A song's three IDs: pick a copy (five a page), see its Plex rating key, Jellyfin item and Navidrome song. */
function ThreeIdsCard({ query, navigate }: { query: string } & Nav) {
  const q = new URLSearchParams(query);
  const at = Math.max(0, Number(q.get('at')) || 0);
  const list = useGet<Copies>(copiesApi('sort=artist&limit=' + PICK + '&offset=' + at));
  const picked = Number(q.get('copy')) || (list.state === 'ok' ? list.data.copies[0]?.rating_key : undefined);
  const href = (copy: number | undefined, off: number) => `${SERVERS_PATH}?${new URLSearchParams({
    ...(copy ? { copy: String(copy) } : {}), ...(off ? { at: String(off) } : {}),
  }).toString()}`.replace(/\?$/, '');
  return (
    <section className="stack" aria-labelledby="srv-ids">
      <Text variant="heading" id="srv-ids">{t('servers.ids')}</Text>
      <Text>{t('servers.ids.what')}</Text>
      {list.state === 'loading' && <Text>{t('servers.loading')}</Text>}
      {list.state === 'failed' && <Card><Failed load={list} /></Card>}
      {list.state === 'ok' && (
        <>
          <nav className="hist-choices" aria-label={t('servers.ids.pick')}>
            {list.data.copies.map((c) => (
              <NavItem key={c.rating_key} label={copyLabel(c)} href={href(c.rating_key, at)} current={c.rating_key === picked}
                onNavigate={(h) => navigate(h)} />
            ))}
          </nav>
          {list.data.total > PICK && (
            <div className="hist-actions">
              <Button disabled={at === 0} href={at ? href(undefined, Math.max(0, at - PICK)) : undefined}
                onClick={() => navigate(href(undefined, Math.max(0, at - PICK)))}>{t('library.rows.prev')}</Button>
              <Button disabled={at + PICK >= list.data.total} href={at + PICK < list.data.total ? href(undefined, at + PICK) : undefined}
                onClick={() => navigate(href(undefined, at + PICK))}>{t('library.rows.next')}</Button>
            </div>
          )}
          {picked != null && <PickedIds key={picked} rk={picked} navigate={navigate} />}
        </>
      )}
    </section>
  );
}

const copyLabel = (c: Copy) => `${c.title || t('rows.untitled')} · ${c.track_artist || c.artist || t('rows.unknown')}`;

function PickedIds({ rk, navigate }: { rk: number } & Nav) {
  const load = useGet<Matches>(matchesApi('rating_key=' + rk));
  const one = useGet<Copies>(copiesApi('rating_key=' + rk));
  const c = one.state === 'ok' ? one.data.copies[0] : undefined;
  return (
    <Card label={c ? copyLabel(c) : tf('servers.rows.copy', { k: rk })}>
      <OnServersBody load={load} copy={c} rk={rk} navigate={navigate} />
      {c && (
        <div><Button variant="quiet" href={trackHref(rk)} onClick={() => navigate(trackHref(rk))}>{t('servers.ids.track')}</Button></div>
      )}
    </Card>
  );
}

/** LIBRARY's track page (T15): this copy on each server, with its tier and that server's own play count, labelled. */
export function OnServers({ rk, plexPlays, navigate }: { rk: number; plexPlays: number } & Nav) {
  const load = useGet<Matches>(matchesApi('rating_key=' + rk));
  const copy = useGet<Copies>(copiesApi('rating_key=' + rk));
  return (
    <Card label={t('servers.on')}>
      <OnServersBody load={load} copy={copy.state === 'ok' ? copy.data.copies[0] : undefined} rk={rk} plexPlays={plexPlays} navigate={navigate} />
    </Card>
  );
}

function OnServersBody({ load, copy, rk, plexPlays, navigate }: {
  load: Load<Matches>; copy?: Copy; rk: number; plexPlays?: number;
} & Nav) {
  if (load.state === 'loading') return <Text>{t('servers.loading')}</Text>;
  if (load.state === 'failed') return <Failed load={load} />;
  const m = load.data;
  if (m.copy && !m.copy.live) return <Text>{t('servers.on.notLive')}</Text>;
  const rows = m.rows?.rows ?? [];
  const plays = rows.filter((r) => r.side === 'both' && r.pair !== 'jellyfin-navidrome' && (r.right?.play_count ?? 0) > 0);
  return (
    <div className="stack">
      <ul className="rows lib-paths" aria-label={t('servers.on')}>
        <li>
          <span>
            <strong>{serverName('plex')}</strong>
            <span className="sub">{[tf('servers.on.ratingKey', { k: rk }), copy?.file ?? copy?.plex_path ?? '',
              plexPlays != null ? tf('servers.on.plays', { n: fmt(plexPlays), unit: t(plexPlays === 1 ? 'unit.play.one' : 'unit.play.other'), s: serverName('plex') }) : '']
              .filter(Boolean).join(' · ')}</span>
          </span>
          <span className="mono lib-fact">{String(rk)}</span>
        </li>
        {OTHER_SERVERS.map((s) => <ServerLine key={s} s={s} m={m} row={rows.find((r) => r.pair === s)} />)}
      </ul>
      <Text variant="note">{plays.length > 0 || plexPlays != null ? t('servers.on.never') : t('servers.on.idsOnly')}</Text>
      <div><Button variant="quiet" href={matchesHref(matchQuery('', { rating_key: rk }))}
        onClick={() => navigate(matchesHref(matchQuery('', { rating_key: rk })))}>{t('servers.on.rows')}</Button></div>
    </div>
  );
}

function ServerLine({ s, m, row }: { s: ServerId; m: Matches; row?: MatchRow }) {
  const snap = m.snapshots.find((x) => x.server === s);
  let value = t('servers.none');
  let sub: string;
  if (!snap || !snap.snapshot) sub = tf('servers.snapshot.noneWhy', { s: serverName(s) });
  else if (!row) sub = t('servers.on.noRow');
  else if (row.side === 'both' && row.right) {
    const it = row.right;
    value = it.id;
    sub = [
      tf('servers.on.tier', { tier: tierIn(row.tier ?? '') }) + (row.how === 'loose' ? ` (${t('servers.note.loose')})` : '')
        + (row.mbid_from ? ` (${tf('servers.on.mbidFrom', { s: serverName(row.mbid_from) })})` : '')
        + (row.multi_part ? ` (${t('servers.note.multi_part')})` : '') + (row.shared ? ` (${t('servers.note.shared_file')})` : ''),
      it.file ?? (it.hidden ? t('servers.on.hidden') : t('servers.none')),
      it.duration_ms != null ? duration(Math.round(it.duration_ms / 1000)) : '',
      tf('servers.on.plays', { n: fmt(it.play_count ?? 0), unit: t(it.play_count === 1 ? 'unit.play.one' : 'unit.play.other'), s: serverName(s) }),
    ].filter(Boolean).join(' · ');
  } else {
    value = t('servers.on.notMatched');
    sub = `${reasonName(row.reason ?? '')}: ${m.reasons[row.reason ?? ''] ?? ''}`;
  }
  return (
    <li>
      <span><strong>{serverName(s)}</strong><span className="sub">{sub}</span></span>
      <span className="mono lib-fact">{value}</span>
    </li>
  );
}

// --- The rows pages -----------------------------------------------------------------------------------------

function Pages({ total, offset, limit, at, navigate }: { total: number; offset: number; limit: number; at: (o: number) => string } & Nav) {
  const prev = offset > 0 ? at(Math.max(0, offset - limit)) : null;
  const next = offset + limit < total ? at(offset + limit) : null;
  if (!prev && !next) return null;
  return (
    <div className="hist-actions">
      <Button disabled={!prev} href={prev ?? undefined} onClick={prev ? () => navigate(prev) : undefined}>{t('library.rows.prev')}</Button>
      <Button disabled={!next} href={next ?? undefined} onClick={next ? () => navigate(next) : undefined}>{t('library.rows.next')}</Button>
    </div>
  );
}

const issueNames = (c: Copy) => c.issues.map((i) => tMaybe(`servers.issue.${i}`) ?? i).join(', ');

/** Why a copy is in these rows (W3): its file key, song, match key and issues. */
export function copyWhy(c: Copy): string {
  return [
    tf('servers.on.ratingKey', { k: c.rating_key }),
    c.file ? tf('servers.why.file', { f: c.file }) : tf('servers.why.noFile', { p: c.plex_path ?? t('servers.none') }),
    c.song ? tf('servers.why.song', { s: c.song }) : '',
    c.match_key ? tf('servers.why.key', { k: c.match_key }) : '',
    c.duration_ms != null ? duration(Math.round(c.duration_ms / 1000)) : t('servers.why.noDuration'),
    c.issues.length ? tf('servers.why.issues', { i: issueNames(c) }) : t('servers.why.clean'),
  ].filter(Boolean).join(' · ');
}

/** The copies behind an identity count, 50 a page, with the rule that selected them. */
export function ServerCopies({ query, navigate }: { query: string } & Nav) {
  const q = copyQuery(query);
  const load = useGet<Copies>(copiesApi(q));
  return (
    <>
      <Band module="S">{t('servers.sub')}</Band>
      <div className="page stack servers">
        <Back href={SERVERS_PATH} label={t('servers.rows.back')} navigate={navigate} />
        <Text variant="heading">{copiesTitle(query)}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Card><Failed load={load} /></Card>}
        {load.state === 'ok' && (() => {
          const l = load.data;
          return (
            <>
              <Text>{tf('servers.rows.total', { n: n(l.total, 'copy'), a: fmt(l.total ? l.offset + 1 : 0), b: fmt(l.offset + l.copies.length) })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${l.rule}.`}</Text>
              {l.copies.length === 0 ? <Text>{t('servers.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {l.copies.map((c, i) => (
                    <StationRow key={c.rating_key} position={l.offset + i + 1} module="L" title={c.title || t('rows.untitled')}
                      artist={[c.track_artist || c.artist || t('rows.unknown'), c.album].filter(Boolean).join(' · ')}
                      why={copyWhy(c)} href={trackHref(c.rating_key)} onNavigate={navigate} />
                  ))}
                </ol>
              )}
              <Pages total={l.total} offset={l.offset} limit={l.limit} navigate={navigate}
                at={(o) => copiesHref(copyQuery(query, { offset: o }))} />
            </>
          );
        })()}
      </div>
    </>
  );
}

const isCopy = (x: MatchRow['left']): x is Copy & Partial<Item> => !!x && 'rating_key' in x && x.rating_key != null;

function sideLine(server: ServerId, x: MatchRow['left']): string {
  if (!x) return '';
  if (isCopy(x)) return tf('servers.why.plexSide', { k: x.rating_key, f: x.file ?? x.plex_path ?? t('servers.none') });
  const it = x as Item;
  return tf('servers.why.itemSide', {
    s: serverName(server), id: it.id, f: it.file ?? (it.hidden ? t('servers.on.hidden') : it.path ?? t('servers.none')),
  });
}

const sides = (p: PairId): ServerId[] => (p === 'jellyfin-navidrome' ? ['jellyfin', 'navidrome'] : ['plex', p]);

/** Why a row is here (W3): both sides, the tier and how, or the one reason. */
export function matchWhy(r: MatchRow, reasons: Record<string, string>): string {
  const [ls, rs] = sides(r.pair);
  if (r.side === 'both') {
    return [
      sideLine(ls, r.left), sideLine(rs, r.right),
      tf('servers.on.tier', { tier: tierIn(r.tier ?? '') }),
      r.how === 'loose' ? t('servers.note.loose') : '',
      r.shared ? t('servers.note.shared_file') : '',
      r.multi_part ? t('servers.note.multi_part') : '',
      r.mbid_from ? tf('servers.on.mbidFrom', { s: serverName(r.mbid_from) }) : '',
      r.via != null ? tf('servers.why.via', { k: r.via }) : '',
      r.right?.play_count ? tf('servers.on.plays', { n: fmt(r.right.play_count), unit: t(r.right.play_count === 1 ? 'unit.play.one' : 'unit.play.other'), s: serverName(rs) }) : '',
    ].filter(Boolean).join(' · ');
  }
  const side = r.side === 'left' ? sideLine(ls, r.left) : sideLine(rs, r.right);
  return [side, `${t('servers.on.notMatched')}: ${reasonName(r.reason ?? '')}`, reasons[r.reason ?? ''] ?? ''].filter(Boolean).join(' · ');
}

/** The match rows behind a pair's count, 50 a page, with the rule that selected them. */
export function ServerMatches({ query, navigate }: { query: string } & Nav) {
  const q = matchQuery(query);
  const load = useGet<Matches>(matchesApi(q));
  return (
    <>
      <Band module="S">{t('servers.sub')}</Band>
      <div className="page stack servers">
        <Back href={SERVERS_PATH} label={t('servers.rows.back')} navigate={navigate} />
        <Text variant="heading">{matchesTitle(query)}</Text>
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Card><Failed load={load} /></Card>}
        {load.state === 'ok' && (() => {
          const rows = load.data.rows;
          if (!rows) return <Text>{t('servers.rows.none')}</Text>;
          return (
            <>
              <Text>{tf('servers.rows.totalRows', { n: fmt(rows.total), a: fmt(rows.total ? rows.offset + 1 : 0), b: fmt(rows.offset + rows.rows.length) })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${rows.rule}. ${load.data.read_only}`}</Text>
              {rows.rows.length === 0 ? <Text>{t('servers.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {rows.rows.map((r, i) => {
                    const x = (r.left ?? r.right)!;
                    const rk = isCopy(r.left) ? r.left.rating_key : null;
                    const [ls, rs] = sides(r.pair);
                    const where = r.side === 'both' ? pairName(r.pair) : tf('servers.rows.only', { s: serverName(r.side === 'left' ? ls : rs) });
                    return (
                      <StationRow key={`${r.pair}-${i + rows.offset}`} position={rows.offset + i + 1} module="S"
                        title={x.title || t('rows.untitled')}
                        artist={[where, ('track_artist' in x && x.track_artist) || x.artist || t('rows.unknown'), x.album].filter(Boolean).join(' · ')}
                        why={matchWhy(r, load.data.reasons)} href={rk != null ? trackHref(rk) : undefined} onNavigate={navigate} />
                    );
                  })}
                </ol>
              )}
              <Pages total={rows.total} offset={rows.offset} limit={rows.limit} navigate={navigate}
                at={(o) => matchesHref(matchQuery(query, { offset: o }))} />
            </>
          );
        })()}
      </div>
    </>
  );
}

/** SETUP's card for the servers: each one's status in a line, opening the SERVERS page. */
export function ServersCard({ navigate }: Nav) {
  const load = useGet<Servers>('/api/servers');
  return (
    <Card label={t('servers.title')}>
      <div className="stack">
        {load.state === 'loading' && <Text>{t('servers.loading')}</Text>}
        {load.state === 'failed' && <Status state="needs" label={t('servers.failed')} />}
        {load.state === 'ok' && (
          <ul className="rows" aria-label={t('servers.title')}>
            {load.data.servers.map((s) => (
              <li key={s.server}>
                <strong>{serverName(s.server)}</strong>
                {s.server === 'plex'
                  ? <Status state={s.read ? 'ready' : 'needs'} label={t(s.read ? 'servers.plex.read' : 'servers.plex.unread')} />
                  : <Status state={s.set_up ? 'ready' : 'off'} label={t(s.set_up ? 'servers.setUp' : 'servers.notSetUp')} />}
              </li>
            ))}
          </ul>
        )}
        <Text variant="note">{t('servers.card.what')}</Text>
        <div><Button variant="quiet" href={SERVERS_PATH} onClick={() => navigate(SERVERS_PATH)}>{t('servers.open')}</Button></div>
      </div>
    </Card>
  );
}
