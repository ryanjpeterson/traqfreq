import { t } from '../../copy/t';

type Props = {
  title: string;
  artist: string;
  /** Artwork URL. Without it the tile shows an empty square with a word. */
  src?: string;
  musicalKey?: string;
  bpm?: number;
};

/** 11 · Artwork tile: square art, code chip (key and BPM), title, artist. */
export function ArtTile({ title, artist, src, musicalKey, bpm }: Props) {
  const code = [musicalKey, bpm != null ? `${bpm} ${t('kit.bpm')}` : null].filter(Boolean).join(' · ');
  return (
    <figure className="kit-art">
      <div className="kit-art-square">
        {src ? <img src={src} alt="" loading="lazy" /> : <span className="kit-art-none">{t('kit.art.none')}</span>}
        {code && <span className="kit-art-code">{code}</span>}
      </div>
      <figcaption>
        <span className="kit-art-title">{title}</span>
        <span className="kit-art-artist">{artist}</span>
      </figcaption>
    </figure>
  );
}
