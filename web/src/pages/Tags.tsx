import { useState } from 'react';
import { Band, Button, Card, NavItem, Status, StationRow, Text } from '../components/kit';
import { t, tf, type StringKey } from '../copy/t';
import { useGet } from '../app/api';
import { albumHref, artistHref } from '../app/entities';
import { count, fmt } from '../app/history';
import { TracksCheckCard } from './TagsTracks';
import {
  LADDER_API, TAGS_PATH, TAG_SETS, TAG_SHOWS, albumsApi, albumsHref, artistsApi, artistsHref, listHref, params, shown,
  type CheckRow, type Ladder, type TagAlbums, type TagArtists, type TagNode, type TagSet, type TagShow,
} from '../app/tags';

type Nav = { navigate: (href: string) => void };

/** A link to the rows behind a number (W3). */
function Num({ href, label, of, navigate }: { href: string; label: string; of?: string } & Nav) {
  return (
    <Button variant="quiet" href={href} onClick={() => navigate(href)}>
      {label}{of && <span className="visually-hidden">{`, ${of}`}</span>}
    </Button>
  );
}

function Back({ navigate }: Nav) {
  return <div><Button variant="quiet" href={TAGS_PATH} onClick={() => navigate(TAGS_PATH)}>{t('tags.back')}</Button></div>;
}

function Failed() {
  return (
    <Card>
      <div className="stack">
        <Status state="needs" label={t('tags.failed')} />
        <Text>{t('tags.failedWhy')}</Text>
      </div>
    </Card>
  );
}

const names = (l: Ladder, keys: string[]) => keys.map((k) => l.nodes[k]?.name ?? k).join(', ');

/** Why a tag sits where it does, in one line (B3): its parents and the rule, its spellings, its notes. */
export function tagWhy(l: Ladder, n: TagNode): string {
  const parts: string[] = [];
  if (n.root) parts.push(n.in_use ? t('tags.why.root') : t('tags.why.rootUnused'));
  else if (!n.broad) parts.push(t('tags.why.alone'));
  else if (n.parents.length === 1 && l.nodes[n.parents[0]]?.root) parts.push(tf('tags.why.broad', { p: names(l, n.parents) }));
  else parts.push(tf(n.parents.length > 1 ? 'tags.why.heads' : 'tags.why.head', { p: names(l, n.parents) }));
  if (n.rung !== null) parts.push(tf('tags.why.rung', { n: n.rung }));
  if (n.variants.length > 1) parts.push(tf('tags.why.spellings', { s: n.variants.join(', ') }));
  if (n.other_heads.length) parts.push(tf('tags.why.other', { s: n.other_heads.join(', ') }));
  if (n.niche) parts.push(t('tags.why.niche'));
  return parts.join(' · ');
}

/** A tag's numbers, each opening its rows. */
function Numbers({ n, navigate }: { n: TagNode } & Nav) {
  return (
    <span className="hist-actions">
      <Num href={albumsHref(n.key)} label={tf('tags.num.albums', { n: count(n.albums, 'album') })} of={n.name} navigate={navigate} />
      {n.below > 0 && <Num href={albumsHref(n.key, 'under')} label={tf('tags.num.under', { n: count(n.under, 'album') })} of={n.name} navigate={navigate} />}
      {n.root && n.missing !== null && <Num href={albumsHref(n.key, 'missing')} label={tf('tags.num.missing', { n: count(n.missing, 'album') })} of={n.name} navigate={navigate} />}
      <Num href={artistsHref(n.key)} label={tf('tags.num.artists', { n: count(n.artists, 'artist') })} of={n.name} navigate={navigate} />
    </span>
  );
}

/** One tag on the ladder, with the rungs below it behind a toggle. Shared children show under each parent. */
function Rung({ l, k, from, navigate }: { l: Ladder; k: string; from?: string } & Nav) {
  const n = l.nodes[k];
  const [open, setOpen] = useState(false);
  const also = from ? n.parents.filter((p) => p !== from) : [];
  return (
    <li className="tags-rung">
      <span className="tags-line">
        <strong>{n.name}</strong>
        <span className="sub">{tagWhy(l, n)}{also.length > 0 && ` · ${tf('tags.why.also', { p: names(l, also) })}`}</span>
        <Numbers n={n} navigate={navigate} />
        {n.children.length > 0 && (
          <span>
            <Button variant="quiet" onClick={() => setOpen(!open)}>
              {tf(open ? 'tags.hideBelow' : 'tags.showBelow', { n: n.children.length })}
              <span className="visually-hidden">{`, ${n.name}`}</span>
            </Button>
          </span>
        )}
        {open && (
          <ul className="rows tags-below" aria-label={tf('tags.belowOf', { tag: n.name })}>
            {n.children.map((c) => <Rung key={c} l={l} k={c} from={k} navigate={navigate} />)}
          </ul>
        )}
      </span>
    </li>
  );
}

function family(f: CheckRow['ladder']): string {
  return f ? tf('tags.check.family', { albums: count(f.albums, 'album'), tagged: fmt(f.tagged), missing: fmt(f.missing ?? 0),
    children: count(f.children.length, 'tag') }) : t('tags.check.absent');
}

function CheckRows({ rows, label, navigate }: { rows: CheckRow[]; label: string } & Nav) {
  return (
    <ul className="rows" aria-label={label}>
      {rows.map((r) => (
        <li key={r.key} className="gate-field">
          <span>
            <Num href={albumsHref(r.key, 'under')} label={r.tag} navigate={navigate} />
            <span className="sub">{tf('tags.check.ours', { v: family(r.ladder) })}</span>
            <span className="sub">{tf('tags.check.theirs', { v: family(r.jimbodj) })}</span>
          </span>
          <Status state={r.matches ? 'ready' : 'needs'} label={t(r.matches ? 'compare.match' : 'compare.differs')} />
        </li>
      ))}
    </ul>
  );
}

/** The ladder next to jimbo-dj's families: its rules run here, and its own stored run (gate check 1). */
export function LadderCheckCard({ l, navigate }: { l: Ladder } & Nav) {
  const c = l.check;
  const [open, setOpen] = useState(false);
  const ok = (rows: CheckRow[]) => rows.filter((r) => r.matches).length;
  return (
    <Card label={t('tags.check.label')}>
      <div className="stack">
        <Status state={c.passed ? 'ready' : 'needs'} label={t(c.passed ? 'compare.passed' : 'compare.notPassed')} />
        <ul className="rows" aria-label={t('tags.check.label')}>
          <li>
            <span>{tf('tags.check.rules', { m: fmt(ok(c.rules.rows)), n: count(c.rules.rows.length, 'broadTag') })}<span className="sub">{c.rules.source}</span></span>
            <Status state={c.rules.matches ? 'ready' : 'needs'} label={t(c.rules.matches ? 'compare.match' : 'compare.differs')} />
          </li>
          <li>
            <span>{tf('tags.check.ends', { m: fmt(c.ends.ok), n: count(c.ends.tags, 'ladder') })}<span className="sub">{c.ends.rule}</span></span>
            <Status state={c.ends.matches ? 'ready' : 'needs'} label={t(c.ends.matches ? 'compare.match' : 'compare.differs')} />
          </li>
          <li>
            {c.stored ? (
              <>
                <span>
                  {tf('tags.check.stored', { m: fmt(ok(c.stored.rows)), n: count(c.stored.rows.length, 'broadTag') })}
                  <span className="sub">{`${c.stored.source} · ${t(c.stored.fresh ? 'compare.fresh' : 'compare.stale')}`}</span>
                </span>
                <Status state={c.stored.matches ? 'ready' : c.stored.fresh ? 'needs' : 'off'}
                  label={t(c.stored.matches ? 'compare.match' : c.stored.fresh ? 'compare.differs' : 'compare.differsStale')} />
              </>
            ) : <span>{t('tags.check.noStored')}</span>}
          </li>
        </ul>
        <div>
          <Button variant="quiet" onClick={() => setOpen(!open)}>
            {tf(open ? 'tags.check.hide' : 'tags.check.show', { n: c.rules.rows.length })}
          </Button>
        </div>
        {open && <CheckRows rows={c.rules.rows} label={t('tags.check.rulesList')} navigate={navigate} />}
        {open && c.stored && <CheckRows rows={c.stored.rows} label={t('tags.check.storedList')} navigate={navigate} />}
      </div>
    </Card>
  );
}

const SUMMARY: Record<TagShow, (s: Ladder['summary']) => string> = {
  tags: (s) => tf('tags.sum.tags', { n: count(s.tags, 'tag') }),
  roots: (s) => tf('tags.sum.roots', { n: count(s.roots, 'broadTag') }),
  deepest: (s) => tf('tags.sum.deepest', { n: fmt(s.deepest) }),
  shared: (s) => tf('tags.sum.shared', { n: count(s.shared, 'tag') }),
  alone: (s) => tf('tags.sum.alone', { n: count(s.alone, 'tag') }),
};

/** TAGS (T20): every genre tag in use on its rungs, broad to specific, with jimbo-dj's rules. */
export function Tags({ navigate }: Nav) {
  const load = useGet<Ladder>(LADDER_API);
  return (
    <>
      <Band module="T">{t('tags.sub')}</Band>
      <div className="page stack history tags">
        <Text variant="title">{t('tags.title')}</Text>
        <Text>{t('tags.intro')}</Text>
        {load.state === 'loading' && <Text>{t('tags.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && <LadderBody l={load.data} navigate={navigate} />}
      </div>
    </>
  );
}

function LadderBody({ l, navigate }: { l: Ladder } & Nav) {
  const s = l.summary;
  return (
    <>
      <Card label={t('tags.sum.label')}>
        <ul className="rows" aria-label={t('tags.sum.label')}>
          {TAG_SHOWS.map((k) => (
            <li key={k}><Num href={listHref(k)} label={SUMMARY[k](s)} navigate={navigate} /></li>
          ))}
        </ul>
        <Text variant="note">{tf('tags.sum.note', { albums: count(s.albums, 'album'), artists: count(s.artists, 'artist'), junk: count(s.junk, 'tag') })}</Text>
      </Card>
      <LadderCheckCard l={l} navigate={navigate} />
      <TracksCheckCard navigate={navigate} />
      <section aria-labelledby="tags-ladder" className="stack">
        <Text variant="heading" id="tags-ladder">{t('tags.ladder')}</Text>
        <Text variant="note">{`${t('tags.rule.parent')}: ${l.rules.parent}.`}</Text>
        {l.roots.length === 0 ? <Text>{t('tags.none')}</Text> : (
          <ul className="rows tags-ladder" aria-label={t('tags.ladder')}>
            {l.roots.map((k) => <Rung key={k} l={l} k={k} navigate={navigate} />)}
          </ul>
        )}
      </section>
      {l.alone.length > 0 && (
        <section aria-labelledby="tags-alone" className="stack">
          <Text variant="heading" id="tags-alone">{t('tags.alone')}</Text>
          <Text variant="note">{`${l.rules.alone}.`}</Text>
          <ul className="rows tags-ladder" aria-label={t('tags.alone')}>
            {l.alone.map((k) => <Rung key={k} l={l} k={k} navigate={navigate} />)}
          </ul>
        </section>
      )}
    </>
  );
}

/** The tags behind a summary number. */
export function TagList({ query, navigate }: { query: string } & Nav) {
  const raw = params(query).get('show');
  const show: TagShow = TAG_SHOWS.includes(raw as TagShow) ? (raw as TagShow) : 'tags';
  const load = useGet<Ladder>(LADDER_API);
  return (
    <>
      <Band module="T">{t('tags.list.sub')}</Band>
      <div className="page stack">
        <Back navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && (() => {
          const rows = shown(load.data, show);
          return (
            <>
              <Text variant="heading">{SUMMARY[show](load.data.summary)}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${t(`tags.list.rule.${show}` as StringKey)}.`}</Text>
              <ol className="hist-rows">
                {rows.map((n, i) => (
                  <StationRow key={n.key} position={i + 1} module="T" title={n.name}
                    artist={[n.broad ?? t('tags.noBroad'), count(n.under, 'album')].join(' · ')}
                    why={tagWhy(load.data, n)} href={albumsHref(n.key, n.below > 0 ? 'under' : 'carries')} onNavigate={navigate} />
                ))}
              </ol>
            </>
          );
        })()}
      </div>
    </>
  );
}

function Pager({ total, limit, offset, href, navigate }: { total: number; limit: number; offset: number; href: (o: number) => string } & Nav) {
  const b = offset + limit;
  if (offset === 0 && b >= total) return null;
  return (
    <div className="hist-actions">
      {offset > 0 && <Num href={href(Math.max(0, offset - limit))} label={t('tags.prev')} navigate={navigate} />}
      {b < total && <Num href={href(offset + limit)} label={t('tags.next')} navigate={navigate} />}
    </div>
  );
}

/** The albums behind a tag's number: carrying it, under it, or missing it (a broad tag). */
export function TagAlbumRows({ query, navigate }: { query: string } & Nav) {
  const p = params(query);
  const tag = p.get('tag') ?? '';
  const set = (TAG_SETS.includes(p.get('set') as TagSet) ? p.get('set') : 'carries') as TagSet;
  const offset = Number(p.get('offset') ?? 0) || 0;
  const load = useGet<TagAlbums>(albumsApi(tag, set, offset));
  return (
    <>
      <Band module="T">{t('tags.albums.sub')}</Band>
      <div className="page stack">
        <Back navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && (() => {
          const d = load.data;
          return (
            <>
              <Text variant="heading">{tf(`tags.albums.${set}` as StringKey, { tag: d.tag.name })}</Text>
              <nav className="hist-choices" aria-label={t('tags.albums.sets')}>
                {TAG_SETS.filter((s) => s !== 'missing' || d.tag.root).map((s) => (
                  <NavItem key={s} label={t(`tags.set.${s}` as StringKey)} href={albumsHref(d.tag.key, s)} current={s === set} onNavigate={navigate} />
                ))}
                <NavItem label={t('tags.set.artists')} href={artistsHref(d.tag.key)} onNavigate={navigate} />
              </nav>
              <Text>{tf('tags.rows.total', { n: count(d.total, 'album') })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${d.rule}.`}</Text>
              {d.items.length === 0 ? <Text>{t('tags.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {d.items.map((a, i) => (
                    <StationRow key={a.album_key} position={d.offset + i + 1} module="T" title={a.title || t('rows.untitled')}
                      artist={[a.artist || t('rows.unknown'), a.year].filter(Boolean).join(' · ')}
                      why={[a.tags.length ? tf('tags.rows.albumTags', { s: a.tags.join(', ') }) : t('tags.rows.noTags'),
                        a.carries ? tf('tags.rows.carries', { tag: d.tag.name }) : '',
                        a.via.length ? tf('tags.rows.via', { s: a.via.join(', ') }) : ''].filter(Boolean).join(' · ')}
                      href={albumHref(a.album_key)} onNavigate={navigate} />
                  ))}
                </ol>
              )}
              <Pager total={d.total} limit={d.limit} offset={d.offset} href={(o) => albumsHref(d.tag.key, set, o)} navigate={navigate} />
            </>
          );
        })()}
      </div>
    </>
  );
}

/** The artists whose Plex artist genres name a tag. */
export function TagArtistRows({ query, navigate }: { query: string } & Nav) {
  const p = params(query);
  const tag = p.get('tag') ?? '';
  const offset = Number(p.get('offset') ?? 0) || 0;
  const load = useGet<TagArtists>(artistsApi(tag, offset));
  return (
    <>
      <Band module="T">{t('tags.artists.sub')}</Band>
      <div className="page stack">
        <Back navigate={navigate} />
        {load.state === 'loading' && <Text>{t('rows.loading')}</Text>}
        {load.state === 'failed' && <Failed />}
        {load.state === 'ok' && (() => {
          const d = load.data;
          return (
            <>
              <Text variant="heading">{tf('tags.artists.title', { tag: d.tag.name })}</Text>
              <div><Num href={albumsHref(d.tag.key)} label={t('tags.artists.toAlbums')} navigate={navigate} /></div>
              <Text>{tf('tags.rows.total', { n: count(d.total, 'artist') })}</Text>
              <Text variant="note">{`${t('rows.rule')}: ${d.rule}.`}</Text>
              {d.items.length === 0 ? <Text>{t('tags.rows.none')}</Text> : (
                <ol className="hist-rows">
                  {d.items.map((a, i) => (
                    <StationRow key={a.artist_key} position={d.offset + i + 1} module="T" title={a.name || t('rows.unknown')}
                      artist={count(a.albums, 'album')}
                      why={a.tags.length ? tf('tags.rows.artistTags', { s: a.tags.join(', ') }) : t('tags.rows.noTags')}
                      href={artistHref(a.artist_key)} onNavigate={navigate} />
                  ))}
                </ol>
              )}
              <Pager total={d.total} limit={d.limit} offset={d.offset} href={(o) => artistsHref(d.tag.key, o)} navigate={navigate} />
            </>
          );
        })()}
      </div>
    </>
  );
}
