import type { ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

type Props = {
  variant?: ButtonVariant;
  children: ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit';
  disabled?: boolean;
  /** Renders a link that looks like the button. */
  href?: string;
};

/** 5 · Button: ink (primary, one per view), outline (secondary), text link (quiet). 44 px tall. */
export function Button({ variant = 'secondary', children, onClick, type = 'button', disabled = false, href }: Props) {
  const cls = `kit-button is-${variant}`;
  if (href && !disabled) {
    return <a className={cls} href={href}>{children}</a>;
  }
  return (
    <button className={cls} type={type} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
