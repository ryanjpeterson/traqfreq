import type { ReactNode } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'quiet';

type Props = {
  variant?: ButtonVariant;
  children: ReactNode;
  /** With href, called instead of following the link (client-side navigation); modified clicks still follow it. */
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
    return (
      <a
        className={cls}
        href={href}
        onClick={onClick ? (e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
          e.preventDefault();
          onClick();
        } : undefined}
      >
        {children}
      </a>
    );
  }
  return (
    <button className={cls} type={type} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
