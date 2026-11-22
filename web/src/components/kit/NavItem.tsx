import { LineBullet } from './LineBullet';
import { lineClass, moduleName, type ModuleId } from './modules';

type Props = {
  /** The module this item opens. Leave it out for a plain item (search, the map), which then needs a label. */
  module?: ModuleId;
  /** The words for a plain item, or to replace the module name. */
  label?: string;
  href: string;
  current?: boolean;
  /** The app's name in the chrome: larger type, no bullet. */
  wordmark?: boolean;
  onNavigate?: (href: string) => void;
};

/** 2 · Nav item: bullet + module name. The current item fills with its module colour (C7) and carries aria-current.
 *  A plain item (no module) has no bullet; when current it fills with chrome-ink. */
export function NavItem({ module, label, href, current = false, wordmark = false, onNavigate }: Props) {
  const cls = ['kit-nav', module ? lineClass(module) : 'is-plain', wordmark && 'is-wordmark', current && 'is-current']
    .filter(Boolean).join(' ');
  return (
    <a
      className={cls}
      href={href}
      aria-current={current ? 'page' : undefined}
      onClick={onNavigate ? (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        onNavigate(href);
      } : undefined}
    >
      {module && <LineBullet module={module} size={24} decorative />}
      <span className="kit-nav-name">{label ?? (module ? moduleName(module) : '')}</span>
    </a>
  );
}
