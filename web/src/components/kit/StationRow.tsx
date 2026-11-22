import { useId, useState } from 'react';
import { t } from '../../copy/t';
import { LineBullet } from './LineBullet';
import type { ModuleId } from './modules';

type Props = {
  position: number;
  /** The line that brought the track in (B3). */
  module: ModuleId;
  title: string;
  artist: string;
  musicalKey?: string;
  bpm?: number;
  /** Why the track is here, in a sentence (B3). Always available behind the toggle. */
  why: string;
  defaultOpen?: boolean;
};

/** 8 · Station row: position, line bullet, title, artist, key and BPM; can always show why it's there. */
export function StationRow({ position, module, title, artist, musicalKey, bpm, why, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <li className="kit-station" data-module={module}>
      <span className="kit-station-pos"><span className="visually-hidden">{t('kit.position')} </span>{position}</span>
      <LineBullet module={module} size={24} />
      <span className="kit-station-main">
        <span className="kit-station-title">{title}</span>
        <span className="kit-station-artist">{artist}</span>
      </span>
      <span className="kit-station-code">
        {musicalKey && <span><span className="visually-hidden">{t('kit.key')} </span>{musicalKey}</span>}
        {bpm != null && <span>{bpm} {t('kit.bpm')}</span>}
      </span>
      <button
        type="button"
        className="kit-station-why"
        aria-expanded={open}
        aria-controls={`${id}-why`}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? t('kit.why.hide') : t('kit.why.show')}
      </button>
      <p className="kit-station-reason" id={`${id}-why`} hidden={!open}>{why}</p>
    </li>
  );
}
