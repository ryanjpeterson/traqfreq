import { Text } from '../components/kit';
import { t } from '../copy/t';
import { EmptyState } from './ModulePage';

export function Search({ navigate }: { navigate: (href: string) => void }) {
  return (
    <div className="stack">
      <Text variant="title">{t('search.title')}</Text>
      <EmptyState body={t('search.empty')} navigate={navigate} />
    </div>
  );
}
