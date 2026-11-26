import { useId, useState, type ReactNode } from 'react';
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
  /** Why the track is here (B3): a sentence, or a sentence with its conditions as ConditionChips. Always
   *  available behind the toggle. */
  why: ReactNode;
  defaultOpen?: boolean;
  /** Makes the title a link (to the track's page). */
  href?: string;
  /** With href, called instead of following the link (client-side navigation); modified clicks still follow it. */
  onNavigate?: (href: string) => void;
};

/** 8 · Station row: position, line bullet, title, artist, key and BPM; can always show why it's there. */
export function StationRow({ position, module, title, artist, musicalKey, bpm, why, defaultOpen = false, href, onNavigate }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <li className="kit-station" data-module={module}>
      <span className="kit-station-pos"><span className="visually-hidden">{t('kit.position')} </span>{position}</span>
      <LineBullet module={module} size={24} />
      <span className="kit-station-main">
        {href ? (
          <a
            className="kit-station-title is-link"
            href={href}
            onClick={onNavigate ? (e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
              e.preventDefault();
              onNavigate(href);
            } : undefined}
          >
            {title}
          </a>
        ) : <span className="kit-station-title">{title}</span>}
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
      <div className="kit-station-reason" id={`${id}-why`} hidden={!open}>{why}</div>
    </li>
  );
}
