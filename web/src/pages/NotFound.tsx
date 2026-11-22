import { Button, Text } from '../components/kit';
import { t } from '../copy/t';

export function NotFound({ navigate }: { navigate: (href: string) => void }) {
  return (
    <div className="stack">
      <Text variant="title">{t('notFound.title')}</Text>
      <Text>{t('notFound.body')}</Text>
      <div><Button href="/" onClick={() => navigate('/')}>{t('notFound.toMap')}</Button></div>
    </div>
  );
}
