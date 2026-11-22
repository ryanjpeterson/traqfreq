import type { ReactNode } from 'react';

export type TextVariant = 'title' | 'heading' | 'body' | 'label' | 'note';

type Props = {
  variant?: TextVariant;
  children: ReactNode;
  id?: string;
};

const TAGS = { title: 'h1', heading: 'h2', body: 'p', label: 'p', note: 'p' } as const;

/** 9 · Text: the type scale (title, heading, body, label, note: a small ink2 line, such as where a number comes from); sizes come from tokens only. */
export function Text({ variant = 'body', children, id }: Props) {
  const Tag = TAGS[variant];
  return <Tag className={`kit-text is-${variant}`} id={id}>{children}</Tag>;
}
