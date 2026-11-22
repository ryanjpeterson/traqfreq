import type { ReactNode } from 'react';

type Props = {
  label?: string;
  /** The thing the card stands for is switched off: dashed border (L2). */
  off?: boolean;
  children?: ReactNode;
};

/** 10 · Card: card colour, rule border, card radius, 16 px padding, label on top. No shadows. */
export function Card({ label, off = false, children }: Props) {
  return (
    <section className={`kit-card${off ? ' is-off' : ''}`} data-off={off || undefined}>
      {label && <p className="kit-card-label">{label}</p>}
      {children}
    </section>
  );
}
