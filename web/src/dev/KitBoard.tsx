import { useState } from 'react';
import {
  ArtTile, Band, Button, Card, ConditionChip, LineBullet, LineLever, MODULE_IDS, NavItem, StationRow, Status, Text,
} from '../components/kit';
import { b } from './b';
import './board.css';

/** Dev only (/kit in `npm run dev`): every kit component in every state. Never in a production build (D1). */
export function KitBoard() {
  const [share, setShare] = useState(40);
  const [chips, setChips] = useState([true, true]);
  return (
    <main className="board">
      <Text variant="title">{b('board.title')}</Text>
      <Text>{b('board.lede')}</Text>

      <section className="board-group">
        <Text variant="label">{b('board.bullets')}</Text>
        <div className="board-row">{MODULE_IDS.map((m) => <LineBullet key={m} module={m} />)}</div>
        <div className="board-row">{([22, 24, 28, 36, 44] as const).map((s) => <LineBullet key={s} module="M" size={s} />)}</div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.nav')}</Text>
        <nav className="board-chrome">
          {MODULE_IDS.map((m) => <NavItem key={m} module={m} href={`#${m}`} current={m === 'H'} onNavigate={() => {}} />)}
        </nav>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.status')}</Text>
        <div className="board-row"><Status state="ready" /><Status state="needs" /><Status state="off" /></div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.band')}</Text>
        <div className="board-stack">{MODULE_IDS.map((m) => <Band key={m} module={m} />)}</div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.buttons')}</Text>
        <div className="board-row">
          <Button variant="primary">{b('board.primary')}</Button>
          <Button variant="secondary">{b('board.secondary')}</Button>
          <Button variant="quiet">{b('board.quiet')}</Button>
          <Button disabled>{b('board.disabled')}</Button>
        </div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.chips')}</Text>
        <div className="board-row">
          {chips[0] && <ConditionChip op="AND" onRemove={() => setChips([false, chips[1]])}>{b('board.chipGenre')}</ConditionChip>}
          {chips[1] && <ConditionChip op="OR" onRemove={() => setChips([chips[0], false])}>{b('board.chipBpm')}</ConditionChip>}
          <ConditionChip op="NOT">{b('board.chipPlayed')}</ConditionChip>
          <ConditionChip op="true">{b('board.chipLoved')}</ConditionChip>
          <ConditionChip op="false">{b('board.chipLoved')}</ConditionChip>
        </div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.levers')}</Text>
        <LineLever module="H" title={b('board.leverHistoryTitle')} detail={b('board.leverHistoryDetail')} share={share} count={Math.round(share / 2.5)} onChange={setShare} />
        <LineLever module="T" title={b('board.leverTagsTitle')} detail={b('board.leverTagsDetail')} share={35} count={14} />
        <LineLever module="M" title={b('board.leverTagsTitle')} detail={b('board.leverTagsDetail')} share={25} count={10} />
        <LineLever module="D" title={b('board.leverDiscoverTitle')} detail={b('board.leverDiscoverDetail')} share={0} count={0} onChange={() => {}} off />
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.stations')}</Text>
        <ol className="board-list">
          <StationRow position={1} module="H" title={b('board.sampleTitle')} artist={b('board.sampleArtist')} musicalKey={b('board.sampleKey')} bpm={124} why={b('board.sampleWhy')} />
          <StationRow position={2} module="T" title={b('board.sampleTitle')} artist={b('board.sampleArtist')} bpm={122} why={b('board.leverTagsDetail')} defaultOpen />
          <StationRow position={3} module="F" title={b('board.sampleTitle')} artist={b('board.sampleArtist')} why={b('board.leverDiscoverDetail')} />
        </ol>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.type')}</Text>
        <Text variant="title">{b('board.typeTitle')}</Text>
        <Text variant="heading">{b('board.typeHeading')}</Text>
        <Text>{b('board.typeBody')}</Text>
        <Text variant="label">{b('board.typeLabel')}</Text>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.cards')}</Text>
        <div className="board-grid">
          <Card label={b('board.cardOn')}><Status state="ready" /><Text>{b('board.cardOnBody')}</Text></Card>
          <Card label={b('board.cardOff')} off><Status state="off" /><Text>{b('board.cardOffBody')}</Text></Card>
        </div>
      </section>

      <section className="board-group">
        <Text variant="label">{b('board.art')}</Text>
        <div className="board-grid board-art">
          <ArtTile title={b('board.sampleTitle')} artist={b('board.sampleArtist')} musicalKey={b('board.sampleKey')} bpm={124} />
          <ArtTile title={b('board.sampleTitle')} artist={b('board.sampleArtist')} bpm={98} />
          <ArtTile title={b('board.sampleTitle')} artist={b('board.sampleArtist')} />
        </div>
      </section>
    </main>
  );
}
